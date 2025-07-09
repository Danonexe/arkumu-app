# Pre-Execution Validation Service

This service provides comprehensive validation of mapping configurations and files before execution to ensure successful import operations. It supports both local files (for development/testing) and S3 files (for production).

## Overview

The Pre-Execution Validation Service validates:
- **File Structure**: Validates file format, encoding, headers, and basic structure
- **Column Mapping**: Ensures all required columns are present and properly mapped
- **Relationship Requirements**: Validates foreign key relationships and dependencies
- **Resource Estimation**: Estimates execution time, memory usage, and system resources
- **Storage Compatibility**: Works with both local and S3 file storage

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

### S3 File Validation

The validator seamlessly handles files stored in S3:

```python
from arkumu.storage.services.bucket_service import BucketService

# Initialize with bucket service
bucket_service = BucketService()
validator = PreExecutionValidator(bucket_service=bucket_service)

# S3 file paths (as they appear in the GUI)
s3_file_paths = [
    "metadata/AkteurIn.csv",
    "metadata/Ereignis.csv",
    "metadata/Projekt.csv"
]

# Get organization bucket
organization_code = "fuk"
bucket_name = bucket_service.get_organization_bucket(organization_code)

# Validate files from S3
result = validator.validate_mapping_execution(
    mapping_config=mapping_config,
    file_paths=s3_file_paths,
    bucket_name=bucket_name  # Optional: specify bucket for S3 files
)
```

### GUI Integration Example

This example shows how the validator is used in the actual ingest workflow:

```python
# From ingest_views.py
def run_pre_execution_validation(request):
    # Get selected files from session (S3 paths)
    selected_files = request.session.get('ingest_selected_files', [])
    
    # Get current mapping
    current_mapping = get_current_mapping(request)
    mapping_id = current_mapping['id']
    
    # Initialize services
    mapping_adapter = MappingAdapter()
    validator = PreExecutionValidator(mapping_adapter=mapping_adapter)
    bucket_service = BucketService()
    
    # Load mapping configuration
    mapping_config = mapping_adapter.load_mapping_config(mapping_id)
    
    # Get organization bucket
    bucket_name = bucket_service.get_organization_bucket(organization_code)
    
    # Run validation with S3 files
    validation_result = validator.validate_mapping_execution(
        mapping_config=mapping_config,
        file_paths=selected_files,
        bucket_name=bucket_name
    )
    
    return JsonResponse({
        'success': True,
        'validation_results': validation_result.to_dict(),
        'files_validated': len(selected_files)
    })
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
- S3 file handling tests with mocked AWS services

### Running Tests

Run all validation tests:
```bash
docker compose -f docker-compose.local.yml run --rm django pytest arkumu/importer/tests/services/pre_execution_validation/
```

### Testing with S3 Files

The test suite uses `moto` to mock AWS S3 services:

```python
import pytest
from moto import mock_aws
import boto3
from django.test import override_settings

@pytest.fixture
def s3_bucket():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3

@override_settings(
    DEFAULT_FILE_STORAGE='storages.backends.s3boto3.S3Boto3Storage',
    AWS_STORAGE_BUCKET_NAME='test-bucket'
)
def test_validate_s3_file(s3_bucket):
    # Upload test file to mocked S3
    s3_bucket.put_object(
        Bucket="test-bucket",
        Key="metadata/test.csv",
        Body="col1,col2\nval1,val2"
    )
    
    # Run validation
    validator = PreExecutionValidator()
    result = validator.validate_file_from_s3(
        bucket_name="test-bucket",
        file_key="metadata/test.csv"
    )
    assert result.is_valid
```

### GUI Simulation Tests

Test the complete user workflow:

```python
def test_user_validation_workflow():
    """Simulates user selecting files and running validation"""
    # 1. User selects organization
    # 2. System lists files from S3
    # 3. User selects multiple files
    # 4. User chooses mapping
    # 5. User clicks validate
    # 6. Validation runs against S3 files
    # 7. Results are displayed
```

## Troubleshooting

### Common Issues

#### FILE_NOT_FOUND errors with S3 files

**Problem**: Validation fails with "File not found" errors even though files exist in S3.

**Solution**: Ensure the validator is initialized with proper S3 support:
```python
# Wrong - tries to access files locally
validator = PreExecutionValidator()
result = validator.validate_mapping_execution(mapping_config, ["metadata/file.csv"])

# Correct - uses S3 storage backend
validator = PreExecutionValidator(bucket_service=BucketService())
result = validator.validate_mapping_execution(
    mapping_config, 
    ["metadata/file.csv"],
    bucket_name="organization-bucket"
)
```

#### Validation passes locally but fails in production

**Problem**: Tests pass but validation fails when deployed.

**Solution**: Check Django storage settings:
```python
# settings/production.py
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": os.environ.get("AWS_STORAGE_BUCKET_NAME"),
            "region_name": os.environ.get("AWS_S3_REGION_NAME"),
        }
    }
}
```

#### Slow validation performance with S3

**Problem**: Validation takes too long when reading from S3.

**Solution**: 
1. Use batch operations when validating multiple files
2. Enable S3 transfer acceleration if available
3. Consider caching file metadata locally
4. Use the resource estimation feature to set user expectations

## Future Enhancements

1. **Real-time validation** - Stream validation for large files
2. **Detailed type checking** - Enhanced column type validation
3. **Custom validation rules** - User-defined validation rules
4. **Performance optimization** - Parallel validation processing
5. **Integration with ML models** - Predictive validation based on historical data