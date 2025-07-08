"""
Phase 2 Coordinator Refactoring Validation Tests

This test suite validates the actual refactored coordinator architecture
based on the current implementation. It focuses on:

1. Validating actual methods implemented in BaseCoordinatorMixin
2. Testing integration between coordinators
3. Validating backward compatibility
4. Testing error handling and edge cases
5. Performance validation

This test suite is designed to validate the current state of the refactoring
and identify any issues that need to be addressed.
"""

import pytest
import time
from unittest.mock import Mock, patch
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware

from arkumu.common.mixins.base_coordinator import BaseCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.importer.mixins.ingest_coordinator import IngestCoordinatorMixin
from arkumu.users.models import Organization


@pytest.fixture
def request_factory():
    """Create a request factory for testing."""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a mock request with session support."""
    request = request_factory.get('/')
    
    # Add session middleware
    middleware = SessionMiddleware(lambda x: None)
    middleware.process_request(request)
    request.session.save()
    
    # Add CSRF middleware
    csrf_middleware = CsrfViewMiddleware(lambda x: None)
    csrf_middleware.process_request(request)
    
    return request


@pytest.fixture
def test_organization(db):
    """Create a test organization."""
    return Organization.objects.create(
        code='TEST_ORG',
        name='Test Organization'
    )


@pytest.fixture
def test_organization_2(db):
    """Create a second test organization."""
    return Organization.objects.create(
        code='TEST_ORG_2',
        name='Test Organization 2'
    )


@pytest.mark.django_db
class TestBaseCoordinatorMethods:
    """Test the actual methods implemented in BaseCoordinatorMixin."""
    
    def test_base_coordinator_has_core_methods(self):
        """Test that BaseCoordinatorMixin has core methods implemented."""
        base = BaseCoordinatorMixin()
        
        # Core session key methods
        assert hasattr(base, 'get_session_key')
        assert hasattr(base, '_get_shared_session_key')
        assert hasattr(base, 'get_session_key_with_pattern')
        
        # Core organization methods
        assert hasattr(base, 'get_current_organization')
        assert hasattr(base, 'set_current_organization')
        assert hasattr(base, 'clear_current_organization')
        assert hasattr(base, 'get_organization_context')
        assert hasattr(base, 'handle_organization_change')
        assert hasattr(base, 'validate_organization_required')
        
        # Core state management methods
        assert hasattr(base, 'clear_organization_specific_state')
        assert hasattr(base, 'get_coordinator_debug_info')
        assert hasattr(base, 'serialize_coordinator_state')
        assert hasattr(base, 'deserialize_coordinator_state')
        
        # Workspace management methods
        assert hasattr(base, 'get_workspace_items')
        assert hasattr(base, 'update_workspace_items')
        assert hasattr(base, 'clear_workspace_items')
        
        # Dataset selection methods
        assert hasattr(base, 'get_selected_datasets')
        assert hasattr(base, 'set_selected_datasets')
        assert hasattr(base, 'toggle_dataset_selection')
        assert hasattr(base, 'clear_selected_datasets')
        
        # Validation methods
        assert hasattr(base, 'validate_session_key_consistency')
        assert hasattr(base, 'validate_coordinator_consistency')
        assert hasattr(base, 'validate_state_integrity')
    
    def test_session_key_generation(self):
        """Test session key generation with different prefixes."""
        base = BaseCoordinatorMixin()
        csv_coord = CSVMappingCoordinatorMixin()
        ingest_coord = IngestCoordinatorMixin()
        
        # Test prefixes
        assert base.SESSION_PREFIX == 'base'
        assert csv_coord.SESSION_PREFIX == 'csv_mapping'
        assert ingest_coord.SESSION_PREFIX == 'ingest'
        
        # Test key generation
        base_key = base.get_session_key('test_key', 123)
        csv_key = csv_coord.get_session_key('test_key', 123)
        ingest_key = ingest_coord.get_session_key('test_key', 123)
        
        assert base_key == 'base_test_key_123'
        assert csv_key == 'csv_mapping_test_key_123'
        assert ingest_key == 'ingest_test_key_123'
        
        # Test shared keys
        shared_key = base._get_shared_session_key('current_organization')
        assert shared_key == 'current_organization'
    
    def test_organization_management(self, mock_request, test_organization):
        """Test organization management methods."""
        base = BaseCoordinatorMixin()
        
        # Test setting organization
        org_data = base.set_current_organization(mock_request, test_organization.code)
        assert org_data is not None
        assert org_data['code'] == test_organization.code
        assert org_data['id'] == test_organization.id
        
        # Test getting organization
        current_org = base.get_current_organization(mock_request)
        assert current_org == org_data
        
        # Test organization context
        context = base.get_organization_context(mock_request)
        assert context['organization_id'] == test_organization.code
        assert context['has_organization'] is True
        
        # Test validation
        is_valid, error, org = base.validate_organization_required(mock_request)
        assert is_valid is True
        assert error is None
        assert org == org_data
        
        # Test clearing
        base.clear_current_organization(mock_request)
        assert base.get_current_organization(mock_request) is None
    
    def test_workspace_management(self, mock_request, test_organization):
        """Test workspace management methods."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Test getting empty workspace
        workspace = base.get_workspace_items(mock_request, test_organization.id, 'test_workspace')
        assert workspace == []
        
        # Test updating workspace
        test_items = [{'id': 1, 'name': 'item1'}, {'id': 2, 'name': 'item2'}]
        base.update_workspace_items(mock_request, test_organization.id, 'test_workspace', test_items)
        
        # Test getting workspace
        workspace = base.get_workspace_items(mock_request, test_organization.id, 'test_workspace')
        assert workspace == test_items
        
        # Test clearing workspace
        base.clear_workspace_items(mock_request, test_organization.id, 'test_workspace')
        workspace = base.get_workspace_items(mock_request, test_organization.id, 'test_workspace')
        assert workspace == []
    
    def test_dataset_selection_management(self, mock_request, test_organization):
        """Test dataset selection management methods."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Test getting empty selection
        datasets = base.get_selected_datasets(mock_request, test_organization.id, 'test_datasets')
        assert datasets == []
        
        # Test setting datasets
        test_datasets = ['dataset1.csv', 'dataset2.csv']
        base.set_selected_datasets(mock_request, test_organization.id, 'test_datasets', test_datasets)
        
        # Test getting datasets
        datasets = base.get_selected_datasets(mock_request, test_organization.id, 'test_datasets')
        assert datasets == test_datasets
        
        # Test toggling dataset
        updated_datasets, was_added = base.toggle_dataset_selection(
            mock_request, test_organization.id, 'test_datasets', 'dataset3.csv'
        )
        assert was_added is True
        assert 'dataset3.csv' in updated_datasets
        
        # Test toggling again (should remove)
        updated_datasets, was_added = base.toggle_dataset_selection(
            mock_request, test_organization.id, 'test_datasets', 'dataset3.csv'
        )
        assert was_added is False
        assert 'dataset3.csv' not in updated_datasets
        
        # Test clearing datasets
        base.clear_selected_datasets(mock_request, test_organization.id, 'test_datasets')
        datasets = base.get_selected_datasets(mock_request, test_organization.id, 'test_datasets')
        assert datasets == []


@pytest.mark.django_db
class TestCoordinatorIntegration:
    """Test integration between different coordinators."""
    
    def test_csv_coordinator_inheritance(self):
        """Test that CSV coordinator properly inherits from base."""
        csv_coord = CSVMappingCoordinatorMixin()
        
        # Test inheritance
        assert isinstance(csv_coord, BaseCoordinatorMixin)
        assert csv_coord.SESSION_PREFIX == 'csv_mapping'
        
        # Test that all base methods are available
        assert hasattr(csv_coord, 'get_session_key')
        assert hasattr(csv_coord, 'get_current_organization')
        assert hasattr(csv_coord, 'get_workspace_items')
        assert hasattr(csv_coord, 'get_selected_datasets')
    
    def test_ingest_coordinator_inheritance(self):
        """Test that ingest coordinator properly inherits from base."""
        ingest_coord = IngestCoordinatorMixin()
        
        # Test inheritance
        assert isinstance(ingest_coord, BaseCoordinatorMixin)
        assert ingest_coord.SESSION_PREFIX == 'ingest'
        
        # Test that all base methods are available
        assert hasattr(ingest_coord, 'get_session_key')
        assert hasattr(ingest_coord, 'get_current_organization')
        assert hasattr(ingest_coord, 'get_workspace_items')
        assert hasattr(ingest_coord, 'get_selected_datasets')
    
    def test_shared_organization_state(self, mock_request, test_organization):
        """Test that organization state is shared between coordinators."""
        csv_coord = CSVMappingCoordinatorMixin()
        ingest_coord = IngestCoordinatorMixin()
        
        # Set organization in CSV coordinator
        csv_coord.set_current_organization(mock_request, test_organization.code)
        
        # Verify ingest coordinator can see it
        org_from_ingest = ingest_coord.get_current_organization(mock_request)
        assert org_from_ingest is not None
        assert org_from_ingest['code'] == test_organization.code
        
        # Clear from ingest coordinator
        ingest_coord.clear_current_organization(mock_request)
        
        # Verify CSV coordinator sees the change
        org_from_csv = csv_coord.get_current_organization(mock_request)
        assert org_from_csv is None
    
    def test_isolated_session_data(self, mock_request, test_organization):
        """Test that coordinator-specific session data is isolated."""
        csv_coord = CSVMappingCoordinatorMixin()
        ingest_coord = IngestCoordinatorMixin()
        
        # Set organization for both
        csv_coord.set_current_organization(mock_request, test_organization.code)
        ingest_coord.set_current_organization(mock_request, test_organization.code)
        
        # Set different workspace data
        csv_coord.update_workspace_items(mock_request, test_organization.id, 'columns', ['col1', 'col2'])
        ingest_coord.update_workspace_items(mock_request, test_organization.id, 'files', ['file1.csv', 'file2.csv'])
        
        # Verify isolation
        csv_data = csv_coord.get_workspace_items(mock_request, test_organization.id, 'columns')
        ingest_data = ingest_coord.get_workspace_items(mock_request, test_organization.id, 'files')
        
        assert csv_data == ['col1', 'col2']
        assert ingest_data == ['file1.csv', 'file2.csv']
        
        # Verify cross-coordinator isolation
        csv_files = csv_coord.get_workspace_items(mock_request, test_organization.id, 'files')
        ingest_columns = ingest_coord.get_workspace_items(mock_request, test_organization.id, 'columns')
        
        assert csv_files == []  # Empty because it's using different session key
        assert ingest_columns == []  # Empty because it's using different session key
    
    def test_organization_change_coordination(self, mock_request, test_organization, test_organization_2):
        """Test that organization changes are properly coordinated."""
        csv_coord = CSVMappingCoordinatorMixin()
        ingest_coord = IngestCoordinatorMixin()
        
        # Set up initial state
        csv_coord.set_current_organization(mock_request, test_organization.code)
        csv_coord.update_workspace_items(mock_request, test_organization.id, 'columns', ['col1'])
        ingest_coord.update_workspace_items(mock_request, test_organization.id, 'files', ['file1.csv'])
        
        # Change organization
        new_org_data, old_org_data = csv_coord.handle_organization_change(mock_request, test_organization_2.code)
        
        # Verify organization changed for both coordinators
        assert new_org_data['code'] == test_organization_2.code
        assert old_org_data['code'] == test_organization.code
        
        csv_current = csv_coord.get_current_organization(mock_request)
        ingest_current = ingest_coord.get_current_organization(mock_request)
        
        assert csv_current['code'] == test_organization_2.code
        assert ingest_current['code'] == test_organization_2.code
        
        # Verify old organization state was cleared
        old_csv_data = csv_coord.get_workspace_items(mock_request, test_organization.id, 'columns')
        old_ingest_data = ingest_coord.get_workspace_items(mock_request, test_organization.id, 'files')
        
        assert old_csv_data == []
        assert old_ingest_data == []


@pytest.mark.django_db
class TestBackwardCompatibility:
    """Test backward compatibility with existing functionality."""
    
    def test_csv_coordinator_existing_methods(self):
        """Test that CSV coordinator maintains existing methods."""
        csv_coord = CSVMappingCoordinatorMixin()
        
        # Test CSV-specific methods
        assert hasattr(csv_coord, 'generate_column_id')
        assert hasattr(csv_coord, 'parse_column_id')
        
        # Test column ID generation
        col_id = csv_coord.generate_column_id('test.csv', 'column1', 'csv')
        assert col_id == 'csv::test.csv::column1'
        
        # Test column ID parsing
        parsed = csv_coord.parse_column_id('csv::test.csv::column1')
        assert parsed['source'] == 'csv'
        assert parsed['dataset'] == 'test.csv'
        assert parsed['column'] == 'column1'
    
    def test_ingest_coordinator_existing_methods(self):
        """Test that ingest coordinator maintains existing methods."""
        ingest_coord = IngestCoordinatorMixin()
        
        # Test ingest-specific methods
        assert hasattr(ingest_coord, 'get_selected_files')
        assert hasattr(ingest_coord, 'set_selected_files')
        assert hasattr(ingest_coord, 'clear_selected_files')
        assert hasattr(ingest_coord, 'get_current_mapping')
        assert hasattr(ingest_coord, 'set_current_mapping')
        assert hasattr(ingest_coord, 'clear_current_mapping')
    
    def test_session_key_compatibility(self, mock_request, test_organization):
        """Test that session keys maintain expected patterns."""
        csv_coord = CSVMappingCoordinatorMixin()
        ingest_coord = IngestCoordinatorMixin()
        
        # Set organization
        csv_coord.set_current_organization(mock_request, test_organization.code)
        
        # Test that organization is stored in shared key
        shared_key = csv_coord._get_shared_session_key('current_organization')
        assert shared_key == 'current_organization'
        assert shared_key in mock_request.session
        
        # Test that coordinator-specific keys use prefixes
        csv_key = csv_coord.get_session_key('test_data', test_organization.id)
        ingest_key = ingest_coord.get_session_key('test_data', test_organization.id)
        
        assert csv_key == f'csv_mapping_test_data_{test_organization.id}'
        assert ingest_key == f'ingest_test_data_{test_organization.id}'
        assert csv_key != ingest_key
    
    def test_organization_context_structure(self, mock_request, test_organization):
        """Test that organization context maintains expected structure."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        context = base.get_organization_context(mock_request)
        
        # Test expected keys
        expected_keys = [
            'organization_id', 'organization_code', 'organization_name',
            'organization_numeric_id', 'has_organization'
        ]
        
        for key in expected_keys:
            assert key in context
        
        # Test values
        assert context['organization_id'] == test_organization.code
        assert context['organization_code'] == test_organization.code
        assert context['organization_name'] == test_organization.name
        assert context['organization_numeric_id'] == test_organization.id
        assert context['has_organization'] is True


@pytest.mark.django_db
class TestPerformanceAndScaling:
    """Test performance aspects of the refactored architecture."""
    
    def test_session_key_generation_performance(self):
        """Test that session key generation is fast."""
        base = BaseCoordinatorMixin()
        
        start_time = time.time()
        
        # Generate many session keys
        for i in range(1000):
            key = base.get_session_key('test_key', i)
            assert key == f'base_test_key_{i}'
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be very fast
        assert duration < 0.1, f"Session key generation took {duration:.3f}s"
    
    def test_bulk_session_operations(self, mock_request, test_organization):
        """Test performance of bulk session operations."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        start_time = time.time()
        
        # Create many workspace items
        items = []
        for i in range(100):
            items.append({'id': i, 'name': f'item_{i}'})
        
        base.update_workspace_items(mock_request, test_organization.id, 'test_workspace', items)
        
        # Retrieve workspace items
        retrieved_items = base.get_workspace_items(mock_request, test_organization.id, 'test_workspace')
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be reasonably fast
        assert duration < 0.5, f"Bulk operations took {duration:.3f}s"
        assert len(retrieved_items) == 100
        assert retrieved_items == items
    
    def test_organization_change_performance(self, mock_request, test_organization, test_organization_2):
        """Test performance of organization change operations."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Create substantial state
        for i in range(50):
            base.update_workspace_items(mock_request, test_organization.id, f'workspace_{i}', [f'item_{i}'])
            base.set_selected_datasets(mock_request, test_organization.id, f'datasets_{i}', [f'dataset_{i}.csv'])
        
        start_time = time.time()
        
        # Change organization
        new_org_data, old_org_data = base.handle_organization_change(mock_request, test_organization_2.code)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should be reasonably fast
        assert duration < 1.0, f"Organization change took {duration:.3f}s"
        assert new_org_data['code'] == test_organization_2.code
        assert old_org_data['code'] == test_organization.code


@pytest.mark.django_db
class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""
    
    def test_invalid_organization_handling(self, mock_request):
        """Test handling of invalid organization identifiers."""
        base = BaseCoordinatorMixin()
        
        # Test None
        result = base.set_current_organization(mock_request, None)
        assert result is None
        
        # Test empty string
        result = base.set_current_organization(mock_request, '')
        assert result is None
        
        # Test non-existent organization
        result = base.set_current_organization(mock_request, 'NON_EXISTENT')
        assert result is None
    
    def test_operations_without_organization(self, mock_request):
        """Test operations when no organization is set."""
        base = BaseCoordinatorMixin()
        
        # Test validation
        is_valid, error, org = base.validate_organization_required(mock_request)
        assert is_valid is False
        assert error == "No organization selected"
        assert org is None
        
        # Test context
        context = base.get_organization_context(mock_request)
        assert context['has_organization'] is False
        assert context['organization_id'] is None
    
    def test_session_key_edge_cases(self):
        """Test session key generation edge cases."""
        base = BaseCoordinatorMixin()
        
        # Test empty base key
        key = base.get_session_key('', 123)
        assert key == 'base__123'
        
        # Test None organization ID
        key = base.get_session_key('test', None)
        assert key == 'base_test'
        
        # Test zero organization ID
        key = base.get_session_key('test', 0)
        assert key == 'base_test_0'
    
    def test_workspace_operations_edge_cases(self, mock_request, test_organization):
        """Test workspace operations edge cases."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Test getting non-existent workspace
        items = base.get_workspace_items(mock_request, test_organization.id, 'non_existent')
        assert items == []
        
        # Test setting empty workspace
        base.update_workspace_items(mock_request, test_organization.id, 'empty_workspace', [])
        items = base.get_workspace_items(mock_request, test_organization.id, 'empty_workspace')
        assert items == []
        
        # Test setting None workspace
        base.update_workspace_items(mock_request, test_organization.id, 'none_workspace', None)
        items = base.get_workspace_items(mock_request, test_organization.id, 'none_workspace')
        assert items == []  # Should default to empty list
    
    def test_dataset_selection_edge_cases(self, mock_request, test_organization):
        """Test dataset selection edge cases."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Test getting non-existent selection
        datasets = base.get_selected_datasets(mock_request, test_organization.id, 'non_existent')
        assert datasets == []
        
        # Test toggling in empty selection
        updated_datasets, was_added = base.toggle_dataset_selection(
            mock_request, test_organization.id, 'empty_selection', 'dataset1.csv'
        )
        assert was_added is True
        assert updated_datasets == ['dataset1.csv']
        
        # Test toggling same item again
        updated_datasets, was_added = base.toggle_dataset_selection(
            mock_request, test_organization.id, 'empty_selection', 'dataset1.csv'
        )
        assert was_added is False
        assert updated_datasets == []


@pytest.mark.django_db
class TestDebugAndMonitoring:
    """Test debug and monitoring functionality."""
    
    def test_debug_info_generation(self, mock_request, test_organization):
        """Test debug information generation."""
        csv_coord = CSVMappingCoordinatorMixin()
        csv_coord.set_current_organization(mock_request, test_organization.code)
        
        # Create some state
        csv_coord.update_workspace_items(mock_request, test_organization.id, 'columns', ['col1', 'col2'])
        
        debug_info = csv_coord.get_coordinator_debug_info(mock_request)
        
        # Test debug info structure
        assert 'coordinator_type' in debug_info
        assert 'session_prefix' in debug_info
        assert 'current_organization' in debug_info
        assert 'coordinator_sessions' in debug_info
        
        # Test values
        assert debug_info['coordinator_type'] == 'CSVMappingCoordinatorMixin'
        assert debug_info['session_prefix'] == 'csv_mapping'
        assert debug_info['current_organization']['code'] == test_organization.code
    
    def test_state_serialization(self, mock_request, test_organization):
        """Test state serialization functionality."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Create test state
        base.update_workspace_items(mock_request, test_organization.id, 'workspace1', ['item1', 'item2'])
        base.set_selected_datasets(mock_request, test_organization.id, 'datasets1', ['dataset1.csv'])
        
        # Serialize state
        serialized = base.serialize_coordinator_state(mock_request, test_organization.id)
        
        # Test serialized structure
        assert 'coordinator_type' in serialized
        assert 'session_prefix' in serialized
        assert 'organization_id' in serialized
        assert 'timestamp' in serialized
        assert 'session_data' in serialized
        
        # Test values
        assert serialized['coordinator_type'] == 'BaseCoordinatorMixin'
        assert serialized['session_prefix'] == 'base'
        assert serialized['organization_id'] == test_organization.id
    
    def test_session_validation(self, mock_request, test_organization):
        """Test session validation functionality."""
        base = BaseCoordinatorMixin()
        base.set_current_organization(mock_request, test_organization.code)
        
        # Create valid state
        base.update_workspace_items(mock_request, test_organization.id, 'workspace1', ['item1'])
        
        # Validate session
        is_consistent, issues = base.validate_session_key_consistency(mock_request, test_organization.id)
        
        # Should be consistent
        assert isinstance(is_consistent, bool)
        assert isinstance(issues, list)
        
        # Test with coordinator consistency
        consistency_report = base.validate_coordinator_consistency(mock_request, test_organization.id)
        assert 'is_consistent' in consistency_report
        assert 'issues' in consistency_report
        assert 'recommendations' in consistency_report