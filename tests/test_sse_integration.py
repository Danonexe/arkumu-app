"""
Comprehensive integration tests for SSE implementation.

These tests verify the complete SSE system including progress publishing,
middleware authentication, task execution, and error handling.
"""

import pytest
import json
import time
from unittest.mock import patch, MagicMock, Mock, call
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.test.client import Client
from django.urls import reverse

from arkumu.importer.models import IngestSession
from arkumu.importer.utils.progress import publish_progress, create_channel_id
from arkumu.importer.tasks import run_import
from arkumu.importer.middleware import SSEAuthMiddleware
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping

User = get_user_model()


@pytest.mark.django_db
class TestSSESystemIntegration:
    """Test the complete SSE system integration."""

    def test_complete_sse_flow_success(self):
        """Test complete SSE flow from start to finish."""
        # Create test data
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
            configuration={'columns': {}, 'datasets': []}
        )
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Mock the SSE publishing
        with patch('arkumu.importer.utils.progress.send_event') as mock_send_event:
            # Mock the processor
            with patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor') as mock_processor_class:
                mock_processor = MagicMock()
                mock_processor.process_with_execution_config.return_value = MagicMock(
                    rows_processed=100,
                    resources_created=50,
                    triples_created=200,
                    errors=0
                )
                mock_processor_class.return_value = mock_processor
                
                # Execute the import task
                run_import(session.pk)
                
                # Verify SSE events were sent
                assert mock_send_event.call_count >= 2  # At least start and complete
                
                # Verify session was updated
                session.refresh_from_db()
                assert session.status == 'completed'
                assert session.started_at is not None
                assert session.completed_at is not None

    def test_complete_sse_flow_with_error(self):
        """Test complete SSE flow with error handling."""
        # Create test data
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
            configuration={'columns': {}, 'datasets': []}
        )
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Mock the SSE publishing
        with patch('arkumu.importer.utils.progress.send_event') as mock_send_event:
            # Mock the processor to fail
            with patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor') as mock_processor_class:
                mock_processor = MagicMock()
                mock_processor.process_with_execution_config.side_effect = Exception("Test error")
                mock_processor_class.return_value = mock_processor
                
                # Execute the import task (should raise exception)
                with pytest.raises(Exception):
                    run_import(session.pk)
                
                # Verify SSE events were sent (start and error)
                assert mock_send_event.call_count >= 2
                
                # Verify session was updated with error
                session.refresh_from_db()
                assert session.status == 'failed'
                assert 'Test error' in session.error_message

    def test_middleware_integration_with_real_session(self):
        """Test middleware integration with real session data."""
        from django.test import RequestFactory
        
        # Create test data
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
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Test middleware with valid session
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        channel = create_channel_id(session.pk)
        request = factory.get('/events/stream/', {'channel': channel})
        request.user = user
        
        response = middleware(request)
        assert response is None  # Should pass through

    def test_progress_publishing_with_real_events(self):
        """Test progress publishing with realistic event data."""
        # Create test data
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        organization = Organization.objects.create(
            name='Test Organization',
            slug='test-org'
        )
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        with patch('arkumu.importer.utils.progress.send_event') as mock_send_event:
            # Test different types of progress events
            events = [
                ({'message': 'Starting import...', 'percentage': 0}, 'start'),
                ({'message': 'Processing entities...', 'percentage': 25}, 'progress'),
                ({'message': 'Creating relationships...', 'percentage': 50}, 'progress'),
                ({'message': 'Finalizing...', 'percentage': 90}, 'progress'),
                ({'message': 'Complete!', 'percentage': 100}, 'complete'),
            ]
            
            for payload, event_type in events:
                publish_progress(channel, payload, event=event_type)
            
            # Verify all events were sent
            expected_calls = [
                call(channel, event_type, payload) for payload, event_type in events
            ]
            mock_send_event.assert_has_calls(expected_calls)


class TestSSESystemResilience(TestCase):
    """Test SSE system resilience and error handling."""

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
        
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization=self.organization,
            configuration={'columns': {}}
        )

    @patch('arkumu.importer.utils.progress.send_event')
    def test_progress_publishing_handles_sse_failure(self, mock_send_event):
        """Test that progress publishing handles SSE failures gracefully."""
        # Mock SSE failure
        mock_send_event.side_effect = Exception("Redis connection failed")
        
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Should not raise exception
        try:
            publish_progress(channel, {'message': 'test'})
        except Exception as e:
            self.fail(f"publish_progress should handle SSE failures gracefully: {e}")

    @patch('arkumu.importer.utils.progress.send_event')
    def test_import_task_continues_despite_sse_failure(self, mock_send_event):
        """Test that import task continues even if SSE fails."""
        # Mock SSE failure
        mock_send_event.side_effect = Exception("Redis connection failed")
        
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        # Mock successful processing
        with patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor.process_with_execution_config.return_value = MagicMock(
                rows_processed=100,
                resources_created=50,
                triples_created=200,
                errors=0
            )
            mock_processor_class.return_value = mock_processor
            
            # Execute the import task (should complete despite SSE failure)
            run_import(session.pk)
            
            # Verify session was still updated
            session.refresh_from_db()
            self.assertEqual(session.status, 'completed')

    def test_middleware_handles_malformed_requests(self):
        """Test that middleware handles malformed requests gracefully."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        # Test with malformed channel
        request = factory.get('/events/stream/', {'channel': 'import-malformed-uuid-test'})
        request.user = self.user
        
        response = middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Invalid channel', response.content.decode())

    def test_concurrent_import_sessions(self):
        """Test handling of concurrent import sessions."""
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = IngestSession.objects.create(
                user=self.user,
                organization=self.organization,
                dataset_name=f'dataset_{i}',
                mapping=self.mapping,
                status='pending'
            )
            sessions.append(session)
        
        # Test channel ID generation for each
        channels = [create_channel_id(session.pk) for session in sessions]
        
        # Should be unique
        self.assertEqual(len(channels), len(set(channels)))
        
        # Should follow expected format
        for i, channel in enumerate(channels):
            self.assertEqual(channel, f'import-{sessions[i].pk}')


class TestSSESystemPerformance(TestCase):
    """Test SSE system performance characteristics."""

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
        
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization=self.organization,
            configuration={'columns': {}}
        )

    @patch('arkumu.importer.utils.progress.send_event')
    def test_high_frequency_progress_updates(self, mock_send_event):
        """Test system handles high-frequency progress updates."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Send many progress updates rapidly
        for i in range(100):
            publish_progress(channel, {
                'message': f'Processing record {i}',
                'percentage': i,
                'current_record': i
            })
        
        # Verify all updates were sent
        self.assertEqual(mock_send_event.call_count, 100)

    def test_large_payload_handling(self):
        """Test handling of large payloads in progress updates."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Create large payload
        large_payload = {
            'message': 'Processing large dataset',
            'percentage': 50,
            'metadata': {
                'errors': [f'Error {i}' for i in range(100)],
                'warnings': [f'Warning {i}' for i in range(100)],
                'processed_entities': [f'Entity {i}' for i in range(100)]
            }
        }
        
        with patch('arkumu.importer.utils.progress.send_event') as mock_send_event:
            # Should handle large payload without issues
            publish_progress(channel, large_payload)
            mock_send_event.assert_called_once_with(channel, 'progress', large_payload)


@pytest.mark.django_db
class TestSSESystemEdgeCases:
    """Test edge cases in SSE system."""

    def test_session_deletion_during_import(self):
        """Test behavior when session is deleted during import."""
        # Create test data
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
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        session_pk = session.pk
        
        # Delete session before import
        session.delete()
        
        # Import should raise DoesNotExist
        with pytest.raises(IngestSession.DoesNotExist):
            run_import(session_pk)

    def test_user_deletion_during_import(self):
        """Test behavior when user is deleted during import."""
        # Create test data
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
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Delete user (should cascade to session due to FK)
        user.delete()
        
        # Session should no longer exist
        with pytest.raises(IngestSession.DoesNotExist):
            run_import(session.pk)

    def test_mapping_deletion_during_import(self):
        """Test behavior when mapping is deleted during import."""
        # Create test data
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
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Delete mapping (should cascade to session due to FK)
        mapping.delete()
        
        # Session should no longer exist
        with pytest.raises(IngestSession.DoesNotExist):
            run_import(session.pk)