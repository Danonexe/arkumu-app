"""
Tests for SSE Authentication Middleware

These tests ensure that the SSE authentication middleware properly
validates user permissions for accessing import channels.
"""

import pytest
import uuid
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden
from django.contrib.auth.models import AnonymousUser

from arkumu.importer.middleware import SSEAuthMiddleware
from arkumu.importer.models import IngestSession
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping

User = get_user_model()


class TestSSEAuthMiddleware(TestCase):
    """Test SSE authentication middleware."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.middleware = SSEAuthMiddleware(lambda request: None)
        
        # Create test users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        # Create organization
        self.organization = Organization.objects.create(
            name='Test Organization',
            slug='test-org'
        )
        
        # Create mapping
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user1,
            organization=self.organization,
            configuration={'columns': {}}
        )
        
        # Create session
        self.session = IngestSession.objects.create(
            user=self.user1,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )

    def test_non_sse_request_passes_through(self):
        """Test that non-SSE requests pass through unchanged."""
        request = self.factory.get('/some/other/path')
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should not return a response (passes through)
        self.assertIsNone(response)

    def test_sse_non_import_channel_passes_through(self):
        """Test that non-import SSE channels pass through."""
        request = self.factory.get('/events/stream/', {'channel': 'other-channel'})
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should not return a response (passes through)
        self.assertIsNone(response)

    def test_sse_import_channel_valid_user(self):
        """Test that valid user can access their own import channel."""
        channel = f'import-{self.session.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should not return a response (passes through)
        self.assertIsNone(response)

    def test_sse_import_channel_unauthenticated_user(self):
        """Test that unauthenticated user cannot access import channel."""
        channel = f'import-{self.session.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = AnonymousUser()
        
        response = self.middleware(request)
        
        # Should return forbidden response
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Authentication required', response.content.decode())

    def test_sse_import_channel_wrong_user(self):
        """Test that wrong user cannot access import channel."""
        channel = f'import-{self.session.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user2  # Different user
        
        response = self.middleware(request)
        
        # Should return forbidden response
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Unauthorized', response.content.decode())

    def test_sse_import_channel_invalid_session_id(self):
        """Test that invalid session ID returns forbidden."""
        invalid_uuid = str(uuid.uuid4())
        channel = f'import-{invalid_uuid}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should return forbidden response
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Invalid channel', response.content.decode())

    def test_sse_import_channel_malformed_channel(self):
        """Test that malformed channel returns forbidden."""
        channel = 'import-not-a-valid-id'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should return forbidden response
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Invalid channel', response.content.decode())

    def test_sse_import_channel_empty_channel(self):
        """Test that empty channel parameter passes through."""
        request = self.factory.get('/events/stream/', {'channel': ''})
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should not return a response (passes through)
        self.assertIsNone(response)

    def test_sse_import_channel_no_channel_parameter(self):
        """Test that missing channel parameter passes through."""
        request = self.factory.get('/events/stream/')
        request.user = self.user1
        
        response = self.middleware(request)
        
        # Should not return a response (passes through)
        self.assertIsNone(response)


class TestSSEAuthMiddlewareWithMultipleSessions(TestCase):
    """Test SSE authentication middleware with multiple sessions."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.middleware = SSEAuthMiddleware(lambda request: None)
        
        # Create test users
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        # Create organization
        self.organization = Organization.objects.create(
            name='Test Organization',
            slug='test-org'
        )
        
        # Create mapping
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user1,
            organization=self.organization,
            configuration={'columns': {}}
        )
        
        # Create sessions for both users
        self.session1 = IngestSession.objects.create(
            user=self.user1,
            organization=self.organization,
            dataset_name='dataset1',
            mapping=self.mapping,
            status='pending'
        )
        
        self.session2 = IngestSession.objects.create(
            user=self.user2,
            organization=self.organization,
            dataset_name='dataset2',
            mapping=self.mapping,
            status='pending'
        )

    def test_user_can_access_own_session(self):
        """Test that user can access their own session."""
        # User1 accessing their own session
        channel = f'import-{self.session1.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user1
        
        response = self.middleware(request)
        self.assertIsNone(response)  # Should pass through
        
        # User2 accessing their own session
        channel = f'import-{self.session2.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user2
        
        response = self.middleware(request)
        self.assertIsNone(response)  # Should pass through

    def test_user_cannot_access_other_user_session(self):
        """Test that user cannot access another user's session."""
        # User1 trying to access User2's session
        channel = f'import-{self.session2.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user1
        
        response = self.middleware(request)
        self.assertIsInstance(response, HttpResponseForbidden)
        
        # User2 trying to access User1's session
        channel = f'import-{self.session1.pk}'
        request = self.factory.get('/events/stream/', {'channel': channel})
        request.user = self.user2
        
        response = self.middleware(request)
        self.assertIsInstance(response, HttpResponseForbidden)


@pytest.mark.django_db
class TestSSEAuthMiddlewareIntegration:
    """Integration tests for SSE authentication middleware."""

    def test_middleware_with_real_session(self):
        """Test middleware with real session data."""
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        # Create test user and organization
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        organization = Organization.objects.create(
            name='Test Organization',
            slug='test-org'
        )
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=user,
            organization=organization,
            configuration={'columns': {}}
        )
        
        # Create session
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Test valid access
        channel = f'import-{session.pk}'
        request = factory.get('/events/stream/', {'channel': channel})
        request.user = user
        
        response = middleware(request)
        assert response is None  # Should pass through

    def test_middleware_exception_handling(self):
        """Test middleware handles exceptions gracefully."""
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        # Create request with invalid channel format
        request = factory.get('/events/stream/', {'channel': 'import-invalid-format-test'})
        request.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        response = middleware(request)
        assert isinstance(response, HttpResponseForbidden)
        assert response.status_code == 403


class TestSSEAuthMiddlewareEdgeCases(TestCase):
    """Test edge cases for SSE authentication middleware."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.middleware = SSEAuthMiddleware(lambda request: None)
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_sse_path_variations(self):
        """Test different SSE path variations."""
        # Test exact path
        request = self.factory.get('/events/stream/')
        request.user = self.user
        response = self.middleware(request)
        self.assertIsNone(response)
        
        # Test path with trailing slash
        request = self.factory.get('/events/stream/extra/')
        request.user = self.user
        response = self.middleware(request)
        self.assertIsNone(response)
        
        # Test path with query parameters
        request = self.factory.get('/events/stream/?channel=test')
        request.user = self.user
        response = self.middleware(request)
        self.assertIsNone(response)

    def test_channel_prefix_variations(self):
        """Test different channel prefix variations."""
        # Test exact import prefix
        request = self.factory.get('/events/stream/', {'channel': 'import-123'})
        request.user = self.user
        response = self.middleware(request)
        # Should try to validate and fail (invalid session)
        self.assertIsInstance(response, HttpResponseForbidden)
        
        # Test similar but different prefix
        request = self.factory.get('/events/stream/', {'channel': 'imports-123'})
        request.user = self.user
        response = self.middleware(request)
        # Should pass through (not import- prefix)
        self.assertIsNone(response)
        
        # Test case sensitivity
        request = self.factory.get('/events/stream/', {'channel': 'Import-123'})
        request.user = self.user
        response = self.middleware(request)
        # Should pass through (case sensitive)
        self.assertIsNone(response)

    def test_session_id_format_handling(self):
        """Test different session ID formats."""
        # Test numeric ID (should work after UUID conversion fails)
        request = self.factory.get('/events/stream/', {'channel': 'import-123'})
        request.user = self.user
        response = self.middleware(request)
        # Should fail validation (session doesn't exist)
        self.assertIsInstance(response, HttpResponseForbidden)
        
        # Test UUID format
        test_uuid = str(uuid.uuid4())
        request = self.factory.get('/events/stream/', {'channel': f'import-{test_uuid}'})
        request.user = self.user
        response = self.middleware(request)
        # Should fail validation (session doesn't exist)
        self.assertIsInstance(response, HttpResponseForbidden)
        
        # Test invalid format
        request = self.factory.get('/events/stream/', {'channel': 'import-not-valid'})
        request.user = self.user
        response = self.middleware(request)
        # Should fail validation (invalid format)
        self.assertIsInstance(response, HttpResponseForbidden)