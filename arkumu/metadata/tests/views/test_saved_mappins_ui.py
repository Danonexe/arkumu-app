"""
Tests for CSV Mapping HTMX UI Views

Tests all HTMX-based UI interactions for saved mapping configurations including
button states, validation feedback, status messages, and HTML responses.
"""

import pytest
import json
from unittest.mock import patch, Mock, MagicMock
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import JsonResponse
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.saved_mappings_ui import (
    ValidateMappingNameView, UpdateButtonStateView, SaveMappingHTMXView,
    LoadMappingHTMXView, DeleteMappingHTMXView
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
def organization_id():
    """Test organization ID"""
    return 'test-org-123'


@pytest.fixture
def sample_mapping_config():
    """Sample mapping configuration data"""
    return {
        'selected_datasets': ['dataset1.csv', 'dataset2.csv'],
        'workspace_columns': {
            'dataset1.csv': ['id', 'name', 'email'],
            'dataset2.csv': ['user_id', 'order_date', 'amount']
        },
        'fk_relationships': {},
        'entity_mappings': {},
        'metadata': {
            'total_datasets': 2,
            'total_columns': 6,
            'total_fk_relationships': 0
        }
    }


@pytest.fixture
def existing_mapping(user, organization_id, sample_mapping_config):
    """Create existing mapping for testing"""
    return Mapping.objects.create(
        name='Test UI Mapping',
        organization_id=organization_id,
        source_datasets=['dataset1.csv', 'dataset2.csv'],
        mapping_config=sample_mapping_config,
        created_by=user,
        validation_status='draft'
    )


@pytest.mark.django_db
class TestValidateMappingNameView:
    """Tests for ValidateMappingNameView"""
    
    def test_validate_empty_name(self, client, user, organization_id):
        """Test validation with empty mapping name"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': '',
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-disabled' in content
        assert 'disabled' in content
        assert 'Save' in content
    
    def test_validate_whitespace_name(self, client, user, organization_id):
        """Test validation with whitespace-only mapping name"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': '   ',
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-disabled' in content
        assert 'disabled' in content
    
    def test_validate_unique_name(self, client, user, organization_id):
        """Test validation with unique mapping name"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'New Unique Mapping',
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-disabled' not in content
        assert 'btn-primary' in content
        assert 'disabled' not in content
        assert 'Save' in content
    
    def test_validate_duplicate_name(self, client, user, organization_id, existing_mapping):
        """Test validation with duplicate mapping name"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': existing_mapping.name,
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-error' in content
        assert 'disabled' in content
        assert 'Name already exists' in content
    
    def test_validate_without_organization(self, client, user):
        """Test validation without organization ID"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'Test Mapping'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-primary' in content  # Should be valid since no duplicate check possible
    
    def test_html_structure(self, client, user, organization_id):
        """Test that returned HTML has correct structure"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'Valid Name',
            'organization': organization_id
        })
        
        content = response.content.decode()
        assert '<button' in content
        assert 'id="save-mapping-btn"' in content
        assert 'hx-post=' in content
        assert 'Save' in content
        assert 'loading-spinner' in content  # Loading indicator should be present


@pytest.mark.django_db
class TestUpdateButtonStateView:
    """Tests for UpdateButtonStateView"""
    
    def test_load_button_enabled(self, client, user, organization_id, existing_mapping):
        """Test load button enabled state with selection"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'load',
            'mapping_id': str(existing_mapping.id),
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-secondary' in content
        assert 'btn-disabled' not in content
        assert 'disabled' not in content
        assert 'Load' in content
        assert 'hx-confirm=' in content  # Should have confirmation
    
    def test_load_button_disabled(self, client, user, organization_id):
        """Test load button disabled state without selection"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'load',
            'mapping_id': '',
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-disabled' in content
        assert 'disabled' in content
        assert 'Load' in content
    
    def test_delete_button_enabled(self, client, user, organization_id, existing_mapping):
        """Test delete button enabled state with selection"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'delete',
            'mapping_id': str(existing_mapping.id),
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-error' in content
        assert 'btn-outline' in content
        assert 'btn-disabled' not in content
        assert 'disabled' not in content
        assert 'Delete' in content
        assert 'hx-confirm=' in content  # Should have confirmation
    
    def test_delete_button_disabled(self, client, user, organization_id):
        """Test delete button disabled state without selection"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'delete',
            'mapping_id': '',
            'organization': organization_id
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'btn-disabled' in content
        assert 'disabled' in content
        assert 'Delete' in content
    
    def test_invalid_button_type(self, client, user, organization_id):
        """Test with invalid button type"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'invalid',
            'mapping_id': 'some-id',
            'organization': organization_id
        })
        
        assert response.status_code == 400
        assert 'Invalid button type' in response.content.decode()
    
    def test_button_html_structure(self, client, user, organization_id, existing_mapping):
        """Test that button HTML has correct HTMX attributes"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'load',
            'mapping_id': str(existing_mapping.id),
            'organization': organization_id
        })
        
        content = response.content.decode()
        assert 'hx-post=' in content
        assert 'hx-vals=' in content
        assert 'hx-include=' in content
        assert 'hx-target=' in content
        assert 'hx-swap=' in content
        assert 'loading-spinner' in content  # Loading indicator


@pytest.mark.django_db
class TestSaveMappingHTMXView:
    """Tests for SaveMappingHTMXView"""
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.SaveMappingView.post')
    def test_save_success_response(self, mock_save_post, client, user, organization_id):
        """Test successful save returns success HTML"""
        # Mock successful JSON response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'message': 'Mapping saved successfully',
            'mapping_id': 'test-id'
        }
        mock_save_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_save_mapping_htmx'), {
            'organization': organization_id,
            'mapping_name': 'Test Mapping'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-success' in content
        assert 'Mapping saved successfully' in content
        assert '<script>' in content  # Should contain JavaScript for UI updates
        assert 'refreshMappings' in content
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.SaveMappingView.post')
    def test_save_error_response(self, mock_save_post, client, user, organization_id):
        """Test error save returns error HTML"""
        # Mock error JSON response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'success': False,
            'error': 'Mapping name already exists'
        }
        mock_save_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_save_mapping_htmx'), {
            'organization': organization_id,
            'mapping_name': 'Duplicate Name'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-error' in content
        assert 'Mapping name already exists' in content
        assert '<script>' not in content  # No JS for errors
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.SaveMappingView.post')
    def test_save_exception_handling(self, mock_save_post, client, user, organization_id):
        """Test exception during save returns generic error HTML"""
        # Mock exception during JSON parsing
        mock_response = Mock()
        mock_response.json.side_effect = Exception("JSON parse error")
        mock_save_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_save_mapping_htmx'), {
            'organization': organization_id,
            'mapping_name': 'Test Mapping'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-error' in content
        assert 'Failed to save mapping' in content


@pytest.mark.django_db
class TestLoadMappingHTMXView:
    """Tests for LoadMappingHTMXView"""
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.LoadMappingView.post')
    def test_load_success_response(self, mock_load_post, client, user, organization_id, existing_mapping):
        """Test successful load returns success HTML"""
        # Mock successful JSON response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'message': 'Mapping loaded successfully',
            'mapping_name': existing_mapping.name
        }
        mock_load_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_load_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id)
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-success' in content
        assert 'Mapping loaded successfully' in content
        assert '<script>' in content
        assert 'window.location.reload()' in content
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.LoadMappingView.post')
    def test_load_success_with_warnings(self, mock_load_post, client, user, organization_id, existing_mapping):
        """Test successful load with warnings returns success HTML with warnings"""
        # Mock successful JSON response with warnings
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'message': 'Mapping loaded successfully',
            'mapping_name': existing_mapping.name,
            'warnings': ['Column X has changed', 'Dataset Y is missing']
        }
        mock_load_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_load_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id)
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-success' in content
        assert 'Mapping loaded successfully' in content
        assert '<ul class="text-sm mt-2">' in content
        assert 'Column X has changed' in content
        assert 'Dataset Y is missing' in content
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.LoadMappingView.post')
    def test_load_error_response(self, mock_load_post, client, user, organization_id):
        """Test error load returns error HTML"""
        # Mock error JSON response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            'success': False,
            'error': 'Mapping not found'
        }
        mock_load_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_load_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': 'non-existent-id'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-error' in content
        assert 'Mapping not found' in content
        assert '<script>' not in content


@pytest.mark.django_db
class TestDeleteMappingHTMXView:
    """Tests for DeleteMappingHTMXView"""
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.DeleteMappingView.post')
    def test_delete_success_response(self, mock_delete_post, client, user, organization_id, existing_mapping):
        """Test successful delete returns success HTML"""
        # Mock successful JSON response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'message': f'Mapping "{existing_mapping.name}" deleted successfully'
        }
        mock_delete_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_delete_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id)
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-success' in content
        assert 'deleted successfully' in content
        assert '<script>' in content
        assert 'refreshMappings' in content
        assert 'mapping-select' in content  # Should clear selection
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.DeleteMappingView.post')
    def test_delete_error_response(self, mock_delete_post, client, user, organization_id):
        """Test error delete returns error HTML"""
        # Mock error JSON response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            'success': False,
            'error': 'Mapping not found'
        }
        mock_delete_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_delete_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': 'non-existent-id'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-error' in content
        assert 'Mapping not found' in content
        assert '<script>' not in content
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_ui.DeleteMappingView.post')
    def test_delete_exception_handling(self, mock_delete_post, client, user, organization_id):
        """Test exception during delete returns generic error HTML"""
        # Mock exception during JSON parsing
        mock_response = Mock()
        mock_response.json.side_effect = Exception("JSON parse error")
        mock_delete_post.return_value = mock_response
        
        client.force_login(user)
        
        response = client.post(reverse('metadata:csv_delete_mapping_htmx'), {
            'organization': organization_id,
            'mapping_id': 'some-id'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'alert-error' in content
        assert 'Failed to delete mapping' in content


@pytest.mark.django_db
class TestUIIntegration:
    """Integration tests for UI workflow"""
    
    def test_complete_ui_workflow(self, client, user, organization_id):
        """Test complete UI workflow: validate → save → load → delete"""
        client.force_login(user)
        
        # 1. Validate new mapping name
        validate_response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'UI Workflow Test',
            'organization': organization_id
        })
        assert validate_response.status_code == 200
        assert 'btn-primary' in validate_response.content.decode()
        assert 'btn-disabled' not in validate_response.content.decode()
        
        # 2. Check load button disabled state
        load_button_response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'load',
            'mapping_id': '',
            'organization': organization_id
        })
        assert load_button_response.status_code == 200
        assert 'btn-disabled' in load_button_response.content.decode()
        
        # 3. Check delete button disabled state
        delete_button_response = client.get(reverse('metadata:csv_update_button_state'), {
            'button': 'delete',
            'mapping_id': '',
            'organization': organization_id
        })
        assert delete_button_response.status_code == 200
        assert 'btn-disabled' in delete_button_response.content.decode()
    
    def test_duplicate_name_validation_workflow(self, client, user, organization_id, existing_mapping):
        """Test validation workflow with duplicate names"""
        client.force_login(user)
        
        # First, validate unique name
        unique_response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'Unique Name',
            'organization': organization_id
        })
        assert 'btn-primary' in unique_response.content.decode()
        assert 'btn-disabled' not in unique_response.content.decode()
        
        # Then, validate duplicate name
        duplicate_response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': existing_mapping.name,
            'organization': organization_id
        })
        assert 'btn-error' in duplicate_response.content.decode()
        assert 'Name already exists' in duplicate_response.content.decode()
    
    def test_button_state_changes(self, client, user, organization_id, existing_mapping):
        """Test button state changes with selection"""
        client.force_login(user)
        
        # Test buttons without selection
        for button_type in ['load', 'delete']:
            response = client.get(reverse('metadata:csv_update_button_state'), {
                'button': button_type,
                'mapping_id': '',
                'organization': organization_id
            })
            assert 'btn-disabled' in response.content.decode()
        
        # Test buttons with selection
        for button_type in ['load', 'delete']:
            response = client.get(reverse('metadata:csv_update_button_state'), {
                'button': button_type,
                'mapping_id': str(existing_mapping.id),
                'organization': organization_id
            })
            assert 'btn-disabled' not in response.content.decode()
            assert 'disabled' not in response.content.decode()
    
    def test_html_response_structure(self, client, user, organization_id):
        """Test that all UI views return proper HTML structure"""
        client.force_login(user)
        
        # Test validation view
        validate_response = client.get(reverse('metadata:csv_validate_mapping_name'), {
            'mapping_name': 'Test Name',
            'organization': organization_id
        })
        validate_content = validate_response.content.decode()
        assert '<button' in validate_content
        assert 'hx-' in validate_content  # HTMX attributes
        
        # Test button state views
        for button_type in ['load', 'delete']:
            button_response = client.get(reverse('metadata:csv_update_button_state'), {
                'button': button_type,
                'mapping_id': 'test-id',
                'organization': organization_id
            })
            button_content = button_response.content.decode()
            assert '<button' in button_content
            assert 'hx-' in button_content
            assert f'{button_type.title()}' in button_content
