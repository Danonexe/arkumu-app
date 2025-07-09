"""
Example usage of the PreExecutionValidator service.

This module demonstrates how to use the PreExecutionValidator for comprehensive
validation of mapping configurations and files before execution.
"""

import json
import logging
from typing import Dict, List, Any

from .pre_execution_validator import PreExecutionValidator
from .validation_result import ValidationMode, ValidationSeverity
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
from arkumu.importer.services.file_matching.file_dataset_matcher import FileDatasetMatcher

logger = logging.getLogger(__name__)


def example_basic_validation():
    """Basic example of pre-execution validation"""
    
    # Initialize validator
    validator = PreExecutionValidator(
        validation_mode=ValidationMode.STRICT
    )
    
    # Example mapping configuration
    mapping_config = {
        "institution": "example_university",
        "domain": "http://example.edu/",
        "anchor_column": "student_id",
        "column_delimiter": ",",
        "mappings": [
            {
                "source_column": "student_id",
                "property": "ex:studentId",
                "range": "xsd:string"
            },
            {
                "source_column": "name",
                "property": "ex:fullName",
                "range": "xsd:string"
            },
            {
                "source_column": "course_id",
                "property": "ex:enrolledIn",
                "object_column": "courses",
                "range": "ex:Course"
            }
        ]
    }
    
    # File paths to validate
    file_paths = [
        "/path/to/students.csv",
        "/path/to/courses.csv"
    ]
    
    # Perform validation
    result = validator.validate_mapping_execution(mapping_config, file_paths)
    
    # Print results
    print(f"Validation Result: {'PASSED' if result.is_valid else 'FAILED'}")
    print(f"Overall Confidence: {result.overall_confidence:.2f}")
    print(f"Issues Found: {len(result.all_issues)}")
    
    # Print issues by severity
    for severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR, ValidationSeverity.WARNING]:
        severity_issues = result.get_issues_by_severity(severity)
        if severity_issues:
            print(f"\n{severity.value.upper()} Issues:")
            for issue in severity_issues:
                print(f"  - {issue}")
    
    # Print recommendations
    if result.execution_recommendations:
        print("\nExecution Recommendations:")
        for rec in result.execution_recommendations:
            print(f"  - {rec}")
    
    # Print resource estimates
    if result.resource_estimate:
        print(f"\nResource Estimates:")
        print(f"  - Execution Time: {result.resource_estimate.estimated_execution_time:.1f}s")
        print(f"  - Memory Usage: {result.resource_estimate.estimated_memory_usage}MB")
        print(f"  - Complexity Score: {result.resource_estimate.complexity_score}/10")
    
    return result


def example_with_mapping_adapter():
    """Example using MappingAdapter integration"""
    
    # Initialize with mapping adapter
    mapping_adapter = MappingAdapter()
    validator = PreExecutionValidator(
        mapping_adapter=mapping_adapter,
        validation_mode=ValidationMode.WARNING_ONLY
    )
    
    # Load mapping from database
    mapping_id = 123
    try:
        mapping_config = mapping_adapter.load_mapping_config(mapping_id)
        
        # File paths (would typically come from user selection)
        file_paths = [
            "/uploads/data_file_1.csv",
            "/uploads/data_file_2.csv"
        ]
        
        # Validate
        result = validator.validate_mapping_execution(mapping_config, file_paths)
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to load mapping {mapping_id}: {e}")
        return None


def example_file_structure_validation():
    """Example of individual file structure validation"""
    
    validator = PreExecutionValidator()
    
    # Dataset configuration (simplified)
    dataset_config = {
        "required_columns": ["id", "name", "email"],
        "delimiter": ",",
        "encoding": "utf-8"
    }
    
    file_path = "/path/to/data.csv"
    
    # Validate individual file
    result = validator.validate_file_structure(file_path, dataset_config)
    
    print(f"File Validation: {'PASSED' if result.is_valid else 'FAILED'}")
    print(f"File Size: {result.file_size} bytes")
    print(f"Columns: {result.column_count}")
    print(f"Rows: {result.row_count}")
    
    if result.issues:
        print("\nIssues:")
        for issue in result.issues:
            print(f"  - {issue}")
    
    return result


def example_column_mapping_validation():
    """Example of column mapping validation"""
    
    validator = PreExecutionValidator()
    
    # File columns (from actual file)
    file_columns = ["student_id", "full_name", "email", "course_code", "grade"]
    
    # Mapping configuration
    mapping_config = {
        "mappings": [
            {
                "source_column": "student_id",
                "property": "ex:studentId"
            },
            {
                "source_column": "full_name",
                "property": "ex:name"
            },
            {
                "source_column": "course_code",
                "property": "ex:courseCode"
            }
        ]
    }
    
    # Validate column mapping
    result = validator.validate_column_mapping(file_columns, mapping_config)
    
    print(f"Column Mapping Coverage: {result.coverage_percentage:.1f}%")
    print(f"Mapped Columns: {len(result.mapped_columns)}")
    print(f"Unmapped Columns: {result.unmapped_columns}")
    print(f"Missing Required: {result.missing_required_columns}")
    
    return result


def example_relationship_validation():
    """Example of relationship validation"""
    
    validator = PreExecutionValidator()
    
    # Mapping with relationships
    mapping_config = {
        "mappings": [
            {
                "source_column": "student_id",
                "property": "ex:studentId",
                "range": "xsd:string"
            },
            {
                "source_column": "course_id",
                "property": "ex:enrolledIn",
                "object_column": "courses",
                "range": "ex:Course"
            },
            {
                "source_column": "instructor_id",
                "property": "ex:taughtBy",
                "object_column": "instructors",
                "range": "ex:Instructor"
            }
        ]
    }
    
    # Validate relationships
    result = validator.validate_relationship_requirements(mapping_config)
    
    print(f"Valid Relationships: {result.valid_relationships}")
    print(f"Invalid Relationships: {result.invalid_relationships}")
    print(f"Missing Dependencies: {result.missing_dependencies}")
    
    if result.circular_dependencies:
        print(f"Circular Dependencies: {result.circular_dependencies}")
    
    return result


def example_resource_estimation():
    """Example of resource estimation"""
    
    validator = PreExecutionValidator()
    
    # Complex mapping configuration
    mapping_config = {
        "mappings": [
            {
                "source_column": "id",
                "property": "ex:id",
                "range": "xsd:string"
            },
            {
                "source_column": "name",
                "property": "ex:name",
                "range": "xsd:string"
            },
            {
                "source_column": "department",
                "property": "ex:belongsTo",
                "object_column": "departments",
                "range": "ex:Department"
            }
        ]
    }
    
    # File sizes (in bytes)
    file_sizes = [
        50 * 1024 * 1024,  # 50MB
        100 * 1024 * 1024,  # 100MB
        25 * 1024 * 1024   # 25MB
    ]
    
    # Estimate resources
    estimate = validator.estimate_resource_requirements(mapping_config, file_sizes)
    
    print(f"Estimated Execution Time: {estimate.estimated_execution_time:.1f}s")
    print(f"Estimated Memory Usage: {estimate.estimated_memory_usage}MB")
    print(f"Estimated Disk Usage: {estimate.estimated_disk_usage}MB")
    print(f"Complexity Score: {estimate.complexity_score}/10")
    print(f"Parallel Processing Recommended: {estimate.parallel_processing_recommendation}")
    
    if estimate.chunking_recommendation:
        print(f"Chunking Recommended: {estimate.chunking_recommendation}")
    
    return estimate


def example_validation_modes():
    """Example of different validation modes"""
    
    # Problematic mapping config (for demonstration)
    mapping_config = {
        "institution": "example_university",
        "domain": "http://example.edu/",
        "anchor_column": "missing_column",  # This column doesn't exist
        "mappings": [
            {
                "source_column": "existing_column",
                "property": "ex:prop"
            },
            {
                "source_column": "missing_column",  # This will cause an error
                "property": "ex:missing"
            }
        ]
    }
    
    file_paths = ["/path/to/test.csv"]
    
    print("=== STRICT Mode ===")
    validator_strict = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
    result_strict = validator_strict.validate_mapping_execution(mapping_config, file_paths)
    print(f"Valid: {result_strict.is_valid}")
    print(f"Errors: {len(result_strict.errors)}")
    
    print("\n=== WARNING_ONLY Mode ===")
    validator_warning = PreExecutionValidator(validation_mode=ValidationMode.WARNING_ONLY)
    result_warning = validator_warning.validate_mapping_execution(mapping_config, file_paths)
    print(f"Valid: {result_warning.is_valid}")
    print(f"Errors: {len(result_warning.errors)}")
    
    print("\n=== LENIENT Mode ===")
    validator_lenient = PreExecutionValidator(validation_mode=ValidationMode.LENIENT)
    result_lenient = validator_lenient.validate_mapping_execution(mapping_config, file_paths)
    print(f"Valid: {result_lenient.is_valid}")
    print(f"Errors: {len(result_lenient.errors)}")
    
    return result_strict, result_warning, result_lenient


def example_integration_with_orchestrator():
    """Example of integration with import orchestrator"""
    
    def validate_before_execution(mapping_id: int, file_paths: List[str]) -> bool:
        """Validate before executing import"""
        
        # Initialize services
        mapping_adapter = MappingAdapter()
        validator = PreExecutionValidator(
            mapping_adapter=mapping_adapter,
            validation_mode=ValidationMode.STRICT
        )
        
        try:
            # Load mapping configuration
            mapping_config = mapping_adapter.load_mapping_config(mapping_id)
            
            # Perform validation
            result = validator.validate_mapping_execution(mapping_config, file_paths)
            
            # Log results
            logger.info(f"Validation completed for mapping {mapping_id}")
            logger.info(f"Result: {'PASSED' if result.is_valid else 'FAILED'}")
            logger.info(f"Issues: {len(result.all_issues)}")
            
            # Handle blocking issues
            if result.has_blocking_issues():
                logger.error("Blocking issues found:")
                for issue in result.errors:
                    logger.error(f"  - {issue}")
                return False
            
            # Log warnings
            if result.warnings:
                logger.warning("Warnings found:")
                for warning in result.warnings:
                    logger.warning(f"  - {warning}")
            
            # Log recommendations
            if result.execution_recommendations:
                logger.info("Execution recommendations:")
                for rec in result.execution_recommendations:
                    logger.info(f"  - {rec}")
            
            return result.is_valid
            
        except Exception as e:
            logger.error(f"Validation failed for mapping {mapping_id}: {e}")
            return False
    
    # Example usage
    mapping_id = 123
    file_paths = ["/uploads/data1.csv", "/uploads/data2.csv"]
    
    if validate_before_execution(mapping_id, file_paths):
        print("✅ Validation passed - safe to execute")
        # Proceed with execution
    else:
        print("❌ Validation failed - fix issues before execution")
        # Handle validation failure


if __name__ == "__main__":
    # Run examples
    print("=== Basic Validation Example ===")
    example_basic_validation()
    
    print("\n=== File Structure Validation Example ===")
    example_file_structure_validation()
    
    print("\n=== Column Mapping Validation Example ===")
    example_column_mapping_validation()
    
    print("\n=== Relationship Validation Example ===")
    example_relationship_validation()
    
    print("\n=== Resource Estimation Example ===")
    example_resource_estimation()
    
    print("\n=== Validation Modes Example ===")
    example_validation_modes()
    
    print("\n=== Integration Example ===")
    example_integration_with_orchestrator()