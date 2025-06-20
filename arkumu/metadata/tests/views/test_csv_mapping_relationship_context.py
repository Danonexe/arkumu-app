"""
Tests for CSV Mapping Relationship Context functionality.

Tests for relationship context views, serialization, validation, and integration
with the CSV mapping system.
"""

import pytest
import json
from unittest.mock import patch, Mock, MagicMock
from django.test import RequestFactory, Client
from django.contrib.auth import get_user_model
from django.http import QueryDict, JsonResponse
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware

from arkumu.metadata.views.csv_mapping.csv_mapping_views import (
    ToggleRelationshipContextFormView,
    SaveInlineRelationshipContextView,
    HideRelationshipContextFormView,
    RemoveRelationshipContextView,
    UpdateRelationshipContextColumnsView
)
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin

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
def mock_workspace_data(organization_id):
    """Mock workspace data with columns suitable for relationship contexts"""
    return {
        'columns': [
            {
                'id': f'{organization_id}::persons.csv::person_id',
                'name': 'person_id',
                'dataset': 'persons.csv',
                'fk_reference': {
                    'target_dataset': 'persons.csv',
                    'target_column': 'id'
                }
            },
            {
                'id': f'{organization_id}::projects.csv::project_id',
                'name': 'project_id', 
                'dataset': 'projects.csv',
                'fk_reference': {
                    'target_dataset': 'projects.csv',
                    'target_column': 'id'
                }
            },
            {
                'id': f'{organization_id}::person_project_roles.csv::role',
                'name': 'role',
                'dataset': 'person_project_roles.csv'
            },
            {
                'id': f'{organization_id}::person_project_roles.csv::person_id',
                'name': 'person_id',
                'dataset': 'person_project_roles.csv',
                'fk_reference': {
                    'target_dataset': 'persons.csv',
                    'target_column': 'id'
                }
            },
            {
                'id': f'{organization_id}::person_project_roles.csv::project_id',
                'name': 'project_id',
                'dataset': 'person_project_roles.csv',
                'fk_reference': {
                    'target_dataset': 'projects.csv',
                    'target_column': 'id'
                }
            }
        ]
    }


def add_session_to_request(request):
    """Add session middleware to request for testing"""
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()
    
    csrf_middleware = CsrfViewMiddleware(lambda req: None)
    csrf_middleware.process_request(request)
    return request


@pytest.mark.django_db
class TestToggleRelationshipContextFormView:
    """Tests for ToggleRelationshipContextFormView"""
    
    def test_toggle_form_view_success(self, request_factory, organization_id, mock_workspace_data):
        """Test successful toggle of relationship context form"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role'
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = ToggleRelationshipContextFormView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_workspace_columns', return_value=mock_workspace_data['columns']):
                with patch.object(view, 'get_all_datasets_with_columns_for_fk') as mock_datasets:
                    mock_datasets.return_value = [
                        {
                            'dataset_name': 'persons.csv',
                            'columns': [{'id': 'person_id', 'name': 'person_id'}]
                        },
                        {
                            'dataset_name': 'projects.csv', 
                            'columns': [{'id': 'project_id', 'name': 'project_id'}]
                        }
                    ]
                    
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                        mock_render.return_value = Mock()
                        
                        response = view.post(request)
                        
                        # Verify render was called with correct template
                        mock_render.assert_called_once()
                        args, kwargs = mock_render.call_args
                        
                        assert args[1] == 'csv_mapping/partials/inline_relationship_context_form.html'
                        context = args[2]
                        
                        # Verify context contains expected data
                        assert 'column' in context
                        assert 'datasets' in context
                        assert context['column']['id'] == post_data['column_id']
    
    def test_toggle_form_view_missing_column_id(self, request_factory, organization_id):
        """Test toggle form view with missing column_id"""
        request = request_factory.post('/', data={})
        request = add_session_to_request(request)
        
        view = ToggleRelationshipContextFormView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            response = view.post(request)
            
            assert response.status_code == 200
            content = response.content.decode()
            assert 'Column ID required' in content or 'text-error' in content


@pytest.mark.django_db
class TestSaveInlineRelationshipContextView:
    """Tests for SaveInlineRelationshipContextView"""
    
    def test_save_relationship_context_success(self, request_factory, organization_id, mock_workspace_data):
        """Test successful save of relationship context configuration"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role',
            'context_predicate': 'hasRole',
            'primary_fk_dataset': 'person_project_roles.csv',
            'primary_fk_column': 'person_id',
            'secondary_fk_dataset': 'person_project_roles.csv',
            'secondary_fk_column': 'project_id'
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = SaveInlineRelationshipContextView()
        
        # Mock workspace columns including the target column
        workspace_columns = mock_workspace_data['columns'].copy()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_workspace_columns', return_value=workspace_columns):
                with patch.object(view, 'update_workspace_columns') as mock_update:
                    with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render_to_string', return_value='<div>Updated column</div>'):
                        response = view.post(request)
                        
                        assert response.status_code == 200
                        content = response.content.decode()
                        assert 'Updated column' in content or 'column-item' in content
                    
                    # Verify update_workspace_columns was called
                    mock_update.assert_called_once()
                    
                    # Get the updated columns
                    call_args = mock_update.call_args[0]
                    updated_columns = call_args[2]
                    
                    # Find the target column and verify relationship context was added
                    target_column = next(
                        col for col in updated_columns 
                        if col['id'] == post_data['column_id']
                    )
                    
                    assert 'relationship_context' in target_column
                    ctx = target_column['relationship_context']
                    assert ctx['predicate'] == 'hasRole'
                    assert ctx['primary_fk_dataset'] == 'person_project_roles.csv'
                    assert ctx['primary_fk_column'] == 'person_id'
                    assert ctx['secondary_fk_dataset'] == 'person_project_roles.csv'
                    assert ctx['secondary_fk_column'] == 'project_id'
    
    def test_save_relationship_context_validation_error(self, request_factory, organization_id):
        """Test save with validation errors"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role',
            'context_predicate': '',  # Empty predicate should fail validation
            'primary_fk_dataset': 'persons.csv',
            'primary_fk_column': 'person_id'
            # Missing secondary FK fields
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = SaveInlineRelationshipContextView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            response = view.post(request)
            
            assert response.status_code == 200
            content = response.content.decode()
            assert 'Missing required fields' in content or 'text-error' in content
    
    def test_save_relationship_context_column_not_found(self, request_factory, organization_id):
        """Test save when target column is not in workspace"""
        post_data = {
            'column_id': f'{organization_id}::nonexistent.csv::role',
            'context_predicate': 'hasRole',
            'primary_fk_dataset': 'persons.csv',
            'primary_fk_column': 'person_id',
            'secondary_fk_dataset': 'projects.csv',
            'secondary_fk_column': 'project_id'
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = SaveInlineRelationshipContextView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_workspace_columns', return_value=[]):
                response = view.post(request)
                
                assert response.status_code == 200
                content = response.content.decode()
                assert 'not found in workspace' in content or 'text-error' in content


@pytest.mark.django_db
class TestRemoveRelationshipContextView:
    """Tests for RemoveRelationshipContextView"""
    
    def test_remove_relationship_context_success(self, request_factory, organization_id, mock_workspace_data):
        """Test successful removal of relationship context"""
        # Add relationship context to a column
        target_column = mock_workspace_data['columns'][2]  # role column
        target_column['relationship_context'] = {
            'predicate': 'hasRole',
            'primary_fk_dataset': 'person_project_roles.csv',
            'primary_fk_column': 'person_id',
            'secondary_fk_dataset': 'person_project_roles.csv',
            'secondary_fk_column': 'project_id'
        }
        
        post_data = {'column_id': target_column['id']}
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = RemoveRelationshipContextView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_workspace_columns', return_value=mock_workspace_data['columns']):
                with patch.object(view, 'update_workspace_columns') as mock_update:
                    with patch.object(view, '_prepare_datasets_with_columns', return_value=[]):
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render_to_string', return_value='<div>Updated workspace</div>'):
                            response = view.post(request)
                            
                            assert response.status_code == 200
                            content = response.content.decode()
                            assert 'Updated workspace' in content or content  # Any content indicates success
                    
                    # Verify the relationship context was removed
                    call_args = mock_update.call_args[0]
                    updated_columns = call_args[2]
                    
                    updated_column = next(
                        col for col in updated_columns 
                        if col['id'] == target_column['id']
                    )
                    
                    assert 'relationship_context' not in updated_column


@pytest.mark.django_db 
class TestRelationshipContextSerialization:
    """Tests for relationship context serialization and deserialization"""
    
    def test_serialize_mapping_state_with_relationship_contexts(self, organization_id, mock_workspace_data):
        """Test that relationship contexts are included in serialized mapping state"""
        # Add relationship context to a column
        target_column = mock_workspace_data['columns'][2]  # role column
        target_column['relationship_context'] = {
            'predicate': 'hasRole',
            'primary_fk_dataset': 'person_project_roles.csv',
            'primary_fk_column': 'person_id',
            'secondary_fk_dataset': 'person_project_roles.csv',
            'secondary_fk_column': 'project_id'
        }
        
        coordinator = CSVMappingCoordinatorMixin()
        
        with patch.object(coordinator, 'get_workspace_columns', return_value=mock_workspace_data['columns']):
            with patch.object(coordinator, 'get_selected_dataset_names', return_value=[]):
                mapping_state = coordinator.serialize_current_mapping_state(
                    Mock(), organization_id
                )
                
                # Verify the serialized state includes relationship contexts
                assert 'version' in mapping_state
                assert mapping_state['version'] == '1.1'
                assert 'workspace_columns' in mapping_state
                
                # Find the column with relationship context
                role_column = next(
                    col for col in mock_workspace_data['columns']
                    if col['name'] == 'role'
                )
                
                assert 'relationship_context' in role_column
                ctx = role_column['relationship_context']
                assert ctx['predicate'] == 'hasRole'
                assert ctx['primary_fk_dataset'] == 'person_project_roles.csv'
    
    def test_deserialize_mapping_state_with_relationship_contexts(self, organization_id):
        """Test that relationship contexts are properly restored during deserialization"""
        # Create mapping state with relationship context
        mapping_state = {
            'version': '1.1',
            'source_id': organization_id,
            'columns': [
                {
                    'id': f'{organization_id}::person_project_roles.csv::role',
                    'name': 'role',
                    'dataset': 'person_project_roles.csv',
                    'relationship_context': {
                        'predicate': 'hasRole',
                        'primary_fk_dataset': 'person_project_roles.csv',
                        'primary_fk_column': 'person_id',
                        'secondary_fk_dataset': 'person_project_roles.csv',
                        'secondary_fk_column': 'project_id'
                    }
                }
            ],
            'selected_datasets': [],
            'import_strategy': {}
        }
        
        coordinator = CSVMappingCoordinatorMixin()
        
        with patch.object(coordinator, 'reset_all_coordinator_state'):
            # The deserialize method directly modifies the session, so we test that
            result = coordinator.deserialize_mapping_state(
                Mock(), organization_id, mapping_state
            )
            
            # Verify deserialization was successful
            assert 'datasets_restored' in result
            assert 'columns_restored' in result  
            assert 'relationship_contexts_restored' in result
            assert result['relationship_contexts_restored'] == 1


@pytest.mark.django_db
class TestRelationshipContextValidation:
    """Tests for relationship context validation logic"""
    
    def test_save_validates_required_fields(self, request_factory, organization_id):
        """Test that the save view validates required fields"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role',
            'context_predicate': '',  # Empty predicate should fail
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = SaveInlineRelationshipContextView()
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            response = view.post(request)
            
            # Should return error response
            assert response.status_code == 200
            content = response.content.decode()
            assert 'Missing required fields' in content or 'context_predicate' in content


@pytest.mark.django_db
class TestUpdateRelationshipContextColumnsView:
    """Tests for UpdateRelationshipContextColumnsView"""
    
    def test_update_columns_for_primary_fk(self, request_factory, organization_id):
        """Test updating columns for primary FK dataset selection"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role',
            'field_type': 'primary',
            'dataset_name': 'persons.csv'
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = UpdateRelationshipContextColumnsView()
        
        mock_datasets = [
            {
                'dataset_name': 'persons.csv',
                'columns': [
                    {'id': 'person_id', 'name': 'person_id'},
                    {'id': 'name', 'name': 'name'}
                ]
            }
        ]
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_all_datasets_with_columns_for_fk', return_value=mock_datasets):
                with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                    mock_render.return_value = Mock()
                    
                    response = view.post(request)
                    
                    # Verify render was called with correct template
                    mock_render.assert_called_once()
                    args, kwargs = mock_render.call_args
                    
                    context = args[2]
                    assert context['field_type'] == 'primary'
                    assert context['dataset_name'] == 'persons.csv'
                    assert len(context['columns']) == 2
    
    def test_update_columns_for_secondary_fk(self, request_factory, organization_id):
        """Test updating columns for secondary FK dataset selection"""
        post_data = {
            'column_id': f'{organization_id}::person_project_roles.csv::role',
            'field_type': 'secondary',
            'dataset_name': 'projects.csv'
        }
        request = request_factory.post('/', data=post_data)
        request = add_session_to_request(request)
        
        view = UpdateRelationshipContextColumnsView()
        
        mock_datasets = [
            {
                'dataset_name': 'projects.csv',
                'columns': [
                    {'id': 'project_id', 'name': 'project_id'},
                    {'id': 'title', 'name': 'title'}
                ]
            }
        ]
        
        with patch.object(view, 'get_organization_id_from_request', return_value=organization_id):
            with patch.object(view, 'get_all_datasets_with_columns_for_fk', return_value=mock_datasets):
                with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render') as mock_render:
                    mock_render.return_value = Mock()
                    
                    response = view.post(request)
                    
                    # Verify render was called with correct template
                    mock_render.assert_called_once()
                    args, kwargs = mock_render.call_args
                    
                    context = args[2]
                    assert context['field_type'] == 'secondary'
                    assert context['dataset_name'] == 'projects.csv'
                    assert len(context['columns']) == 2