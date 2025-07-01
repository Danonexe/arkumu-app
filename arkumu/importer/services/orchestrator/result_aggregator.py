"""
Result Aggregator

Aggregates results across datasets and processing phases.
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class DatasetResult:
    """Result for a single dataset"""
    dataset_name: str
    success: bool
    execution_time_seconds: float
    
    # Processing metrics
    rows_processed: int = 0
    resources_created: int = 0
    triples_created: int = 0
    cells_processed: int = 0
    
    # Quality metrics
    errors: int = 0
    warnings: int = 0
    truncated_values: int = 0
    
    # Performance metrics
    rows_per_second: float = 0.0
    peak_memory_mb: float = 0.0
    
    # Error details
    error_messages: List[str] = field(default_factory=list)
    warning_messages: List[str] = field(default_factory=list)
    
    # Processing details
    phase_number: Optional[int] = None
    strategy_used: str = "unknown"
    
    def add_error(self, message: str):
        """Add an error message"""
        self.error_messages.append(message)
        self.errors += 1
        self.success = False
    
    def add_warning(self, message: str):
        """Add a warning message"""
        self.warning_messages.append(message)
        self.warnings += 1


@dataclass
class PhaseResult:
    """Result for a processing phase"""
    phase_number: int
    phase_name: str
    success: bool
    execution_time_seconds: float
    
    # Datasets in this phase
    datasets: List[str] = field(default_factory=list)
    dataset_results: Dict[str, DatasetResult] = field(default_factory=dict)
    
    # Aggregated metrics
    total_resources_created: int = 0
    total_triples_created: int = 0
    total_rows_processed: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    
    def add_dataset_result(self, result: DatasetResult):
        """Add a dataset result to this phase"""
        self.dataset_results[result.dataset_name] = result
        
        # Aggregate metrics
        self.total_resources_created += result.resources_created
        self.total_triples_created += result.triples_created
        self.total_rows_processed += result.rows_processed
        self.total_errors += result.errors
        self.total_warnings += result.warnings
        
        # Update success status
        if not result.success:
            self.success = False


@dataclass
class AggregatedResult:
    """Aggregated result across all datasets and phases"""
    success: bool
    total_execution_time_seconds: float
    start_time: datetime
    end_time: datetime
    
    # High-level metrics
    total_datasets: int = 0
    datasets_processed: int = 0
    datasets_failed: int = 0
    total_phases: int = 0
    
    # Processing metrics
    total_resources_created: int = 0
    total_triples_created: int = 0
    total_rows_processed: int = 0
    total_cells_processed: int = 0
    
    # Quality metrics
    total_errors: int = 0
    total_warnings: int = 0
    total_truncated_values: int = 0
    
    # Performance metrics
    average_rows_per_second: float = 0.0
    peak_memory_mb: float = 0.0
    
    # Results breakdown
    dataset_results: Dict[str, DatasetResult] = field(default_factory=dict)
    phase_results: List[PhaseResult] = field(default_factory=list)
    
    # Error and warning summaries
    error_summary: List[str] = field(default_factory=list)
    warning_summary: List[str] = field(default_factory=list)
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.total_datasets == 0:
            return 0.0
        return (self.datasets_processed / self.total_datasets) * 100.0
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        return {
            'total_execution_time_seconds': self.total_execution_time_seconds,
            'average_rows_per_second': self.average_rows_per_second,
            'peak_memory_mb': self.peak_memory_mb,
            'resources_per_second': self.total_resources_created / self.total_execution_time_seconds if self.total_execution_time_seconds > 0 else 0,
            'triples_per_second': self.total_triples_created / self.total_execution_time_seconds if self.total_execution_time_seconds > 0 else 0
        }


class ResultAggregator:
    """
    Aggregates results across datasets and processing phases.
    
    Provides comprehensive result analysis, performance metrics,
    and quality assessment for import operations.
    """
    
    def __init__(self):
        self.current_aggregation: Optional[AggregatedResult] = None
    
    def start_aggregation(self, start_time: datetime, total_datasets: int) -> AggregatedResult:
        """
        Start a new result aggregation.
        
        Args:
            start_time: Import start time
            total_datasets: Total number of datasets to process
            
        Returns:
            New AggregatedResult object
        """
        self.current_aggregation = AggregatedResult(
            success=True,
            total_execution_time_seconds=0.0,
            start_time=start_time,
            end_time=start_time,
            total_datasets=total_datasets
        )
        
        logger.info(f"Started result aggregation for {total_datasets} datasets")
        return self.current_aggregation
    
    def add_dataset_result(self,
                          dataset_name: str,
                          stats: Any,  # BulkUpdateStats or similar
                          execution_time: float,
                          success: bool = True,
                          errors: Optional[List[str]] = None,
                          warnings: Optional[List[str]] = None,
                          phase_number: Optional[int] = None,
                          strategy_used: str = "unknown") -> DatasetResult:
        """
        Add result for a single dataset.
        
        Args:
            dataset_name: Name of the dataset
            stats: Processing statistics
            execution_time: Dataset execution time in seconds
            success: Whether processing succeeded
            errors: List of error messages
            warnings: List of warning messages
            phase_number: Phase number (for multi-phase processing)
            strategy_used: Processing strategy used
            
        Returns:
            DatasetResult object
        """
        if not self.current_aggregation:
            raise ValueError("No active aggregation - call start_aggregation first")
        
        # Extract metrics from stats object
        rows_processed = getattr(stats, 'rows_processed', 0)
        resources_created = getattr(stats, 'resources_created', 0)
        triples_created = getattr(stats, 'triples_created', 0)
        cells_processed = getattr(stats, 'cells_processed', 0)
        truncated_values = getattr(stats, 'truncated_values', 0)
        
        # Calculate performance metrics
        rows_per_second = rows_processed / execution_time if execution_time > 0 else 0
        
        # Create dataset result
        dataset_result = DatasetResult(
            dataset_name=dataset_name,
            success=success,
            execution_time_seconds=execution_time,
            rows_processed=rows_processed,
            resources_created=resources_created,
            triples_created=triples_created,
            cells_processed=cells_processed,
            truncated_values=truncated_values,
            rows_per_second=rows_per_second,
            phase_number=phase_number,
            strategy_used=strategy_used
        )
        
        # Add errors and warnings
        if errors:
            for error in errors:
                dataset_result.add_error(error)
        
        if warnings:
            for warning in warnings:
                dataset_result.add_warning(warning)
        
        # Add to aggregation
        self.current_aggregation.dataset_results[dataset_name] = dataset_result
        
        # Update aggregated metrics
        if success:
            self.current_aggregation.datasets_processed += 1
        else:
            self.current_aggregation.datasets_failed += 1
            self.current_aggregation.success = False
        
        self.current_aggregation.total_resources_created += resources_created
        self.current_aggregation.total_triples_created += triples_created
        self.current_aggregation.total_rows_processed += rows_processed
        self.current_aggregation.total_cells_processed += cells_processed
        self.current_aggregation.total_errors += dataset_result.errors
        self.current_aggregation.total_warnings += dataset_result.warnings
        self.current_aggregation.total_truncated_values += truncated_values
        
        logger.info(f"Added dataset result for '{dataset_name}': "
                   f"{resources_created} resources, {triples_created} triples")
        
        return dataset_result
    
    def add_phase_result(self,
                        phase_number: int,
                        phase_name: str,
                        datasets: List[str],
                        execution_time: float,
                        success: bool = True) -> PhaseResult:
        """
        Add result for a processing phase.
        
        Args:
            phase_number: Phase number
            phase_name: Phase name
            datasets: List of datasets in this phase
            execution_time: Phase execution time in seconds
            success: Whether phase succeeded
            
        Returns:
            PhaseResult object
        """
        if not self.current_aggregation:
            raise ValueError("No active aggregation - call start_aggregation first")
        
        phase_result = PhaseResult(
            phase_number=phase_number,
            phase_name=phase_name,
            success=success,
            execution_time_seconds=execution_time,
            datasets=datasets
        )
        
        # Add dataset results to this phase
        for dataset_name in datasets:
            if dataset_name in self.current_aggregation.dataset_results:
                dataset_result = self.current_aggregation.dataset_results[dataset_name]
                dataset_result.phase_number = phase_number
                phase_result.add_dataset_result(dataset_result)
        
        self.current_aggregation.phase_results.append(phase_result)
        self.current_aggregation.total_phases += 1
        
        if not success:
            self.current_aggregation.success = False
        
        logger.info(f"Added phase result for phase {phase_number}: "
                   f"{len(datasets)} datasets, {execution_time:.1f}s")
        
        return phase_result
    
    def finalize_aggregation(self, end_time: datetime) -> AggregatedResult:
        """
        Finalize the current aggregation.
        
        Args:
            end_time: Import end time
            
        Returns:
            Finalized AggregatedResult
        """
        if not self.current_aggregation:
            raise ValueError("No active aggregation to finalize")
        
        self.current_aggregation.end_time = end_time
        self.current_aggregation.total_execution_time_seconds = (
            end_time - self.current_aggregation.start_time
        ).total_seconds()
        
        # Calculate final performance metrics
        if self.current_aggregation.total_execution_time_seconds > 0:
            self.current_aggregation.average_rows_per_second = (
                self.current_aggregation.total_rows_processed / 
                self.current_aggregation.total_execution_time_seconds
            )
        
        # Calculate peak memory usage across all datasets
        peak_memory = 0.0
        for result in self.current_aggregation.dataset_results.values():
            if result.peak_memory_mb > peak_memory:
                peak_memory = result.peak_memory_mb
        self.current_aggregation.peak_memory_mb = peak_memory
        
        # Generate error and warning summaries
        self._generate_error_summary()
        self._generate_warning_summary()
        
        logger.info(f"Finalized aggregation: {self.current_aggregation.datasets_processed}/"
                   f"{self.current_aggregation.total_datasets} datasets, "
                   f"{self.current_aggregation.total_resources_created} resources, "
                   f"{self.current_aggregation.total_execution_time_seconds:.1f}s")
        
        result = self.current_aggregation
        self.current_aggregation = None
        return result
    
    def _generate_error_summary(self):
        """Generate error summary across all datasets"""
        if not self.current_aggregation:
            return
        
        error_counts = {}
        
        for dataset_result in self.current_aggregation.dataset_results.values():
            for error in dataset_result.error_messages:
                # Categorize errors
                if "validation" in error.lower():
                    category = "Validation Errors"
                elif "database" in error.lower() or "db" in error.lower():
                    category = "Database Errors"
                elif "memory" in error.lower():
                    category = "Memory Errors"
                elif "timeout" in error.lower():
                    category = "Timeout Errors"
                else:
                    category = "Processing Errors"
                
                if category not in error_counts:
                    error_counts[category] = 0
                error_counts[category] += 1
        
        # Create summary
        for category, count in error_counts.items():
            self.current_aggregation.error_summary.append(f"{category}: {count}")
    
    def _generate_warning_summary(self):
        """Generate warning summary across all datasets"""
        if not self.current_aggregation:
            return
        
        warning_counts = {}
        
        for dataset_result in self.current_aggregation.dataset_results.values():
            for warning in dataset_result.warning_messages:
                # Categorize warnings
                if "truncated" in warning.lower():
                    category = "Truncated Values"
                elif "missing" in warning.lower():
                    category = "Missing Data"
                elif "performance" in warning.lower():
                    category = "Performance Warnings"
                elif "validation" in warning.lower():
                    category = "Validation Warnings"
                else:
                    category = "General Warnings"
                
                if category not in warning_counts:
                    warning_counts[category] = 0
                warning_counts[category] += 1
        
        # Create summary
        for category, count in warning_counts.items():
            self.current_aggregation.warning_summary.append(f"{category}: {count}")
    
    def get_quality_assessment(self, result: AggregatedResult) -> Dict[str, Any]:
        """
        Generate quality assessment for aggregated results.
        
        Args:
            result: AggregatedResult to assess
            
        Returns:
            Quality assessment dictionary
        """
        total_values = result.total_resources_created
        
        quality_score = 1.0
        quality_issues = []
        
        # Error rate assessment
        if result.total_errors > 0:
            error_rate = result.total_errors / total_values if total_values > 0 else 1.0
            if error_rate > 0.1:
                quality_score -= 0.5
                quality_issues.append(f"High error rate: {error_rate:.1%}")
            elif error_rate > 0.05:
                quality_score -= 0.2
                quality_issues.append(f"Moderate error rate: {error_rate:.1%}")
        
        # Truncation assessment
        if result.total_truncated_values > 0:
            truncation_rate = result.total_truncated_values / total_values if total_values > 0 else 0
            if truncation_rate > 0.05:
                quality_score -= 0.3
                quality_issues.append(f"High truncation rate: {truncation_rate:.1%}")
            elif truncation_rate > 0.01:
                quality_score -= 0.1
                quality_issues.append(f"Moderate truncation rate: {truncation_rate:.1%}")
        
        # Success rate assessment
        success_rate = result.get_success_rate() / 100
        if success_rate < 0.9:
            quality_score -= (1.0 - success_rate) * 0.5
            quality_issues.append(f"Low success rate: {success_rate:.1%}")
        
        # Determine quality grade
        if quality_score >= 0.9:
            quality_grade = "Excellent"
        elif quality_score >= 0.7:
            quality_grade = "Good"
        elif quality_score >= 0.5:
            quality_grade = "Fair"
        else:
            quality_grade = "Poor"
        
        return {
            'quality_score': max(quality_score, 0.0),
            'quality_grade': quality_grade,
            'quality_issues': quality_issues,
            'metrics': {
                'success_rate': success_rate,
                'error_rate': result.total_errors / total_values if total_values > 0 else 0,
                'truncation_rate': result.total_truncated_values / total_values if total_values > 0 else 0,
                'warning_rate': result.total_warnings / total_values if total_values > 0 else 0
            },
            'recommendations': self._generate_quality_recommendations(result, quality_issues)
        }
    
    def _generate_quality_recommendations(self,
                                        result: AggregatedResult,
                                        quality_issues: List[str]) -> List[str]:
        """Generate quality improvement recommendations"""
        
        recommendations = []
        
        # Error-based recommendations
        if result.total_errors > 0:
            recommendations.append("Review error logs and fix data quality issues")
            if result.total_errors > result.total_resources_created * 0.1:
                recommendations.append("Consider data validation and cleaning before import")
        
        # Truncation recommendations
        if result.total_truncated_values > 0:
            recommendations.append("Review truncated values and consider increasing field sizes")
        
        # Performance recommendations
        if result.average_rows_per_second < 1000:
            recommendations.append("Consider optimizing processing strategy for better performance")
        
        # Success rate recommendations
        if result.get_success_rate() < 90:
            recommendations.append("Investigate failed datasets and resolve underlying issues")
        
        return recommendations
    
    def generate_summary_report(self, result: AggregatedResult) -> Dict[str, Any]:
        """
        Generate comprehensive summary report.
        
        Args:
            result: AggregatedResult to summarize
            
        Returns:
            Summary report dictionary
        """
        quality_assessment = self.get_quality_assessment(result)
        performance_summary = result.get_performance_summary()
        
        return {
            'execution_summary': {
                'success': result.success,
                'total_execution_time_seconds': result.total_execution_time_seconds,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'datasets_processed': result.datasets_processed,
                'datasets_failed': result.datasets_failed,
                'success_rate_percentage': result.get_success_rate()
            },
            'processing_metrics': {
                'total_resources_created': result.total_resources_created,
                'total_triples_created': result.total_triples_created,
                'total_rows_processed': result.total_rows_processed,
                'total_cells_processed': result.total_cells_processed
            },
            'quality_metrics': {
                'total_errors': result.total_errors,
                'total_warnings': result.total_warnings,
                'total_truncated_values': result.total_truncated_values,
                'error_summary': result.error_summary,
                'warning_summary': result.warning_summary
            },
            'performance_summary': performance_summary,
            'quality_assessment': quality_assessment,
            'dataset_breakdown': [
                {
                    'dataset_name': name,
                    'success': ds_result.success,
                    'resources_created': ds_result.resources_created,
                    'execution_time_seconds': ds_result.execution_time_seconds,
                    'errors': ds_result.errors,
                    'warnings': ds_result.warnings
                }
                for name, ds_result in result.dataset_results.items()
            ],
            'phase_breakdown': [
                {
                    'phase_number': phase.phase_number,
                    'phase_name': phase.phase_name,
                    'success': phase.success,
                    'datasets': phase.datasets,
                    'execution_time_seconds': phase.execution_time_seconds,
                    'resources_created': phase.total_resources_created
                }
                for phase in result.phase_results
            ] if result.phase_results else None
        }