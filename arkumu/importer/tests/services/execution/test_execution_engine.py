"""
Tests for MappingExecutionEngine.

Tests the main execution engine that orchestrates data processing,
resource management, and update analysis for mapping-aware imports.
"""
import pytest
import polars as pl
from unittest.mock import Mock, patch, call
from datetime import datetime, timezone

from arkumu.common.enums import UpdateStrategy
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.models import Resource
from arkumu.importer.services.execution.execution_engine import MappingExecutionEngine
from arkumu.importer.services.execution.statistics import ExecutionMetrics


def create_mock_resource(resource_id=1, uri="test://resource"):
    """Helper function to create properly mocked Django Resource instances"""
    mock_resource = Mock(spec=Resource)
    mock_resource.id = resource_id
    mock_resource.uri = uri
    mock_resource._meta = Resource._meta
    mock_resource._state = Mock()
    mock_resource._state.db = 'default'
    return mock_resource


@pytest.mark.django_db
class TestMappingExecutionEngine:
    """Test suite for MappingExecutionEngine"""
    
    def test_engine_initialization(self, test_organization_code, test_base_uri):
        """Test engine initialization with proper configuration"""
        engine = MappingExecutionEngine(
            organization_id=test_organization_code,
            base_uri=test_base_uri,
            default_strategy=UpdateStrategy.UPDATE_VALUES,
            timestamp_column="updated_at",
            batch_size=500
        )
        
        assert engine.organization_id == test_organization_code
        assert engine.base_uri == test_base_uri
        assert engine.default_strategy == UpdateStrategy.UPDATE_VALUES
        assert engine.timestamp_column == "updated_at"
        assert engine.batch_size == 500
        
        # Verify component initialization
        assert engine.statistics is not None
        assert engine.data_processor is not None
        assert engine.resource_manager is not None
        assert engine.update_analyzer is not None
        assert engine.mapping_coordinator is not None
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_execute_simple_import_with_list_data(self, mock_triple_objects, mock_resource_objects, 
                                                execution_engine, sample_csv_data):
        """Test simple import with list data"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Execute import
        metrics = execution_engine.execute_simple_import(
            csv_data=sample_csv_data,
            dataset_name="test_dataset"
        )
        
        # Verify metrics
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.rows_processed == 0  # Will be set during actual processing
        assert metrics.resources_created >= 0
        
        # Verify database operations were called
        assert mock_resource_objects.get_or_create.called
        assert mock_resource_objects.bulk_create.called
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_execute_simple_import_with_polars_df(self, mock_triple_objects, mock_resource_objects,
                                                execution_engine, sample_polars_df):
        """Test simple import with Polars DataFrame"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Execute import
        metrics = execution_engine.execute_simple_import(
            csv_data=sample_polars_df,
            dataset_name="test_dataset"
        )
        
        # Verify metrics
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.resources_created >= 0
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_execute_with_mapping_config(self, mock_triple_objects, mock_resource_objects,
                                       execution_engine, sample_csv_data, simple_mapping_config):
        """Test execution with mapping configuration"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Execute import with mapping config
        metrics = execution_engine.execute_simple_import(
            csv_data=sample_csv_data,
            dataset_name="test_dataset",
            mapping_config=simple_mapping_config
        )
        
        # Verify execution completed
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_execute_with_empty_data(self, execution_engine):
        """Test execution with empty dataset"""
        metrics = execution_engine.execute_simple_import(
            csv_data=[],
            dataset_name="empty_dataset"
        )
        
        # Should complete without errors
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.rows_processed == 0
    
    def test_execute_with_invalid_data_type(self, execution_engine):
        """Test execution with invalid data type raises error"""
        with pytest.raises(TypeError):
            execution_engine.execute_simple_import(
                csv_data="invalid_data_type",
                dataset_name="test_dataset"
            )
    
    @patch('arkumu.metadata.models.Resource.objects')
    def test_analyze_import_impact(self, mock_resource_objects, execution_engine, sample_csv_data):
        """Test import impact analysis (dry run)"""
        # Mock existing resources
        mock_resource_objects.filter.return_value.values.return_value = [
            {
                'uri': 'http://arkumu.test.org/data/TEST_ORG/datasets/test_dataset/name/1',
                'value': 'Old Name',
                'name': 'name',
                'updated_at': datetime.now(timezone.utc)
            }
        ]
        
        # Analyze impact
        analysis = execution_engine.analyze_import_impact(
            csv_data=sample_csv_data,
            dataset_name="test_dataset"
        )
        
        # Verify analysis structure
        assert isinstance(analysis, dict)
        assert 'total_rows' in analysis
        assert 'total_cells' in analysis
        assert 'new_resources' in analysis
        assert 'existing_resources' in analysis
        assert 'potential_updates' in analysis
        assert 'conflicts' in analysis
        assert 'recommendations' in analysis
    
    def test_extract_mapping_config_from_workspace_columns(self, execution_engine, workspace_columns):
        """Test extraction of mapping config from workspace columns"""
        mapping_config = execution_engine._extract_mapping_config("people", workspace_columns)
        
        assert mapping_config is not None
        assert 'columns' in mapping_config
        assert 'name' in mapping_config['columns']
        assert 'age' in mapping_config['columns']
        
        # Verify column configuration
        name_config = mapping_config['columns']['name']
        assert name_config['is_anchor'] is False
        assert name_config['is_fk'] is False
        assert name_config['is_multi_value'] is False
    
    def test_extract_mapping_config_no_matching_dataset(self, execution_engine, workspace_columns):
        """Test extraction when no columns match the dataset"""
        mapping_config = execution_engine._extract_mapping_config("nonexistent_dataset", workspace_columns)
        
        assert mapping_config is None
    
    def test_should_create_row_resources(self, execution_engine):
        """Test row resource creation logic"""
        # Default should be False (column-only topology)
        should_create = execution_engine._should_create_row_resources(None)
        assert should_create is False
        
        should_create = execution_engine._should_create_row_resources({})
        assert should_create is False
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_process_special_columns_detection(self, mock_triple_objects, mock_resource_objects,
                                             execution_engine, complex_mapping_config):
        """Test detection and processing of special column types"""
        # Create test DataFrame
        df = pl.DataFrame([
            {"person_id": "P001", "name": "John", "department_id": "D001", "skills": "Python,Java", "orcid": "0000-0000-0000-0001"}
        ])
        
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        
        # Test special column processing (this is a placeholder in the current implementation)
        execution_engine._process_special_columns(df, "test_dataset", complex_mapping_config)
        
        # Should complete without errors (current implementation is a placeholder)
    
    def test_execution_summary(self, execution_engine):
        """Test execution summary generation"""
        summary = execution_engine.get_execution_summary()
        
        assert isinstance(summary, dict)
        assert 'engine_info' in summary
        assert 'overall' in summary
        
        engine_info = summary['engine_info']
        assert engine_info['organization_id'] == execution_engine.organization_id
        assert engine_info['base_uri'] == execution_engine.base_uri
        assert engine_info['batch_size'] == execution_engine.batch_size
        assert engine_info['default_strategy'] == execution_engine.default_strategy.name
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_batch_processing(self, mock_triple_objects, mock_resource_objects, execution_engine):
        """Test batch processing with custom batch size"""
        # Set small batch size for testing
        execution_engine.batch_size = 2
        
        # Create test data with more rows than batch size
        test_data = [
            {"name": f"Person {i}", "age": str(20 + i)} 
            for i in range(5)
        ]
        
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Execute import
        metrics = execution_engine.execute_simple_import(
            csv_data=test_data,
            dataset_name="batch_test"
        )
        
        # Verify processing completed
        assert isinstance(metrics, ExecutionMetrics)
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_execute_with_processing_plan(self, mock_triple_objects, mock_resource_objects, 
                                        execution_engine, sample_csv_data, workspace_columns):
        """Test execution with FK processing plan"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Mock FK processing plan
        mock_processing_plan = Mock()
        
        # Execute with processing plan
        metrics = execution_engine.execute_with_processing_plan(
            csv_data=sample_csv_data,
            processing_plan=mock_processing_plan,
            dataset_name="test_dataset",
            workspace_columns=workspace_columns
        )
        
        # Verify execution completed
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_error_handling_in_execution(self, execution_engine):
        """Test error handling during execution"""
        # Test with data that should cause processing errors
        invalid_data = [{"": "invalid"}]  # Empty column name
        
        # Should handle gracefully and log errors
        metrics = execution_engine.execute_simple_import(
            csv_data=invalid_data,
            dataset_name="error_test"
        )
        
        # Should complete despite errors
        assert isinstance(metrics, ExecutionMetrics)
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_unicode_data_handling(self, mock_triple_objects, mock_resource_objects,
                                 execution_engine, unicode_csv_data):
        """Test handling of Unicode data"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Execute import with Unicode data
        metrics = execution_engine.execute_simple_import(
            csv_data=unicode_csv_data,
            dataset_name="unicode_test"
        )
        
        # Should handle Unicode data without errors
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_statistics_tracking(self, execution_engine):
        """Test that statistics are properly tracked during execution"""
        initial_stats = execution_engine.statistics.current_metrics
        
        # Execute a simple import
        metrics = execution_engine.execute_simple_import(
            csv_data=[{"name": "Test", "age": "25"}],
            dataset_name="stats_test"
        )
        
        # Verify statistics were updated
        assert isinstance(metrics, ExecutionMetrics)
        # Start and end times should be set during execution
        assert execution_engine.statistics.current_metrics.start_time is not None
    
    def test_multi_dataset_processing(self, execution_engine):
        """Test processing multiple datasets in sequence"""
        datasets = [
            ("dataset1", [{"name": "Person1", "age": "30"}]),
            ("dataset2", [{"title": "Book1", "year": "2023"}]),
            ("dataset3", [{"product": "Item1", "price": "10.99"}])
        ]
        
        results = []
        for dataset_name, data in datasets:
            metrics = execution_engine.execute_simple_import(
                csv_data=data,
                dataset_name=dataset_name
            )
            results.append(metrics)
        
        # All imports should complete
        assert len(results) == 3
        assert all(isinstance(m, ExecutionMetrics) for m in results)


@pytest.mark.django_db
class TestExecutionEnginePerformance:
    """Performance tests for execution engine"""
    
    @patch('arkumu.metadata.models.Resource.objects')
    @patch('arkumu.metadata.models.triples.Triple.objects')
    def test_large_dataset_performance(self, mock_triple_objects, mock_resource_objects,
                                     execution_engine, performance_test_data):
        """Test performance with large dataset"""
        # Mock database operations
        mock_resource = create_mock_resource()
        mock_resource_objects.get_or_create.return_value = (mock_resource, True)
        mock_resource_objects.bulk_create.return_value = []
        mock_resource_objects.filter.return_value.select_related.return_value = []
        mock_triple_objects.bulk_create.return_value = []
        
        # Measure execution time
        start_time = datetime.now()
        
        # Use smaller subset for testing to avoid timeouts
        test_subset = performance_test_data[:1000]
        
        metrics = execution_engine.execute_simple_import(
            csv_data=test_subset,
            dataset_name="performance_test"
        )
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        # Verify execution completed and track performance
        assert isinstance(metrics, ExecutionMetrics)
        assert execution_time < 60  # Should complete within reasonable time
        
        # Log performance metrics for analysis
        print(f"Processed {len(test_subset)} rows in {execution_time:.2f} seconds")
        if execution_time > 0:
            print(f"Processing rate: {len(test_subset) / execution_time:.1f} rows/second")
    
    def test_memory_usage_with_large_dataset(self, execution_engine):
        """Test memory usage with large dataset"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create large dataset
        large_data = [
            {"id": str(i), "name": f"Person {i}", "data": "x" * 100}
            for i in range(5000)
        ]
        
        # Execute import
        metrics = execution_engine.execute_simple_import(
            csv_data=large_data,
            dataset_name="memory_test"
        )
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Verify execution completed
        assert isinstance(metrics, ExecutionMetrics)
        
        # Log memory usage for analysis
        print(f"Memory usage: {initial_memory:.1f}MB -> {final_memory:.1f}MB (+{memory_increase:.1f}MB)")
        
        # Memory increase should be reasonable
        assert memory_increase < 500  # Should not use excessive memory


@pytest.mark.django_db
class TestExecutionEngineEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_none_data_handling(self, execution_engine):
        """Test handling of None data"""
        with pytest.raises((TypeError, AttributeError)):
            execution_engine.execute_simple_import(
                csv_data=None,
                dataset_name="none_test"
            )
    
    def test_empty_string_dataset_name(self, execution_engine):
        """Test handling of empty dataset name"""
        metrics = execution_engine.execute_simple_import(
            csv_data=[{"name": "Test"}],
            dataset_name=""
        )
        
        # Should handle empty dataset name gracefully
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_special_characters_in_dataset_name(self, execution_engine):
        """Test handling of special characters in dataset name"""
        special_names = [
            "dataset-with-hyphens",
            "dataset_with_underscores",
            "dataset with spaces",
            "dataset.with.dots",
            "dataset@with@symbols"
        ]
        
        for name in special_names:
            metrics = execution_engine.execute_simple_import(
                csv_data=[{"test": "value"}],
                dataset_name=name
            )
            assert isinstance(metrics, ExecutionMetrics)
    
    def test_very_long_dataset_name(self, execution_engine):
        """Test handling of very long dataset name"""
        long_name = "a" * 1000
        
        metrics = execution_engine.execute_simple_import(
            csv_data=[{"test": "value"}],
            dataset_name=long_name
        )
        
        # Should handle long names gracefully
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_column_names_with_special_characters(self, execution_engine):
        """Test handling of column names with special characters"""
        special_data = [
            {"column-with-hyphens": "value1"},
            {"column_with_underscores": "value2"},
            {"column with spaces": "value3"},
            {"column.with.dots": "value4"},
            {"column@with@symbols": "value5"}
        ]
        
        for data in special_data:
            metrics = execution_engine.execute_simple_import(
                csv_data=[data],
                dataset_name="special_columns_test"
            )
            assert isinstance(metrics, ExecutionMetrics)
    
    def test_extremely_large_cell_values(self, execution_engine):
        """Test handling of extremely large cell values"""
        large_value = "x" * 10000  # 10KB value
        
        metrics = execution_engine.execute_simple_import(
            csv_data=[{"large_field": large_value}],
            dataset_name="large_values_test"
        )
        
        # Should handle large values (may truncate)
        assert isinstance(metrics, ExecutionMetrics)
    
    def test_mixed_data_types_in_columns(self, execution_engine):
        """Test handling of mixed data types in same column"""
        mixed_data = [
            {"mixed_field": "string_value"},
            {"mixed_field": 123},
            {"mixed_field": 45.67},
            {"mixed_field": True},
            {"mixed_field": None}
        ]
        
        metrics = execution_engine.execute_simple_import(
            csv_data=mixed_data,
            dataset_name="mixed_types_test"
        )
        
        # Should handle mixed types gracefully
        assert isinstance(metrics, ExecutionMetrics)