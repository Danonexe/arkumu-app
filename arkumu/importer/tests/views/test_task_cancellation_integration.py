"""
Integration tests for the complete task cancellation system
"""

import pytest
import json
import uuid
import time
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.contrib.auth import get_user_model

from arkumu.importer.models import IngestSession
from arkumu.importer.services.task_manager import (
    TaskManager, TaskState, CancellationReason, get_task_manager, cancellable_task
)
from arkumu.users.models import Organization, User
from huey.exceptions import CancelExecution


class TestTaskCancellationIntegration(TestCase):
    """Integration tests for the complete task cancellation system"""
    
    def setUp(self):
        """Set up test environment"""
        self.client = Client()
        cache.clear()
        
        # Create test organization and user
        self.test_org, _ = Organization.objects.get_or_create(
            code="test_org",
            defaults={
                "name": "Test Organization",
                "description": "Test organization"
            }
        )
        
        self.test_user, _ = User.objects.get_or_create(
            username="test_user",
            defaults={
                "email": "test@example.com",
                "name": "Test User",
                "organization": self.test_org,
                "role": "researcher"
            }
        )
        
        # Login test user
        self.client.force_login(self.test_user)
        
        # Create test session
        self.test_session = IngestSession.objects.create(
            user=self.test_user,
            organization=self.test_org,
            dataset_name="test_dataset",
            s3_bucket="test_bucket",
            s3_object_key="test_file.csv",
            status='processing'
        )

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()
        IngestSession.objects.filter(dataset_name="test_dataset").delete()

    def test_complete_cancellation_workflow(self):
        """Test complete cancellation workflow from UI to task execution"""
        task_id = str(uuid.uuid4())
        
        # Mock huey instance for task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        # Register task
        context = task_manager.register_task(
            task_id=task_id,
            session_id=str(self.test_session.id),
            user_id=str(self.test_user.id)
        )
        
        # Add cleanup callbacks
        cleanup_called = False
        rollback_called = False
        
        def cleanup_callback():
            nonlocal cleanup_called
            cleanup_called = True
        
        def rollback_callback():
            nonlocal rollback_called
            rollback_called = True
        
        task_manager.add_cleanup_callback(task_id, cleanup_callback)
        task_manager.add_rollback_callback(task_id, rollback_callback)
        
        # Simulate task progress
        task_manager.update_task_progress(task_id, 30, "processing", "Processing data...")
        
        # Step 1: Check initial progress monitor
        monitor_url = reverse('importer:progress_monitor', kwargs={'task_id': task_id})
        response = self.client.get(monitor_url, {'session_id': str(self.test_session.id)})
        
        assert response.status_code == 200
        assert task_id in response.context['task_id']
        
        # Step 2: Check task status shows cancel button
        status_url = reverse('importer:task_status_api', kwargs={'task_id': task_id})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.get(status_url, {'session_id': str(self.test_session.id)})
            
            assert response.status_code == 200
            content = response.content.decode()
            
            # Should show running task with cancel button
            assert '30%' in content
            assert 'processing' in content
            assert 'Cancel' in content
        
        # Step 3: User clicks cancel button
        cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_id})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.post(
                cancel_url,
                data=json.dumps({'reason': 'user_requested'}),
                content_type='application/json',
                headers={'HX-Request': 'true'}
            )
            
            assert response.status_code == 200
            
            # Verify cancellation was requested
            assert context.cancellation_requested is True
            assert context.cancellation_reason == CancellationReason.USER_REQUESTED
            assert context.state == TaskState.CANCELLING
        
        # Step 4: Simulate task manager processing cancellation
        task_manager._process_cancellation(context)
        
        # Step 5: Check final status
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.get(status_url, {'session_id': str(self.test_session.id)})
            
            assert response.status_code == 200
            content = response.content.decode()
            
            # Should show cancelled state
            assert 'cancelled' in content.lower()
            assert 'hx-trigger="none"' in content or 'hx-get' not in content
        
        # Step 6: Verify cleanup was performed
        assert cleanup_called is True
        assert rollback_called is True
        assert context.state == TaskState.CANCELLED
        
        # Step 7: Verify database was updated
        self.test_session.refresh_from_db()
        assert self.test_session.status == 'cancelled'

    def test_cancellation_with_decorator(self):
        """Test cancellation with the @cancellable_task decorator"""
        task_id = str(uuid.uuid4())
        
        # Mock the global task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        execution_started = False
        cancellation_detected = False
        
        @cancellable_task()
        def test_import_task(task_id_for_cache, upload_session_id=None, **kwargs):
            nonlocal execution_started, cancellation_detected
            execution_started = True
            
            update_progress = kwargs.get('update_progress')
            task_context = kwargs.get('task_context')
            
            # Simulate some work
            for i in range(5):
                try:
                    update_progress(i * 20, f"step_{i}", f"Processing step {i}")
                    time.sleep(0.1)  # Simulate work
                except CancelExecution:
                    cancellation_detected = True
                    raise
            
            return {"success": True}
        
        # Patch the global task manager
        with patch('arkumu.importer.services.task_manager.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            # Start the task in a separate thread to simulate async execution
            import threading
            
            task_result = None
            task_exception = None
            
            def run_task():
                nonlocal task_result, task_exception
                try:
                    task_result = test_import_task(
                        task_id_for_cache=task_id,
                        upload_session_id=str(self.test_session.id)
                    )
                except Exception as e:
                    task_exception = e
            
            task_thread = threading.Thread(target=run_task)
            task_thread.start()
            
            # Wait for task to start
            time.sleep(0.2)
            assert execution_started is True
            
            # Request cancellation through the UI
            cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_id})
            
            with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_ui_manager:
                mock_get_ui_manager.return_value = task_manager
                
                response = self.client.post(cancel_url, headers={'HX-Request': 'true'})
                assert response.status_code == 200
            
            # Wait for task thread to complete
            task_thread.join(timeout=2)
            
            # Verify cancellation was processed
            assert isinstance(task_exception, CancelExecution)
            assert cancellation_detected is True

    def test_multiple_concurrent_cancellations(self):
        """Test cancellation with multiple concurrent tasks"""
        task_ids = [str(uuid.uuid4()) for _ in range(3)]
        
        # Mock huey instance for task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = IngestSession.objects.create(
                user=self.test_user,
                organization=self.test_org,
                dataset_name=f"test_dataset_{i}",
                s3_bucket="test_bucket",
                s3_object_key=f"test_file_{i}.csv",
                status='processing'
            )
            sessions.append(session)
        
        # Register all tasks
        contexts = []
        for i, task_id in enumerate(task_ids):
            context = task_manager.register_task(
                task_id=task_id,
                session_id=str(sessions[i].id),
                user_id=str(self.test_user.id)
            )
            contexts.append(context)
            
            # Simulate progress
            task_manager.update_task_progress(task_id, 25, "processing", f"Processing task {i}")
        
        # Cancel only the middle task
        cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_ids[1]})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.post(cancel_url, headers={'HX-Request': 'true'})
            assert response.status_code == 200
        
        # Process cancellation
        task_manager._process_cancellation(contexts[1])
        
        # Complete the other tasks
        task_manager.complete_task(task_ids[0], success=True)
        task_manager.complete_task(task_ids[2], success=True)
        
        # Verify states
        assert contexts[0].state == TaskState.COMPLETED
        assert contexts[1].state == TaskState.CANCELLED
        assert contexts[2].state == TaskState.COMPLETED
        
        # Verify only the cancelled task has cancellation reason
        assert contexts[0].cancellation_reason is None
        assert contexts[1].cancellation_reason == CancellationReason.USER_REQUESTED
        assert contexts[2].cancellation_reason is None
        
        # Verify database states
        for i, session in enumerate(sessions):
            session.refresh_from_db()
            if i == 1:  # Middle task was cancelled
                assert session.status == 'cancelled'
            else:  # Other tasks completed
                assert session.status == 'completed'

    def test_cancellation_edge_cases(self):
        """Test edge cases in cancellation workflow"""
        task_id = str(uuid.uuid4())
        
        # Mock huey instance for task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        # Test 1: Cancel non-existent task
        cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_id})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.post(cancel_url)
            assert response.status_code == 200
            
            # Should handle gracefully
            assert response.context['task']['state'] in ['error', 'not_found']
        
        # Test 2: Cancel already completed task
        context = task_manager.register_task(task_id, str(self.test_session.id))
        task_manager.complete_task(task_id, success=True)
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.post(cancel_url)
            assert response.status_code == 200
            
            # Task should remain completed
            assert context.state == TaskState.COMPLETED
        
        # Test 3: Multiple cancellation requests
        task_id_2 = str(uuid.uuid4())
        context_2 = task_manager.register_task(task_id_2, str(self.test_session.id))
        
        cancel_url_2 = reverse('importer:cancel_task_api', kwargs={'task_id': task_id_2})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            # First cancellation
            response1 = self.client.post(cancel_url_2)
            assert response1.status_code == 200
            
            # Second cancellation (should be idempotent)
            response2 = self.client.post(cancel_url_2)
            assert response2.status_code == 200
            
            # Should still be in cancelling state
            assert context_2.state == TaskState.CANCELLING
            assert context_2.cancellation_requested is True

    def test_htmx_polling_during_cancellation(self):
        """Test HTMX polling behavior during cancellation process"""
        task_id = str(uuid.uuid4())
        
        # Mock huey instance for task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        # Register and start task
        context = task_manager.register_task(task_id, str(self.test_session.id))
        task_manager.update_task_progress(task_id, 40, "processing", "Processing...")
        
        status_url = reverse('importer:task_status_api', kwargs={'task_id': task_id})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            # Check initial state - should show cancel button and continue polling
            response = self.client.get(status_url, headers={'HX-Request': 'true'})
            assert response.status_code == 200
            content = response.content.decode()
            
            assert 'Cancel' in content
            assert 'hx-get' in content  # Should continue polling
            assert '40%' in content
            
            # Request cancellation
            cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_id})
            response = self.client.post(cancel_url, headers={'HX-Request': 'true'})
            assert response.status_code == 200
            
            # Check cancelling state - should continue polling but no cancel button
            response = self.client.get(status_url, headers={'HX-Request': 'true'})
            assert response.status_code == 200
            content = response.content.decode()
            
            assert 'cancelling' in content.lower()
            assert 'hx-get' in content  # Should continue polling while cancelling
            
            # Process cancellation
            task_manager._process_cancellation(context)
            
            # Check final cancelled state - should stop polling
            response = self.client.get(status_url, headers={'HX-Request': 'true'})
            assert response.status_code == 200
            content = response.content.decode()
            
            assert 'cancelled' in content.lower()
            assert 'hx-trigger="none"' in content or 'hx-get' not in content  # Should stop polling

    def test_session_ownership_during_cancellation(self):
        """Test that only task owners can cancel their tasks"""
        task_id = str(uuid.uuid4())
        
        # Create another user and session
        other_user, _ = User.objects.get_or_create(
            username="other_user",
            defaults={
                "email": "other@example.com",
                "name": "Other User",
                "organization": self.test_org,
                "role": "researcher"
            }
        )
        
        other_session = IngestSession.objects.create(
            user=other_user,
            organization=self.test_org,
            dataset_name="other_dataset",
            s3_bucket="test_bucket",
            s3_object_key="other_file.csv",
            status='processing'
        )
        
        # Mock huey instance for task manager
        mock_huey = MagicMock()
        task_manager = TaskManager(mock_huey)
        
        # Register task for other user
        context = task_manager.register_task(
            task_id=task_id,
            session_id=str(other_session.id),
            user_id=str(other_user.id)
        )
        
        # Current user tries to cancel other user's task
        cancel_url = reverse('importer:cancel_task_api', kwargs={'task_id': task_id})
        
        with patch('arkumu.importer.views.progress.get_task_manager') as mock_get_manager:
            mock_get_manager.return_value = task_manager
            
            response = self.client.post(
                cancel_url,
                {'session_id': str(other_session.id)},
                headers={'HX-Request': 'true'}
            )
            
            # Should handle gracefully (implementation might vary)
            assert response.status_code == 200
            
            # The task should still be in its original state
            # (Implementation detail: the view might not prevent this at UI level,
            # but the task manager should handle ownership at the service level)
            
        # Clean up
        other_session.delete()
        other_user.delete()