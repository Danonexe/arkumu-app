"""
Metadata Services Module

This module provides a comprehensive set of services for semantic data transformation,
designed to be used both in Django views and REST API endpoints.

Services Architecture:
- TableAnalysisService: Analyze CSV structure and discover patterns
- MappingConfigurationService: Manage mapping rules and templates
- ProcessingPipelineService: Execute multi-phase transformations
- ReferenceResolutionService: Handle cross-table references and FK resolution
- ValidationService: Data quality checks and integrity validation
- PreviewService: Simulation and impact analysis before execution
- ServiceFactory: Factory for creating and configuring service instances
"""

from .table_analysis import TableAnalysisService
from .mapping_configuration import MappingConfigurationService
from .processing_pipeline import ProcessingPipelineService
from .reference_resolution import ReferenceResolutionService
from .validation import ValidationService
from .preview import PreviewService
from .service_factory import ServiceFactory

__all__ = [
    'TableAnalysisService',
    'MappingConfigurationService', 
    'ProcessingPipelineService',
    'ReferenceResolutionService',
    'ValidationService',
    'PreviewService',
    'ServiceFactory',
] 