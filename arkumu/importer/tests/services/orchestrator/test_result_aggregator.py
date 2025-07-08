"""
Tests for ResultAggregator.

Comprehensive tests for result aggregation across datasets and processing
phases with quality assessment and performance analysis.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta

from arkumu.importer.services.orchestrator.result_aggregator import (
    ResultAggregator, DatasetResult, PhaseResult, AggregatedResult
)


class TestResultAggregator:
    """Test suite for ResultAggregator class"""

    def test_init_default_state(self, result_aggregator):
        """Test ResultAggregator initialization"""
        assert result_aggregator.current_aggregation is None

    def test_start_aggregation(self, result_aggregator):
        """Test starting a new result aggregation"""
        start_time = datetime.now(timezone.utc)
        
        result = result_aggregator.start_aggregation(start_time, total_datasets=3)
        
        assert isinstance(result, AggregatedResult)
        assert result_aggregator.current_aggregation == result
        assert result.success is True
        assert result.total_datasets == 3
        assert result.start_time == start_time
        assert result.end_time == start_time
        assert result.datasets_processed == 0
        assert result.total_resources_created == 0

    def test_add_dataset_result_success(self, result_aggregator, mock_bulk_update_stats):
        """Test adding successful dataset result"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=2)
        
        dataset_result = result_aggregator.add_dataset_result(
            dataset_name='test_dataset',
            stats=mock_bulk_update_stats,
            execution_time=30.5,
            success=True,
            errors=None,
            warnings=['Minor warning'],
            phase_number=1,
            strategy_used='entity_centric'
        )
        
        # Verify dataset result
        assert isinstance(dataset_result, DatasetResult)
        assert dataset_result.dataset_name == 'test_dataset'
        assert dataset_result.success is True
        assert dataset_result.execution_time_seconds == 30.5
        assert dataset_result.rows_processed == 100
        assert dataset_result.resources_created == 200
        assert dataset_result.triples_created == 800
        assert dataset_result.cells_processed == 400
        assert dataset_result.phase_number == 1
        assert dataset_result.strategy_used == 'entity_centric'
        assert dataset_result.warnings == 1
        assert len(dataset_result.warning_messages) == 1
        
        # Verify aggregation updated
        aggregation = result_aggregator.current_aggregation
        assert aggregation.datasets_processed == 1
        assert aggregation.datasets_failed == 0
        assert aggregation.total_resources_created == 200
        assert aggregation.total_triples_created == 800
        assert aggregation.total_rows_processed == 100
        assert aggregation.total_cells_processed == 400

    def test_add_dataset_result_failure(self, result_aggregator, mock_bulk_update_stats):
        """Test adding failed dataset result"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=1)
        
        # Mock stats for failed processing
        mock_bulk_update_stats.resources_created = 0
        mock_bulk_update_stats.triples_created = 0
        mock_bulk_update_stats.rows_processed = 0
        
        dataset_result = result_aggregator.add_dataset_result(
            dataset_name='failed_dataset',
            stats=mock_bulk_update_stats,
            execution_time=15.0,
            success=False,
            errors=['Database connection failed', 'Validation error'],
            warnings=None,
            strategy_used='entity_centric'
        )
        
        # Verify dataset result
        assert dataset_result.success is False
        assert dataset_result.errors == 2
        assert len(dataset_result.error_messages) == 2
        assert 'Database connection failed' in dataset_result.error_messages
        
        # Verify aggregation updated
        aggregation = result_aggregator.current_aggregation
        assert aggregation.success is False  # Overall failure due to dataset failure
        assert aggregation.datasets_processed == 0
        assert aggregation.datasets_failed == 1

    def test_add_dataset_result_no_aggregation(self, result_aggregator, mock_bulk_update_stats):
        """Test adding dataset result without starting aggregation"""
        with pytest.raises(ValueError, match="No active aggregation"):
            result_aggregator.add_dataset_result(
                dataset_name='test',
                stats=mock_bulk_update_stats,
                execution_time=10.0
            )

    def test_add_phase_result(self, result_aggregator, mock_bulk_update_stats):
        """Test adding phase result"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=3)
        
        # Add dataset results first
        dataset_result_1 = result_aggregator.add_dataset_result(
            dataset_name='dataset_a',
            stats=mock_bulk_update_stats,
            execution_time=20.0,
            success=True
        )
        
        dataset_result_2 = result_aggregator.add_dataset_result(
            dataset_name='dataset_b', 
            stats=mock_bulk_update_stats,
            execution_time=25.0,
            success=True
        )
        
        # Add phase result
        phase_result = result_aggregator.add_phase_result(
            phase_number=1,
            phase_name='Initial Processing',
            datasets=['dataset_a', 'dataset_b'],
            execution_time=50.0,
            success=True
        )
        
        # Verify phase result
        assert isinstance(phase_result, PhaseResult)
        assert phase_result.phase_number == 1
        assert phase_result.phase_name == 'Initial Processing'
        assert phase_result.success is True
        assert phase_result.execution_time_seconds == 50.0
        assert phase_result.datasets == ['dataset_a', 'dataset_b']
        assert len(phase_result.dataset_results) == 2
        assert 'dataset_a' in phase_result.dataset_results
        assert 'dataset_b' in phase_result.dataset_results
        
        # Verify aggregated metrics in phase
        assert phase_result.total_resources_created == 400  # 200 * 2
        assert phase_result.total_triples_created == 1600   # 800 * 2
        assert phase_result.total_rows_processed == 200     # 100 * 2
        
        # Verify aggregation updated
        aggregation = result_aggregator.current_aggregation
        assert aggregation.total_phases == 1
        assert len(aggregation.phase_results) == 1

    def test_add_phase_result_no_aggregation(self, result_aggregator):
        """Test adding phase result without starting aggregation"""
        with pytest.raises(ValueError, match="No active aggregation"):
            result_aggregator.add_phase_result(
                phase_number=1,
                phase_name='Test Phase',
                datasets=[],
                execution_time=10.0
            )

    def test_finalize_aggregation(self, result_aggregator, mock_bulk_update_stats):
        """Test finalizing aggregation with calculations"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=2)
        
        # Add dataset results with different memory usage
        mock_stats_1 = Mock()
        mock_stats_1.rows_processed = 100
        mock_stats_1.resources_created = 200
        mock_stats_1.triples_created = 800
        mock_stats_1.cells_processed = 400
        mock_stats_1.truncated_values = 5
        
        dataset_result_1 = result_aggregator.add_dataset_result(
            dataset_name='dataset_1',
            stats=mock_stats_1,
            execution_time=30.0,
            success=True
        )
        dataset_result_1.peak_memory_mb = 120.0
        
        mock_stats_2 = Mock()
        mock_stats_2.rows_processed = 150
        mock_stats_2.resources_created = 300
        mock_stats_2.triples_created = 1200
        mock_stats_2.cells_processed = 600
        mock_stats_2.truncated_values = 8
        
        dataset_result_2 = result_aggregator.add_dataset_result(
            dataset_name='dataset_2',
            stats=mock_stats_2,
            execution_time=40.0,
            success=True
        )
        dataset_result_2.peak_memory_mb = 150.0
        
        # Finalize after some time
        end_time = start_time + timedelta(seconds=75)
        final_result = result_aggregator.finalize_aggregation(end_time)
        
        # Verify final result  
        assert result_aggregator.current_aggregation is None  # Should be cleared
        assert final_result is not None
        
        assert final_result.end_time == end_time
        assert final_result.total_execution_time_seconds == 75.0
        assert final_result.average_rows_per_second == 250 / 75.0  # Total rows / time
        assert final_result.peak_memory_mb == 150.0  # Max of dataset peaks
        
        # Verify error and warning summaries were generated
        assert isinstance(final_result.error_summary, list)
        assert isinstance(final_result.warning_summary, list)

    def test_finalize_aggregation_no_active(self, result_aggregator):
        """Test finalizing aggregation without active aggregation"""
        end_time = datetime.now(timezone.utc)
        
        with pytest.raises(ValueError, match="No active aggregation to finalize"):
            result_aggregator.finalize_aggregation(end_time)

    def test_generate_error_summary(self, result_aggregator, mock_bulk_update_stats):
        """Test error summary generation"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=2)
        
        # Add dataset with validation errors
        result_aggregator.add_dataset_result(
            dataset_name='dataset_1',
            stats=mock_bulk_update_stats,
            execution_time=20.0,
            success=False,
            errors=['Validation error: missing field', 'Database connection timeout']
        )
        
        # Add dataset with memory errors
        result_aggregator.add_dataset_result(
            dataset_name='dataset_2',
            stats=mock_bulk_update_stats,
            execution_time=15.0,
            success=False,
            errors=['Memory allocation failed', 'Processing timeout occurred']
        )
        
        # Trigger error summary generation
        result_aggregator._generate_error_summary()
        
        error_summary = result_aggregator.current_aggregation.error_summary
        assert len(error_summary) > 0
        
        # Should categorize errors
        summary_text = ' '.join(error_summary)
        assert 'Validation Errors' in summary_text or 'Database Errors' in summary_text
        assert 'Memory Errors' in summary_text or 'Timeout Errors' in summary_text

    def test_generate_warning_summary(self, result_aggregator, mock_bulk_update_stats):
        """Test warning summary generation"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=2)
        
        # Add dataset with various warnings
        result_aggregator.add_dataset_result(
            dataset_name='dataset_1',
            stats=mock_bulk_update_stats,
            execution_time=20.0,
            success=True,
            warnings=['Value truncated to fit field', 'Missing optional data in row 5']
        )
        
        result_aggregator.add_dataset_result(
            dataset_name='dataset_2',
            stats=mock_bulk_update_stats,
            execution_time=25.0,
            success=True,
            warnings=['Performance warning: slow processing', 'Validation warning: suspicious value']
        )
        
        # Trigger warning summary generation
        result_aggregator._generate_warning_summary()
        
        warning_summary = result_aggregator.current_aggregation.warning_summary
        assert len(warning_summary) > 0
        
        # Should categorize warnings
        summary_text = ' '.join(warning_summary)
        assert any(category in summary_text for category in 
                  ['Truncated Values', 'Missing Data', 'Performance Warnings', 'Validation Warnings'])

    def test_get_quality_assessment_excellent(self, result_aggregator):
        """Test quality assessment for excellent results"""
        # Create aggregated result with excellent quality
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=60.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_datasets=2,
            datasets_processed=2,
            datasets_failed=0,
            total_resources_created=1000,
            total_errors=0,
            total_warnings=5,
            total_truncated_values=0
        )
        
        quality_assessment = result_aggregator.get_quality_assessment(result)
        
        assert quality_assessment['quality_score'] >= 0.9
        assert quality_assessment['quality_grade'] == 'Excellent'
        assert len(quality_assessment['quality_issues']) == 0
        assert quality_assessment['metrics']['success_rate'] == 1.0
        assert quality_assessment['metrics']['error_rate'] == 0.0

    def test_get_quality_assessment_poor(self, result_aggregator):
        """Test quality assessment for poor results"""
        # Create aggregated result with poor quality
        result = AggregatedResult(
            success=False,
            total_execution_time_seconds=120.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_datasets=4,
            datasets_processed=2,
            datasets_failed=2,
            total_resources_created=100,
            total_errors=50,  # High error rate
            total_warnings=20,
            total_truncated_values=30  # High truncation rate
        )
        
        quality_assessment = result_aggregator.get_quality_assessment(result)
        
        assert quality_assessment['quality_score'] < 0.5
        assert quality_assessment['quality_grade'] == 'Poor'
        assert len(quality_assessment['quality_issues']) > 0
        assert 'High error rate' in ' '.join(quality_assessment['quality_issues'])
        assert 'High truncation rate' in ' '.join(quality_assessment['quality_issues'])

    def test_generate_quality_recommendations(self, result_aggregator):
        """Test quality improvement recommendations"""
        # Create result with various issues
        result = AggregatedResult(
            success=False,
            total_execution_time_seconds=300.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_datasets=3,
            datasets_processed=2,
            datasets_failed=1,
            total_resources_created=500,
            total_errors=60,  # 12% error rate
            total_warnings=25,
            total_truncated_values=30,  # 6% truncation rate
            average_rows_per_second=500  # Low performance
        )
        
        quality_issues = ['High error rate: 12.0%', 'High truncation rate: 6.0%', 'Low success rate: 66.7%']
        recommendations = result_aggregator._generate_quality_recommendations(result, quality_issues)
        
        assert len(recommendations) > 0
        recommendation_text = ' '.join(recommendations)
        assert 'error logs' in recommendation_text or 'data quality' in recommendation_text
        assert 'truncated values' in recommendation_text or 'field sizes' in recommendation_text
        assert 'failed datasets' in recommendation_text or 'underlying issues' in recommendation_text

    def test_generate_summary_report(self, result_aggregator):
        """Test comprehensive summary report generation"""
        # Create sample aggregated result
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=90)
        
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=90.0,
            start_time=start_time,
            end_time=end_time,
            total_datasets=3,
            datasets_processed=3,
            datasets_failed=0,
            total_resources_created=750,
            total_triples_created=3000,
            total_rows_processed=300,
            total_cells_processed=1200,
            total_errors=2,
            total_warnings=5,
            total_truncated_values=3,
            average_rows_per_second=300/90,
            peak_memory_mb=125.0
        )
        
        # Add dataset breakdown
        result.dataset_results = {
            'dataset_1': DatasetResult(
                dataset_name='dataset_1',
                success=True,
                execution_time_seconds=30.0,
                resources_created=250,
                errors=0,
                warnings=1
            ),
            'dataset_2': DatasetResult(
                dataset_name='dataset_2',
                success=True,
                execution_time_seconds=35.0,
                resources_created=300,
                errors=1,
                warnings=2
            ),
            'dataset_3': DatasetResult(
                dataset_name='dataset_3',
                success=True,
                execution_time_seconds=25.0,
                resources_created=200,
                errors=1,
                warnings=2
            )
        }
        
        # Add phase breakdown
        result.phase_results = [
            PhaseResult(
                phase_number=1,
                phase_name='Initial Phase',
                success=True,
                execution_time_seconds=45.0,
                datasets=['dataset_1', 'dataset_2'],
                total_resources_created=550
            ),
            PhaseResult(
                phase_number=2,
                phase_name='Final Phase',
                success=True,
                execution_time_seconds=45.0,
                datasets=['dataset_3'],
                total_resources_created=200
            )
        ]
        
        summary_report = result_aggregator.generate_summary_report(result)
        
        # Verify report structure
        assert 'execution_summary' in summary_report
        assert 'processing_metrics' in summary_report
        assert 'quality_metrics' in summary_report
        assert 'performance_summary' in summary_report
        assert 'quality_assessment' in summary_report
        assert 'dataset_breakdown' in summary_report
        assert 'phase_breakdown' in summary_report
        
        # Verify execution summary
        exec_summary = summary_report['execution_summary']
        assert exec_summary['success'] is True
        assert exec_summary['total_execution_time_seconds'] == 90.0
        assert exec_summary['datasets_processed'] == 3
        assert exec_summary['datasets_failed'] == 0
        assert exec_summary['success_rate_percentage'] == 100.0
        
        # Verify processing metrics
        proc_metrics = summary_report['processing_metrics']
        assert proc_metrics['total_resources_created'] == 750
        assert proc_metrics['total_triples_created'] == 3000
        
        # Verify dataset breakdown
        dataset_breakdown = summary_report['dataset_breakdown']
        assert len(dataset_breakdown) == 3
        assert all('dataset_name' in ds for ds in dataset_breakdown)
        assert all('success' in ds for ds in dataset_breakdown)
        
        # Verify phase breakdown
        phase_breakdown = summary_report['phase_breakdown']
        assert len(phase_breakdown) == 2
        assert phase_breakdown[0]['phase_number'] == 1
        assert phase_breakdown[1]['phase_number'] == 2


class TestDatasetResult:
    """Test suite for DatasetResult class"""

    def test_dataset_result_initialization(self):
        """Test DatasetResult initialization"""
        result = DatasetResult(
            dataset_name='test_dataset',
            success=True,
            execution_time_seconds=45.5,
            rows_processed=100,
            resources_created=200,
            triples_created=800,
            cells_processed=400,
            errors=2,
            warnings=3,
            phase_number=1,
            strategy_used='entity_centric'
        )
        
        assert result.dataset_name == 'test_dataset'
        assert result.success is True
        assert result.execution_time_seconds == 45.5
        assert result.rows_processed == 100
        assert result.resources_created == 200
        assert result.triples_created == 800
        assert result.cells_processed == 400
        assert result.errors == 2
        assert result.warnings == 3
        assert result.phase_number == 1
        assert result.strategy_used == 'entity_centric'

    def test_add_error_method(self):
        """Test adding error to dataset result"""
        result = DatasetResult(
            dataset_name='test',
            success=True,
            execution_time_seconds=10.0
        )
        
        result.add_error('Test error message')
        
        assert result.success is False
        assert result.errors == 1
        assert len(result.error_messages) == 1
        assert 'Test error message' in result.error_messages

    def test_add_warning_method(self):
        """Test adding warning to dataset result"""
        result = DatasetResult(
            dataset_name='test',
            success=True,
            execution_time_seconds=10.0
        )
        
        result.add_warning('Test warning message')
        
        assert result.warnings == 1
        assert len(result.warning_messages) == 1
        assert 'Test warning message' in result.warning_messages


class TestPhaseResult:
    """Test suite for PhaseResult class"""

    def test_phase_result_initialization(self):
        """Test PhaseResult initialization"""
        result = PhaseResult(
            phase_number=1,
            phase_name='Initial Phase',
            success=True,
            execution_time_seconds=60.0,
            datasets=['dataset_a', 'dataset_b']
        )
        
        assert result.phase_number == 1
        assert result.phase_name == 'Initial Phase'
        assert result.success is True
        assert result.execution_time_seconds == 60.0
        assert result.datasets == ['dataset_a', 'dataset_b']
        assert result.dataset_results == {}
        assert result.total_resources_created == 0

    def test_add_dataset_result_method(self):
        """Test adding dataset result to phase"""
        phase_result = PhaseResult(
            phase_number=1,
            phase_name='Test Phase',
            success=True,
            execution_time_seconds=30.0
        )
        
        dataset_result = DatasetResult(
            dataset_name='test_dataset',
            success=True,
            execution_time_seconds=15.0,
            resources_created=100,
            triples_created=400,
            rows_processed=50,
            errors=1,
            warnings=2
        )
        
        phase_result.add_dataset_result(dataset_result)
        
        # Verify dataset was added
        assert 'test_dataset' in phase_result.dataset_results
        assert phase_result.dataset_results['test_dataset'] == dataset_result
        
        # Verify aggregated metrics
        assert phase_result.total_resources_created == 100
        assert phase_result.total_triples_created == 400
        assert phase_result.total_rows_processed == 50
        assert phase_result.total_errors == 1
        assert phase_result.total_warnings == 2

    def test_add_failed_dataset_result(self):
        """Test adding failed dataset result affects phase success"""
        phase_result = PhaseResult(
            phase_number=1,
            phase_name='Test Phase',
            success=True,
            execution_time_seconds=30.0
        )
        
        failed_dataset = DatasetResult(
            dataset_name='failed_dataset',
            success=False,
            execution_time_seconds=10.0,
            errors=3
        )
        
        phase_result.add_dataset_result(failed_dataset)
        
        # Phase should now be marked as failed
        assert phase_result.success is False
        assert phase_result.total_errors == 3


class TestAggregatedResult:
    """Test suite for AggregatedResult class"""

    def test_aggregated_result_initialization(self):
        """Test AggregatedResult initialization"""
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=120)
        
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=120.0,
            start_time=start_time,
            end_time=end_time,
            total_datasets=5,
            datasets_processed=4,
            datasets_failed=1
        )
        
        assert result.success is True
        assert result.total_execution_time_seconds == 120.0
        assert result.start_time == start_time
        assert result.end_time == end_time
        assert result.total_datasets == 5
        assert result.datasets_processed == 4
        assert result.datasets_failed == 1

    def test_get_success_rate(self):
        """Test success rate calculation"""
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=60.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_datasets=4,
            datasets_processed=3
        )
        
        success_rate = result.get_success_rate()
        assert success_rate == 75.0

    def test_get_success_rate_zero_datasets(self):
        """Test success rate with zero total datasets"""
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=60.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_datasets=0,
            datasets_processed=0
        )
        
        success_rate = result.get_success_rate()
        assert success_rate == 0.0

    def test_get_performance_summary(self):
        """Test performance summary generation"""
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=90.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_resources_created=900,
            total_triples_created=3600,
            average_rows_per_second=55.5,
            peak_memory_mb=200.0
        )
        
        perf_summary = result.get_performance_summary()
        
        assert perf_summary['total_execution_time_seconds'] == 90.0
        assert perf_summary['average_rows_per_second'] == 55.5
        assert perf_summary['peak_memory_mb'] == 200.0
        assert perf_summary['resources_per_second'] == 10.0  # 900/90
        assert perf_summary['triples_per_second'] == 40.0    # 3600/90

    def test_get_performance_summary_zero_time(self):
        """Test performance summary with zero execution time"""
        result = AggregatedResult(
            success=True,
            total_execution_time_seconds=0.0,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            total_resources_created=100,
            total_triples_created=400
        )
        
        perf_summary = result.get_performance_summary()
        
        assert perf_summary['resources_per_second'] == 0
        assert perf_summary['triples_per_second'] == 0


class TestResultAggregatorIntegration:
    """Integration tests for ResultAggregator"""

    def test_complete_aggregation_workflow(self, result_aggregator):
        """Test complete aggregation workflow from start to finish"""
        start_time = datetime.now(timezone.utc)
        
        # Start aggregation
        result_aggregator.start_aggregation(start_time, total_datasets=3)
        
        # Create mock stats for different datasets
        mock_stats_1 = Mock()
        mock_stats_1.rows_processed = 100
        mock_stats_1.resources_created = 200
        mock_stats_1.triples_created = 800
        mock_stats_1.cells_processed = 400
        mock_stats_1.truncated_values = 2
        
        mock_stats_2 = Mock()
        mock_stats_2.rows_processed = 150
        mock_stats_2.resources_created = 300
        mock_stats_2.triples_created = 1200
        mock_stats_2.cells_processed = 600
        mock_stats_2.truncated_values = 3
        
        mock_stats_3 = Mock()
        mock_stats_3.rows_processed = 75
        mock_stats_3.resources_created = 150
        mock_stats_3.triples_created = 600
        mock_stats_3.cells_processed = 300
        mock_stats_3.truncated_values = 1
        
        # Add dataset results
        dataset_1 = result_aggregator.add_dataset_result(
            dataset_name='dataset_a',
            stats=mock_stats_1,
            execution_time=30.0,
            success=True,
            warnings=['Minor issue'],
            phase_number=1
        )
        dataset_1.peak_memory_mb = 120.0
        
        dataset_2 = result_aggregator.add_dataset_result(
            dataset_name='dataset_b',
            stats=mock_stats_2,
            execution_time=40.0,
            success=True,
            errors=['Validation warning'],
            phase_number=1
        )
        dataset_2.peak_memory_mb = 150.0
        
        dataset_3 = result_aggregator.add_dataset_result(
            dataset_name='dataset_c',
            stats=mock_stats_3,
            execution_time=25.0,
            success=True,
            phase_number=2
        )
        dataset_3.peak_memory_mb = 100.0
        
        # Add phase results
        phase_1 = result_aggregator.add_phase_result(
            phase_number=1,
            phase_name='First Phase',
            datasets=['dataset_a', 'dataset_b'],
            execution_time=75.0,
            success=True
        )
        
        phase_2 = result_aggregator.add_phase_result(
            phase_number=2,
            phase_name='Second Phase',
            datasets=['dataset_c'],
            execution_time=30.0,
            success=True
        )
        
        # Finalize aggregation
        end_time = start_time + timedelta(seconds=110)
        final_result = result_aggregator.finalize_aggregation(end_time)
        
        # Verify final aggregated result
        assert final_result.success is True
        assert final_result.total_datasets == 3
        assert final_result.datasets_processed == 3
        assert final_result.datasets_failed == 0
        assert final_result.total_phases == 2
        assert final_result.total_execution_time_seconds == 110.0
        assert final_result.total_resources_created == 650  # 200+300+150
        assert final_result.total_triples_created == 2600   # 800+1200+600
        assert final_result.total_rows_processed == 325     # 100+150+75
        assert final_result.total_cells_processed == 1300   # 400+600+300
        assert final_result.total_truncated_values == 6     # 2+3+1
        assert final_result.peak_memory_mb == 150.0
        assert final_result.average_rows_per_second == 325 / 110.0
        
        # Verify dataset breakdown
        assert len(final_result.dataset_results) == 3
        assert 'dataset_a' in final_result.dataset_results
        assert 'dataset_b' in final_result.dataset_results
        assert 'dataset_c' in final_result.dataset_results
        
        # Verify phase breakdown
        assert len(final_result.phase_results) == 2
        assert final_result.phase_results[0].phase_number == 1
        assert final_result.phase_results[1].phase_number == 2
        
        # Generate and verify summary report
        summary_report = result_aggregator.generate_summary_report(final_result)
        assert summary_report['execution_summary']['success'] is True
        assert summary_report['execution_summary']['datasets_processed'] == 3
        assert len(summary_report['dataset_breakdown']) == 3
        assert len(summary_report['phase_breakdown']) == 2

    def test_aggregation_with_failures(self, result_aggregator):
        """Test aggregation workflow with some failures"""
        start_time = datetime.now(timezone.utc)
        result_aggregator.start_aggregation(start_time, total_datasets=3)
        
        # Mock stats for mixed success/failure
        success_stats = Mock()
        success_stats.rows_processed = 100
        success_stats.resources_created = 200
        success_stats.triples_created = 800
        success_stats.cells_processed = 400
        success_stats.truncated_values = 0
        
        failure_stats = Mock()
        failure_stats.rows_processed = 0
        failure_stats.resources_created = 0
        failure_stats.triples_created = 0
        failure_stats.cells_processed = 0
        failure_stats.truncated_values = 0
        
        # Add successful dataset
        result_aggregator.add_dataset_result(
            dataset_name='success_dataset',
            stats=success_stats,
            execution_time=30.0,
            success=True
        )
        
        # Add failed datasets
        result_aggregator.add_dataset_result(
            dataset_name='failed_dataset_1',
            stats=failure_stats,
            execution_time=15.0,
            success=False,
            errors=['Database connection failed']
        )
        
        result_aggregator.add_dataset_result(
            dataset_name='failed_dataset_2',
            stats=failure_stats,
            execution_time=10.0,
            success=False,
            errors=['Invalid data format', 'Validation failed']
        )
        
        # Finalize
        end_time = start_time + timedelta(seconds=60)
        final_result = result_aggregator.finalize_aggregation(end_time)
        
        # Verify failure handling
        assert final_result.success is False  # Overall failure
        assert final_result.datasets_processed == 1
        assert final_result.datasets_failed == 2
        assert final_result.get_success_rate() == (1/3) * 100  # 33.33%
        assert final_result.total_errors == 3  # 0 + 1 + 2
        
        # Quality assessment should reflect poor quality
        quality_assessment = result_aggregator.get_quality_assessment(final_result)
        assert quality_assessment['quality_grade'] in ['Poor', 'Fair']
        assert len(quality_assessment['quality_issues']) > 0