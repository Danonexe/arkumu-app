"""
Basic integration test for the pre-execution validation service.

This module provides basic tests to verify the service integration works correctly.
"""

import os
import tempfile
import json
from typing import Dict, Any

from .pre_execution_validator import PreExecutionValidator
from .validation_result import ValidationMode, ValidationSeverity
from .integration_helpers import ValidationIntegrationHelper


def create_test_csv_file(headers: list, data: list) -> str:
    """Create a temporary CSV file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        # Write headers
        f.write(','.join(headers) + '\n')
        
        # Write data rows
        for row in data:
            f.write(','.join(str(cell) for cell in row) + '\n')
        
        return f.name


def create_test_mapping_config() -> Dict[str, Any]:
    """Create a test mapping configuration"""
    return {
        "institution": "test_university",
        "domain": "http://test.edu/",
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
                "source_column": "email",
                "property": "ex:email",
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


def test_basic_validation():
    """Test basic validation functionality"""
    print("=== Testing Basic Validation ===")
    
    # Create test file
    test_file = create_test_csv_file(
        headers=['student_id', 'name', 'email', 'course_id'],
        data=[
            ['1', 'Alice Smith', 'alice@example.com', 'CS101'],
            ['2', 'Bob Johnson', 'bob@example.com', 'CS102'],
            ['3', 'Carol Brown', 'carol@example.com', 'CS101']
        ]
    )
    
    try:
        # Create validator
        validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
        
        # Create mapping config
        mapping_config = create_test_mapping_config()
        
        # Validate
        result = validator.validate_mapping_execution(mapping_config, [test_file])
        
        # Check results
        print(f"✅ Validation completed")
        print(f"   - Valid: {result.is_valid}")
        print(f"   - Confidence: {result.overall_confidence:.2f}")
        print(f"   - Issues: {len(result.all_issues)}")
        print(f"   - Files validated: {len(result.file_validation_results)}")
        
        # Print issues if any
        if result.all_issues:
            print("   - Issues found:")
            for issue in result.all_issues:
                print(f"     * {issue.severity.value}: {issue.message}")
        
        # Print recommendations
        if result.execution_recommendations:
            print("   - Recommendations:")
            for rec in result.execution_recommendations:
                print(f"     * {rec}")
        
        return result.is_valid
        
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.unlink(test_file)


def test_file_structure_validation():
    """Test file structure validation"""
    print("\n=== Testing File Structure Validation ===")
    
    # Create test file with issues
    test_file = create_test_csv_file(
        headers=['student_id', 'name', 'name'],  # Duplicate header
        data=[
            ['1', 'Alice Smith', 'alice@example.com'],
            ['2', 'Bob Johnson'],  # Missing column
            ['3', 'Carol Brown', 'carol@example.com']
        ]
    )
    
    try:
        validator = PreExecutionValidator()
        dataset_config = {"required_columns": ["student_id", "name", "email"]}
        
        result = validator.validate_file_structure(test_file, dataset_config)
        
        print(f"✅ File structure validation completed")
        print(f"   - Valid: {result.is_valid}")
        print(f"   - File size: {result.file_size} bytes")
        print(f"   - Columns: {result.column_count}")
        print(f"   - Rows: {result.row_count}")
        print(f"   - Issues: {len(result.issues)}")
        
        # Print specific issues
        for issue in result.issues:
            print(f"     * {issue.severity.value}: {issue.message}")
        
        return result
        
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)


def test_column_mapping_validation():
    """Test column mapping validation"""
    print("\n=== Testing Column Mapping Validation ===")
    
    validator = PreExecutionValidator()
    
    # File columns
    file_columns = ['student_id', 'full_name', 'email_address', 'course_code', 'grade']
    
    # Mapping config
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
                "source_column": "missing_column",  # This will be missing
                "property": "ex:missing"
            }
        ]
    }
    
    result = validator.validate_column_mapping(file_columns, mapping_config)
    
    print(f"✅ Column mapping validation completed")
    print(f"   - Coverage: {result.coverage_percentage:.1f}%")
    print(f"   - Mapped columns: {len(result.mapped_columns)}")
    print(f"   - Unmapped columns: {result.unmapped_columns}")
    print(f"   - Missing required: {result.missing_required_columns}")
    print(f"   - Issues: {len(result.issues)}")
    
    for issue in result.issues:
        print(f"     * {issue.severity.value}: {issue.message}")
    
    return result


def test_relationship_validation():
    """Test relationship validation"""
    print("\n=== Testing Relationship Validation ===")
    
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
    
    result = validator.validate_relationship_requirements(mapping_config)
    
    print(f"✅ Relationship validation completed")
    print(f"   - Valid relationships: {len(result.valid_relationships)}")
    print(f"   - Invalid relationships: {len(result.invalid_relationships)}")
    print(f"   - Missing dependencies: {result.missing_dependencies}")
    print(f"   - Issues: {len(result.issues)}")
    
    for issue in result.issues:
        print(f"     * {issue.severity.value}: {issue.message}")
    
    return result


def test_resource_estimation():
    """Test resource estimation"""
    print("\n=== Testing Resource Estimation ===")
    
    validator = PreExecutionValidator()
    
    # Complex mapping
    mapping_config = create_test_mapping_config()
    
    # File sizes (in bytes)
    file_sizes = [
        1024 * 1024,  # 1MB
        5 * 1024 * 1024,  # 5MB
        10 * 1024 * 1024  # 10MB
    ]
    
    estimate = validator.estimate_resource_requirements(mapping_config, file_sizes)
    
    print(f"✅ Resource estimation completed")
    print(f"   - Execution time: {estimate.estimated_execution_time:.1f}s")
    print(f"   - Memory usage: {estimate.estimated_memory_usage}MB")
    print(f"   - Disk usage: {estimate.estimated_disk_usage}MB")
    print(f"   - CPU usage: {estimate.estimated_cpu_usage:.1f}%")
    print(f"   - Complexity score: {estimate.complexity_score}/10")
    print(f"   - Parallel processing: {estimate.parallel_processing_recommendation}")
    
    if estimate.chunking_recommendation:
        print(f"   - Chunking recommended: {estimate.chunking_recommendation}")
    
    return estimate


def test_validation_modes():
    """Test different validation modes"""
    print("\n=== Testing Validation Modes ===")
    
    # Create file with issues
    test_file = create_test_csv_file(
        headers=['student_id', 'name'],
        data=[['1', 'Alice'], ['2', 'Bob']]
    )
    
    # Problematic mapping (missing column)
    mapping_config = {
        "institution": "test_university",
        "domain": "http://test.edu/",
        "anchor_column": "missing_column",  # This will cause an error
        "mappings": [
            {
                "source_column": "student_id",
                "property": "ex:studentId"
            },
            {
                "source_column": "missing_column",  # This will cause an error
                "property": "ex:missing"
            }
        ]
    }
    
    try:
        modes = [
            (ValidationMode.STRICT, "STRICT"),
            (ValidationMode.WARNING_ONLY, "WARNING_ONLY"),
            (ValidationMode.LENIENT, "LENIENT")
        ]
        
        for mode, mode_name in modes:
            validator = PreExecutionValidator(validation_mode=mode)
            result = validator.validate_mapping_execution(mapping_config, [test_file])
            
            print(f"   {mode_name} Mode:")
            print(f"     - Valid: {result.is_valid}")
            print(f"     - Errors: {len(result.errors)}")
            print(f"     - Warnings: {len(result.warnings)}")
            print(f"     - Confidence: {result.overall_confidence:.2f}")
        
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)


def run_all_tests():
    """Run all integration tests"""
    print("🚀 Running Pre-Execution Validation Integration Tests")
    print("=" * 60)
    
    try:
        # Run individual tests
        test_basic_validation()
        test_file_structure_validation()
        test_column_mapping_validation()
        test_relationship_validation()
        test_resource_estimation()
        test_validation_modes()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()