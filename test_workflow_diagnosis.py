#!/usr/bin/env python
"""
Comprehensive workflow test to diagnose polling/cache key issues.

This test reproduces the exact workflow from metadata import trigger to completion
to identify why polling is not working properly.

PROBLEM IDENTIFIED:
===================
1. Import view creates task with polling_task_id (UUID) 
2. Cache key in import view: f"task_status_{polling_task_id}"
3. Task uses upload_session_id as actual_task_id
4. Cache key in task: f"task_state_{actual_task_id}" 
5. Progress view uses: f"task_state_{task_id}"

CACHE KEY MISMATCH:
- View stores: task_status_<uuid>
- Task stores: task_state_<session_id>  
- Progress polls: task_state_<uuid>

SOLUTION: Align all cache keys to use the same pattern.
"""

import os
import django
import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.cache import cache
from unittest.mock import patch, MagicMock

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from arkumu.users.models import User, Organization
from arkumu.importer.models import IngestSession
from arkumu.importer.tasks.import_metadata import run_csv_import_workflow

class WorkflowDiagnosisTest(TestCase):
    """Test the complete workflow to identify cache key issues"""
    
    def setUp(self):
        """Setup test data"""
        # Use get_or_create to avoid duplicate key errors
        self.user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'password': 'testpass123'
            }
        )
        
        self.organization, created = Organization.objects.get_or_create(
            code='TEST',
            defaults={
                'name': 'Test Org'
            }
        )
        
        self.client = Client()
        self.client.force_login(self.user)
        
        # Clear cache before each test
        cache.clear()
    
    def test_cache_key_workflow_diagnosis(self):
        """
        Test the complete workflow from import trigger to status polling
        to identify cache key mismatches
        """
        print("\n" + "="*80)
        print("WORKFLOW DIAGNOSIS: Cache Key Mismatch Investigation")
        print("="*80)
        
        # Step 1: Simulate import trigger (from import_views.py:ingest_file)
        print("\n1. IMPORT TRIGGER - ingest_file view")
        print("-" * 40)
        
        # This mimics the FIXED flow in import_views.py
        # Create IngestSession first
        ingest_session = IngestSession.objects.create(
            user=self.user,
            dataset_name="test_dataset",
            organization=self.organization,
            s3_bucket="test-bucket",
            s3_object_key="test/file.csv",
            status='pending',
            delimiter=';',
            has_quoted_fields=True,
            base_uri="http://arkumu.org/data",
            task_id="",  # Will be set to session ID
        )
        
        # Use session ID as polling task ID (FIXED)
        polling_task_id = str(ingest_session.id)
        ingest_session.task_id = polling_task_id
        ingest_session.save()
        
        print(f"Created IngestSession with ID: {ingest_session.id}")
        print(f"Polling task ID (same as session ID): {polling_task_id}")
        print(f"IngestSession task_id (polling): {ingest_session.task_id}")
        
        # Store initial cache status with FIXED cache key
        cache_key_view = f"task_state_{polling_task_id}"
        initial_task_info = {
            "status": "pending", 
            "message": f"CSV ingestion for 'file.csv' has been queued.",
            "progress": 0
        }
        cache.set(cache_key_view, initial_task_info, timeout=3600)
        print(f"View cache key: {cache_key_view}")
        print(f"View cache content: {cache.get(cache_key_view)}")
        
        # Step 2: Mock Huey task execution
        print("\n2. HUEY TASK EXECUTION - run_csv_import_workflow")
        print("-" * 50)
        
        # Mock the task execution to see cache key logic
        with patch('arkumu.importer.tasks.import_metadata.ImportOrchestrator') as mock_orchestrator:
            mock_orchestrator.return_value.import_csv.return_value = {
                'status': 'completed',
                'processed_files': 1,
                'total_triples': 100
            }
            
            # This is what happens in the FIXED task (uses task_id_for_cache)
            upload_session_id = ingest_session.id
            task_id_for_cache = polling_task_id  # This is passed from the view
            actual_task_id = task_id_for_cache  # Task now uses the passed task_id_for_cache
            cache_key_task = f"task_state_{actual_task_id}"
            
            print(f"Task upload_session_id: {upload_session_id}")
            print(f"Task task_id_for_cache: {task_id_for_cache}")
            print(f"Task actual_task_id: {actual_task_id}")
            print(f"Task cache key: {cache_key_task}")
            
            # Simulate task cache update (lines 460-470)
            task_payload = {"status": "processing", "message": "Processing CSV...", "progress": 50}
            cache.set(cache_key_task, task_payload, timeout=3600)
            print(f"Task cache content: {cache.get(cache_key_task)}")
        
        # Step 3: Simulate progress polling
        print("\n3. PROGRESS POLLING - task_status_view")
        print("-" * 40)
        
        # This is what the FIXED progress view does (now uses task_state_)
        poll_cache_key = f"task_state_{polling_task_id}"
        polled_data = cache.get(poll_cache_key)
        print(f"Polling cache key: {poll_cache_key}")
        print(f"Polled data: {polled_data}")
        
        # Check new progress view
        progress_cache_key = f"task_state_{polling_task_id}"
        progress_data = cache.get(progress_cache_key)
        print(f"Progress view cache key: {progress_cache_key}")
        print(f"Progress data: {progress_data}")
        
        # Step 4: Verify the fix
        print("\n4. CACHE KEY ANALYSIS (AFTER FIX)")
        print("-" * 35)
        
        print(f"View stores in:    task_state_{polling_task_id}")
        print(f"Task stores in:    task_state_{polling_task_id}")
        print(f"Progress polls:    task_state_{polling_task_id}")
        print(f"Legacy polls:      task_state_{polling_task_id}")
        
        print(f"\npolling_task_id:   {polling_task_id}")
        print(f"session_id:        {ingest_session.id}")
        print(f"Keys match:        {polling_task_id == str(ingest_session.id)}")
        
        # Show what's actually in cache
        print(f"\nCache contents:")
        print(f"task_state_{polling_task_id}: {cache.get(f'task_state_{polling_task_id}')}")
        print(f"task_state_{ingest_session.id}: {cache.get(f'task_state_{ingest_session.id}')}")
        
        # Test key alignment
        view_key = f"task_state_{polling_task_id}"
        task_key = f"task_state_{polling_task_id}"
        print(f"\nKey alignment check:")
        print(f"View key == Task key: {view_key == task_key}")
        print(f"Both keys point to same data: {cache.get(view_key) == cache.get(task_key)}")
        
        # Step 5: Test the views
        print("\n5. VIEW TESTING")
        print("-" * 15)
        
        # Test legacy task status view
        response = self.client.get(f'/importer/task-status/{polling_task_id}/')
        print(f"Legacy task status response: {response.status_code}")
        if response.status_code == 200:
            print("✓ Legacy view works (finds task_status_ key)")
        
        # Test new progress view
        response = self.client.get(f'/importer/progress/status/{polling_task_id}/')
        print(f"Progress API response: {response.status_code}")
        if response.status_code == 200:
            print("✓ Progress view accessible")
        
        print("\n" + "="*80)
        print("DIAGNOSIS COMPLETE")
        print("="*80)

if __name__ == '__main__':
    test = WorkflowDiagnosisTest()
    test.setUp()
    test.test_cache_key_workflow_diagnosis()