"""
Tests for Huey ingest tasks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from django.core.cache import cache
from django.test import override_settings
import tempfile
import os
from datetime import datetime

from arkumu.importer.tasks.import_metadata import (
    run_csv_import_workflow,
    run_csv_directory_import_workflow
)
from arkumu.importer.models.ingest_sessions import IngestSession
from arkumu.users.models import Organization, User


@pytest.fixture
def test_user():
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass'
    )


@pytest.fixture
def test_organization():
    """Create a test organization."""
    return Organization.objects.create(
        name='Test Organization',
        code='test-org'
    )


@pytest.fixture
def mock_ingest_session():
    """Create a mock IngestSession."""
    session = Mock(spec=IngestSession)
    session.id = 123
    session.status = 'in_progress'
    session.progress = 0
    session.task_id = 'test-task-id'
    session.save = Mock()
    return session


@pytest.fixture
def mock_s3_file_content():
    """Mock CSV file content for S3 downloads."""
    return b"name,age,city\nAlice,25,NYC\nBob,30,LA\nCharlie,35,Chicago"


@pytest.fixture
def mock_import_workflow_service():
    """Mock ImportWorkflowService for testing."""
    mock_service = Mock()
    mock_result = Mock()
    mock_result.execution_statistics = Mock()
    mock_result.execution_statistics.current_metrics = Mock()
    mock_result.execution_statistics.current_metrics.resources_created = 3
    mock_result.execution_statistics.current_metrics.triples_created = 9
    mock_result.execution_statistics.current_metrics.rows_processed = 3
    mock_result.execution_statistics.current_metrics.cells_processed = 9
    mock_service.run_import_workflow.return_value = mock_result
    return mock_service


@pytest.fixture
def mock_bucket_service():
    """Mock BucketService with S3 client."""
    mock_service = Mock()
    mock_s3_client = Mock()
    mock_service.base_s3_service = Mock()
    mock_service.base_s3_service.s3_client = mock_s3_client
    return mock_service


class TestRunCSVImportWorkflow:
    """Test the main CSV import workflow task."""
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    @patch('arkumu.importer.tasks.import_metadata.cache')
    def test_csv_import_workflow_success(self, mock_cache, mock_bucket_service_class, 
                                        mock_workflow_service_class, test_organization,
                                        mock_import_workflow_service, mock_bucket_service):
        """Test successful CSV import workflow execution."""
        # Setup mocks
        # Mock workflow service to return stats in expected format
        mock_workflow_service_class.import_csv.return_value = {
            "stats": {
                "rows_processed": 3,
                "cells_processed": 9,
                "resources_created": 3,
                "triples_created": 9,
                "errors": 0
            }
        }
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly (not as async task)
            # Access the underlying function to bypass Huey task wrapper
            from arkumu.importer.tasks.import_metadata import run_csv_import_workflow
            
            # Call the task function directly to get the result dict
            result = run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify result
            assert result['status'] == 'success'
            assert 'resources_created' in result
            assert 'triples_created' in result
            assert 'rows_processed' in result
            assert 'cells_processed' in result
            
            # Verify S3 download was called
            mock_bucket_service.base_s3_service.s3_client.download_file.assert_called_once()
            
            # Verify workflow service was called
            mock_workflow_service_class.import_csv.assert_called_once()
            
            # Verify session was updated
            assert mock_session.save.called
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    @patch('arkumu.importer.tasks.import_metadata.cache')
    def test_csv_import_workflow_s3_error(self, mock_cache, mock_bucket_service_class, 
                                         mock_workflow_service_class, test_organization,
                                         mock_bucket_service):
        """Test CSV import workflow handles S3 download errors."""
        # Mock S3 error
        mock_bucket_service_class.return_value = mock_bucket_service
        mock_bucket_service.base_s3_service.s3_client.download_file.side_effect = Exception("S3 download failed")
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            from arkumu.importer.tasks.import_metadata import run_csv_import_workflow as task_func
            
            result = run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify error result
            assert result['status'] == 'error'
            assert 'S3 download failed' in result['error_message']
            
            # Verify session status was updated to failed
            assert mock_session.status == 'failed'
            assert mock_session.save.called
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    @patch('arkumu.importer.tasks.import_metadata.cache')
    def test_csv_import_workflow_processing_error(self, mock_cache, mock_bucket_service_class, 
                                                 mock_workflow_service_class, test_organization,
                                                 mock_bucket_service):
        """Test CSV import workflow handles processing errors."""
        # Setup S3 mocks
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock workflow service to raise error during CSV import
        mock_workflow_service_class.import_csv.side_effect = Exception("Processing failed")
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            from arkumu.importer.tasks.import_metadata import run_csv_import_workflow as task_func
            
            result = run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify error result
            assert result['status'] == 'error'
            assert 'Processing failed' in result['error_message']
            
            # Verify session status was updated to failed
            assert mock_session.status == 'failed'
            assert mock_session.save.called
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    @patch('arkumu.importer.tasks.import_metadata.cache')
    def test_csv_import_workflow_with_mapping(self, mock_cache, mock_bucket_service_class, 
                                             mock_workflow_service_class, test_organization,
                                             mock_import_workflow_service, mock_bucket_service):
        """Test CSV import workflow with mapping configuration."""
        # Setup mocks
        mock_workflow_service_class.return_value = mock_import_workflow_service
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task with mapping
            result = run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
                mapping_id=456,
                use_mapping=True
            )
            
            # Verify result
            assert result['status'] == 'success'
            
            # Verify ImportWorkflowService.import_csv was called
            # Since mapping loading failed, it should use standard import_csv method
            mock_workflow_service_class.import_csv.assert_called_once()
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_csv_import_workflow_progress_tracking(self, mock_bucket_service_class, 
                                                  mock_workflow_service_class, test_organization):
        """Test that progress is properly tracked during import."""
        cache_key = 'test-progress-key'
        
        # Clear cache before test
        cache.delete(cache_key)
        
        # Setup mocks
        mock_workflow_service_class.import_csv.return_value = {
            "stats": {
                "resources_created": 5,
                "triples_created": 15,
                "rows_processed": 5,
                "cells_processed": 15,
                "errors": 0
            }
        }
        
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache=cache_key,
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Check that progress was tracked in cache
            # The task uses 'task_status_{task_id}' format, so check that key
            from django.core.cache import cache as django_cache
            actual_cache_key = f"task_status_{cache_key}"
            final_status = django_cache.get(actual_cache_key)
            assert final_status is not None
            assert final_status['status'] == 'completed'
            assert final_status['progress'] == 100


class TestRunCSVDirectoryImportWorkflow:
    """Test the directory import workflow task."""
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_directory_import_workflow_success(self, mock_bucket_service_class, mock_workflow_service_class,
                                              test_organization):
        """Test successful directory import workflow execution."""
        # Mock BucketService
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock S3 list_objects_v2 response
        mock_bucket_service.base_s3_service.s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'data/file1.csv', 'Size': 1024},
                {'Key': 'data/file2.csv', 'Size': 2048},
                {'Key': 'data/readme.txt', 'Size': 512}  # Should be ignored
            ]
        }
        
        # Mock ImportWorkflowService.import_csv_directory
        mock_workflow_service_class.import_csv_directory.return_value = {
            "files_processed": 2,
            "resources_created": 10,
            "triples_created": 30,
            "errors": 0
        }
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            from arkumu.importer.tasks.import_metadata import run_csv_directory_import_workflow
            
            result = run_csv_directory_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_folder_prefix='data/',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify result
            assert result['status'] == 'success'
            assert result['csv_files_found'] == 2  # Only CSV files found
            assert result['csv_files_downloaded'] == 2  # CSV files downloaded
            
            # Directory import doesn't directly call CSV import tasks
            # It uses ImportWorkflowService.import_csv_directory instead
            
            # Verify S3 was queried correctly
            mock_bucket_service.base_s3_service.s3_client.list_objects_v2.assert_called_once_with(
                Bucket='test-bucket',
                Prefix='data/'
            )
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_directory_import_workflow_s3_error(self, mock_bucket_service_class, test_organization):
        """Test directory import workflow handles S3 listing errors."""
        # Mock S3 error
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        mock_bucket_service.base_s3_service.s3_client.list_objects_v2.side_effect = Exception("S3 listing failed")
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            from arkumu.importer.tasks.import_metadata import run_csv_directory_import_workflow
            
            result = run_csv_directory_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_folder_prefix='data/',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify error result
            assert result['status'] == 'error'
            assert 'S3 listing failed' in result['error_message']
            
            # Verify session status was updated
            assert mock_session.status == 'failed'
            assert mock_session.save.called
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_directory_import_workflow_no_csv_files(self, mock_bucket_service_class, mock_workflow_service_class,
                                                   test_organization):
        """Test directory import workflow when no CSV files found."""
        # Mock BucketService
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock S3 response with no CSV files
        mock_bucket_service.base_s3_service.s3_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'data/readme.txt', 'Size': 512},
                {'Key': 'data/config.json', 'Size': 256}
            ]
        }
        
        # Mock ImportWorkflowService for no CSV scenario
        mock_workflow_service_class.import_csv_directory.return_value = {
            "files_processed": 0,
            "resources_created": 0,
            "triples_created": 0,
            "errors": 0
        }
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly
            from arkumu.importer.tasks.import_metadata import run_csv_directory_import_workflow
            
            result = run_csv_directory_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_folder_prefix='data/',
                dataset_name='test_dataset',
                task_id_for_cache='test-cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify result - should fail when no CSV files found
            assert result['status'] == 'error'
            assert 'No CSV files found' in result['error_message']


class TestTaskIntegration:
    """Integration tests for task workflows."""
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_task_cache_integration(self, mock_bucket_service_class, mock_workflow_service_class, 
                                   test_organization):
        """Test that tasks properly integrate with Django cache for progress tracking."""
        cache_key = 'integration-test-key'
        
        # Clear cache
        cache.delete(cache_key)
        
        # Setup mocks
        mock_workflow_service_class.import_csv.return_value = {
            "stats": {
                "resources_created": 1,
                "triples_created": 3,
                "rows_processed": 1,
                "cells_processed": 3,
                "errors": 0
            }
        }
        
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock IngestSession
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly to ensure cache is updated
            run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache=cache_key,
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com',
            )
            
            # Verify cache was updated
            from django.core.cache import cache as django_cache
            actual_cache_key = f"task_status_{cache_key}"
            cached_status = django_cache.get(actual_cache_key)
            assert cached_status is not None
            assert cached_status['status'] == 'completed'
            assert cached_status['progress'] == 100
    
    @pytest.mark.django_db
    @patch('arkumu.importer.tasks.import_metadata.ImportWorkflowService')
    @patch('arkumu.importer.tasks.import_metadata.BucketService')
    def test_ingest_session_integration(self, mock_bucket_service_class, mock_workflow_service_class, 
                                       test_organization, test_user):
        """Test that tasks properly update IngestSession models."""
        # Setup mocks - mock the class method import_csv
        mock_workflow_service_class.import_csv.return_value = {
            "stats": {
                "resources_created": 5,
                "triples_created": 15,
                "rows_processed": 10,
                "cells_processed": 20,
                "errors": 0
            }
        }
        
        mock_bucket_service = Mock()
        mock_bucket_service_class.return_value = mock_bucket_service
        
        # Mock IngestSession to avoid database connection issues in task execution
        with patch('arkumu.importer.tasks.import_metadata.IngestSession') as mock_session_class:
            mock_session = Mock()
            mock_session_class.objects.get.return_value = mock_session
            
            # Execute task directly (not as async Huey task)
            result = run_csv_import_workflow.func(
                s3_bucket_name='test-bucket',
                s3_object_key='data/test.csv',
                dataset_name='test_dataset',
                task_id_for_cache='cache-key',
                upload_session_id=123,
                institution='test-institution',
                base_uri='http://test.example.com'
            )
            
            # Verify task completed successfully
            assert result['status'] == 'success'
            assert result['resources_created'] == 5
            assert result['triples_created'] == 15
            
            # Verify session was updated
            assert mock_session.save.called
            assert mock_session.status == 'completed'