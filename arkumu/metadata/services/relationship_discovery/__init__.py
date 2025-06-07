"""
Relationship Discovery Package

A modular package for discovering potential semantic relationships between columns
within and across datasets. Provides data-driven analysis to guide users in
understanding column relationships before data transformation.
"""

from .service import RelationshipDiscoveryService
from .domain import ColumnRelationship, DatasetRelationshipAnalysis

__all__ = [
    'RelationshipDiscoveryService',
    'ColumnRelationship', 
    'DatasetRelationshipAnalysis'
]