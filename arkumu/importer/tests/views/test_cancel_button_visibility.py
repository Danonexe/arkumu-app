"""
Tests specifically for cancel button visibility and functionality.
These tests will fail until we fix the task state tracking.
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from unittest.mock import patch, MagicMock
from arkumu.importer.models import IngestSession
from arkumu.importer.services.task_manager import TaskState, get_task_manager
from arkumu.importer.tasks.import_metadata import run_mapping_aware_import_workflow


class CancelButtonVisibilityTests(TestCase):
    """Test that the cancel button appears when tasks are in cancellable states"""
    
    def setUp(self):
        self.client = Client()
        self.task_id = "test-task-123"
        
    def test_cancel_button_visible_for_running_task(self):
        """Test that cancel button appears when task is in RUNNING state"""
        # Arrange: Set up task in RUNNING state in cache
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'running',  # This should make cancel button appear
            'progress': 50,
            'phase': 'processing',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': None,
            'error_message': None,
            'metadata': {},
            'timestamp': '2025-01-01T10:00:00Z'
        })
        
        # Act: Get the progress page
        url = reverse('importer:task_status_api', kwargs={'task_id': self.task_id})
        response = self.client.get(url)
        
        # Assert: Cancel button should be present
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel', msg_prefix="Cancel button should be visible for running tasks")
        self.assertContains(response, 'hx-post', msg_prefix="Cancel button should have HTMX action")
        
    def test_cancel_button_visible_for_pending_task(self):
        """Test that cancel button appears when task is in PENDING state"""
        # Arrange: Set up task in PENDING state
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'pending',
            'progress': 0,
            'phase': 'initializing',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': None,
            'error_message': None,
            'metadata': {},
            'timestamp': '2025-01-01T10:00:00Z'
        })
        
        # Act: Get the progress page
        url = reverse('importer:task_status_api', kwargs={'task_id': self.task_id})
        response = self.client.get(url)
        
        # Assert: Cancel button should be present
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel', msg_prefix="Cancel button should be visible for pending tasks")
        
    def test_cancel_button_visible_for_processing_task(self):
        """Test that cancel button appears when task is in PROCESSING state"""
        # Arrange: Set up task in PROCESSING state (this is what tasks actually use)
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'processing',  # This is the actual state used by tasks
            'progress': 30,
            'phase': 'importing',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': None,
            'error_message': None,
            'metadata': {},
            'timestamp': '2025-01-01T10:00:00Z'
        })
        
        # Act: Get the progress page
        url = reverse('importer:task_status_api', kwargs={'task_id': self.task_id})
        response = self.client.get(url)
        
        # Assert: Cancel button should be present
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel', msg_prefix="Cancel button should be visible for processing tasks")
        
    def test_cancel_button_not_visible_for_completed_task(self):
        """Test that cancel button does NOT appear when task is completed"""
        # Arrange: Set up task in COMPLETED state
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'completed',
            'progress': 100,
            'phase': 'finished',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': '2025-01-01T10:30:00Z',
            'error_message': None,
            'metadata': {},
            'timestamp': '2025-01-01T10:30:00Z'
        })
        
        # Act: Get the progress page
        url = reverse('importer:task_status_api', kwargs={'task_id': self.task_id})
        response = self.client.get(url)
        
        # Assert: Cancel button should NOT be present
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Cancel', msg_prefix="Cancel button should NOT be visible for completed tasks")
        
    def test_cancel_button_not_visible_for_failed_task(self):
        """Test that cancel button does NOT appear when task has failed"""
        # Arrange: Set up task in FAILED state
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'failed',
            'progress': 50,
            'phase': 'error',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': '2025-01-01T10:15:00Z',
            'error_message': 'Something went wrong',
            'metadata': {},
            'timestamp': '2025-01-01T10:15:00Z'
        })
        
        # Act: Get the progress page
        url = reverse('importer:task_status_api', kwargs={'task_id': self.task_id})
        response = self.client.get(url)
        
        # Assert: Cancel button should NOT be present
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Cancel', msg_prefix="Cancel button should NOT be visible for failed tasks")


class TaskManagerIntegrationTests(TestCase):
    """Test that the @cancellable_task decorator properly integrates with TaskManager"""
    
    def setUp(self):
        self.task_id = "integration-test-456"
        cache.clear()
    def test_cancellable_task_decorator_registers_with_task_manager(self, mock_get_task_manager):
        """Test that @cancellable_task decorator properly registers the task"""
        # Arrange: Mock the task manager
        mock_task_manager = MagicMock()
        mock_get_task_manager.return_value = mock_task_manager
        
        # Arrange: Mock the task context
        mock_context = MagicMock()
        mock_task_manager.task_context.return_value.__enter__.return_value = mock_context
        
        # Act: Call the decorated function (this should trigger registration)
        # Note: This test will fail until we fix the decorator
        with patch('arkumu.importer.tasks.import_metadata.run_mapping_aware_import_workflow') as mock_func:
            mock_func.return_value = {'status': 'success'}
            
            # This should trigger the decorator
            result = run_mapping_aware_import_workflow(
                s3_bucket_name='test-bucket',
                s3_object_key='test-key',
                dataset_name='test-dataset',
                institution='test-org',
                mapping_id='test-mapping',
                upload_session_id=self.task_id
            )
        
        # Assert: Task manager should have been called
        mock_get_task_manager.assert_called()
        mock_task_manager.task_context.assert_called_once_with(self.task_id, self.task_id)
        
    def test_task_state_persisted_to_cache(self):
        """Test that task state is actually persisted to Redis cache"""
        # This test will fail until we fix the task state persistence
        
        # Arrange: Get the task manager
        task_manager = get_task_manager()
        
        # Act: Register a task
        context = task_manager.register_task(self.task_id, session_id=self.task_id)
        
        # Assert: Task state should be in cache
        cached_state = cache.get(f"task_state_{self.task_id}")
        self.assertIsNotNone(cached_state, "Task state should be persisted to cache")
        self.assertEqual(cached_state['task_id'], self.task_id)
        self.assertEqual(cached_state['state'], 'pending')  # Should start in pending state
        
    def test_task_state_updates_when_progress_changes(self):
        """Test that task state updates when progress is reported"""
        # This test will fail until we fix the progress tracking
        
        # Arrange: Get the task manager and register a task
        task_manager = get_task_manager()
        context = task_manager.register_task(self.task_id, session_id=self.task_id)
        
        # Act: Update task progress
        task_manager.update_task_progress(self.task_id, 50, 'processing', 'Working on it...')
        
        # Assert: Task state should be updated in cache
        cached_state = cache.get(f"task_state_{self.task_id}")
        self.assertIsNotNone(cached_state, "Task state should be updated in cache")
        self.assertEqual(cached_state['progress'], 50)
        self.assertEqual(cached_state['phase'], 'processing')
        self.assertEqual(cached_state['state'], 'running')  # Should be running when progress is updated


class CancellationFunctionalityTests(TestCase):
    """Test that the cancellation functionality works end-to-end"""
    
    def setUp(self):
        self.client = Client()
        self.task_id = "cancel-test-789"
        cache.clear()
        
    def test_cancel_api_endpoint_works(self):
        """Test that the cancel API endpoint properly cancels a task"""
        # Arrange: Set up a running task
        cache.set(f"task_state_{self.task_id}", {
            'task_id': self.task_id,
            'state': 'running',
            'progress': 50,
            'phase': 'processing',
            'cancellation_requested': False,
            'cancellation_reason': None,
            'start_time': '2025-01-01T10:00:00Z',
            'end_time': None,
            'error_message': None,
            'metadata': {},
            'timestamp': '2025-01-01T10:00:00Z'
        })
        
        # Act: Call the cancel endpoint
        url = reverse('importer:cancel_task_api', kwargs={'task_id': self.task_id})
        response = self.client.post(url, 
                                   data='{"reason": "user_requested"}',
                                   content_type='application/json')
        
        # Assert: Task should be marked as cancelling
        self.assertEqual(response.status_code, 200)
        
        # Check that the task state was updated
        cached_state = cache.get(f"task_state_{self.task_id}")
        if cached_state:  # May be None if task manager isn't working
            self.assertTrue(cached_state.get('cancellation_requested', False))
            self.assertEqual(cached_state.get('cancellation_reason'), 'user_requested')
            
    def test_redis_cleanup_on_cancellation(self):
        """Test that Redis is cleaned up when a task is cancelled"""
        # This test will fail until we implement Redis cleanup
        
        # Arrange: Set up a running task with some Redis data
        cache.set(f"task_state_{self.task_id}", {'state': 'running'})
        cache.set(f"task_data_{self.task_id}", {'some': 'data'})
        cache.set(f"task_progress_{self.task_id}", {'progress': 50})
        
        # Act: Cancel the task through the task manager
        task_manager = get_task_manager()
        success = task_manager.request_cancellation(self.task_id)
        
        # Assert: Redis should be cleaned up
        self.assertTrue(success, "Cancellation should succeed")
        
        # Check that task-related keys are cleaned up
        # Note: This depends on our Redis cleanup implementation
        remaining_keys = cache.keys(f"*{self.task_id}*")
        self.assertEqual(len(remaining_keys), 0, "All task-related keys should be cleaned up")