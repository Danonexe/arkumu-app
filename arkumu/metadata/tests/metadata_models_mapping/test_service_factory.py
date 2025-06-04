"""
Tests for ServiceFactory

Tests singleton behavior, dependency injection, and service creation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import RequestFactory
from django.contrib.sessions.backends.db import SessionStore

# Import the ServiceFactory and related classes
from arkumu.metadata.services.metadata_models_mapping.service_factory import ServiceFactory, get_services_for_request, get_services_for_api


class TestServiceFactory:
    """Test cases for ServiceFactory class"""
    
    def setup_method(self):
        """Setup before each test - clear instances"""
        ServiceFactory.clear_instances()
    
    def teardown_method(self):
        """Cleanup after each test"""
        ServiceFactory.clear_instances()

    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.TableAnalysisService')
    def test_get_table_analysis_service_singleton(self, mock_table_analysis):
        """Test that TableAnalysisService follows singleton pattern"""
        # Setup mock
        mock_instance = Mock()
        mock_table_analysis.return_value = mock_instance
        
        # Get service twice
        service1 = ServiceFactory.get_table_analysis_service()
        service2 = ServiceFactory.get_table_analysis_service()
        
        # Assert same instance returned
        assert service1 is service2
        assert service1 is mock_instance
        
        # Assert service only created once
        mock_table_analysis.assert_called_once()
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.MappingConfigurationService')
    def test_get_mapping_configuration_service_not_singleton(self, mock_mapping_config):
        """Test that MappingConfigurationService is not singleton"""
        # Setup mocks - return different instances each time
        mock_instance1 = Mock()
        mock_instance2 = Mock()
        mock_mapping_config.side_effect = [mock_instance1, mock_instance2]
        
        # Get service twice
        service1 = ServiceFactory.get_mapping_configuration_service()
        service2 = ServiceFactory.get_mapping_configuration_service()
        
        # Assert different instances returned
        assert service1 is not service2
        assert service1 is mock_instance1
        assert service2 is mock_instance2
        
        # Assert service created twice
        assert mock_mapping_config.call_count == 2
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.MappingConfigurationService')
    def test_get_mapping_configuration_service_with_session_storage(self, mock_mapping_config):
        """Test MappingConfigurationService receives session storage"""
        mock_session = Mock()
        mock_instance = Mock()
        mock_mapping_config.return_value = mock_instance
        
        service = ServiceFactory.get_mapping_configuration_service(session_storage=mock_session)
        
        # Assert service created with session storage
        mock_mapping_config.assert_called_once_with(session_storage=mock_session)
        assert service is mock_instance
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ReferenceResolutionService')
    def test_get_reference_resolution_service_singleton(self, mock_reference_resolution):
        """Test that ReferenceResolutionService follows singleton pattern"""
        mock_instance = Mock()
        mock_reference_resolution.return_value = mock_instance
        
        service1 = ServiceFactory.get_reference_resolution_service()
        service2 = ServiceFactory.get_reference_resolution_service()
        
        assert service1 is service2
        assert service1 is mock_instance
        mock_reference_resolution.assert_called_once()
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ValidationService')
    def test_get_validation_service_singleton(self, mock_validation):
        """Test that ValidationService follows singleton pattern"""
        mock_instance = Mock()
        mock_validation.return_value = mock_instance
        
        service1 = ServiceFactory.get_validation_service()
        service2 = ServiceFactory.get_validation_service()
        
        assert service1 is service2
        assert service1 is mock_instance
        mock_validation.assert_called_once()
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.PreviewService')
    def test_get_preview_service_with_dependencies(self, mock_preview_service):
        """Test that PreviewService is created with proper dependencies"""
        # Setup mocks for dependencies
        with patch.object(ServiceFactory, 'get_table_analysis_service') as mock_table_analysis, \
             patch.object(ServiceFactory, 'get_mapping_configuration_service') as mock_mapping_config, \
             patch.object(ServiceFactory, 'get_reference_resolution_service') as mock_reference_resolution, \
             patch.object(ServiceFactory, 'get_validation_service') as mock_validation:
            
            # Setup return values
            mock_table_instance = Mock()
            mock_mapping_instance = Mock()
            mock_reference_instance = Mock()
            mock_validation_instance = Mock()
            mock_preview_instance = Mock()
            
            mock_table_analysis.return_value = mock_table_instance
            mock_mapping_config.return_value = mock_mapping_instance
            mock_reference_resolution.return_value = mock_reference_instance
            mock_validation.return_value = mock_validation_instance
            mock_preview_service.return_value = mock_preview_instance
            
            mock_session = Mock()
            
            # Call the method
            service = ServiceFactory.get_preview_service(session_storage=mock_session)
            
            # Assert dependencies were fetched
            mock_table_analysis.assert_called_once()
            mock_mapping_config.assert_called_once_with(mock_session)
            mock_reference_resolution.assert_called_once()
            mock_validation.assert_called_once()
            
            # Assert PreviewService was created with dependencies
            mock_preview_service.assert_called_once_with(
                table_analysis_service=mock_table_instance,
                mapping_config_service=mock_mapping_instance,
                reference_resolution_service=mock_reference_instance,
                validation_service=mock_validation_instance
            )
            
            assert service is mock_preview_instance
    
    @patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ProcessingPipelineService')
    def test_get_processing_pipeline_service_with_dependencies(self, mock_pipeline_service):
        """Test that ProcessingPipelineService is created with proper dependencies"""
        # Setup mocks for dependencies
        with patch.object(ServiceFactory, 'get_table_analysis_service') as mock_table_analysis, \
             patch.object(ServiceFactory, 'get_mapping_configuration_service') as mock_mapping_config, \
             patch.object(ServiceFactory, 'get_reference_resolution_service') as mock_reference_resolution, \
             patch.object(ServiceFactory, 'get_validation_service') as mock_validation:
            
            # Setup return values
            mock_table_instance = Mock()
            mock_mapping_instance = Mock()
            mock_reference_instance = Mock()
            mock_validation_instance = Mock()
            mock_pipeline_instance = Mock()
            
            mock_table_analysis.return_value = mock_table_instance
            mock_mapping_config.return_value = mock_mapping_instance
            mock_reference_resolution.return_value = mock_reference_instance
            mock_validation.return_value = mock_validation_instance
            mock_pipeline_service.return_value = mock_pipeline_instance
            
            mock_session = Mock()
            
            # Call the method
            service = ServiceFactory.get_processing_pipeline_service(session_storage=mock_session)
            
            # Assert dependencies were fetched
            mock_table_analysis.assert_called_once()
            mock_mapping_config.assert_called_once_with(mock_session)
            mock_reference_resolution.assert_called_once()
            mock_validation.assert_called_once()
            
            # Assert ProcessingPipelineService was created with dependencies
            mock_pipeline_service.assert_called_once_with(
                table_analysis_service=mock_table_instance,
                mapping_config_service=mock_mapping_instance,
                reference_resolution_service=mock_reference_instance,
                validation_service=mock_validation_instance
            )
            
            assert service is mock_pipeline_instance
    
    def test_create_complete_service_set(self):
        """Test that complete service set contains all expected services"""
        with patch.object(ServiceFactory, 'get_table_analysis_service') as mock_table_analysis, \
             patch.object(ServiceFactory, 'get_mapping_configuration_service') as mock_mapping_config, \
             patch.object(ServiceFactory, 'get_reference_resolution_service') as mock_reference_resolution, \
             patch.object(ServiceFactory, 'get_validation_service') as mock_validation, \
             patch.object(ServiceFactory, 'get_preview_service') as mock_preview, \
             patch.object(ServiceFactory, 'get_processing_pipeline_service') as mock_pipeline:
            
            # Setup return values
            mock_instances = {
                'table_analysis': Mock(),
                'mapping_configuration': Mock(),
                'reference_resolution': Mock(),
                'validation': Mock(),
                'preview': Mock(),
                'processing_pipeline': Mock(),
            }
            
            mock_table_analysis.return_value = mock_instances['table_analysis']
            mock_mapping_config.return_value = mock_instances['mapping_configuration']
            mock_reference_resolution.return_value = mock_instances['reference_resolution']
            mock_validation.return_value = mock_instances['validation']
            mock_preview.return_value = mock_instances['preview']
            mock_pipeline.return_value = mock_instances['processing_pipeline']
            
            mock_session = Mock()
            
            # Call the method
            services = ServiceFactory.create_complete_service_set(session_storage=mock_session)
            
            # Assert all services are present
            expected_keys = {
                'table_analysis', 'mapping_configuration', 'reference_resolution',
                'validation', 'preview', 'processing_pipeline'
            }
            assert set(services.keys()) == expected_keys
            
            # Assert correct instances returned
            for key, mock_instance in mock_instances.items():
                assert services[key] is mock_instance
            
            # Assert session storage passed to appropriate services
            mock_mapping_config.assert_called_once_with(mock_session)
            mock_preview.assert_called_once_with(mock_session)
            mock_pipeline.assert_called_once_with(mock_session)
    
    def test_clear_instances(self):
        """Test that clear_instances removes all cached instances"""
        # Setup some instances
        with patch('arkumu.metadata.services.metadata_models_mapping.service_factory.TableAnalysisService') as mock_service:
            mock_instance = Mock()
            mock_service.return_value = mock_instance
            
            # Create an instance
            service1 = ServiceFactory.get_table_analysis_service()
            assert service1 is mock_instance
            
            # Clear instances
            ServiceFactory.clear_instances()
            
            # Create another instance - should be a new call
            mock_service.reset_mock()
            service2 = ServiceFactory.get_table_analysis_service()
            
            # Assert new instance was created
            mock_service.assert_called_once()


class TestConvenienceFunctions:
    """Test cases for convenience functions"""
    
    def setup_method(self):
        """Setup before each test"""
        ServiceFactory.clear_instances()
    
    def teardown_method(self):
        """Cleanup after each test"""
        ServiceFactory.clear_instances()
    
    def test_get_services_for_request_with_request(self):
        """Test get_services_for_request with Django request"""
        # Create a mock request with session
        request = Mock()
        mock_session = Mock()
        request.session = mock_session
        
        with patch.object(ServiceFactory, 'create_complete_service_set') as mock_create_services:
            mock_services = {'test': 'services'}
            mock_create_services.return_value = mock_services
            
            result = get_services_for_request(request)
            
            # Assert session passed to factory
            mock_create_services.assert_called_once_with(mock_session)
            assert result is mock_services
    
    def test_get_services_for_request_without_request(self):
        """Test get_services_for_request without request"""
        with patch.object(ServiceFactory, 'create_complete_service_set') as mock_create_services:
            mock_services = {'test': 'services'}
            mock_create_services.return_value = mock_services
            
            result = get_services_for_request()
            
            # Assert None passed as session_storage
            mock_create_services.assert_called_once_with(None)
            assert result is mock_services
    
    def test_get_services_for_api(self):
        """Test get_services_for_api"""
        with patch.object(ServiceFactory, 'create_complete_service_set') as mock_create_services:
            mock_services = {'test': 'services'}
            mock_create_services.return_value = mock_services
            
            result = get_services_for_api()
            
            # Assert None passed as session_storage
            mock_create_services.assert_called_once_with(session_storage=None)
            assert result is mock_services


class TestIntegration:
    """Integration tests using Django's test framework"""
    
    def setup_method(self):
        """Setup before each test"""
        ServiceFactory.clear_instances()
        self.factory = RequestFactory()
    
    def teardown_method(self):
        """Cleanup after each test"""
        ServiceFactory.clear_instances()
    
    @pytest.mark.django_db
    def test_get_services_for_request_integration(self):
        """Integration test with real Django request"""
        # Create a real request
        request = self.factory.get('/')
        
        # Add session
        session = SessionStore()
        session.create()
        request.session = session
        
        # This would normally create real service instances
        # For testing, we'll still mock the actual service classes
        with patch('arkumu.metadata.services.metadata_models_mapping.service_factory.TableAnalysisService'), \
             patch('arkumu.metadata.services.metadata_models_mapping.service_factory.MappingConfigurationService'), \
             patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ReferenceResolutionService'), \
             patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ValidationService'), \
             patch('arkumu.metadata.services.metadata_models_mapping.service_factory.PreviewService'), \
             patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ProcessingPipelineService'):
            
            services = get_services_for_request(request)
            
            # Assert all expected services are present
            expected_keys = {
                'table_analysis', 'mapping_configuration', 'reference_resolution',
                'validation', 'preview', 'processing_pipeline'
            }
            assert set(services.keys()) == expected_keys
            
            # Assert services are not None
            for service in services.values():
                assert service is not None


@pytest.fixture
def mock_all_services():
    """Fixture to mock all service classes"""
    with patch('arkumu.metadata.services.metadata_models_mapping.service_factory.TableAnalysisService') as table_analysis, \
         patch('arkumu.metadata.services.metadata_models_mapping.service_factory.MappingConfigurationService') as mapping_config, \
         patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ReferenceResolutionService') as reference_resolution, \
         patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ValidationService') as validation, \
         patch('arkumu.metadata.services.metadata_models_mapping.service_factory.PreviewService') as preview, \
         patch('arkumu.metadata.services.metadata_models_mapping.service_factory.ProcessingPipelineService') as pipeline:
        
        yield {
            'table_analysis': table_analysis,
            'mapping_config': mapping_config,
            'reference_resolution': reference_resolution,
            'validation': validation,
            'preview': preview,
            'pipeline': pipeline,
        }


class TestServiceFactoryWithFixtures:
    """Test cases using fixtures for cleaner setup"""
    
    def setup_method(self):
        """Setup before each test"""
        ServiceFactory.clear_instances()
    
    def teardown_method(self):
        """Cleanup after each test"""
        ServiceFactory.clear_instances()
    
    def test_singleton_behavior_with_fixture(self, mock_all_services):
        """Test singleton behavior using fixture"""
        mock_instance = Mock()
        mock_all_services['table_analysis'].return_value = mock_instance
        
        service1 = ServiceFactory.get_table_analysis_service()
        service2 = ServiceFactory.get_table_analysis_service()
        
        assert service1 is service2
        assert service1 is mock_instance
        mock_all_services['table_analysis'].assert_called_once()
    
    def test_complete_service_creation_with_fixture(self, mock_all_services):
        """Test complete service creation using fixture"""
        # Setup all mocks to return unique instances
        for key, mock_service in mock_all_services.items():
            mock_service.return_value = Mock(name=f"mock_{key}")
        
        services = ServiceFactory.create_complete_service_set()
        
        # Assert all services created
        assert len(services) == 6
        for service in services.values():
            assert service is not None