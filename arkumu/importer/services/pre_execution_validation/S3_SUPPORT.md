# S3 Support in Pre-Execution Validator

## Overview

The Pre-Execution Validator now supports both local files and S3 files, allowing it to validate files stored in S3 buckets without requiring them to be downloaded to the local filesystem.

## Key Features

### 1. Automatic Path Detection

The validator automatically detects whether a file path refers to a local file or an S3 object:

```python
# S3 paths (detected automatically)
"metadata/AkteurIn.csv"        # ✅ S3 path
"folder/subfolder/file.csv"    # ✅ S3 path
"AkteurIn.csv"                 # ✅ S3 path

# Local paths (detected automatically)
"/home/user/file.csv"          # ❌ Local absolute path
"./file.csv"                   # ❌ Local relative path
"../data/file.csv"             # ❌ Local relative path
"~/file.csv"                   # ❌ Home directory path
```

### 2. S3 File Operations

The validator can perform the following operations on S3 files:

- **File existence checks**: Verify if files exist in S3 buckets
- **File size retrieval**: Get file sizes from S3 metadata
- **Content reading**: Download and parse file content from S3
- **Column extraction**: Extract column headers from S3 files

### 3. Supported File Formats

Both local and S3 files support the same formats:

- **CSV files** (`.csv`, `.tsv`, `.txt`): Full parsing with delimiter detection
- **JSON files** (`.json`): Object and array parsing

## Usage

### Basic Usage

```python
from arkumu.importer.services.pre_execution_validation.pre_execution_validator import PreExecutionValidator

# Initialize validator
validator = PreExecutionValidator()

# Validate S3 files
validation_result = validator.validate_mapping_execution(
    mapping_config=mapping_config,
    file_paths=["metadata/AkteurIn.csv", "metadata/Werk.csv"],
    organization_code="rsh"  # Required for S3 operations
)
```

### Mixed Local and S3 Files

```python
# The validator handles both local and S3 files automatically
file_paths = [
    "metadata/AkteurIn.csv",     # S3 file
    "/tmp/local_file.csv",       # Local file
    "metadata/Werk.csv"          # S3 file
]

validation_result = validator.validate_mapping_execution(
    mapping_config=mapping_config,
    file_paths=file_paths,
    organization_code="rsh"
)
```

## Implementation Details

### S3 Path Detection

The validator uses the following logic to detect S3 paths:

```python
def _is_s3_path(self, file_path: str) -> bool:
    """Check if a file path is an S3 path (not a local file path)"""
    return (not os.path.isabs(file_path) and 
            ':' not in file_path and 
            not file_path.startswith('.') and
            not file_path.startswith('~'))
```

### S3 File Access

S3 files are accessed using the `BucketService`:

```python
def _validate_csv_file_structure_s3(self, file_path, dataset_config, result, organization_code):
    """Validate CSV file structure from S3"""
    # Get organization bucket
    bucket_name = self.bucket_service.get_organization_bucket(organization_code)
    
    # Download file content
    file_content_response = self.bucket_service.get_file_content(bucket_name, file_path)
    
    # Parse content
    content_bytes = file_content_response.get('content', b'')
    content_str = content_bytes.decode(encoding)
    
    # Validate using standard CSV parsing
    # ...
```

### Error Handling

The validator provides specific error messages for S3-related issues:

- **File not found**: "File not found in S3: {file_path}"
- **Read errors**: "Cannot read file from S3: {file_path}"
- **Missing organization**: "Organization code required for S3 file validation"

## Configuration Requirements

### Organization Code

S3 file validation requires an organization code to determine the correct bucket:

```python
# Required for S3 operations
validation_result = validator.validate_mapping_execution(
    mapping_config=mapping_config,
    file_paths=s3_file_paths,
    organization_code="rsh"  # ← Required for S3
)
```

### Bucket Service

The validator uses the `BucketService` for S3 operations:

```python
# Custom bucket service (optional)
validator = PreExecutionValidator(bucket_service=custom_bucket_service)

# Default bucket service (automatic)
validator = PreExecutionValidator()  # Uses default BucketService
```

## Testing

The S3 support includes comprehensive tests:

```bash
# Run S3 support tests
pytest arkumu/importer/services/pre_execution_validation/test_s3_support.py -v
```

Test coverage includes:
- S3 path detection
- File existence checks
- Content reading and parsing
- Error handling
- Mixed local/S3 file scenarios

## Benefits

1. **No temporary files**: Files are processed directly from S3 without local downloads
2. **Efficient**: Only downloads necessary content (headers, sample data)
3. **Scalable**: Works with large files by streaming content
4. **Robust**: Handles encoding detection and delimiter detection from S3 content
5. **Backward compatible**: Existing local file validation continues to work

## Migration Guide

### Before (Local Files Only)

```python
# Old approach - only worked with local files
validator = PreExecutionValidator()
result = validator.validate_mapping_execution(
    mapping_config=config,
    file_paths=["/tmp/downloaded_file.csv"]
)
```

### After (S3 and Local Files)

```python
# New approach - works with both S3 and local files
validator = PreExecutionValidator()
result = validator.validate_mapping_execution(
    mapping_config=config,
    file_paths=["metadata/AkteurIn.csv"],  # S3 path
    organization_code="rsh"  # Required for S3
)
```

## Troubleshooting

### Common Issues

1. **Missing organization code**: Ensure `organization_code` is provided for S3 files
2. **Path format**: S3 paths should not start with `/`, `.`, or `~`
3. **Bucket permissions**: Ensure the application has read access to S3 buckets
4. **File encoding**: The validator handles encoding detection automatically

### Debug Information

Enable debug logging to see S3 operations:

```python
import logging
logging.getLogger('arkumu.importer.services.pre_execution_validation').setLevel(logging.DEBUG)
```

This will show:
- S3 path detection decisions
- File existence checks
- Content download operations
- Parsing steps