import pytest
from unittest.mock import Mock, patch
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.execution.resource_manager import ResourceManager
from arkumu.importer.services.execution.statistics import ExecutionStatistics

# Test constants
BASE_URI = "http://test.arkumu.org/data"
INSTITUTION = "TEST_INST"

# Standard vocabulary URIs
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"


@pytest.fixture
def mock_statistics():
    """Mock statistics tracker."""
    mock_stats = Mock(spec=ExecutionStatistics)
    # Create a mock current_metrics that has all the numeric attributes as real integers
    # This must match the actual ExecutionMetrics structure
    mock_current_metrics = Mock()
    mock_current_metrics.values_truncated = 0
    mock_current_metrics.triples_created = 0  # Make sure this is a real integer
    mock_current_metrics.resources_created = 0
    mock_current_metrics.values_created = 0  # Add this missing attribute
    mock_current_metrics.rows_processed = 0
    mock_current_metrics.cells_processed = 0
    mock_current_metrics.errors = 0
    mock_current_metrics.warnings = 0
    mock_stats.current_metrics = mock_current_metrics
    return mock_stats


@pytest.fixture
def resource_manager(mock_statistics):
    """ResourceManager with mocked statistics."""
    return ResourceManager(INSTITUTION, BASE_URI, mock_statistics)


@pytest.fixture
def real_resource_manager():
    """ResourceManager with real statistics for integration tests."""
    return ResourceManager(INSTITUTION, BASE_URI)


@pytest.fixture
def initial_data_empty(db):
    """Clear database and create required RDF properties."""
    Resource.objects.all().delete()
    Triple.objects.all().delete()
    # Create standard RDF properties similar to existing test pattern
    Resource.objects.get_or_create(uri=HAS_PART_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=RDF_VALUE_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=DCTERMS_RELATION_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": INSTITUTION})


class TestResourceManagerInitialization:
    """Test ResourceManager initialization."""
    
    def test_initialization_with_defaults(self):
        """Test initialization with default parameters."""
        manager = ResourceManager("test_org", "http://example.com")
        
        assert manager.institution == "test-org"  # Should be slugified
        assert manager.base_uri == "http://example.com"
        assert isinstance(manager.statistics, ExecutionStatistics)
    
    @pytest.mark.django_db
    def test_standard_properties_initialization(self, initial_data_empty):
        """Test that standard RDF properties are created."""
        manager = ResourceManager(INSTITUTION, BASE_URI)
        
        # Standard properties should be created
        assert manager.has_part_prop is not None
        assert manager.rdf_value_prop is not None
        assert manager.dcterms_relation_prop is not None
        
        # Verify they exist in database
        has_part = Resource.objects.get(uri="http://purl.org/dc/terms/hasPart")
        assert has_part.resource_type == ResourceType.PROPERTY
        assert has_part.name == "hasPart"


class TestURIGeneration:
    """Test URI generation methods."""
    
    @pytest.mark.django_db
    def test_generate_dataset_uri(self, resource_manager):
        """Test dataset URI generation."""
        uri = resource_manager.generate_dataset_uri("my_dataset")
        expected = f"{BASE_URI}/test-inst/datasets/my-dataset"
        assert uri == expected
    
    @pytest.mark.django_db
    def test_generate_column_uri(self, resource_manager):
        """Test column URI generation."""
        uri = resource_manager.generate_column_uri("my_dataset", "my_column")
        expected = f"{BASE_URI}/test-inst/datasets/my-dataset/columns/my-column"
        assert uri == expected
    
    @pytest.mark.django_db
    def test_generate_row_uri(self, resource_manager):
        """Test row URI generation."""
        uri = resource_manager.generate_row_uri("my_dataset", "123")
        expected = f"{BASE_URI}/test-inst/datasets/my-dataset/rows/123"
        assert uri == expected
    
    @pytest.mark.django_db
    def test_generate_cell_uri(self, resource_manager):
        """Test cell URI generation."""
        uri = resource_manager.generate_cell_uri("my_dataset", "my_column", "123")
        expected = f"{BASE_URI}/test-inst/datasets/my-dataset/my-column/123"
        assert uri == expected
    
    def test_extract_row_id_from_uri(self, resource_manager):
        """Test extracting row ID from cell URI."""
        cell_uri = f"{BASE_URI}/{INSTITUTION.lower()}/datasets/test/column1/123"
        row_id = resource_manager.extract_row_id_from_uri(cell_uri)
        assert row_id == "123"
        
        # Test invalid URI
        invalid_uri = "invalid"
        row_id = resource_manager.extract_row_id_from_uri(invalid_uri)
        assert row_id == "invalid"
    
    @pytest.mark.django_db
    def test_extract_column_name_from_uri(self, resource_manager):
        """Test extracting column name from cell URI."""
        # Cell URI format: base_uri/institution/datasets/dataset/column/row_id
        cell_uri = f"{BASE_URI}/test-inst/datasets/test/column1/123"  
        column_name = resource_manager.extract_column_name_from_uri(cell_uri)
        assert column_name == "column1"
        
        # Test URI without datasets
        invalid_uri = f"{BASE_URI}/something/else"
        column_name = resource_manager.extract_column_name_from_uri(invalid_uri)
        assert column_name is None


class TestResourceCreation:
    """Test resource creation methods."""
    
    @pytest.mark.django_db
    def test_create_dataset_resource(self, initial_data_empty, resource_manager):
        """Test creating dataset resource."""
        dataset_name = "test_dataset"
        
        resource = resource_manager.create_dataset_resource(dataset_name)
        
        assert resource.name == dataset_name
        assert resource.resource_type == ResourceType.IRI
        assert resource.source == "test-inst"  # Expect slugified institution name
        
        # Should increment statistics
        resource_manager.statistics.increment_resources_created.assert_called_once()
    
    @pytest.mark.django_db
    def test_create_dataset_resource_existing(self, initial_data_empty, resource_manager):
        """Test creating dataset resource that already exists."""
        dataset_name = "test_dataset"
        
        # Create first time
        resource1 = resource_manager.create_dataset_resource(dataset_name)
        
        # Create second time (should get existing)
        resource_manager.statistics.reset_mock()
        resource2 = resource_manager.create_dataset_resource(dataset_name)
        
        assert resource1.id == resource2.id
        # Should not increment statistics for existing resource
        resource_manager.statistics.increment_resources_created.assert_not_called()
    
    @pytest.mark.django_db
    def test_create_column_resources(self, initial_data_empty, resource_manager):
        """Test creating multiple column resources."""
        dataset_name = "test_dataset"
        column_names = ["col1", "col2", "col3"]
        
        column_resources = resource_manager.create_column_resources(dataset_name, column_names)
        
        assert len(column_resources) == 3
        for col_name in column_names:
            assert col_name in column_resources
            assert column_resources[col_name].name == col_name
            assert column_resources[col_name].resource_type == ResourceType.IRI
    
    @pytest.mark.django_db
    def test_create_row_resources(self, initial_data_empty, resource_manager):
        """Test creating multiple row resources."""
        dataset_name = "test_dataset"
        row_ids = {"1", "2", "3"}
        
        row_resources = resource_manager.create_row_resources(dataset_name, row_ids)
        
        assert len(row_resources) == 3
        for row_id in row_ids:
            assert row_id in row_resources
            assert row_resources[row_id].name == f"Row {row_id}"
            assert row_resources[row_id].resource_type == ResourceType.IRI
    
    @pytest.mark.django_db
    def test_create_cell_resources_bulk(self, initial_data_empty, resource_manager):
        """Test bulk creation of cell resources."""
        cell_data = [
            ("dataset1", "col1", "1"),
            ("dataset1", "col2", "1"),
            ("dataset1", "col1", "2")
        ]
        
        cell_resources = resource_manager.create_cell_resources_bulk(cell_data)
        
        assert len(cell_resources) == 3
        for uri, resource in cell_resources.items():
            assert resource.resource_type == ResourceType.IRI
            assert "test-inst" in uri  # Expect slugified institution name in URI
    
    @pytest.mark.django_db
    def test_create_value_resources_bulk(self, initial_data_empty, resource_manager):
        """Test bulk creation of value resources."""
        values = [
            ("value1", "http://www.w3.org/2001/XMLSchema#string"),
            ("value2", "http://www.w3.org/2001/XMLSchema#string"),
            ("123", "http://www.w3.org/2001/XMLSchema#integer")
        ]
        
        value_resources = resource_manager.create_value_resources_bulk(values)
        
        assert len(value_resources) == 3
        assert "value1" in value_resources
        assert value_resources["value1"].resource_type == ResourceType.LITERAL
        assert value_resources["value1"].datatype == "http://www.w3.org/2001/XMLSchema#string"


class TestValueTruncation:
    """Test value truncation functionality."""
    
    def test_truncate_value_if_needed_short_value(self, resource_manager):
        """Test that short values are not truncated."""
        short_value = "This is a short value"
        result = resource_manager._truncate_value_if_needed(short_value)
        assert result == short_value
    
    def test_truncate_value_if_needed_long_value(self, resource_manager):
        """Test that very long values are truncated."""
        # Create a value longer than MAX_INDEXED_VALUE_SIZE
        long_value = "x" * 10000  # Much longer than typical limit
        result = resource_manager._truncate_value_if_needed(long_value)
        
        # Should be truncated and end with "..."
        assert len(result) < len(long_value)
        assert result.endswith("...")
        
        # Should increment truncation counter
        assert resource_manager.statistics.current_metrics.values_truncated > 0


class TestTripleCreation:
    """Test triple creation methods."""
    
    @pytest.mark.django_db
    def test_create_structural_triples_bulk(self, initial_data_empty, resource_manager):
        """Test creating structural triples."""
        # Create resources first
        dataset_resource = resource_manager.create_dataset_resource("test_dataset")
        column_resources = resource_manager.create_column_resources("test_dataset", ["col1", "col2"])
        
        # Create structural triples
        triples = resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources
        )
        
        assert len(triples) == 2  # One for each column
        
        # Verify triples were created in database
        db_triples = Triple.objects.filter(subject=dataset_resource)
        assert db_triples.count() == 2
    
    @pytest.mark.django_db
    def test_create_structural_triples_with_rows(self, initial_data_empty, resource_manager):
        """Test creating structural triples including row resources."""
        dataset_resource = resource_manager.create_dataset_resource("test_dataset")
        column_resources = resource_manager.create_column_resources("test_dataset", ["col1"])
        row_resources = resource_manager.create_row_resources("test_dataset", {"1", "2"})
        
        triples = resource_manager.create_structural_triples_bulk(
            dataset_resource, column_resources, row_resources
        )
        
        # Should include dataset→column and dataset→row triples
        assert len(triples) == 3  # 1 column + 2 rows
    
    @pytest.mark.django_db
    def test_create_value_triples_bulk(self, initial_data_empty, resource_manager):
        """Test creating value triples."""
        # Create cell and value resources
        cell_data = [("dataset1", "col1", "1")]
        cell_resources = resource_manager.create_cell_resources_bulk(cell_data)
        
        value_data = [("test_value", "http://www.w3.org/2001/XMLSchema#string")]
        value_resources = resource_manager.create_value_resources_bulk(value_data)
        
        # Create value triples
        cell_value_pairs = [
            (list(cell_resources.values())[0], value_resources["test_value"])
        ]
        
        triples = resource_manager.create_value_triples_bulk(cell_value_pairs)
        
        assert len(triples) == 1
        assert triples[0].predicate == resource_manager.rdf_value_prop
        
        # Verify statistics were updated
        assert resource_manager.statistics.current_metrics.triples_created > 0
        assert resource_manager.statistics.current_metrics.values_created > 0


class TestUtilityMethods:
    """Test utility methods."""
    
    @pytest.mark.django_db
    def test_get_existing_resources_bulk(self, initial_data_empty, resource_manager):
        """Test bulk fetching of existing resources."""
        # Create some resources
        dataset_resource = resource_manager.create_dataset_resource("test_dataset")
        column_resources = resource_manager.create_column_resources("test_dataset", ["col1", "col2"])
        
        # Get URIs
        uris = [dataset_resource.uri] + [res.uri for res in column_resources.values()]
        
        # Fetch existing resources
        existing = resource_manager.get_existing_resources_bulk(uris)
        
        assert len(existing) == 3
        assert dataset_resource.uri in existing
        for col_resource in column_resources.values():
            assert col_resource.uri in existing
    
    @pytest.mark.django_db
    def test_get_existing_resources_bulk_empty(self, resource_manager):
        """Test bulk fetching with no matching resources."""
        non_existent_uris = ["http://fake.uri/1", "http://fake.uri/2"]
    
        existing = resource_manager.get_existing_resources_bulk(non_existent_uris)
    
        assert isinstance(existing, dict)
        assert len(existing) == 0 