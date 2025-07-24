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

from arkumu.metadata.views.csv_mapping.views.core_editor_views import (
    CSVMappingEditorView,
    MappingGraphDataView
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
class TestMappingGraphDataView:
    """Tests for MappingGraphDataView - Graph visualization for CSV mapping relationships"""
    
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
    def mock_workspace_columns(self, organization_id):
        """Mock workspace columns with relationships"""
        return {
            f'{organization_id}::dataset1.csv::id': {
                'dataset': 'dataset1.csv',
                'name': 'id',
                'is_anchor': True,
                'is_fk': False,
                'is_multi_value': False,
                'is_relationship_context': False,
                'is_external_ontology': False
            },
            f'{organization_id}::dataset1.csv::user_id': {
                'dataset': 'dataset1.csv',
                'name': 'user_id',
                'is_anchor': False,
                'is_fk': True,
                'is_multi_value': False,
                'is_relationship_context': False,
                'is_external_ontology': False,
                'fk_config': {
                    'target_dataset': 'users.csv',
                    'target_column': 'id',
                    'direction': 'outbound'
                }
            },
            f'{organization_id}::dataset2.csv::id': {
                'dataset': 'dataset2.csv',
                'name': 'id',
                'is_anchor': True,
                'is_fk': False,
                'is_multi_value': False,
                'is_relationship_context': False,
                'is_external_ontology': False
            }
        }
    
    @pytest.fixture
    def mock_mapping_model(self, organization_id, mock_workspace_columns):
        """Mock mapping model instance"""
        mapping = Mock()
        mapping.id = 'test-mapping-123'
        mapping.name = 'Test Mapping'
        mapping.description = 'Test mapping description'
        mapping.mapping_config = {
            'workspace_columns': mock_workspace_columns,
            'import_strategy': {'strategy': 'append'}
        }
        return mapping

    def test_get_htmx_request_success(self, request_factory, organization_id, mock_organization_context, mock_workspace_columns):
        """Test successful HTMX request returns modal with graph data"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        # Add HTMX headers
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch.object(view, 'get_workspace_columns', return_value=mock_workspace_columns):
                with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                    mock_render.return_value = Mock()
                    
                    response = view.get(request)
                    
                    # Verify render was called with correct template for HTMX
                    mock_render.assert_called_once()
                    args, kwargs = mock_render.call_args
                    
                    assert args[1] == 'csv_mapping/partials/mapping_graph_modal_open.html'
                    context = args[2]
                    
                    # Verify context contains graph data
                    assert 'graph_data' in context
                    assert 'nodes' in context['graph_data']
                    assert 'edges' in context['graph_data']
                    assert context['error'] is None
                    
                    # Verify graph data structure
                    graph_data = context['graph_data']
                    assert len(graph_data['nodes']) > 0  # Should have dataset and column nodes
                    assert len(graph_data['edges']) > 0  # Should have edges

    def test_get_htmx_request_with_mapping_id(self, request_factory, organization_id, mock_organization_context, mock_mapping_model):
        """Test HTMX request with specific mapping ID loads mapping from database"""
        request = request_factory.get(f'/?organization={organization_id}&mapping_id=test-mapping-123')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch('arkumu.metadata.models.mappings.Mapping.objects.get', return_value=mock_mapping_model):
                with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                    mock_render.return_value = Mock()
                    
                    response = view.get(request)
                    
                    # Verify template and context
                    args, kwargs = mock_render.call_args
                    assert args[1] == 'csv_mapping/partials/mapping_graph_modal_open.html'
                    context = args[2]
                    
                    # Verify mapping info is in context
                    assert context['mapping_name'] == 'Test Mapping'
                    assert context['mapping_description'] == 'Test mapping description'
                    assert 'graph_data' in context

    def test_get_json_request_success(self, request_factory, organization_id, mock_organization_context, mock_workspace_columns):
        """Test non-HTMX request returns JSON data"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        # No HTMX headers - should return JSON
        
        view = MappingGraphDataView()
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch.object(view, 'get_workspace_columns', return_value=mock_workspace_columns):
                response = view.get(request)
                
                # Should return JsonResponse
                assert hasattr(response, 'content')
                
                # Parse JSON content
                content = json.loads(response.content.decode())
                assert 'nodes' in content
                assert 'edges' in content
                assert len(content['nodes']) > 0
                assert len(content['edges']) > 0

    def test_get_invalid_organization_htmx(self, request_factory):
        """Test HTMX request with invalid organization returns error modal"""
        request = request_factory.get('/?organization=invalid-org')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        invalid_org_context = {
            'organization_id': 'invalid-org',
            'organization_exists': False,
            'organizations': []
        }
        
        with patch.object(view, 'get_organization_context', return_value=invalid_org_context):
            with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                mock_render.return_value = Mock()
                
                response = view.get(request)
                
                # Verify error template
                args, kwargs = mock_render.call_args
                assert args[1] == 'csv_mapping/partials/mapping_graph_content.html'
                context = args[2]
                
                assert context['error'] == 'Invalid organization'
                assert context['graph_data']['nodes'] == []
                assert context['graph_data']['edges'] == []

    def test_get_mapping_not_found_htmx(self, request_factory, organization_id, mock_organization_context):
        """Test HTMX request with non-existent mapping ID returns error"""
        request = request_factory.get(f'/?organization={organization_id}&mapping_id=non-existent')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        from arkumu.metadata.models.mappings import Mapping
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch.object(Mapping.objects, 'get', side_effect=Mapping.DoesNotExist):
                with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                    mock_render.return_value = Mock()
                    
                    response = view.get(request)
                    
                    # Verify error handling
                    args, kwargs = mock_render.call_args
                    context = args[2]
                    
                    assert 'Mapping non-existent not found' in context['error']

    def test_graph_data_disabled(self, request_factory, organization_id, mock_organization_context, mock_workspace_columns):
        """Test that graph visualization is disabled and returns appropriate error"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        
        view = MappingGraphDataView()
        
        # Test that graph visualization returns disabled message
        response = view.get(request)
        
        # Should return 501 status for non-HTMX requests
        assert response.status_code == 501
        
        # Should contain error message about disabled functionality
        response_data = json.loads(response.content)
        assert 'Graph visualization libraries have been removed' in response_data['error']

    def test_exception_handling_htmx(self, request_factory, organization_id):
        """Test that exceptions are properly handled and return error templates for HTMX"""
        request = request_factory.get(f'/?organization={organization_id}')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        # Force an exception
        with patch.object(view, 'get_organization_context', side_effect=Exception("Test error")):
            with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                mock_render.return_value = Mock()
                
                response = view.get(request)
                
                # Verify error handling
                args, kwargs = mock_render.call_args
                assert args[1] == 'csv_mapping/partials/mapping_graph_content.html'
                context = args[2]
                
                assert context['error'] == 'Test error'

    def test_modal_target_issue_analysis(self, request_factory, organization_id, mock_organization_context, mock_workspace_columns):
        """Test to verify the HTMX target/swap issue with modal loading"""
        # Use a valid UUID for mapping_id to avoid validation errors
        import uuid
        valid_mapping_id = str(uuid.uuid4())
        
        request = request_factory.get(f'/?organization={organization_id}&mapping_id={valid_mapping_id}')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        # Mock the mapping to avoid database lookup
        mock_mapping = Mock()
        mock_mapping.name = 'Test Mapping'
        mock_mapping.description = 'Test Description'
        mock_mapping.mapping_config = {
            'workspace_columns': mock_workspace_columns
        }
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch.object(view, 'get_workspace_columns', return_value=mock_workspace_columns):
                with patch('arkumu.metadata.models.mappings.Mapping.objects.get', return_value=mock_mapping):
                    with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                        mock_response = Mock()
                        mock_response.content = b'<dialog id="mapping-graph-modal" class="modal" open>...</dialog>'
                        mock_render.return_value = mock_response
                        
                        response = view.get(request)
                        
                        # Verify the view returns the open modal template
                        args, kwargs = mock_render.call_args
                        template_name = args[1]
                        
                        # ISSUE IDENTIFIED: The view should return mapping_graph_modal_open.html for HTMX requests
                        # but current implementation may return content template during errors
                        assert template_name == 'csv_mapping/partials/mapping_graph_modal_open.html'
                        
                        # The response content should contain a complete modal element
                        assert b'<dialog id="mapping-graph-modal"' in response.content
                        assert b'open' in response.content

    def test_error_handling_returns_content_template_not_modal(self, request_factory, organization_id, mock_organization_context):
        """Test that demonstrates the issue: errors return content template instead of modal template"""
        # Use invalid mapping ID to trigger error
        request = request_factory.get(f'/?organization={organization_id}&mapping_id=invalid-uuid')
        request = add_session_to_request(request)
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        view = MappingGraphDataView()
        
        with patch.object(view, 'get_organization_context', return_value=mock_organization_context):
            with patch('arkumu.metadata.views.csv_mapping.views.core_editor_views.render') as mock_render:
                mock_render.return_value = Mock()
                
                response = view.get(request)
                
                # This is the BUG: When there's an error, the view returns content template
                # instead of modal template, which breaks HTMX modal opening
                args, kwargs = mock_render.call_args
                template_name = args[1]
                
                # This demonstrates the bug - errors return content template
                assert template_name == 'csv_mapping/partials/mapping_graph_content.html'
                
                # This means HTMX gets content instead of a proper modal structure
                context = args[2]
                assert 'error' in context 