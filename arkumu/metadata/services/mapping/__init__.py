"""
Mapping Services Module - FK and relationship mapping analysis.

This module provides services for analyzing GUI mapping configurations
and building processing plans for the importer.

Main Classes:
- MappingCoordinator: Orchestrates all mapping analysis
- FKAnalyzer: Analyzes foreign key configurations
- DependencyResolver: Builds dataset processing order
- FKProcessingPlan: Data structure for processing plans

Usage:
    from arkumu.metadata.services.mapping import MappingCoordinator
    
    coordinator = MappingCoordinator(organization_id="my_org")
    plan = coordinator.build_processing_plan(workspace_columns, selected_datasets)
"""

from .mapping_coordinator import MappingCoordinator
from .fk_analyzer import FKAnalyzer
from .dependency_resolver import DependencyResolver
from .processing_plan import (
    FKProcessingPlan,
    FKConfig,
    ExternalOntologyConfig,
    AnchorColumnConfig,
    RelationshipContextConfig,
    ValidationResult,
    FKDirection
)

__all__ = [
    'MappingCoordinator',
    'FKAnalyzer', 
    'DependencyResolver',
    'FKProcessingPlan',
    'FKConfig',
    'ExternalOntologyConfig',
    'AnchorColumnConfig',
    'RelationshipContextConfig',
    'ValidationResult',
    'FKDirection'
] 