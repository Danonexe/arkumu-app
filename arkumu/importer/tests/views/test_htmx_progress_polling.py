"""
HTMX Progress Polling Integration Test

This test suite validates the complete HTMX polling system for import progress tracking.
It tests the full workflow from session creation to progress polling with proper authentication.

## Test Components

- **IngestSession creation** with proper user association
- **Progress polling** via HTMX endpoints
- **Authentication and authorization** checks
- **Progress cache** integration
- **Mock import workflow** with progress updates

## Test Flow

1. Create authenticated user and organization
2. Create IngestSession with proper user association
3. Start mock import process with progress updates
4. Test HTMX progress polling with authentication
5. Verify progress data and polling behavior
6. Test error conditions and authorization

This resolves the 403 Forbidden errors in the logs by ensuring proper user authentication
and session ownership validation.
"""

import pytest
import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponse
from unittest.mock import patch, MagicMock

from arkumu.importer.models import IngestSession
from arkumu.importer.services.progress_cache import ProgressCacheService
from arkumu.users.models import Organization
from arkumu.metadata.models.mappings import Mapping

User = get_user_model()


class HTMXProgressPollingTest(TestCase):
    """Test HTMX progress polling system with proper authentication"""
    
    def setUp(self):
        """Set up test environment"""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test organization
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='TEST',
            is_active=True
        )
        
        # Create test mapping
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            organization_id=self.organization.code,
            mapping_config={'test': 'data'}
        )
        
        # Initialize progress cache service
        self.progress_cache = ProgressCacheService()
    
    def test_session_creation_with_user_association(self):
        """Test that IngestSession is created with proper user association"""
        # Create session with user (mimics the fixed ingest_views.py)
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Verify user is properly associated
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.organization, self.organization)
        self.assertEqual(session.status, 'pending')
        self.assertIsNotNone(session.pk)
    
    def test_progress_polling_authenticated_success(self):
        """Test successful HTMX progress polling with authentication"""
        # Create session with user
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Set up progress data in cache
        progress_data = {
            'status': 'processing',
            'message': 'Processing data...',
            'percentage': 45,
            'event_type': 'progress'
        }
        self.progress_cache.update_progress(str(session.pk), progress_data)
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make HTMX request to progress endpoint
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Verify successful response
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Processing data...')
        
        # Verify response is HTML partial (not JSON)
        self.assertEqual(response['Content-Type'], 'text/html; charset=utf-8')
    
    def test_progress_polling_forbidden_no_auth(self):
        """Test that progress polling fails without authentication"""
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Don't login - should redirect to login
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_progress_polling_forbidden_wrong_user(self):
        """Test that progress polling fails for different user"""
        # Create another user
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        # Create session with first user
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Login as different user
        self.client.login(username='otheruser', password='otherpass123')
        
        # Make HTMX request
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should be forbidden
        self.assertEqual(response.status_code, 403)
    
    def test_progress_polling_session_not_found(self):
        """Test progress polling with non-existent session"""
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Use random UUID
        random_uuid = uuid.uuid4()
        
        # Make HTMX request
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': random_uuid}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should be forbidden
        self.assertEqual(response.status_code, 403)
    
    def test_progress_polling_default_data(self):
        """Test progress polling returns default data when no cache data"""
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make HTMX request (no cache data set)
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should return default progress data
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Waiting to start...')
    
    def test_progress_polling_completed_status(self):
        """Test that polling indicates completion for completed status"""
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='completed',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Set completed progress data
        progress_data = {
            'status': 'completed',
            'message': 'Import completed successfully',
            'percentage': 100,
            'event_type': 'progress'
        }
        self.progress_cache.update_progress(str(session.pk), progress_data)
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make HTMX request
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should indicate completion
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import completed successfully')
    
    def test_progress_polling_failed_status(self):
        """Test that polling handles failed status correctly"""
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='failed',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Set failed progress data
        progress_data = {
            'status': 'failed',
            'message': 'Import failed with error',
            'percentage': 0,
            'event_type': 'error'
        }
        self.progress_cache.update_progress(str(session.pk), progress_data)
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make HTMX request
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should indicate failure
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Import failed with error')
    
    @patch('arkumu.importer.services.progress_cache.ProgressCacheService.get_progress')
    def test_progress_polling_cache_error(self, mock_get_progress):
        """Test progress polling handles cache errors gracefully"""
        # Mock cache error
        mock_get_progress.side_effect = Exception("Cache error")
        
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make HTMX request
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        # Should handle error gracefully
        self.assertEqual(response.status_code, 403)
    
    def test_mock_import_workflow_with_progress(self):
        """Test complete mock import workflow with progress tracking"""
        # Create session
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Simulate progress updates
        progress_updates = [
            {'status': 'processing', 'message': 'Starting import...', 'percentage': 0},
            {'status': 'processing', 'message': 'Processing rows...', 'percentage': 25},
            {'status': 'processing', 'message': 'Halfway done...', 'percentage': 50},
            {'status': 'processing', 'message': 'Almost finished...', 'percentage': 75},
            {'status': 'completed', 'message': 'Import completed!', 'percentage': 100}
        ]
        
        for progress in progress_updates:
            # Update progress cache
            self.progress_cache.update_progress(str(session.pk), progress)
            
            # Poll progress
            response = self.client.get(
                reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
                HTTP_HX_REQUEST='true'
            )
            
            # Verify response
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, progress['message'])
    
    def tearDown(self):
        """Clean up test data"""
        # Clean up any cache entries
        try:
            self.progress_cache.clear_progress(str(self.user.pk))
        except:
            pass
        
        # Clean up database
        IngestSession.objects.all().delete()
        Mapping.objects.all().delete()
        Organization.objects.all().delete()
        User.objects.all().delete()


@pytest.mark.django_db
class TestHTMXProgressPollingIntegration:
    """Pytest-based integration tests for HTMX polling system"""
    
    def setup_method(self):
        """Set up test environment for each test"""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test organization
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='TEST',
            is_active=True
        )
        
        # Create test mapping
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            organization_id=self.organization.code,
            mapping_config={'test': 'data'}
        )
    
    def test_full_session_lifecycle_with_polling(self):
        """Test complete session lifecycle with HTMX polling"""
        # Create session with user (fixed bug)
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file.csv'],
            mapping=self.mapping
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Test initial polling
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert 'Waiting to start...' in response.content.decode()
        
        # Simulate progress updates
        progress_cache = ProgressCacheService()
        
        # Update 1: Started
        progress_cache.update_progress(str(session.pk), {
            'status': 'processing',
            'message': 'Import started',
            'percentage': 10
        })
        
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert 'Import started' in response.content.decode()
        
        # Update 2: Completed
        progress_cache.update_progress(str(session.pk), {
            'status': 'completed',
            'message': 'Import completed successfully',
            'percentage': 100
        })
        
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session.pk}),
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        assert 'Import completed successfully' in response.content.decode()
    
    def test_concurrent_user_sessions(self):
        """Test that multiple users can have separate sessions"""
        # Create second user
        user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        # Create sessions for both users
        session1 = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            status='pending',
            file_paths=['test_file1.csv'],
            mapping=self.mapping
        )
        
        session2 = IngestSession.objects.create(
            user=user2,
            organization=self.organization,
            status='pending',
            file_paths=['test_file2.csv'],
            mapping=self.mapping
        )
        
        # Set different progress for each session
        progress_cache = ProgressCacheService()
        progress_cache.update_progress(str(session1.pk), {
            'status': 'processing',
            'message': 'User 1 processing',
            'percentage': 30
        })
        progress_cache.update_progress(str(session2.pk), {
            'status': 'processing',
            'message': 'User 2 processing',
            'percentage': 70
        })
        
        # Test user 1 can only access their session
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session1.pk}),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        assert 'User 1 processing' in response.content.decode()
        
        # User 1 cannot access user 2's session
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session2.pk}),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 403
        
        # Test user 2 can access their session
        self.client.login(username='testuser2', password='testpass123')
        
        response = self.client.get(
            reverse('importer:import_progress', kwargs={'session_pk': session2.pk}),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        assert 'User 2 processing' in response.content.decode()