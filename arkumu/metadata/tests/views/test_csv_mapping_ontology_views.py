"""
Test CSV Mapping External Ontology Views

Tests for external ontology configuration functionality including:
- Toggle ontology forms 
- Save/remove ontology configurations
- Validate ontology identifiers
- Support for multiple ontologies per column
"""

import pytest
import json
from unittest.mock import Mock, patch
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse

from arkumu.metadata.views.csv_mapping.views.ontology_views import (
    ToggleExternalOntologyFormView,
    SaveInlineExternalOntologyView,
    HideExternalOntologyFormView, 
    RemoveExternalOntologyView,
    RemoveIndividualExternalOntologyView,
    ValidateExternalOntologyIdentifierView
)


@pytest.fixture
def request_factory():
    """Request factory for creating mock requests."""
    return RequestFactory()


@pytest.fixture
def organization_id():
    """Test organization ID."""
    return "test-org-123"


@pytest.fixture
def user():
    """Test user fixture."""
    from django.contrib.auth.models import User
    return User.objects.create_user(username='testuser', password='testpass')


@pytest.fixture
def sample_column_data():
    """Sample column data for testing."""
    return {
        'id': 'test-org-123::dataset1::column1',
        'name': 'column1',
        'dataset': 'dataset1',
        'source': 'test-org-123',
        'is_external_ontology': False,
        'external_ontologies': []
    }


@pytest.fixture
def sample_column_with_ontologies():
    """Sample column data with multiple ontologies."""
    return {
        'id': 'test-org-123::dataset1::column1',
        'name': 'column1', 
        'dataset': 'dataset1',
        'source': 'test-org-123',
        'is_external_ontology': True,
        'external_ontologies': [
            {
                'ontology_type': 'orcid',
                'uri_template': 'https://orcid.org/{identifier}',
                'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
                'validation_enabled': True
            },
            {
                'ontology_type': 'wikidata', 
                'uri_template': 'https://www.wikidata.org/wiki/{identifier}',
                'identifier_pattern': r'^Q\d+$',
                'validation_enabled': True
            }
        ]
    }


@pytest.fixture
def sample_column_legacy_ontology():
    """Sample column data with legacy single ontology format."""
    return {
        'id': 'test-org-123::dataset1::column1',
        'name': 'column1',
        'dataset': 'dataset1', 
        'source': 'test-org-123',
        'is_external_ontology': True,
        'external_ontology': {
            'ontology_type': 'orcid',
            'uri_template': 'https://orcid.org/{identifier}',
            'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
            'validation_enabled': True
        }
    }


@pytest.fixture
def mock_coordinator_methods():
    """Mock coordinator methods for testing."""
    return {
        'get_organization_id_from_request': Mock(return_value='test-org-123'),
        'get_workspace_columns': Mock(return_value=[]),
        'get_unified_column_by_id': Mock(return_value=None),
        'update_workspace_columns': Mock(),
        'render_column_item_template': Mock(return_value='<div>column item</div>'),
        'render_workspace_template': Mock(return_value='<div>workspace</div>')
    }


def add_session_to_request(request):
    """Add session middleware to request for testing."""
    middleware = SessionMiddleware(lambda x: x)
    middleware.process_request(request)
    request.session.save()
    return request


@pytest.mark.django_db
class TestToggleExternalOntologyFormView:
    """Test ToggleExternalOntologyFormView functionality."""
    
    def test_post_missing_column_id(self, request_factory, mock_coordinator_methods):
        """Test POST request with missing column_id returns error."""
        request = request_factory.post('/test/', {})
        request = add_session_to_request(request)
        
        view = ToggleExternalOntologyFormView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        assert 'Column ID required' in response.content.decode()
    
    def test_post_column_not_found(self, request_factory, mock_coordinator_methods):
        """Test POST request with column not found in workspace."""
        request = request_factory.post('/test/', {'column_id': 'nonexistent'})
        request = add_session_to_request(request)
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_unified_column_by_id'] = Mock(return_value=None)
        
        view = ToggleExternalOntologyFormView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        assert 'Column not found' in response.content.decode()
    
    def test_post_success_renders_form(self, request_factory, mock_coordinator_methods, sample_column_data):
        """Test successful POST request renders ontology form."""
        request = request_factory.post('/test/', {'column_id': 'test-col-1'})
        request = add_session_to_request(request)
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_unified_column_by_id'] = Mock(return_value=sample_column_data)
        
        view = ToggleExternalOntologyFormView()
        with patch.multiple(view, **mock_methods), \
             patch('arkumu.metadata.views.csv_mapping.views.ontology_views.render_to_string') as mock_render:
            mock_render.return_value = '<form>ontology form</form>'
            response = view.post(request)
        
        assert response.status_code == 200
        mock_render.assert_called_once()


@pytest.mark.django_db  
class TestSaveInlineExternalOntologyView:
    """Test SaveInlineExternalOntologyView functionality."""
    
    def test_post_missing_required_fields(self, request_factory, mock_coordinator_methods):
        """Test POST request with missing required fields returns error."""
        request = request_factory.post('/test/', {})
        request = add_session_to_request(request)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        assert 'Missing required fields' in response.content.decode()
    
    def test_post_custom_ontology_missing_uri_template(self, request_factory, mock_coordinator_methods):
        """Test POST request for custom ontology without URI template returns error."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'custom'
        })
        request = add_session_to_request(request)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        assert 'URI template is required' in response.content.decode()
    
    def test_post_add_first_ontology_to_column(self, request_factory, mock_coordinator_methods, sample_column_data):
        """Test adding first ontology to a column."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'orcid',
            'uri_template': 'https://orcid.org/{identifier}',
            'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_data.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify column was updated
        updated_column = workspace_columns[0]
        assert updated_column['is_external_ontology'] is True
        assert len(updated_column['external_ontologies']) == 1
        assert updated_column['external_ontologies'][0]['ontology_type'] == 'orcid'
        
        assert response.status_code == 200
        mock_methods['update_workspace_columns'].assert_called_once()
    
    def test_post_add_second_ontology_to_column(self, request_factory, mock_coordinator_methods, sample_column_with_ontologies):
        """Test adding second ontology to a column that already has one."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'gnd',
            'uri_template': 'https://d-nb.info/gnd/{identifier}',
            'identifier_pattern': r'^\d{8,9}[\dX]$'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_with_ontologies.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify third ontology was added
        updated_column = workspace_columns[0]
        assert len(updated_column['external_ontologies']) == 3
        assert updated_column['external_ontologies'][2]['ontology_type'] == 'gnd'
        
        assert response.status_code == 200
    
    def test_post_update_existing_ontology_type(self, request_factory, mock_coordinator_methods, sample_column_with_ontologies):
        """Test updating an existing ontology type in the list."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'orcid',  # Same type as first ontology
            'uri_template': 'https://orcid.org/{identifier}',
            'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
            'validation_enabled': 'off'  # Changed from True to False
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_with_ontologies.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify existing ontology was updated, not added
        updated_column = workspace_columns[0]
        assert len(updated_column['external_ontologies']) == 2  # Still 2, not 3
        assert updated_column['external_ontologies'][0]['validation_enabled'] is False
        
        assert response.status_code == 200
    
    def test_post_migrate_legacy_format(self, request_factory, mock_coordinator_methods, sample_column_legacy_ontology):
        """Test migration from legacy single ontology format to multiple format."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'wikidata',
            'uri_template': 'https://www.wikidata.org/wiki/{identifier}',
            'identifier_pattern': r'^Q\d+$'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_legacy_ontology.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = SaveInlineExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify legacy format was migrated and new ontology added
        updated_column = workspace_columns[0]
        assert 'external_ontology' not in updated_column
        assert len(updated_column['external_ontologies']) == 2
        assert updated_column['external_ontologies'][0]['ontology_type'] == 'orcid'  # Migrated
        assert updated_column['external_ontologies'][1]['ontology_type'] == 'wikidata'  # New
        
        assert response.status_code == 200


@pytest.mark.django_db
class TestRemoveExternalOntologyView:
    """Test RemoveExternalOntologyView functionality."""
    
    def test_post_removes_all_ontologies(self, request_factory, mock_coordinator_methods, sample_column_with_ontologies):
        """Test removing all external ontologies from a column."""
        request = request_factory.post('/test/', {'column_id': 'test-col-1'})
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_with_ontologies.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = RemoveExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify all ontologies were removed
        updated_column = workspace_columns[0]
        assert updated_column['is_external_ontology'] is False
        assert updated_column['external_ontologies'] == []
        assert updated_column['external_ontology'] == {}
        
        assert response.status_code == 200
        mock_methods['update_workspace_columns'].assert_called_once()


@pytest.mark.django_db
class TestRemoveIndividualExternalOntologyView:
    """Test RemoveIndividualExternalOntologyView functionality."""
    
    def test_post_missing_required_fields(self, request_factory, mock_coordinator_methods):
        """Test POST request with missing required fields returns error."""
        request = request_factory.post('/test/', {})
        request = add_session_to_request(request)
        
        view = RemoveIndividualExternalOntologyView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        assert 'Missing required fields' in response.content.decode()
    
    def test_post_remove_specific_ontology(self, request_factory, mock_coordinator_methods, sample_column_with_ontologies):
        """Test removing a specific ontology from the list."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'orcid'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_with_ontologies.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = RemoveIndividualExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify only ORCID was removed, Wikidata remains
        updated_column = workspace_columns[0]
        assert len(updated_column['external_ontologies']) == 1
        assert updated_column['external_ontologies'][0]['ontology_type'] == 'wikidata'
        assert updated_column['is_external_ontology'] is True  # Still has ontologies
        
        assert response.status_code == 200
    
    def test_post_remove_last_ontology(self, request_factory, mock_coordinator_methods):
        """Test removing the last ontology marks column as not having external ontology."""
        sample_column = {
            'id': 'test-col-1',
            'is_external_ontology': True,
            'external_ontologies': [
                {'ontology_type': 'orcid', 'uri_template': 'https://orcid.org/{identifier}'}
            ]
        }
        
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1', 
            'ontology_type': 'orcid'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = RemoveIndividualExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify column no longer marked as having external ontology
        updated_column = workspace_columns[0]
        assert updated_column['is_external_ontology'] is False
        assert len(updated_column['external_ontologies']) == 0
        
        assert response.status_code == 200
    
    def test_post_remove_from_legacy_format(self, request_factory, mock_coordinator_methods, sample_column_legacy_ontology):
        """Test removing ontology from legacy single ontology format."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'ontology_type': 'orcid'
        })
        request = add_session_to_request(request)
        
        workspace_columns = [sample_column_legacy_ontology.copy()]
        
        mock_methods = mock_coordinator_methods.copy()
        mock_methods['get_workspace_columns'] = Mock(return_value=workspace_columns)
        
        view = RemoveIndividualExternalOntologyView()
        with patch.multiple(view, **mock_methods):
            response = view.post(request)
        
        # Verify legacy ontology was removed
        updated_column = workspace_columns[0]
        assert updated_column['is_external_ontology'] is False
        assert updated_column['external_ontology'] == {}
        
        assert response.status_code == 200


@pytest.mark.django_db
class TestValidateExternalOntologyIdentifierView:
    """Test ValidateExternalOntologyIdentifierView functionality."""
    
    @pytest.mark.parametrize("ontology_type,identifier,pattern,expected_valid", [
        ('orcid', '0000-0002-1825-0097', r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$', True),
        ('orcid', '0000-0002-1825-009X', r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$', True),
        ('orcid', 'invalid-orcid', r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$', False),
        ('wikidata', 'Q42', r'^Q\d+$', True),
        ('wikidata', 'Q123456', r'^Q\d+$', True),
        ('wikidata', 'invalid', r'^Q\d+$', False),
        ('gnd', '118540238', r'^\d{8,9}[\dX]$', True),
        ('gnd', '11854023X', r'^\d{8,9}[\dX]$', True),
        ('gnd', 'invalid', r'^\d{8,9}[\dX]$', False),
    ])
    def test_identifier_validation_patterns(self, request_factory, mock_coordinator_methods, 
                                          ontology_type, identifier, pattern, expected_valid):
        """Test identifier validation with various patterns."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'identifier': identifier,
            'ontology_type': ontology_type,
            'identifier_pattern': pattern
        })
        request = add_session_to_request(request)
        
        view = ValidateExternalOntologyIdentifierView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        response_data = json.loads(response.content.decode())
        assert response_data['valid'] == expected_valid
        assert response_data['identifier'] == identifier
        assert response_data['ontology_type'] == ontology_type
    
    def test_post_missing_required_fields(self, request_factory, mock_coordinator_methods):
        """Test POST request with missing required fields returns error."""
        request = request_factory.post('/test/', {})
        request = add_session_to_request(request)
        
        view = ValidateExternalOntologyIdentifierView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        response_data = json.loads(response.content.decode())
        assert response_data['valid'] is False
        assert 'error' in response_data
    
    def test_post_no_pattern_returns_valid(self, request_factory, mock_coordinator_methods):
        """Test validation without pattern returns valid."""
        request = request_factory.post('/test/', {
            'column_id': 'test-col-1',
            'identifier': 'any-identifier',
            'ontology_type': 'custom'
            # No identifier_pattern provided
        })
        request = add_session_to_request(request)
        
        view = ValidateExternalOntologyIdentifierView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.post(request)
        
        assert response.status_code == 200
        response_data = json.loads(response.content.decode())
        assert response_data['valid'] is True


@pytest.mark.django_db  
class TestHideExternalOntologyFormView:
    """Test HideExternalOntologyFormView functionality."""
    
    def test_get_returns_empty_form_div(self, request_factory, mock_coordinator_methods):
        """Test GET request returns empty div to hide form."""
        request = request_factory.get('/test/', {'column_id': 'test-col-1'})
        request = add_session_to_request(request)
        
        view = HideExternalOntologyFormView()
        with patch.multiple(view, **mock_coordinator_methods):
            response = view.get(request)
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'external-ontology-form-test-col-1' in content
        assert '<div id=' in content