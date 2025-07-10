"""
Mapping Consumer Package

This package handles the consumption and translation of mapping configurations
from the arkumu.metadata app for use by the execution engine.

Key Components:
- MappingAdapter: Loads mapping configs from database
- ConfigTranslator: Converts GUI format to execution format  
- DependencyResolver: Handles FK dependencies
- DEPRECATED: ValidationService (replaced by arkumu.importer.services.mapping_validation.validator.MappingValidator)
"""

from .mapping_adapter import MappingAdapter
from .config_translator import (
    ConfigTranslator, 
    ExecutionConfig, 
    ColumnConfig, 
    ColumnType,
    ProcessingStrategy,
    FKRelationship,
    RelationshipContext,
    DatasetConfig
)
from .dependency_resolver import DependencyResolver
# DEPRECATED - keeping for backward compatibility only
from .validation import ValidationService, ValidationResult

__all__ = [
    'MappingAdapter',
    'ConfigTranslator', 
    'ExecutionConfig',
    'ColumnConfig',
    'ColumnType',
    'ProcessingStrategy',
    'FKRelationship',
    'RelationshipContext',
    'DatasetConfig',
    'DependencyResolver',
    'ValidationService',
    'ValidationResult'
]