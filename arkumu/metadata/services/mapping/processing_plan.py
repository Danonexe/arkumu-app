"""
Data structures for FK and mapping processing plans.

These classes define the interface between /metadata (analysis) and /importer (execution).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class FKDirection(Enum):
    """Direction of foreign key relationships."""
    OUTBOUND = "outbound"  # This entity references another
    INBOUND = "inbound"    # Another entity references this
    BIDIRECTIONAL = "bidirectional"  # Mutual references


@dataclass
class FKConfig:
    """Configuration for a single foreign key relationship."""
    source_dataset: str
    source_column: str
    target_dataset: str
    target_column: str
    direction: FKDirection = FKDirection.OUTBOUND
    predicate_uri: Optional[str] = None  # Custom relationship predicate
    
    def __post_init__(self):
        if isinstance(self.direction, str):
            self.direction = FKDirection(self.direction)


@dataclass
class ExternalOntologyConfig:
    """Configuration for external ontology mappings."""
    ontology_type: str  # "orcid", "wikidata", "gnd", etc.
    uri_template: str   # "https://orcid.org/{identifier}"
    identifier_pattern: Optional[str] = None  # Regex validation pattern
    
    def generate_uri(self, identifier: str) -> str:
        """Generate external URI from identifier."""
        return self.uri_template.format(identifier=identifier)


@dataclass
class AnchorColumnConfig:
    """Configuration for dataset anchor columns."""
    dataset: str
    column: str
    is_composite: bool = False  # True for multi-column anchors
    composite_columns: List[str] = field(default_factory=list)


@dataclass
class RelationshipContextConfig:
    """Configuration for n-ary relationship contexts."""
    context_predicate: str
    primary_fk_dataset: str
    primary_fk_column: str
    secondary_fk_dataset: str
    secondary_fk_column: str
    context_dataset: str  # Dataset containing the relationship context


@dataclass
class FKProcessingPlan:
    """Complete processing plan for FK-aware dataset import."""
    
    # Processing order: datasets grouped by dependency layers
    processing_order: List[List[str]] = field(default_factory=list)
    
    # FK relationship configurations
    fk_relationships: Dict[str, FKConfig] = field(default_factory=dict)
    
    # Anchor column configurations per dataset
    anchor_columns: Dict[str, AnchorColumnConfig] = field(default_factory=dict)
    
    # External ontology configurations per column
    external_ontologies: Dict[str, ExternalOntologyConfig] = field(default_factory=dict)
    
    # Relationship context configurations
    relationship_contexts: Dict[str, RelationshipContextConfig] = field(default_factory=dict)
    
    # Multi-value column configurations
    multi_value_columns: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Processing metadata
    organization_id: str = ""
    base_uri: str = "http://arkumu.org/data"
    
    def get_dependencies_for_dataset(self, dataset: str) -> List[str]:
        """Get list of datasets that must be processed before this one."""
        dependencies = []
        for fk_config in self.fk_relationships.values():
            if fk_config.source_dataset == dataset:
                dependencies.append(fk_config.target_dataset)
        return list(set(dependencies))
    
    def get_layer_for_dataset(self, dataset: str) -> int:
        """Get processing layer number for a dataset (0 = first layer)."""
        for layer_num, layer_datasets in enumerate(self.processing_order):
            if dataset in layer_datasets:
                return layer_num
        return -1  # Not found
    
    def has_fk_relationships(self) -> bool:
        """Check if this plan includes any FK relationships."""
        return len(self.fk_relationships) > 0
    
    def has_external_ontologies(self) -> bool:
        """Check if this plan includes any external ontology mappings."""
        return len(self.external_ontologies) > 0


@dataclass
class ValidationResult:
    """Result of FK processing plan validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, message: str):
        """Add validation error."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        """Add validation warning."""
        self.warnings.append(message) 