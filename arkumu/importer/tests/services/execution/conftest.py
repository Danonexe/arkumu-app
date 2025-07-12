"""
Pytest configuration for execution layer tests.
Provides fixtures specific to execution engine components.

Also imports shared fixtures from staged_tests for the legacy integration test.
"""
import pytest
import polars as pl
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from typing import Dict, List, Any

from arkumu.common.enums import UpdateStrategy
from arkumu.metadata.models import Resource
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.importer.services.execution.statistics import ExecutionStatistics, ExecutionMetrics
from arkumu.importer.services.execution.resource_manager import ResourceManager
from arkumu.importer.services.execution.data_processor import DataProcessor
from arkumu.importer.services.execution.update_analyzer import UpdateAnalyzer
from arkumu.importer.services.execution.execution_engine import MappingExecutionEngine
from arkumu.importer.services.execution.chunked_processor import StreamingConfig, ChunkedProcessor
from arkumu.importer.services.mapping_consumer import ExecutionConfig, DatasetConfig, ColumnConfig, ColumnType, ProcessingStrategy


@pytest.fixture
def test_organization_code():
    """Test organization code"""
    return "TEST_ORG"


@pytest.fixture
def test_base_uri():
    """Test base URI"""
    return "http://arkumu.test.org/data"


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing"""
    return [
        {"name": "John Doe", "age": "30", "city": "New York"},
        {"name": "Jane Smith", "age": "25", "city": "Los Angeles"},
        {"name": "Bob Johnson", "age": "35", "city": "Chicago"},
        {"name": "", "age": "40", "city": "Boston"},  # Empty name
        {"name": "Alice Brown", "age": "", "city": "Seattle"},  # Empty age
    ]


@pytest.fixture
def sample_polars_df():
    """Sample Polars DataFrame for testing"""
    return pl.DataFrame([
        {"name": "John Doe", "age": 30, "city": "New York", "salary": 50000.0},
        {"name": "Jane Smith", "age": 25, "city": "Los Angeles", "salary": 60000.0},
        {"name": "Bob Johnson", "age": 35, "city": "Chicago", "salary": 55000.0},
    ])


@pytest.fixture
def large_csv_data():
    """Large CSV data for chunked processing tests"""
    data = []
    for i in range(1000):
        data.append({
            "id": str(i + 1),
            "name": f"Person {i + 1}",
            "age": str(20 + (i % 50)),
            "department": f"Dept {(i % 10) + 1}",
            "email": f"person{i + 1}@example.com"
        })
    return data


@pytest.fixture
def unicode_csv_data():
    """CSV data with Unicode characters for normalization testing"""
    return [
        {"name": "José García", "city": "São Paulo", "notes": "Café"},
        {"name": "François Müller", "city": "Zürich", "notes": "naïve"},
        {"name": "北京用户", "city": "北京", "notes": "测试数据"},
    ]


@pytest.fixture
def multi_value_csv_data():
    """CSV data with multi-value fields"""
    return [
        {"name": "John", "skills": "Python,Java,SQL", "hobbies": "reading;swimming"},
        {"name": "Jane", "skills": "R,Statistics", "hobbies": "hiking;photography;cooking"},
        {"name": "Bob", "skills": "JavaScript", "hobbies": "gaming"},
    ]


@pytest.fixture
def execution_statistics():
    """Fresh execution statistics instance"""
    return ExecutionStatistics()


@pytest.fixture
def execution_metrics():
    """Sample execution metrics"""
    metrics = ExecutionMetrics()
    metrics.start_time = datetime.now(timezone.utc)
    metrics.rows_processed = 100
    metrics.cells_processed = 300
    metrics.resources_created = 250
    metrics.triples_created = 400
    metrics.values_created = 300
    return metrics


@pytest.fixture
def data_processor():
    """DataProcessor instance for testing"""
    return DataProcessor(multi_value_threshold=0.2)


@pytest.fixture
def resource_manager(test_organization_code, test_base_uri, execution_statistics):
    """ResourceManager instance for testing"""
    return ResourceManager(
        institution=test_organization_code,
        base_uri=test_base_uri,
        statistics=execution_statistics
    )


@pytest.fixture
def update_analyzer(resource_manager):
    """UpdateAnalyzer instance for testing"""
    return UpdateAnalyzer(
        resource_manager=resource_manager,
        default_strategy=UpdateStrategy.SKIP_EXISTING,
        timestamp_column="updated_at"
    )


@pytest.fixture
def execution_engine(test_organization_code, test_base_uri):
    """MappingExecutionEngine instance for testing"""
    return MappingExecutionEngine(
        organization_id=test_organization_code,
        base_uri=test_base_uri,
        default_strategy=UpdateStrategy.UPDATE_VALUES,
        batch_size=50  # Smaller batch for testing
    )


@pytest.fixture
def streaming_config():
    """StreamingConfig for chunked processing tests"""
    return StreamingConfig(
        chunk_size=100,  # Small chunks for testing
        max_memory_mb=50,
        enable_gc=True,
        persist_chunks=True,
        max_pending_relationships=1000
    )


@pytest.fixture
def chunked_processor(test_organization_code, test_base_uri, streaming_config):
    """ChunkedProcessor instance for testing"""
    return ChunkedProcessor(
        institution=test_organization_code,
        base_uri=test_base_uri,
        streaming_config=streaming_config
    )


@pytest.fixture
def simple_mapping_config():
    """Simple mapping configuration for testing"""
    return {
        "columns": {
            "name": {
                "is_anchor": False,
                "is_fk": False,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            },
            "age": {
                "is_anchor": False,
                "is_fk": False,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#integer"
            }
        }
    }


@pytest.fixture
def complex_mapping_config():
    """Complex mapping configuration with FK and multi-value columns"""
    return {
        "columns": {
            "person_id": {
                "is_anchor": True,
                "is_fk": False,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            },
            "name": {
                "is_anchor": False,
                "is_fk": False,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            },
            "department_id": {
                "is_anchor": False,
                "is_fk": True,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "target_dataset": "departments",
                "target_column": "dept_id",
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            },
            "skills": {
                "is_anchor": False,
                "is_fk": False,
                "is_multi_value": True,
                "is_relationship_context": False,
                "is_external_ontology": False,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            },
            "orcid": {
                "is_anchor": False,
                "is_fk": False,
                "is_multi_value": False,
                "is_relationship_context": False,
                "is_external_ontology": True,
                "separator": ",",
                "datatype": "http://www.w3.org/2001/XMLSchema#string"
            }
        }
    }


@pytest.fixture
def workspace_columns():
    """Sample workspace columns configuration"""
    return [
        {
            "dataset_name": "people",
            "column_name": "name",
            "is_anchor": False,
            "is_fk": False,
            "is_multi_value": False,
            "is_relationship_context": False,
            "is_external_ontology": False,
            "separator": ","
        },
        {
            "dataset_name": "people",
            "column_name": "age",
            "is_anchor": False,
            "is_fk": False,
            "is_multi_value": False,
            "is_relationship_context": False,
            "is_external_ontology": False,
            "separator": ","
        }
    ]


@pytest.fixture
def execution_config_simple():
    """Simple execution configuration for mapping-aware processor"""
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="test_mapping",
        organization="test_org",
        datasets=[
            DatasetConfig(
                dataset_name="test_dataset",
                columns=[
                    ColumnConfig(
                        column_name="name",
                        dataset_name="test_dataset",
                        column_type=ColumnType.REGULAR,
                        arkumu_type="name",
                        datatype="http://www.w3.org/2001/XMLSchema#string",
                        is_anchor=False,
                        is_multi_value=False,
                        multi_value_separator=",",
                        is_external_ontology=False,
                        external_ontology_config=None
                    ),
                    ColumnConfig(
                        column_name="age",
                        dataset_name="test_dataset",
                        column_type=ColumnType.REGULAR,
                        arkumu_type="age",
                        datatype="http://www.w3.org/2001/XMLSchema#integer",
                        is_anchor=False,
                        is_multi_value=False,
                        multi_value_separator=",",
                        is_external_ontology=False,
                        external_ontology_config=None
                    )
                ]
            )
        ],
        fk_relationships=[],
        relationship_contexts=[],
        processing_strategy=ProcessingStrategy.ENTITY_CENTRIC
    )


@pytest.fixture
def mock_django_db():
    """Mock Django database operations"""
    with patch('arkumu.metadata.models.Resource.objects') as mock_resource_objects, \
         patch('arkumu.metadata.models.triples.Triple.objects') as mock_triple_objects:
        
        # Mock resource creation
        mock_resource = Mock(spec=Resource)
        mock_resource.id = 1
        mock_resource.uri = "test://resource"
        mock_resource._meta = Resource._meta
        mock_resource._state = Mock()
        mock_resource._state.db = 'default'
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        
        # Mock triple creation
        mock_triple = Mock(spec=Triple)
        mock_triple.id = 1
        mock_triple._meta = Triple._meta
        mock_triple._state = Mock()
        mock_triple._state.db = 'default'
        mock_triple_objects.bulk_create.return_value = []
        mock_triple_objects.get_or_create.return_value = (mock_triple, True)
        
        yield {
            'resource_objects': mock_resource_objects,
            'triple_objects': mock_triple_objects
        }


@pytest.fixture
def test_resources():
    """Pre-created test resources for testing"""
    resources = {}
    
    # Create dataset resource
    dataset_resource = Mock(spec=Resource)
    dataset_resource.id = 1
    dataset_resource.uri = "http://arkumu.test.org/data/test-org/datasets/test-dataset"  # Slugified URIs
    dataset_resource.resource_type = ResourceType.IRI
    dataset_resource.name = "test_dataset"
    dataset_resource._meta = Resource._meta
    dataset_resource._state = Mock()
    dataset_resource._state.db = 'default'
    resources['dataset'] = dataset_resource
    
    # Create column resources
    name_column = Mock(spec=Resource)
    name_column.id = 2
    name_column.uri = "http://arkumu.test.org/data/test-org/datasets/test-dataset/columns/name"  # Slugified URIs
    name_column.resource_type = ResourceType.IRI
    name_column.name = "name"
    name_column._meta = Resource._meta
    name_column._state = Mock()
    name_column._state.db = 'default'
    resources['name_column'] = name_column
    
    age_column = Mock(spec=Resource)
    age_column.id = 3
    age_column.uri = "http://arkumu.test.org/data/test-org/datasets/test-dataset/columns/age"  # Slugified URIs
    age_column.resource_type = ResourceType.IRI
    age_column.name = "age"
    age_column._meta = Resource._meta
    age_column._state = Mock()
    age_column._state.db = 'default'
    resources['age_column'] = age_column
    
    return resources


@pytest.fixture
def error_csv_data():
    """CSV data that should trigger various error conditions"""
    return [
        {"": "value"},  # Empty column name
        {"name": None, "age": "invalid"},  # None value and invalid age
        {"name": "a" * 2000, "age": "25"},  # Very long name
    ]


@pytest.fixture
def timestamp_csv_data():
    """CSV data with timestamp columns for update analysis"""
    return [
        {
            "id": "1",
            "name": "John Doe",
            "updated_at": "2023-01-01 10:00:00"
        },
        {
            "id": "2", 
            "name": "Jane Smith",
            "updated_at": "2023-01-02 15:30:00"
        },
        {
            "id": "3",
            "name": "Bob Johnson", 
            "updated_at": "2023-01-03 09:15:00"
        }
    ]


@pytest.fixture
def mock_mapping_coordinator():
    """Mock mapping coordinator for testing"""
    mock_coordinator = Mock()
    mock_coordinator.process_fk_dependencies.return_value = Mock()
    mock_coordinator.get_processing_plan.return_value = Mock()
    return mock_coordinator


@pytest.fixture
def performance_test_data():
    """Large dataset for performance testing"""
    import random
    import string
    
    data = []
    for i in range(10000):
        name = ''.join(random.choices(string.ascii_letters, k=10))
        age = random.randint(18, 80)
        salary = random.randint(30000, 150000)
        data.append({
            "id": str(i + 1),
            "name": name,
            "age": str(age),
            "salary": str(salary),
            "department": f"Dept_{i % 20}",
            "skills": ','.join(random.choices(['Python', 'Java', 'SQL', 'R', 'JavaScript'], k=random.randint(1, 3)))
        })
    return data


@pytest.fixture(autouse=True)
def reset_execution_stats():
    """Reset execution statistics before each test"""
    # This ensures each test starts with fresh statistics
    yield
    # Cleanup after test if needed


# Import shared fixtures from staged_tests for legacy integration test
try:
    from .staged_tests.conftest import (
        fuk_mapping_from_s3,
        production_test_mapping,
        real_csv_data,
        bucket_service,
        mapping_adapter,
        EXPECTED_FUK_CSV_FILES
    )
except ImportError:
    # Fixtures not available if staged_tests directory doesn't exist
    pass