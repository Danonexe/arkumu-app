"""
Simple Import Polling Integration Test

This test validates the polling mechanism without actually executing the import workflow.
It focuses on the view-based polling system and user experience.
"""

import pytest
import logging
from typing import Dict, Any
from unittest.mock import patch
import json
import uuid

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone as django_timezone

from arkumu.importer.models import IngestSession
from arkumu.importer.services.progress_cache import ProgressCacheService
from arkumu.users.models import Organization, User
from arkumu.metadata.models.mappings import Mapping

logger = logging.getLogger(__name__)


class TestSimplePollingIntegration:
    """Simple integration test focusing on the polling mechanism"""

    def setup_method(self):
        """Setup test environment"""
        self.client = Client()
        self.progress_cache = ProgressCacheService()
        
        # Create test organization
        self.test_org, _ = Organization.objects.get_or_create(
            code="test_org",
            defaults={
                "name": "Test Organization",
                "description": "Test organization for polling integration"
            }
        )
        
        # Create test user
        self.test_user, _ = User.objects.get_or_create(
            username="test_polling_user",
            defaults={
                "email": "test@example.com",
                "name": "Test User",
                "organization": self.test_org,
                "role": "researcher"
            }
        )
        
        # Login test user
        self.client.force_login(self.test_user)
        
        # Test session tracking
        self.test_session = None
        self.test_task_id = None

    @pytest.mark.django_db(transaction=True)
    def test_progress_polling_workflow(self):
        """Test the progress polling workflow with simulated data"""
        logger.info("=== TESTING PROGRESS POLLING WORKFLOW ===")
        
        # Create a test IngestSession
        session = IngestSession.objects.create(
            user=self.test_user,
            organization=self.test_org,
            dataset_name="test_dataset",
            s3_bucket="test_bucket",
            s3_object_key="test_file.csv",
            status='processing',
            progress_percentage=25,
            progress_message="Processing data..."
        )
        
        self.test_session = session
        
        # Update progress in cache to match what we expect
        self._update_progress(session.pk, 25, "Processing data...")
        
        # Debug: Try setting cache directly
        cache_key = f"import_progress_{session.pk}"
        test_data = {'status': 'processing', 'percentage': 25, 'message': 'Processing data...'}
        cache.set(cache_key, test_data, timeout=3600)
        
        # Check what's actually in the cache
        cached_data = cache.get(cache_key)
        logger.info(f"Cache key: {cache_key}")
        logger.info(f"Cached data: {cached_data}")
        
        # Test 1: Initial progress polling
        initial_progress = self._test_progress_polling_step(session.pk, expected_progress=25)
        
        # Test 2: Progress update
        self._update_progress(session.pk, 50, "Halfway through processing...")
        mid_progress = self._test_progress_polling_step(session.pk, expected_progress=50)
        
        # Test 3: Completion
        self._update_progress(session.pk, 100, "Import completed successfully", status="completed")
        final_progress = self._test_progress_polling_step(session.pk, expected_progress=100)
        
        # Verify polling stops after completion
        assert not final_progress['should_poll'], "Polling should stop after completion"
        
        logger.info("=== PROGRESS POLLING WORKFLOW TEST PASSED ===")

    @pytest.mark.django_db(transaction=True)
    def test_task_status_polling_workflow(self):
        """Test the task status polling workflow with cache-based updates"""
        logger.info("=== TESTING TASK STATUS POLLING WORKFLOW ===")
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        self.test_task_id = task_id
        
        # Test 1: Initial status
        self._update_task_status(task_id, "processing", 20, "Loading data...")
        initial_status = self._test_task_status_polling_step(task_id, expected_status="processing")
        
        # Test 2: Mid-progress with phase info
        self._update_task_status(task_id, "processing", 60, "Processing rows...", phase_info={
            "current_phase": "data_import",
            "current_phase_index": 3,
            "total_phases": 5,
            "execution_strategy": "mapping_driven"
        })
        mid_status = self._test_task_status_polling_step(task_id, expected_status="processing")
        
        # Test 3: Completion
        self._update_task_status(task_id, "completed", 100, "Import completed", details={
            "rows_processed": 1000,
            "resources_created": 500,
            "triples_created": 2500
        })
        final_status = self._test_task_status_polling_step(task_id, expected_status="completed")
        
        # Verify polling stops after completion
        assert not final_status['should_poll'], "Task status polling should stop after completion"
        
        logger.info("=== TASK STATUS POLLING WORKFLOW TEST PASSED ===")

    @pytest.mark.django_db(transaction=True)
    def test_error_handling_in_polling(self):
        """Test error handling in both polling mechanisms"""
        logger.info("=== TESTING ERROR HANDLING IN POLLING ===")
        
        # Test progress polling error handling
        session = IngestSession.objects.create(
            user=self.test_user,
            organization=self.test_org,
            dataset_name="error_test_dataset",
            s3_bucket="test_bucket",
            s3_object_key="error_file.csv",
            status='failed',
            error_message="File not found"
        )
        
        self.test_session = session
        
        # Update progress with error
        self._update_progress(session.pk, 0, "Import failed: File not found", status="failed")
        
        # Test progress polling with error
        error_progress = self._test_progress_polling_step(session.pk, expected_status="failed")
        
        # Verify error handling
        assert not error_progress['should_poll'], "Progress polling should stop on error"
        assert 'failed' in error_progress['content'].lower(), "Error status should be visible"
        
        # Test task status polling error handling
        task_id = str(uuid.uuid4())
        self.test_task_id = task_id
        
        self._update_task_status(task_id, "failed", 0, "Task failed", error_type="FileNotFoundError")
        
        error_task_status = self._test_task_status_polling_step(task_id, expected_status="failed")
        
        # Verify error handling
        assert not error_task_status['should_poll'], "Task status polling should stop on error"
        assert 'failed' in error_task_status['content'].lower(), "Error status should be visible"
        
        logger.info("=== ERROR HANDLING TEST PASSED ===")

    @pytest.mark.django_db(transaction=True)
    def test_session_ownership_validation(self):
        """Test that users can only access their own sessions"""
        logger.info("=== TESTING SESSION OWNERSHIP VALIDATION ===")
        
        # Create another user
        other_user, _ = User.objects.get_or_create(
            username="other_user",
            defaults={
                "email": "other@example.com",
                "name": "Other User",
                "organization": self.test_org,
                "role": "researcher"
            }
        )
        
        # Create session for other user
        other_session = IngestSession.objects.create(
            user=other_user,
            organization=self.test_org,
            dataset_name="other_dataset",
            s3_bucket="test_bucket",
            s3_object_key="other_file.csv",
            status='processing'
        )
        
        # Try to access other user's session (should fail)
        url = reverse('importer:import_progress', kwargs={'session_pk': other_session.pk})
        response = self.client.get(url, headers={'HX-Request': 'true'})
        
        # Should be forbidden or not found
        assert response.status_code in [403, 404], f"Should not allow access to other user's session: {response.status_code}"
        
        logger.info("=== SESSION OWNERSHIP VALIDATION TEST PASSED ===")

    def _test_progress_polling_step(self, session_pk: uuid.UUID, expected_progress: int = None, expected_status: str = None) -> Dict[str, Any]:
        """Test a single progress polling step"""
        url = reverse('importer:import_progress', kwargs={'session_pk': session_pk})
        response = self.client.get(url, headers={'HX-Request': 'true'})
        
        assert response.status_code == 200, f"Progress polling failed: {response.status_code}"
        
        content = response.content.decode()
        
        if expected_progress is not None:
            assert str(expected_progress) in content, f"Expected progress {expected_progress} not found"
        
        if expected_status:
            assert expected_status in content.lower(), f"Expected status {expected_status} not found"
        
        # Check if polling should continue - look for hx-trigger="none" which indicates polling should stop
        should_poll = 'hx-trigger="none"' not in content
        
        return {
            'content': content,
            'should_poll': should_poll,
            'response': response
        }

    def _test_task_status_polling_step(self, task_id: str, expected_progress: int = None, expected_status: str = None) -> Dict[str, Any]:
        """Test a single task status polling step"""
        url = reverse('importer:task_status', kwargs={'task_id': task_id})
        response = self.client.get(url, headers={'HX-Request': 'true'})
        
        assert response.status_code == 200, f"Task status polling failed: {response.status_code}"
        
        content = response.content.decode()
        
        # Task status template shows visual indicators, not raw progress numbers
        # So we check for the appropriate visual elements instead
        if expected_status == "processing":
            assert 'loading loading-spinner' in content, "Expected loading spinner for processing status"
        elif expected_status == "completed":
            assert 'text-success' in content, "Expected success icon for completed status"
        elif expected_status == "failed":
            assert 'text-error' in content, "Expected error icon for failed status"
        
        # Check if polling should continue - look for hx-trigger="none" which indicates polling should stop
        should_poll = 'hx-trigger="none"' not in content
        
        return {
            'content': content,
            'should_poll': should_poll,
            'response': response
        }

    def _update_progress(self, session_pk: uuid.UUID, progress: int, message: str, status: str = "processing"):
        """Update progress in the cache"""
        data = {
            'status': status,
            'progress': progress,
            'message': message,
            'percentage': progress,  # The view expects 'percentage' field
            'timestamp': django_timezone.now().isoformat()
        }
        logger.info(f"Updating progress for session {session_pk}: {data}")
        self.progress_cache.update_progress(str(session_pk), data)
        
        # Verify it was set
        cached_data = self.progress_cache.get_progress(str(session_pk))
        logger.info(f"Verification - cached data: {cached_data}")

    def _update_task_status(self, task_id: str, status: str, progress: int, message: str, 
                           phase_info: Dict = None, details: Dict = None, error_type: str = None):
        """Update task status in Django cache"""
        cache_key = f"task_status_{task_id}"
        
        data = {
            'status': status,
            'progress': progress,
            'message': message,
            'timestamp': django_timezone.now().isoformat()
        }
        
        if phase_info:
            data['phase_info'] = phase_info
        if details:
            data['details'] = details
        if error_type:
            data['error_type'] = error_type
        
        cache.set(cache_key, data, timeout=3600)

    def teardown_method(self):
        """Clean up after each test"""
        logger.info("Cleaning up test resources...")
        
        # Clear cache entries
        if self.test_task_id:
            cache.delete(f"task_status_{self.test_task_id}")
        
        if self.test_session:
            self.progress_cache.clear_progress(self.test_session.pk)
            
        # Clean up test sessions
        IngestSession.objects.filter(
            user=self.test_user,
            dataset_name__startswith="test_"
        ).delete()
        
        logger.info("Test cleanup completed")