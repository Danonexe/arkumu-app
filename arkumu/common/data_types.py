"""Common data types shared across the Arkumu application."""
from dataclasses import dataclass, field
from typing import List, Optional

from .enums import UpdateStrategy


@dataclass
class BulkUpdateStats:
    """Statistics for bulk update operations."""
    rows_processed: int = 0
    cells_processed: int = 0
    resources_created: int = 0
    resources_updated: int = 0
    resources_skipped: int = 0
    triples_created: int = 0
    triples_updated: int = 0
    triples_skipped: int = 0
    row_links_created: int = 0
    errors: int = 0
    truncated_values: int = 0
    multi_value_cells_detected: int = 0
    relationships_created: int = 0
    
    def merge(self, other: 'BulkUpdateStats'):
        """Merge another stats object into this one."""
        self.rows_processed += other.rows_processed
        self.cells_processed += other.cells_processed
        self.resources_created += other.resources_created
        self.resources_updated += other.resources_updated
        self.resources_skipped += other.resources_skipped
        self.triples_created += other.triples_created
        self.triples_updated += other.triples_updated
        self.triples_skipped += other.triples_skipped
        self.row_links_created += other.row_links_created
        self.errors += other.errors
        self.truncated_values += other.truncated_values
        self.multi_value_cells_detected += other.multi_value_cells_detected
        self.relationships_created += other.relationships_created


@dataclass
class ResourceUpdate:
    """Represents a potential resource update."""
    uri: str
    new_values: List[str] = field(default_factory=list)  # Changed from new_value to support multiple values
    new_name: Optional[str] = None
    new_datatype: Optional[str] = None
    new_language: Optional[str] = None
    action: UpdateStrategy = UpdateStrategy.SKIP_EXISTING