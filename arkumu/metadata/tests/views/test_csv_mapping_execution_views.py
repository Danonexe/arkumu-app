"""
Tests for CSV Mapping Execution Views

Tests the simplified SmartBulkUpdaterPolars integration in execution_views.py
Using pytest syntax
"""

import json
import pytest
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.template.response import TemplateResponse

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.views.execution_views import (
    ExecuteGUIMappingView,
    GetMappingExecutionStatusView,
    ValidateMappingExecutionView
)
from arkumu.importer.services.importer.smart_bulk_updater_polars import BulkUpdateStats

User = get_user_model()


@pytest.fixture
def user():
    """Create test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )


@pytest.fixture
def request_factory():
    """Create Django request factory."""
    return RequestFactory()


@pytest.fixture
def mapping_config():
    """Sample mapping configuration."""
    return {
        'selected_datasets': ['test_dataset.csv'],
        'workspace_columns': {
            'column1': {'name': 'title', 'arkumu_type': 'title'},
            'column2': {'name': 'description', 'arkumu_type': 'description'}
        },
        'metadata': {
            'name': 'Test Mapping',
            'description': 'Test mapping description'
        }
    }


@pytest.fixture
def test_mapping(user, mapping_config):
    """Create test mapping."""
    return Mapping.objects.create(
        name='Test Mapping',
        organization_id='test_org',
        mapping_config=mapping_config,
        source_datasets=mapping_config.get('selected_datasets', []),
        created_by=user
    )


@pytest.fixture
def mock_bulk_stats():
    """Create mock BulkUpdateStats."""
    stats = BulkUpdateStats()
    stats.rows_processed = 100
    stats.resources_created = 200
    stats.triples_created = 300
    stats.total_values_created = 400
    stats.resources_updated = 10
    stats.resources_skipped = 5
    stats.errors = 0  # errors is an int, not a list
    stats.cells_processed = 200
    return stats


@pytest.mark.django_db
class TestExecuteGUIMappingView:
    """Test ExecuteGUIMappingView - the main execution endpoint."""
    
    def test_post_missing_parameters(self, request_factory):
        """Test POST request without required parameters."""
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Either mapping_id or dataset_name is required' in data['error']
    
    def test_post_mapping_not_found(self, request_factory):
        """Test POST request with non-existent mapping ID."""
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': '12345678-1234-1234-1234-123456789abc'})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 404
        data = json.loads(response.content)
        assert 'error' in data
        assert 'not found' in data['error']
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.SmartBulkUpdaterPolars')
    def test_post_successful_execution_with_mapping_id(self, mock_updater_class, mock_analyzer_class, 
                                                       request_factory, test_mapping, mock_bulk_stats):
        """Test successful execution with mapping ID."""
        # Mock the analyzer
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = ['test_dataset.csv']
        mock_analyzer.stream_process_s3_source_with_smart_updater.return_value = mock_bulk_stats
        
        # Mock the updater
        mock_updater_class.return_value = Mock()
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {
            'mapping_id': str(test_mapping.id),
            'strategy': 'SKIP_EXISTING'
        })
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        # Check response structure
        assert data['status'] == 'success'
        assert 'execution_name' in data
        assert 'execution_summary' in data
        assert data['engine_used'] == 'SmartBulkUpdaterPolars'
        
        # Check execution results
        summary = data['execution_summary']
        assert summary['total_rows_processed'] == 100
        assert summary['total_resources_created'] == 200
        assert summary['total_triples_created'] == 300
        assert summary['engine_used'] == 'SmartBulkUpdaterPolars'
        assert summary['processing_method'] == 'direct_polars'
        
        # Verify SmartBulkUpdaterPolars was initialized correctly
        mock_updater_class.assert_called_once()
        call_args = mock_updater_class.call_args[1]
        assert call_args['institution'] == 'test_org'
        assert call_args['base_uri'] == 'http://arkumu.org/data'
        assert call_args['link_row_cells'] is True
        assert call_args['link_topology'] == 'first_column'
        assert call_args['multi_value_threshold'] == 0.2
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.SmartBulkUpdaterPolars')
    def test_post_htmx_request_success(self, mock_updater_class, mock_analyzer_class, 
                                       request_factory, test_mapping, mock_bulk_stats):
        """Test HTMX request returns HTML template response."""
        # Setup mocks
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = ['test_dataset.csv']
        mock_analyzer.stream_process_s3_source_with_smart_updater.return_value = mock_bulk_stats
        mock_updater_class.return_value = Mock()
        
        # Create HTMX request
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': str(test_mapping.id)})
        request.META['HTTP_HX_REQUEST'] = 'true'
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        # Should return HTML template response
        assert response.status_code == 200
        assert 'text/html' in response.get('Content-Type', '')
        # Check that it contains expected execution results content
        content = response.content.decode('utf-8')
        assert 'Transformation Complete' in content or 'Service-Powered' in content
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    def test_post_dataset_not_found_in_s3(self, mock_analyzer_class, request_factory, test_mapping):
        """Test execution when dataset is not found in S3."""
        # Mock analyzer that doesn't find the dataset
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = ['other_dataset.csv']
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': str(test_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert 'No data was successfully processed' in data['error']
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.SmartBulkUpdaterPolars')
    def test_post_with_dataset_name(self, mock_updater_class, mock_analyzer_class, 
                                    request_factory, mock_bulk_stats):
        """Test execution using dataset_name instead of mapping_id."""
        # Setup mocks
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = ['session_dataset.csv']
        mock_analyzer.stream_process_s3_source_with_smart_updater.return_value = mock_bulk_stats
        mock_updater_class.return_value = Mock()
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'dataset_name': 'session_dataset'})
        
        # Mock session state serialization
        session_config = {
            'selected_datasets': ['session_dataset.csv'],
            'workspace_columns': {
                'col1': {'name': 'name', 'arkumu_type': 'name'}
            }
        }
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'), \
             patch.object(view, 'serialize_current_mapping_state', return_value=session_config):
            response = view.post(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'success'
        assert 'Current Session' in data['execution_name']
    
    def test_post_exception_handling(self, request_factory, test_mapping):
        """Test that exceptions are properly handled and returned."""
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': str(test_mapping.id)})
        
        # Force an exception by mocking get_organization_id_from_request to raise
        with patch.object(view, 'get_organization_id_from_request', side_effect=Exception('Test error')):
            response = view.post(request)
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Test error' in data['error']


@pytest.mark.django_db
class TestGetMappingExecutionStatusView:
    """Test GetMappingExecutionStatusView - execution preview endpoint."""
    
    @pytest.fixture
    def status_mapping(self, user):
        """Create mapping for status tests."""
        config = {
            'selected_datasets': ['test1.csv', 'test2.csv'],
            'workspace_columns': {
                'col1': {'name': 'title', 'arkumu_type': 'title'},
                'col2': {'name': 'desc', 'arkumu_type': 'description'},
                'col3': {'name': 'author', 'arkumu_type': 'creator'}
            }
        }
        return Mapping.objects.create(
            name='Status Test Mapping',
            organization_id='test_org',
            mapping_config=config,
            source_datasets=config.get('selected_datasets', []),
            created_by=user
        )
    
    def test_get_missing_parameters(self, request_factory):
        """Test GET request without required parameters."""
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/')
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.get(request)
        
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Either mapping_id or dataset_name is required' in data['error']
    
    def test_get_mapping_not_found(self, request_factory):
        """Test GET request with non-existent mapping ID."""
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/', {'mapping_id': '12345678-1234-1234-1234-123456789abc'})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.get(request)
        
        assert response.status_code == 404
        data = json.loads(response.content)
        assert 'error' in data
        assert 'not found' in data['error']
    
    def test_get_successful_status_with_mapping_id(self, request_factory, status_mapping):
        """Test successful status check with mapping ID."""
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/', {'mapping_id': str(status_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.get(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        # Check response structure
        assert data['status'] == 'analysis_complete'
        assert 'Status Test Mapping' in data['analysis_name']
        assert data['ready_to_execute'] is True  # Has datasets and columns
        assert data['datasets'] == ['test1.csv', 'test2.csv']
        assert data['total_columns'] == 3
        assert data['engine'] == 'SmartBulkUpdaterPolars'
        assert data['mapping_id'] == str(status_mapping.id)
    
    def test_get_not_ready_to_execute(self, request_factory, user):
        """Test status check for mapping that's not ready to execute."""
        # Create mapping with no datasets
        incomplete_config = {
            'selected_datasets': [],  # No datasets
            'workspace_columns': {
                'col1': {'name': 'title', 'arkumu_type': 'title'}
            }
        }
        incomplete_mapping = Mapping.objects.create(
            name='Incomplete Mapping',
            organization_id='test_org',
            mapping_config=incomplete_config,
            source_datasets=incomplete_config.get('selected_datasets', []),
            created_by=user
        )
        
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/', {'mapping_id': str(incomplete_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.get(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        assert data['ready_to_execute'] is False  # No datasets
        assert data['datasets'] == []
        assert data['total_columns'] == 1
    
    def test_get_with_dataset_name(self, request_factory):
        """Test status check using dataset_name instead of mapping_id."""
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/', {'dataset_name': 'session_dataset'})
        
        session_config = {
            'selected_datasets': ['session_dataset.csv'],
            'workspace_columns': {
                'col1': {'name': 'name', 'arkumu_type': 'name'},
                'col2': {'name': 'value', 'arkumu_type': 'value'}
            }
        }
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'), \
             patch.object(view, 'serialize_current_mapping_state', return_value=session_config):
            response = view.get(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        assert 'Current Session' in data['analysis_name']
        assert data['ready_to_execute'] is True
        assert data['datasets'] == ['session_dataset.csv']
        assert data['total_columns'] == 2
    
    def test_get_exception_handling(self, request_factory, status_mapping):
        """Test that exceptions are properly handled."""
        view = GetMappingExecutionStatusView()
        request = request_factory.get('/status/', {'mapping_id': str(status_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', side_effect=Exception('Test error')):
            response = view.get(request)
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Test error' in data['error']


@pytest.mark.django_db
class TestValidateMappingExecutionView:
    """Test ValidateMappingExecutionView - validation endpoint."""
    
    @pytest.fixture
    def valid_mapping(self, user):
        """Create valid mapping for validation tests."""
        config = {
            'selected_datasets': ['valid_dataset.csv'],
            'workspace_columns': {
                'col1': {'name': 'title', 'arkumu_type': 'title'}
            }
        }
        return Mapping.objects.create(
            name='Valid Mapping',
            organization_id='test_org',
            mapping_config=config,
            source_datasets=config.get('selected_datasets', []),
            created_by=user
        )
    
    @pytest.fixture
    def invalid_mapping(self, user):
        """Create invalid mapping for validation tests."""
        config = {
            'selected_datasets': [],  # No datasets
            'workspace_columns': {}   # No columns
        }
        return Mapping.objects.create(
            name='Invalid Mapping',
            organization_id='test_org',
            mapping_config=config,
            source_datasets=config.get('selected_datasets', []),
            created_by=user
        )
    
    def test_post_missing_mapping_id(self, request_factory):
        """Test POST request without mapping_id."""
        view = ValidateMappingExecutionView()
        request = request_factory.post('/validate/', {})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'mapping_id is required' in data['error']
    
    def test_post_mapping_not_found(self, request_factory):
        """Test POST request with non-existent mapping ID."""
        view = ValidateMappingExecutionView()
        request = request_factory.post('/validate/', {'mapping_id': '12345678-1234-1234-1234-123456789abc'})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 404
        data = json.loads(response.content)
        assert 'error' in data
        assert 'not found' in data['error']
    
    def test_post_valid_mapping(self, request_factory, valid_mapping):
        """Test validation of a valid mapping."""
        view = ValidateMappingExecutionView()
        request = request_factory.post('/validate/', {'mapping_id': str(valid_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        # Check validation results
        assert 'Valid Mapping' in data['validation_target']
        assert data['is_valid'] is True
        assert data['is_executable'] is True
        assert data['errors'] == []
        assert data['warnings'] == []
        assert data['mapping_id'] == str(valid_mapping.id)
    
    def test_post_invalid_mapping(self, request_factory, invalid_mapping):
        """Test validation of an invalid mapping."""
        view = ValidateMappingExecutionView()
        request = request_factory.post('/validate/', {'mapping_id': str(invalid_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        
        # Check validation results
        assert 'Invalid Mapping' in data['validation_target']
        assert data['is_valid'] is False
        assert data['is_executable'] is False
        assert 'No datasets selected' in data['errors']
        assert 'No columns configured' in data['errors']
        assert data['mapping_id'] == str(invalid_mapping.id)
    
    def test_post_exception_handling(self, request_factory, valid_mapping):
        """Test that exceptions are properly handled."""
        view = ValidateMappingExecutionView()
        request = request_factory.post('/validate/', {'mapping_id': str(valid_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', side_effect=Exception('Test error')):
            response = view.post(request)
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Test error' in data['error']


@pytest.mark.django_db
class TestSmartBulkUpdaterIntegration:
    """Test the integration with SmartBulkUpdaterPolars."""
    
    @pytest.fixture
    def integration_mapping(self, user):
        """Create mapping for integration tests."""
        config = {
            'selected_datasets': ['integration_test.csv'],
            'workspace_columns': {
                'title': {'name': 'title', 'arkumu_type': 'title'},
                'description': {'name': 'description', 'arkumu_type': 'description'},
                'creator': {'name': 'creator', 'arkumu_type': 'creator'}
            }
        }
        return Mapping.objects.create(
            name='Integration Test Mapping',
            organization_id='test_org',
            mapping_config=config,
            source_datasets=config.get('selected_datasets', []),
            created_by=user
        )
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.SmartBulkUpdaterPolars')
    @pytest.mark.parametrize("strategy,expected", [
        ('SKIP_EXISTING', 'should_work'),
        ('UPDATE_EXISTING', 'should_work'),
        ('REPLACE_EXISTING', 'should_work'),
        ('INVALID_STRATEGY', 'should_default')
    ])
    def test_smart_bulk_updater_initialization(self, mock_updater_class, mock_analyzer_class, 
                                               request_factory, integration_mapping, mock_bulk_stats,
                                               strategy, expected):
        """Test that SmartBulkUpdaterPolars is initialized with correct parameters."""
        # Setup mocks
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = ['integration_test.csv']
        mock_analyzer.stream_process_s3_source_with_smart_updater.return_value = mock_bulk_stats
        mock_updater_class.return_value = Mock()
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {
            'mapping_id': str(integration_mapping.id),
            'strategy': strategy
        })
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 200
        
        # Verify SmartBulkUpdaterPolars was called with correct params
        mock_updater_class.assert_called()
        call_kwargs = mock_updater_class.call_args[1]
        
        # Check all initialization parameters
        assert call_kwargs['institution'] == 'test_org'
        assert call_kwargs['base_uri'] == 'http://arkumu.org/data'
        assert call_kwargs['link_row_cells'] is True
        assert call_kwargs['link_topology'] == 'first_column'
        assert call_kwargs['multi_value_threshold'] == 0.2
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.SmartBulkUpdaterPolars')
    def test_multiple_datasets_processing(self, mock_updater_class, mock_analyzer_class, 
                                          request_factory, user):
        """Test processing multiple datasets and stat aggregation."""
        # Setup mapping with multiple datasets
        multi_dataset_config = {
            'selected_datasets': ['dataset1.csv', 'dataset2.csv', 'dataset3.csv'],
            'workspace_columns': {
                'col1': {'name': 'title', 'arkumu_type': 'title'}
            }
        }
        
        multi_mapping = Mapping.objects.create(
            name='Multi Dataset Mapping',
            organization_id='test_org',
            mapping_config=multi_dataset_config,
            source_datasets=multi_dataset_config.get('selected_datasets', []),
            created_by=user
        )
        
        # Mock analyzer
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.return_value = [Mock(name='test_source')]
        mock_analyzer.get_dataset_names_from_s3_source.return_value = [
            'dataset1.csv', 'dataset2.csv', 'dataset3.csv'
        ]
        
        # Mock different stats for each dataset
        stats_list = []
        for i in range(3):
            stats = BulkUpdateStats()
            stats.rows_processed = 50 + i * 10  # 50, 60, 70
            stats.resources_created = 100 + i * 20  # 100, 120, 140
            stats.triples_created = 150 + i * 30  # 150, 180, 210
            stats.total_values_created = 200 + i * 40  # 200, 240, 280
            stats.resources_updated = i * 5  # 0, 5, 10
            stats.resources_skipped = i * 2  # 0, 2, 4
            stats.errors = 1 if i == 1 else 0  # Only second dataset has error
            stats.cells_processed = 100 + i * 20  # 100, 120, 140
            stats_list.append(stats)
        
        mock_analyzer.stream_process_s3_source_with_smart_updater.side_effect = stats_list
        mock_updater_class.return_value = Mock()
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': str(multi_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 200
        data = json.loads(response.content)
        summary = data['execution_summary']
        
        # Check aggregated stats
        assert summary['total_rows_processed'] == 180  # 50 + 60 + 70
        assert summary['total_resources_created'] == 360  # 100 + 120 + 140
        assert summary['total_triples_created'] == 540  # 150 + 180 + 210
        assert summary['total_values_created'] == 720  # 200 + 240 + 280
        assert summary['resources_updated'] == 15  # 0 + 5 + 10
        assert summary['resources_skipped'] == 6  # 0 + 2 + 4
        assert summary['cells_processed'] == 360  # 100 + 120 + 140
        assert summary['datasets_processed'] == 3
        
        # Check errors were aggregated
        assert len(summary['errors']) == 1
        assert '1 error(s) occurred' in summary['errors'][0]
        
        # Verify analyzer was called for each dataset
        assert mock_analyzer.stream_process_s3_source_with_smart_updater.call_count == 3
    
    @patch('arkumu.metadata.views.csv_mapping.views.execution_views.S3DirectDataAnalyzer')
    def test_s3_source_discovery_failure(self, mock_analyzer_class, request_factory, integration_mapping):
        """Test handling when S3 source discovery fails."""
        # Mock analyzer that fails to discover sources
        mock_analyzer = Mock()
        mock_analyzer_class.return_value = mock_analyzer
        mock_analyzer.discover_s3_data_sources.side_effect = Exception('S3 connection failed')
        
        view = ExecuteGUIMappingView()
        request = request_factory.post('/execute/', {'mapping_id': str(integration_mapping.id)})
        
        with patch.object(view, 'get_organization_id_from_request', return_value='test_org'):
            response = view.post(request)
        
        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert 'No data was successfully processed' in data['error'] 