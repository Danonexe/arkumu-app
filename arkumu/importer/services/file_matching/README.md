# File Matching Service

The File Matching Service provides comprehensive file-to-dataset matching functionality for the Arkumu import pipeline. It automatically matches files to dataset configurations based on naming conventions, validates file structures, and provides detailed compatibility analysis.

## Features

- **Automatic File-to-Dataset Matching**: Intelligently matches files to datasets using various naming conventions
- **Multiple Matching Strategies**: Supports exact match, fuzzy match, pattern match, and contains match
- **File Structure Validation**: Validates CSV, JSON, and TSV files against dataset requirements
- **Compatibility Analysis**: Analyzes file compatibility with dataset requirements
- **Batch Processing**: Handles multiple files efficiently with comprehensive results
- **Error Handling**: Integrated with the structured error handling system
- **S3 Integration**: Works with existing S3 upload services

## Core Components

### FileDatasetMatcher

The main service class that provides all matching functionality.

```python
from arkumu.importer.services.file_matching import FileDatasetMatcher
from arkumu.importer.services.error_handling.error_manager import ErrorManager

# Initialize with error manager
error_manager = ErrorManager()
matcher = FileDatasetMatcher(error_manager=error_manager)
```

### Key Methods

#### `match_files_to_datasets(selected_files, execution_config, base_directory=None)`

Matches a list of files to dataset configurations.

```python
# Load execution config
execution_config = mapping_adapter.translate_to_execution_config(mapping_id)

# Match files
selected_files = ['/path/to/users.csv', '/path/to/products.json']
result = matcher.match_files_to_datasets(selected_files, execution_config)

print(f"Match rate: {result.match_rate:.2%}")
print(f"Successful matches: {len(result.successful_matches)}")
print(f"Failed matches: {len(result.failed_matches)}")
```

#### `validate_file_structure(file_path, dataset_config, base_directory=None)`

Validates file structure against dataset expectations.

```python
dataset_config = execution_config.get_dataset_config("users")
is_valid, issues = matcher.validate_file_structure("/path/to/users.csv", dataset_config)

if not is_valid:
    print("Validation issues:")
    for issue in issues:
        print(f"- {issue}")
```

#### `get_dataset_from_filename(filename)`

Extracts dataset name from filename using various patterns.

```python
# Various naming patterns supported
assert matcher.get_dataset_from_filename("users.csv") == "users"
assert matcher.get_dataset_from_filename("user_data.csv") == "user"
assert matcher.get_dataset_from_filename("product-info.json") == "product"
assert matcher.get_dataset_from_filename("orders_2023.csv") == "orders"
```

#### `analyze_file_compatibility(file_path, dataset_requirements, base_directory=None)`

Analyzes file compatibility with dataset requirements.

```python
dataset_requirements = {
    'required_columns': ['id', 'name', 'email'],
    'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'},
    'size_range': (0, 1024 * 1024)  # 0-1MB
}

analysis = matcher.analyze_file_compatibility("/path/to/users.csv", dataset_requirements)
print(f"Compatible: {analysis['compatible']}")
print(f"Score: {analysis['compatibility_score']:.2f}")
```

## Data Structures

### FileInfo

Contains comprehensive information about a file:

```python
@dataclass
class FileInfo:
    file_path: str
    filename: str
    basename: str          # filename without extension
    extension: str
    size: int
    exists: bool
    is_readable: bool
    directory: str
    relative_path: str
```

### MatchResult

Result of matching a single file to datasets:

```python
@dataclass
class MatchResult:
    file_info: FileInfo
    dataset_name: Optional[str]
    confidence: float
    matching_strategy: MatchingStrategy
    reasons: List[str]
    validation_issues: List[str]
    is_valid: bool
    metadata: Dict[str, Any]
```

### BatchMatchResult

Result of matching multiple files:

```python
@dataclass
class BatchMatchResult:
    successful_matches: List[MatchResult]
    failed_matches: List[MatchResult]
    unmatched_files: List[FileInfo]
    unmatched_datasets: List[str]
    total_files: int
    total_datasets: int
    match_rate: float
```

## Matching Strategies

### 1. Exact Match (Priority: Highest)
- Direct case-insensitive comparison
- `users.csv` → `users` dataset
- Confidence: 1.0

### 2. Fuzzy Match
- Uses sequence similarity algorithm
- `user_data.csv` → `users` dataset
- Confidence: 0.0-1.0 based on similarity

### 3. Pattern Match
- Handles common naming patterns
- `users_export.csv` → `users` dataset
- `product-list.json` → `products` dataset
- Confidence: 0.8-0.9

### 4. Contains Match
- Substring matching
- `user_info.csv` → `users` dataset
- Confidence: 0.7

## Supported File Formats

### CSV Files (.csv)
- Automatic delimiter detection
- Header validation
- Column count verification
- Data consistency checks

### TSV Files (.tsv)
- Tab-separated values
- Same validation as CSV
- Column mapping support

### JSON Files (.json)
- Array of objects format
- Single object format
- Field presence validation
- Structure consistency checks

## Integration with Existing Services

### Error Handling Integration

```python
from arkumu.importer.services.error_handling.error_manager import ErrorManager

error_manager = ErrorManager()
matcher = FileDatasetMatcher(error_manager=error_manager)

# Errors are automatically recorded
result = matcher.match_files_to_datasets(files, config)
```

### S3 Upload Service Integration

```python
from arkumu.importer.services.file_matching.integration_helpers import FileMatchingIntegration

integration = FileMatchingIntegration(
    error_manager=error_manager,
    s3_upload_service=s3_service
)

# Get upload suggestions
suggestions = integration.suggest_file_uploads(local_files, mapping_id)
```

### Mapping Adapter Integration

```python
from arkumu.importer.services.file_matching.integration_helpers import match_files_quick

# Quick matching with mapping ID
result = match_files_quick(mapping_id, selected_files, base_directory)
print(f"Ready for import: {result['ready_for_import']}")
```

## Configuration

### Fuzzy Matching Threshold
```python
matcher.fuzzy_threshold = 0.6  # Default: 0.6 (60% similarity)
```

### Supported Extensions
```python
matcher.supported_extensions = {'.csv', '.tsv', '.txt', '.json', '.xml'}
```

### Naming Patterns
```python
matcher.naming_patterns = [
    r'^([^_.-]+).*',          # First part before delimiter
    r'^([^_-]+)_.*',          # Underscore separated
    r'^([^-_]+)-.*',          # Hyphen separated
    r'^(.+?)(?:_\d+)?(?:\.[^.]+)?$',  # Without trailing numbers
    r'^(.+?)(?:-\d+)?(?:\.[^.]+)?$',  # Without trailing numbers (hyphen)
]
```

## Usage Examples

### Basic File Matching

```python
from arkumu.importer.services.file_matching import FileDatasetMatcher
from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter

# Initialize services
mapping_adapter = MappingAdapter()
matcher = FileDatasetMatcher()

# Load mapping configuration
execution_config = mapping_adapter.translate_to_execution_config(mapping_id)

# Match files
files = ['/data/users.csv', '/data/products.json', '/data/orders.tsv']
result = matcher.match_files_to_datasets(files, execution_config)

# Process results
for match in result.successful_matches:
    print(f"File: {match.file_info.filename}")
    print(f"Dataset: {match.dataset_name}")
    print(f"Confidence: {match.confidence:.2f}")
    print(f"Strategy: {match.matching_strategy.value}")
    print(f"Valid: {match.is_valid}")
    print()
```

### File Validation

```python
# Validate specific file-dataset pairs
file_dataset_pairs = [
    ('/data/users.csv', 'users'),
    ('/data/products.json', 'products'),
    ('/data/orders.tsv', 'orders')
]

for file_path, dataset_name in file_dataset_pairs:
    dataset_config = execution_config.get_dataset_config(dataset_name)
    is_valid, issues = matcher.validate_file_structure(file_path, dataset_config)
    
    if not is_valid:
        print(f"Validation failed for {file_path}:")
        for issue in issues:
            print(f"  - {issue}")
```

### Compatibility Analysis

```python
# Analyze file compatibility
dataset_requirements = {
    'required_columns': ['id', 'name', 'email'],
    'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'},
    'size_range': (100, 1024 * 1024)  # 100 bytes to 1MB
}

analysis = matcher.analyze_file_compatibility('/data/users.csv', dataset_requirements)

print(f"Compatible: {analysis['compatible']}")
print(f"Score: {analysis['compatibility_score']:.2f}")
print(f"Issues: {analysis['issues']}")
print(f"Recommendations: {analysis['recommendations']}")
```

### Integration Helper Usage

```python
from arkumu.importer.services.file_matching.integration_helpers import FileMatchingIntegration

# Initialize integration
integration = FileMatchingIntegration(error_manager=error_manager)

# Complete file matching with recommendations
result = integration.match_files_for_mapping(mapping_id, selected_files)

print(f"Match rate: {result['matching_results']['match_rate']:.2%}")
print(f"Ready for import: {result['ready_for_import']}")
print("Recommendations:")
for rec in result['recommendations']:
    print(f"  - {rec}")
```

## Testing

### Running Tests

```bash
# Run all file matching tests
docker compose -f docker-compose.local.yml run --rm django pytest arkumu/importer/tests/services/file_matching/

# Run specific test file
docker compose -f docker-compose.local.yml run --rm django pytest arkumu/importer/tests/services/file_matching/test_file_dataset_matcher.py

# Run with coverage
docker compose -f docker-compose.local.yml run --rm django pytest arkumu/importer/tests/services/file_matching/ --cov=arkumu.importer.services.file_matching
```

### Test Coverage

The test suite covers:
- All matching strategies
- File validation for different formats
- Error handling scenarios
- Integration with existing services
- Edge cases and error conditions
- Performance with large files

## Performance Considerations

### File Size Limits
- Default maximum file size: 100MB
- Configurable through validation logic
- Large files trigger warnings and recommendations

### Batch Processing
- Efficient processing of multiple files
- Parallel validation where possible
- Memory-conscious file reading

### Caching
- Pattern compilation cached
- Dataset candidates cached per execution config
- File metadata cached during batch processing

## Error Handling

### Structured Error Recording
All errors are recorded through the ErrorManager:

```python
self.error_manager.record_error(
    error_code="FILE_MATCHING_ERROR",
    error_type="MatchingError",
    error_message="Failed to match file to dataset",
    error_category="file_processing",
    context={"file_path": file_path, "dataset": dataset_name}
)
```

### Common Error Types
- `FILE_INFO_CREATION_ERROR`: File access issues
- `FILE_VALIDATION_ERROR`: Validation failures
- `FILE_MATCHING_ERROR`: Matching algorithm errors
- `FILE_COMPATIBILITY_ANALYSIS_ERROR`: Compatibility analysis errors

## Best Practices

### File Naming Conventions
- Use dataset names as prefixes: `users.csv`, `products.json`
- Avoid special characters in filenames
- Use consistent separators (underscore or hyphen)
- Include version numbers at the end: `users_v2.csv`

### Dataset Configuration
- Ensure dataset names are descriptive and unique
- Use consistent naming across mappings
- Define clear column requirements
- Specify data types when possible

### Performance Optimization
- Process files in appropriate batch sizes
- Use base directories for relative path resolution
- Validate files before attempting matching
- Cache execution configurations for repeated use

## Troubleshooting

### Low Match Rates
- Check file naming conventions
- Verify dataset names in mapping configuration
- Adjust fuzzy matching threshold
- Review naming patterns

### Validation Failures
- Check file format and structure
- Verify required columns are present
- Ensure data types match expectations
- Check file permissions and accessibility

### Integration Issues
- Verify error manager is properly initialized
- Check S3 service configuration
- Ensure mapping adapter is working correctly
- Review log files for detailed error information