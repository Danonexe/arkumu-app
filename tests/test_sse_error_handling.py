"""
Tests for SSE error handling and edge cases.

These tests ensure that the SSE implementation handles various error
conditions gracefully and doesn't break the overall import process.
"""

import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from arkumu.importer.models import IngestSession
from arkumu.importer.utils.progress import publish_progress, create_channel_id
from arkumu.importer.tasks.tasks import run_import
from arkumu.importer.middleware import SSEAuthMiddleware
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping

User = get_user_model()


class TestSSEErrorHandling(TestCase):
    """Test SSE error handling scenarios."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )
        
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization_id=self.organization.code,
            mapping_config={'columns': {}, 'datasets': []}
        )

    @patch('django_eventstream.send_event')
    def test_redis_connection_failure(self, mock_send_event):
        """Test handling of Redis connection failures."""
        # Mock Redis connection failure
        mock_send_event.side_effect = ConnectionError("Redis connection failed")
        
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
            self.fail(f"publish_progress should handle Redis failures gracefully: {e}")

    @patch('django_eventstream.send_event')
    def test_eventstream_import_error(self, mock_send_event):
        """Test handling of django-eventstream import errors."""
        # Mock import error
        mock_send_event.side_effect = ImportError("django-eventstream not available")
        
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
            self.fail(f"publish_progress should handle import errors gracefully: {e}")

    @patch('django_eventstream.send_event')
    def test_json_serialization_error(self, mock_send_event):
        """Test handling of JSON serialization errors."""
        # Mock JSON serialization error
        mock_send_event.side_effect = TypeError("Object is not JSON serializable")
        
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
            self.fail(f"publish_progress should handle serialization errors gracefully: {e}")

    @patch('django_eventstream.send_event')
    def test_task_execution_with_sse_errors(self, mock_send_event):
        """Test that task execution continues despite SSE errors."""
        # Mock SSE error
        mock_send_event.side_effect = Exception("SSE publishing failed")
        
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
            
            # Execute the import task (should complete despite SSE errors)
            run_import(session.pk)
            
            # Verify session was still updated
            session.refresh_from_db()
            self.assertEqual(session.status, 'completed')

    def test_invalid_payload_types(self):
        """Test handling of invalid payload types."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        with patch('django_eventstream.send_event') as mock_send_event:
            # Test with various payload types
            invalid_payloads = [
                None,  # None type
                "string",  # String instead of dict
                123,  # Integer instead of dict
                [],  # List instead of dict
            ]
            
            for payload in invalid_payloads:
                try:
                    publish_progress(channel, payload)
                except Exception as e:
                    self.fail(f"publish_progress should handle invalid payload types gracefully: {e}")

    def test_extremely_large_payloads(self):
        """Test handling of extremely large payloads."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Create extremely large payload
        large_data = 'x' * 1000000  # 1MB of data
        large_payload = {
            'message': 'Processing...',
            'percentage': 50,
            'large_data': large_data
        }
        
        with patch('django_eventstream.send_event') as mock_send_event:
            try:
                publish_progress(channel, large_payload)
            except Exception as e:
                self.fail(f"publish_progress should handle large payloads gracefully: {e}")

    def test_unicode_handling_in_payloads(self):
        """Test handling of Unicode characters in payloads."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Test with various Unicode characters
        unicode_payload = {
            'message': 'Processing entities with émojis 🚀 and åccénts',
            'percentage': 50,
            'entity_name': 'José María González',
            'description': 'Ñandú y colibrí en el jardín'
        }
        
        with patch('django_eventstream.send_event') as mock_send_event:
            try:
                publish_progress(channel, unicode_payload)
                mock_send_event.assert_called_once_with(channel, 'progress', unicode_payload)
            except Exception as e:
                self.fail(f"publish_progress should handle Unicode gracefully: {e}")


class TestSSEMiddlewareErrorHandling(TestCase):
    """Test SSE middleware error handling."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )

    def test_middleware_database_error(self):
        """Test middleware handling of database errors."""
        from django.test import RequestFactory
        from django.db import DatabaseError
        
        factory = RequestFactory()
        
        # Mock database error
        with patch('arkumu.importer.models.IngestSession.objects.get') as mock_get:
            mock_get.side_effect = DatabaseError("Database connection failed")
            
            middleware = SSEAuthMiddleware(lambda request: None)
            request = factory.get('/events/stream/', {'channel': 'import-123'})
            request.user = self.user
            
            response = middleware(request)
            
            # Should return forbidden response
            self.assertEqual(response.status_code, 403)
            self.assertIn('Access denied', response.content.decode())

    def test_middleware_user_attribute_error(self):
        """Test middleware handling when request.user is None."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        request = factory.get('/events/stream/', {'channel': 'import-123'})
        request.user = None  # Simulate missing user attribute
        
        response = middleware(request)
        
        # Should return forbidden response
        self.assertEqual(response.status_code, 403)

    def test_middleware_malformed_channel_formats(self):
        """Test middleware with various malformed channel formats."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        middleware = SSEAuthMiddleware(lambda request: None)
        
        malformed_channels = [
            'import-',  # Empty ID
            'import-abc-def',  # Multiple dashes
            'import-!@#$%',  # Special characters
            'import-' + 'x' * 1000,  # Extremely long ID
            'import-0.5',  # Decimal number
            'import-null',  # String 'null'
            'import-undefined',  # String 'undefined'
        ]
        
        for channel in malformed_channels:
            request = factory.get('/events/stream/', {'channel': channel})
            request.user = self.user
            
            response = middleware(request)
            
            # Should return forbidden response for all malformed formats
            self.assertEqual(response.status_code, 403)


class TestSSETaskErrorHandling(TestCase):
    """Test SSE task error handling."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )
        
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization_id=self.organization.code,
            mapping_config={'columns': {}}
        )

    def test_task_session_does_not_exist(self):
        """Test task behavior when session doesn't exist."""
        # Try to run task with non-existent session
        with self.assertRaises(IngestSession.DoesNotExist):
            run_import(999999)

    def test_task_processor_import_error(self):
        """Test task behavior when processor import fails."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        # Mock processor import error
        with patch('arkumu.importer.tasks.tasks.MappingAwareProcessor') as mock_processor_class:
            mock_processor_class.side_effect = ImportError("Processor module not found")
            
            with self.assertRaises(ImportError):
                run_import(session.pk)
            
            # Verify session was marked as failed
            session.refresh_from_db()
            self.assertEqual(session.status, 'failed')

    def test_task_config_translation_error(self):
        """Test task behavior when config translation fails."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        # Mock config translator error
        with patch('arkumu.importer.tasks.tasks.ConfigTranslator') as mock_translator_class:
            mock_translator = MagicMock()
            mock_translator.translate_mapping_to_execution_config.side_effect = ValueError("Invalid mapping configuration")
            mock_translator_class.return_value = mock_translator
            
            with self.assertRaises(ValueError):
                run_import(session.pk)
            
            # Verify session was marked as failed
            session.refresh_from_db()
            self.assertEqual(session.status, 'failed')

    def test_task_statistics_error(self):
        """Test task behavior when statistics creation fails."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        # Mock statistics error
        with patch('arkumu.importer.tasks.tasks.ExecutionStatistics') as mock_stats_class:
            mock_stats_class.side_effect = RuntimeError("Statistics initialization failed")
            
            with self.assertRaises(RuntimeError):
                run_import(session.pk)
            
            # Verify session was marked as failed
            session.refresh_from_db()
            self.assertEqual(session.status, 'failed')

    @patch('django_eventstream.send_event')
    def test_task_partial_processing_error(self, mock_send_event):
        """Test task behavior when processing partially fails."""
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending'
        )
        
        # Mock processor that fails after partial processing
        with patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor') as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor.process_with_execution_config.side_effect = Exception("Processing failed midway")
            mock_processor_class.return_value = mock_processor
            
            with self.assertRaises(Exception):
                run_import(session.pk)
            
            # Verify session was marked as failed
            session.refresh_from_db()
            self.assertEqual(session.status, 'failed')
            self.assertIn('Processing failed midway', session.error_message)


@pytest.mark.django_db
class TestSSESystemRecovery:
    """Test SSE system recovery scenarios."""

    def test_recovery_after_redis_reconnection(self):
        """Test system recovery after Redis reconnection."""
        # Create test data
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=user,
            organization_id=organization.code,
            mapping_config={'columns': {}}
        )
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        channel = create_channel_id(session.pk)
        
        # Mock Redis failure followed by success
        with patch('django_eventstream.send_event') as mock_send_event:
            # First call fails, second succeeds
            mock_send_event.side_effect = [
                ConnectionError("Redis connection failed"),
                None  # Success
            ]
            
            # First call should fail silently
            publish_progress(channel, {'message': 'test1'})
            
            # Second call should succeed
            publish_progress(channel, {'message': 'test2'})
            
            # Verify both calls were attempted
            assert mock_send_event.call_count == 2

    def test_graceful_degradation_without_sse(self):
        """Test system works without SSE functionality."""
        # Create test data
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=user,
            organization_id=organization.code,
            mapping_config={'columns': {}}
        )
        
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Mock complete SSE failure
        with patch('django_eventstream.send_event') as mock_send_event:
            mock_send_event.side_effect = Exception("SSE completely unavailable")
            
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
                
                # Execute the import task (should complete despite SSE failures)
                run_import(session.pk)
                
                # Verify session was still updated
                session.refresh_from_db()
                assert session.status == 'completed'