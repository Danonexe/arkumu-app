import pytest
from datetime import datetime, timezone, timedelta
from arkumu.importer.services.execution.statistics import ExecutionMetrics, ExecutionStatistics


@pytest.fixture
def sample_metrics():
    """Sample ExecutionMetrics for testing."""
    metrics = ExecutionMetrics()
    metrics.rows_processed = 10
    metrics.resources_created = 20
    metrics.errors = 1
    return metrics


@pytest.fixture
def sample_statistics():
    """Sample ExecutionStatistics for testing."""
    return ExecutionStatistics()


class TestExecutionMetrics:
    """Test ExecutionMetrics data class functionality."""
    
    def test_empty_metrics_initialization(self):
        """Test that metrics initialize with default values."""
        metrics = ExecutionMetrics()
        
        assert metrics.rows_processed == 0
        assert metrics.cells_processed == 0
        assert metrics.resources_created == 0
        assert metrics.errors == 0
        assert metrics.fk_relationships_created == 0
        assert metrics.start_time is None
        assert metrics.end_time is None
    
    def test_duration_calculation_without_times(self):
        """Test duration calculation when times are not set."""
        metrics = ExecutionMetrics()
        assert metrics.duration_seconds() == 0.0
    
    def test_duration_calculation_with_times(self):
        """Test duration calculation with start and end times."""
        metrics = ExecutionMetrics()
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=5.5)
        
        metrics.start_time = start_time
        metrics.end_time = end_time
        
        assert metrics.duration_seconds() == 5.5
    
    def test_merge_metrics(self):
        """Test merging two metrics objects."""
        metrics1 = ExecutionMetrics()
        metrics1.rows_processed = 10
        metrics1.resources_created = 20
        metrics1.errors = 1
        metrics1.fk_relationships_created = 5
        
        metrics2 = ExecutionMetrics()
        metrics2.rows_processed = 15
        metrics2.resources_created = 30
        metrics2.errors = 2
        metrics2.fk_relationships_created = 3
        
        metrics1.merge(metrics2)
        
        assert metrics1.rows_processed == 25
        assert metrics1.resources_created == 50
        assert metrics1.errors == 3
        assert metrics1.fk_relationships_created == 8
    
    def test_to_dict_conversion(self):
        """Test converting metrics to dictionary."""
        metrics = ExecutionMetrics()
        metrics.rows_processed = 10
        metrics.resources_created = 20
        metrics.fk_relationships_created = 5
        
        result_dict = metrics.to_dict()
        
        assert result_dict['rows_processed'] == 10
        assert result_dict['resources_created'] == 20
        assert result_dict['fk_relationships_created'] == 5
        assert 'duration_seconds' in result_dict


class TestExecutionStatistics:
    """Test ExecutionStatistics tracking functionality."""
    
    def test_statistics_initialization(self):
        """Test that statistics initialize properly."""
        stats = ExecutionStatistics()
        
        assert isinstance(stats.current_metrics, ExecutionMetrics)
        assert len(stats.dataset_metrics) == 0
    
    def test_execution_timing(self):
        """Test start and end execution tracking."""
        stats = ExecutionStatistics()
        
        # Start execution
        start_time = datetime.now(timezone.utc)
        stats.start_execution()
        
        assert stats.current_metrics.start_time is not None
        assert stats.current_metrics.start_time >= start_time
        
        # End execution
        stats.end_execution()
        
        assert stats.current_metrics.end_time is not None
        assert stats.current_metrics.end_time >= stats.current_metrics.start_time
        assert stats.current_metrics.duration_seconds() > 0
    
    def test_dataset_timing(self):
        """Test dataset-specific timing."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        
        # Start dataset
        stats.start_dataset(dataset_name)
        
        assert dataset_name in stats.dataset_metrics
        assert stats.dataset_metrics[dataset_name].start_time is not None
        
        # End dataset
        stats.end_dataset(dataset_name)
        
        assert stats.dataset_metrics[dataset_name].end_time is not None
        assert stats.dataset_metrics[dataset_name].duration_seconds() > 0
    
    def test_increment_resources_created(self):
        """Test incrementing resource creation counts."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        stats.start_dataset(dataset_name)
        
        # Increment overall
        stats.increment_resources_created(5)
        assert stats.current_metrics.resources_created == 5
        
        # Increment with dataset
        stats.increment_resources_created(3, dataset_name)
        assert stats.current_metrics.resources_created == 8
        assert stats.dataset_metrics[dataset_name].resources_created == 3
    
    def test_increment_fk_relationships(self):
        """Test incrementing FK relationship counts."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        stats.start_dataset(dataset_name)
        
        stats.increment_fk_relationships(2, dataset_name)
        
        assert stats.current_metrics.fk_relationships_created == 2
        assert stats.dataset_metrics[dataset_name].fk_relationships_created == 2
    
    def test_increment_external_ontology_matches(self):
        """Test incrementing external ontology match counts."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        stats.start_dataset(dataset_name)
        
        stats.increment_external_ontology_matches(3, dataset_name)
        
        assert stats.current_metrics.external_ontology_matches == 3
        assert stats.dataset_metrics[dataset_name].external_ontology_matches == 3
    
    def test_add_error(self):
        """Test adding errors."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        stats.start_dataset(dataset_name)
        
        stats.add_error("Test error", dataset_name)
        
        assert stats.current_metrics.errors == 1
        assert stats.dataset_metrics[dataset_name].errors == 1
    
    def test_add_warning(self):
        """Test adding warnings."""
        stats = ExecutionStatistics()
        dataset_name = "test_dataset"
        stats.start_dataset(dataset_name)
        
        stats.add_warning("Test warning", dataset_name)
        
        assert stats.current_metrics.warnings == 1
        assert stats.dataset_metrics[dataset_name].warnings == 1
    
    def test_get_summary(self):
        """Test getting complete summary."""
        stats = ExecutionStatistics()
        dataset1 = "dataset1"
        dataset2 = "dataset2"
        
        # Add some data
        stats.start_execution()
        stats.start_dataset(dataset1)
        stats.increment_resources_created(10, dataset1)
        stats.end_dataset(dataset1)
        
        stats.start_dataset(dataset2)
        stats.increment_resources_created(20, dataset2)
        stats.end_dataset(dataset2)
        stats.end_execution()
        
        summary = stats.get_summary()
        
        assert 'overall' in summary
        assert 'datasets' in summary
        assert 'totals' in summary
        
        assert summary['overall']['resources_created'] == 30
        assert summary['datasets'][dataset1]['resources_created'] == 10
        assert summary['datasets'][dataset2]['resources_created'] == 20
        assert summary['totals']['total_datasets'] == 2
    
    def test_multiple_dataset_tracking(self):
        """Test tracking multiple datasets simultaneously."""
        stats = ExecutionStatistics()
        
        # Start multiple datasets
        stats.start_dataset("dataset1")
        stats.start_dataset("dataset2")
        stats.start_dataset("dataset3")
        
        # Add different metrics to each
        stats.increment_resources_created(5, "dataset1")
        stats.increment_fk_relationships(2, "dataset2")
        stats.add_error("Error in dataset3", "dataset3")
        
        # Verify each dataset has its own metrics
        assert stats.dataset_metrics["dataset1"].resources_created == 5
        assert stats.dataset_metrics["dataset1"].fk_relationships_created == 0
        
        assert stats.dataset_metrics["dataset2"].fk_relationships_created == 2
        assert stats.dataset_metrics["dataset2"].resources_created == 0
        
        assert stats.dataset_metrics["dataset3"].errors == 1
        assert stats.dataset_metrics["dataset3"].resources_created == 0
        
        # Verify overall metrics aggregate
        assert stats.current_metrics.resources_created == 5
        assert stats.current_metrics.fk_relationships_created == 2
        assert stats.current_metrics.errors == 1 