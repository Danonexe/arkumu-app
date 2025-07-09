"""
Tests for the validation result classes.
"""

import pytest
from datetime import datetime
from arkumu.importer.services.pre_execution_validation.validation_result import (
    ValidationIssue,
    ValidationSeverity,
    ValidationCategory,
    ValidationMode,
    PreExecutionValidationResult,
    FileValidationResult,
    ColumnMappingValidationResult,
    RelationshipValidationResult,
    ResourceEstimate,
    ValidationErrorCodes
)


class TestValidationIssue:
    """Test ValidationIssue class"""
    
    def test_creation(self):
        """Test creating a ValidationIssue"""
        issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error message",
            file_path="/test/file.csv",
            column_name="test_column",
            line_number=42,
            suggested_fix="Fix this issue"
        )
        
        assert issue.code == "TEST_ERROR"
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.category == ValidationCategory.FILE_STRUCTURE
        assert issue.message == "Test error message"
        assert issue.file_path == "/test/file.csv"
        assert issue.column_name == "test_column"
        assert issue.line_number == 42
        assert issue.suggested_fix == "Fix this issue"
    
    def test_str_representation(self):
        """Test string representation of ValidationIssue"""
        issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error message",
            file_path="/test/file.csv",
            column_name="test_column",
            line_number=42
        )
        
        str_repr = str(issue)
        assert "[ERROR]" in str_repr
        assert "TEST_ERROR" in str_repr
        assert "Test error message" in str_repr
        assert "file: /test/file.csv" in str_repr
        assert "column: test_column" in str_repr
        assert "line: 42" in str_repr
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error message",
            file_path="/test/file.csv"
        )
        
        issue_dict = issue.to_dict()
        
        assert issue_dict["code"] == "TEST_ERROR"
        assert issue_dict["severity"] == "error"
        assert issue_dict["category"] == "file_structure"
        assert issue_dict["message"] == "Test error message"
        assert issue_dict["file_path"] == "/test/file.csv"


class TestPreExecutionValidationResult:
    """Test PreExecutionValidationResult class"""
    
    def test_creation(self):
        """Test creating a PreExecutionValidationResult"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=0.85
        )
        
        assert result.is_valid is True
        assert result.validation_mode == ValidationMode.STRICT
        # Confidence gets recalculated in __post_init__ - with no issues, it becomes 1.0
        assert result.overall_confidence == 1.0
        assert len(result.all_issues) == 0
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.infos) == 0
    
    def test_add_issue(self):
        """Test adding issues to the result"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=1.0
        )
        
        # Add an error issue
        error_issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error"
        )
        result.add_issue(error_issue)
        
        assert len(result.all_issues) == 1
        assert len(result.errors) == 1
        assert len(result.warnings) == 0
        assert result.overall_confidence < 1.0  # Should be recalculated
        
        # Add a warning issue
        warning_issue = ValidationIssue(
            code="TEST_WARNING",
            severity=ValidationSeverity.WARNING,
            category=ValidationCategory.COLUMN_MAPPING,
            message="Test warning"
        )
        result.add_issue(warning_issue)
        
        assert len(result.all_issues) == 2
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
    
    def test_has_blocking_issues(self):
        """Test blocking issues detection"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=1.0
        )
        
        # No blocking issues initially
        assert result.has_blocking_issues() is False
        
        # Add a warning - not blocking
        warning_issue = ValidationIssue(
            code="TEST_WARNING",
            severity=ValidationSeverity.WARNING,
            category=ValidationCategory.COLUMN_MAPPING,
            message="Test warning"
        )
        result.add_issue(warning_issue)
        assert result.has_blocking_issues() is False
        
        # Add an error - blocking
        error_issue = ValidationIssue(
            code="TEST_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Test error"
        )
        result.add_issue(error_issue)
        assert result.has_blocking_issues() is True
    
    def test_get_issues_by_category(self):
        """Test filtering issues by category"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=1.0
        )
        
        # Add issues from different categories
        file_issue = ValidationIssue(
            code="FILE_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="File error"
        )
        
        column_issue = ValidationIssue(
            code="COLUMN_ERROR",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.COLUMN_MAPPING,
            message="Column error"
        )
        
        result.add_issue(file_issue)
        result.add_issue(column_issue)
        
        file_issues = result.get_issues_by_category(ValidationCategory.FILE_STRUCTURE)
        assert len(file_issues) == 1
        assert file_issues[0].code == "FILE_ERROR"
        
        column_issues = result.get_issues_by_category(ValidationCategory.COLUMN_MAPPING)
        assert len(column_issues) == 1
        assert column_issues[0].code == "COLUMN_ERROR"
    
    def test_get_issues_by_severity(self):
        """Test filtering issues by severity"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=1.0
        )
        
        # Add issues with different severities
        error_issue = ValidationIssue(
            code="ERROR_ISSUE",
            severity=ValidationSeverity.ERROR,
            category=ValidationCategory.FILE_STRUCTURE,
            message="Error issue"
        )
        
        warning_issue = ValidationIssue(
            code="WARNING_ISSUE",
            severity=ValidationSeverity.WARNING,
            category=ValidationCategory.COLUMN_MAPPING,
            message="Warning issue"
        )
        
        result.add_issue(error_issue)
        result.add_issue(warning_issue)
        
        error_issues = result.get_issues_by_severity(ValidationSeverity.ERROR)
        assert len(error_issues) == 1
        assert error_issues[0].code == "ERROR_ISSUE"
        
        warning_issues = result.get_issues_by_severity(ValidationSeverity.WARNING)
        assert len(warning_issues) == 1
        assert warning_issues[0].code == "WARNING_ISSUE"
    
    def test_get_summary(self):
        """Test getting validation summary"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=0.9
        )
        
        summary = result.get_summary()
        
        assert summary["is_valid"] is True
        # Confidence gets recalculated in __post_init__ - with no issues, it becomes 1.0
        assert summary["overall_confidence"] == 1.0
        assert summary["validation_mode"] == "strict"
        assert summary["total_issues"] == 0
        assert summary["errors"] == 0
        assert summary["warnings"] == 0
        assert summary["infos"] == 0
        assert summary["has_blocking_issues"] is False
        assert summary["execution_ready"] is True
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        result = PreExecutionValidationResult(
            is_valid=True,
            validation_mode=ValidationMode.STRICT,
            overall_confidence=0.9
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["is_valid"] is True
        assert result_dict["validation_mode"] == "strict"
        # Confidence gets recalculated in __post_init__ - with no issues, it becomes 1.0
        assert result_dict["overall_confidence"] == 1.0
        assert "all_issues" in result_dict
        assert "summary" in result_dict
        assert "validation_timestamp" in result_dict
        assert "validation_duration" in result_dict


class TestFileValidationResult:
    """Test FileValidationResult class"""
    
    def test_creation(self):
        """Test creating a FileValidationResult"""
        result = FileValidationResult(
            file_path="/test/file.csv",
            is_valid=True,
            file_size=1024,
            column_count=5,
            row_count=100,
            missing_columns=["col1"],
            extra_columns=["col2"],
            encoding="utf-8",
            delimiter=","
        )
        
        assert result.file_path == "/test/file.csv"
        assert result.is_valid is True
        assert result.file_size == 1024
        assert result.column_count == 5
        assert result.row_count == 100
        assert result.missing_columns == ["col1"]
        assert result.extra_columns == ["col2"]
        assert result.encoding == "utf-8"
        assert result.delimiter == ","
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        result = FileValidationResult(
            file_path="/test/file.csv",
            is_valid=True,
            file_size=1024,
            column_count=5,
            row_count=100
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["file_path"] == "/test/file.csv"
        assert result_dict["is_valid"] is True
        assert result_dict["file_size"] == 1024
        assert result_dict["column_count"] == 5
        assert result_dict["row_count"] == 100


class TestColumnMappingValidationResult:
    """Test ColumnMappingValidationResult class"""
    
    def test_creation(self):
        """Test creating a ColumnMappingValidationResult"""
        result = ColumnMappingValidationResult(
            mapped_columns={"col1": "prop1", "col2": "prop2"},
            unmapped_columns=["col3", "col4"],
            missing_required_columns=["col5"],
            type_mismatches=[{"column": "col1", "expected": "string", "actual": "int"}],
            transformation_warnings=[],
            coverage_percentage=80.0
        )
        
        assert result.mapped_columns == {"col1": "prop1", "col2": "prop2"}
        assert result.unmapped_columns == ["col3", "col4"]
        assert result.missing_required_columns == ["col5"]
        assert len(result.type_mismatches) == 1
        assert result.coverage_percentage == 80.0
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        result = ColumnMappingValidationResult(
            mapped_columns={"col1": "prop1"},
            unmapped_columns=["col2"],
            missing_required_columns=["col3"],
            type_mismatches=[],
            transformation_warnings=[],
            coverage_percentage=60.0
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["mapped_columns"] == {"col1": "prop1"}
        assert result_dict["unmapped_columns"] == ["col2"]
        assert result_dict["missing_required_columns"] == ["col3"]
        assert result_dict["coverage_percentage"] == 60.0


class TestResourceEstimate:
    """Test ResourceEstimate class"""
    
    def test_creation(self):
        """Test creating a ResourceEstimate"""
        estimate = ResourceEstimate(
            estimated_execution_time=120.5,
            estimated_memory_usage=512,
            estimated_disk_usage=1024,
            estimated_cpu_usage=75.0,
            complexity_score=7,
            parallel_processing_recommendation=True,
            chunking_recommendation={"recommended": True, "chunk_size": 10000}
        )
        
        assert estimate.estimated_execution_time == 120.5
        assert estimate.estimated_memory_usage == 512
        assert estimate.estimated_disk_usage == 1024
        assert estimate.estimated_cpu_usage == 75.0
        assert estimate.complexity_score == 7
        assert estimate.parallel_processing_recommendation is True
        assert estimate.chunking_recommendation["recommended"] is True
    
    def test_to_dict(self):
        """Test serialization to dictionary"""
        estimate = ResourceEstimate(
            estimated_execution_time=120.5,
            estimated_memory_usage=512,
            estimated_disk_usage=1024,
            estimated_cpu_usage=75.0,
            complexity_score=7
        )
        
        estimate_dict = estimate.to_dict()
        
        assert estimate_dict["estimated_execution_time"] == 120.5
        assert estimate_dict["estimated_memory_usage"] == 512
        assert estimate_dict["estimated_disk_usage"] == 1024
        assert estimate_dict["estimated_cpu_usage"] == 75.0
        assert estimate_dict["complexity_score"] == 7


class TestValidationErrorCodes:
    """Test ValidationErrorCodes class"""
    
    def test_error_codes_exist(self):
        """Test that error codes are defined"""
        # File structure errors
        assert hasattr(ValidationErrorCodes, 'FILE_NOT_FOUND')
        assert hasattr(ValidationErrorCodes, 'FILE_NOT_READABLE')
        assert hasattr(ValidationErrorCodes, 'FILE_EMPTY')
        assert hasattr(ValidationErrorCodes, 'FILE_TOO_LARGE')
        
        # Column mapping errors
        assert hasattr(ValidationErrorCodes, 'REQUIRED_COLUMN_MISSING')
        assert hasattr(ValidationErrorCodes, 'COLUMN_TYPE_MISMATCH')
        assert hasattr(ValidationErrorCodes, 'UNMAPPED_REQUIRED_COLUMN')
        
        # Relationship errors
        assert hasattr(ValidationErrorCodes, 'MISSING_FOREIGN_KEY')
        assert hasattr(ValidationErrorCodes, 'INVALID_RELATIONSHIP')
        assert hasattr(ValidationErrorCodes, 'CIRCULAR_DEPENDENCY')
        
        # Resource warnings
        assert hasattr(ValidationErrorCodes, 'HIGH_MEMORY_USAGE')
        assert hasattr(ValidationErrorCodes, 'LONG_EXECUTION_TIME')
        assert hasattr(ValidationErrorCodes, 'DISK_SPACE_WARNING')
    
    def test_error_codes_are_strings(self):
        """Test that error codes are string constants"""
        assert isinstance(ValidationErrorCodes.FILE_NOT_FOUND, str)
        assert isinstance(ValidationErrorCodes.REQUIRED_COLUMN_MISSING, str)
        assert isinstance(ValidationErrorCodes.INVALID_RELATIONSHIP, str)
        assert isinstance(ValidationErrorCodes.HIGH_MEMORY_USAGE, str)