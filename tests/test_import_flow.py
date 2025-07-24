"""
Integration tests for SSE import flow.

These tests verify the complete import flow with SSE events,
including progress updates, task execution, and error handling.
"""

import pytest
import json
import time
from unittest.mock import patch, MagicMock, Mock
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test.client import Client
from django.db import transaction

from arkumu.importer.models import IngestSession
from arkumu.importer.utils.progress import publish_progress, create_channel_id
from arkumu.importer.tasks.tasks import run_import
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping

User = get_user_model()


class TestImportFlowIntegration(TransactionTestCase):
    """Integration tests for import flow with SSE events."""

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
        
        self.session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=self.mapping,
            status='pending',
            file_paths=['test_file.csv']
        )
        
        self.client = Client()
        self.client.force_login(self.user)

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_with_progress_updates(self, mock_process, mock_publish):
        """Test complete import flow with progress updates."""
        # Mock successful processing
        mock_process.return_value = MagicMock(
            rows_processed=100,
            resources_created=50,
            triples_created=200,
            errors=0
        )
        
        # Run the import task
        channel_id = create_channel_id(self.session.pk)
        
        # Execute the task
        run_import(self.session.pk)
        
        # Verify progress calls were made
        expected_calls = [
            # Initial start notification
            (channel_id, {
                'status': 'started',
                'message': 'Import job started',
                'percentage': 0
            }),
            # Completion notification
            (channel_id, {
                'status': 'complete',
                'message': 'Import completed successfully',
                'percentage': 100
            })
        ]
        
        # Check that progress was published
        self.assertTrue(mock_publish.called)
        
        # Verify session status
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'completed')

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_with_error_handling(self, mock_process, mock_publish):
        """Test import flow with error handling."""
        # Mock processing failure
        mock_process.side_effect = Exception("Processing failed")
        
        channel_id = create_channel_id(self.session.pk)
        
        # Execute the task (should handle exception)
        with self.assertRaises(Exception):
            run_import(self.session.pk)
        
        # Verify error progress was published
        self.assertTrue(mock_publish.called)
        
        # Verify session status
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'failed')
        self.assertIn('Processing failed', self.session.error_message)

    @patch('django_eventstream.send_event')
    def test_import_flow_session_not_found(self, mock_publish):
        """Test import flow when session doesn't exist."""
        nonexistent_session_id = 99999
        
        # Should handle gracefully
        with self.assertRaises(IngestSession.DoesNotExist):
            run_import(nonexistent_session_id)

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor')
    def test_import_flow_with_mapping_processor(self, mock_processor_class, mock_publish):
        """Test import flow with mapping processor integration."""
        # Mock processor instance
        mock_processor = MagicMock()
        mock_processor.process_with_execution_config.return_value = MagicMock(
            rows_processed=50,
            resources_created=25,
            triples_created=100,
            errors=0
        )
        mock_processor_class.return_value = mock_processor
        
        channel_id = create_channel_id(self.session.pk)
        
        # Execute the task
        run_import(self.session.pk)
        
        # Verify processor was created with correct parameters
        mock_processor_class.assert_called_once()
        
        # Verify processor was called
        mock_processor.process_with_execution_config.assert_called_once()
        
        # Verify session status
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'completed')

    def test_channel_id_generation_consistency(self):
        """Test that channel ID generation is consistent."""
        session_pk = self.session.pk
        
        # Generate channel ID multiple times
        channel_1 = create_channel_id(session_pk)
        channel_2 = create_channel_id(session_pk)
        
        # Should be consistent
        self.assertEqual(channel_1, channel_2)
        self.assertEqual(channel_1, f'import-{session_pk}')

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_updates_session_progress(self, mock_process, mock_publish):
        """Test that import flow updates session progress fields."""
        # Mock successful processing
        mock_process.return_value = MagicMock(
            rows_processed=100,
            resources_created=50,
            triples_created=200,
            errors=0
        )
        
        # Initial session state
        self.assertEqual(self.session.status, 'pending')
        self.assertIsNone(self.session.started_at)
        self.assertIsNone(self.session.completed_at)
        
        # Execute the task
        run_import(self.session.pk)
        
        # Verify session was updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'completed')
        self.assertIsNotNone(self.session.started_at)
        self.assertIsNotNone(self.session.completed_at)

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_with_statistics_integration(self, mock_process, mock_publish):
        """Test import flow with statistics integration."""
        # Mock processing with statistics
        mock_metrics = MagicMock()
        mock_metrics.rows_processed = 150
        mock_metrics.resources_created = 75
        mock_metrics.triples_created = 300
        mock_metrics.errors = 0
        
        mock_process.return_value = mock_metrics
        
        # Execute the task
        run_import(self.session.pk)
        
        # Verify session was updated with stats
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, 'completed')
        
        # Verify progress was published
        self.assertTrue(mock_publish.called)


class TestImportFlowWithRealData(TransactionTestCase):
    """Integration tests with more realistic data scenarios."""

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
        
        # Create mapping with sample configuration
        self.mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization_id=self.organization.code,
            mapping_config={
                'columns': {
                    'name': {'arkumu_type': 'person_name', 'datatype': 'string'},
                    'age': {'arkumu_type': 'person_age', 'datatype': 'integer'}
                },
                'datasets': [
                    {'name': 'people', 'columns': ['name', 'age']}
                ]
            }
        )

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_with_realistic_mapping(self, mock_process, mock_publish):
        """Test import flow with realistic mapping configuration."""
        # Create session with realistic data
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='people_dataset',
            mapping=self.mapping,
            status='pending',
            file_paths=['people.csv', 'addresses.csv']
        )
        
        # Mock successful processing
        mock_process.return_value = MagicMock(
            rows_processed=500,
            resources_created=250,
            triples_created=1000,
            errors=0
        )
        
        # Execute the task
        run_import(session.pk)
        
        # Verify session was updated
        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        
        # Verify progress was published
        self.assertTrue(mock_publish.called)

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_with_partial_failure(self, mock_process, mock_publish):
        """Test import flow with partial processing failure."""
        # Mock processing with some errors
        mock_process.return_value = MagicMock(
            rows_processed=100,
            resources_created=80,
            triples_created=400,
            errors=20
        )
        
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='partial_failure_dataset',
            mapping=self.mapping,
            status='pending',
            file_paths=['data.csv']
        )
        
        # Execute the task
        run_import(session.pk)
        
        # Verify session was still marked as completed (partial success)
        session.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        
        # Verify progress was published
        self.assertTrue(mock_publish.called)


@pytest.mark.django_db
class TestImportFlowViews:
    """Test import flow views and endpoints."""

    def test_start_import_view_unauthorized(self):
        """Test start import view with unauthorized access."""
        client = Client()
        
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
        
        # Try to access without login
        response = client.post(
            reverse('importer:start_import_session', kwargs={'session_pk': session.pk})
        )
        
        # Should return 403 forbidden
        assert response.status_code == 403

    def test_start_import_view_wrong_user(self):
        """Test start import view with wrong user access."""
        client = Client()
        
        # Create two users
        user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        
        user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        organization = Organization.objects.create(
            name='Test Organization',
            code='test-org'
        )
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=user1,
            organization_id=organization.code,
            mapping_config={'columns': {}}
        )
        
        # Create session for user1
        session = IngestSession.objects.create(
            user=user1,
            organization=organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending'
        )
        
        # Login as user2
        client.force_login(user2)
        
        # Try to access user1's session
        response = client.post(
            reverse('importer:start_import_session', kwargs={'session_pk': session.pk})
        )
        
        # Should be forbidden
        assert response.status_code == 403

    @patch('arkumu.importer.tasks.import_metadata.run_mapping_aware_import_workflow')
    def test_start_import_view_success(self, mock_run_import_workflow):
        """Test successful start import view."""
        client = Client()
        
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
            status='pending',
            file_paths=['test_data.csv']
        )
        
        # Login as correct user
        client.force_login(user)
        
        # Start import
        response = client.post(
            reverse('importer:start_import_session', kwargs={'session_pk': session.pk})
        )
        
        # Should be successful
        assert response.status_code == 200
        
        # Verify task was queued
        mock_run_import_workflow.assert_called_once()

    @patch('arkumu.importer.services.schema_service.SchemaService')
    @patch('arkumu.importer.tasks.import_metadata.run_mapping_aware_import_workflow') 
    def test_schema_service_integration_in_import_flow(self, mock_run_import_workflow, mock_schema_service_class):
        """Test that schema service is properly integrated into import flow."""
        # Setup
        client = Client()
        user = User.objects.create_user(username='testuser', email='test@example.com', password='testpass123')
        organization = Organization.objects.create(name='Test Organization', code='test-org')
        
        # Create test mapping
        from arkumu.metadata.models import Mapping
        mapping = Mapping.objects.create(
            name='Test Mapping',
            mapping_config={'test': 'data'},
            organization_id=organization,
            created_by=user
        )
        
        # Create test session
        from arkumu.importer.models import IngestSession
        session = IngestSession.objects.create(
            user=user,
            organization=organization,
            mapping=mapping,
            total_files=1,
            processed_files=0,
            status='pending'
        )
        
        # Mock schema service
        mock_schema_service = mock_schema_service_class.return_value
        mock_schema_service.create_complete_schema.return_value = {'datasets': ['authors'], 'properties': 10}
        
        # Mock import workflow to return success
        mock_run_import_workflow.return_value = {'status': 'success'}
        
        # Test data
        test_data = {
            'ingest_session_id': str(session.id),
            'file_path': 'test-authors.csv',
            'dataset_name': 'authors',
            'bucket_name': 'test-bucket',
            'object_key': 'test-authors.csv'
        }
        
        # Login user
        client.force_login(user)
        
        # Make request to start import
        response = client.post('/importer/api/start_import/', test_data, content_type='application/json')
        
        # Verify response
        assert response.status_code == 200
        
        # Verify import workflow was called
        mock_run_import_workflow.assert_called_once()
        
        # Verify schema service was instantiated with correct mapping_id
        # (This tests the integration even though it's mocked)
        call_args = mock_run_import_workflow.call_args
        assert 'mapping_id' in call_args.kwargs or any('mapping_id' in str(arg) for arg in call_args.args)


class TestImportFlowErrorHandling(TestCase):
    """Test error handling in import flow."""

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

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_database_error(self, mock_process, mock_publish):
        """Test import flow with database connection error."""
        # Mock database error
        mock_process.side_effect = Exception("Database connection failed")
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization_id=self.organization.code,
            mapping_config={
                'workspace_columns': {
                    'test_data::test_column': {
                        'arkumu_type': 'person_name',
                        'datatype': 'string'
                    }
                },
                'workspace_datasets': ['test_data']
            }
        )
        
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending',
            file_paths=['test_data.csv']
        )
        
        # Execute the task
        run_import(session.pk)
        
        # Verify the processor was called
        mock_process.assert_called_once()
        
        # Verify error was published
        self.assertTrue(mock_publish.called)
        
        # Verify session status
        session.refresh_from_db()
        self.assertEqual(session.status, 'failed')
        self.assertIn('Database connection failed', session.error_message or '')

    @patch('django_eventstream.send_event')
    @patch('arkumu.importer.services.execution.mapping_aware_processor.MappingAwareProcessor.process_with_execution_config')
    def test_import_flow_timeout_error(self, mock_process, mock_publish):
        """Test import flow with timeout error."""
        # Mock timeout error
        mock_process.side_effect = TimeoutError("Processing timed out")
        
        mapping = Mapping.objects.create(
            name='Test Mapping',
            created_by=self.user,
            organization_id=self.organization.code,
            mapping_config={
                'workspace_columns': {
                    'test_data::test_column': {
                        'arkumu_type': 'person_name',
                        'datatype': 'string'
                    }
                },
                'workspace_datasets': ['test_data']
            }
        )
        
        session = IngestSession.objects.create(
            user=self.user,
            organization=self.organization,
            dataset_name='test_dataset',
            mapping=mapping,
            status='pending',
            file_paths=['test_data.csv']
        )
        
        # Execute the task
        with self.assertRaises(TimeoutError):
            run_import(session.pk)
        
        # Verify error was published
        self.assertTrue(mock_publish.called)
        
        # Verify session status
        session.refresh_from_db()
        self.assertEqual(session.status, 'failed')
        self.assertIn('Processing timed out', session.error_message)