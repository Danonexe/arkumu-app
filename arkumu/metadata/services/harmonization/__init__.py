"""
Harmonization Service Package

This package implements a semantic alignment layer on top of archive-specific data,
enabling unified queries across multiple archives with different schemas.

The service generates catalog-level URIs and alignment triples (owl:sameAs, skos:exactMatch)
to harmonize properties across archives while preserving original data integrity.
"""

from .harmonization_service import HarmonizationService
from .catalog_uri_generator import CatalogUriGenerator
from .alignment_generator import AlignmentGenerator
from .mapping_rules import RuleMatcher
from .bulk_processor import HarmonizationBulkProcessor
from .conflict_resolver import ConflictResolver

__all__ = [
    'HarmonizationService',
    'CatalogUriGenerator', 
    'AlignmentGenerator',
    'RuleMatcher',
    'HarmonizationBulkProcessor',
    'ConflictResolver'
]