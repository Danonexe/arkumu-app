import json
import pytest
from unittest.mock import Mock, patch
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from arkumu.users.models import Organization
from arkumu.importer.views.ingest_views import list_importable_mappings, import_selected_mappings

User = get_user_model()


@pytest.mark.django_db
class TestMappingImportViews(TestCase):
    """Test cases for mapping import views."""
    
    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.organization = Organization.objects.create(
            name='Test Organization',
            code='test_org'
        )
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.MappingImportService')
    def test_list_importable_mappings_success(self, mock_service_class):
        """Test successful listing of importable mappings."""
        # Mock service and response
        mock_service = Mock()
        mock_service.list_available_mapping_files.return_value = [
            {
                'key': 'test_org/metadata/mapping1.json',
                'name': 'mapping1.json',
                'size': 1024,
                'last_modified': '2025-07-12T10:30:00Z',
                'display_name': 'Mapping 1'
            }
        ]
        mock_service_class.return_value = mock_service
        
        # Create request with session
        request = self.factory.get('/mappings/list-importable/')
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = {
                'id': self.organization.id,
                'code': self.organization.code,
                'name': self.organization.name
            }
            mock_view_class.return_value = mock_view
            
            response = list_importable_mappings(request)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'mapping1.json')
        
        # Verify service was called correctly
        mock_service.list_available_mapping_files.assert_called_once_with('test_org')
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.MappingImportService')
    def test_list_importable_mappings_no_organization(self, mock_service_class):
        """Test listing when no organization is selected."""
        request = self.factory.get('/mappings/list-importable/')
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization to return None
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = None
            mock_view_class.return_value = mock_view
            
            response = list_importable_mappings(request)
        
        # Verify response contains error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No organization selected')
    
    def test_list_importable_mappings_wrong_method(self):
        """Test list endpoint with wrong HTTP method."""
        request = self.factory.post('/mappings/list-importable/')
        request.user = self.user
        
        response = list_importable_mappings(request)
        
        self.assertEqual(response.status_code, 405)
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.MappingImportService')
    def test_import_selected_mappings_success(self, mock_service_class):
        """Test successful mapping import."""
        # Mock service and response
        mock_service = Mock()
        mock_service.batch_import_mappings.return_value = {
            'total_files': 1,
            'successful_imports': [
                {
                    'file': 'test_org/metadata/mapping1.json',
                    'mapping_name': 'Test Mapping',
                    'mapping_id': 'uuid-123'
                }
            ],
            'failed_imports': [],
            'imported_mappings': []
        }
        mock_service_class.return_value = mock_service
        
        # Create request with form data
        request = self.factory.post('/mappings/import/', {
            'selected_files': ['test_org/metadata/mapping1.json']
        })
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = {
                'id': self.organization.id,
                'code': self.organization.code,
                'name': self.organization.name
            }
            mock_view_class.return_value = mock_view
            
            response = import_selected_mappings(request)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.content)
        
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['imported_count'], 1)
        self.assertEqual(response_data['failed_count'], 0)
        self.assertIn('Test Mapping', response_data['message'])
        
        # Verify service was called correctly
        mock_service.batch_import_mappings.assert_called_once_with(
            file_keys=['test_org/metadata/mapping1.json'],
            organization_id='test_org',
            created_by=self.user
        )
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.MappingImportService')
    def test_import_selected_mappings_no_files(self, mock_service_class):
        """Test import with no files selected."""
        request = self.factory.post('/mappings/import/', {})
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = {
                'id': self.organization.id,
                'code': self.organization.code,
                'name': self.organization.name
            }
            mock_view_class.return_value = mock_view
            
            response = import_selected_mappings(request)
        
        # Verify error response
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        
        self.assertFalse(response_data['success'])
        self.assertIn('No files selected', response_data['error'])
    
    def test_import_selected_mappings_no_organization(self):
        """Test import when no organization is selected."""
        request = self.factory.post('/mappings/import/', {
            'selected_files': ['test_org/metadata/mapping1.json']
        })
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization to return None
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = None
            mock_view_class.return_value = mock_view
            
            response = import_selected_mappings(request)
        
        # Verify error response
        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.content)
        
        self.assertFalse(response_data['success'])
        self.assertIn('No organization selected', response_data['error'])
    
    def test_import_selected_mappings_wrong_method(self):
        """Test import endpoint with wrong HTTP method."""
        request = self.factory.get('/mappings/import/')
        request.user = self.user
        
        response = import_selected_mappings(request)
        
        self.assertEqual(response.status_code, 405)
    
    @patch('arkumu.metadata.services.mapping.mapping_import_service.MappingImportService')
    def test_import_selected_mappings_service_error(self, mock_service_class):
        """Test import with service error."""
        # Mock service to raise exception
        mock_service = Mock()
        mock_service.batch_import_mappings.side_effect = Exception("S3 connection failed")
        mock_service_class.return_value = mock_service
        
        request = self.factory.post('/mappings/import/', {
            'selected_files': ['test_org/metadata/mapping1.json']
        })
        request.user = self.user
        request.session = {}
        
        # Mock IngestDataView.get_current_organization
        with patch('arkumu.importer.views.ingest_views.IngestDataView') as mock_view_class:
            mock_view = Mock()
            mock_view.get_current_organization.return_value = {
                'id': self.organization.id,
                'code': self.organization.code,
                'name': self.organization.name
            }
            mock_view_class.return_value = mock_view
            
            response = import_selected_mappings(request)
        
        # Verify error response
        self.assertEqual(response.status_code, 500)
        response_data = json.loads(response.content)
        
        self.assertFalse(response_data['success'])
        self.assertIn('S3 connection failed', response_data['error'])