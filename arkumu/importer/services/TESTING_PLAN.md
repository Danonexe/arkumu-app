# Arkumu Importer Services - Comprehensive Testing Plan

## Overview

This document outlines a comprehensive testing strategy for the `arkumu/importer/services/` architecture. The plan covers all five service layers with detailed test scenarios, mock requirements, and organization structure.

## Test Organization Structure

Tests are organized to mirror the services architecture:

```
arkumu/importer/tests/
├── services/
│   ├── __init__.py
│   ├── conftest.py
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── test_import_orchestrator.py
│   │   ├── test_progress_tracker.py
│   │   ├── test_result_aggregator.py
│   │   └── test_strategy_selector.py
│   ├── mapping_consumer/
│   │   ├── __init__.py
│   │   ├── test_mapping_adapter.py
│   │   ├── test_config_translator.py
│   │   ├── test_dependency_resolver.py
│   │   └── test_validation.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── test_execution_engine.py
│   │   ├── test_mapping_aware_processor.py
│   │   ├── test_chunked_processor.py
│   │   ├── test_data_processor.py
│   │   ├── test_resource_manager.py
│   │   └── test_update_analyzer.py
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── test_validation.py
│   │   └── test_validation_utils.py
│   └── file_upload/
│       ├── __init__.py
│       └── test_s3_upload_service.py
└── fixtures/
    ├── mappings/
    │   ├── simple_mapping.json
    │   ├── complex_mapping_with_deps.json
    │   ├── invalid_mapping.json
    │   └── circular_deps_mapping.json
    └── data/
        ├── simple_data_1.csv
        ├── simple_data_2.csv
        └── large_test_data.csv
```

## Testing Strategy by Layer

### 1. File Upload Layer (`file_upload/`)

#### Core Functionality
- Uploading single files to S3
- Batch uploading from directories
- File path resolution

#### Key Test Scenarios
- **Success scenarios**: Valid file upload, directory upload
- **Error scenarios**: File not found, invalid credentials, network errors
- **Edge cases**: Empty directories, permission issues

#### Mock Requirements
- `boto3.client('s3')` using `moto` library
- File system operations (`os.path.exists`, `os.path.isdir`)

### 2. Validation Layer (`validation/`)

#### Core Functionality
- Mapping structure validation
- Data column validation against mappings
- Reference validation for foreign keys

#### Key Test Scenarios
- **Structure validation**: Valid/invalid JSON, missing required fields
- **Data validation**: Column presence/absence in CSV data
- **Reference validation**: Existing/non-existing FK target tables

#### Mock Requirements
- `polars.read_csv` for data loading
- Django ORM (`Resource.objects.filter`) for reference checking

### 3. Mapping Consumer Layer (`mapping_consumer/`)

#### Core Functionality
- Loading mapping configurations from Django models
- Translating JSON configs to ExecutionConfig objects
- Dependency resolution for processing order
- Pre-execution validation

#### Key Test Scenarios
- **Translation**: Simple and complex mapping translation
- **Dependency resolution**: Linear dependencies, circular dependency detection
- **Validation**: Valid/invalid mapping configurations
- **Error handling**: Missing mappings, malformed JSON

#### Mock Requirements
- `arkumu.metadata.models.Mapping` model and manager
- Mock ExecutionConfig objects

### 4. Execution Layer (`execution/`)

#### Core Functionality
- High-performance data processing using Polars
- Resource and triple creation
- Chunked processing for large files
- URI generation and management

#### Key Test Scenarios
- **Data processing**: Cleaning, transformation, type conversion
- **Resource management**: URI generation, bulk creation
- **Chunked processing**: Large file handling, memory management
- **Update analysis**: New vs existing data comparison

#### Mock Requirements
- Django ORM bulk operations
- Polars DataFrame operations
- File system for chunked processing

### 5. Orchestration Layer (`orchestrator/`)

#### Core Functionality
- Main import workflow coordination
- Processing strategy selection
- Progress tracking and reporting
- Result aggregation

#### Key Test Scenarios
- **Strategy selection**: Entity-centric, streaming, multi-phase strategies
- **Coordination**: Service integration, error propagation
- **Progress tracking**: Real-time updates, completion reporting
- **Result aggregation**: Multi-dataset result compilation

#### Mock Requirements
- All lower-layer services (mapping_consumer, execution)
- Progress callback functions
- Result objects

## Test Data Requirements

### Fixture Files

#### Mapping Configurations
- `simple_mapping.json`: Basic single-dataset mapping
- `complex_mapping_with_deps.json`: Multi-dataset with FK relationships
- `invalid_mapping.json`: Structurally invalid mapping
- `circular_deps_mapping.json`: Mapping with circular dependencies

#### CSV Data Files
- `simple_data_1.csv`: Small dataset for basic testing
- `simple_data_2.csv`: Related dataset for FK testing
- `large_test_data.csv`: Large dataset for chunked processing

### Mock Data Structures
- ExecutionConfig objects for various scenarios
- Resource and Triple objects for database mocking
- Progress tracking data structures

## Testing Guidelines

### General Principles
1. **Isolation**: Each test should be independent and not rely on external state
2. **Database**: Use `@pytest.mark.django_db` for database access, never mock Django ORM
3. **Docker**: Always run tests with `docker compose -f docker-compose.local.yml run --rm django pytest`
4. **Performance**: Test with realistic data volumes for performance validation

### Mock Strategy
- **External Services**: Mock AWS S3, file system operations
- **Database**: Use real database with `@pytest.mark.django_db`
- **Layer Isolation**: Mock dependencies between service layers for unit tests
- **Integration Tests**: Use real implementations for integration scenarios

### Test Coverage Goals
- **Unit Tests**: 90%+ coverage for individual methods and classes
- **Integration Tests**: End-to-end workflow testing
- **Performance Tests**: Large dataset processing validation
- **Error Handling**: Comprehensive error scenario coverage

## Implementation Phases

### Phase 1: Foundation
1. Set up test structure and conftest.py
2. Create fixture files and mock utilities
3. Implement basic unit tests for each layer

### Phase 2: Core Functionality
1. Comprehensive unit tests for all modules
2. Basic integration tests between layers
3. Error handling and edge case testing

### Phase 3: Advanced Scenarios
1. Performance testing with large datasets
2. Complex dependency resolution testing
3. End-to-end workflow validation

### Phase 4: Maintenance
1. Test maintenance and refactoring
2. Coverage analysis and improvement
3. Performance regression testing

## Success Criteria

- **Coverage**: >90% line coverage across all modules
- **Performance**: Tests complete within reasonable time limits
- **Reliability**: All tests pass consistently in Docker environment
- **Maintainability**: Tests are easy to understand and modify
- **Isolation**: Tests can run independently without side effects