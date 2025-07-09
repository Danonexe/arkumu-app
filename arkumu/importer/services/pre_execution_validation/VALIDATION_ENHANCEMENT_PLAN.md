# Pre-Execution Validation Enhancement Plan

## Overview

This document outlines the comprehensive plan to enhance the pre-execution validation service to properly handle S3 file paths and create robust tests that simulate real user interactions.

## Current Issues

1. **File Access Problem**: The validator tries to access files locally when they're actually stored in S3
2. **Storage Abstraction**: The service doesn't use Django's storage abstraction layer
3. **Test Coverage**: Tests don't simulate real GUI user interactions or S3 file handling

## Implementation Plan

### Phase 1: Core Service Refactoring

#### 1.1 Update File Access to Use Django Storage

**Current Approach (Problematic):**
```python
# Direct filesystem access - fails for S3
if not os.path.exists(file_path):
    raise FileNotFoundError(f"File not found at {file_path}")

with open(file_path, 'r') as f:
    df = pd.read_csv(f)
```

**New Approach (Storage-Agnostic):**
```python
from django.core.files.storage import default_storage

try:
    with default_storage.open(file_path, 'r') as f:
        df = pd.read_csv(f)
except FileNotFoundError:
    raise FileNotFoundError(f"File not found in storage at {file_path}")
```

#### 1.2 Key Files to Update

1. `pre_execution_validator.py`: Replace all direct file operations with storage API
2. `validation_result.py`: Ensure file paths are handled correctly
3. `integration_helpers.py`: Update any file access utilities

### Phase 2: Enhanced Testing Strategy

#### 2.1 Unit Tests with Mocked S3

Create `test_s3_validation.py`:
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
    result = validator.validate_file("metadata/test.csv")
    assert result.is_valid
```

#### 2.2 Integration Tests Simulating GUI Flow

Create `test_gui_simulation.py`:
```python
@pytest.mark.django_db
def test_full_validation_flow():
    """Simulates complete user workflow from GUI"""
    # 1. User selects organization
    # 2. Files are listed from S3
    # 3. User selects files
    # 4. User chooses mapping
    # 5. User clicks validate
    # 6. Validation runs against S3 files
    # 7. Results are displayed
```

### Phase 3: Integration Points

#### 3.1 View Integration (`ingest_views.py`)

Update the validation endpoint to:
1. Properly handle S3 file paths
2. Use BucketService for file operations
3. Return meaningful error messages

#### 3.2 Frontend Integration

Ensure the frontend:
1. Passes correct S3 file paths
2. Handles validation results properly
3. Shows appropriate error messages

### Phase 4: Immediate Fix

For the immediate issue, we need to update the validator to handle S3 paths:

```python
class PreExecutionValidator:
    def __init__(self, bucket_service=None):
        self.bucket_service = bucket_service or BucketService()
    
    def validate_file_from_s3(self, bucket_name, file_key):
        """Validate a file directly from S3"""
        try:
            # Download file content from S3
            file_content = self.bucket_service.get_file_content(
                bucket_name=bucket_name,
                file_key=file_key
            )
            
            # Process the content
            df = pd.read_csv(io.StringIO(file_content))
            return self._validate_dataframe(df)
            
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Failed to read file from S3: {str(e)}"]
            )
```

## Testing Requirements

### GUI Simulation Tests

1. **File Selection Flow**:
   - Test selecting files from S3 bucket listing
   - Test multiple file selection
   - Test deselection

2. **Mapping Selection Flow**:
   - Test loading available mappings
   - Test selecting a mapping
   - Test changing mappings

3. **Validation Execution Flow**:
   - Test validation with valid files
   - Test validation with missing files
   - Test validation with incompatible files
   - Test validation progress indication

4. **Error Handling**:
   - Test S3 connection errors
   - Test file access errors
   - Test mapping loading errors

## Implementation Timeline

1. **Immediate (Today)**: Fix S3 file access issue
2. **Short-term (This Week)**: Implement storage abstraction
3. **Medium-term (Next Week)**: Create comprehensive test suite
4. **Long-term (This Month)**: Full GUI integration tests

## Success Criteria

1. Validation works with both local and S3 files
2. All tests pass in both environments
3. No hardcoded file paths
4. Clear error messages for users
5. Comprehensive test coverage (>90%)

## Dependencies

- `django-storages`: For S3 storage backend
- `boto3`: For AWS S3 operations
- `moto`: For mocking AWS services in tests
- `pytest-django`: For Django testing utilities

## Configuration

### Settings Structure
```python
# settings/base.py
STORAGES = {
    "default": {
        "BACKEND": env("DEFAULT_FILE_STORAGE", 
                      default="django.core.files.storage.FileSystemStorage")
    }
}

# settings/production.py
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "region_name": env("AWS_S3_REGION_NAME"),
        }
    }
}
```

## Notes

- Always use Django's storage API for file operations
- Never assume files are on local filesystem
- Test with both local and S3 storage backends
- Use dependency injection for storage services
- Maintain backward compatibility