"""
Tests for ImportOrchestrator.

Comprehensive tests for the main orchestration logic that coordinates
mapping consumer and execution engine for complete import workflows.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
import time

from arkumu.importer.services.orchestrator import (
    ImportOrchestrator, ImportResult, ProcessingStrategy
)
from arkumu.importer.services.mapping_consumer import ExecutionConfig


class TestImportOrchestrator:
    """Test suite for ImportOrchestrator class"""

    def test_init_with_defaults(self):
        """Test orchestrator initialization with default values"""
        with patch('arkumu.importer.services.orchestrator.import_orchestrator.MappingAdapter'):
            orchestrator = ImportOrchestrator()
            
            assert orchestrator.institution == "DEFAULT"
            assert orchestrator.base_uri == "http://arkumu.org/data"
            assert orchestrator.enable_progress_tracking is True
            assert orchestrator.progress_tracker is not None
            assert orchestrator.mapping_adapter is not None
            assert orchestrator.strategy_selector is not None
            assert orchestrator.result_aggregator is not None

    def test_init_custom_parameters(self):
        """Test orchestrator initialization with custom parameters"""
        with patch('arkumu.importer.services.orchestrator.import_orchestrator.MappingAdapter'):
            orchestrator = ImportOrchestrator(
                institution="CUSTOM_INST",
                base_uri="http://custom.org/data",
                enable_progress_tracking=False
            )
            
            assert orchestrator.institution == "CUSTOM_INST"
            assert orchestrator.base_uri == "http://custom.org/data"
            assert orchestrator.enable_progress_tracking is False
            assert orchestrator.progress_tracker is None

    def test_execute_mapping_import_success(self, import_orchestrator, 
                                           sample_execution_config, 
                                           sample_csv_sources,
                                           mock_execution_engine_class):
        """Test successful mapping import execution"""
        # Mock the execution engine
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 100
        mock_stats.triples_created = 500
        mock_stats.rows_processed = 50
        mock_stats.cells_processed = 200
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        # Setup mocks
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        import_orchestrator.strategy_selector.choose_optimal_strategy.return_value = ProcessingStrategy.ENTITY_CENTRIC
        import_orchestrator.strategy_selector.get_strategy_rationale.return_value = "Test rationale"
        
        # Execute import
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="auto"
        )
        
        # Verify result
        assert isinstance(result, ImportResult)
        assert result.success is True
        assert result.mapping_id == 1
        assert result.strategy_used == "entity_centric"
        assert result.datasets_processed == 1
        assert result.total_resources_created == 100
        assert result.total_triples_created == 500
        assert result.execution_time_seconds > 0
        
        # Verify method calls
        import_orchestrator.mapping_adapter.get_mapping_info.assert_called_once_with(1)
        import_orchestrator.mapping_adapter.validate_mapping.assert_called_once_with(1)
        import_orchestrator.mapping_adapter.translate_to_execution_config.assert_called_once_with(1)

    def test_execute_mapping_import_validation_failure(self, import_orchestrator):
        """Test import execution with mapping validation failure"""
        # Mock validation failure
        mock_validation = Mock()
        mock_validation.is_valid = False
        mock_validation.errors = ["Invalid mapping configuration", "Missing required fields"]
        mock_validation.warnings = []
        import_orchestrator.mapping_adapter.validate_mapping.return_value = mock_validation
        
        # Execute import
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources={},
            strategy="auto"
        )
        
        # Verify failure
        assert result.success is False
        assert len(result.errors) == 2
        assert "Invalid mapping configuration" in result.errors[0]
        assert "Missing required fields" in result.errors[1]

    def test_execute_mapping_import_exception_handling(self, import_orchestrator):
        """Test import execution with exception handling"""
        # Mock exception during mapping load
        import_orchestrator.mapping_adapter.get_mapping_info.side_effect = Exception("Database connection failed")
        
        # Execute import
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources={},
            strategy="auto"
        )
        
        # Verify error handling
        assert result.success is False
        assert len(result.errors) == 1
        assert "Failed to load mapping" in result.errors[0]
        assert "Database connection failed" in result.errors[0]

    def test_execute_mapping_import_with_requested_strategy(self, import_orchestrator,
                                                           sample_execution_config,
                                                           sample_csv_sources,
                                                           mock_execution_engine_class):
        """Test import execution with specific requested strategy"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 75
        mock_stats.triples_created = 300
        mock_stats.rows_processed = 40
        mock_stats.cells_processed = 160
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        import_orchestrator.strategy_selector.get_strategy_rationale.return_value = "Manual selection"
        
        # Execute with specific strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="streaming_entity_centric"
        )
        
        # Verify strategy was used
        assert result.success is True
        assert result.strategy_used == "streaming_entity_centric"
        
        # Verify strategy selector was not called for auto-selection
        import_orchestrator.strategy_selector.choose_optimal_strategy.assert_not_called()

    def test_execute_mapping_import_invalid_strategy_fallback(self, import_orchestrator,
                                                            sample_execution_config,
                                                            sample_csv_sources,
                                                            mock_execution_engine_class):
        """Test import execution with invalid strategy falls back to auto-selection"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 50
        mock_stats.triples_created = 250
        mock_stats.rows_processed = 25
        mock_stats.cells_processed = 100
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        import_orchestrator.strategy_selector.choose_optimal_strategy.return_value = ProcessingStrategy.ENTITY_CENTRIC
        import_orchestrator.strategy_selector.get_strategy_rationale.return_value = "Fallback selection"
        
        # Execute with invalid strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="invalid_strategy"
        )
        
        # Verify fallback to auto-selection
        assert result.success is True
        assert result.strategy_used == "entity_centric"
        import_orchestrator.strategy_selector.choose_optimal_strategy.assert_called_once()

    def test_entity_centric_execution(self, import_orchestrator,
                                     sample_execution_config,
                                     sample_csv_sources,
                                     mock_execution_engine_class):
        """Test entity-centric processing execution"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 100
        mock_stats.triples_created = 400
        mock_stats.rows_processed = 50
        mock_stats.cells_processed = 200
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        
        # Execute entity-centric strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="entity_centric"
        )
        
        # Verify execution
        assert result.success is True
        assert result.datasets_processed == 1
        assert 'test_dataset' in result.dataset_results
        
        # Verify engine was called correctly
        mock_execution_engine_class.assert_called_once_with(
            institution="TEST_INST",
            base_uri="http://test.org/data"
        )
        mock_engine.execute_simple_import.assert_called_once()

    def test_streaming_entity_centric_execution_fallback(self, import_orchestrator,
                                                        sample_execution_config,
                                                        sample_csv_sources,
                                                        mock_execution_engine_class):
        """Test streaming entity-centric falls back to regular when datasets are small"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 50
        mock_stats.triples_created = 200
        mock_stats.rows_processed = 25
        mock_stats.cells_processed = 100
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        
        # Mock _check_for_large_datasets to return False
        import_orchestrator._check_for_large_datasets = Mock(return_value=False)
        
        # Execute streaming strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="streaming_entity_centric"
        )
        
        # Verify fallback to regular entity-centric
        assert result.success is True
        assert len(result.warnings) > 0
        assert "small enough for in-memory processing" in result.warnings[0]

    def test_streaming_entity_centric_with_chunked_processor(self, import_orchestrator,
                                                           sample_execution_config,
                                                           large_csv_sources,
                                                           mock_chunked_processor_class,
                                                           mock_streaming_config_class):
        """Test streaming entity-centric with chunked processor for large datasets"""
        # Setup mocks
        mock_processor = Mock()
        mock_metrics = Mock()
        mock_metrics.resources_created = 1000
        mock_metrics.triples_created = 4000
        mock_metrics.rows_processed = 500
        mock_metrics.cells_processed = 2000
        mock_processor.process_large_csv_sources.return_value = mock_metrics
        
        mock_summary = {
            'chunks_processed': 3,
            'total_rows_processed': 500,
            'average_memory_usage_mb': 85.0,
            'rows_per_second': 150.0,
            'chunk_details': [
                {'chunk_id': 1, 'rows': 200, 'memory_mb': 80.0},
                {'chunk_id': 2, 'rows': 200, 'memory_mb': 85.0},
                {'chunk_id': 3, 'rows': 100, 'memory_mb': 90.0}
            ]
        }
        mock_processor.get_processing_summary.return_value = mock_summary
        
        mock_chunked_processor_class.return_value = mock_processor
        mock_streaming_config = Mock()
        mock_streaming_config_class.return_value = mock_streaming_config
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        
        # Mock _check_for_large_datasets to return True
        import_orchestrator._check_for_large_datasets = Mock(return_value=True)
        
        # Execute streaming strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=large_csv_sources,
            strategy="streaming_entity_centric"
        )
        
        # Verify chunked processing was used
        assert result.success is True
        assert result.total_resources_created == 1000
        assert result.total_triples_created == 4000
        assert result.peak_memory_usage_mb == 90.0
        assert len(result.phase_results) == 1
        assert result.phase_results[0]['phase_name'] == 'streaming_entity_centric'

    def test_multi_phase_execution(self, import_orchestrator,
                                  complex_execution_config,
                                  sample_csv_sources,
                                  mock_execution_engine_class,
                                  mock_dependency_resolver_class,
                                  mock_dependency_resolver):
        """Test multi-phase processing execution"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 75
        mock_stats.triples_created = 300
        mock_stats.rows_processed = 30
        mock_stats.cells_processed = 120
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        mock_dependency_resolver_class.return_value = mock_dependency_resolver
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = complex_execution_config
        
        # Adjust CSV sources to match complex config
        csv_sources = {
            'dataset_a': [['id', 'name'], ['1', 'Item A']],
            'dataset_b': [['id', 'ref_id'], ['1', '1']],
            'dataset_c': [['id', 'ref_id'], ['1', '1']]
        }
        
        # Execute multi-phase strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=2,
            csv_sources=csv_sources,
            strategy="multi_phase"
        )
        
        # Verify multi-phase execution
        assert result.success is True
        assert len(result.phase_results) == 3
        assert result.phase_results[0]['phase_number'] == 1
        assert result.phase_results[1]['phase_number'] == 2
        assert result.phase_results[2]['phase_number'] == 3
        
        # Verify dependency resolver was used
        mock_dependency_resolver.resolve_dependencies.assert_called_once_with(complex_execution_config)

    def test_multi_phase_execution_with_dataset_failure(self, import_orchestrator,
                                                       complex_execution_config,
                                                       sample_csv_sources,
                                                       mock_execution_engine_class,
                                                       mock_dependency_resolver_class,
                                                       mock_dependency_resolver):
        """Test multi-phase execution with dataset failure"""
        # Setup mocks - engine fails on second call
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 50
        mock_stats.triples_created = 200
        mock_stats.rows_processed = 25
        mock_stats.cells_processed = 100
        
        mock_engine.execute_simple_import.side_effect = [
            mock_stats,  # First call succeeds
            Exception("Processing error"),  # Second call fails
            mock_stats   # Third call succeeds
        ]
        mock_execution_engine_class.return_value = mock_engine
        
        mock_dependency_resolver_class.return_value = mock_dependency_resolver
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = complex_execution_config
        
        # Adjust CSV sources
        csv_sources = {
            'dataset_a': [['id', 'name'], ['1', 'Item A']],
            'dataset_b': [['id', 'ref_id'], ['1', '1']],
            'dataset_c': [['id', 'ref_id'], ['1', '1']]
        }
        
        # Execute multi-phase strategy
        result = import_orchestrator.execute_mapping_import(
            mapping_id=2,
            csv_sources=csv_sources,
            strategy="multi_phase"
        )
        
        # Verify partial failure
        assert result.success is False  # Overall failure due to dataset failure
        assert len(result.errors) > 0
        assert "Processing error" in str(result.errors)

    def test_get_import_status_with_tracking(self, import_orchestrator):
        """Test getting import status when progress tracking is enabled"""
        # Mock progress tracker status
        expected_status = {
            'mapping_id': 1,
            'status': 'running',
            'progress': 50,
            'current_dataset': 'test_dataset'
        }
        import_orchestrator.progress_tracker.get_status.return_value = expected_status
        
        # Get status
        status = import_orchestrator.get_import_status(1)
        
        # Verify status
        assert status == expected_status
        import_orchestrator.progress_tracker.get_status.assert_called_once_with(1)

    def test_get_import_status_without_tracking(self, import_orchestrator_no_progress):
        """Test getting import status when progress tracking is disabled"""
        # Get status (should return None)
        status = import_orchestrator_no_progress.get_import_status(1)
        
        # Verify no status returned
        assert status is None

    def test_analyze_import_feasibility(self, import_orchestrator,
                                      sample_execution_config,
                                      sample_csv_sources,
                                      mock_dependency_resolver_class,
                                      mock_dependency_resolver):
        """Test import feasibility analysis"""
        # Setup mocks
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        
        strategy_analysis = {
            'recommended_strategy': 'entity_centric',
            'strategies': ['entity_centric', 'streaming_entity_centric']
        }
        import_orchestrator.strategy_selector.analyze_all_strategies.return_value = strategy_analysis
        
        mock_dependency_resolver_class.return_value = mock_dependency_resolver
        
        # Analyze feasibility
        analysis = import_orchestrator.analyze_import_feasibility(1, sample_csv_sources)
        
        # Verify analysis structure
        assert 'mapping_info' in analysis
        assert 'data_analysis' in analysis
        assert 'strategy_analysis' in analysis
        assert 'dependency_analysis' in analysis
        assert 'feasibility' in analysis
        assert 'recommendations' in analysis
        
        # Verify mapping info
        assert analysis['mapping_info']['id'] == 1
        assert analysis['mapping_info']['name'] == 'Test Mapping'
        
        # Verify data analysis
        assert analysis['data_analysis']['total_rows'] == 7  # Sample data has 7 total rows (4 + 3)
        assert analysis['data_analysis']['total_columns'] == 6  # Sample data has 6 total columns (3 + 3)

    def test_analyze_import_feasibility_exception_handling(self, import_orchestrator):
        """Test feasibility analysis with exception handling"""
        # Mock exception during mapping load
        import_orchestrator.mapping_adapter.translate_to_execution_config.side_effect = Exception("Mapping not found")
        
        # Analyze feasibility
        analysis = import_orchestrator.analyze_import_feasibility(1, {})
        
        # Verify error handling
        assert 'error' in analysis
        assert analysis['feasibility'] == 'unknown'
        assert "Mapping not found" in analysis['error']

    def test_check_for_large_datasets_file_paths(self, import_orchestrator):
        """Test checking for large datasets with file paths"""
        # Mock file size checking
        with patch('os.path.getsize') as mock_getsize:
            # Mock large file (>50MB)
            mock_getsize.return_value = 60 * 1024 * 1024  # 60MB
            
            csv_sources = {
                'large_dataset': '/path/to/large_file.csv'
            }
            
            # Check for large datasets
            is_large = import_orchestrator._check_for_large_datasets(csv_sources)
            
            assert is_large is True
            mock_getsize.assert_called_once_with('/path/to/large_file.csv')

    def test_check_for_large_datasets_in_memory(self, import_orchestrator):
        """Test checking for large datasets with in-memory data"""
        # Create large in-memory dataset
        large_data = [['id', 'name']]
        for i in range(25000):  # > 20,000 rows threshold
            large_data.append([str(i), f'Item {i}'])
        
        csv_sources = {
            'large_dataset': large_data
        }
        
        # Check for large datasets
        is_large = import_orchestrator._check_for_large_datasets(csv_sources)
        
        assert is_large is True

    def test_check_for_large_datasets_small_datasets(self, import_orchestrator):
        """Test checking for large datasets with small datasets"""
        csv_sources = {
            'small_dataset': [
                ['id', 'name'],
                ['1', 'Item 1'],
                ['2', 'Item 2']
            ]
        }
        
        # Check for large datasets
        is_large = import_orchestrator._check_for_large_datasets(csv_sources)
        
        assert is_large is False

    def test_progress_tracking_integration(self, import_orchestrator,
                                         sample_execution_config,
                                         sample_csv_sources,
                                         mock_execution_engine_class):
        """Test progress tracking integration during import"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 100
        mock_stats.triples_created = 400
        mock_stats.rows_processed = 50
        mock_stats.cells_processed = 200
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        import_orchestrator.strategy_selector.choose_optimal_strategy.return_value = ProcessingStrategy.ENTITY_CENTRIC
        import_orchestrator.strategy_selector.get_strategy_rationale.return_value = "Test rationale"
        
        # Execute import
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="auto"
        )
        
        # Verify progress tracking calls
        import_orchestrator.progress_tracker.start_import.assert_called_once()
        import_orchestrator.progress_tracker.start_dataset.assert_called_once_with('test_dataset')
        import_orchestrator.progress_tracker.complete_dataset.assert_called_once_with('test_dataset', success=True)
        import_orchestrator.progress_tracker.complete_import.assert_called_once_with(success=True)

    def test_performance_metrics_calculation(self, import_orchestrator,
                                           sample_execution_config,
                                           sample_csv_sources,
                                           mock_execution_engine_class):
        """Test performance metrics calculation in import result"""
        # Setup mocks
        mock_engine = Mock()
        mock_stats = Mock()
        mock_stats.resources_created = 200
        mock_stats.triples_created = 800
        mock_stats.rows_processed = 100
        mock_stats.cells_processed = 400
        mock_engine.execute_simple_import.return_value = mock_stats
        mock_execution_engine_class.return_value = mock_engine
        
        import_orchestrator.mapping_adapter.translate_to_execution_config.return_value = sample_execution_config
        import_orchestrator.strategy_selector.choose_optimal_strategy.return_value = ProcessingStrategy.ENTITY_CENTRIC
        import_orchestrator.strategy_selector.get_strategy_rationale.return_value = "Test rationale"
        
        # Execute import
        result = import_orchestrator.execute_mapping_import(
            mapping_id=1,
            csv_sources=sample_csv_sources,
            strategy="auto"
        )
        
        # Verify performance metrics
        assert result.execution_time_seconds > 0
        assert result.average_rows_per_second is not None
        assert result.average_rows_per_second > 0
        assert result.total_rows_processed == 100


class TestImportResult:
    """Test suite for ImportResult class"""

    def test_import_result_initialization(self):
        """Test ImportResult initialization"""
        start_time = datetime.now(timezone.utc)
        end_time = datetime.now(timezone.utc)
        
        result = ImportResult(
            success=True,
            mapping_id=1,
            mapping_name='Test Mapping',
            organization='TEST_ORG',
            strategy_used='entity_centric',
            execution_time_seconds=30.5,
            start_time=start_time,
            end_time=end_time,
            datasets_processed=2
        )
        
        assert result.success is True
        assert result.mapping_id == 1
        assert result.mapping_name == 'Test Mapping'
        assert result.organization == 'TEST_ORG'
        assert result.strategy_used == 'entity_centric'
        assert result.execution_time_seconds == 30.5
        assert result.datasets_processed == 2

    def test_add_error_method(self, sample_import_result):
        """Test adding errors to import result"""
        sample_import_result.add_error("Test error message")
        
        assert sample_import_result.success is False
        assert len(sample_import_result.errors) == 1
        assert "Test error message" in sample_import_result.errors

    def test_add_warning_method(self, sample_import_result):
        """Test adding warnings to import result"""
        sample_import_result.add_warning("Test warning message")
        
        assert len(sample_import_result.warnings) == 2  # One from fixture + one added
        assert "Test warning message" in sample_import_result.warnings

    def test_get_summary_success(self, sample_import_result):
        """Test getting summary for successful import"""
        summary = sample_import_result.get_summary()
        
        assert "Successfully processed" in summary
        assert "2 datasets" in summary
        assert "entity_centric strategy" in summary
        assert "300 resources" in summary
        assert "1200 triples" in summary

    def test_get_summary_failure(self, failed_import_result):
        """Test getting summary for failed import"""
        summary = failed_import_result.get_summary()
        
        assert "Import failed" in summary
        assert "2 errors" in summary
        assert "0 warnings" in summary