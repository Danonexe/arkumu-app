# Arkumu Importer Services Analysis

## Overview

The `arkumu/importer/services/` directory contains a sophisticated, multi-layered architecture for importing and processing data (primarily CSV files) based on complex mapping configurations. The architecture is modular with clear separation of concerns, designed for high performance and scalability.

## Architecture Layers

### 1. Orchestration Layer (`orchestrator/`)
The highest level layer responsible for managing the entire import workflow.

**Key Components:**
- `import_orchestrator.py`: Main entry point coordinating the import process
- `strategy_selector.py`: Intelligently selects processing strategy based on dataset characteristics
- `progress_tracker.py`: Real-time progress updates for long-running imports
- `result_aggregator.py`: Collects and aggregates results into comprehensive reports

### 2. Mapping Consumer Layer (`mapping_consumer/`)
Bridge between user-defined mapping configurations (GUI) and the execution engine.

**Key Components:**
- `mapping_adapter.py`: Loads mapping configurations from Django models
- `config_translator.py`: Translates JSON configurations into structured `ExecutionConfig`
- `dependency_resolver.py`: Analyzes foreign key relationships and builds dependency graphs
- `validation.py`: Pre-execution validation of mapping configurations

### 3. Execution Layer (`execution/`)
Core data processing engine that performs the actual import operations.

**Key Components:**
- `execution_engine.py`: High-performance orchestration of the import process
- `mapping_aware_processor.py`: Enhanced processor understanding full `ExecutionConfig`
- `chunked_processor.py`: Handles large CSV files through chunked processing
- `data_processor.py`: High-performance data cleaning and transformation using Polars
- `resource_manager.py`: Manages RDF resource and triple creation
- `update_analyzer.py`: Dry-run analysis of import impact

### 4. Importer Layer (`importer/`)
Lower-level, specialized services used by the execution engine. This appears to be an older implementation layer.

**Key Components:**
- `bulk_update_engine.py`: Determines and prepares resource updates
- `bulk_database_executor.py`: Handles bulk database operations
- `bulk_relationship_processor.py`: Processes foreign key relationships
- `bulk_data_analyzer.py`: Data analysis and preparation
- `bulk_uri_service.py`: Centralized URI generation
- `mapping_processor.py`: Older mapping processor (predecessor to mapping_aware_processor)

### 5. Validation Layer (`validation/`)
Validates mapping files against data sources before import execution.

**Key Components:**
- `validation.py`: Core validation service
- `validation_utils.py`: Utility classes for validation reporting

### 6. File Upload Layer (`file_upload/`)
Handles file uploads to external storage during import.

**Key Components:**
- `s3_upload_service.py`: AWS S3 upload implementation

## Identified Duplications and Redundancies

### 1. URI Generation Functions

**Major Duplication:** `execution/resource_manager.py` completely duplicates URI generation from `importer/bulk_uri_service.py`

| Function | Location 1 | Location 2 |
|----------|-----------|-----------|
| `generate_dataset_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |
| `generate_column_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |
| `generate_row_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |
| `generate_cell_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |
| `generate_entity_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |
| `generate_junction_uri` | `importer/bulk_uri_service.py` | `execution/resource_manager.py` |

**Additional Duplication:** `execution/mapping_aware_processor.py` contains ad-hoc URI generation:
- `_generate_entity_uri`
- `_generate_property_uri`
- `_generate_target_entity_uri`

### 2. Data Processing/Normalization

**Unicode Normalization Duplication:**
- `normalize_unicode_vectorized` exists in both:
  - `importer/bulk_data_analyzer.py`
  - `execution/data_processor.py`

**Multi-value String Splitting:**
- `split_multi_values` in `importer/data_utils.py`
- `split_cell_values` in `importer/bulk_data_analyzer.py`

### 3. Resource Creation

**Standard RDF Properties Creation:**
- `ensure_rdf_properties` in `importer/bulk_database_executor.py`
- `_init_standard_properties` in `execution/resource_manager.py`

Both create standard properties like `rdf:value`, `dcterms:hasPart`, etc.

### 4. Validation Functions

**Header/Column Validation:**
- `validate_source_headers` in `importer/data_utils.py`
- Similar functionality in `validate_mapping_against_data` in `validation/validation.py`

### 5. Execution Engine Overlap

**Major Architectural Overlap:**
- `importer/bulk_update_engine.py` vs `execution/execution_engine.py` + `execution/mapping_aware_processor.py`
- Both serve as execution engines, with the `execution/` layer appearing to be the newer, more comprehensive implementation

## Recommendations

### 1. Consolidate URI Generation
- Make `BulkURIService` the single source of truth for URI generation
- Remove duplicate implementations from `ResourceManager` and `MappingAwareProcessor`
- Consider moving `BulkURIService` to a more central location

### 2. Unify Data Processing
- Choose between `DataProcessor` (newer, Polars-based) and older implementations
- Remove duplicate `normalize_unicode_vectorized` function
- Consolidate multi-value splitting logic

### 3. Clarify Execution Architecture
- Determine if `importer/` layer is legacy code that should be deprecated
- If not, clearly define the responsibilities of each layer
- Consider refactoring `importer/` services into focused utilities used by `execution/` layer

### 4. Centralize Resource Creation
- Make `ResourceManager` the sole service for creating RDF resources and triples
- Remove resource creation logic from other services

### 5. Streamline Validation
- Consolidate validation logic in the `validation/` layer
- Remove duplicate validation functions from other modules

## Migration Path

1. **Phase 1**: Centralize URI generation by updating all services to use `BulkURIService`
2. **Phase 2**: Consolidate data processing functions into `DataProcessor`
3. **Phase 3**: Refactor resource creation to use only `ResourceManager`
4. **Phase 4**: Evaluate and potentially deprecate older `importer/` services
5. **Phase 5**: Document clear architectural boundaries and responsibilities

## Performance Considerations

The newer `execution/` layer shows significant performance improvements:
- Uses Polars for data processing (vectorized operations)
- Implements chunked processing for large files
- Provides streaming capabilities for memory efficiency

Maintaining both old and new implementations may impact maintainability without providing performance benefits.

## Impact Analysis: Removing the `importer/` Folder

### Files Affected Outside the `importer/` Directory

Based on the analysis, removing the `importer/` folder would affect the following files:

#### 1. **UpdateStrategy Enum** (from `bulk_update_engine`)
Most widely used component that would need replacement:
- `arkumu/importer/views/import_views.py`
- `arkumu/importer/tasks/import_metadata.py`
- `arkumu/metadata/views/csv_mapping/views/execution_views.py`
- `arkumu/importer/management/commands/import_csv_brute_force.py`
- `arkumu/importer/services/execution/execution_engine.py`
- `arkumu/importer/services/execution/update_analyzer.py`
- `arkumu/importer/services/execution/mapping_aware_processor.py`

#### 2. **ImportWorkflowService** (from `import_workflow`)
High-level orchestration service used by:
- `arkumu/importer/tasks/import_metadata.py`
- `arkumu/rest/views/import_viewsets.py`
- `arkumu/metadata/views/bulk_editor_views.py`
- `arkumu/importer/views/import_api.py`
- `arkumu/importer/management/commands/import_csv_directory.py`

#### 3. **URI Utilities** (from `uri_utils`)
Core URI functions used by:
- `arkumu/metadata/views/csv_mapping/views/execution_processors.py` (mint_uri, slugify_uri_part)
- `arkumu/importer/services/execution/resource_manager.py` (mint_uri, slugify_uri_part)
- `arkumu/metadata/services/mapping_executor.py` (mint_uri, slugify_uri_part)

#### 4. **Other Components**
- `arkumu/metadata/services/data_analysis/s3_direct_data_analyzer.py` - uses `BulkDataAnalyzer`
- `arkumu/importer/services/execution/resource_manager.py` - uses `MAX_INDEXED_VALUE_SIZE`
- `arkumu/importer/services/execution/mapping_aware_processor.py` - uses `FKRelationship`
- `arkumu/metadata/views/csv_mapping/views/execution_validators.py` - uses `GUIMappingProcessor`

### Refactoring Requirements Before Removal

1. **Move Core Enums and Constants**
   - Extract `UpdateStrategy` enum to a shared location (e.g., `arkumu/importer/constants.py`)
   - Move `MAX_INDEXED_VALUE_SIZE` constant to a shared module

2. **Replace ImportWorkflowService**
   - Update all consumers to use `ImportOrchestrator` from the `orchestrator/` layer
   - Ensure feature parity between old and new orchestration services

3. **Centralize URI Utilities**
   - Move `mint_uri` and `slugify_uri_part` to a central utilities module
   - Update all imports to use the new location

4. **Update Execution Layer Dependencies**
   - Remove dependency on `FKRelationship` from old module
   - Ensure execution layer has its own implementation or shared model

5. **Migrate GUI Mapping Processor**
   - Replace `GUIMappingProcessor` usage with `MappingAwareProcessor`
   - Update validation logic to use new processor

### Recommended Approach

Given the extensive usage of components from the `importer/` folder, complete removal should be done incrementally:

1. **Phase 1**: Extract shared components (enums, constants, utilities) to neutral locations
2. **Phase 2**: Create adapter/wrapper services to maintain backward compatibility
3. **Phase 3**: Gradually migrate each consumer to use new services
4. **Phase 4**: Remove deprecated services once all migrations are complete
5. **Phase 5**: Clean up and remove the `importer/` folder

This approach minimizes disruption while ensuring a smooth transition to the newer architecture.