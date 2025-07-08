"""
Progress Tracker

Tracks progress for multi-dataset import operations.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ImportStatus(Enum):
    """Import status values"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetStatus(Enum):
    """Dataset processing status values"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DatasetProgress:
    """Progress information for a single dataset"""
    dataset_name: str
    status: DatasetStatus = DatasetStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    execution_time_seconds: float = 0.0
    
    # Processing metrics
    rows_processed: int = 0
    resources_created: int = 0
    triples_created: int = 0
    
    # Error information
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    def get_duration(self) -> float:
        """Get execution duration in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            return (datetime.now(timezone.utc) - self.start_time).total_seconds()
        else:
            return 0.0


@dataclass
class ProgressUpdate:
    """A progress update message"""
    mapping_id: int
    timestamp: datetime
    overall_status: ImportStatus
    current_dataset: Optional[str] = None
    datasets_completed: int = 0
    total_datasets: int = 0
    message: str = ""
    
    # Aggregated metrics
    total_rows_processed: int = 0
    total_resources_created: int = 0
    total_triples_created: int = 0
    
    def get_completion_percentage(self) -> float:
        """Get completion percentage (0-100)"""
        if self.total_datasets == 0:
            return 0.0
        return (self.datasets_completed / self.total_datasets) * 100.0


class ProgressTracker:
    """
    Tracks progress for multi-dataset import operations.
    
    Provides real-time progress updates, performance metrics,
    and status information for long-running imports.
    """
    
    def __init__(self):
        # Active imports: mapping_id -> import session
        self.active_imports: Dict[int, Dict[str, Any]] = {}
        
        # Progress history for completed imports
        self.import_history: Dict[int, Dict[str, Any]] = {}
        
        # Maximum history entries to keep
        self.max_history_entries = 100
    
    def start_import(self,
                    mapping_id: int,
                    total_datasets: int,
                    strategy: str,
                    **kwargs):
        """
        Start tracking a new import operation.
        
        Args:
            mapping_id: ID of the mapping being imported
            total_datasets: Total number of datasets to process
            strategy: Processing strategy being used
            **kwargs: Additional import parameters
        """
        now = datetime.now(timezone.utc)
        
        import_session = {
            'mapping_id': mapping_id,
            'status': ImportStatus.RUNNING,
            'strategy': strategy,
            'start_time': now,
            'end_time': None,
            'total_datasets': total_datasets,
            'datasets_completed': 0,
            'current_dataset': None,
            
            # Dataset tracking
            'dataset_progress': {},  # dataset_name -> DatasetProgress
            'dataset_order': [],     # Order of dataset processing
            
            # Aggregated metrics
            'total_rows_processed': 0,
            'total_resources_created': 0,
            'total_triples_created': 0,
            
            # Performance tracking
            'peak_memory_mb': 0.0,
            'progress_updates': [],
            
            # Error tracking
            'errors': [],
            'warnings': [],
            
            # Additional parameters
            **kwargs
        }
        
        self.active_imports[mapping_id] = import_session
        
        logger.info(f"Started tracking import for mapping {mapping_id}: "
                   f"{total_datasets} datasets, strategy: {strategy}")
        
        # Create initial progress update
        self._create_progress_update(mapping_id, "Import started")
    
    def start_dataset(self, mapping_id: int, dataset_name: str):
        """
        Mark a dataset as started.
        
        Args:
            mapping_id: ID of the mapping
            dataset_name: Name of the dataset being processed
        """
        if mapping_id not in self.active_imports:
            logger.warning(f"No active import found for mapping {mapping_id}")
            return
        
        session = self.active_imports[mapping_id]
        now = datetime.now(timezone.utc)
        
        # Create dataset progress entry
        dataset_progress = DatasetProgress(
            dataset_name=dataset_name,
            status=DatasetStatus.RUNNING,
            start_time=now
        )
        
        session['dataset_progress'][dataset_name] = dataset_progress
        session['current_dataset'] = dataset_name
        
        # Track processing order
        if dataset_name not in session['dataset_order']:
            session['dataset_order'].append(dataset_name)
        
        logger.info(f"Started processing dataset '{dataset_name}' for mapping {mapping_id}")
        
        # Create progress update
        self._create_progress_update(mapping_id, f"Started processing dataset: {dataset_name}")
    
    def complete_dataset(self,
                        mapping_id: int,
                        dataset_name: str,
                        success: bool = True,
                        error: Optional[str] = None,
                        **metrics):
        """
        Mark a dataset as completed.
        
        Args:
            mapping_id: ID of the mapping
            dataset_name: Name of the dataset
            success: Whether processing succeeded
            error: Error message if failed
            **metrics: Processing metrics (rows_processed, resources_created, etc.)
        """
        if mapping_id not in self.active_imports:
            logger.warning(f"No active import found for mapping {mapping_id}")
            return
        
        session = self.active_imports[mapping_id]
        
        if dataset_name not in session['dataset_progress']:
            logger.warning(f"Dataset '{dataset_name}' not found in progress tracking")
            return
        
        dataset_progress = session['dataset_progress'][dataset_name]
        dataset_progress.end_time = datetime.now(timezone.utc)
        dataset_progress.execution_time_seconds = dataset_progress.get_duration()
        
        if success:
            dataset_progress.status = DatasetStatus.COMPLETED
            session['datasets_completed'] += 1
            
            # Update metrics
            dataset_progress.rows_processed = metrics.get('rows_processed', 0)
            dataset_progress.resources_created = metrics.get('resources_created', 0)
            dataset_progress.triples_created = metrics.get('triples_created', 0)
            
            # Aggregate metrics
            session['total_rows_processed'] += dataset_progress.rows_processed
            session['total_resources_created'] += dataset_progress.resources_created
            session['total_triples_created'] += dataset_progress.triples_created
            
            logger.info(f"Completed dataset '{dataset_name}' for mapping {mapping_id}: "
                       f"{dataset_progress.resources_created} resources, "
                       f"{dataset_progress.triples_created} triples")
            
            message = f"Completed dataset: {dataset_name}"
        else:
            dataset_progress.status = DatasetStatus.FAILED
            dataset_progress.error_message = error
            session['errors'].append(f"Dataset {dataset_name}: {error}")
            
            logger.error(f"Failed to process dataset '{dataset_name}' for mapping {mapping_id}: {error}")
            
            message = f"Failed dataset: {dataset_name}"
        
        # Clear current dataset if this was the active one
        if session['current_dataset'] == dataset_name:
            session['current_dataset'] = None
        
        # Create progress update
        self._create_progress_update(mapping_id, message)
    
    def complete_import(self,
                       mapping_id: int,
                       success: bool = True,
                       error: Optional[str] = None):
        """
        Mark an import as completed.
        
        Args:
            mapping_id: ID of the mapping
            success: Whether import succeeded
            error: Error message if failed
        """
        if mapping_id not in self.active_imports:
            logger.warning(f"No active import found for mapping {mapping_id}")
            return
        
        session = self.active_imports[mapping_id]
        session['end_time'] = datetime.now(timezone.utc)
        
        if success:
            session['status'] = ImportStatus.COMPLETED
            message = "Import completed successfully"
        else:
            session['status'] = ImportStatus.FAILED
            if error:
                session['errors'].append(f"Import failed: {error}")
            message = f"Import failed: {error}" if error else "Import failed"
        
        # Calculate final execution time
        if session['start_time'] and session['end_time']:
            execution_time = (session['end_time'] - session['start_time']).total_seconds()
            session['execution_time_seconds'] = execution_time
        
        logger.info(f"Import {mapping_id} completed: {message} "
                   f"({session['datasets_completed']}/{session['total_datasets']} datasets)")
        
        # Create final progress update
        self._create_progress_update(mapping_id, message)
        
        # Move to history and clean up
        self._archive_import_session(mapping_id)
    
    def update_metrics(self,
                      mapping_id: int,
                      dataset_name: Optional[str] = None,
                      **metrics):
        """
        Update metrics for current processing.
        
        Args:
            mapping_id: ID of the mapping
            dataset_name: Name of the dataset (if dataset-specific)
            **metrics: Metrics to update
        """
        if mapping_id not in self.active_imports:
            return
        
        session = self.active_imports[mapping_id]
        
        # Update dataset-specific metrics
        if dataset_name and dataset_name in session['dataset_progress']:
            dataset_progress = session['dataset_progress'][dataset_name]
            
            for key, value in metrics.items():
                if hasattr(dataset_progress, key):
                    setattr(dataset_progress, key, value)
        
        # Update session-level metrics
        for key, value in metrics.items():
            if key.startswith('peak_') or key.startswith('total_'):
                session[key] = value
    
    def get_status(self, mapping_id: int) -> Optional[Dict[str, Any]]:
        """
        Get current status for an import.
        
        Args:
            mapping_id: ID of the mapping
            
        Returns:
            Status dictionary or None if not found
        """
        # Check active imports first
        if mapping_id in self.active_imports:
            session = self.active_imports[mapping_id]
            return self._format_session_status(session)
        
        # Check history
        if mapping_id in self.import_history:
            session = self.import_history[mapping_id]
            return self._format_session_status(session)
        
        return None
    
    def get_progress_updates(self, mapping_id: int, since: Optional[datetime] = None) -> List[ProgressUpdate]:
        """
        Get progress updates for an import.
        
        Args:
            mapping_id: ID of the mapping
            since: Only return updates after this timestamp
            
        Returns:
            List of progress updates
        """
        session = self.active_imports.get(mapping_id) or self.import_history.get(mapping_id)
        if not session:
            return []
        
        updates = session.get('progress_updates', [])
        
        if since:
            updates = [update for update in updates if update.timestamp > since]
        
        return updates
    
    def cancel_import(self, mapping_id: int, reason: str = "Cancelled by user"):
        """
        Cancel an active import.
        
        Args:
            mapping_id: ID of the mapping
            reason: Cancellation reason
        """
        if mapping_id not in self.active_imports:
            logger.warning(f"No active import found for mapping {mapping_id}")
            return
        
        session = self.active_imports[mapping_id]
        session['status'] = ImportStatus.CANCELLED
        session['end_time'] = datetime.now(timezone.utc)
        session['errors'].append(f"Import cancelled: {reason}")
        
        # Mark current dataset as cancelled if any
        current_dataset = session.get('current_dataset')
        if current_dataset and current_dataset in session['dataset_progress']:
            dataset_progress = session['dataset_progress'][current_dataset]
            dataset_progress.status = DatasetStatus.SKIPPED
            dataset_progress.end_time = datetime.now(timezone.utc)
        
        logger.info(f"Cancelled import {mapping_id}: {reason}")
        
        # Create cancellation update
        self._create_progress_update(mapping_id, f"Import cancelled: {reason}")
        
        # Archive the session
        self._archive_import_session(mapping_id)
    
    def _create_progress_update(self, mapping_id: int, message: str):
        """Create a progress update"""
        
        session = self.active_imports[mapping_id]
        
        update = ProgressUpdate(
            mapping_id=mapping_id,
            timestamp=datetime.now(timezone.utc),
            overall_status=session['status'],
            current_dataset=session.get('current_dataset'),
            datasets_completed=session['datasets_completed'],
            total_datasets=session['total_datasets'],
            message=message,
            total_rows_processed=session.get('total_rows_processed', 0),
            total_resources_created=session.get('total_resources_created', 0),
            total_triples_created=session.get('total_triples_created', 0)
        )
        
        session['progress_updates'].append(update)
        
        # Limit number of updates to prevent memory issues
        if len(session['progress_updates']) > 100:
            session['progress_updates'] = session['progress_updates'][-50:]
    
    def _format_session_status(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Format session data for external consumption"""
        
        # Calculate overall execution time
        start_time = session.get('start_time')
        end_time = session.get('end_time')
        
        if start_time and end_time:
            execution_time = (end_time - start_time).total_seconds()
        elif start_time:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        else:
            execution_time = 0.0
        
        # Format dataset progress
        dataset_progress = []
        for dataset_name in session.get('dataset_order', []):
            if dataset_name in session.get('dataset_progress', {}):
                progress = session['dataset_progress'][dataset_name]
                dataset_progress.append({
                    'dataset_name': progress.dataset_name,
                    'status': progress.status.value,
                    'execution_time_seconds': progress.get_duration(),
                    'rows_processed': progress.rows_processed,
                    'resources_created': progress.resources_created,
                    'triples_created': progress.triples_created,
                    'error_message': progress.error_message,
                    'warnings': progress.warnings
                })
        
        return {
            'mapping_id': session['mapping_id'],
            'status': session['status'].value,
            'strategy': session.get('strategy', 'unknown'),
            'start_time': start_time.isoformat() if start_time else None,
            'end_time': end_time.isoformat() if end_time else None,
            'execution_time_seconds': execution_time,
            'total_datasets': session['total_datasets'],
            'datasets_completed': session['datasets_completed'],
            'current_dataset': session.get('current_dataset'),
            'completion_percentage': (session['datasets_completed'] / session['total_datasets']) * 100 if session['total_datasets'] > 0 else 0,
            'total_rows_processed': session.get('total_rows_processed', 0),
            'total_resources_created': session.get('total_resources_created', 0),
            'total_triples_created': session.get('total_triples_created', 0),
            'peak_memory_mb': session.get('peak_memory_mb', 0),
            'dataset_progress': dataset_progress,
            'errors': session.get('errors', []),
            'warnings': session.get('warnings', [])
        }
    
    def _archive_import_session(self, mapping_id: int):
        """Move import session to history"""
        
        if mapping_id in self.active_imports:
            session = self.active_imports[mapping_id]
            
            # Move to history
            self.import_history[mapping_id] = session
            
            # Remove from active
            del self.active_imports[mapping_id]
            
            # Cleanup old history entries
            if len(self.import_history) > self.max_history_entries:
                # Keep most recent entries
                sorted_history = sorted(
                    self.import_history.items(),
                    key=lambda x: x[1].get('start_time', datetime.min.replace(tzinfo=timezone.utc)),
                    reverse=True
                )
                
                self.import_history = dict(sorted_history[:self.max_history_entries])
    
    def get_active_imports(self) -> List[Dict[str, Any]]:
        """Get list of currently active imports"""
        
        return [
            self._format_session_status(session)
            for session in self.active_imports.values()
        ]
    
    def cleanup_old_sessions(self, older_than_hours: int = 24):
        """
        Clean up old completed sessions.
        
        Args:
            older_than_hours: Remove sessions older than this many hours
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        
        # Clean up history
        to_remove = []
        for mapping_id, session in self.import_history.items():
            end_time = session.get('end_time')
            if end_time and end_time < cutoff_time:
                to_remove.append(mapping_id)
        
        for mapping_id in to_remove:
            del self.import_history[mapping_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old import sessions")