"""
Data models for mapping-file correlation analysis.

These models provide deterministic binary results for file-dataset matching,
column correlation, and type compatibility checking.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path


@dataclass
class FileAnalysis:
    """Analysis result for a single CSV file."""
    file_path: str
    file_name: str
    column_count: int
    row_count: int
    columns: List[str]
    column_types: Dict[str, str]
    matched_dataset_name: Optional[str] = None  # Exact filename match to dataset or None
    sample_data: Optional[List[Dict[str, Any]]] = None
    
    def __post_init__(self):
        """Extract file name from path if not provided."""
        if not self.file_name:
            self.file_name = Path(self.file_path).stem


@dataclass
class MappingAnalysis:
    """Analysis result for mapping configuration."""
    mapping_id: str
    mapping_name: str
    expected_datasets: List[str]
    dataset_columns: Dict[str, List[str]]
    required_columns: Dict[str, List[str]]
    column_types: Dict[str, Dict[str, str]]
    relationships: List[Dict] = field(default_factory=list)


@dataclass
class DatasetCorrelation:
    """Exact correlation between a file and mapping dataset."""
    file_path: str
    dataset_name: str
    is_exact_match: bool  # True only if filename exactly matches dataset name
    matched_columns: List[str]  # Columns that exist in both file and mapping
    missing_columns: List[str]  # Required mapping columns not found in file
    extra_columns: List[str]  # File columns not defined in mapping
    type_mismatches: List[Dict]  # Exact type mismatches (string vs int, etc)
    status: Literal['exact_match', 'no_match']
    
    @property
    def has_issues(self) -> bool:
        """Check if this correlation has any issues."""
        return bool(self.missing_columns or self.type_mismatches)
    
    @property
    def coverage_percentage(self) -> float:
        """Calculate percentage of file columns that are mapped."""
        total_columns = len(self.matched_columns) + len(self.extra_columns)
        if total_columns == 0:
            return 0.0
        return (len(self.matched_columns) / total_columns) * 100


@dataclass
class CorrelationResult:
    """Complete deterministic correlation analysis result."""
    file_analyses: List[FileAnalysis]
    mapping_analysis: Optional[MappingAnalysis]
    dataset_correlations: List[DatasetCorrelation]
    exactly_matched_datasets: List[str]  # Datasets with exact filename matches
    missing_datasets: List[str]  # Required datasets with no matching files
    unmatched_files: List[str]  # Files that don't match any dataset names
    has_all_required_datasets: bool  # True only if every required dataset has exact match
    has_no_extra_files: bool  # True only if no unmatched files exist
    recommendations: List[str] = field(default_factory=list)
    
    @property
    def is_ready_for_execution(self) -> bool:
        """Check if the correlation is ready for execution."""
        return self.has_all_required_datasets and self.has_no_extra_files
    
    @property
    def total_issues_count(self) -> int:
        """Count total issues across all correlations."""
        issues = 0
        for correlation in self.dataset_correlations:
            if correlation.has_issues:
                issues += len(correlation.missing_columns) + len(correlation.type_mismatches)
        issues += len(self.missing_datasets) + len(self.unmatched_files)
        return issues
    
    @property
    def overall_coverage_percentage(self) -> float:
        """Calculate overall coverage across all matched files."""
        if not self.dataset_correlations:
            return 0.0
        
        total_coverage = sum(
            correlation.coverage_percentage 
            for correlation in self.dataset_correlations 
            if correlation.is_exact_match
        )
        matched_count = len([c for c in self.dataset_correlations if c.is_exact_match])
        
        return total_coverage / matched_count if matched_count > 0 else 0.0