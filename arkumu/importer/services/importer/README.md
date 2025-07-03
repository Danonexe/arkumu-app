# Arkumu Importer Services - Modular Architecture

This directory contains the modular importer services that were refactored from the original monolithic `smart_bulk_updater_polars.py` file. The architecture implements a high-performance, multi-stage pipeline for importing CSV data into a graph-based (RDF-like) data model.

## Architecture Overview

The importer uses a **modular pipeline architecture** with these key characteristics:
- **High Performance**: Utilizes Polars for vectorized operations and Django bulk database operations
- **Flexible Strategies**: Supports multiple import modes (skip existing, update, merge, replace)
- **Graph-Based Model**: Transforms tabular CSV data into RDF triples with proper URI management
- **Phased Processing**: Handles complex dependencies through ordered execution phases

## Module Descriptions and Usage

### Core Data Processing Modules

#### 1. `bulk_data_analyzer.py` - Data Analysis & Preparation
**Purpose**: Pre-import data inspection and transformation
**Key Features**:
- Unicode normalization (NFC) for consistent data handling
- Multi-value cell detection (e.g., "tag1, tag2, tag3")
- Data quality metrics (null percentages, empty rows)
- Dry-run capability to preview changes

**Usage Example**:
```python
analyzer = BulkDataAnalyzer(multi_value_threshold=0.2)
df_normalized = analyzer.normalize_unicode_vectorized(df)
multi_value_analysis = analyzer.analyze_dataset_multi_values(df, column_configs)
```

#### 2. `bulk_uri_service.py` - URI Generation & Management
**Purpose**: Centralized URI generation following consistent patterns
**Key Features**:
- Generates URIs for datasets, columns, rows, cells, entities, and properties
- Parses existing URIs to extract components
- Ensures URI consistency across the entire system

**Usage Example**:
```python
uri_service = BulkURIService(base_uri="http://example.org", organization_id="org1")
dataset_uri = uri_service.mint_dataset_uri("my_dataset")
entity_uri = uri_service.mint_entity_uri("my_dataset", "column1", "value123")
```

#### 3. `bulk_update_engine.py` - Update Strategy & Planning
**Purpose**: Determines what actions to take with incoming data
**Key Features**:
- Multiple update strategies via `UpdateStrategy` enum:
  - `SKIP_EXISTING`: Don't update existing resources
  - `UPDATE_VALUES`: Update literal values only
  - `MERGE_TRIPLES`: Add new triples, keep existing
  - `REPLACE_ALL`: Complete replacement
- Generates `ResourceUpdate` objects representing planned changes
- Compares with existing database state

**Usage Example**:
```python
engine = BulkUpdateEngine()
updates, stats = engine.determine_update_actions(
    df=polars_dataframe,
    dataset_name="my_dataset",
    update_strategy=UpdateStrategy.UPDATE_VALUES
)
```

#### 4. `bulk_database_executor.py` - Database Operations
**Purpose**: Efficiently executes bulk database operations
**Key Features**:
- Bulk creates/updates using Django's bulk operations
- Implements different linking topologies (row, column, mesh)
- Creates proper structural hierarchy (dataset → columns → rows → cells)
- Handles multi-value cells with proper relationship creation

**Usage Example**:
```python
executor = BulkDatabaseExecutor(uri_service)
final_stats = executor.execute_bulk_update(
    updates=resource_updates,
    dataset_name="my_dataset",
    update_strategy=UpdateStrategy.UPDATE_VALUES
)
```

#### 5. `bulk_relationship_processor.py` - Cross-Dataset Relationships
**Purpose**: Creates relationships between datasets after import
**Key Features**:
- Foreign key relationship processing
- Junction table handling for many-to-many relationships
- Entity reference resolution across datasets
- Supports both inbound and outbound relationships

**Usage Example**:
```python
processor = BulkRelationshipProcessor(uri_service)
fk_relationship = FKRelationship(
    source_column="author_id",
    source_dataset="articles",
    target_column="id", 
    target_dataset="authors",
    relationship_type="has_author"
)
relationships_created = processor.process_foreign_key_relationships(
    df, "articles", [fk_relationship]
)
```

### Orchestration & High-Level Services

#### 6. `import_workflow.py` - Main Import Orchestrator
**Purpose**: Primary entry point for all import operations
**Key Features**:
- Single CSV file import with configurable strategies
- Directory-based batch imports with relationship discovery
- Smart update mode vs. fast import mode
- Optional file upload handling

**Usage Example**:
```python
# Simple import
stats = ImportWorkflowService.import_csv(
    csv_path="/path/to/data.csv",
    dataset_name="my_dataset",
    institution="my_org",
    base_uri="http://example.org",
    delimiter=";",
    has_quoted_fields=True,
    use_smart_updater=True,
    update_strategy=UpdateStrategy.UPDATE_VALUES
)

# Directory import with relationships
results = ImportWorkflowService.import_csv_directory(
    directory_path="/path/to/csvs/",
    institution="my_org",
    discover_foreign_keys=True,
    process_foreign_keys=True
)
```

#### 7. `mapping_processor.py` - GUI Mapping Configuration Processor
**Purpose**: Handles complex user-defined mappings from the UI
**Key Features**:
- Four-phase execution model:
  1. **Phase 1**: Create anchor entities from key columns
  2. **Phase 2**: Add literal values to entities
  3. **Phase 3**: Create relationships (foreign keys)
  4. **Phase 4**: Create relationship contexts (junction tables)
- Respects data dependencies between phases
- Supports external ontology mappings

**Usage Example**:
```python
processor = GUIMappingProcessor(base_uri="http://example.org")
result = processor.process_gui_mapping(
    mapping_config={
        "workspace_columns": [...],
        "column_configs": {...},
        "import_strategy": {...}
    },
    csv_data=dataframe_as_dict_list,
    organization_id="org1",
    dataset_name="my_dataset"
)
```

### Utility Modules

#### 8. `file_handler.py` - File Upload Management
**Purpose**: Handles file uploads referenced in CSV data
**Key Features**:
- Heuristic detection of file path columns
- Resolves relative paths against base directory
- Uploads files to storage and links URLs to cells

**Usage Example**:
```python
handler = FileHandler(upload_service, files_base_directory="/data/files")
stats = handler.process_file_uploads(
    dataset_name="images",
    file_columns=["image_path", "thumbnail_path"]
)
```

#### 9. `data_utils.py` - Data Manipulation Utilities
**Purpose**: Common data transformation and validation functions
**Key Features**:
- CSV header validation and normalization
- Multi-value cell splitting with quote handling
- Unicode normalization for entire datasets
- XSD data type inference

**Usage Example**:
```python
# Validate headers
is_valid, message = validate_csv_headers(["col 1", "col-2", "col_3"])

# Split multi-value cell
values = split_multi_value_cell("apple, banana, cherry", separator=",")

# Infer data type
xsd_type = infer_xsd_type("2024-01-01")  # Returns XSD.date
```

#### 10. `uri_utils.py` - URI Manipulation Utilities
**Purpose**: Low-level URI generation and manipulation
**Key Features**:
- String slugification for URI-safe components
- Consistent URI minting patterns
- Unicode handling for international characters

**Usage Example**:
```python
# Slugify for URI use
slug = slugify_uri_part("Hello World!")  # Returns "hello-world"

# Mint a URI
uri = mint_uri("http://example.org", "datasets", "my-dataset")
# Returns: "http://example.org/datasets/my-dataset"
```

#### 11. `linking_schema_generator.py` - Relationship Schema Generator
**Purpose**: Generates formal schemas describing discovered relationships
**Key Features**:
- Creates JSON schemas for foreign key relationships
- Supports different merge strategies for duplicate handling
- Machine-readable relationship definitions

**Usage Example**:
```python
generator = LinkingSchemaGenerator()
schema = generator.generate_foreign_key_schema(
    source_dataset="orders",
    source_column="customer_id",
    target_dataset="customers",
    target_column="id"
)
```

### Test Files

#### `test_modular_structure.py`
Validates that the modular architecture works correctly and all imports are properly configured.

## Typical Import Workflows

### 1. Simple CSV Import
```
CSV File → ImportWorkflowService → BulkDataAnalyzer → BulkUpdateEngine 
→ BulkDatabaseExecutor → FileHandler (optional) → Complete
```

### 2. Batch Directory Import with Relationships
```
CSV Directory → ImportWorkflowService → Process each CSV → 
BulkRelationshipProcessor → LinkingSchemaGenerator → Complete
```

### 3. GUI-Driven Mapping Import
```
Mapping Config + CSV → GUIMappingProcessor → Phase 1 (Entities) → 
Phase 2 (Literals) → Phase 3 (Relationships) → Phase 4 (Contexts) → Complete
```

## Dependencies

### External Dependencies
- **Polars**: High-performance dataframe operations
- **Django ORM**: Database persistence
- **dateutil**: Date parsing and manipulation

### Internal Dependencies
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

Most modules depend on:
└── uri_utils.py (foundational utilities)
```

## Update Strategies

The system supports multiple strategies for handling existing data:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `SKIP_EXISTING` | Skip if resource exists | Initial imports, avoid overwrites |
| `UPDATE_VALUES` | Update literal values only | Data corrections |
| `MERGE_TRIPLES` | Add new, keep existing | Incremental updates |
| `REPLACE_ALL` | Complete replacement | Full refresh |
| `FORCE_OVERWRITE` | Always overwrite | Development/testing |
| `SMART_MERGE` | Intelligent merge based on timestamps | Production updates |

## Performance Considerations

1. **Vectorized Operations**: Uses Polars for all data transformations
2. **Bulk Database Operations**: Minimizes database round trips
3. **Batch Processing**: Configurable batch sizes (default: 5000)
4. **Memory Efficient**: Streaming support for large files
5. **Index Management**: Automatic index creation for common queries

## Migration Status

✅ **COMPLETE** - Successfully migrated from monolithic to modular architecture:
- Original file: `smart_bulk_updater_polars.py` (deprecated)
- New architecture: 11 focused modules with clear responsibilities
- All dependent services updated to use new modules
- Full test coverage maintained

## Future Enhancements

1. **Async Processing**: Add async/await support for I/O operations
2. **Streaming Large Files**: Enhanced memory management for GB+ files
3. **Validation Framework**: Pluggable data validation rules
4. **Import Profiles**: Saved configuration templates
5. **Progress Tracking**: Real-time import progress updates