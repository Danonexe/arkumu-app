"""
Pre-execution validation result classes and error codes.

This module provides comprehensive result classes and error codes for
pre-execution validation in the import pipeline.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """Categories of validation issues"""
    FILE_STRUCTURE = "file_structure"
    COLUMN_MAPPING = "column_mapping"
    RELATIONSHIP_VALIDATION = "relationship_validation"
    RESOURCE_ESTIMATION = "resource_estimation"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    COMPATIBILITY = "compatibility"


class ValidationMode(Enum):
    """Validation modes"""
    STRICT = "strict"  # Fail on any error
    WARNING_ONLY = "warning_only"  # Convert errors to warnings
    LENIENT = "lenient"  # Allow minor issues


@dataclass
class ValidationIssue:
    """Represents a single validation issue"""
    code: str
    severity: ValidationSeverity
    category: ValidationCategory
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    column_name: Optional[str] = None
    line_number: Optional[int] = None
    suggested_fix: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of the validation issue"""
        location = []
        if self.file_path:
            location.append(f"file: {self.file_path}")
        if self.column_name:
            location.append(f"column: {self.column_name}")
        if self.line_number:
            location.append(f"line: {self.line_number}")
        
        location_str = f" ({', '.join(location)})" if location else ""
        return f"[{self.severity.value.upper()}] {self.code}: {self.message}{location_str}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "code": self.code,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "details": self.details,
            "file_path": self.file_path,
            "column_name": self.column_name,
            "line_number": self.line_number,
            "suggested_fix": self.suggested_fix
        }


@dataclass
class ResourceEstimate:
    """Resource estimation for mapping execution"""
    estimated_execution_time: float  # in seconds
    estimated_memory_usage: int  # in MB
    estimated_disk_usage: int  # in MB
    estimated_cpu_usage: float  # percentage
    file_processing_time: Dict[str, float] = field(default_factory=dict)  # per file
    complexity_score: int = 0  # 1-10 scale
    parallel_processing_recommendation: bool = False
    chunking_recommendation: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "estimated_execution_time": self.estimated_execution_time,
            "estimated_memory_usage": self.estimated_memory_usage,
            "estimated_disk_usage": self.estimated_disk_usage,
            "estimated_cpu_usage": self.estimated_cpu_usage,
            "file_processing_time": self.file_processing_time,
            "complexity_score": self.complexity_score,
            "parallel_processing_recommendation": self.parallel_processing_recommendation,
            "chunking_recommendation": self.chunking_recommendation
        }


@dataclass
class FileValidationResult:
    """Result of file structure validation"""
    file_path: str
    is_valid: bool
    file_size: int
    column_count: int
    row_count: int
    missing_columns: List[str] = field(default_factory=list)
    extra_columns: List[str] = field(default_factory=list)
    column_types: Dict[str, str] = field(default_factory=dict)
    encoding: str = "utf-8"
    delimiter: str = ","
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue to this result"""
        self.issues.append(issue)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "file_path": self.file_path,
            "is_valid": self.is_valid,
            "file_size": self.file_size,
            "column_count": self.column_count,
            "row_count": self.row_count,
            "missing_columns": self.missing_columns,
            "extra_columns": self.extra_columns,
            "column_types": self.column_types,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "issues": [issue.to_dict() for issue in self.issues]
        }


@dataclass
class ColumnMappingValidationResult:
    """Result of column mapping validation"""
    mapped_columns: Dict[str, str]  # source -> target mapping
    unmapped_columns: List[str]
    missing_required_columns: List[str]
    type_mismatches: List[Dict[str, Any]]
    transformation_warnings: List[ValidationIssue]
    coverage_percentage: float
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "mapped_columns": self.mapped_columns,
            "unmapped_columns": self.unmapped_columns,
            "missing_required_columns": self.missing_required_columns,
            "type_mismatches": self.type_mismatches,
            "transformation_warnings": [warning.to_dict() for warning in self.transformation_warnings],
            "coverage_percentage": self.coverage_percentage,
            "issues": [issue.to_dict() for issue in self.issues]
        }


@dataclass
class RelationshipValidationResult:
    """Result of relationship validation"""
    valid_relationships: List[str]
    invalid_relationships: List[str]
    missing_dependencies: List[str]
    circular_dependencies: List[List[str]]
    foreign_key_issues: List[Dict[str, Any]]
    orphaned_records_estimate: int
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "valid_relationships": self.valid_relationships,
            "invalid_relationships": self.invalid_relationships,
            "missing_dependencies": self.missing_dependencies,
            "circular_dependencies": self.circular_dependencies,
            "foreign_key_issues": self.foreign_key_issues,
            "orphaned_records_estimate": self.orphaned_records_estimate,
            "issues": [issue.to_dict() for issue in self.issues]
        }


@dataclass
class PreExecutionValidationResult:
    """Comprehensive result of pre-execution validation"""
    is_valid: bool
    validation_mode: ValidationMode
    overall_confidence: float  # 0.0 to 1.0
    
    # Individual validation results
    file_validation_results: List[FileValidationResult] = field(default_factory=list)
    column_mapping_result: Optional[ColumnMappingValidationResult] = None
    relationship_validation_result: Optional[RelationshipValidationResult] = None
    resource_estimate: Optional[ResourceEstimate] = None
    
    # Aggregated issues
    all_issues: List[ValidationIssue] = field(default_factory=list)
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    infos: List[ValidationIssue] = field(default_factory=list)
    
    # Execution recommendations
    execution_recommendations: List[str] = field(default_factory=list)
    required_actions: List[str] = field(default_factory=list)
    
    # Metadata
    validation_timestamp: datetime = field(default_factory=datetime.now)
    validation_duration: float = 0.0  # in seconds
    
    def __post_init__(self):
        """Post-initialization processing"""
        self._categorize_issues()
        self._calculate_overall_confidence()
    
    def _categorize_issues(self):
        """Categorize all issues by severity"""
        self.errors = [issue for issue in self.all_issues if issue.severity == ValidationSeverity.ERROR]
        self.warnings = [issue for issue in self.all_issues if issue.severity == ValidationSeverity.WARNING]
        self.infos = [issue for issue in self.all_issues if issue.severity == ValidationSeverity.INFO]
    
    def _calculate_overall_confidence(self):
        """Calculate overall confidence score - simplified deterministic approach"""
        # Deterministic confidence: 1.0 if no blocking issues, 0.0 if blocking issues exist
        if self.has_blocking_issues():
            self.overall_confidence = 0.0
        else:
            self.overall_confidence = 1.0
    
    def get_issues_by_category(self, category: ValidationCategory) -> List[ValidationIssue]:
        """Get issues filtered by category"""
        return [issue for issue in self.all_issues if issue.category == category]
    
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get issues filtered by severity"""
        return [issue for issue in self.all_issues if issue.severity == severity]
    
    def has_blocking_issues(self) -> bool:
        """Check if there are any blocking issues"""
        return any(issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR] 
                  for issue in self.all_issues)
    
    def add_issue(self, issue: ValidationIssue):
        """Add an issue to the result"""
        self.all_issues.append(issue)
        self._categorize_issues()
        self._calculate_overall_confidence()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the validation result"""
        return {
            "is_valid": self.is_valid,
            "overall_confidence": self.overall_confidence,
            "validation_mode": self.validation_mode.value,
            "total_issues": len(self.all_issues),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "infos": len(self.infos),
            "files_validated": len(self.file_validation_results),
            "has_blocking_issues": self.has_blocking_issues(),
            "execution_ready": self.is_valid and not self.has_blocking_issues(),
            "validation_duration": self.validation_duration
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "is_valid": self.is_valid,
            "validation_mode": self.validation_mode.value,
            "overall_confidence": self.overall_confidence,
            "file_validation_results": [result.to_dict() for result in self.file_validation_results],
            "column_mapping_result": self.column_mapping_result.to_dict() if self.column_mapping_result else None,
            "relationship_validation_result": self.relationship_validation_result.to_dict() if self.relationship_validation_result else None,
            "resource_estimate": self.resource_estimate.to_dict() if self.resource_estimate else None,
            "all_issues": [issue.to_dict() for issue in self.all_issues],
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "infos": [issue.to_dict() for issue in self.infos],
            "execution_recommendations": self.execution_recommendations,
            "required_actions": self.required_actions,
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "validation_duration": self.validation_duration,
            "summary": self.get_summary()
        }


# Error codes for validation issues
class ValidationErrorCodes:
    """Standard error codes for validation issues"""
    
    # File structure errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_NOT_READABLE = "FILE_NOT_READABLE"
    FILE_EMPTY = "FILE_EMPTY"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    ENCODING_ERROR = "ENCODING_ERROR"
    MALFORMED_CSV = "MALFORMED_CSV"
    HEADER_MISSING = "HEADER_MISSING"
    DUPLICATE_HEADERS = "DUPLICATE_HEADERS"
    
    # Column mapping errors
    REQUIRED_COLUMN_MISSING = "REQUIRED_COLUMN_MISSING"
    COLUMN_TYPE_MISMATCH = "COLUMN_TYPE_MISMATCH"
    INVALID_COLUMN_NAME = "INVALID_COLUMN_NAME"
    UNMAPPED_REQUIRED_COLUMN = "UNMAPPED_REQUIRED_COLUMN"
    TRANSFORMATION_ERROR = "TRANSFORMATION_ERROR"
    DATA_QUALITY_ISSUE = "DATA_QUALITY_ISSUE"
    
    # Relationship validation errors
    MISSING_FOREIGN_KEY = "MISSING_FOREIGN_KEY"
    INVALID_RELATIONSHIP = "INVALID_RELATIONSHIP"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    ORPHANED_RECORDS = "ORPHANED_RECORDS"
    DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
    REFERENCE_TABLE_MISSING = "REFERENCE_TABLE_MISSING"
    
    # Resource estimation warnings
    HIGH_MEMORY_USAGE = "HIGH_MEMORY_USAGE"
    LONG_EXECUTION_TIME = "LONG_EXECUTION_TIME"
    DISK_SPACE_WARNING = "DISK_SPACE_WARNING"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    
    # Configuration errors
    INVALID_MAPPING_CONFIG = "INVALID_MAPPING_CONFIG"
    MISSING_CONFIGURATION = "MISSING_CONFIGURATION"
    INCOMPATIBLE_SETTINGS = "INCOMPATIBLE_SETTINGS"
    
    # General validation errors
    VALIDATION_TIMEOUT = "VALIDATION_TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"