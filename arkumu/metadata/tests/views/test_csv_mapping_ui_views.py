"""
Tests for CSV Mapping UI Views

Tests for user interface views that handle template rendering, 
organization discovery, and JSON content display.
"""

import pytest
import json
from unittest.mock import patch, Mock, MagicMock
from django.test import RequestFactory, Client
from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware

from arkumu.metadata.views.csv_mapping.csv_mapping_views import (
    CSVMappingEditorView,
    GetMappingJSONContentView
)

User = get_user_model()


@pytest.fixture
def user():
    """Create test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def request_factory():
    """Django request factory"""
    return RequestFactory()


@pytest.fixture
def organization_id():
    """Test organization ID"""
    return 'test-org-123'


@pytest.fixture
def mock_csv_datasets():
    """Mock CSV datasets for testing"""
    return [
        {
            'name': 'dataset1.csv',
            'source': 'csv',
            'preview': {
                'colHeaders': ['id', 'name', 'email'],
                'data': [['1', 'John', 'john@example.com'], ['2', 'Jane', 'jane@example.com']],
                'total_rows': 2
            }
        },
        {
            'name': 'dataset2.csv', 
            'source': 'csv',
            'preview': {
                'colHeaders': ['user_id', 'order_date', 'amount'],
                'data': [['1', '2024-01-01', '100.00'], ['2', '2024-01-02', '250.50']],
                'total_rows': 2
            }
        }
    ]


def add_session_to_request(request):
    """Add session middleware to request for testing"""
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()
    
    csrf_middleware = CsrfViewMiddleware(lambda req: None)
    csrf_middleware.process_request(request)
    return request


@pytest.mark.django_db
class TestCSVMappingEditorView:
    """Tests for CSVMappingEditorView - Main UI controller"""
    
    @pytest.fixture
    def mock_organization_context(self, organization_id):
        """Mock organization context"""
        return {
            'organization_id': organization_id,
            'organization_exists': True,
            'organizations': [
                {'id': organization_id, 'name': 'Test Organization'},
                {'id': 'other-org', 'name': 'Other Organization'}
            ]
        }
    
    @pytest.fixture
    def mock_coordinator_methods(self, mock_csv_datasets, organization_id):
        """Mock all coordinator mixin methods"""
        return {
            'get_csv_datasets_for_organization': Mock(return_value=mock_csv_datasets),
            'get_selected_datasets_with_details': Mock(return_value=(
                ['dataset1.csv'], 
                [{'name': 'dataset1.csv', 'source': 'csv'}]
            )),
            'get_workspace_columns': Mock(return_value=[
                f'{organization_id}::dataset1.csv::id',
                f'{organization_id}::dataset1.csv::name'
            ]),
            'get_import_strategy': Mock(return_value={'strategy': 'append'}),
            'get_import_strategy_summary': Mock(return_value={'total_operations': 1}),
            'get_workspace_summary': Mock(return_value={
                'total_datasets': 1,
                'total_columns': 2,
                'total_relationships': 0
            }),
            '_prepare_datasets_with_columns': Mock(return_value=[
                {
                    'dataset_name': 'dataset1.csv',
                    'columns': [
                        {'id': f'{organization_id}::dataset1.csv::id', 'name': 'id'},
                        {'id': f'{organization_id}::dataset1.csv::name', 'name': 'name'}
                    ]
                }
            ])
        }
    
    def test_get_request_success(self, request_factory, organization_id, mock_organization_context, mock_coordinator_methods):
        """Test successful GET request returns main editor template"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = CSVMappingEditorView()
        
        with patch.multiple(view, **mock_coordinator_methods):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.get(request)
                        
                        # Verify render was called with correct template and context
                        mock_render.assert_called_once()
                        args, kwargs = mock_render.call_args
                        
                        assert args[1] == 'csv_mapping/main_editor.html'  # Correct template
                        context = args[2]
                        
                        # Verify context contains expected data
                        assert context['organization_id'] == organization_id
                        assert 'csv_datasets' in context
                        assert 'selected_datasets' in context
                        assert 'workspace_summary' in context
                        assert 'import_strategy' in context
    
    def test_get_request_invalid_organization(self, request_factory, mock_coordinator_methods):
        """Test GET request with invalid organization shows error"""
        request = request_factory.get('/?organization=invalid-org')
        request = add_session_to_request(request)
        
        view = CSVMappingEditorView()
        
        invalid_org_context = {
            'organization_id': 'invalid-org',
            'organization_exists': False,
            'organizations': [{'id': 'valid-org', 'name': 'Valid Org'}]
        }
        
        with patch.multiple(view, **mock_coordinator_methods):
            with patch.object(view, 'get_organization_context', return_value=invalid_org_context):
                with patch.object(view, 'get_organization_id_from_request', return_value='invalid-org'):
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.get(request)
                        
                        # Verify error context
                        args, kwargs = mock_render.call_args
                        context = args[2]
                        
                        assert 'error' in context
                        assert 'invalid-org' in context['error']
                        assert 'not found' in context['error']
                        assert context['show_organization_help'] is True
    
    def test_get_request_missing_organization(self, request_factory, mock_coordinator_methods):
        """Test GET request without organization parameter"""
        request = request_factory.get('/')  # No organization parameter
        request = add_session_to_request(request)
        
        view = CSVMappingEditorView()
        
        missing_org_context = {
            'organization_id': 'default-org',
            'organization_exists': False,
            'organizations': []
        }
        
        with patch.multiple(view, **mock_coordinator_methods):
            with patch.object(view, 'get_organization_context', return_value=missing_org_context):
                with patch.object(view, 'get_organization_id_from_request', return_value='default-org'):
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.get(request)
                        
                        # Verify error context
                        args, kwargs = mock_render.call_args
                        context = args[2]
                        
                        assert 'error' in context
                        assert 'Organization parameter required' in context['error']
                        assert '?organization=YOUR_ORG_ID' in context['error']
    
    def test_htmx_request_workspace_tab(self, request_factory, organization_id, mock_organization_context, mock_coordinator_methods):
        """Test HTMX request for workspace tab returns partial template"""
        request = request_factory.get(f'/?organization={organization_id}&tab=workspace')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = CSVMappingEditorView()
        
        with patch.multiple(view, **mock_coordinator_methods):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.get(request)
                        
                        # Verify correct partial template used
                        args, kwargs = mock_render.call_args
                        assert args[1] == 'csv_mapping/partials/selected_columns_workspace.html'
                        
                        context = args[2]
                        assert 'datasets_with_columns' in context
                        assert context['organization_id'] == organization_id
    
    def test_htmx_request_main_content(self, request_factory, organization_id, mock_organization_context, mock_coordinator_methods):
        """Test HTMX request for main content returns partial template"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = CSVMappingEditorView()
        
        with patch.multiple(view, **mock_coordinator_methods):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.get(request)
                        
                        # Verify correct partial template used
                        args, kwargs = mock_render.call_args
                        assert args[1] == 'csv_mapping/partials/main_content.html'
    
    def test_exception_handling(self, request_factory, organization_id):
        """Test exception handling in GET request"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = CSVMappingEditorView()
        
        # Mock get_organization_context to raise exception
        with patch.object(view, 'get_organization_context', side_effect=Exception("Test error")):
            with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.logger') as mock_logger:
                    mock_render.return_value = Mock()
                    
                    response = view.get(request)
                    
                    # Verify error logging
                    mock_logger.error.assert_called()
                    
                    # Verify error context
                    args, kwargs = mock_render.call_args
                    context = args[2]
                    assert 'error' in context
                    assert 'Error loading CSV mapping editor' in context['error']


@pytest.mark.django_db  
class TestGetMappingJSONContentView:
    """Tests for GetMappingJSONContentView - JSON content display"""
    
    @pytest.fixture
    def mock_organization_context(self, organization_id):
        """Mock organization context"""
        return {
            'organization_id': organization_id,
            'organization_exists': True,
            'organizations': [{'id': organization_id, 'name': 'Test Organization'}]
        }
    
    @pytest.fixture
    def mock_mapping_config(self, organization_id):
        """Mock mapping configuration"""
        return {
            'version': '1.0',
            'organization_id': organization_id,
            'selected_datasets': ['dataset1.csv', 'dataset2.csv'],
            'workspace_columns': {
                f'{organization_id}::dataset1.csv::id': {
                    'name': 'id',
                    'dataset': 'dataset1.csv',
                    'source': organization_id
                },
                f'{organization_id}::dataset1.csv::name': {
                    'name': 'name', 
                    'dataset': 'dataset1.csv',
                    'source': organization_id
                }
            },
            'fk_relationships': {},
            'entity_mappings': {},
            'metadata': {
                'total_datasets': 2,
                'total_columns': 2,
                'total_fk_relationships': 0
            }
        }
    
    def test_get_json_content_success(self, request_factory, organization_id, mock_organization_context, mock_mapping_config):
        """Test successful JSON content generation"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = GetMappingJSONContentView()
        
        mock_workspace_summary = {
            'total_datasets': 2,
            'total_columns': 2,
            'selected_datasets': ['dataset1.csv', 'dataset2.csv']
        }
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'serialize_current_mapping_state', return_value=mock_mapping_config):
                    with patch.object(view, 'get_workspace_summary', return_value=mock_workspace_summary):
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.timezone') as mock_timezone:
                            mock_timezone.now.return_value.isoformat.return_value = '2024-01-01T12:00:00'
                            mock_timezone.now.return_value.strftime.return_value = '2024-01-01 12:00:00'
                            
                            response = view.get(request)
                            
                            # Verify response content contains expected elements
                            content = response.content.decode()
                            
                            assert 'Current Mapping Configuration' in content
                            assert '📋 Copy JSON' in content
                            assert '💾 Download JSON' in content
                            assert '"organization_id"' in content
                            assert f'"{organization_id}"' in content
                            assert 'export_timestamp' in content
                            assert 'workspace_summary' in content
                            
                            # Verify JSON structure is included
                            assert 'workspace_columns' in content
                            assert 'selected_datasets' in content
    
    def test_get_json_content_invalid_organization(self, request_factory, organization_id):
        """Test JSON content with invalid organization"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = GetMappingJSONContentView()
        
        invalid_org_context = {
            'organization_id': organization_id,
            'organization_exists': False,
            'organizations': []
        }
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_organization_context', return_value=invalid_org_context):
                response = view.get(request)
                
                content = response.content.decode()
                
                # Verify error JSON structure
                assert 'Invalid organization' in content
                assert f'Organization \\"{organization_id}\\" not found' in content
                assert '<pre class="bg-gray-100' in content  # Error format
    
    def test_get_json_content_with_complex_data(self, request_factory, organization_id, mock_organization_context):
        """Test JSON content with complex mapping data including FK relationships"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        complex_mapping_config = {
            'version': '1.0',
            'organization_id': organization_id,
            'selected_datasets': ['users.csv', 'orders.csv', 'products.csv'],
            'workspace_columns': {
                f'{organization_id}::users.csv::id': {'name': 'id', 'dataset': 'users.csv'},
                f'{organization_id}::users.csv::name': {'name': 'name', 'dataset': 'users.csv'},
                f'{organization_id}::orders.csv::user_id': {'name': 'user_id', 'dataset': 'orders.csv'},
                f'{organization_id}::orders.csv::product_id': {'name': 'product_id', 'dataset': 'orders.csv'},
                f'{organization_id}::products.csv::id': {'name': 'id', 'dataset': 'products.csv'},
            },
            'fk_relationships': {
                f'{organization_id}::orders.csv::user_id': {
                    'target_dataset': 'users.csv',
                    'target_column': 'id',
                    'relationship_type': 'many_to_one'
                },
                f'{organization_id}::orders.csv::product_id': {
                    'target_dataset': 'products.csv',
                    'target_column': 'id',
                    'relationship_type': 'many_to_one'
                }
            },
            'entity_mappings': {},
            'metadata': {
                'total_datasets': 3,
                'total_columns': 5,
                'total_fk_relationships': 2
            }
        }
        
        view = GetMappingJSONContentView()
        
        mock_workspace_summary = {
            'total_datasets': 3,
            'total_columns': 5,
            'selected_datasets': ['users.csv', 'orders.csv', 'products.csv']
        }
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'serialize_current_mapping_state', return_value=complex_mapping_config):
                    with patch.object(view, 'get_workspace_summary', return_value=mock_workspace_summary):
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.timezone') as mock_timezone:
                            # Create a proper mock that returns strings, not MagicMocks
                            mock_now = Mock()
                            mock_now.isoformat.return_value = '2024-01-01T12:00:00'
                            mock_now.strftime.return_value = '2024-01-01 12:00:00'
                            mock_timezone.now.return_value = mock_now
                            
                            response = view.get(request)
                            
                            content = response.content.decode()
                            
                            # Verify complex data is included
                            assert 'fk_relationships' in content
                            assert 'many_to_one' in content
                            assert 'Datasets: 3' in content
                            assert 'Columns: 5' in content  
                            assert 'FK Relations: 2' in content
                            
                            # Verify organization_id format in column IDs
                            assert f'{organization_id}::users.csv::id' in content
                            assert f'{organization_id}::orders.csv::user_id' in content
    
    def test_exception_handling(self, request_factory, organization_id):
        """Test exception handling in JSON content generation"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = GetMappingJSONContentView()
        
        with patch.object(view, 'get_organization_id_from_request', side_effect=Exception("Test error")):
            with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.logger') as mock_logger:
                response = view.get(request)
                
                # Verify error logging
                mock_logger.error.assert_called()
                
                # Verify error HTML response
                content = response.content.decode()
                assert 'Error Loading JSON' in content
                assert 'Test error' in content
                assert 'bg-red-50' in content  # Error styling
    
    def test_json_formatting_and_structure(self, request_factory, organization_id, mock_organization_context, mock_mapping_config):
        """Test that JSON is properly formatted and structured"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = GetMappingJSONContentView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
                with patch.object(view, 'serialize_current_mapping_state', return_value=mock_mapping_config):
                    with patch.object(view, 'get_workspace_summary', return_value={}):
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.timezone') as mock_timezone:
                            mock_timezone.now.return_value.isoformat.return_value = '2024-01-01T12:00:00'
                            mock_timezone.now.return_value.strftime.return_value = '2024-01-01 12:00:00'
                            
                            response = view.get(request)
                            content = response.content.decode()
                            
                            # Verify JSON structure and formatting
                            assert 'json-content' in content  # ID for copy functionality
                            assert 'copyJsonToClipboard' in content  # Copy function
                            assert '/metadata/csv-mapping/export-json/' in content  # Download link
                            assert 'Generated:' in content  # Timestamp
                            
                            # Extract and verify JSON structure
                            import re
                            json_match = re.search(r'<code>({.*})</code>', content, re.DOTALL)
                            assert json_match is not None
                            
                            # Parse the JSON to verify it's valid
                            json_content = json_match.group(1)
                            parsed_json = json.loads(json_content)
                            
                            # Verify expected structure
                            assert 'export_timestamp' in parsed_json
                            assert 'exported_by' in parsed_json
                            assert 'workspace_summary' in parsed_json
                            assert parsed_json['organization_id'] == organization_id


@pytest.mark.django_db
class TestViewIntegration:
    """Integration tests for UI views"""
    
    def test_view_direct_instantiation(self, request_factory, organization_id):
        """Test that views can be instantiated and called directly"""
        # Test CSVMappingEditorView instantiation
        editor_view = CSVMappingEditorView()
        assert editor_view is not None
        assert hasattr(editor_view, 'get')
        
        # Test GetMappingJSONContentView instantiation
        json_view = GetMappingJSONContentView()
        assert json_view is not None
        assert hasattr(json_view, 'get')
        
        # Test that both views have the expected mixin methods
        assert hasattr(editor_view, 'get_organization_context')
        assert hasattr(editor_view, 'get_csv_datasets_for_organization')
        assert hasattr(json_view, 'serialize_current_mapping_state')
        assert hasattr(json_view, 'get_workspace_summary') 