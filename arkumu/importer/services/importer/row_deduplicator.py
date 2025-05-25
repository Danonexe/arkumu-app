import hashlib
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DuplicateStrategy(Enum):
    """Strategies for handling duplicate rows."""
    SKIP = "skip"  # Skip duplicate rows
    UPDATE = "update"  # Update existing row if newer
    KEEP_BOTH = "keep_both"  # Keep both versions
    MANUAL_REVIEW = "manual_review"  # Flag for manual review


@dataclass
class RowHash:
    """Represents a hashed row with metadata."""
    content_hash: str
    source_file: str
    row_number: int
    timestamp: Optional[str] = None
    raw_data: Dict[str, Any] = None


@dataclass
class DuplicateDetectionResult:
    """Result of duplicate detection for a row."""
    is_duplicate: bool
    existing_hash: Optional[RowHash] = None
    strategy: DuplicateStrategy = DuplicateStrategy.SKIP
    reason: str = ""


class RowDeduplicator:
    """
    Service for detecting and handling duplicate rows across CSV imports.
    Uses content hashing to identify duplicates regardless of row order.
    """
    
    def __init__(self, 
                 exclude_columns: Optional[List[str]] = None,
                 timestamp_columns: Optional[List[str]] = None):
        """
        Initialize the row deduplicator.
        
        Args:
            exclude_columns: Columns to exclude from hash (e.g., timestamps, auto-generated IDs)
            timestamp_columns: Columns that contain timestamps for update detection
        """
        self.exclude_columns = set(exclude_columns or [])
        self.timestamp_columns = set(timestamp_columns or [])
        
        # Automatically exclude timestamp columns from content hash
        # This allows detecting updates based on timestamps
        self.exclude_columns.update(self.timestamp_columns)
        
        self.row_hashes: Dict[str, RowHash] = {}  # content_hash -> RowHash
    
    def generate_row_hash(self, 
                         row_data: Dict[str, Any], 
                         source_file: str, 
                         row_number: int) -> RowHash:
        """
        Generate a hash for a row of data.
        
        Args:
            row_data: Dictionary of column_name -> value
            source_file: Name of the source CSV file
            row_number: Row number in the source file
            
        Returns:
            RowHash object
        """
        # Create content for hashing (excluding specified columns)
        hash_content = {}
        for key, value in row_data.items():
            if key not in self.exclude_columns:
                # Clean and standardize the value
                clean_value = self._clean_value(value)
                hash_content[key] = clean_value
        
        # Generate content hash (preserves exact content, excluding timestamps)
        content_hash = self._generate_hash(hash_content)
        
        # Extract timestamp if available
        timestamp = self._extract_timestamp(row_data)
        
        return RowHash(
            content_hash=content_hash,
            source_file=source_file,
            row_number=row_number,
            timestamp=timestamp,
            raw_data=row_data.copy()
        )
    
    def check_duplicate(self, row_hash: RowHash) -> DuplicateDetectionResult:
        """
        Check if a row is a duplicate and determine the appropriate strategy.
        
        Args:
            row_hash: RowHash to check
            
        Returns:
            DuplicateDetectionResult
        """
        # Check for exact content match (excluding timestamps)
        if row_hash.content_hash in self.row_hashes:
            existing = self.row_hashes[row_hash.content_hash]
            
            # If we have timestamp columns configured, this might be an update
            if self.timestamp_columns and row_hash.timestamp and existing.timestamp:
                if self._is_newer(row_hash.timestamp, existing.timestamp):
                    return DuplicateDetectionResult(
                        is_duplicate=True,
                        existing_hash=existing,
                        strategy=DuplicateStrategy.UPDATE,
                        reason=f"Newer version of row {existing.row_number} from {existing.source_file}"
                    )
                else:
                    return DuplicateDetectionResult(
                        is_duplicate=True,
                        existing_hash=existing,
                        strategy=DuplicateStrategy.SKIP,
                        reason=f"Older version of row {existing.row_number} from {existing.source_file}"
                    )
            
            # No timestamp info or same timestamp - exact duplicate
            return DuplicateDetectionResult(
                is_duplicate=True,
                existing_hash=existing,
                strategy=DuplicateStrategy.SKIP,
                reason=f"Exact duplicate of row {existing.row_number} from {existing.source_file}"
            )
        
        # Not a duplicate
        return DuplicateDetectionResult(is_duplicate=False)
    
    def add_row_hash(self, row_hash: RowHash):
        """Add a row hash to the tracking system."""
        self.row_hashes[row_hash.content_hash] = row_hash
    
    def process_row(self, 
                   row_data: Dict[str, Any], 
                   source_file: str, 
                   row_number: int) -> Tuple[RowHash, DuplicateDetectionResult]:
        """
        Process a single row: generate hash and check for duplicates.
        
        Args:
            row_data: Dictionary of column_name -> value
            source_file: Name of the source CSV file
            row_number: Row number in the source file
            
        Returns:
            Tuple of (RowHash, DuplicateDetectionResult)
        """
        row_hash = self.generate_row_hash(row_data, source_file, row_number)
        duplicate_result = self.check_duplicate(row_hash)
        
        if not duplicate_result.is_duplicate or duplicate_result.strategy == DuplicateStrategy.UPDATE:
            self.add_row_hash(row_hash)
        
        return row_hash, duplicate_result
    
    def _clean_value(self, value: Any) -> str:
        """Clean and standardize a value for hashing."""
        if value is None:
            return ""
        
        # Convert to string and strip whitespace
        clean_str = str(value).strip()
        
        # Handle empty values consistently
        if clean_str.lower() in ['', 'null', 'none', 'n/a', 'na']:
            return ""
        
        return clean_str
    
    def _generate_hash(self, content: Dict[str, str]) -> str:
        """Generate a hash from content."""
        # Sort keys for consistent ordering
        sorted_items = sorted(content.items())
        hash_string = json.dumps(sorted_items, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(hash_string.encode('utf-8')).hexdigest()
    
    def _extract_timestamp(self, row_data: Dict[str, Any]) -> Optional[str]:
        """Extract timestamp from row data if available."""
        for col in self.timestamp_columns:
            if col in row_data and row_data[col]:
                return str(row_data[col]).strip()
        return None
    
    def _is_newer(self, timestamp1: str, timestamp2: str) -> bool:
        """Check if timestamp1 is newer than timestamp2."""
        try:
            # Simple string comparison for now
            # In production, you'd want proper datetime parsing
            return timestamp1 > timestamp2
        except:
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about processed rows and duplicates."""
        total_rows = len(self.row_hashes)
        
        return {
            "total_unique_rows": total_rows,
            "duplicate_rate": 0.0  # We don't track duplicates in statistics anymore
        }




