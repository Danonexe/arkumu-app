#!/usr/bin/env python
"""
Test to verify the cancel button shows up correctly during import processing.
"""

import os
import django
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.cache import cache

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from arkumu.users.models import User, Organization
from arkumu.importer.models import IngestSession

def test_cancel_button_display():
    """Test that cancel button appears when task is in processing state"""
    print("\n" + "="*60)
    print("TESTING CANCEL BUTTON DISPLAY")
    print("="*60)
    
    # Create test user and organization
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={'email': 'test@example.com'}
    )
    
    organization, created = Organization.objects.get_or_create(
        code='TEST',
        defaults={'name': 'Test Org'}
    )
    
    # Create test session
    session = IngestSession.objects.create(
        user=user,
        dataset_name="test_dataset",
        organization=organization,
        s3_bucket="test-bucket",
        s3_object_key="test/file.csv",
        status='pending',
        delimiter=';',
        has_quoted_fields=True,
        base_uri="http://arkumu.org/data",
        task_id="",
    )
    
    # Set the session ID as task ID (our fix)
    session.task_id = str(session.id)
    session.save()
    
    print(f"✅ Created test session: {session.id}")
    print(f"✅ Task ID: {session.task_id}")
    
    # Simulate task in processing state
    cache_key = f"task_state_{session.task_id}"
    task_data = {
        'task_id': session.task_id,
        'state': 'processing',  # This should trigger cancel button
        'progress': 50,
        'phase': 'data_processing',
        'message': 'Processing CSV data...',
        'error_message': None,
        'start_time': '2025-07-18T16:56:00Z',
        'end_time': None,
        'cancellation_requested': False,
        'cancellation_reason': None,
    }
    
    cache.set(cache_key, task_data, timeout=3600)
    print(f"✅ Set cache data for key: {cache_key}")
    print(f"✅ Task state: {task_data['state']}")
    
    # Test the progress view
    client = Client()
    client.force_login(user)
    
    response = client.get(f'/importer/progress/status/{session.task_id}/?session_id={session.id}')
    print(f"✅ Progress view response: {response.status_code}")
    
    # Check if cancel button logic would work
    template_condition = task_data['state'] in ['running', 'pending', 'processing']
    print(f"✅ Template condition (should be True): {template_condition}")
    
    # Check response content for cancel button
    if response.status_code == 200:
        content = response.content.decode()
        has_cancel_button = 'Cancel' in content and 'btn-error' in content
        print(f"✅ Cancel button in response: {has_cancel_button}")
        
        # Print some of the response to debug
        print("\n--- Response Content Preview ---")
        lines = content.split('\n')
        for i, line in enumerate(lines[:20]):
            if 'Cancel' in line or 'btn-error' in line or 'processing' in line:
                print(f"Line {i}: {line.strip()}")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == '__main__':
    test_cancel_button_display()