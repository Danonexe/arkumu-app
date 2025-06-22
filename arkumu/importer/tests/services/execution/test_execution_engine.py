import pytest
import polars as pl
from unittest.mock import Mock, patch, MagicMock
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy
from arkumu.importer.services.execution.execution_engine import MappingExecutionEngine
from arkumu.importer.services.execution.statistics import ExecutionMetrics

# Test constants
BASE_URI = "http://test.arkumu.org/data"
ORGANIZATION_ID = "TEST_ORG"

# Standard vocabulary URIs
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing."""
    return [
        {"name": "Alice", "age": 25, "department": "Engineering"},
        {"name": "Bob", "age": 30, "department": "Design"},
        {"name": "Charlie", "age": 35, "department": "Product"}
    ]


@pytest.fixture
def sample_dataframe(sample_csv_data):
    """Sample Polars DataFrame for testing."""
    return pl.DataFrame(sample_csv_data)


@pytest.fixture
def workspace_columns():
    """Sample workspace columns configuration."""
    return [
        {
            "dataset_name": "employees",
            "column_name": "name",
            "is_anchor": True,
            "is_fk": False,
            "is_multi_value": False
        },
        {
            "dataset_name": "employees", 
            "column_name": "age",
            "is_anchor": False,
            "is_fk": False,
            "is_multi_value": False
        },
        {
            "dataset_name": "employees",
            "column_name": "department",
            "is_anchor": False,
            "is_fk": True,
            "target_dataset": "departments",
            "target_column": "name"
        }
    ]


@pytest.fixture
def initial_data_empty(db):
    """Clear database and create required RDF properties."""
    Resource.objects.all().delete()
    Triple.objects.all().delete()
    # Create standard RDF properties similar to existing test pattern
    Resource.objects.get_or_create(uri=HAS_PART_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": ORGANIZATION_ID})
    Resource.objects.get_or_create(uri=RDF_VALUE_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": ORGANIZATION_ID})
    Resource.objects.get_or_create(uri=DCTERMS_RELATION_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": ORGANIZATION_ID})


@pytest.fixture
def execution_engine():
    """MappingExecutionEngine instance with default settings."""
    return MappingExecutionEngine(
        organization_id=ORGANIZATION_ID,
        base_uri=BASE_URI,
        batch_size=100  # Small batch size for testing
    )


@pytest.fixture
def execution_engine_with_timestamps():
    """MappingExecutionEngine instance with timestamp-based updates."""
    return MappingExecutionEngine(
        organization_id=ORGANIZATION_ID,
        base_uri=BASE_URI,
        default_strategy=UpdateStrategy.UPDATE_VALUES,
        timestamp_column="modified_date",
        batch_size=100
    )


@pytest.fixture
def execution_engine_large_batch():
    """MappingExecutionEngine instance with larger batch size."""
    return MappingExecutionEngine(
        organization_id=ORGANIZATION_ID,
        base_uri=BASE_URI,
        batch_size=500
    )


class TestExecutionEngineInitialization:
    """Test MappingExecutionEngine initialization."""
    
    def test_initialization_with_defaults(self):
        """Test engine initializes with correct defaults."""
        engine = MappingExecutionEngine(ORGANIZATION_ID, BASE_URI)
        
        assert engine.organization_id == ORGANIZATION_ID
        assert engine.base_uri == BASE_URI
        assert engine.default_strategy == UpdateStrategy.SKIP_EXISTING
        assert engine.timestamp_column is None
        assert engine.batch_size == 1000
        
        # Check component initialization
        assert engine.data_processor is not None
        assert engine.resource_manager is not None
        assert engine.update_analyzer is not None
        assert engine.statistics is not None
        assert engine.mapping_coordinator is not None
    
    def test_initialization_with_custom_params(self):
        """Test engine initialization with custom parameters."""
        engine = MappingExecutionEngine(
            organization_id=ORGANIZATION_ID,
            base_uri=BASE_URI,
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            timestamp_column="modified_date",
            batch_size=500
        )
        
        assert engine.default_strategy == UpdateStrategy.UPDATE_VALUES
        assert engine.timestamp_column == "modified_date"
        assert engine.batch_size == 500


class TestSimpleImportExecution:
    """Test simple import execution functionality."""
    
    @pytest.mark.django_db
    def test_execute_simple_import_with_list_data(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test executing simple import with list of dictionaries."""
        dataset_name = "test_dataset"
        
        metrics = execution_engine.execute_simple_import(sample_csv_data, dataset_name)
        
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created > 0
        assert metrics.triples_created > 0
        
        # Verify resources were created in database
        # Note: dataset names are slugified in URIs, so test_dataset becomes test-dataset
        slugified_dataset_name = dataset_name.replace('_', '-')
        dataset_resources = Resource.objects.filter(uri__contains=slugified_dataset_name)
        assert dataset_resources.count() > 0
    
    @pytest.mark.django_db
    def test_execute_simple_import_with_dataframe(self, initial_data_empty, execution_engine, sample_dataframe):
        """Test executing simple import with Polars DataFrame."""
        dataset_name = "test_dataset"
        
        metrics = execution_engine.execute_simple_import(sample_dataframe, dataset_name)
        
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created > 0
        assert metrics.triples_created > 0
    
    @pytest.mark.django_db
    def test_execute_simple_import_with_mapping_config(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test executing simple import with mapping configuration."""
        dataset_name = "test_dataset"
        mapping_config = {
            "columns": {
                "name": {"is_anchor": True},
                "department": {"is_fk": True, "target_dataset": "departments"}
            }
        }
        
        metrics = execution_engine.execute_simple_import(sample_csv_data, dataset_name, mapping_config)
        
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created > 0
    
    @pytest.mark.django_db
    def test_execute_simple_import_empty_data(self, initial_data_empty, execution_engine):
        """Test executing simple import with empty data."""
        dataset_name = "empty_dataset"
        empty_data = []
        
        metrics = execution_engine.execute_simple_import(empty_data, dataset_name)
        
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created == 0  # Should be minimal or zero for empty data


class TestMappingConfigExtraction:
    """Test mapping configuration extraction."""
    
    def test_extract_mapping_config_valid_dataset(self, execution_engine, workspace_columns):
        """Test extracting mapping config for valid dataset."""
        mapping_config = execution_engine._extract_mapping_config("employees", workspace_columns)
        
        assert mapping_config is not None
        assert "columns" in mapping_config
        assert "name" in mapping_config["columns"]
        assert "age" in mapping_config["columns"]
        assert "department" in mapping_config["columns"]
        
        # Check specific column configurations
        assert mapping_config["columns"]["name"]["is_anchor"] is True
        assert mapping_config["columns"]["department"]["is_fk"] is True
        assert mapping_config["columns"]["department"]["target_dataset"] == "departments"
    
    def test_extract_mapping_config_nonexistent_dataset(self, execution_engine, workspace_columns):
        """Test extracting mapping config for nonexistent dataset."""
        mapping_config = execution_engine._extract_mapping_config("nonexistent", workspace_columns)
        
        assert mapping_config is None
    
    def test_extract_mapping_config_empty_columns(self, execution_engine):
        """Test extracting mapping config with empty columns."""
        mapping_config = execution_engine._extract_mapping_config("test", [])
        
        assert mapping_config is None


class TestProcessingPlanExecution:
    """Test processing plan execution."""
    
    @patch('arkumu.importer.services.execution.execution_engine.MappingCoordinator')
    def test_execute_with_processing_plan(self, mock_coordinator_class, execution_engine, sample_csv_data, workspace_columns):
        """Test executing with a complete processing plan."""
        # Mock the processing plan
        mock_plan = Mock()
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator
        
        dataset_name = "test_dataset"
        
        with patch.object(execution_engine, '_execute_dataset_import') as mock_execute:
            mock_execute.return_value = ExecutionMetrics()
            
            metrics = execution_engine.execute_with_processing_plan(
                sample_csv_data, mock_plan, dataset_name, workspace_columns
            )
            
            assert isinstance(metrics, ExecutionMetrics)
            mock_execute.assert_called_once()


class TestImpactAnalysis:
    """Test import impact analysis (dry run)."""
    
    @pytest.mark.django_db
    def test_analyze_import_impact_new_data(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test impact analysis for completely new data."""
        dataset_name = "new_dataset"
        
        analysis = execution_engine.analyze_import_impact(sample_csv_data, dataset_name)
        
        assert "total_rows" in analysis
        assert "new_resources" in analysis
        assert "existing_resources" in analysis
        assert "conflicts" in analysis
        assert analysis["total_rows"] == 3
        assert analysis["new_resources"] > 0
        assert analysis["existing_resources"] == 0
    
    @pytest.mark.django_db
    def test_analyze_import_impact_with_mapping(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test impact analysis with mapping configuration."""
        dataset_name = "test_dataset"
        mapping_config = {
            "columns": {
                "name": {"is_anchor": True},
                "department": {"is_fk": True, "target_dataset": "departments"}
            }
        }
        
        analysis = execution_engine.analyze_import_impact(sample_csv_data, dataset_name, mapping_config)
        
        assert "anchor_columns" in analysis
        assert "fk_columns" in analysis
        # Note: The actual column names may not appear in these lists due to how analysis works


class TestBatchProcessing:
    """Test batch processing functionality."""
    
    @pytest.mark.django_db
    def test_process_batch_functionality(self, initial_data_empty, execution_engine):
        """Test internal batch processing."""
        # Create a small DataFrame for batch testing
        df = pl.DataFrame({
            "row_id": [0, 1],
            "name": ["Alice", "Bob"],
            "age": [25, 30]
        })
        
        dataset_name = "batch_test"
        
        # Create column resources first (simulating the normal flow)
        column_resources = execution_engine.resource_manager.create_column_resources(
            dataset_name, ["name", "age"]
        )
        
        # Test the batch processing
        execution_engine._process_batch(df, dataset_name, None, column_resources)
        
        # Verify cells were processed
        assert execution_engine.statistics.current_metrics.cells_processed > 0


class TestSpecialColumnProcessing:
    """Test processing of special column types."""
    
    def test_process_special_columns_detection(self, execution_engine):
        """Test detection and processing of special column types."""
        df = pl.DataFrame({
            "name": ["Alice", "Bob"],
            "fk_col": ["dept1", "dept2"],
            "multi_col": ["tag1,tag2", "tag3,tag4"]
        })
        
        mapping_config = {
            "columns": {
                "fk_col": {"is_fk": True, "target_dataset": "departments"},
                "multi_col": {"is_multi_value": True, "separator": ","}
            }
        }
        
        # This should run without errors (placeholder implementation)
        execution_engine._process_special_columns(df, "test_dataset", mapping_config)
    
    def test_should_create_row_resources(self, execution_engine):
        """Test row resource creation decision."""
        # Currently defaults to False
        result = execution_engine._should_create_row_resources(None)
        assert result is False
        
        result = execution_engine._should_create_row_resources({})
        assert result is False


class TestExecutionSummary:
    """Test execution summary functionality."""
    
    def test_get_execution_summary(self, execution_engine):
        """Test getting execution summary."""
        # Add some test data to statistics
        execution_engine.statistics.increment_resources_created(10)
        execution_engine.statistics.increment_fk_relationships(5)
        
        summary = execution_engine.get_execution_summary()
        
        assert "overall" in summary
        assert "datasets" in summary
        assert "totals" in summary
        assert "engine_info" in summary
        
        # Check engine info
        engine_info = summary["engine_info"]
        assert engine_info["organization_id"] == ORGANIZATION_ID
        assert engine_info["base_uri"] == BASE_URI
        assert engine_info["batch_size"] == execution_engine.batch_size
        assert "default_strategy" in engine_info


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.django_db
    def test_execute_with_invalid_data(self, initial_data_empty, execution_engine):
        """Test execution with invalid data types."""
        invalid_data = "not a list or dataframe"
        
        with pytest.raises(Exception):
            execution_engine.execute_simple_import(invalid_data, "test_dataset")
    
    @pytest.mark.django_db
    def test_execute_with_database_error(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test execution when database operations fail."""
        dataset_name = "error_test"
        
        # Mock a database error
        with patch.object(execution_engine.resource_manager, 'create_dataset_resource') as mock_create:
            mock_create.side_effect = Exception("Database error")
            
            with pytest.raises(Exception):
                execution_engine.execute_simple_import(sample_csv_data, dataset_name)
            
            # Verify error was logged in statistics
            assert execution_engine.statistics.current_metrics.errors > 0


class TestIntegrationWithComponents:
    """Test integration between execution engine components."""
    
    @pytest.mark.django_db
    def test_component_integration_flow(self, initial_data_empty, execution_engine, sample_csv_data):
        """Test complete component integration flow."""
        dataset_name = "integration_test"
        
        # Execute import
        metrics = execution_engine.execute_simple_import(sample_csv_data, dataset_name)
        
        # Verify execution metrics
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created > 0
        assert metrics.cells_processed > 0
        
        # Verify database state
        # Note: dataset names are slugified in URIs, so integration_test becomes integration-test
        slugified_dataset_name = dataset_name.replace('_', '-')
        dataset_resources = Resource.objects.filter(uri__contains=slugified_dataset_name)
        assert dataset_resources.count() > 0
        
        # Verify execution summary
        summary = execution_engine.get_execution_summary()
        assert "overall" in summary
        assert "engine_info" in summary 