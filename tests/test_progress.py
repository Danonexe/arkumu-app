"""
Unit tests for SSE progress utility functions.

These tests ensure that the progress publishing utilities work correctly
and can handle various scenarios including error conditions.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings

from arkumu.importer.utils.progress import publish_progress, create_channel_id
from arkumu.importer.models import IngestSession
from arkumu.users.models import Organization

User = get_user_model()


class TestProgressUtilities(TestCase):
    """Test progress utility functions."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.organization = Organization.objects.create(
            name='Test Organization',
            slug='test-org'
        )
        
        self.session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            status='pending'
        )

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_basic(self, mock_send_event):
        """Test basic progress publishing."""
        channel = 'test-channel'
        payload = {
            'message': 'Processing...',
            'percentage': 50,
            'processed': 100,
            'total': 200
        }
        
        publish_progress(channel, payload)
        
        mock_send_event.assert_called_once_with(channel, 'progress', payload)

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_with_custom_event(self, mock_send_event):
        """Test progress publishing with custom event type."""
        channel = 'test-channel'
        payload = {'status': 'complete'}
        event_type = 'completion'
        
        publish_progress(channel, payload, event=event_type)
        
        mock_send_event.assert_called_once_with(channel, event_type, payload)

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_empty_payload(self, mock_send_event):
        """Test progress publishing with empty payload."""
        channel = 'test-channel'
        payload = {}
        
        publish_progress(channel, payload)
        
        mock_send_event.assert_called_once_with(channel, 'progress', payload)

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_complex_payload(self, mock_send_event):
        """Test progress publishing with complex payload."""
        channel = 'test-channel'
        payload = {
            'message': 'Processing entities...',
            'percentage': 75,
            'processed': 750,
            'total': 1000,
            'current_dataset': 'people.csv',
            'current_entity': 'person_123',
            'metadata': {
                'errors': 0,
                'warnings': 2,
                'start_time': '2024-01-01T10:00:00Z'
            }
        }
        
        publish_progress(channel, payload)
        
        mock_send_event.assert_called_once_with(channel, 'progress', payload)

    def test_create_channel_id(self):
        """Test channel ID generation."""
        session_pk = self.session.pk
        expected_channel = f'import-{session_pk}'
        
        channel_id = create_channel_id(session_pk)
        
        self.assertEqual(channel_id, expected_channel)

    def test_create_channel_id_with_uuid(self):
        """Test channel ID generation with UUID primary key."""
        # IngestSession uses UUID primary key
        session_pk = self.session.pk
        expected_channel = f'import-{session_pk}'
        
        channel_id = create_channel_id(session_pk)
        
        self.assertEqual(channel_id, expected_channel)
        self.assertIn('import-', channel_id)

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_handles_send_event_exception(self, mock_send_event):
        """Test that publish_progress handles exceptions from send_event."""
        mock_send_event.side_effect = Exception("Redis connection failed")
        
        channel = 'test-channel'
        payload = {'message': 'test'}
        
        # Should not raise an exception
        try:
            publish_progress(channel, payload)
        except Exception as e:
            self.fail(f"publish_progress should handle exceptions gracefully, but raised: {e}")

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_json_serializable_payload(self, mock_send_event):
        """Test that only JSON-serializable payloads are accepted."""
        channel = 'test-channel'
        
        # Test with JSON-serializable payload
        valid_payload = {
            'message': 'test',
            'percentage': 50,
            'data': ['item1', 'item2'],
            'metadata': {'key': 'value'}
        }
        
        publish_progress(channel, valid_payload)
        mock_send_event.assert_called_once_with(channel, 'progress', valid_payload)


class TestProgressUtilitiesWithMockSession(TestCase):
    """Test progress utilities with mock session objects."""

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_multiple_calls(self, mock_send_event):
        """Test multiple progress publishing calls."""
        channel = 'test-channel'
        
        # Simulate multiple progress updates
        updates = [
            {'message': 'Starting...', 'percentage': 0},
            {'message': 'Processing...', 'percentage': 25},
            {'message': 'Halfway done...', 'percentage': 50},
            {'message': 'Almost complete...', 'percentage': 90},
            {'message': 'Complete!', 'percentage': 100}
        ]
        
        for update in updates:
            publish_progress(channel, update)
        
        # Verify all calls were made
        expected_calls = [
            call(channel, 'progress', update) for update in updates
        ]
        mock_send_event.assert_has_calls(expected_calls)
        self.assertEqual(mock_send_event.call_count, len(updates))

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_different_channels(self, mock_send_event):
        """Test progress publishing to different channels."""
        channels = ['import-1', 'import-2', 'import-3']
        payload = {'message': 'Processing...', 'percentage': 50}
        
        for channel in channels:
            publish_progress(channel, payload)
        
        # Verify calls to different channels
        expected_calls = [
            call(channel, 'progress', payload) for channel in channels
        ]
        mock_send_event.assert_has_calls(expected_calls)

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_different_event_types(self, mock_send_event):
        """Test progress publishing with different event types."""
        channel = 'test-channel'
        
        events = [
            ({'message': 'Starting...'}, 'start'),
            ({'message': 'Processing...'}, 'progress'),
            ({'message': 'Complete!'}, 'complete'),
            ({'message': 'Error occurred!'}, 'error')
        ]
        
        for payload, event_type in events:
            publish_progress(channel, payload, event=event_type)
        
        # Verify calls with different event types
        expected_calls = [
            call(channel, event_type, payload) for payload, event_type in events
        ]
        mock_send_event.assert_has_calls(expected_calls)


@pytest.mark.django_db
class TestProgressUtilitiesIntegration:
    """Integration tests for progress utilities."""

    def test_create_channel_id_with_real_session(self):
        """Test channel ID creation with real session."""
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
        
        # Create session
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            status='pending'
        )
        
        # Test channel ID generation
        channel_id = create_channel_id(session.pk)
        expected_channel = f'import-{session.pk}'
        
        assert channel_id == expected_channel

    @patch('arkumu.importer.utils.progress.send_event')
    def test_publish_progress_with_session_channel(self, mock_send_event):
        """Test progress publishing using session-generated channel."""
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
        
        # Create session
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            status='pending'
        )
        
        # Generate channel and publish progress
        channel_id = create_channel_id(session.pk)
        payload = {
            'message': 'Processing dataset...',
            'percentage': 75,
            'session_id': str(session.pk),
            'dataset_name': session.dataset_name
        }
        
        publish_progress(channel_id, payload)
        
        # Verify the call
        mock_send_event.assert_called_once_with(channel_id, 'progress', payload)