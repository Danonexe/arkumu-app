"""
Progress tracking services for import operations.

This package provides enhanced progress tracking capabilities including:
- Mapping-aware progress estimation
- Phase-based progress tracking
- Complexity-based duration estimates
- Enhanced user feedback
"""

from .mapping_progress_estimator import (
    MappingProgressEstimator,
    ExecutionStrategy,
    MappingComplexity,
    PhaseEstimate,
    progress_estimator
)

__all__ = [
    'MappingProgressEstimator',
    'ExecutionStrategy', 
    'MappingComplexity',
    'PhaseEstimate',
    'progress_estimator'
]