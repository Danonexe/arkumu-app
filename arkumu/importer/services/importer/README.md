# Arkumu Importer Services Directory

This directory contains the modular importer services that were refactored from the original monolithic `smart_bulk_updater_polars.py` file.

## File Usage Analysis

### Core Modular Architecture (NEW - Active Use)

These files represent the new modular architecture that replaced the monolithic importer:

- **`bulk_data_analyzer.py`** - ✅ **ACTIVE** - Data analysis and multi-value detection
- **`bulk_uri_service.py`** - ✅ **ACTIVE** - URI generation and parsing services  
- **`bulk_update_engine.py`** - ✅ **ACTIVE** - Update strategy logic and action determination
- **`bulk_database_executor.py`** - ✅ **ACTIVE** - Database operations and bulk processing
- **`bulk_relationship_processor.py`** - ✅ **ACTIVE** - Foreign key relationships and cross-dataset linking

### Orchestration Layer (Active Use)

- **`import_workflow.py`** - ✅ **ACTIVE** - Main orchestration service for CSV imports
  - **External usage**: 10 imports across management commands, API views, tests, and tasks
  - **Dependencies**: Uses all bulk_* modules + FileHandler
  - **Status**: Essential - primary entry point for import operations

- **`mapping_processor.py`** - ✅ **ACTIVE** - GUI mapping configuration processor  
  - **External usage**: 3 imports (CSV mapping views, tests)
  - **Dependencies**: Uses all bulk_* modules + uri_utils
  - **Status**: Essential for GUI-based CSV mapping functionality

### Utility Services (Active Use)

- **`uri_utils.py`** - ✅ **ACTIVE** - URI utilities (mint_uri, slugify_uri_part)
  - **External usage**: 11 imports across multiple services and tests
  - **Dependencies**: No internal dependencies (base utility)
  - **Status**: Essential - widely used utility functions

- **`file_handler.py`** - ✅ **ACTIVE** - File upload handling services
  - **External usage**: 1 import (import_workflow.py)
  - **Dependencies**: No internal dependencies  
  - **Status**: Active - used by import workflow for file uploads

- **`data_utils.py`** - ✅ **ACTIVE** - Data type inference and validation utilities
  - **External usage**: 1 import (test file)
  - **Dependencies**: uri_utils (for XSD_BASE_URI)
  - **Status**: Active - has dedicated test coverage

### Specialized Services (Limited Use)

- **`linking_schema_generator.py`** - ⚠️ **LIMITED USE** - Schema generation for data linking
  - **External usage**: 1 import (test_import_pipeline.py)
  - **Dependencies**: No internal dependencies
  - **Status**: Specialized use case - kept for specific pipeline functionality

### Potentially Unused Files

- **`row_linker.py`** - ❓ **UNUSED** - Row linking functionality
  - **External usage**: 0 imports found
  - **Dependencies**: No internal dependencies
  - **Status**: Appears unused - candidate for removal or deprecation

### Test Files

- **`test_modular_structure.py`** - ✅ **ACTIVE** - Tests for the modular architecture
  - **Status**: Test file - validates the new modular structure works correctly

## Deprecated Files (Outside Current Directory)

The following files were moved/renamed during the modularization:

- `smart_bulk_updater_polars_DEPRECATED.py` - The original monolithic file (deprecated)
- `smart_bulk_updater_polars_ORIGINAL_BACKUP.py` - Backup of the original file

## Dependencies Graph

```
import_workflow.py
├── file_handler.py
└── bulk_* modules (all 5)

mapping_processor.py  
├── uri_utils.py
└── bulk_* modules (all 5)

bulk_update_engine.py
├── bulk_uri_service.py
└── bulk_data_analyzer.py

bulk_database_executor.py
├── bulk_uri_service.py
└── bulk_update_engine.py

bulk_relationship_processor.py
├── bulk_uri_service.py
├── bulk_update_engine.py
└── uri_utils.py

bulk_uri_service.py
└── uri_utils.py

data_utils.py
└── uri_utils.py

bulk_data_analyzer.py (no internal deps)
file_handler.py (no internal deps)  
linking_schema_generator.py (no internal deps)
row_linker.py (no internal deps)
uri_utils.py (no internal deps)
```

## Recommendations

### Keep These Files
- All `bulk_*` modules - core of the new architecture
- `import_workflow.py` - main orchestration layer
- `mapping_processor.py` - GUI mapping functionality  
- `uri_utils.py` - widely used utilities
- `file_handler.py` - active file upload functionality
- `data_utils.py` - has test coverage and utilities
- `linking_schema_generator.py` - specialized but used

### Consider for Removal
- `row_linker.py` - appears unused with no external imports

### Already Deprecated
- `smart_bulk_updater_polars_DEPRECATED.py` - can be removed after verification
- `smart_bulk_updater_polars_ORIGINAL_BACKUP.py` - backup file for safety

## Migration Status

✅ **COMPLETE** - The monolithic `smart_bulk_updater_polars.py` has been successfully split into 5 modular components with proper separation of concerns. All dependent files (`import_workflow.py` and `mapping_processor.py`) have been updated to use the new modular architecture.