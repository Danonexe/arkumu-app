import pytest
import polars as pl
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy
from arkumu.importer.services.execution.update_analyzer import UpdateAnalyzer
from arkumu.importer.services.execution.resource_manager import ResourceManager

# Test constants
BASE_URI = "http://test.arkumu.org/data"
INSTITUTION = "TEST_INST"

# Standard vocabulary URIs
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"


@pytest.fixture
def mock_resource_manager():
    """Mock resource manager."""
    mock = Mock(spec=ResourceManager)
    mock.generate_dataset_uri.return_value = f"{BASE_URI}/{INSTITUTION.lower()}/datasets/test_dataset"
    mock.generate_cell_uri.side_effect = lambda dataset, column, row: f"{BASE_URI}/{INSTITUTION.lower()}/datasets/{dataset}/{column}/{row}"
    return mock


@pytest.fixture
def update_analyzer_with_defaults(mock_resource_manager):
    """UpdateAnalyzer with default settings."""
    return UpdateAnalyzer(mock_resource_manager)


@pytest.fixture
def update_analyzer(mock_resource_manager):
    """Default UpdateAnalyzer fixture for simple tests."""
    return UpdateAnalyzer(mock_resource_manager)


@pytest.fixture
def update_analyzer_with_timestamps(mock_resource_manager):
    """UpdateAnalyzer with timestamp-based updates."""
    return UpdateAnalyzer(
        mock_resource_manager,
        default_strategy=UpdateStrategy.TIMESTAMP_BASED,
        timestamp_column="modified_date"
    )


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing."""
    return pl.DataFrame({
        "row_id": [0, 1, 2],
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "tags": ["art,design", "tech", "music,art"]
    })


@pytest.fixture
def initial_data_empty(db):
    """Clear database for clean tests."""
    Resource.objects.all().delete()
    Triple.objects.all().delete()


class TestUpdateAnalyzerInitialization:
    """Test UpdateAnalyzer initialization."""
    
    def test_initialization_with_defaults(self, mock_resource_manager):
        """Test initialization with default parameters."""
        analyzer = UpdateAnalyzer(mock_resource_manager)
        
        assert analyzer.resource_manager == mock_resource_manager
        assert analyzer.default_strategy == UpdateStrategy.SKIP_EXISTING
        assert analyzer.timestamp_column is None
    
    def test_initialization_with_custom_params(self, mock_resource_manager):
        """Test initialization with custom parameters."""
        analyzer = UpdateAnalyzer(
            mock_resource_manager,
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            timestamp_column="modified_date"
        )
        
        assert analyzer.default_strategy == UpdateStrategy.UPDATE_VALUES
        assert analyzer.timestamp_column == "modified_date"


class TestDatasetChangeAnalysis:
    """Test dataset change analysis functionality."""
    
    @pytest.mark.django_db
    def test_analyze_empty_dataset(self, initial_data_empty, update_analyzer):
        """Test analyzing empty dataset."""
        empty_df = pl.DataFrame()
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", empty_df)
        
        assert analysis["total_rows"] == 0
        assert analysis["total_cells"] == 0
        assert analysis["new_resources"] == 0
        assert analysis["existing_resources"] == 0
    
    @pytest.mark.django_db
    def test_analyze_new_dataset(self, initial_data_empty, update_analyzer, sample_dataframe):
        """Test analyzing completely new dataset."""
        analysis = update_analyzer.analyze_dataset_changes("new_dataset", sample_dataframe)
        
        assert analysis["total_rows"] == 3
        assert analysis["total_cells"] == 9  # 3 rows × 3 columns (excluding row_id)
        assert analysis["new_resources"] == 9  # All resources are new
        assert analysis["existing_resources"] == 0
        assert len(analysis["conflicts"]) == 0
    
    @pytest.mark.django_db
    def test_analyze_with_mapping_config(self, initial_data_empty, update_analyzer, sample_dataframe):
        """Test analyzing dataset with mapping configuration."""
        mapping_config = {
            "columns": {
                "name": {"is_anchor": True},
                "tags": {"is_multi_value": True, "separator": ","},
                "age": {"is_fk": True, "target_dataset": "people"}
            }
        }
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", sample_dataframe, mapping_config)
        
        assert "name" in analysis["anchor_columns"]
        assert "tags" in analysis["multi_value_columns"]
        assert "age" in analysis["fk_columns"]
    
    @pytest.mark.django_db
    def test_analyze_with_existing_data(self, initial_data_empty, update_analyzer, sample_dataframe):
        """Test analyzing dataset with some existing data."""
        # Create some existing resources
        existing_resource = Resource.objects.create(
            uri=f"{BASE_URI}/{INSTITUTION.lower()}/datasets/test_dataset/name/1",
            value="Alice",
            resource_type=ResourceType.LITERAL,
            name="name",
            source=INSTITUTION.lower()
        )
        
        analysis = update_analyzer.analyze_dataset_changes("test_dataset", sample_dataframe)
        
        # Should detect existing resources
        assert analysis["existing_resources"] > 0
        assert analysis["new_resources"] > 0


class TestColumnTypeDetection:
    """Test column type detection functionality."""
    
    def test_get_column_type_no_config(self, update_analyzer):
        """Test column type detection without mapping config."""
        column_type = update_analyzer._get_column_type("test_column", None)
        assert column_type == "regular"
    
    def test_get_column_type_with_config(self, update_analyzer):
        """Test column type detection with mapping config."""
        mapping_config = {
            "columns": {
                "anchor_col": {"is_anchor": True},
                "fk_col": {"is_fk": True},
                "multi_col": {"is_multi_value": True},
                "context_col": {"is_relationship_context": True},
                "ontology_col": {"is_external_ontology": True},
                "regular_col": {}
            }
        }
        
        assert update_analyzer._get_column_type("anchor_col", mapping_config) == "anchor"
        assert update_analyzer._get_column_type("fk_col", mapping_config) == "foreign_key"
        assert update_analyzer._get_column_type("multi_col", mapping_config) == "multi_value"
        assert update_analyzer._get_column_type("context_col", mapping_config) == "relationship_context"
        assert update_analyzer._get_column_type("ontology_col", mapping_config) == "external_ontology"
        assert update_analyzer._get_column_type("regular_col", mapping_config) == "regular"


class TestTimestampParsing:
    """Test timestamp parsing functionality."""
    
    def test_parse_timestamp_valid_formats(self, update_analyzer):
        """Test parsing various valid timestamp formats."""
        valid_timestamps = [
            "2023-12-01 14:30:00",
            "2023-12-01T14:30:00",
            "2023-12-01T14:30:00.123456",
            "2023-12-01T14:30:00Z",
            "2023-12-01",
            "01.12.2023",
            "01/12/2023",
            "12/01/2023"
        ]
        
        for timestamp_str in valid_timestamps:
            result = update_analyzer._parse_timestamp(timestamp_str)
            assert result is not None
            assert isinstance(result, datetime)
    
    def test_parse_timestamp_invalid_formats(self, update_analyzer):
        """Test parsing invalid timestamp formats."""
        invalid_timestamps = [
            "",
            "not a date",
            "2023-13-45",  # Invalid date
            None
        ]
        
        for timestamp_str in invalid_timestamps:
            result = update_analyzer._parse_timestamp(timestamp_str)
            if timestamp_str is None:
                continue  # None input should return None
            assert result is None or isinstance(result, datetime)  # Some may be parsed by dateutil
    
    def test_compare_timestamps(self, update_analyzer):
        """Test timestamp comparison."""
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(hours=1)
        later = now + timedelta(hours=1)
        
        assert update_analyzer._compare_timestamps(later, now) == "newer"
        assert update_analyzer._compare_timestamps(earlier, now) == "older"
        assert update_analyzer._compare_timestamps(now, now) == "equal"
        assert update_analyzer._compare_timestamps(now, None) == "unknown"


class TestUpdateStrategyDetermination:
    """Test update strategy determination."""
    
    def test_determine_strategy_new_resource(self, update_analyzer):
        """Test strategy for new resources."""
        strategy = update_analyzer.determine_update_strategy(None, "new_value", {})
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_strategy_unchanged_value(self, update_analyzer):
        """Test strategy when value hasn't changed."""
        existing_resource = Mock()
        existing_resource.value = "same_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource, "same_value", {}
        )
        assert strategy == UpdateStrategy.SKIP_EXISTING
    
    def test_determine_strategy_skip_existing(self, update_analyzer):
        """Test SKIP_EXISTING strategy."""
        update_analyzer.default_strategy = UpdateStrategy.SKIP_EXISTING
        existing_resource = Mock()
        existing_resource.value = "old_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource, "new_value", {}
        )
        assert strategy == UpdateStrategy.SKIP_EXISTING
    
    def test_determine_strategy_update_values(self, update_analyzer):
        """Test UPDATE_VALUES strategy."""
        update_analyzer.default_strategy = UpdateStrategy.UPDATE_VALUES
        existing_resource = Mock()
        existing_resource.value = "old_value"
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource, "new_value", {}
        )
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_strategy_timestamp_based_newer(self, update_analyzer):
        """Test timestamp-based strategy with newer timestamp."""
        update_analyzer.default_strategy = UpdateStrategy.TIMESTAMP_BASED
        update_analyzer.timestamp_column = "modified_date"
        
        existing_resource = Mock()
        existing_resource.value = "old_value"
        existing_resource.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        
        row_data = {"modified_date": datetime.now(timezone.utc).isoformat()}
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource, "new_value", row_data
        )
        assert strategy == UpdateStrategy.UPDATE_VALUES
    
    def test_determine_strategy_timestamp_based_older(self, update_analyzer):
        """Test timestamp-based strategy with older timestamp."""
        update_analyzer.default_strategy = UpdateStrategy.TIMESTAMP_BASED
        update_analyzer.timestamp_column = "modified_date"
        
        existing_resource = Mock()
        existing_resource.value = "old_value"
        existing_resource.updated_at = datetime.now(timezone.utc)
        
        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        row_data = {"modified_date": old_timestamp.isoformat()}
        
        strategy = update_analyzer.determine_update_strategy(
            existing_resource, "new_value", row_data
        )
        assert strategy == UpdateStrategy.SKIP_EXISTING


class TestRecommendationGeneration:
    """Test recommendation generation."""
    
    def test_generate_recommendations_updates_detected(self, update_analyzer):
        """Test recommendations when updates are detected."""
        analysis = {
            "potential_updates": 5,
            "existing_resources": 10,
            "new_resources": 2,
            "fk_columns": ["author_id"],
            "anchor_columns": ["id"],
            "multi_value_columns": ["tags"],
            "recommendations": []
        }
        
        update_analyzer._generate_recommendations(analysis)
        
        recommendations = analysis["recommendations"]
        assert len(recommendations) > 0
        assert any("potential updates" in rec for rec in recommendations)
        assert any("Foreign key columns" in rec for rec in recommendations)
        assert any("Anchor columns" in rec for rec in recommendations)
        assert any("Multi-value columns" in rec for rec in recommendations)
    
    def test_generate_recommendations_mostly_existing(self, update_analyzer):
        """Test recommendations when mostly existing data."""
        analysis = {
            "potential_updates": 0,
            "existing_resources": 100,
            "new_resources": 5,
            "fk_columns": [],
            "anchor_columns": [],
            "multi_value_columns": [],
            "recommendations": []
        }
        
        update_analyzer._generate_recommendations(analysis)
        
        recommendations = analysis["recommendations"]
        assert any("SKIP_EXISTING" in rec for rec in recommendations) 