"""
Tests for ingest views
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import RequestFactory, Client
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.urls import reverse
from django.core.exceptions import PermissionDenied

from arkumu.users.models import Organization, User
from arkumu.importer.views.ingest_views import (
    ingest_data,
    get_organization_files_for_ingest
)


@pytest.fixture
def request_factory():
    """Django request factory for creating mock requests."""
    return RequestFactory()


@pytest.fixture
def authenticated_user():
    """Create an authenticated user for testing."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def test_organization():
    """Create a test organization."""
    return Organization.objects.create(
        name='Test Organization',
        code='test-org'
    )


@pytest.fixture
def mock_bucket_service():
    """Mock BucketService for testing."""
    mock_service = Mock()
    mock_service.get_organization_bucket.return_value = 'test-org-bucket'
    return mock_service


@pytest.fixture
def mock_bucket_contents():
    """Mock bucket contents returned by BucketService.list_bucket_contents."""
    return [
        {
            'type': 'file',
            'name': 'test1.csv',
            'path': 'data/test1.csv',
            'size': 1024,
            'size_formatted': '1.0 KB',
            'last_modified': None
        },
        {
            'type': 'file', 
            'name': 'test2.csv',
            'path': 'data/subfolder/test2.csv',
            'size': 2048,
            'size_formatted': '2.0 KB',
            'last_modified': None
        },
        {
            'type': 'file',
            'name': 'readme.txt',
            'path': 'data/readme.txt',
            'size': 512,
            'size_formatted': '512 B',
            'last_modified': None
        },
        {
            'type': 'folder',
            'name': 'subfolder',
            'path': 'data/subfolder/',
            'size': 0,
            'size_formatted': '0 B',
            'last_modified': None
        }
    ]


class TestIngestDataView:
    """Test the main ingest_data view."""
    
    @pytest.mark.django_db
    def test_ingest_data_view_authenticated(self, request_factory, authenticated_user, test_organization):
        """Test ingest_data view with authenticated user."""
        request = request_factory.get('/ingest/')
        request.user = authenticated_user
        
        response = ingest_data(request)
        
        assert response.status_code == 200
        # Check content contains organization name and page title
        content = response.content.decode('utf-8')
        assert test_organization.name in content
        assert 'Data Ingestion Center' in content
    
    @pytest.mark.django_db
    def test_ingest_data_view_unauthenticated(self, request_factory):
        """Test ingest_data view handles unauthenticated users."""
        request = request_factory.get('/ingest/')
        request.user = AnonymousUser()
        
        # Should raise PermissionDenied
        with pytest.raises(PermissionDenied):
            ingest_data(request)
    
    @pytest.mark.django_db
    def test_ingest_data_view_organizations_ordering(self, request_factory, authenticated_user):
        """Test that organizations are ordered by name."""
        # Create multiple organizations
        org_b = Organization.objects.create(name='B Organization', code='b-org')
        org_a = Organization.objects.create(name='A Organization', code='a-org')
        org_c = Organization.objects.create(name='C Organization', code='c-org')
        
        request = request_factory.get('/ingest/')
        request.user = authenticated_user
        
        response = ingest_data(request)
        
        # Check that organizations appear in alphabetical order in content
        content = response.content.decode('utf-8')
        assert org_a.name in content
        assert org_b.name in content
        assert org_c.name in content
        
        # Check order by finding positions
        pos_a = content.find(org_a.name)
        pos_b = content.find(org_b.name)
        pos_c = content.find(org_c.name)
        assert pos_a < pos_b < pos_c


class TestGetOrganizationFilesForIngestView:
    """Test the get_organization_files_for_ingest HTMX endpoint."""
    
    @pytest.mark.django_db
    def test_get_files_no_organization_id(self, request_factory, authenticated_user):
        """Test endpoint returns empty template when no organization ID provided."""
        request = request_factory.get('/ingest/files/')
        request.user = authenticated_user
        
        response = get_organization_files_for_ingest(request)
        
        assert response.status_code == 200
        # Check that it returns the empty template content
        content = response.content.decode('utf-8')
        # The empty template should not contain file lists
        assert 'csv' not in content.lower()
    
    @pytest.mark.django_db
    def test_get_files_invalid_organization_id(self, request_factory, authenticated_user):
        """Test endpoint handles invalid organization ID."""
        request = request_factory.get('/ingest/files/?organization=999')
        request.user = authenticated_user
        
        response = get_organization_files_for_ingest(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Organization not found' in content
    
    @pytest.mark.django_db
    @patch('arkumu.storage.services.bucket_service.BucketService')
    def test_get_files_success(self, mock_bucket_service_class, 
                              request_factory, authenticated_user, test_organization,
                              mock_bucket_service, mock_bucket_contents):
        """Test successful file listing."""
        # Setup mocks
        mock_bucket_service.list_bucket_contents.return_value = mock_bucket_contents
        mock_bucket_service_class.return_value = mock_bucket_service
        
        request = request_factory.get(f'/ingest/files/?organization={test_organization.id}')
        request.user = authenticated_user
        
        response = get_organization_files_for_ingest(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Should contain CSV files in response
        assert 'test1.csv' in content
        assert 'test2.csv' in content
        assert 'readme.txt' not in content  # Non-CSV files filtered out
        
        # Verify services were called correctly
        mock_bucket_service.get_organization_bucket.assert_called_once_with('test-org')
        mock_bucket_service.list_bucket_contents.assert_called_once_with(
            bucket_name='test-org-bucket',
            prefix='data/'
        )
    
    @pytest.mark.django_db
    @patch('arkumu.storage.services.bucket_service.BucketService')
    def test_get_files_filters_csv_only(self, mock_bucket_service_class,
                                       request_factory, authenticated_user, test_organization,
                                       mock_bucket_service, mock_bucket_contents):
        """Test that only CSV files are included in results."""
        # Setup mocks
        mock_bucket_service.list_bucket_contents.return_value = mock_bucket_contents
        mock_bucket_service_class.return_value = mock_bucket_service
        
        request = request_factory.get(f'/ingest/files/?organization={test_organization.id}')
        request.user = authenticated_user
        
        response = get_organization_files_for_ingest(request)
        
        content = response.content.decode('utf-8')
        
        # Should only include CSV files, not the txt file
        assert 'test1.csv' in content
        assert 'test2.csv' in content
        assert 'readme.txt' not in content
    
    @pytest.mark.django_db
    @patch('arkumu.storage.services.bucket_service.BucketService')
    def test_get_files_builds_tree_structure(self, mock_bucket_service_class,
                                            request_factory, authenticated_user, test_organization,
                                            mock_bucket_service, mock_bucket_contents):
        """Test that files are organized into proper tree structure."""
        # Setup mocks
        mock_bucket_service.list_bucket_contents.return_value = mock_bucket_contents
        mock_bucket_service_class.return_value = mock_bucket_service
        
        request = request_factory.get(f'/ingest/files/?organization={test_organization.id}')
        request.user = authenticated_user
        
        response = get_organization_files_for_ingest(request)
        
        content = response.content.decode('utf-8')
        
        # Should contain both files organized in tree structure
        assert 'test1.csv' in content  # Root level file
        assert 'test2.csv' in content  # Subfolder file
        assert 'subfolder' in content  # Subfolder should be mentioned
    
    @pytest.mark.django_db
    @patch('arkumu.storage.services.bucket_service.BucketService')
    def test_get_files_service_exception(self, mock_bucket_service_class,
                                        request_factory, authenticated_user, test_organization,
                                        mock_bucket_service):
        """Test handling of service exceptions."""
        # Setup mocks to raise exception
        mock_bucket_service.list_bucket_contents.side_effect = Exception("Storage service error")
        mock_bucket_service_class.return_value = mock_bucket_service
        
        request = request_factory.get(f'/ingest/files/?organization={test_organization.id}')
        request.user = authenticated_user
        
        with patch('arkumu.importer.views.ingest_views.logger') as mock_logger:
            response = get_organization_files_for_ingest(request)
            
            assert response.status_code == 200
            content = response.content.decode('utf-8')
            assert 'Storage service error' in content
            
            # Verify error was logged
            mock_logger.error.assert_called_once()
    
    @pytest.mark.django_db
    def test_get_files_unauthenticated(self, request_factory, test_organization):
        """Test endpoint handles unauthenticated users."""
        request = request_factory.get(f'/ingest/files/?organization={test_organization.id}')
        request.user = AnonymousUser()
        
        # Should raise PermissionDenied
        with pytest.raises(PermissionDenied):
            get_organization_files_for_ingest(request)


class TestIngestViewsIntegration:
    """Integration tests for ingest views."""
    
    @pytest.mark.django_db
    def test_view_functionality_directly(self, authenticated_user, test_organization):
        """Test views work correctly when called directly."""
        # Mock the views directly since URLs may not be configured in tests
        factory = RequestFactory()
        
        # Test main ingest view
        request = factory.get('/ingest/')
        request.user = authenticated_user
        response = ingest_data(request)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert test_organization.name in content
        
        # Test HTMX file listing (mocked)
        with patch('arkumu.storage.services.bucket_service.BucketService') as mock_bucket:
            
            mock_service = Mock()
            mock_service.get_organization_bucket.return_value = 'test-bucket'
            mock_service.list_bucket_contents.return_value = [
                {
                    'type': 'file',
                    'name': 'sample.csv',
                    'path': 'data/sample.csv',
                    'size': 1024,
                    'size_formatted': '1.0 KB',
                    'last_modified': None
                }
            ]
            mock_bucket.return_value = mock_service
            
            request = factory.get(f'/ingest/files/?organization={test_organization.id}')
            request.user = authenticated_user
            response = get_organization_files_for_ingest(request)
            assert response.status_code == 200
            assert b'sample.csv' in response.content
    
    @pytest.mark.django_db
    def test_error_handling_integration(self, authenticated_user):
        """Test error handling across views."""
        factory = RequestFactory()
        
        # Test with invalid organization ID
        request = factory.get('/ingest/files/?organization=999')
        request.user = authenticated_user
        response = get_organization_files_for_ingest(request)
        assert response.status_code == 200
        assert b'Organization not found' in response.content
        
        # Test with no organization ID
        request = factory.get('/ingest/files/')
        request.user = authenticated_user
        response = get_organization_files_for_ingest(request)
        assert response.status_code == 200