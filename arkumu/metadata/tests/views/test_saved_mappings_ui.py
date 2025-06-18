import pytest
from unittest.mock import patch, Mock
from django.contrib.auth import get_user_model
from arkumu.metadata.models.mappings import Mapping

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
        'fk_relationships': {
            'dataset1.csv|id': {
                'target_dataset': 'dataset2.csv',
                'target_column': 'user_id',
                'relationship_type': 'one_to_many'
            }
        },
        'entity_mappings': {},
        'metadata': {
            'total_datasets': 2,
            'total_columns': 6,
            'total_fk_relationships': 1
        }
    }


@pytest.fixture
def existing_mapping(user, organization_id, sample_mapping_config):
    """Create existing mapping for testing"""
    return Mapping.objects.create(
        name='Test Mapping',
        organization_id=organization_id,
        source_datasets=['dataset1.csv', 'dataset2.csv'],
        mapping_config=sample_mapping_config,
        created_by=user,
        validation_status='draft'
    )

@pytest.mark.django_db
class TestRefreshWorkspaceView:
    """Tests for RefreshWorkspaceView"""
    
    def test_refresh_workspace_success(self, client, user, organization_id):
        """Test successful workspace refresh"""
        client.force_login(user)
        
        # Mock coordinator methods
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_workspace_columns=Mock(return_value=[
                {
                    'id': 'csv::dataset1::column1',
                    'name': 'Column 1',
                    'dataset_name': 'dataset1.csv',
                    'source_name': 'csv'
                }
            ]),
            get_selected_dataset_names=Mock(return_value=['dataset1.csv']),
            _prepare_datasets_with_columns=Mock(return_value=[{
                'dataset_name': 'dataset1.csv',
                'columns': [{'id': 'csv::dataset1::column1', 'name': 'Column 1'}],
                'selected_count': 1
            }])
        ):
            response = client.get(f'/metadata/csv-refresh-workspace/?organization={organization_id}')
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'selected-columns-workspace' in content
        assert 'Column Workspace' in content
    
    def test_refresh_workspace_missing_organization(self, client, user):
        """Test workspace refresh without organization ID"""
        client.force_login(user)
        
        response = client.get('/metadata/csv-refresh-workspace/')
        
        assert response.status_code == 400
        assert 'Organization ID required' in response.content.decode()
    
    def test_refresh_workspace_error_handling(self, client, user, organization_id):
        """Test workspace refresh error handling"""
        client.force_login(user)
        
        # Mock coordinator to raise exception
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_workspace_columns=Mock(side_effect=Exception("Test error")),
        ):
            response = client.get(f'/metadata/csv-refresh-workspace/?organization={organization_id}')
        
        assert response.status_code == 500
        assert 'Failed to refresh workspace' in response.content.decode()


@pytest.mark.django_db  
class TestRefreshDatasetBadgesView:
    """Tests for RefreshDatasetBadgesView"""
    
    def test_refresh_badges_success(self, client, user, organization_id):
        """Test successful dataset badges refresh"""
        client.force_login(user)
        
        # Mock coordinator methods
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_selected_dataset_names=Mock(return_value=['dataset1.csv']),
            get_csv_datasets_for_organization=Mock(return_value=[
                {'name': 'dataset1.csv', 'source': 'csv'},
                {'name': 'dataset2.csv', 'source': 'csv'}
            ])
        ):
            response = client.get(f'/metadata/csv-refresh-dataset-badges/?organization={organization_id}')
        
        assert response.status_code == 200
        content = response.content.decode()
        # Check for actual badge content
        assert 'dataset1.csv' in content
        assert 'dataset2.csv' in content
        assert 'badge-success' in content  # dataset1.csv should be selected
        assert 'badge-outline badge-success' in content  # dataset2.csv should be unselected
        assert 'Clear All' in content  # Clear all button should be present
    
    def test_refresh_badges_missing_organization(self, client, user):
        """Test dataset badges refresh without organization ID"""
        client.force_login(user)
        
        response = client.get('/metadata/csv-refresh-dataset-badges/')
        
        assert response.status_code == 400
        assert 'Organization ID required' in response.content.decode()


@pytest.mark.django_db
class TestEnhancedMappingLoadWorkflow:
    """Integration tests for the enhanced mapping load workflow"""
    
    def test_complete_load_workflow(self, client, user, organization_id, existing_mapping):
        """Test the complete enhanced load workflow"""
        client.force_login(user)
        
        # Mock coordinator methods for both load and refresh operations
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            deserialize_mapping_state=Mock(return_value={
                'datasets_restored': 1,
                'columns_restored': 2,
                'fk_relationships_restored': 0,
                'mapping_name': 'Test Mapping'
            }),
            validate_mapping_compatibility=Mock(return_value={
                'is_valid': True,
                'warnings': [],
                'errors': []
            })
        ):
            # 1. Load the mapping via HTMX
            load_response = client.post('/metadata/csv-load-mapping-htmx/', {
                'organization': organization_id,
                'mapping_id': str(existing_mapping.id)
            })
        
        assert load_response.status_code == 200
        load_content = load_response.content.decode()
        
        # Check that the load response includes our enhanced JavaScript
        assert 'csv-refresh-workspace' in load_content
        assert 'csv-refresh-dataset-badges' in load_content
        assert 'Comprehensive UI refresh after mapping load' in load_content
        
        # 2. Test that workspace refresh would work
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_workspace_columns=Mock(return_value=[]),
            get_selected_dataset_names=Mock(return_value=[]),
            _prepare_datasets_with_columns=Mock(return_value=[])
        ):
            workspace_response = client.get(f'/metadata/csv-refresh-workspace/?organization={organization_id}')
        
        assert workspace_response.status_code == 200
        
        # 3. Test that badges refresh would work  
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_selected_dataset_names=Mock(return_value=['dataset1.csv']),
            get_csv_datasets_for_organization=Mock(return_value=[
                {'name': 'dataset1.csv', 'source': 'csv'}
            ])
        ):
            badges_response = client.get(f'/metadata/csv-refresh-dataset-badges/?organization={organization_id}')
        
        assert badges_response.status_code == 200
        badges_content = badges_response.content.decode()
        assert 'dataset1.csv' in badges_content  # Should show the loaded dataset


@pytest.mark.django_db
class TestMappingControlsIntegration:
    """Integration tests for mapping controls with enhanced workflow"""
    
    def test_mapping_controls_load_button_integration(self, client, user, organization_id, existing_mapping):
        """Test that mapping controls load button triggers enhanced workflow correctly"""
        client.force_login(user)
        
        # Mock coordinator methods for load operation
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            deserialize_mapping_state=Mock(return_value={
                'datasets_restored': 1,
                'columns_restored': 2,
                'fk_relationships_restored': 0,
                'mapping_name': 'Test Mapping'
            }),
            validate_mapping_compatibility=Mock(return_value={
                'is_valid': True,
                'warnings': [],
                'errors': []
            })
        ):
            # Simulate the load button click from mapping_controls.html
            response = client.post('/metadata/csv-load-mapping-htmx/', {
                'organization': organization_id,
                'mapping_id': str(existing_mapping.id)
            })
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Verify the enhanced workflow JavaScript is present
        assert 'csv-refresh-workspace' in content
        assert 'csv-refresh-dataset-badges' in content
        assert '#selected-columns-workspace' in content
        assert '#dataset-badges' in content
        assert 'Comprehensive UI refresh after mapping load' in content
        
        # Verify success message
        assert 'alert-success' in content
        assert 'Test Mapping' in content or 'loaded successfully' in content.lower()
    
    def test_mapping_controls_target_elements_exist(self, client, user, organization_id):
        """Test that the target elements our enhanced workflow needs actually exist"""
        client.force_login(user)
        
        # Mock coordinator methods to return data for rendering
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_ui.CSVMappingCoordinatorMixin',
            get_workspace_columns=Mock(return_value=[{
                'id': 'csv::test::column1',
                'name': 'Test Column',
                'dataset_name': 'test.csv'
            }]),
            get_selected_dataset_names=Mock(return_value=['test.csv']),
            _prepare_datasets_with_columns=Mock(return_value=[{
                'dataset_name': 'test.csv',
                'columns': [{'id': 'csv::test::column1', 'name': 'Test Column'}]
            }]),
            get_csv_datasets_for_organization=Mock(return_value=[
                {'name': 'test.csv', 'source': 'csv'}
            ])
        ):
            # Test workspace refresh endpoint
            workspace_response = client.get(f'/metadata/csv-refresh-workspace/?organization={organization_id}')
            assert workspace_response.status_code == 200
            workspace_content = workspace_response.content.decode()
            assert 'selected-columns-workspace' in workspace_content
            
            # Test dataset badges refresh endpoint  
            badges_response = client.get(f'/metadata/csv-refresh-dataset-badges/?organization={organization_id}')
            assert badges_response.status_code == 200
            badges_content = badges_response.content.decode()
            assert 'test.csv' in badges_content
            assert 'badge' in badges_content


@pytest.mark.django_db
class TestDropdownMappingsLoading:
    """Tests for debugging dropdown mappings loading issue"""
    
    def test_dropdown_lists_existing_mappings(self, client, user, organization_id, existing_mapping):
        """Test that the dropdown correctly loads existing mappings via HTMX"""
        client.force_login(user)
        
        # Simulate HTMX request (dropdown loading)
        response = client.get(
            f'/metadata/csv-list-mappings/?organization={organization_id}',
            HTTP_HX_REQUEST='true'  # This makes it an HTMX request
        )
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should contain HTML options for the dropdown
        assert '<option value="">' in content  # Default option
        assert f'<option value="{existing_mapping.id}"' in content  # Our test mapping
        assert existing_mapping.name in content  # Mapping name should appear
        assert 'datasets' in content  # Should show dataset count
        assert 'columns' in content  # Should show column count
        
        print(f"Dropdown content: {content}")  # Debug output
    
    def test_dropdown_empty_when_no_mappings(self, client, user, organization_id):
        """Test that dropdown shows only default option when no mappings exist"""
        client.force_login(user)
        
        # Test with organization that has no mappings
        response = client.get(
            f'/metadata/csv-list-mappings/?organization=nonexistent-org',
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should only contain the default option
        assert '<option value="">Select a mapping...</option>' in content
        assert content.count('<option') == 1  # Only one option (the default)
        
        print(f"Empty dropdown content: {content}")  # Debug output
    
    def test_dropdown_for_specific_organization(self, client, user, organization_id, existing_mapping):
        """Test that dropdown only shows mappings for the specific organization"""
        client.force_login(user)
        
        # Create mapping for different organization
        from arkumu.metadata.models.mappings import Mapping
        other_org_mapping = Mapping.objects.create(
            name='Other Org Mapping',
            organization_id='different-org',
            source_datasets=['test.csv'],
            mapping_config={'test': 'data'},
            created_by=user
        )
        
        # Request mappings for our organization
        response = client.get(
            f'/metadata/csv-list-mappings/?organization={organization_id}',
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 200
        content = response.content.decode()
        
        # Should contain our organization's mapping but not the other
        assert existing_mapping.name in content
        assert 'Other Org Mapping' not in content
        assert f'<option value="{existing_mapping.id}"' in content
        assert f'<option value="{other_org_mapping.id}"' not in content
        
        print(f"Organization-specific content: {content}")  # Debug output


@pytest.mark.django_db
class TestDropdownHTMXTrigger:
    """Tests for debugging HTMX trigger issues in dropdown"""
    
    def test_htmx_request_without_organization_id(self, client, user):
        """Test what happens when no organization_id is provided"""
        client.force_login(user)
        
        # Request without organization parameter
        response = client.get(
            '/metadata/csv-list-mappings/',
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 400  # Should return error
        content = response.content.decode()
        assert 'Organization ID is required' in content
        
        print(f"No org ID response: {content}")
    
    def test_htmx_request_with_empty_organization_id(self, client, user):
        """Test what happens when organization_id is empty"""
        client.force_login(user)
        
        # Request with empty organization parameter
        response = client.get(
            '/metadata/csv-list-mappings/?organization=',
            HTTP_HX_REQUEST='true'
        )
        
        assert response.status_code == 400  # Should return error
        content = response.content.decode()
        assert 'Organization ID is required' in content
        
        print(f"Empty org ID response: {content}")
    
    def test_non_htmx_request_returns_json(self, client, user, organization_id, existing_mapping):
        """Test that non-HTMX requests return JSON instead of HTML"""
        client.force_login(user)
        
        # Request without HTMX header (regular AJAX/fetch request)
        response = client.get(f'/metadata/csv-list-mappings/?organization={organization_id}')
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'
        
        import json
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'mappings' in data
        assert len(data['mappings']) == 1
        assert data['mappings'][0]['name'] == existing_mapping.name
        
        print(f"JSON response: {data}")


@pytest.mark.django_db
class TestMappingControlsTemplate:
    """Tests for mapping controls template behavior"""
    
    def test_mapping_controls_with_organization_id(self, client, user, organization_id, existing_mapping):
        """Test that mapping controls render correctly when organization_id is provided"""
        client.force_login(user)
        
        from django.template.loader import render_to_string
        from django.middleware.csrf import get_token
        from django.test import RequestFactory
        
        request = RequestFactory().get('/')
        request.user = user
        
        context = {
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        html = render_to_string(
            'csv_mapping/partials/mapping_controls.html',
            context,
            request=request
        )
        
        # Should have HTMX attributes when organization_id is present
        assert 'hx-get="/metadata/csv-list-mappings/"' in html
        assert f'"organization": "{organization_id}"' in html
        assert 'hx-trigger="load, refreshMappings from:body"' in html
        assert 'Select saved mapping...' in html
        assert 'Select organization first...' not in html
        
        print(f"Template with org ID: {html[:500]}...")
    
    def test_mapping_controls_without_organization_id(self, client, user):
        """Test that mapping controls render correctly when organization_id is missing"""
        client.force_login(user)
        
        from django.template.loader import render_to_string
        from django.middleware.csrf import get_token
        from django.test import RequestFactory
        
        request = RequestFactory().get('/')
        request.user = user
        
        context = {
            'organization_id': None,  # No organization
            'csrf_token': get_token(request),
        }
        
        html = render_to_string(
            'csv_mapping/partials/mapping_controls.html',
            context,
            request=request
        )
        
        # Should NOT have HTMX attributes when organization_id is missing
        assert 'hx-get="/metadata/csv-list-mappings/"' not in html
        assert 'hx-vals=' not in html
        assert 'Select organization first...' in html
        assert 'Select saved mapping...' not in html
        
        print(f"Template without org ID: {html[:500]}...") 