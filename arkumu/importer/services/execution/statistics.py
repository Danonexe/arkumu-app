"""
Statistics and metrics tracking for execution engine.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Detailed metrics for a single execution."""
    
    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # Data processing
    rows_processed: int = 0
    cells_processed: int = 0
    columns_processed: int = 0
    
    # Resource operations
    resources_created: int = 0
    resources_updated: int = 0
    resources_skipped: int = 0
    
    # Triple operations
    triples_created: int = 0
    triples_updated: int = 0
    
    # Values
    values_created: int = 0
    values_truncated: int = 0
    
    # Errors
    errors: int = 0
    warnings: int = 0
    
    # FK processing
    fk_relationships_created: int = 0
    fk_dependencies_resolved: int = 0
    cross_dataset_links: int = 0
    
    # External ontology
    external_ontology_lookups: int = 0
    external_ontology_matches: int = 0
    
    # Multi-value processing
    multi_value_cells_split: int = 0
    multi_value_items_created: int = 0
    
    # Entity processing
    stub_entities_created: int = 0
    relationships_created: int = 0
    
    def duration_seconds(self) -> float:
        """Calculate execution duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def merge(self, other: 'ExecutionMetrics') -> None:
        """Merge another metrics object into this one."""
        # Data processing
        self.rows_processed += other.rows_processed
        self.cells_processed += other.cells_processed
        self.columns_processed += other.columns_processed
        
        # Resource operations
        self.resources_created += other.resources_created
        self.resources_updated += other.resources_updated
        self.resources_skipped += other.resources_skipped
        
        # Triple operations  
        self.triples_created += other.triples_created
        self.triples_updated += other.triples_updated
        
        # Values
        self.values_created += other.values_created
        self.values_truncated += other.values_truncated
        
        # Errors
        self.errors += other.errors
        self.warnings += other.warnings
        
        # FK processing
        self.fk_relationships_created += other.fk_relationships_created
        self.fk_dependencies_resolved += other.fk_dependencies_resolved
        self.cross_dataset_links += other.cross_dataset_links
        
        # External ontology
        self.external_ontology_lookups += other.external_ontology_lookups
        self.external_ontology_matches += other.external_ontology_matches
        
        # Multi-value
        self.multi_value_cells_split += other.multi_value_cells_split
        self.multi_value_items_created += other.multi_value_items_created
        
        # Entity processing
        self.stub_entities_created += other.stub_entities_created
        self.relationships_created += other.relationships_created
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'duration_seconds': self.duration_seconds(),
            'rows_processed': self.rows_processed,
            'cells_processed': self.cells_processed,
            'columns_processed': self.columns_processed,
            'resources_created': self.resources_created,
            'resources_updated': self.resources_updated,
            'resources_skipped': self.resources_skipped,
            'triples_created': self.triples_created,
            'values_created': self.values_created,
            'values_truncated': self.values_truncated,
            'errors': self.errors,
            'warnings': self.warnings,
            'fk_relationships_created': self.fk_relationships_created,
            'external_ontology_matches': self.external_ontology_matches,
            'multi_value_items_created': self.multi_value_items_created,
            'stub_entities_created': self.stub_entities_created,
            'relationships_created': self.relationships_created
        }


class ExecutionStatistics:
    """Statistics tracker for execution operations."""
    
    def __init__(self):
        self.current_metrics = ExecutionMetrics()
        self.dataset_metrics: Dict[str, ExecutionMetrics] = {}
        
    def start_execution(self) -> None:
        """Mark the start of execution."""
        self.current_metrics.start_time = datetime.now(timezone.utc)
        logger.info("Execution statistics tracking started")
    
    def end_execution(self) -> None:
        """Mark the end of execution."""
        self.current_metrics.end_time = datetime.now(timezone.utc)
        duration = self.current_metrics.duration_seconds()
        logger.info(f"Execution completed in {duration:.2f} seconds")
    
    def start_dataset(self, dataset_name: str) -> None:
        """Start tracking a specific dataset."""
        if dataset_name not in self.dataset_metrics:
            self.dataset_metrics[dataset_name] = ExecutionMetrics()
        self.dataset_metrics[dataset_name].start_time = datetime.now(timezone.utc)
    
    def end_dataset(self, dataset_name: str) -> None:
        """End tracking a specific dataset."""
        if dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].end_time = datetime.now(timezone.utc)
    
    def increment_resources_created(self, count: int = 1, dataset_name: Optional[str] = None) -> None:
        """Increment resource creation count."""
        self.current_metrics.resources_created += count
        if dataset_name and dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].resources_created += count
    
    def increment_fk_relationships(self, count: int = 1, dataset_name: Optional[str] = None) -> None:
        """Increment FK relationship count."""
        self.current_metrics.fk_relationships_created += count
        if dataset_name and dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].fk_relationships_created += count
    
    def increment_external_ontology_matches(self, count: int = 1, dataset_name: Optional[str] = None) -> None:
        """Increment external ontology match count."""
        self.current_metrics.external_ontology_matches += count
        if dataset_name and dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].external_ontology_matches += count
    
    def add_error(self, message: str, dataset_name: Optional[str] = None) -> None:
        """Add an error to the statistics."""
        self.current_metrics.errors += 1
        if dataset_name and dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].errors += 1
        logger.error(f"Execution error: {message}")
    
    def add_warning(self, message: str, dataset_name: Optional[str] = None) -> None:
        """Add a warning to the statistics."""
        self.current_metrics.warnings += 1
        if dataset_name and dataset_name in self.dataset_metrics:
            self.dataset_metrics[dataset_name].warnings += 1
        logger.warning(f"Execution warning: {message}")
    
    def merge_metrics(self, metrics: ExecutionMetrics) -> None:
        """Merge external metrics into current statistics."""
        self.current_metrics.merge(metrics)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all statistics."""
        summary = {
            'overall': self.current_metrics.to_dict(),
            'datasets': {
                name: metrics.to_dict() 
                for name, metrics in self.dataset_metrics.items()
            },
            'totals': {
                'total_datasets': len(self.dataset_metrics),
                'total_duration': self.current_metrics.duration_seconds(),
                'avg_dataset_duration': (
                    sum(m.duration_seconds() for m in self.dataset_metrics.values()) / 
                    len(self.dataset_metrics) if self.dataset_metrics else 0
                )
            }
        }
        return summary
    
    def log_final_summary(self) -> None:
        """Log a final summary of the execution."""
        summary = self.get_summary()
        overall = summary['overall']
        
        logger.info("=== EXECUTION SUMMARY ===")
        logger.info(f"Duration: {overall['duration_seconds']:.2f}s")
        logger.info(f"Datasets processed: {summary['totals']['total_datasets']}")
        logger.info(f"Rows: {overall['rows_processed']}, Cells: {overall['cells_processed']}")
        logger.info(f"Resources: {overall['resources_created']} created, {overall['resources_updated']} updated")
        logger.info(f"FK relationships: {overall['fk_relationships_created']}")
        logger.info(f"External ontology matches: {overall['external_ontology_matches']}")
        if overall['errors'] > 0:
            logger.warning(f"Errors: {overall['errors']}")
        if overall['warnings'] > 0:
            logger.info(f"Warnings: {overall['warnings']}")
        logger.info("========================") 