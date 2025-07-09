"""
Pre-execution validation service for the import pipeline.

This package provides comprehensive validation of mapping configurations and files
before execution to ensure successful import operations.
"""

from .validation_result import (
    PreExecutionValidationResult,
    FileValidationResult,
    ColumnMappingValidationResult,
    RelationshipValidationResult,
    ResourceEstimate,
    ValidationIssue,
    ValidationSeverity,
    ValidationCategory,
    ValidationMode,
    ValidationErrorCodes
)

# PreExecutionValidator requires external dependencies, so import conditionally
try:
    from .pre_execution_validator import PreExecutionValidator
    _VALIDATOR_AVAILABLE = True
except ImportError:
    _VALIDATOR_AVAILABLE = False
    # Create a placeholder class for when dependencies are not available
    class PreExecutionValidator:
        def __init__(self, *args, **kwargs):
            raise ImportError("PreExecutionValidator requires additional dependencies (polars, etc.)")

__all__ = [
    'PreExecutionValidator',
    'PreExecutionValidationResult',
    'FileValidationResult',
    'ColumnMappingValidationResult',
    'RelationshipValidationResult',
    'ResourceEstimate',
    'ValidationIssue',
    'ValidationSeverity',
    'ValidationCategory',
    'ValidationMode',
    'ValidationErrorCodes'
]