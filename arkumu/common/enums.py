"""Common enums shared across the Arkumu application."""
from enum import Enum


class UpdateStrategy(Enum):
    """Strategies for handling existing data during bulk imports."""
    SKIP_EXISTING = "skip_existing"  # Skip if resource already exists
    UPDATE_VALUES = "update_values"  # Update existing literal values
    MERGE_TRIPLES = "merge_triples"  # Add new triples, keep existing ones
    REPLACE_ALL = "replace_all"      # Replace all data for the entity
    TIMESTAMP_BASED = "timestamp_based"  # Use timestamps to determine updates


class LiteralURIStrategy(Enum):
    """Strategies for generating literal URIs."""
    CONTEXTUAL = "contextual"  # Context-based URIs with institution prefix (legacy)
    CANONICAL = "canonical"    # Canonical content-based URIs
    SEMANTIC = "semantic"      # Semantic type-based URIs with datatype path