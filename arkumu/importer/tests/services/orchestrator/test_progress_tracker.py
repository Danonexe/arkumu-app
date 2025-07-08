"""
Tests for ProgressTracker.

Comprehensive tests for progress tracking functionality during
multi-dataset import operations with real-time updates and status management.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from arkumu.importer.services.orchestrator.progress_tracker import (
    ProgressTracker, ProgressUpdate, DatasetProgress, 
    ImportStatus, DatasetStatus
)


class TestProgressTracker:
    """Test suite for ProgressTracker class"""

    def test_init_default_values(self, progress_tracker):
        """Test ProgressTracker initialization with default values"""
        assert progress_tracker.active_imports == {}
        assert progress_tracker.import_history == {}
        assert progress_tracker.max_history_entries == 100

    def test_start_import_creates_session(self, progress_tracker):
        """Test starting import creates proper session"""
        progress_tracker.start_import(
            mapping_id=1,
            total_datasets=3,
            strategy='entity_centric',
            custom_param='test_value'
        )
        
        assert 1 in progress_tracker.active_imports
        session = progress_tracker.active_imports[1]
        
        assert session['mapping_id'] == 1
        assert session['status'] == ImportStatus.RUNNING
        assert session['strategy'] == 'entity_centric'
        assert session['total_datasets'] == 3
        assert session['datasets_completed'] == 0
        assert session['current_dataset'] is None
        assert session['custom_param'] == 'test_value'
        assert 'start_time' in session
        assert session['end_time'] is None
        assert len(session['progress_updates']) == 1  # Initial update

    def test_start_dataset_tracking(self, progress_tracker):
        """Test starting dataset tracking"""
        # Start import first
        progress_tracker.start_import(
            mapping_id=1,
            total_datasets=2,
            strategy='entity_centric'
        )
        
        # Start dataset
        progress_tracker.start_dataset(1, 'test_dataset')
        
        session = progress_tracker.active_imports[1]
        assert session['current_dataset'] == 'test_dataset'
        assert 'test_dataset' in session['dataset_progress']
        assert 'test_dataset' in session['dataset_order']
        
        dataset_progress = session['dataset_progress']['test_dataset']
        assert isinstance(dataset_progress, DatasetProgress)
        assert dataset_progress.dataset_name == 'test_dataset'
        assert dataset_progress.status == DatasetStatus.RUNNING
        assert dataset_progress.start_time is not None
        assert dataset_progress.end_time is None

    def test_start_dataset_no_active_import(self, progress_tracker):
        """Test starting dataset when no active import exists"""
        # Should handle gracefully
        progress_tracker.start_dataset(999, 'test_dataset')
        
        # No session should be created
        assert 999 not in progress_tracker.active_imports

    def test_complete_dataset_success(self, progress_tracker):
        """Test completing dataset successfully"""
        # Setup
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'test_dataset')
        
        # Complete dataset
        progress_tracker.complete_dataset(
            mapping_id=1,
            dataset_name='test_dataset',
            success=True,
            rows_processed=100,
            resources_created=200,
            triples_created=800
        )
        
        session = progress_tracker.active_imports[1]
        dataset_progress = session['dataset_progress']['test_dataset']
        
        assert dataset_progress.status == DatasetStatus.COMPLETED
        assert dataset_progress.end_time is not None
        assert dataset_progress.rows_processed == 100
        assert dataset_progress.resources_created == 200
        assert dataset_progress.triples_created == 800
        assert dataset_progress.execution_time_seconds > 0
        
        # Check aggregated metrics
        assert session['datasets_completed'] == 1
        assert session['total_rows_processed'] == 100
        assert session['total_resources_created'] == 200
        assert session['total_triples_created'] == 800
        assert session['current_dataset'] is None

    def test_complete_dataset_failure(self, progress_tracker):
        """Test completing dataset with failure"""
        # Setup
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'test_dataset')
        
        # Complete dataset with failure
        progress_tracker.complete_dataset(
            mapping_id=1,
            dataset_name='test_dataset',
            success=False,
            error='Processing failed'
        )
        
        session = progress_tracker.active_imports[1]
        dataset_progress = session['dataset_progress']['test_dataset']
        
        assert dataset_progress.status == DatasetStatus.FAILED
        assert dataset_progress.error_message == 'Processing failed'
        assert session['datasets_completed'] == 0  # No increment on failure
        assert len(session['errors']) == 1
        assert 'Processing failed' in session['errors'][0]

    def test_complete_dataset_nonexistent(self, progress_tracker):
        """Test completing nonexistent dataset"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        
        # Try to complete dataset that was never started
        progress_tracker.complete_dataset(
            mapping_id=1,
            dataset_name='nonexistent_dataset',
            success=True
        )
        
        # Should handle gracefully without errors
        session = progress_tracker.active_imports[1]
        assert 'nonexistent_dataset' not in session['dataset_progress']

    def test_complete_import_success(self, progress_tracker):
        """Test completing import successfully"""
        # Setup with completed datasets
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'dataset1')
        progress_tracker.complete_dataset(1, 'dataset1', success=True)
        progress_tracker.start_dataset(1, 'dataset2')
        progress_tracker.complete_dataset(1, 'dataset2', success=True)
        
        # Complete import
        progress_tracker.complete_import(mapping_id=1, success=True)
        
        # Import should be moved to history
        assert 1 not in progress_tracker.active_imports
        assert 1 in progress_tracker.import_history
        
        session = progress_tracker.import_history[1]
        assert session['status'] == ImportStatus.COMPLETED
        assert session['end_time'] is not None
        assert 'execution_time_seconds' in session

    def test_complete_import_failure(self, progress_tracker):
        """Test completing import with failure"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        
        # Complete import with failure
        progress_tracker.complete_import(
            mapping_id=1, 
            success=False, 
            error='Import failed due to system error'
        )
        
        session = progress_tracker.import_history[1]
        assert session['status'] == ImportStatus.FAILED
        assert 'Import failed: Import failed due to system error' in session['errors']

    def test_update_metrics_dataset_specific(self, progress_tracker):
        """Test updating dataset-specific metrics"""
        # Setup
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'test_dataset')
        
        # Update metrics
        progress_tracker.update_metrics(
            mapping_id=1,
            dataset_name='test_dataset',
            rows_processed=50,
            resources_created=100
        )
        
        dataset_progress = progress_tracker.active_imports[1]['dataset_progress']['test_dataset']
        assert dataset_progress.rows_processed == 50
        assert dataset_progress.resources_created == 100

    def test_update_metrics_session_level(self, progress_tracker):
        """Test updating session-level metrics"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        
        # Update session metrics
        progress_tracker.update_metrics(
            mapping_id=1,
            peak_memory_mb=150.5,
            total_rows_processed=1000
        )
        
        session = progress_tracker.active_imports[1]
        assert session['peak_memory_mb'] == 150.5
        assert session['total_rows_processed'] == 1000

    def test_get_status_active_import(self, progress_tracker):
        """Test getting status for active import"""
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'dataset1')
        progress_tracker.complete_dataset(1, 'dataset1', success=True, rows_processed=100)
        
        status = progress_tracker.get_status(1)
        
        assert status is not None
        assert status['mapping_id'] == 1
        assert status['status'] == ImportStatus.RUNNING.value
        assert status['strategy'] == 'entity_centric'
        assert status['total_datasets'] == 2
        assert status['datasets_completed'] == 1
        assert status['completion_percentage'] == 50.0
        assert len(status['dataset_progress']) == 1

    def test_get_status_from_history(self, progress_tracker):
        """Test getting status from import history"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        progress_tracker.complete_import(mapping_id=1, success=True)
        
        status = progress_tracker.get_status(1)
        
        assert status is not None
        assert status['status'] == ImportStatus.COMPLETED.value

    def test_get_status_nonexistent(self, progress_tracker):
        """Test getting status for nonexistent import"""
        status = progress_tracker.get_status(999)
        assert status is None

    def test_get_progress_updates(self, progress_tracker):
        """Test getting progress updates"""
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'dataset1')
        progress_tracker.complete_dataset(1, 'dataset1', success=True)
        
        updates = progress_tracker.get_progress_updates(1)
        
        assert len(updates) >= 3  # Start import, start dataset, complete dataset
        assert all(isinstance(update, ProgressUpdate) for update in updates)
        assert all(update.mapping_id == 1 for update in updates)

    def test_get_progress_updates_with_since_filter(self, progress_tracker):
        """Test getting progress updates with timestamp filter"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        
        # Record timestamp
        since_time = datetime.now(timezone.utc)
        
        # Add more updates
        progress_tracker.start_dataset(1, 'dataset1')
        progress_tracker.complete_dataset(1, 'dataset1', success=True)
        
        # Get updates since timestamp
        updates = progress_tracker.get_progress_updates(1, since=since_time)
        
        # Should only get updates after the timestamp
        assert len(updates) >= 2
        assert all(update.timestamp > since_time for update in updates)

    def test_cancel_import(self, progress_tracker):
        """Test canceling an active import"""
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'dataset1')
        
        # Cancel import
        progress_tracker.cancel_import(1, reason='User requested cancellation')
        
        # Should be moved to history with cancelled status
        assert 1 not in progress_tracker.active_imports
        assert 1 in progress_tracker.import_history
        
        session = progress_tracker.import_history[1]
        assert session['status'] == ImportStatus.CANCELLED
        assert 'User requested cancellation' in session['errors'][0]
        
        # Current dataset should be marked as skipped
        dataset_progress = session['dataset_progress']['dataset1']
        assert dataset_progress.status == DatasetStatus.SKIPPED

    def test_cancel_nonexistent_import(self, progress_tracker):
        """Test canceling nonexistent import"""
        # Should handle gracefully
        progress_tracker.cancel_import(999, reason='Test')
        
        assert 999 not in progress_tracker.active_imports
        assert 999 not in progress_tracker.import_history

    def test_get_active_imports(self, progress_tracker):
        """Test getting list of active imports"""
        # Start multiple imports
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        progress_tracker.start_import(mapping_id=2, total_datasets=2, strategy='streaming_entity_centric')
        
        active_imports = progress_tracker.get_active_imports()
        
        assert len(active_imports) == 2
        mapping_ids = [imp['mapping_id'] for imp in active_imports]
        assert 1 in mapping_ids
        assert 2 in mapping_ids

    def test_cleanup_old_sessions(self, progress_tracker):
        """Test cleaning up old completed sessions"""
        from datetime import timedelta
        
        # Create old session in history
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)  # 25 hours ago
        
        old_session = {
            'mapping_id': 1,
            'status': ImportStatus.COMPLETED,
            'end_time': old_time
        }
        progress_tracker.import_history[1] = old_session
        
        # Create recent session
        recent_time = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago
        recent_session = {
            'mapping_id': 2,
            'status': ImportStatus.COMPLETED,
            'end_time': recent_time
        }
        progress_tracker.import_history[2] = recent_session
        
        # Cleanup sessions older than 24 hours
        progress_tracker.cleanup_old_sessions(older_than_hours=24)
        
        # Old session should be removed, recent should remain
        assert 1 not in progress_tracker.import_history
        assert 2 in progress_tracker.import_history

    def test_archive_import_session_max_history(self, progress_tracker):
        """Test archiving respects max history entries"""
        # Set small max history for testing
        progress_tracker.max_history_entries = 2
        
        # Create multiple completed imports
        for i in range(4):
            progress_tracker.start_import(mapping_id=i, total_datasets=1, strategy='entity_centric')
            progress_tracker.complete_import(mapping_id=i, success=True)
        
        # Should only keep most recent entries
        assert len(progress_tracker.import_history) == 2
        # Should keep the most recent ones (2 and 3)
        assert 2 in progress_tracker.import_history
        assert 3 in progress_tracker.import_history

    def test_progress_update_creation(self, progress_tracker):
        """Test progress update creation and content"""
        progress_tracker.start_import(mapping_id=1, total_datasets=3, strategy='entity_centric')
        progress_tracker.start_dataset(1, 'dataset1')
        progress_tracker.complete_dataset(1, 'dataset1', success=True, rows_processed=100)
        
        session = progress_tracker.active_imports[1]
        updates = session['progress_updates']
        
        # Should have at least 3 updates
        assert len(updates) >= 3
        
        # Check last update (dataset completion)
        last_update = updates[-1]
        assert last_update.mapping_id == 1
        assert last_update.overall_status == ImportStatus.RUNNING
        assert last_update.datasets_completed == 1
        assert last_update.total_datasets == 3
        assert last_update.get_completion_percentage() == (1/3) * 100

    def test_progress_update_limit(self, progress_tracker):
        """Test progress updates are limited to prevent memory issues"""
        progress_tracker.start_import(mapping_id=1, total_datasets=1, strategy='entity_centric')
        
        # Create many updates to trigger trimming
        # After 1 initial + 100 manual updates = 101 > 100, trim to 50
        # Then add 20 more updates = 50 + 20 = 70 final
        for i in range(120):
            progress_tracker._create_progress_update(1, f"Update {i}")
        
        session = progress_tracker.active_imports[1]
        updates = session['progress_updates']
        
        # Should be limited when exceeding 100, resulting in 70 total
        assert len(updates) == 70


class TestDatasetProgress:
    """Test suite for DatasetProgress class"""

    def test_dataset_progress_initialization(self):
        """Test DatasetProgress initialization"""
        progress = DatasetProgress(dataset_name='test_dataset')
        
        assert progress.dataset_name == 'test_dataset'
        assert progress.status == DatasetStatus.PENDING
        assert progress.start_time is None
        assert progress.end_time is None
        assert progress.execution_time_seconds == 0.0
        assert progress.rows_processed == 0
        assert progress.resources_created == 0
        assert progress.triples_created == 0
        assert progress.error_message is None
        assert progress.warnings == []

    def test_get_duration_both_times(self):
        """Test get_duration with both start and end times"""
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=30)
        
        progress = DatasetProgress(
            dataset_name='test',
            start_time=start_time,
            end_time=end_time
        )
        
        duration = progress.get_duration()
        assert abs(duration - 30.0) < 0.1  # Allow small floating point variance

    def test_get_duration_only_start_time(self):
        """Test get_duration with only start time"""
        start_time = datetime.now(timezone.utc) - timedelta(seconds=15)
        
        progress = DatasetProgress(
            dataset_name='test',
            start_time=start_time
        )
        
        duration = progress.get_duration()
        assert duration >= 14.0  # Should be around 15 seconds

    def test_get_duration_no_times(self):
        """Test get_duration with no times set"""
        progress = DatasetProgress(dataset_name='test')
        
        duration = progress.get_duration()
        assert duration == 0.0


class TestProgressUpdate:
    """Test suite for ProgressUpdate class"""

    def test_progress_update_initialization(self):
        """Test ProgressUpdate initialization"""
        timestamp = datetime.now(timezone.utc)
        
        update = ProgressUpdate(
            mapping_id=1,
            timestamp=timestamp,
            overall_status=ImportStatus.RUNNING,
            current_dataset='test_dataset',
            datasets_completed=2,
            total_datasets=5,
            message='Processing dataset',
            total_rows_processed=1000,
            total_resources_created=2000,
            total_triples_created=8000
        )
        
        assert update.mapping_id == 1
        assert update.timestamp == timestamp
        assert update.overall_status == ImportStatus.RUNNING
        assert update.current_dataset == 'test_dataset'
        assert update.datasets_completed == 2
        assert update.total_datasets == 5
        assert update.message == 'Processing dataset'
        assert update.total_rows_processed == 1000
        assert update.total_resources_created == 2000
        assert update.total_triples_created == 8000

    def test_get_completion_percentage(self):
        """Test completion percentage calculation"""
        update = ProgressUpdate(
            mapping_id=1,
            timestamp=datetime.now(timezone.utc),
            overall_status=ImportStatus.RUNNING,
            datasets_completed=3,
            total_datasets=4
        )
        
        percentage = update.get_completion_percentage()
        assert percentage == 75.0

    def test_get_completion_percentage_zero_total(self):
        """Test completion percentage with zero total datasets"""
        update = ProgressUpdate(
            mapping_id=1,
            timestamp=datetime.now(timezone.utc),
            overall_status=ImportStatus.RUNNING,
            datasets_completed=0,
            total_datasets=0
        )
        
        percentage = update.get_completion_percentage()
        assert percentage == 0.0


class TestImportStatus:
    """Test suite for ImportStatus enum"""

    def test_import_status_values(self):
        """Test ImportStatus enum values"""
        assert ImportStatus.PENDING.value == "pending"
        assert ImportStatus.RUNNING.value == "running"
        assert ImportStatus.COMPLETED.value == "completed"
        assert ImportStatus.FAILED.value == "failed"
        assert ImportStatus.CANCELLED.value == "cancelled"


class TestDatasetStatus:
    """Test suite for DatasetStatus enum"""

    def test_dataset_status_values(self):
        """Test DatasetStatus enum values"""
        assert DatasetStatus.PENDING.value == "pending"
        assert DatasetStatus.RUNNING.value == "running"
        assert DatasetStatus.COMPLETED.value == "completed"
        assert DatasetStatus.FAILED.value == "failed"
        assert DatasetStatus.SKIPPED.value == "skipped"


class TestProgressTrackerIntegration:
    """Integration tests for ProgressTracker"""

    def test_complete_import_workflow(self, progress_tracker):
        """Test complete import workflow from start to finish"""
        # Start import
        progress_tracker.start_import(
            mapping_id=1,
            total_datasets=3,
            strategy='multi_phase',
            chunk_size=1000
        )
        
        # Process first dataset
        progress_tracker.start_dataset(1, 'dataset_a')
        progress_tracker.update_metrics(1, dataset_name='dataset_a', rows_processed=50)
        progress_tracker.complete_dataset(
            1, 'dataset_a', success=True,
            rows_processed=100, resources_created=200, triples_created=800
        )
        
        # Process second dataset
        progress_tracker.start_dataset(1, 'dataset_b')
        progress_tracker.complete_dataset(
            1, 'dataset_b', success=True,
            rows_processed=150, resources_created=300, triples_created=1200
        )
        
        # Process third dataset with failure
        progress_tracker.start_dataset(1, 'dataset_c')
        progress_tracker.complete_dataset(
            1, 'dataset_c', success=False,
            error='Processing error occurred'
        )
        
        # Complete import
        progress_tracker.complete_import(1, success=False, error='Partial failure')
        
        # Verify final state
        assert 1 not in progress_tracker.active_imports
        assert 1 in progress_tracker.import_history
        
        final_status = progress_tracker.get_status(1)
        assert final_status['status'] == ImportStatus.FAILED.value
        assert final_status['datasets_completed'] == 2
        assert final_status['total_rows_processed'] == 250
        assert final_status['total_resources_created'] == 500
        assert final_status['total_triples_created'] == 2000
        assert len(final_status['errors']) >= 2  # Dataset error + import error

    def test_multiple_concurrent_imports(self, progress_tracker):
        """Test handling multiple concurrent imports"""
        # Start multiple imports
        progress_tracker.start_import(mapping_id=1, total_datasets=2, strategy='entity_centric')
        progress_tracker.start_import(mapping_id=2, total_datasets=1, strategy='streaming_entity_centric')
        progress_tracker.start_import(mapping_id=3, total_datasets=3, strategy='multi_phase')
        
        # Process datasets in different imports
        progress_tracker.start_dataset(1, 'dataset_1a')
        progress_tracker.start_dataset(2, 'dataset_2a')
        progress_tracker.start_dataset(3, 'dataset_3a')
        
        progress_tracker.complete_dataset(1, 'dataset_1a', success=True)
        progress_tracker.complete_dataset(2, 'dataset_2a', success=True)
        progress_tracker.complete_dataset(3, 'dataset_3a', success=True)
        
        # Verify all are tracking correctly
        active_imports = progress_tracker.get_active_imports()
        assert len(active_imports) == 3
        
        # Complete one import
        progress_tracker.complete_import(2, success=True)
        
        # Verify state
        assert 2 not in progress_tracker.active_imports
        assert 2 in progress_tracker.import_history
        assert len(progress_tracker.get_active_imports()) == 2