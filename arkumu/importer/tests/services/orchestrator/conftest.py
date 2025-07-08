"""
Pytest configuration for orchestrator tests.
Provides fixtures specific to orchestration layer testing.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
from arkumu.importer.services.mapping_consumer import ExecutionConfig, DatasetConfig, ColumnConfig, FKRelationship
from arkumu.importer.services.orchestrator import (
    ImportOrchestrator, ProcessingStrategy, ProgressTracker, 
    ResultAggregator, ImportResult, ProgressUpdate, AggregatedResult
)


@pytest.fixture
def mock_mapping_adapter():
    """Mock mapping adapter for orchestrator tests"""
    mock_adapter = Mock()
    
    # Mock mapping info
    mock_adapter.get_mapping_info.return_value = Mock(
        id=1,
        name='Test Mapping',
        organization='TEST_ORG'
    )
    
    # Mock validation result
    mock_adapter.validate_mapping.return_value = Mock(
        is_valid=True,
        errors=[],
        warnings=[]
    )
    
    # Mock execution config
    execution_config = Mock(spec=ExecutionConfig)
    execution_config.mapping_id = 1
    execution_config.mapping_name = 'Test Mapping'
    execution_config.datasets = []
    execution_config.column_configurations = []
    execution_config.fk_relationships = []
    
    mock_adapter.translate_to_execution_config.return_value = execution_config
    
    return mock_adapter


@pytest.fixture
def mock_execution_engine():
    """Mock execution engine for orchestrator tests"""
    mock_engine = Mock()
    
    # Mock execution stats
    mock_stats = Mock()
    mock_stats.resources_created = 100
    mock_stats.triples_created = 500
    mock_stats.rows_processed = 50
    mock_stats.cells_processed = 200
    mock_stats.execution_time = 30.5
    mock_stats.errors = 0
    
    mock_engine.execute_simple_import.return_value = mock_stats
    
    return mock_engine


@pytest.fixture
def sample_execution_config():
    """Sample execution configuration for testing"""
    dataset_config = Mock(spec=DatasetConfig)
    dataset_config.dataset_name = 'test_dataset'
    dataset_config.columns = []
    dataset_config.dependencies = []
    
    config = Mock(spec=ExecutionConfig)
    config.mapping_id = 1
    config.mapping_name = 'Test Mapping'
    config.datasets = [dataset_config]
    config.column_configurations = []
    config.fk_relationships = []
    
    return config


@pytest.fixture
def sample_csv_sources():
    """Sample CSV data sources for testing"""
    return {
        'test_dataset': [
            ['name', 'age', 'location'],
            ['John Doe', '30', 'New York'],
            ['Jane Smith', '25', 'Los Angeles'],
            ['Bob Johnson', '35', 'Chicago']
        ],
        'second_dataset': [
            ['id', 'title', 'category'],
            ['1', 'Project A', 'Research'],
            ['2', 'Project B', 'Development']
        ]
    }


@pytest.fixture
def large_csv_sources():
    """Large CSV data sources for strategy testing"""
    # Generate larger datasets for strategy selection testing
    large_data = [['id', 'name', 'data']]
    for i in range(25000):  # Above streaming threshold
        large_data.append([str(i), f'Item {i}', f'Data value {i}'])
    
    return {
        'large_dataset': large_data,
        'small_dataset': [
            ['id', 'value'],
            ['1', 'test'],
            ['2', 'data']
        ]
    }


@pytest.fixture
def complex_execution_config():
    """Complex execution configuration with dependencies"""
    # Create dataset configs with dependencies
    dataset_a = Mock(spec=DatasetConfig)
    dataset_a.dataset_name = 'dataset_a'
    dataset_a.columns = []
    dataset_a.dependencies = []
    
    dataset_b = Mock(spec=DatasetConfig)
    dataset_b.dataset_name = 'dataset_b'
    dataset_b.columns = []
    dataset_b.dependencies = ['dataset_a']
    
    dataset_c = Mock(spec=DatasetConfig)
    dataset_c.dataset_name = 'dataset_c'
    dataset_c.columns = []
    dataset_c.dependencies = ['dataset_b']
    
    # Create FK relationships
    fk_rel = Mock(spec=FKRelationship)
    fk_rel.source_dataset = 'dataset_b'
    fk_rel.target_dataset = 'dataset_a'
    fk_rel.source_column = 'ref_id'
    fk_rel.target_column = 'id'
    
    config = Mock(spec=ExecutionConfig)
    config.mapping_id = 2
    config.mapping_name = 'Complex Mapping'
    config.datasets = [dataset_a, dataset_b, dataset_c]
    config.column_configurations = []
    config.fk_relationships = [fk_rel]
    
    return config


@pytest.fixture
def mock_dependency_resolver():
    """Mock dependency resolver for multi-phase testing"""
    mock_resolver = Mock()
    
    # Mock processing phases
    phase_1 = Mock()
    phase_1.phase_number = 1
    phase_1.phase_name = 'Independent datasets'
    phase_1.datasets = ['dataset_a']
    
    phase_2 = Mock()
    phase_2.phase_number = 2
    phase_2.phase_name = 'Dependent datasets'
    phase_2.datasets = ['dataset_b']
    
    phase_3 = Mock()
    phase_3.phase_number = 3
    phase_3.phase_name = 'Final datasets'
    phase_3.datasets = ['dataset_c']
    
    mock_resolver.resolve_dependencies.return_value = [phase_1, phase_2, phase_3]
    
    # Mock dependency analysis
    mock_resolver.analyze_dependencies.return_value = {
        'has_cycles': False,
        'complexity_assessment': 'medium',
        'total_phases': 3,
        'max_depth': 2
    }
    
    return mock_resolver


@pytest.fixture
def mock_chunked_processor():
    """Mock chunked processor for streaming tests"""
    mock_processor = Mock()
    
    # Mock processing metrics
    mock_metrics = Mock()
    mock_metrics.resources_created = 1000
    mock_metrics.triples_created = 5000
    mock_metrics.rows_processed = 500
    mock_metrics.cells_processed = 2000
    
    mock_processor.process_large_csv_sources.return_value = mock_metrics
    
    # Mock processing summary
    mock_processor.get_processing_summary.return_value = {
        'chunks_processed': 5,
        'total_rows_processed': 500,
        'average_memory_usage_mb': 75.5,
        'rows_per_second': 125.0,
        'chunk_details': [
            {'chunk_id': 1, 'rows': 100, 'memory_mb': 70.0},
            {'chunk_id': 2, 'rows': 100, 'memory_mb': 72.5},
            {'chunk_id': 3, 'rows': 100, 'memory_mb': 78.0},
            {'chunk_id': 4, 'rows': 100, 'memory_mb': 80.0},
            {'chunk_id': 5, 'rows': 100, 'memory_mb': 77.0}
        ]
    }
    
    return mock_processor


@pytest.fixture
def import_orchestrator(mock_mapping_adapter):
    """Create ImportOrchestrator with mocked dependencies"""
    with patch('arkumu.importer.services.orchestrator.import_orchestrator.MappingAdapter', return_value=mock_mapping_adapter), \
         patch('arkumu.importer.services.orchestrator.import_orchestrator.StrategySelector') as mock_strategy_selector_class, \
         patch('arkumu.importer.services.orchestrator.import_orchestrator.ResultAggregator') as mock_result_aggregator_class, \
         patch('arkumu.importer.services.orchestrator.import_orchestrator.ProgressTracker') as mock_progress_tracker_class:
        
        # Setup mock instances
        mock_strategy_selector = Mock()
        mock_strategy_selector.choose_optimal_strategy.return_value = ProcessingStrategy.ENTITY_CENTRIC
        mock_strategy_selector.get_strategy_rationale.return_value = "Test rationale"
        mock_strategy_selector.analyze_all_strategies.return_value = {'recommended_strategy': 'entity_centric'}
        mock_strategy_selector_class.return_value = mock_strategy_selector
        
        mock_result_aggregator = Mock()
        mock_result_aggregator_class.return_value = mock_result_aggregator
        
        mock_progress_tracker = Mock()
        mock_progress_tracker_class.return_value = mock_progress_tracker
        
        orchestrator = ImportOrchestrator(
            institution='TEST_INST',
            base_uri='http://test.org/data',
            enable_progress_tracking=True
        )
        return orchestrator


@pytest.fixture
def import_orchestrator_no_progress():
    """Create ImportOrchestrator without progress tracking"""
    with patch('arkumu.importer.services.orchestrator.import_orchestrator.MappingAdapter'):
        orchestrator = ImportOrchestrator(
            institution='TEST_INST',
            base_uri='http://test.org/data',
            enable_progress_tracking=False
        )
        return orchestrator


@pytest.fixture
def progress_tracker():
    """Create a ProgressTracker instance"""
    return ProgressTracker()


@pytest.fixture
def result_aggregator():
    """Create a ResultAggregator instance"""
    return ResultAggregator()


@pytest.fixture
def mock_bulk_update_stats():
    """Mock BulkUpdateStats for result aggregation"""
    mock_stats = Mock()
    mock_stats.rows_processed = 100
    mock_stats.resources_created = 200
    mock_stats.triples_created = 800
    mock_stats.cells_processed = 400
    mock_stats.truncated_values = 5
    mock_stats.errors = 2
    mock_stats.warnings = 3
    
    return mock_stats


@pytest.fixture
def sample_import_result():
    """Sample ImportResult for testing"""
    return ImportResult(
        success=True,
        mapping_id=1,
        mapping_name='Test Mapping',
        organization='TEST_ORG',
        strategy_used='entity_centric',
        execution_time_seconds=45.2,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        datasets_processed=2,
        total_resources_created=300,
        total_triples_created=1200,
        total_rows_processed=150,
        total_cells_processed=600,
        phase_results=[],
        dataset_results={
            'dataset_a': {
                'resources_created': 150,
                'triples_created': 600,
                'rows_processed': 75,
                'cells_processed': 300
            },
            'dataset_b': {
                'resources_created': 150,
                'triples_created': 600,
                'rows_processed': 75,
                'cells_processed': 300
            }
        },
        errors=[],
        warnings=['Minor validation warning']
    )


@pytest.fixture
def failed_import_result():
    """Failed ImportResult for testing"""
    return ImportResult(
        success=False,
        mapping_id=1,
        mapping_name='Failed Mapping',
        organization='TEST_ORG',
        strategy_used='entity_centric',
        execution_time_seconds=15.5,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        datasets_processed=0,
        total_resources_created=0,
        total_triples_created=0,
        total_rows_processed=0,
        total_cells_processed=0,
        errors=['Database connection failed', 'Invalid data format'],
        warnings=[]
    )


# Mock patches for common dependencies
@pytest.fixture
def mock_execution_engine_class():
    """Mock MappingExecutionEngine class"""
    with patch('arkumu.importer.services.orchestrator.import_orchestrator.MappingExecutionEngine') as mock_class:
        yield mock_class


@pytest.fixture
def mock_dependency_resolver_class():
    """Mock DependencyResolver class"""
    with patch('arkumu.importer.services.mapping_consumer.DependencyResolver') as mock_class:
        yield mock_class


@pytest.fixture
def mock_chunked_processor_class():
    """Mock ChunkedProcessor class"""
    with patch('arkumu.importer.services.execution.chunked_processor.ChunkedProcessor') as mock_class:
        yield mock_class


@pytest.fixture
def mock_streaming_config_class():
    """Mock StreamingConfig class"""
    with patch('arkumu.importer.services.execution.chunked_processor.StreamingConfig') as mock_class:
        yield mock_class