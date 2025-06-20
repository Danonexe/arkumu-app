"""
Tests for CSV Mapping Persistence API Views

Tests all CRUD operations for saved mapping configurations including
success cases, error handling, validation, and HTMX responses.
"""

import pytest
import json
from unittest.mock import patch, Mock
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.saved_mappings_api import (
    SaveMappingView, LoadMappingView, ListMappingsView, DeleteMappingView, UpdateMappingView
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


@pytest.fixture
def request_factory():
    """Django request factory"""
    return RequestFactory()


@pytest.fixture
def mock_coordinator_methods():
    """Mock coordinator mixin methods"""
    with patch.multiple(
        'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
        serialize_current_mapping_state=Mock(return_value={
            'version': '1.0',
            'organization_id': 'test-org-123',
            'selected_datasets': ['dataset1.csv', 'dataset2.csv'],
            'workspace_columns': {
                'test-org-123::dataset1.csv::id': {'name': 'id', 'dataset': 'dataset1.csv', 'source': 'csv'},
                'test-org-123::dataset2.csv::name': {'name': 'name', 'dataset': 'dataset2.csv', 'source': 'csv'}
            },
            'fk_relationships': {},
            'entity_mappings': {},
            'metadata': {
                'total_datasets': 2,
                'total_columns': 2,
                'total_fk_relationships': 0
            }
        }),
        deserialize_mapping_state=Mock(return_value={'restored': True}),
        validate_mapping_compatibility=Mock(return_value={
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'missing_datasets': []
        }),
        get_csv_datasets_for_organization=Mock(return_value=[
            {'name': 'dataset1.csv'},
            {'name': 'dataset2.csv'}
        ])
    ) as mocked:
        yield mocked


@pytest.mark.django_db
class TestSaveMappingView:
    """Tests for SaveMappingView"""
    
    def test_save_mapping_success(self, client, user, organization_id, mock_coordinator_methods):
        """Test successful mapping save"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_name': 'New Test Mapping'
        }
        
        response = client.post(reverse('metadata:csv_save_mapping'), data)
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert response_data['mapping_name'] == 'New Test Mapping'
        assert 'mapping_id' in response_data
        
        # Verify mapping was created in database
        mapping = Mapping.objects.get(name='New Test Mapping')
        assert mapping.organization_id == organization_id
        assert mapping.created_by == user
    
    def test_save_mapping_missing_organization(self, client, user):
        """Test save mapping without organization ID"""
        client.force_login(user)
        
        data = {'mapping_name': 'Test Mapping'}
        response = client.post(reverse('metadata:csv_save_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Organization ID is required' in response_data['error']
    
    def test_save_mapping_missing_name(self, client, user, organization_id):
        """Test save mapping without mapping name"""
        client.force_login(user)
        
        data = {'organization': organization_id}
        response = client.post(reverse('metadata:csv_save_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Mapping name is required' in response_data['error']
    
    def test_save_mapping_duplicate_name(self, client, user, organization_id, existing_mapping):
        """Test save mapping with duplicate name"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_name': existing_mapping.name  # Same name as existing mapping
        }
        
        response = client.post(reverse('metadata:csv_save_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'already exists' in response_data['error']
    
    def test_save_mapping_empty_name(self, client, user, organization_id):
        """Test save mapping with empty/whitespace name"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_name': '   '  # Whitespace only
        }
        
        response = client.post(reverse('metadata:csv_save_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Mapping name is required' in response_data['error']
    
    @patch('arkumu.metadata.views.csv_mapping.saved_mappings_api.logger')
    def test_save_mapping_exception_handling(self, mock_logger, client, user, organization_id):
        """Test exception handling during save"""
        # Mock serialize method to raise exception
        with patch('arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin.serialize_current_mapping_state', side_effect=Exception("Test error")):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_name': 'Test Mapping'
            }
            
            response = client.post(reverse('metadata:csv_save_mapping'), data)
            
            assert response.status_code == 500
            response_data = json.loads(response.content)
            assert 'Failed to save mapping' in response_data['error']
            mock_logger.error.assert_called()
    
    def test_save_mapping_invalid_configuration(self, client, user, organization_id):
        """Test save mapping with invalid configuration"""
        # Mock coordinator to return invalid mapping config
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            serialize_current_mapping_state=Mock(return_value={
                'selected_datasets': ['nonexistent_dataset.csv'],
                'workspace_columns': {},  # Empty workspace
                'fk_relationships': {},
                'metadata': {'total_datasets': 1, 'total_columns': 0, 'total_fk_relationships': 0}
            }),
            get_csv_datasets_for_organization=Mock(return_value=[
                {'name': 'existing_dataset.csv'}  # Different dataset
            ])
        ):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_name': 'Invalid Mapping'
            }
            
            response = client.post(reverse('metadata:csv_save_mapping'), data)
            
            assert response.status_code == 400
            response_data = json.loads(response.content)
            assert 'Mapping is not valid' in response_data['error']
            assert 'validation_errors' in response_data


@pytest.mark.django_db
class TestLoadMappingView:
    """Tests for LoadMappingView"""
    
    def test_load_mapping_success(self, client, user, organization_id, existing_mapping, mock_coordinator_methods):
        """Test successful mapping load"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id)
        }
        
        response = client.post(reverse('metadata:csv_load_mapping'), data)
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert response_data['mapping_name'] == existing_mapping.name
        assert 'summary' in response_data
    
    def test_load_mapping_missing_organization(self, client, user, existing_mapping):
        """Test load mapping without organization ID"""
        client.force_login(user)
        
        data = {'mapping_id': str(existing_mapping.id)}
        response = client.post(reverse('metadata:csv_load_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Organization ID is required' in response_data['error']
    
    def test_load_mapping_missing_id(self, client, user, organization_id):
        """Test load mapping without mapping ID"""
        client.force_login(user)
        
        data = {'organization': organization_id}
        response = client.post(reverse('metadata:csv_load_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Mapping ID is required' in response_data['error']
    
    def test_load_mapping_not_found(self, client, user, organization_id, mock_coordinator_methods):
        """Test load mapping with non-existent ID"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_id': '00000000-0000-0000-0000-000000000000'  # Non-existent UUID
        }
        
        response = client.post(reverse('metadata:csv_load_mapping'), data)
        
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert 'not found' in response_data['error']
    
    def test_load_mapping_wrong_organization(self, client, user, existing_mapping, mock_coordinator_methods):
        """Test load mapping with wrong organization ID"""
        client.force_login(user)
        
        data = {
            'organization': 'wrong-org-id',
            'mapping_id': str(existing_mapping.id)
        }
        
        response = client.post(reverse('metadata:csv_load_mapping'), data)
        
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert 'not found' in response_data['error']
    
    def test_load_mapping_incompatible(self, client, user, organization_id, existing_mapping):
        """Test load mapping that's incompatible with current datasets"""
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            validate_mapping_compatibility=Mock(return_value={
                'is_valid': False,
                'errors': ['Dataset not found'],
                'warnings': [],
                'missing_datasets': ['missing_dataset.csv']
            })
        ):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_id': str(existing_mapping.id)
            }
            
            response = client.post(reverse('metadata:csv_load_mapping'), data)
            
            assert response.status_code == 400
            response_data = json.loads(response.content)
            assert 'not compatible' in response_data['error']
            assert 'validation_errors' in response_data
            assert 'missing_datasets' in response_data
    
    def test_load_mapping_with_warnings(self, client, user, organization_id, existing_mapping):
        """Test load mapping with compatibility warnings"""
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            validate_mapping_compatibility=Mock(return_value={
                'is_valid': True,
                'errors': [],
                'warnings': ['Some columns have changed'],
                'missing_datasets': []
            }),
            deserialize_mapping_state=Mock(return_value={'restored': True})
        ):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_id': str(existing_mapping.id)
            }
            
            response = client.post(reverse('metadata:csv_load_mapping'), data)
            
            assert response.status_code == 200
            response_data = json.loads(response.content)
            assert response_data['success'] is True
            assert 'warnings' in response_data
            assert len(response_data['warnings']) > 0


@pytest.mark.django_db
class TestListMappingsView:
    """Tests for ListMappingsView"""
    
    def test_list_mappings_json_response(self, client, user, organization_id, existing_mapping):
        """Test list mappings returns JSON for API calls"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert 'mappings' in response_data
        assert len(response_data['mappings']) == 1
        
        mapping_data = response_data['mappings'][0]
        assert mapping_data['name'] == existing_mapping.name
        assert mapping_data['id'] == str(existing_mapping.id)
        assert 'created_at' in mapping_data
        assert 'created_by' in mapping_data
    
    def test_list_mappings_htmx_response(self, client, user, organization_id, existing_mapping):
        """Test list mappings returns HTML options for HTMX requests"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        }, headers={'HX-Request': 'true'})
        
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/html; charset=utf-8'
        
        content = response.content.decode()
        assert '<option value="">' in content  # Default option
        assert f'<option value="{existing_mapping.id}"' in content
        assert existing_mapping.name in content
    
    def test_list_mappings_missing_organization(self, client, user):
        """Test list mappings without organization ID"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_list_mappings'))
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Organization ID is required' in response_data['error']
    
    def test_list_mappings_empty_result(self, client, user, organization_id):
        """Test list mappings with no existing mappings"""
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert len(response_data['mappings']) == 0
        assert response_data['total_count'] == 0
    
    def test_list_mappings_multiple_mappings(self, client, user, organization_id, sample_mapping_config):
        """Test list mappings with multiple mappings"""
        # Create multiple mappings
        mappings = []
        for i in range(3):
            mapping = Mapping.objects.create(
                name=f'Test Mapping {i+1}',
                organization_id=organization_id,
                source_datasets=[f'dataset{i+1}.csv'],
                mapping_config=sample_mapping_config,
                created_by=user,
                validation_status='draft'
            )
            mappings.append(mapping)
        
        client.force_login(user)
        
        response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert len(response_data['mappings']) == 3
        assert response_data['total_count'] == 3
        
        # Check ordering (should be newest first)
        mapping_names = [m['name'] for m in response_data['mappings']]
        assert mapping_names == ['Test Mapping 3', 'Test Mapping 2', 'Test Mapping 1']


@pytest.mark.django_db
class TestDeleteMappingView:
    """Tests for DeleteMappingView"""
    
    def test_delete_mapping_success(self, client, user, organization_id, existing_mapping):
        """Test successful mapping deletion"""
        client.force_login(user)
        mapping_id = str(existing_mapping.id)
        
        data = {
            'organization': organization_id,
            'mapping_id': mapping_id
        }
        
        response = client.post(reverse('metadata:csv_delete_mapping'), data)
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert 'deleted successfully' in response_data['message']
        
        # Verify mapping was deleted from database
        assert not Mapping.objects.filter(id=mapping_id).exists()
    
    def test_delete_mapping_missing_organization(self, client, user, existing_mapping):
        """Test delete mapping without organization ID"""
        client.force_login(user)
        
        data = {'mapping_id': str(existing_mapping.id)}
        response = client.post(reverse('metadata:csv_delete_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Organization ID is required' in response_data['error']
    
    def test_delete_mapping_missing_id(self, client, user, organization_id):
        """Test delete mapping without mapping ID"""
        client.force_login(user)
        
        data = {'organization': organization_id}
        response = client.post(reverse('metadata:csv_delete_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Mapping ID is required' in response_data['error']
    
    def test_delete_mapping_not_found(self, client, user, organization_id):
        """Test delete mapping with non-existent ID"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_id': '00000000-0000-0000-0000-000000000000'  # Non-existent UUID
        }
        
        response = client.post(reverse('metadata:csv_delete_mapping'), data)
        
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert 'not found' in response_data['error']
    
    def test_delete_mapping_wrong_organization(self, client, user, existing_mapping):
        """Test delete mapping with wrong organization ID"""
        client.force_login(user)
        
        data = {
            'organization': 'wrong-org-id',
            'mapping_id': str(existing_mapping.id)
        }
        
        response = client.post(reverse('metadata:csv_delete_mapping'), data)
        
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert 'not found' in response_data['error']


@pytest.mark.django_db
class TestViewIntegration:
    """Integration tests across multiple views"""
    
    def test_save_load_delete_workflow(self, client, user, organization_id, mock_coordinator_methods):
        """Test complete save -> load -> delete workflow"""
        client.force_login(user)
        
        # 1. Save mapping
        save_data = {
            'organization': organization_id,
            'mapping_name': 'Workflow Test Mapping'
        }
        save_response = client.post(reverse('metadata:csv_save_mapping'), save_data)
        assert save_response.status_code == 200
        
        save_result = json.loads(save_response.content)
        mapping_id = save_result['mapping_id']
        
        # 2. List mappings
        list_response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        assert list_response.status_code == 200
        
        list_result = json.loads(list_response.content)
        assert len(list_result['mappings']) == 1
        assert list_result['mappings'][0]['id'] == mapping_id
        
        # 3. Load mapping
        load_data = {
            'organization': organization_id,
            'mapping_id': mapping_id
        }
        load_response = client.post(reverse('metadata:csv_load_mapping'), load_data)
        assert load_response.status_code == 200
        
        # 4. Delete mapping
        delete_data = {
            'organization': organization_id,
            'mapping_id': mapping_id
        }
        delete_response = client.post(reverse('metadata:csv_delete_mapping'), delete_data)
        assert delete_response.status_code == 200
        
        # 5. Verify mapping is gone
        final_list_response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        final_list_result = json.loads(final_list_response.content)
        assert len(final_list_result['mappings']) == 0
    
    def test_concurrent_operations(self, client, user, organization_id, mock_coordinator_methods):
        """Test handling of concurrent operations"""
        client.force_login(user)
        
        # Create multiple mappings with similar names
        mapping_names = ['Test A', 'Test B', 'Test C']
        created_ids = []
        
        for name in mapping_names:
            data = {
                'organization': organization_id,
                'mapping_name': name
            }
            response = client.post(reverse('metadata:csv_save_mapping'), data)
            assert response.status_code == 200
            
            result = json.loads(response.content)
            created_ids.append(result['mapping_id'])
        
        # List all mappings
        list_response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        list_result = json.loads(list_response.content)
        assert len(list_result['mappings']) == 3
        
        # Delete one mapping
        delete_data = {
            'organization': organization_id,
            'mapping_id': created_ids[1]  # Delete middle one
        }
        delete_response = client.post(reverse('metadata:csv_delete_mapping'), delete_data)
        assert delete_response.status_code == 200
        
        # Verify only 2 remain
        final_list_response = client.get(reverse('metadata:csv_list_mappings'), {
            'organization': organization_id
        })
        final_list_result = json.loads(final_list_response.content)
        assert len(final_list_result['mappings']) == 2
        
        remaining_ids = [m['id'] for m in final_list_result['mappings']]
        assert created_ids[0] in remaining_ids
        assert created_ids[1] not in remaining_ids  # This one was deleted
        assert created_ids[2] in remaining_ids


@pytest.mark.django_db
class TestUpdateMappingView:
    """Tests for UpdateMappingView"""
    
    def test_update_mapping_success(self, client, user, organization_id, existing_mapping, mock_coordinator_methods):
        """Test successful mapping update"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id),
            'mapping_name': 'Updated Mapping Name'
        }
        
        response = client.post(reverse('metadata:csv_update_mapping'), data)
        
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert response_data['mapping_name'] == 'Updated Mapping Name'
        assert response_data['updated'] is True
        
        # Verify mapping was updated in database
        existing_mapping.refresh_from_db()
        assert existing_mapping.name == 'Updated Mapping Name'
    
    def test_update_mapping_missing_organization(self, client, user, existing_mapping):
        """Test update mapping without organization ID"""
        client.force_login(user)
        
        data = {
            'mapping_id': str(existing_mapping.id),
            'mapping_name': 'Updated Name'
        }
        response = client.post(reverse('metadata:csv_update_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Organization ID is required' in response_data['error']
    
    def test_update_mapping_missing_id(self, client, user, organization_id):
        """Test update mapping without mapping ID"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_name': 'Updated Name'
        }
        response = client.post(reverse('metadata:csv_update_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'Mapping ID is required' in response_data['error']
    
    def test_update_mapping_not_found(self, client, user, organization_id, mock_coordinator_methods):
        """Test update mapping with non-existent ID"""
        client.force_login(user)
        
        data = {
            'organization': organization_id,
            'mapping_id': '00000000-0000-0000-0000-000000000000',
            'mapping_name': 'Updated Name'
        }
        
        response = client.post(reverse('metadata:csv_update_mapping'), data)
        
        assert response.status_code == 404
        response_data = json.loads(response.content)
        assert 'not found' in response_data['error']
    
    def test_update_mapping_duplicate_name(self, client, user, organization_id, existing_mapping, mock_coordinator_methods):
        """Test update mapping with name that would create duplicate"""
        client.force_login(user)
        
        # Create another mapping
        other_mapping = Mapping.objects.create(
            name='Other Mapping',
            organization_id=organization_id,
            source_datasets=[],
            mapping_config={},
            created_by=user
        )
        
        # Try to update existing_mapping to have same name as other_mapping
        data = {
            'organization': organization_id,
            'mapping_id': str(existing_mapping.id),
            'mapping_name': 'Other Mapping'  # This should conflict
        }
        
        response = client.post(reverse('metadata:csv_update_mapping'), data)
        
        assert response.status_code == 400
        response_data = json.loads(response.content)
        assert 'already exists' in response_data['error']


@pytest.mark.django_db
class TestColumnIDCompatibility:
    """Test compatibility of saved mappings API with new organization_id column format"""
    
    def test_save_mapping_with_new_column_format(self, client, user, organization_id):
        """Test saving mapping with new organization_id::dataset::column format"""
        # Mock serialization to return new format
        new_format_config = {
            'version': '1.0',
            'organization_id': organization_id,
            'selected_datasets': ['test_dataset.csv'],
            'workspace_columns': {
                f'{organization_id}::test_dataset.csv::id': {
                    'name': 'id', 
                    'dataset': 'test_dataset.csv', 
                    'source': 'test_source'
                },
                f'{organization_id}::test_dataset.csv::name': {
                    'name': 'name', 
                    'dataset': 'test_dataset.csv', 
                    'source': 'test_source'
                }
            },
            'fk_relationships': {},
            'entity_mappings': {},
            'metadata': {
                'total_datasets': 1,
                'total_columns': 2,
                'total_fk_relationships': 0
            }
        }
        
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            serialize_current_mapping_state=Mock(return_value=new_format_config),
            get_csv_datasets_for_organization=Mock(return_value=[
                {'name': 'test_dataset.csv'}
            ])
        ):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_name': 'New Format Test Mapping'
            }
            
            response = client.post(reverse('metadata:csv_save_mapping'), data)
            
            assert response.status_code == 200
            response_data = json.loads(response.content)
            assert response_data['success'] is True
            
            # Verify the mapping was saved with correct format
            mapping = Mapping.objects.get(name='New Format Test Mapping')
            stored_config = mapping.mapping_config
            
            # Check that column IDs use organization_id format
            column_ids = list(stored_config['workspace_columns'].keys())
            for column_id in column_ids:
                assert column_id.startswith(organization_id), f"Column ID {column_id} should start with {organization_id}"
                assert '::' in column_id, f"Column ID {column_id} should contain ::"
                
                # Parse the ID to verify format
                parts = column_id.split('::')
                assert len(parts) == 3, f"Column ID {column_id} should have 3 parts"
                assert parts[0] == organization_id, f"First part should be organization_id"
                assert parts[1] == 'test_dataset.csv', f"Second part should be dataset name"
    
    def test_backward_compatibility_with_legacy_column_format(self, client, user, organization_id):
        """Test that API can handle legacy column format gracefully"""
        # Create mapping with legacy format
        legacy_format_config = {
            'selected_datasets': ['test_dataset.csv'],
            'workspace_columns': {
                'test_dataset.csv::id': {  # Legacy format without organization prefix
                    'name': 'id', 
                    'dataset': 'test_dataset.csv'
                },
                'csv::test_dataset.csv::name': {  # Old CSV format
                    'name': 'name', 
                    'dataset': 'test_dataset.csv'
                }
            },
            'fk_relationships': {},
            'entity_mappings': {}
        }
        
        mapping = Mapping.objects.create(
            name='Legacy Format Mapping',
            organization_id=organization_id,
            source_datasets=['test_dataset.csv'],
            mapping_config=legacy_format_config,
            created_by=user
        )
        
        with patch.multiple(
            'arkumu.metadata.views.csv_mapping.saved_mappings_api.CSVMappingCoordinatorMixin',
            validate_mapping_compatibility=Mock(return_value={
                'is_valid': True,
                'errors': [],
                'warnings': ['Some column formats have been updated'],
                'missing_datasets': []
            }),
            deserialize_mapping_state=Mock(return_value={'restored': True})
        ):
            client.force_login(user)
            
            data = {
                'organization': organization_id,
                'mapping_id': str(mapping.id)
            }
            
            response = client.post(reverse('metadata:csv_load_mapping'), data)
            
            # Should load successfully with warnings
            assert response.status_code == 200
            response_data = json.loads(response.content)
            assert response_data['success'] is True
            assert 'warnings' in response_data
