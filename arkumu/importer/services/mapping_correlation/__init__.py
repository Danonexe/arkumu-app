"""
Mapping-File Correlation Service

Provides deterministic matching between selected CSV files and mapping configurations
in the ingest UI. Performs exact filename and column matching with binary results.
"""

from .correlation_service import MappingFileCorrelationService
from .data_models import (
    FileAnalysis,
    MappingAnalysis, 
    DatasetCorrelation,
    CorrelationResult
)

__all__ = [
    'MappingFileCorrelationService',
    'FileAnalysis',
    'MappingAnalysis',
    'DatasetCorrelation', 
    'CorrelationResult'
]