"""
Domain Models for Relationship Discovery

Contains the core data structures used throughout the relationship discovery system.
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple


@dataclass
class ColumnRelationship:
    """Represents a potential relationship between two columns"""
    source_column: str
    target_column: str
    relationship_type: str  # 'foreign_key', 'semantic_similar', 'value_overlap', 'pattern_match'
    confidence: float
    evidence: Dict[str, Any]
    suggested_predicate: Optional[str] = None
    bidirectional: bool = False


@dataclass
class DatasetRelationshipAnalysis:
    """Complete relationship analysis for a dataset"""
    dataset_name: str
    column_count: int
    row_count: int
    column_names: List[str]
    relationships: List[ColumnRelationship]
    relationship_matrix: Dict[Tuple[str, str], float]
    semantic_clusters: List[List[str]]
    foreign_key_candidates: List[str]
    quality_metrics: Dict[str, float]