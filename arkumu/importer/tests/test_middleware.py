import pytest
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponseForbidden, QueryDict
from django.test import TestCase
from unittest.mock import Mock

from arkumu.importer.middleware import SSEAuthMiddleware
from arkumu.importer.models import IngestSession
from arkumu.users.models import Organization

User = get_user_model()


@pytest.mark.django_db
class TestSSEAuthMiddleware(TestCase):
    """Test SSE authentication middleware for securing import channels."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        self.organization = Organization.objects.create(
            name='Test Org',
            code='test-org'
        )
        
        # Create test session
        self.session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test-dataset',
            status='pending'
        )
        
        # Mock get_response
        self.get_response = Mock(return_value=Mock())
        self.middleware = SSEAuthMiddleware(self.get_response)
    
    def create_request(self, path, channel=None, user=None):
        """Helper to create HttpRequest with proper GET parameters."""
        request = HttpRequest()
        request.path = path
        request.user = user or self.user
        
        if channel:
            request.GET = QueryDict(f'channel={channel}')
        else:
            request.GET = QueryDict('')
        
        return request
    
    def test_non_sse_request_passes_through(self):
        """Test that non-SSE requests pass through unchanged."""
        request = self.create_request('/some/other/path')
        
        response = self.middleware(request)
        
        self.get_response.assert_called_once_with(request)
        self.assertEqual(response, self.get_response.return_value)
    
    def test_sse_request_with_valid_channel_and_user(self):
        """Test that valid SSE requests with correct user pass through."""
        request = self.create_request('/events/stream/', f'import-{self.session.pk}')
        
        response = self.middleware(request)
        
        self.get_response.assert_called_once_with(request)
        self.assertEqual(response, self.get_response.return_value)
    
    def test_sse_request_with_unauthenticated_user(self):
        """Test that unauthenticated users are rejected."""
        unauthenticated_user = Mock()
        unauthenticated_user.is_authenticated = False
        request = self.create_request('/events/stream/', f'import-{self.session.pk}', unauthenticated_user)
        
        response = self.middleware(request)
        
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.content.decode(), 'Authentication required')
        self.get_response.assert_not_called()
    
    def test_sse_request_with_wrong_user(self):
        """Test that users accessing other users' sessions are rejected."""
        request = self.create_request('/events/stream/', f'import-{self.session.pk}', self.other_user)
        
        response = self.middleware(request)
        
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.content.decode(), 'Unauthorized')
        self.get_response.assert_not_called()
    
    def test_sse_request_with_invalid_channel_format(self):
        """Test that invalid channel formats are rejected."""
        request = self.create_request('/events/stream/', 'invalid-channel-format')
        
        response = self.middleware(request)
        
        self.get_response.assert_called_once_with(request)
        self.assertEqual(response, self.get_response.return_value)
    
    def test_sse_request_with_nonexistent_session(self):
        """Test that channels for non-existent sessions are rejected."""
        import uuid
        fake_uuid = str(uuid.uuid4())
        request = self.create_request('/events/stream/', f'import-{fake_uuid}')
        
        response = self.middleware(request)
        
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.content.decode(), 'Invalid channel')
        self.get_response.assert_not_called()
    
    def test_sse_request_with_non_import_channel(self):
        """Test that non-import channels pass through unchanged."""
        request = self.create_request('/events/stream/', 'other-channel-123')
        
        response = self.middleware(request)
        
        self.get_response.assert_called_once_with(request)
        self.assertEqual(response, self.get_response.return_value)
    
    def test_sse_request_with_no_channel_param(self):
        """Test that SSE requests without channel parameter pass through."""
        request = self.create_request('/events/stream/')
        
        response = self.middleware(request)
        
        self.get_response.assert_called_once_with(request)
        self.assertEqual(response, self.get_response.return_value)
    
    def test_sse_request_with_invalid_session_id(self):
        """Test that channels with invalid session IDs are rejected."""
        request = self.create_request('/events/stream/', 'import-not-a-uuid')
        
        response = self.middleware(request)
        
        self.assertIsInstance(response, HttpResponseForbidden)
        self.assertEqual(response.content.decode(), 'Invalid channel')
        self.get_response.assert_not_called()