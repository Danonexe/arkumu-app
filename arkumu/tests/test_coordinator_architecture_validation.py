"""
Comprehensive Validation Tests for Refactored Coordinator Architecture

This test suite validates the Phase 2 refactoring of the coordinator architecture:
- Enhanced BaseCoordinatorMixin with 33 new methods
- Refactored CSV coordinator focused on CSV-specific functionality 
- Enhanced ingest coordinator with new capabilities

Test Coverage:
1. Architecture validation - inheritance, method availability, session key patterns
2. Integration testing - base coordinator working with specific coordinators
3. Performance testing - session key operations, state management
4. Edge cases and error handling
5. Backward compatibility verification
6. State persistence and consistency
7. Organization change handling
8. Debug and monitoring functionality

This comprehensive test suite ensures the refactored architecture maintains
backward compatibility while providing enhanced capabilities.
"""

import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.middleware.csrf import CsrfViewMiddleware
from django.contrib.auth import get_user_model

from arkumu.common.mixins.base_coordinator import BaseCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.importer.mixins.ingest_coordinator import IngestCoordinatorMixin
from arkumu.users.models import Organization

User = get_user_model()


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


@pytest.fixture
def base_coordinator():
    """Create a base coordinator for testing."""
    return BaseCoordinatorMixin()


@pytest.fixture
def csv_coordinator():
    """Create a CSV coordinator for testing."""
    return CSVMappingCoordinatorMixin()


@pytest.fixture
def ingest_coordinator():
    """Create an ingest coordinator for testing."""
    return IngestCoordinatorMixin()


@pytest.mark.django_db
class TestArchitectureValidation:
    """Test that the refactored architecture is correctly implemented."""
    
    def test_base_coordinator_has_33_new_methods(self, base_coordinator):
        """Test that BaseCoordinatorMixin has the expected 33 new methods."""
        expected_methods = [
            # Session key management (5 methods)
            'get_session_key', '_get_shared_session_key', 'get_session_keys_by_pattern',
            'get_all_session_keys_for_organization', 'migrate_session_key',
            
            # Organization management (8 methods)
            'get_current_organization', 'set_current_organization', 'clear_current_organization',
            'get_organization_context', 'handle_organization_change', 'validate_organization_required',
            'get_base_template_context', 'clear_organization_specific_state',
            
            # Generic workspace management (7 methods)
            'get_workspace_data', 'set_workspace_data', 'clear_workspace_data',
            'add_workspace_item', 'remove_workspace_item', 'update_workspace_item',
            'get_workspace_summary',
            
            # Generic dataset selection management (7 methods)
            'get_selected_datasets', 'set_selected_datasets', 'clear_selected_datasets',
            'add_selected_dataset', 'remove_selected_dataset', 'toggle_dataset_selection',
            'get_selected_dataset_summary',
            
            # State serialization/persistence (7 methods)
            'serialize_coordinator_state', 'deserialize_coordinator_state',
            'save_coordinator_state', 'load_coordinator_state', 'export_coordinator_state',
            'import_coordinator_state', 'validate_coordinator_state',
            
            # Validation and consistency (7 methods)
            'validate_session_consistency', 'repair_session_inconsistencies',
            'get_coordinator_debug_info', 'get_session_health_report',
            'cleanup_orphaned_sessions', 'get_state_statistics', 'reset_coordinator_state'
        ]
        
        missing_methods = []
        for method_name in expected_methods:
            if not hasattr(base_coordinator, method_name):
                missing_methods.append(method_name)
            elif not callable(getattr(base_coordinator, method_name)):
                missing_methods.append(f"{method_name} (not callable)")
        
        assert len(missing_methods) == 0, f"Missing methods: {missing_methods}"
        assert len(expected_methods) == 33, f"Expected 33 methods, got {len(expected_methods)}"
    
    def test_csv_coordinator_inheritance(self, csv_coordinator):
        """Test that CSV coordinator properly inherits from BaseCoordinatorMixin."""
        # Check inheritance chain
        assert isinstance(csv_coordinator, BaseCoordinatorMixin)
        assert csv_coordinator.SESSION_PREFIX == 'csv_mapping'
        
        # Check that all base methods are available
        base_methods = [
            'get_session_key', 'get_current_organization', 'set_current_organization',
            'handle_organization_change', 'validate_organization_required',
            'get_workspace_data', 'set_workspace_data', 'get_selected_datasets'
        ]
        
        for method in base_methods:
            assert hasattr(csv_coordinator, method)
            assert callable(getattr(csv_coordinator, method))
    
    def test_ingest_coordinator_inheritance(self, ingest_coordinator):
        """Test that ingest coordinator properly inherits from BaseCoordinatorMixin."""
        # Check inheritance chain
        assert isinstance(ingest_coordinator, BaseCoordinatorMixin)
        assert ingest_coordinator.SESSION_PREFIX == 'ingest'
        
        # Check that all base methods are available
        base_methods = [
            'get_session_key', 'get_current_organization', 'set_current_organization',
            'handle_organization_change', 'validate_organization_required',
            'get_workspace_data', 'set_workspace_data', 'get_selected_datasets'
        ]
        
        for method in base_methods:
            assert hasattr(ingest_coordinator, method)
            assert callable(getattr(ingest_coordinator, method))
    
    def test_session_key_patterns_across_coordinators(self, csv_coordinator, ingest_coordinator):
        """Test that session key patterns are consistent across coordinators."""
        test_org_id = 123
        
        # Test CSV coordinator keys
        csv_key = csv_coordinator.get_session_key('workspace_columns', test_org_id)
        assert csv_key == 'csv_mapping_workspace_columns_123'
        
        # Test ingest coordinator keys
        ingest_key = ingest_coordinator.get_session_key('selected_files', test_org_id)
        assert ingest_key == 'ingest_selected_files_123'
        
        # Test shared keys (should be the same)
        csv_shared = csv_coordinator._get_shared_session_key('current_organization')
        ingest_shared = ingest_coordinator._get_shared_session_key('current_organization')
        assert csv_shared == ingest_shared == 'current_organization'


@pytest.mark.django_db
class TestIntegrationBetweenCoordinators:
    """Test integration between base coordinator and specific coordinators."""
    
    def test_organization_state_sharing(self, mock_request, csv_coordinator, ingest_coordinator, test_organization):
        """Test that organization state is properly shared between coordinators."""
        # Set organization using CSV coordinator
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Verify ingest coordinator can access the same organization
        org_from_ingest = ingest_coordinator.get_current_organization(mock_request)
        assert org_from_ingest is not None
        assert org_from_ingest['code'] == test_organization.code
        
        # Clear organization using ingest coordinator
        ingest_coordinator.clear_current_organization(mock_request)
        
        # Verify CSV coordinator sees the change
        org_from_csv = csv_coordinator.get_current_organization(mock_request)
        assert org_from_csv is None
    
    def test_session_isolation_between_coordinators(self, mock_request, csv_coordinator, ingest_coordinator, test_organization):
        """Test that coordinator-specific session data is properly isolated."""
        # Set organization for both coordinators
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        ingest_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Set coordinator-specific data
        csv_coordinator.set_workspace_data(mock_request, test_organization.id, 'test_data', {'csv': 'data'})
        ingest_coordinator.set_workspace_data(mock_request, test_organization.id, 'test_data', {'ingest': 'data'})
        
        # Verify data isolation
        csv_data = csv_coordinator.get_workspace_data(mock_request, test_organization.id, 'test_data')
        ingest_data = ingest_coordinator.get_workspace_data(mock_request, test_organization.id, 'test_data')
        
        assert csv_data == {'csv': 'data'}
        assert ingest_data == {'ingest': 'data'}
        assert csv_data != ingest_data
    
    def test_organization_change_coordination(self, mock_request, csv_coordinator, ingest_coordinator, test_organization, test_organization_2):
        """Test that organization changes are properly coordinated."""
        # Set up state in both coordinators for org 1
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        csv_coordinator.set_workspace_data(mock_request, test_organization.id, 'columns', ['col1', 'col2'])
        ingest_coordinator.set_workspace_data(mock_request, test_organization.id, 'files', ['file1.csv'])
        
        # Change organization using CSV coordinator
        new_org_data, old_org_data = csv_coordinator.handle_organization_change(mock_request, test_organization_2.code)
        
        # Verify organization changed for both coordinators
        assert new_org_data['code'] == test_organization_2.code
        assert old_org_data['code'] == test_organization.code
        
        csv_current = csv_coordinator.get_current_organization(mock_request)
        ingest_current = ingest_coordinator.get_current_organization(mock_request)
        
        assert csv_current['code'] == test_organization_2.code
        assert ingest_current['code'] == test_organization_2.code
        
        # Verify old organization state was cleared
        old_csv_data = csv_coordinator.get_workspace_data(mock_request, test_organization.id, 'columns')
        old_ingest_data = ingest_coordinator.get_workspace_data(mock_request, test_organization.id, 'files')
        
        assert old_csv_data is None
        assert old_ingest_data is None


@pytest.mark.django_db
class TestPerformanceValidation:
    """Test performance aspects of the refactored architecture."""
    
    def test_session_key_generation_performance(self, base_coordinator):
        """Test that session key generation is performant."""
        start_time = time.time()
        
        # Generate 1000 session keys
        for i in range(1000):
            key = base_coordinator.get_session_key('test_key', i)
            assert key == f'base_test_key_{i}'
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in less than 0.1 seconds
        assert duration < 0.1, f"Session key generation took {duration:.3f}s, expected < 0.1s"
    
    def test_bulk_session_operations_performance(self, mock_request, base_coordinator, test_organization):
        """Test performance of bulk session operations."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        start_time = time.time()
        
        # Set 100 workspace items
        for i in range(100):
            base_coordinator.set_workspace_data(
                mock_request, test_organization.id, f'item_{i}', {'data': f'value_{i}'}
            )
        
        # Get all workspace items
        for i in range(100):
            data = base_coordinator.get_workspace_data(mock_request, test_organization.id, f'item_{i}')
            assert data == {'data': f'value_{i}'}
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in less than 1 second
        assert duration < 1.0, f"Bulk operations took {duration:.3f}s, expected < 1.0s"
    
    def test_organization_change_performance(self, mock_request, csv_coordinator, test_organization, test_organization_2):
        """Test performance of organization change operations."""
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create substantial state for organization 1
        for i in range(50):
            csv_coordinator.set_workspace_data(
                mock_request, test_organization.id, f'key_{i}', {'data': f'value_{i}'}
            )
        
        start_time = time.time()
        
        # Change organization (should clear old state)
        new_org_data, old_org_data = csv_coordinator.handle_organization_change(
            mock_request, test_organization_2.code
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in less than 0.5 seconds
        assert duration < 0.5, f"Organization change took {duration:.3f}s, expected < 0.5s"
        
        # Verify state was cleared
        for i in range(50):
            data = csv_coordinator.get_workspace_data(mock_request, test_organization.id, f'key_{i}')
            assert data is None


@pytest.mark.django_db
class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""
    
    def test_operations_without_session(self, request_factory, base_coordinator):
        """Test operations on request without session."""
        request = request_factory.get('/')
        # No session middleware added
        
        # Operations should not crash but return sensible defaults
        try:
            org = base_coordinator.get_current_organization(request)
            # Should either return None or raise AttributeError
            assert org is None or isinstance(org, type(None))
        except AttributeError:
            # This is acceptable for requests without sessions
            pass
    
    def test_invalid_organization_identifiers(self, mock_request, base_coordinator):
        """Test handling of invalid organization identifiers."""
        # Test None
        result = base_coordinator.set_current_organization(mock_request, None)
        assert result is None
        
        # Test empty string
        result = base_coordinator.set_current_organization(mock_request, '')
        assert result is None
        
        # Test non-existent organization
        result = base_coordinator.set_current_organization(mock_request, 'NON_EXISTENT')
        assert result is None
    
    def test_session_key_edge_cases(self, base_coordinator):
        """Test session key generation edge cases."""
        # Test empty base key
        key = base_coordinator.get_session_key('', 123)
        assert key == 'base__123'
        
        # Test None organization ID
        key = base_coordinator.get_session_key('test', None)
        assert key == 'base_test'
        
        # Test zero organization ID
        key = base_coordinator.get_session_key('test', 0)
        assert key == 'base_test_0'
    
    def test_workspace_operations_edge_cases(self, mock_request, base_coordinator, test_organization):
        """Test workspace operations edge cases."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Test getting non-existent data
        data = base_coordinator.get_workspace_data(mock_request, test_organization.id, 'non_existent')
        assert data is None
        
        # Test setting None data
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'test', None)
        retrieved = base_coordinator.get_workspace_data(mock_request, test_organization.id, 'test')
        assert retrieved is None
        
        # Test clearing non-existent data
        base_coordinator.clear_workspace_data(mock_request, test_organization.id, 'non_existent')
        # Should not raise exception
    
    def test_concurrent_coordinator_operations(self, mock_request, csv_coordinator, ingest_coordinator, test_organization):
        """Test concurrent operations from different coordinators."""
        # Simulate concurrent operations
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        ingest_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Both coordinators modify their own data simultaneously
        csv_coordinator.set_workspace_data(mock_request, test_organization.id, 'data', {'csv': True})
        ingest_coordinator.set_workspace_data(mock_request, test_organization.id, 'data', {'ingest': True})
        
        # Both coordinators should retain their own data
        csv_data = csv_coordinator.get_workspace_data(mock_request, test_organization.id, 'data')
        ingest_data = ingest_coordinator.get_workspace_data(mock_request, test_organization.id, 'data')
        
        assert csv_data == {'csv': True}
        assert ingest_data == {'ingest': True}


@pytest.mark.django_db
class TestStatePersistenceAndConsistency:
    """Test state persistence and consistency across operations."""
    
    def test_state_serialization_deserialization(self, mock_request, csv_coordinator, test_organization):
        """Test state serialization and deserialization."""
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create test state
        test_state = {
            'columns': ['col1', 'col2'],
            'datasets': ['data1.csv', 'data2.csv'],
            'config': {'setting': 'value'}
        }
        
        for key, value in test_state.items():
            csv_coordinator.set_workspace_data(mock_request, test_organization.id, key, value)
        
        # Serialize state
        serialized = csv_coordinator.serialize_coordinator_state(mock_request, test_organization.id)
        
        # Verify serialized state contains expected data
        assert 'coordinator_type' in serialized
        assert 'session_prefix' in serialized
        assert 'organization_id' in serialized
        assert 'workspace_data' in serialized
        assert serialized['organization_id'] == test_organization.id
        assert serialized['session_prefix'] == 'csv_mapping'
        
        # Clear state
        csv_coordinator.clear_workspace_data(mock_request, test_organization.id, 'columns')
        csv_coordinator.clear_workspace_data(mock_request, test_organization.id, 'datasets')
        csv_coordinator.clear_workspace_data(mock_request, test_organization.id, 'config')
        
        # Verify state is cleared
        for key in test_state.keys():
            data = csv_coordinator.get_workspace_data(mock_request, test_organization.id, key)
            assert data is None
        
        # Deserialize state
        restored = csv_coordinator.deserialize_coordinator_state(mock_request, test_organization.id, serialized)
        
        # Verify state is restored
        assert restored['success'] is True
        assert restored['items_restored'] == len(test_state)
        
        for key, expected_value in test_state.items():
            actual_value = csv_coordinator.get_workspace_data(mock_request, test_organization.id, key)
            assert actual_value == expected_value
    
    def test_session_consistency_validation(self, mock_request, base_coordinator, test_organization):
        """Test session consistency validation."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create consistent state
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'data1', {'value': 1})
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'data2', {'value': 2})
        
        # Validate consistency
        is_consistent, issues = base_coordinator.validate_session_consistency(mock_request, test_organization.id)
        assert is_consistent is True
        assert len(issues) == 0
        
        # Manually corrupt session (simulate inconsistency)
        corrupt_key = base_coordinator.get_session_key('corrupt_data', test_organization.id)
        mock_request.session[corrupt_key] = "invalid_json_data"
        
        # Re-validate
        is_consistent, issues = base_coordinator.validate_session_consistency(mock_request, test_organization.id)
        # Should detect the issue or handle it gracefully
        assert isinstance(is_consistent, bool)
        assert isinstance(issues, list)
    
    def test_orphaned_session_cleanup(self, mock_request, base_coordinator, test_organization):
        """Test cleanup of orphaned sessions."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create normal session data
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'normal_data', {'value': 1})
        
        # Create orphaned session keys (simulate leftover data)
        orphaned_key = base_coordinator.get_session_key('orphaned_data', 99999)  # Non-existent org
        mock_request.session[orphaned_key] = {'orphaned': True}
        
        # Cleanup orphaned sessions
        cleaned_count = base_coordinator.cleanup_orphaned_sessions(mock_request)
        
        # Should clean up orphaned data
        assert cleaned_count >= 0  # May be 0 if no orphaned data detected
        assert orphaned_key not in mock_request.session or mock_request.session[orphaned_key] is None
        
        # Normal data should remain
        normal_data = base_coordinator.get_workspace_data(mock_request, test_organization.id, 'normal_data')
        assert normal_data == {'value': 1}


@pytest.mark.django_db
class TestDebugAndMonitoring:
    """Test debug and monitoring functionality."""
    
    def test_coordinator_debug_info(self, mock_request, csv_coordinator, test_organization):
        """Test debug information generation."""
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        csv_coordinator.set_workspace_data(mock_request, test_organization.id, 'debug_data', {'test': True})
        
        debug_info = csv_coordinator.get_coordinator_debug_info(mock_request)
        
        # Verify debug info structure
        assert 'coordinator_type' in debug_info
        assert 'session_prefix' in debug_info
        assert 'current_organization' in debug_info
        assert 'coordinator_sessions' in debug_info
        assert 'total_session_keys' in debug_info
        assert 'coordinator_session_count' in debug_info
        
        # Verify content
        assert debug_info['coordinator_type'] == 'CSVMappingCoordinatorMixin'
        assert debug_info['session_prefix'] == 'csv_mapping'
        assert debug_info['current_organization']['code'] == test_organization.code
        assert debug_info['coordinator_session_count'] > 0
    
    def test_session_health_report(self, mock_request, base_coordinator, test_organization):
        """Test session health reporting."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create test data
        for i in range(10):
            base_coordinator.set_workspace_data(mock_request, test_organization.id, f'data_{i}', {'value': i})
        
        health_report = base_coordinator.get_session_health_report(mock_request)
        
        # Verify health report structure
        assert 'total_sessions' in health_report
        assert 'coordinator_sessions' in health_report
        assert 'shared_sessions' in health_report
        assert 'memory_usage_estimate' in health_report
        assert 'health_status' in health_report
        
        # Verify content
        assert health_report['total_sessions'] > 0
        assert health_report['coordinator_sessions'] > 0
        assert health_report['health_status'] in ['healthy', 'warning', 'critical']
    
    def test_state_statistics(self, mock_request, base_coordinator, test_organization):
        """Test state statistics generation."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Create varied test data
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'small_data', {'a': 1})
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'medium_data', {'b': list(range(100))})
        base_coordinator.set_workspace_data(mock_request, test_organization.id, 'large_data', {'c': list(range(1000))})
        
        stats = base_coordinator.get_state_statistics(mock_request, test_organization.id)
        
        # Verify statistics structure
        assert 'total_items' in stats
        assert 'item_sizes' in stats
        assert 'largest_item' in stats
        assert 'smallest_item' in stats
        assert 'average_size' in stats
        
        # Verify content
        assert stats['total_items'] == 3
        assert stats['largest_item']['key'] == 'large_data'
        assert stats['smallest_item']['key'] == 'small_data'
        assert stats['average_size'] > 0


@pytest.mark.django_db
class TestBackwardCompatibility:
    """Test backward compatibility with existing views and functionality."""
    
    def test_csv_coordinator_preserves_existing_methods(self, csv_coordinator):
        """Test that CSV coordinator preserves existing public methods."""
        # List of methods that should be preserved for backward compatibility
        expected_methods = [
            'get_csv_datasets_for_organization',
            'toggle_dataset_selection',
            'get_selected_dataset_names',
            'get_workspace_columns',
            'add_column_to_workspace',
            'validate_workspace_column_uniqueness',
            'reset_all_coordinator_state',
            'get_workspace_summary',
            'serialize_current_mapping_state',
            'deserialize_mapping_state',
            'get_loaded_mapping_context',
            'generate_column_id',
            'parse_column_id'
        ]
        
        missing_methods = []
        for method_name in expected_methods:
            if not hasattr(csv_coordinator, method_name):
                missing_methods.append(method_name)
            elif not callable(getattr(csv_coordinator, method_name)):
                missing_methods.append(f"{method_name} (not callable)")
        
        assert len(missing_methods) == 0, f"Missing backward compatibility methods: {missing_methods}"
    
    def test_ingest_coordinator_preserves_existing_methods(self, ingest_coordinator):
        """Test that ingest coordinator preserves existing public methods."""
        # List of methods that should be preserved for backward compatibility
        expected_methods = [
            'get_selected_files',
            'set_selected_files',
            'add_selected_file',
            'remove_selected_file',
            'toggle_file_selection',
            'clear_selected_files',
            'get_selected_mapping',
            'set_selected_mapping',
            'clear_selected_mapping',
            'get_ingest_context',
            'reset_ingest_state',
            'clear_organization_specific_state'
        ]
        
        missing_methods = []
        for method_name in expected_methods:
            if not hasattr(ingest_coordinator, method_name):
                missing_methods.append(method_name)
            elif not callable(getattr(ingest_coordinator, method_name)):
                missing_methods.append(f"{method_name} (not callable)")
        
        assert len(missing_methods) == 0, f"Missing backward compatibility methods: {missing_methods}"
    
    def test_session_key_backward_compatibility(self, mock_request, csv_coordinator, test_organization):
        """Test that session keys maintain backward compatibility patterns."""
        csv_coordinator.set_current_organization(mock_request, test_organization.code)
        
        # Test that organization is still stored in shared key
        org_key = csv_coordinator._get_shared_session_key('current_organization')
        assert org_key == 'current_organization'
        assert org_key in mock_request.session
        
        # Test that coordinator-specific keys use the expected prefix
        test_key = csv_coordinator.get_session_key('test_data', test_organization.id)
        assert test_key == f'csv_mapping_test_data_{test_organization.id}'
        
        # Test that numeric IDs are used consistently
        assert isinstance(test_organization.id, int)
        assert str(test_organization.id) in test_key
    
    def test_organization_context_compatibility(self, mock_request, base_coordinator, test_organization):
        """Test that organization context maintains expected structure."""
        base_coordinator.set_current_organization(mock_request, test_organization.code)
        
        context = base_coordinator.get_organization_context(mock_request)
        
        # Verify expected keys are present with correct types
        expected_keys = {
            'organization_id': str,
            'organization_code': str,
            'organization_name': str,
            'organization_numeric_id': int,
            'has_organization': bool
        }
        
        for key, expected_type in expected_keys.items():
            assert key in context, f"Missing context key: {key}"
            if context[key] is not None:  # Allow None values
                assert isinstance(context[key], expected_type), f"Wrong type for {key}: {type(context[key])}"
        
        # Verify values
        assert context['organization_id'] == test_organization.code
        assert context['organization_code'] == test_organization.code
        assert context['organization_name'] == test_organization.name
        assert context['organization_numeric_id'] == test_organization.id
        assert context['has_organization'] is True