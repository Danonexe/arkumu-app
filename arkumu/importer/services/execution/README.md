# Modular Execution Engine

This directory contains the modular execution engine for processing CSV data with mapping configurations. It replaces the monolithic `SmartBulkUpdaterPolars` with a clean, maintainable architecture.

## Architecture Overview

The execution engine is built with a **layered architecture** where each module has a single responsibility:

```
MappingExecutionEngine (orchestrator)
├── DataProcessor (data preparation)
├── ResourceManager (URI generation & database operations)  
├── UpdateAnalyzer (change detection & strategies)
├── ExecutionStatistics (metrics tracking)
└── MappingCoordinator (mapping analysis - from metadata app)
```

## Core Files

### 1. `execution_engine.py` - Main Orchestrator
**What it does:** The main entry point that coordinates all other components.

**Key features:**
- Orchestrates the complete import workflow
- Handles both simple imports and complex mapping-driven imports
- Manages batch processing and error handling
- Provides unified interface for CSV processing

**Main class:** `MappingExecutionEngine`
- `execute_simple_import()` - For basic CSV imports
- `execute_with_processing_plan()` - For complex mapping-driven imports
- `analyze_import_impact()` - Preview changes before import

### 2. `data_processor.py` - Data Preparation
**What it does:** Handles all data cleaning, validation, and preprocessing.

**Key features:**
- Converts list data to Polars DataFrames for performance
- Unicode normalization (vectorized for speed)
- Multi-value column detection and processing
- Data validation against mapping constraints
- Row identifier assignment

**Main class:** `DataProcessor`
- `prepare_for_processing()` - Complete data preparation pipeline
- `normalize_unicode_vectorized()` - Fast Unicode normalization
- `detect_multi_value_columns()` - Auto-detect comma-separated values

### 3. `resource_manager.py` - URI Generation & Database Operations
**What it does:** Manages URI creation and bulk database operations.

**Key features:**
- Generates consistent URIs for datasets, rows, and cells
- Bulk creation of resources and triples for performance
- Handles anchor columns (custom primary keys)
- Foreign key relationship management

**Main class:** `ResourceManager`
- `generate_dataset_uri()` - Creates dataset URIs
- `generate_cell_uri()` - Creates cell-level URIs
- `create_resources_bulk()` - Efficient bulk resource creation
- `create_triples_bulk()` - Efficient bulk triple creation

### 4. `update_analyzer.py` - Change Detection & Update Strategies
**What it does:** Analyzes existing data and determines update strategies.

**Key features:**
- Detects what data already exists in the database
- Implements different update strategies (skip, overwrite, timestamp-based)
- Analyzes potential impacts before making changes
- Optimizes for minimal database operations

**Main class:** `UpdateAnalyzer`
- `analyze_existing_data()` - Check what's already in database
- `determine_update_strategy()` - Decide how to handle conflicts
- `get_impact_summary()` - Preview what will change

### 5. `statistics.py` - Metrics Tracking
**What it does:** Tracks detailed metrics throughout the import process.

**Key features:**
- Per-dataset statistics tracking
- Performance metrics (processing time, rows/second)
- Error counting and categorization
- Memory usage monitoring

**Main classes:**
- `ExecutionMetrics` - Individual metrics container
- `ExecutionStatistics` - Statistics aggregator and tracker

## Integration with Mapping System

The execution engine integrates with the mapping analysis system from the metadata app:

```
/arkumu/metadata/services/mapping/     # ← Mapping analysis & configuration  
/arkumu/importer/services/execution/   # ← This directory - execution engine
```

**How it works:**
1. User creates mappings in GUI (`execution_views.py`)
2. Mapping coordinator analyzes FK relationships and dependencies
3. Execution engine receives processing plan and executes it
4. Components handle special column types (FK, anchor, multi-value, external ontology)

## Special Column Types Support

The execution engine supports all column types from the GUI mapping system:

| Column Type | Symbol | Support Status | Handler |
|-------------|--------|----------------|---------|
| **Anchor Columns** | ⚓ | ✅ Full | `ResourceManager.generate_cell_uri()` |
| **Foreign Keys** | 🔗 | 🚧 Framework Ready | `ResourceManager` + future FK resolver |
| **Multi-value** | 🔀 | ✅ Full | `DataProcessor.detect_multi_value_columns()` |
| **Relationship Context** | 🏷️ | 🚧 Framework Ready | Future implementation |
| **External Ontology** | 🌐 | 🚧 Framework Ready | Future external resolver |

## Performance Features

### Polars DataFrame Processing
- **Vectorized operations** for Unicode normalization
- **Lazy evaluation** for memory efficiency  
- **Columnar processing** for better cache performance

### Bulk Database Operations
- **Batch insertions** reduce database round-trips
- **Bulk resource creation** with conflict handling
- **Optimized queries** for existing data detection

### Memory Management
- **Streaming processing** for large datasets
- **Configurable batch sizes** 
- **Memory usage tracking**

## Usage Examples

### Basic Import
```python
engine = MappingExecutionEngine("INSTITUTION", "http://base.uri")
metrics = engine.execute_simple_import(csv_data, "dataset_name")
print(f"Created {metrics.resources_created} resources")
```

### Mapping-Driven Import
```python
# With mapping configuration from GUI
metrics = engine.execute_simple_import(
    csv_data, 
    "employees",
    mapping_config={
        "columns": {
            "name": {"is_anchor": True},
            "department": {"is_fk": True, "target_dataset": "departments"},
            "skills": {"is_multi_value": True, "separator": ","}
        }
    }
)
```

### Impact Analysis
```python
# Preview changes before import
impact = engine.analyze_import_impact(csv_data, "dataset_name")
print(f"Will create {impact['new_resources']} new resources")
print(f"Will update {impact['updated_resources']} existing resources")
```

## Testing

Each module has comprehensive pytest test coverage:

- `test_execution_engine.py` - Integration tests for main orchestrator
- `test_data_processor.py` - Data processing and cleaning tests
- `test_resource_manager.py` - URI generation and database tests  
- `test_update_analyzer.py` - Change detection strategy tests
- `test_statistics.py` - Metrics tracking tests

**Run tests:**
```bash
pytest arkumu/importer/tests/services/execution/ -v
```

## Migration from SmartBulkUpdaterPolars

This modular architecture **preserves all performance optimizations** from the original `SmartBulkUpdaterPolars`:

- ✅ Polars DataFrame processing
- ✅ Vectorized Unicode normalization  
- ✅ Bulk database operations
- ✅ Multi-value column handling
- ✅ Efficient batching

**Plus adds:**
- 🆕 Mapping configuration consumption
- 🆕 FK relationship processing framework
- 🆕 Modular, testable architecture
- 🆕 Comprehensive metrics tracking
- 🆕 Multiple update strategies

## Future Enhancements

The modular architecture makes it easy to add new features:

1. **FK Relationship Resolver** - Process foreign key relationships across datasets
2. **External Ontology Integration** - ORCID, Wikidata, etc.
3. **Advanced Multi-value Processing** - Nested relationships
4. **Streaming Import** - Handle massive datasets
5. **Parallel Processing** - Multi-threaded execution