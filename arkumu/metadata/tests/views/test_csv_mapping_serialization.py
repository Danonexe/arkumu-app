"""
Test suite for CSV mapping serialization with organization_id as source identifier.

This test suite verifies the changes made to fix the column ID generation and 
serialization format to use organization_id instead of source_name as the 
source identifier in column IDs.

Key changes being tested:
- Column IDs now use format: "organization_id::dataset::column_name"  
- Serialized mappings correctly identify source as organization_id
- Parsing and filtering logic works with new format
- Coordinator mixin methods handle the new format correctly
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware

from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.csv_mapping_views import (
    CSVMappingEditorView,
    AddColumnToWorkspaceView,
    RemoveColumnFromWorkspaceView,
    ExportMappingJSONView,
    GetMappingJSONContentView
)


@pytest.fixture
def base_test_data():
    """Base test data fixture for CSV mapping serialization tests."""
    return {
        'factory': RequestFactory(),
        'organization_id': 'test_org',
        'dataset_name': 'test_dataset.csv',
        'source_name': 'test_source',  # This should NOT appear in column IDs anymore
        'column_name': 'test_column',
    }


@pytest.fixture
def expected_column_id(base_test_data):
    """Expected column ID format after our changes."""
    return f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::{base_test_data['column_name']}"


@pytest.fixture
def mock_datasets(base_test_data):
    """Mock S3 data for testing."""
    return [
        {
            'name': base_test_data['dataset_name'],
            'source': base_test_data['source_name'],
            'preview': {
                'colHeaders': ['test_column', 'another_column', 'third_column'],
                'data': [['value1', 'value2', 'value3']],
                'total_rows': 1
            }
        }
    ]


def add_session_to_request(request):
    """Add session middleware to request for testing."""
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()
    
    csrf_middleware = CsrfViewMiddleware(lambda req: None)
    csrf_middleware.process_request(request)
    return request


class TestColumnIDGeneration:
    """Test column ID generation using organization_id as source identifier."""
    
    def test_generate_column_id_with_organization_id(self, base_test_data, expected_column_id):
        """Test that generate_column_id uses organization_id as source."""
        # Test the static method directly
        column_id = CSVMappingCoordinatorMixin.generate_column_id(
            base_test_data['dataset_name'], 
            base_test_data['column_name'], 
            base_test_data['organization_id']  # Should use organization_id, not source_name
        )
        
        assert column_id == expected_column_id
        assert base_test_data['organization_id'] in column_id
        assert base_test_data['source_name'] not in column_id  # source_name should NOT be in ID
    
    def test_parse_column_id_with_organization_id(self, base_test_data, expected_column_id):
        """Test that parse_column_id correctly parses the new format."""
        parsed = CSVMappingCoordinatorMixin.parse_column_id(expected_column_id)
        
        expected_parsed = {
            'source': base_test_data['organization_id'],  # Should be organization_id
            'dataset': base_test_data['dataset_name'],
            'column': base_test_data['column_name']
        }
        
        assert parsed == expected_parsed
        assert parsed['source'] == base_test_data['organization_id']
        assert parsed['source'] != base_test_data['source_name']
    
    def test_legacy_column_id_parsing(self, base_test_data):
        """Test that legacy column IDs without organization context still parse."""
        legacy_id = f"{base_test_data['dataset_name']}::{base_test_data['column_name']}"
        parsed = CSVMappingCoordinatorMixin.parse_column_id(legacy_id)
        
        expected_parsed = {
            'source': None,
            'dataset': base_test_data['dataset_name'],
            'column': base_test_data['column_name']
        }
        
        assert parsed == expected_parsed


class TestCoordinatorMixinWithOrganizationID:
    """Test coordinator mixin methods with organization_id-based column IDs."""
    
    @pytest.fixture
    def coordinator_setup(self, base_test_data):
        """Set up coordinator and request with session."""
        coordinator = CSVMappingCoordinatorMixin()
        request = base_test_data['factory'].post('/')
        request = add_session_to_request(request)
        return {
            'coordinator': coordinator,
            'request': request
        }
    
    @pytest.mark.django_db
    def test_add_column_with_validation_uses_organization_id(self, base_test_data, expected_column_id, coordinator_setup):
        """Test that add_column_with_validation creates column ID with organization_id."""
        coordinator = coordinator_setup['coordinator']
        request = coordinator_setup['request']
        
        # Mock the dataset selection check
        with patch.object(coordinator, '_is_dataset_selected', return_value=True):
            with patch.object(coordinator, 'add_column_to_workspace') as mock_add:
                mock_add.return_value = (True, {'id': expected_column_id}, 1)
                
                success, new_column, total_columns, error = coordinator.add_column_with_validation(
                    request,
                    base_test_data['organization_id'],
                    base_test_data['column_name'],
                    base_test_data['dataset_name'],
                    base_test_data['source_name']  # This is passed but shouldn't be used in column ID
                )
                
                # Verify the method was called with the correct column ID format
                mock_add.assert_called_once()
                call_args = mock_add.call_args[0]
                column_id_used = call_args[2]  # Third argument is column_id
                
                assert column_id_used == expected_column_id
                assert base_test_data['organization_id'] in column_id_used
                assert base_test_data['source_name'] not in column_id_used
    
    @pytest.mark.django_db
    def test_batch_add_columns_with_organization_id(self, base_test_data, coordinator_setup):
        """Test batch column addition uses organization_id in column IDs."""
        coordinator = coordinator_setup['coordinator']
        request = coordinator_setup['request']
        column_names = ['col1', 'col2', 'col3']
        
        with patch.object(coordinator, 'validate_and_fix_dataset_selection_state') as mock_validate:
            mock_validate.return_value = (True, False, "Valid")
            
            with patch.object(coordinator, 'get_workspace_columns') as mock_get_workspace:
                mock_get_workspace.return_value = []
                
                with patch.object(coordinator, 'update_workspace_columns') as mock_update:
                    total_added, skipped, final_count, error = coordinator.batch_add_columns_with_validation(
                        request,
                        base_test_data['organization_id'],
                        column_names,
                        base_test_data['dataset_name'],
                        base_test_data['source_name']
                    )
                    
                    # Verify update_workspace_columns was called
                    assert mock_update.called
                    
                    # Get the columns that were added
                    added_columns = mock_update.call_args[0][2]  # Third argument is the columns list
                    
                    # Verify each column has the correct ID format with organization_id
                    for i, column in enumerate(added_columns):
                        expected_id = f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::{column_names[i]}"
                        assert column['id'] == expected_id
                        assert column['source'] == base_test_data['source_name']  # source field is separate from ID
                        assert base_test_data['organization_id'] in column['id']
    
    def test_workspace_column_filtering_with_organization_id(self, base_test_data):
        """Test that workspace column filtering works with organization_id-based IDs."""
        # Create mock workspace columns with the new ID format
        workspace_columns = [
            {
                'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1",
                'name': 'col1',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            },
            {
                'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col2", 
                'name': 'col2',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            },
            {
                'id': f"other_org::{base_test_data['dataset_name']}::col3",
                'name': 'col3',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            }
        ]
        
        # Filter columns that belong to our organization
        filtered_columns = []
        for col in workspace_columns:
            parsed = CSVMappingCoordinatorMixin.parse_column_id(col['id'])
            if parsed['source'] == base_test_data['organization_id'] and parsed['dataset'] == base_test_data['dataset_name']:
                filtered_columns.append(parsed['column'])
        
        # Should only get columns from our organization
        assert len(filtered_columns) == 2
        assert 'col1' in filtered_columns
        assert 'col2' in filtered_columns
        assert 'col3' not in filtered_columns  # Different organization


class TestSerializationFormat:
    """Test the serialization format with organization_id-based column IDs."""
    
    @pytest.fixture
    def serialization_setup(self, base_test_data):
        """Set up serialization test fixtures."""
        coordinator = CSVMappingCoordinatorMixin()
        request = base_test_data['factory'].post('/')
        request = add_session_to_request(request)
        return {
            'coordinator': coordinator,
            'request': request
        }
    
    @pytest.mark.django_db
    def test_serialize_current_mapping_state_format(self, base_test_data, serialization_setup):
        """Test that serialize_current_mapping_state produces correct format."""
        coordinator = serialization_setup['coordinator']
        request = serialization_setup['request']
        
        # Set up mock workspace data with new column ID format
        workspace_columns = [
            {
                'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1",
                'name': 'col1',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name'],
                'is_fk': True,
                'fk_config': {
                    'direction': 'outbound',
                    'target_dataset': 'target_dataset',
                    'target_column': 'target_col'
                }
            }
        ]
        
        with patch.object(coordinator, 'get_selected_dataset_names') as mock_datasets:
            mock_datasets.return_value = [base_test_data['dataset_name']]
            
            with patch.object(coordinator, 'get_workspace_columns') as mock_columns:
                mock_columns.return_value = workspace_columns
                
                mapping_config = coordinator.serialize_current_mapping_state(
                    request, 
                    base_test_data['organization_id']
                )
                
                # Verify organization_id is correct
                assert mapping_config['organization_id'] == base_test_data['organization_id']
                
                # Verify column ID format in workspace_columns
                expected_column_id = f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1"
                assert expected_column_id in mapping_config['workspace_columns']
                
                column_data = mapping_config['workspace_columns'][expected_column_id]
                assert column_data['source'] == base_test_data['source_name']  # source field separate from ID
                
                # Verify FK relationships use the correct column ID
                assert expected_column_id in mapping_config['fk_relationships']
                fk_config = mapping_config['fk_relationships'][expected_column_id]
                assert fk_config['target_dataset'] == 'target_dataset'
    
    @pytest.mark.django_db
    def test_json_export_format(self, base_test_data, serialization_setup):
        """Test that JSON export maintains the correct format."""
        request = serialization_setup['request']
        
        # Mock the coordinator's serialize method
        expected_mapping = {
            'organization_id': base_test_data['organization_id'],
            'workspace_columns': {
                f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1": {
                    'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1",
                    'name': 'col1',
                    'dataset': base_test_data['dataset_name'],
                    'source': base_test_data['source_name']
                }
            },
            'selected_datasets': [base_test_data['dataset_name']],
            'fk_relationships': {},
            'entity_mappings': {}
        }
        
        view = ExportMappingJSONView()
        
        with patch.object(view, 'get_organization_id_from_request') as mock_org_id:
            mock_org_id.return_value = base_test_data['organization_id']
            
            with patch.object(view, 'get_organization_context') as mock_org_context:
                mock_org_context.return_value = {'organization_exists': True}
                
                with patch.object(view, 'serialize_current_mapping_state') as mock_serialize:
                    mock_serialize.return_value = expected_mapping
                    
                    response = view.get(request)
                    
                    # Parse the JSON response
                    response_data = json.loads(response.content.decode())
                    
                    # Verify the organization_id is correct
                    assert response_data['organization_id'] == base_test_data['organization_id']
                    
                    # Verify column ID format
                    expected_column_id = f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1"
                    assert expected_column_id in response_data['workspace_columns']


class TestViewIntegrationWithOrganizationID:
    """Test view integration with the new organization_id-based column IDs."""
    
    @pytest.fixture
    def view_integration_setup(self, base_test_data):
        """Set up view integration test fixtures."""
        request = base_test_data['factory'].post('/', {
            'column': base_test_data['column_name'],
            'dataset': base_test_data['dataset_name'],
            'source': base_test_data['source_name']
        })
        request = add_session_to_request(request)
        return {'request': request}
    
    @pytest.mark.django_db
    @patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.S3DirectDataAnalyzer')
    def test_add_column_view_uses_organization_id(self, mock_analyzer_class, base_test_data, expected_column_id, mock_datasets, view_integration_setup):
        """Test that AddColumnToWorkspaceView creates column IDs with organization_id."""
        request = view_integration_setup['request']
        
        # Mock the analyzer
        mock_analyzer = MagicMock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.get_s3_source_summary.return_value = {
            'datasets': mock_datasets
        }
        
        view = AddColumnToWorkspaceView()
        
        with patch.object(view, 'get_organization_id_from_request') as mock_org_id:
            mock_org_id.return_value = base_test_data['organization_id']
            
            with patch.object(view, 'safe_add_column_with_validation') as mock_add:
                mock_add.return_value = (True, {'id': expected_column_id}, 1, None)
                
                with patch.object(view, 'get_workspace_columns') as mock_workspace:
                    mock_workspace.return_value = []
                    
                    with patch.object(view, '_prepare_datasets_with_columns') as mock_prepare:
                        mock_prepare.return_value = []
                        
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render_to_string') as mock_render:
                            mock_render.return_value = '<div>test</div>'
                            
                            response = view.post(request)
                            
                            # Verify the column was added with correct organization_id format
                            mock_add.assert_called_once_with(
                                request,
                                base_test_data['organization_id'],
                                base_test_data['column_name'],
                                base_test_data['dataset_name'],
                                base_test_data['source_name']
                            )
    
    @pytest.mark.django_db
    @patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.S3DirectDataAnalyzer')
    def test_remove_column_view_uses_organization_id(self, mock_analyzer_class, base_test_data, expected_column_id, mock_datasets, view_integration_setup):
        """Test that RemoveColumnFromWorkspaceView uses organization_id-based column IDs."""
        request = view_integration_setup['request']
        
        # Mock the analyzer
        mock_analyzer = MagicMock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.get_s3_source_summary.return_value = {
            'datasets': mock_datasets
        }
        
        view = RemoveColumnFromWorkspaceView()
        
        # Mock workspace with a column that has the new ID format
        workspace_columns = [
            {
                'id': expected_column_id,
                'name': base_test_data['column_name'],
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            }
        ]
        
        with patch.object(view, 'get_organization_id_from_request') as mock_org_id:
            mock_org_id.return_value = base_test_data['organization_id']
            
            with patch.object(view, 'get_workspace_columns') as mock_workspace:
                mock_workspace.return_value = workspace_columns
                
                with patch.object(view, 'update_workspace_columns') as mock_update:
                    with patch.object(view, '_prepare_datasets_with_columns') as mock_prepare:
                        mock_prepare.return_value = []
                        
                        with patch('arkumu.metadata.views.csv_mapping.csv_mapping_views.render_to_string') as mock_render:
                            mock_render.return_value = '<div>test</div>'
                            
                            response = view.post(request)
                            
                            # Verify the column was removed (empty list passed to update)
                            mock_update.assert_called_once_with(
                                request,
                                base_test_data['organization_id'],
                                []  # Column should be removed
                            )


class TestColumnFiltering:
    """Test column filtering logic with organization_id-based IDs."""
    
    def test_filter_columns_by_organization_and_dataset(self, base_test_data):
        """Test filtering workspace columns by organization and dataset."""
        # Create workspace with mixed organization and dataset columns
        workspace_columns = [
            # Correct organization and dataset
            {
                'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::col1",
                'name': 'col1',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            },
            # Correct organization, different dataset  
            {
                'id': f"{base_test_data['organization_id']}::other_dataset.csv::col2",
                'name': 'col2', 
                'dataset': 'other_dataset.csv',
                'source': base_test_data['source_name']
            },
            # Different organization, same dataset
            {
                'id': f"other_org::{base_test_data['dataset_name']}::col3",
                'name': 'col3',
                'dataset': base_test_data['dataset_name'],
                'source': base_test_data['source_name']
            }
        ]
        
        # Filter columns - this simulates the logic used in the views
        filtered_columns = []
        for col_dict in workspace_columns:
            col_id = col_dict.get('id')
            if col_id:
                parsed = CSVMappingCoordinatorMixin.parse_column_id(col_id)
                # This is the key comparison that was fixed
                if parsed['dataset'] == base_test_data['dataset_name'] and parsed['source'] == base_test_data['organization_id']:
                    filtered_columns.append(parsed['column'])
        
        # Should only get col1 (correct org + dataset)
        assert len(filtered_columns) == 1
        assert filtered_columns[0] == 'col1'
    
    def test_backward_compatibility_with_legacy_ids(self, base_test_data):
        """Test that the system handles legacy column IDs gracefully."""
        # Mix of new format and legacy format
        workspace_columns = [
            # New format
            {
                'id': f"{base_test_data['organization_id']}::{base_test_data['dataset_name']}::new_col",
                'name': 'new_col'
            },
            # Legacy format (no organization prefix)
            {
                'id': f"{base_test_data['dataset_name']}::legacy_col",
                'name': 'legacy_col'
            },
            # Very old format (just column name)
            {
                'id': 'very_old_col',
                'name': 'very_old_col'
            }
        ]
        
        new_format_count = 0
        legacy_format_count = 0
        
        for col_dict in workspace_columns:
            col_id = col_dict.get('id')
            parsed = CSVMappingCoordinatorMixin.parse_column_id(col_id)
            
            if parsed['source'] == base_test_data['organization_id']:
                new_format_count += 1
            elif parsed['source'] is None:
                legacy_format_count += 1
        
        assert new_format_count == 1  # Only the new format column
        assert legacy_format_count == 2  # Legacy and very old format


