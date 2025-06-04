"""
Service Factory

Factory for creating and managing service instances with proper dependency injection.
Provides easy initialization for both Django views and REST API endpoints.
"""

from typing import Optional
from django.conf import settings
import logging

from .table_analysis import TableAnalysisService
from .mapping_configuration import MappingConfigurationService
from .processing_pipeline import ProcessingPipelineService
from .reference_resolution import ReferenceResolutionService
from .validation import ValidationService
from .preview import PreviewService

logger = logging.getLogger(__name__)


class ServiceFactory:
    """Factory for creating and managing semantic transformation services"""
    
    _instances = {}
    
    @classmethod
    def get_table_analysis_service(cls) -> TableAnalysisService:
        """Get TableAnalysisService instance (singleton)"""
        if 'table_analysis' not in cls._instances:
            cls._instances['table_analysis'] = TableAnalysisService()
        return cls._instances['table_analysis']
    
    @classmethod
    def get_mapping_configuration_service(cls, session_storage=None) -> MappingConfigurationService:
        """Get MappingConfigurationService instance"""
        # Don't use singleton for this service as it needs session storage
        return MappingConfigurationService(session_storage=session_storage)
    
    @classmethod
    def get_reference_resolution_service(cls) -> ReferenceResolutionService:
        """Get ReferenceResolutionService instance (singleton)"""
        if 'reference_resolution' not in cls._instances:
            cls._instances['reference_resolution'] = ReferenceResolutionService()
        return cls._instances['reference_resolution']
    
    @classmethod
    def get_validation_service(cls) -> ValidationService:
        """Get ValidationService instance (singleton)"""
        if 'validation' not in cls._instances:
            cls._instances['validation'] = ValidationService()
        return cls._instances['validation']
    
    @classmethod
    def get_preview_service(cls, session_storage=None) -> PreviewService:
        """Get PreviewService instance with dependencies"""
        # Always create new instance as it depends on other services
        table_analysis = cls.get_table_analysis_service()
        mapping_config = cls.get_mapping_configuration_service(session_storage)
        reference_resolution = cls.get_reference_resolution_service()
        validation = cls.get_validation_service()
        
        return PreviewService(
            table_analysis_service=table_analysis,
            mapping_config_service=mapping_config,
            reference_resolution_service=reference_resolution,
            validation_service=validation
        )
    
    @classmethod
    def get_processing_pipeline_service(cls, session_storage=None) -> ProcessingPipelineService:
        """Get ProcessingPipelineService instance with dependencies"""
        # Always create new instance as it depends on other services
        table_analysis = cls.get_table_analysis_service()
        mapping_config = cls.get_mapping_configuration_service(session_storage)
        reference_resolution = cls.get_reference_resolution_service()
        validation = cls.get_validation_service()
        
        return ProcessingPipelineService(
            table_analysis_service=table_analysis,
            mapping_config_service=mapping_config,
            reference_resolution_service=reference_resolution,
            validation_service=validation
        )
    
    @classmethod
    def create_complete_service_set(cls, session_storage=None) -> dict:
        """Create a complete set of services for use in views or APIs"""
        return {
            'table_analysis': cls.get_table_analysis_service(),
            'mapping_configuration': cls.get_mapping_configuration_service(session_storage),
            'reference_resolution': cls.get_reference_resolution_service(),
            'validation': cls.get_validation_service(),
            'preview': cls.get_preview_service(session_storage),
            'processing_pipeline': cls.get_processing_pipeline_service(session_storage),
        }
    
    @classmethod
    def clear_instances(cls):
        """Clear all cached service instances (useful for testing)"""
        cls._instances.clear()
        logger.info("Service instances cleared")


def get_services_for_request(request=None):
    """
    Convenience function to get services configured for a Django request
    
    Args:
        request: Django HttpRequest object (optional, for session storage)
        
    Returns:
        Dictionary of service instances
    """
    session_storage = request.session if request else None
    return ServiceFactory.create_complete_service_set(session_storage)


def get_services_for_api():
    """
    Convenience function to get services configured for API use (no session)
    
    Returns:
        Dictionary of service instances
    """
    return ServiceFactory.create_complete_service_set(session_storage=None) 