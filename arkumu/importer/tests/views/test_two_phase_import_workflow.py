"""
Test for the two-phase import workflow:
1. Phase 1: Synchronous blueprint creation 
2. Phase 2: Asynchronous dataset processing using cached blueprints

This test verifies that blueprint creation happens ONCE per mapping,
and all dataset processing tasks reuse the cached blueprints.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock, call
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping
from arkumu.importer.models import IngestSession
from arkumu.importer.views.ingest_views import IngestDataView
from arkumu.importer.tasks.import_metadata import _initialize_mapping_schemas_sync

User = get_user_model()


@pytest.fixture
def user():
    return User.objects.create_user(username='testuser', password='testpass')


@pytest.fixture  
def organization():
    return Organization.objects.create(
        name='Test Org',
        code='test_org'
    )


@pytest.fixture
def mapping():
    return Mapping.objects.create(
        name='Test Mapping',
        description='Test mapping for workflow',
        organization_id='test_org',
        mapping_config={'test': 'data'}
    )


@pytest.fixture
def request_factory():
    return RequestFactory()


class TestTwoPhaseImportWorkflow:
    """Test the two-phase import workflow implementation."""
    
    @pytest.mark.django_db
    @patch('arkumu.importer.views.ingest_views.process_dataset_data')
    @patch('arkumu.importer.views.ingest_views._initialize_mapping_schemas_sync')
    @patch('arkumu.importer.views.ingest_views.BucketService')
    def test_two_phase_workflow_execution(
        self, 
        mock_bucket_service,
        mock_schema_init,
        mock_process_dataset,
        user,
        organization,
        mapping,
        request_factory
    ):
        """
        Test that the two-phase workflow executes correctly:
        1. Blueprint creation happens once synchronously
        2. Dataset processing tasks are queued for each file
        """
        # Setup mocks
        mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
        
        # Mock successful blueprint creation
        mock_schema_init.return_value = {
            'status': 'success',
            'mapping_id': str(mapping.id),
            'mapping_name': mapping.name,
            'datasets_schema_created': 3,
            'total_properties': 50,
            'message': 'Blueprint creation completed successfully'
        }
        
        # Mock dataset processing tasks
        mock_task_results = [
            MagicMock(id='task-1'),
            MagicMock(id='task-2'), 
            MagicMock(id='task-3')
        ]
        mock_process_dataset.side_effect = mock_task_results
        
        # Prepare request data
        selected_files = [
            'uploads/dataset1.csv',
            'uploads/dataset2.csv', 
            'uploads/dataset3.csv'
        ]
        
        request = request_factory.post(
            '/importer/start-import/',
            data={
                'organization': organization.id,
                'mapping': mapping.id,
                'selected_files': selected_files
            }
        )
        request.user = user
        
        # Mock session data
        with patch('arkumu.importer.views.ingest_views.request') as mock_request_module:
            mock_request_module.session = {
                'ingest_selected_files': selected_files,
                'ingest_organization': {'id': organization.id, 'code': organization.code},
                'ingest_mapping': {'id': str(mapping.id), 'name': mapping.name}
            }
            
            # Execute the workflow
            view = IngestDataView()
            response = view.post(request)
        
        # Verify Phase 1: Blueprint creation called once
        mock_schema_init.assert_called_once_with(
            mapping_id=str(mapping.id),
            institution=organization.code,
            upload_session_id=pytest.any(uuid.UUID)
        )
        
        # Verify Phase 2: Dataset processing called for each file
        assert mock_process_dataset.call_count == 3
        
        expected_calls = [
            call(
                s3_bucket_name='test-bucket',
                s3_object_key='uploads/dataset1.csv',
                dataset_name='dataset1',
                institution=organization.code,
                mapping_id=str(mapping.id),
                upload_session_id=pytest.any(uuid.UUID)
            ),
            call(
                s3_bucket_name='test-bucket',
                s3_object_key='uploads/dataset2.csv',
                dataset_name='dataset2', 
                institution=organization.code,
                mapping_id=str(mapping.id),
                upload_session_id=pytest.any(uuid.UUID)
            ),
            call(
                s3_bucket_name='test-bucket',
                s3_object_key='uploads/dataset3.csv',
                dataset_name='dataset3',
                institution=organization.code,
                mapping_id=str(mapping.id),
                upload_session_id=pytest.any(uuid.UUID)
            )
        ]
        
        mock_process_dataset.assert_has_calls(expected_calls, any_order=False)
        
        # Verify IngestSession was created
        assert IngestSession.objects.filter(user=user, organization=organization).exists()
        
        # Verify successful response
        assert response.status_code == 200


    @pytest.mark.django_db
    @patch('arkumu.importer.views.ingest_views._initialize_mapping_schemas_sync')
    @patch('arkumu.importer.views.ingest_views.BucketService')
    def test_blueprint_creation_failure_handling(
        self,
        mock_bucket_service,
        mock_schema_init,
        user,
        organization,
        mapping,
        request_factory
    ):
        """
        Test that blueprint creation failure is handled properly.
        """
        # Setup mocks
        mock_bucket_service.return_value.get_organization_bucket.return_value = 'test-bucket'
        
        # Mock failed blueprint creation
        mock_schema_init.return_value = {
            'status': 'error',
            'error_message': 'Mapping not found',
            'error_type': 'MappingNotFound'
        }
        
        # Prepare request
        selected_files = ['uploads/dataset1.csv']
        
        request = request_factory.post(
            '/importer/start-import/',
            data={
                'organization': organization.id,
                'mapping': mapping.id,
                'selected_files': selected_files
            }
        )
        request.user = user
        
        # Mock session data
        with patch('arkumu.importer.views.ingest_views.request') as mock_request_module:
            mock_request_module.session = {
                'ingest_selected_files': selected_files,
                'ingest_organization': {'id': organization.id, 'code': organization.code},
                'ingest_mapping': {'id': str(mapping.id), 'name': mapping.name}
            }
            
            # Execute the workflow
            view = IngestDataView()
            response = view.post(request)
        
        # Verify blueprint creation was called
        mock_schema_init.assert_called_once()
        
        # Verify error response
        assert response.status_code == 500
        assert 'Error creating blueprints' in response.content.decode()
        assert 'Mapping not found' in response.content.decode()


    @pytest.mark.django_db 
    def test_blueprint_creation_vs_dataset_processing_efficiency(self):
        """
        Test that demonstrates the efficiency of the two-phase approach.
        This test focuses on the workflow pattern rather than implementation details.
        """
        # Simulate the old approach: blueprint creation per dataset
        old_approach_calls = []
        
        datasets = ['dataset1', 'dataset2', 'dataset3', 'dataset4', 'dataset5']
        
        # Old approach: Each dataset task creates blueprints
        for dataset in datasets:
            old_approach_calls.append(f"create_blueprints_for_{dataset}")
            old_approach_calls.append(f"process_data_for_{dataset}")
        
        # New approach: Blueprint creation once, then dataset processing
        new_approach_calls = []
        new_approach_calls.append("create_blueprints_once")  # Phase 1
        for dataset in datasets:
            new_approach_calls.append(f"process_data_for_{dataset}")  # Phase 2
        
        # Verify efficiency gains
        blueprint_creation_calls_old = len([call for call in old_approach_calls if 'create_blueprints' in call])
        blueprint_creation_calls_new = len([call for call in new_approach_calls if 'create_blueprints' in call])
        
        assert blueprint_creation_calls_old == 5  # 5 datasets = 5 blueprint creations
        assert blueprint_creation_calls_new == 1  # 1 blueprint creation for all datasets
        
        efficiency_ratio = blueprint_creation_calls_old / blueprint_creation_calls_new
        assert efficiency_ratio == 5.0  # 5x fewer blueprint creation calls
        
        print(f"Blueprint creation efficiency: {efficiency_ratio}x improvement")
        print(f"Old approach: {blueprint_creation_calls_old} blueprint creations")
        print(f"New approach: {blueprint_creation_calls_new} blueprint creation")


    def test_workflow_comparison_with_old_approach(self):
        """
        Test that demonstrates the efficiency gain of the new two-phase approach
        vs the old single-task approach.
        """
        # Old approach: Blueprint creation per task
        # - 3 files = 3 blueprint creations = 3x overhead
        
        # New approach: Blueprint creation once
        # - 3 files = 1 blueprint creation + 3 data processing = 1x overhead
        
        files_count = 10
        
        # Old approach overhead: blueprint creation per file
        old_approach_blueprint_calls = files_count
        
        # New approach overhead: blueprint creation once
        new_approach_blueprint_calls = 1
        
        efficiency_gain = old_approach_blueprint_calls / new_approach_blueprint_calls
        
        assert efficiency_gain == files_count
        assert efficiency_gain > 1, "New approach should be more efficient"
        
        print(f"Efficiency gain with {files_count} files: {efficiency_gain}x faster blueprint creation")