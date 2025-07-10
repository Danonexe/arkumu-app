# Arkumu Import Execution System

This directory contains the modular execution engine for the Arkumu data import system. It transforms CSV data into RDF triples through a structured pipeline, providing sophisticated mapping capabilities including foreign keys, multi-value columns, and external ontologies.

## System Overview

The execution service transforms CSV data into RDF triples through a structured pipeline that converts each CSV cell into semantic statements. For example, a cell containing "John Doe" in the "author" column at row 5 generates triples stating:
- The dataset "My Publications" `hasPart` a column "author"
- There is a cell resource representing "author" at row 5
- This cell resource `hasValue` "John Doe"

### Core Data Flow
```
ChunkedProcessor → MappingAwareProcessor → MappingExecutionEngine → (DataProcessor & ResourceManager)
```

### How Triples are Generated

**1. Structural Triples** - Define dataset architecture:
```python
# Dataset → hasPart → Column relationships
Triple(subject=dataset_resource, predicate=has_part_prop, object=column_resource)
```

**2. Value Triples** - Link cells to their data:
```python  
# Cell → rdf:value → Literal relationships
Triple(subject=cell_resource, predicate=rdf_value_prop, object=value_resource)
```

### How Resources are Created

Each entity becomes a `Resource` with unique URIs:
- **Dataset Resource**: `{base_uri}/dataset/{dataset_name}`
- **Column Resources**: `{base_uri}/dataset/{dataset_name}/column/{column_name}`
- **Cell Resources**: `{base_uri}/dataset/{dataset_name}/column/{column_name}/row/{row_id}`
- **Value Resources**: `{base_uri}/value/{hash(literal_value)}`

## Architecture Overview

The import system uses a **two-tier architecture** that separates high-level mapping logic from low-level execution:

```
GUI Mapping Configuration
        ↓
GUIMappingProcessor (High-level orchestrator)
        ↓
MappingExecutionPlan (4 phases)
        ↓
Phase-by-Phase Execution:
  - Phase 1: EntityProcessor (anchor entities)
  - Phase 2: Literals processing (regular + multi-value)
  - Phase 3: RelationshipProcessor (FK relationships)
  - Phase 4: ContextProcessor (junction tables)
        ↓
MappingExecutionEngine (Low-level engine)
        ↓
Database (Resources & Triples)
```

## Core Components

### 1. **MappingExecutionEngine** (`execution_engine.py`)
The low-level execution engine responsible for:
- Processing data according to execution plans
- Managing batch operations for performance
- Coordinating component services
- Providing both simple and complex import capabilities

**Key Features:**
- Generic design (not GUI-specific)
- Supports dry-run analysis
- Handles streaming for large datasets
- Tracks comprehensive statistics

### 2. **MappingAwareProcessor** (`mapping_aware_processor.py`)
Enhanced processor that:
- Interprets complex user-defined mapping configurations (`ExecutionConfig`)
- Handles complex column types (FK, multi-value, external ontologies)
- Manages Foreign Key relationship logic across chunks/datasets
- Supports multiple processing strategies (entity-centric, streaming, multi-phase)

### 3. **DataProcessor** (`data_processor.py`)
Handles data preparation using Polars:
- High-performance data cleaning and preparation
- Vectorized Unicode normalization
- Data validation and empty row removal
- Row identifier assignment

### 4. **ResourceManager** (`resource_manager.py`)
Manages database resource creation:
- Abstracts all direct database interactions for `Resource` and `Triple` objects
- Generates consistent, unique URIs for all entities
- Uses Django's ORM with `bulk_create` for efficient database operations
- Caches standard properties (like `rdf:value`) to avoid repeated lookups

### 5. **UpdateAnalyzer** (`update_analyzer.py`)
Provides change detection and analysis:
- Determines what data already exists
- Implements update strategies (skip, overwrite, timestamp-based)
- Provides impact analysis for dry runs

### 6. **ChunkedProcessor** (`chunked_processor.py`)
Handles large dataset processing:
- Memory-efficient CSV reading in chunks using Polars
- Streaming data in configurable chunks
- Progress tracking and garbage collection between chunks

### 7. **ExecutionStatistics** (`statistics.py`)
Tracks detailed metrics:
- Per-dataset statistics
- Performance metrics
- Error categorization
- Memory usage monitoring

## Processing Phases

The system processes data in **four distinct phases** to handle dependencies correctly:

### Phase 1: Entity Creation
- Creates anchor entities using primary key columns
- Establishes the foundation for all other data
- Must complete before properties can be added

### Phase 2: Literal Processing
- Adds regular properties to entities
- Handles multi-value columns (comma-separated values)
- Each value becomes a separate triple

### Phase 3: Relationship Processing
- Creates FK relationships between entities
- Links source entities to target entities
- Creates stub entities if targets don't exist
- Supports multi-value FKs

### Phase 4: Context Processing
- Handles junction tables with additional attributes
- Creates relationship contexts
- Manages many-to-many relationships with properties

## Integration with GUI Mapping System

The execution system integrates seamlessly with the GUI mapping interface:

### GUI to Execution Flow

1. **User Configuration** (GUI)
   - Select datasets
   - Configure column mappings
   - Mark anchor columns, FKs, multi-value fields
   - Define external ontology mappings

2. **Mapping Analysis** (`GUIMappingProcessor`)
   - Analyzes GUI configuration
   - Creates `MappingExecutionPlan`
   - Organizes columns by processing phase
   - Validates dependencies

3. **Phased Execution**
   - Each phase processes relevant columns
   - Maintains proper dependency order
   - Handles errors gracefully
   - Tracks statistics

### Supported Column Types

| Column Type | Symbol | Phase | Description |
|-------------|--------|-------|-------------|
| **Anchor** | ⚓ | 1 | Primary keys for entity creation |
| **Regular** | 📝 | 2 | Standard literal properties |
| **Multi-value** | 🔀 | 2 | Comma-separated values |
| **Foreign Key** | 🔗 | 3 | Relationships to other entities |
| **External Ontology** | 🌐 | 2/3 | Links to external URIs (ORCID, Wikidata) |
| **Relationship Context** | 🏷️ | 4 | Junction table attributes |

## Usage Examples

### Simple Import
```python
engine = MappingExecutionEngine("INSTITUTION", "http://base.uri")
metrics = engine.execute_simple_import(
    csv_data=data,
    dataset_name="employees"
)
```

### Complex Mapping Import
```python
# With GUI mapping configuration
processor = MappingAwareProcessor(institution, base_uri, statistics)
metrics = processor.process_with_execution_config(
    execution_config=config,
    csv_sources={"employees": emp_data, "departments": dept_data},
    strategy=ProcessingStrategy.MULTI_PHASE
)
```

### Streaming Large Dataset
```python
config = StreamingConfig(chunk_size=5000, parallel_chunks=2)
process_large_dataset_chunked(
    csv_path="/path/to/large.csv",
    dataset_name="large_dataset",
    config=config
)
```

## Key Differences from Previous System

### Modular Architecture
- **Before**: Monolithic SmartBulkUpdaterPolars
- **Now**: Specialized components with single responsibilities

### Phased Processing
- **Before**: Single-pass processing
- **Now**: Four-phase execution with dependency handling

### GUI Integration
- **Before**: Limited mapping support
- **Now**: Full GUI mapping configuration support

### Flexibility
- **Before**: Fixed processing approach
- **Now**: Multiple strategies (entity-centric, streaming, multi-phase)

## Performance Considerations

- **Batch Processing**: Configurable batch sizes for optimal performance
- **Streaming Support**: Handle datasets larger than memory
- **Bulk Operations**: Minimize database round trips
- **Parallel Processing**: Support for concurrent chunk processing

## Future Enhancements

1. **Advanced FK Patterns**: Many-to-many with properties
2. **External Ontology Validation**: Real-time validation against external sources
3. **Custom Processing Phases**: User-defined phases for special requirements
4. **Distributed Processing**: Support for cluster-based processing

## Related Documentation

- Parent directory: `/arkumu/importer/services/importer/README.md`
- GUI mapping views: `/arkumu/metadata/views/csv_mapping/`
- Mapping analysis: `/arkumu/metadata/services/mapping/`