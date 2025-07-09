# Pre-Execution Validation Service

This service provides comprehensive validation of mapping configurations and files before execution to ensure successful import operations.

## Overview

The Pre-Execution Validation Service validates:
- **File Structure**: Validates file format, encoding, headers, and basic structure
- **Column Mapping**: Ensures all required columns are present and properly mapped
- **Relationship Requirements**: Validates foreign key relationships and dependencies
- **Resource Estimation**: Estimates execution time, memory usage, and system resources

## Key Features

### 1. Comprehensive Validation
- File existence and readability checks
- CSV/JSON structure validation
- Column mapping verification
- Relationship dependency validation
- Resource requirement estimation

### 2. Multiple Validation Modes
- **STRICT**: Fail on any error (default)
- **WARNING_ONLY**: Convert errors to warnings
- **LENIENT**: Allow minor issues

### 3. Detailed Reporting
- Structured validation results
- Issue categorization by severity
- Execution recommendations
- Resource estimates

### 4. Integration Support
- Works with existing MappingAdapter
- Integrates with FileDatasetMatcher
- Compatible with import orchestrator

## Usage

### Basic Usage

```python
from arkumu.importer.services.pre_execution_validation import PreExecutionValidator, ValidationMode

# Initialize validator
validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)

# Mapping configuration
mapping_config = {
    "institution": "example_university",
    "domain": "http://example.edu/",
    "anchor_column": "student_id",
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
        }
    ]
}

# File paths to validate
file_paths = ["/path/to/students.csv", "/path/to/courses.csv"]

# Perform validation
result = validator.validate_mapping_execution(mapping_config, file_paths)

# Check results
if result.is_valid:
    print("✅ Validation passed - safe to execute")
else:
    print("❌ Validation failed:")
    for error in result.errors:
        print(f"  - {error}")
```

### Individual Validation Methods

```python
# Validate file structure
file_result = validator.validate_file_structure("/path/to/data.csv", dataset_config)

# Validate column mapping
column_result = validator.validate_column_mapping(file_columns, mapping_config)

# Validate relationships
relation_result = validator.validate_relationship_requirements(mapping_config)

# Estimate resources
resource_estimate = validator.estimate_resource_requirements(mapping_config, file_sizes)
```

### Integration with Mapping Adapter

```python
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter

# Initialize with mapping adapter
mapping_adapter = MappingAdapter()
validator = PreExecutionValidator(mapping_adapter=mapping_adapter)

# Load mapping from database
mapping_config = mapping_adapter.load_mapping_config(mapping_id)

# Validate
result = validator.validate_mapping_execution(mapping_config, file_paths)
```

## Validation Results

### PreExecutionValidationResult

The main result object containing:
- `is_valid`: Overall validation status
- `overall_confidence`: Confidence score (0.0-1.0)
- `file_validation_results`: Individual file validation results
- `column_mapping_result`: Column mapping validation
- `relationship_validation_result`: Relationship validation
- `resource_estimate`: Resource estimation
- `all_issues`: List of all validation issues
- `execution_recommendations`: Recommendations for execution
- `required_actions`: Actions required before execution

### Validation Issues

Each issue contains:
- `code`: Standard error code
- `severity`: CRITICAL, ERROR, WARNING, or INFO
- `category`: Issue category (file_structure, column_mapping, etc.)
- `message`: Human-readable description
- `file_path`: Associated file (if applicable)
- `column_name`: Associated column (if applicable)
- `suggested_fix`: Recommended fix (if available)

## Error Codes

### File Structure Errors
- `FILE_NOT_FOUND`: File does not exist
- `FILE_NOT_READABLE`: File cannot be read
- `FILE_EMPTY`: File has no content
- `FILE_TOO_LARGE`: File exceeds size limits
- `INVALID_FILE_FORMAT`: Unsupported file format
- `ENCODING_ERROR`: Character encoding issues
- `MALFORMED_CSV`: CSV parsing errors
- `HEADER_MISSING`: Required headers missing
- `DUPLICATE_HEADERS`: Duplicate column headers

### Column Mapping Errors
- `REQUIRED_COLUMN_MISSING`: Required column not found
- `COLUMN_TYPE_MISMATCH`: Column data type mismatch
- `UNMAPPED_REQUIRED_COLUMN`: Required column not mapped
- `TRANSFORMATION_ERROR`: Column transformation issues

### Relationship Errors
- `MISSING_FOREIGN_KEY`: Foreign key reference missing
- `INVALID_RELATIONSHIP`: Invalid relationship definition
- `CIRCULAR_DEPENDENCY`: Circular dependency detected
- `REFERENCE_TABLE_MISSING`: Referenced table not found

### Resource Warnings
- `HIGH_MEMORY_USAGE`: High memory usage expected
- `LONG_EXECUTION_TIME`: Long execution time expected
- `DISK_SPACE_WARNING`: Disk space concerns
- `PERFORMANCE_DEGRADATION`: Performance issues expected

## Configuration

### Validation Modes

```python
# Strict mode - fail on any error
validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)

# Warning mode - convert errors to warnings
validator = PreExecutionValidator(validation_mode=ValidationMode.WARNING_ONLY)

# Lenient mode - allow minor issues
validator = PreExecutionValidator(validation_mode=ValidationMode.LENIENT)
```

### Performance Thresholds

The validator uses configurable thresholds for:
- Maximum file size (default: 500MB)
- Maximum row count (default: 1M rows)
- Execution time warnings (default: 5 minutes)
- Memory usage warnings (default: 1GB)

## Integration Points

### With Import Orchestrator

```python
def validate_before_execution(mapping_id: int, file_paths: List[str]) -> bool:
    validator = PreExecutionValidator(validation_mode=ValidationMode.STRICT)
    mapping_config = mapping_adapter.load_mapping_config(mapping_id)
    result = validator.validate_mapping_execution(mapping_config, file_paths)
    
    if result.has_blocking_issues():
        logger.error("Blocking issues found - cannot execute")
        return False
    
    return result.is_valid
```

### With File Dataset Matcher

```python
# Validate files against dataset expectations
file_matcher = FileDatasetMatcher()
validator = PreExecutionValidator(file_matcher=file_matcher)

# The validator will use the file matcher for enhanced file validation
```

## Best Practices

1. **Always validate before execution** - Use pre-execution validation as a required step
2. **Handle validation results appropriately** - Don't ignore warnings and recommendations
3. **Use appropriate validation mode** - Choose based on your tolerance for issues
4. **Monitor resource estimates** - Plan execution based on resource requirements
5. **Fix blocking issues** - Address all critical and error-level issues before execution

## Testing

The service includes comprehensive test coverage:
- Unit tests for individual validation methods
- Integration tests with existing services
- Performance tests for large files
- Error condition tests

Run tests with:
```bash
docker compose -f docker-compose.local.yml run --rm django pytest arkumu/importer/tests/services/pre_execution_validation/
```

## Future Enhancements

1. **Real-time validation** - Stream validation for large files
2. **Detailed type checking** - Enhanced column type validation
3. **Custom validation rules** - User-defined validation rules
4. **Performance optimization** - Parallel validation processing
5. **Integration with ML models** - Predictive validation based on historical data