# URL Creation and Dataset Import Process in Arkumu

This document explains the URL/URI creation process and dataset import workflow in the Arkumu application, covering both technical implementation details and high-level concepts for non-technical users.

## Table of Contents

1. [Overview](#overview)
2. [Understanding the Core Relationships: Datasets → Mappings → Blueprints](#understanding-the-core-relationships-datasets--mappings--blueprints)
3. [URI Types and Their Usage](#uri-types-and-their-usage)
4. [URI Creation Process](#uri-creation-process) 
5. [Mapping System: The Bridge from CSV to RDF](#mapping-system-the-bridge-from-csv-to-rdf)
6. [Blueprint System: Execution Planning](#blueprint-system-execution-planning)
7. [Dataset Import Process](#dataset-import-process)
8. [Technical Architecture](#technical-architecture)
9. [Non-Technical Summary](#non-technical-summary)

## Overview

The Arkumu system transforms CSV data into RDF (Resource Description Framework) triples, creating a knowledge graph structure. This transformation happens through a **three-layer architecture**:

1. **CSV Data Layer**: Your original spreadsheet with column headers like "Title", "Creator", "Date"
2. **Mapping Configuration Layer**: Defines column properties including names, types, relationships, and external ontology links
3. **RDF Output Layer**: Generated knowledge graph with URIs for entities, properties, and values

**Key Principle**: The mapping configuration defines the column properties that become RDF property names. While there's often similarity between CSV column names and mapping column names, the mapping's `name` field (which defaults to the CSV column name but can be customized) determines the final property URIs after slugification. This allows semantic consistency and clean property naming across datasets.

During the transformation process, every piece of data needs a unique identifier called a URI (Uniform Resource Identifier), similar to how every web page has a unique URL.

## URI Types and Their Usage

### Core URI Utility Functions
Located in `arkumu/common/uri_utils.py`:
- `mint_uri()`: Main function for creating URIs by combining base URI, institution, and path components
- `slugify_uri_part()`: Converts text to URI-safe format (lowercase, special chars to hyphens)
- `normalize_string_nfc()`: Ensures Unicode consistency

### Actually Created URIs During Import

#### 1. Dataset URIs ✅
```
Pattern: {base_uri}/{institution}/datasets/{dataset_name}
Example: http://arkumu.org/data/museum-xyz/datasets/artifact-collection
When created: Always - for every dataset being imported
Purpose: Main container/namespace for all data from a CSV file
```

#### 2. Entity URIs ✅
```
Pattern: {base_uri}/{institution}/entities/{dataset_name}/{entity_id}
Example: http://arkumu.org/data/museum-xyz/entities/artifact-collection/artifact-456
When created: For each row in the CSV file
Purpose: Represents individual data items (artifacts, persons, etc.)
```

#### 3. Property URIs ✅
```
Pattern: {base_uri}/properties/{property_name}
Example: http://arkumu.org/data/properties/artifact-title
When created: For each column's arkumu_type in the mapping
Purpose: Defines the relationship type between entities and their values
```

#### 4. Literal Value URIs ✅
```
Pattern: {base_uri}/literals/{hash}
Example: http://arkumu.org/data/literals/a7b8c9d0e2f4
When created: For each unique literal value in the data
Purpose: Represents actual data values (text, numbers, dates)
```

#### 5. Type URIs ✅
```
Pattern: {base_uri}/types/{type_name}
Example: http://arkumu.org/data/types/artifact-entity
When created: When schema metadata is created for datasets
Purpose: Defines the entity type for RDF type relationships
```

#### 6. External Ontology URIs ✅
```
Pattern: Varies by ontology (e.g., https://orcid.org/{orcid-id})
Example: https://orcid.org/0000-0002-1825-0097
When created: For columns mapped to external ontologies (ORCID, Wikidata, etc.)
Purpose: Links to external authority records
```


## URI Creation Process

### 1. Input Sanitization (slugify_uri_part)
- Special characters replaced: ä→ae, ö→oe, ü→ue, ß→ss
- Spaces and underscores → hyphens
- Non-alphanumeric characters removed
- Text converted to lowercase
- Multiple hyphens collapsed to single hyphen
- Empty strings become "n-a"

### 2. URI Assembly (mint_uri)
```python
# Example call
mint_uri("http://arkumu.org/data", "museum-xyz", "entities", "artifacts", "vase-001")
# Result: http://arkumu.org/data/museum-xyz/entities/artifacts/vase-001
```

### 3. Entity ID Generation
- **With anchor columns**: Uses specified column values as ID
- **Without anchors**: Uses row number (1-based) as ID
- Example: Row 0 in CSV → Entity "1" → URI: `.../entities/dataset-name/1`

### 4. Deduplication Strategy
- **Entities**: New URI for each row (even if data is identical)
- **Literals**: Reused based on value hash (Blake2b)
- **Properties**: Global URIs reused across all datasets
- **Types**: Reused when same type name appears

## Understanding the Core Relationships: Datasets → Mappings → Blueprints

### The Three-Level Architecture

```
Datasets           Mapping            Blueprint         Resources & Triples
┌─────────────┐    ┌───────────────┐   ┌──────────────┐   ┌─────────────────┐
│ CSV Files   │    │ Configuration │   │ Execution    │   │ Knowledge       │
│ - people.csv├───►│ - Column      ├──►│ Schema       ├──►│ Graph           │
│ - orgs.csv  │    │   mappings    │   │ - URIs       │   │ - Entities      │
│ - events.csv│    │ - FK relations│   │ - Properties │   │ - Relationships │
└─────────────┘    └───────────────┘   └──────────────┘   └─────────────────┘
   (Many)              (One)              (Generated)         (Many)
```

### What Each Component Does

#### 1. **Datasets** (Data Sources)
- **What**: Individual CSV files or data sources (e.g., "people.csv", "organizations.csv", "events.csv")
- **When created**: When users upload or register data files
- **Lifetime**: Persistent until explicitly deleted
- **Relationship**: Multiple datasets can be used by one mapping

#### 2. **Mapping** (Configuration)
- **What**: A user-defined configuration that specifies how to transform multiple datasets into RDF
- **Contains**: Column definitions, foreign key relationships, data types, external ontology links
- **Scope**: Can reference and process multiple datasets together (stored in `workspace_datasets`)
- **When created**: Manually by users through the UI
- **Relationship**: One mapping can handle multiple datasets

#### 3. **Blueprint** (Execution Plan)
- **What**: An automatically-generated, in-memory execution plan created from a mapping
- **Contains**: Complete schema definitions, property URIs, relationship instructions
- **When created**: Automatically at the start of each import execution
- **Lifetime**: Temporary - exists only during processing
- **Purpose**: Translates mapping configuration into machine-executable instructions

#### 4. **Resources & Triples** (Final Output)
- **What**: The actual knowledge graph - entities, properties, and relationships
- **When created**: During blueprint execution as data is processed
- **Lifetime**: Persistent in the database for querying

## Mapping System: The Bridge from CSV to RDF

### What is a Mapping?

A **Mapping** is the central configuration object that tells Arkumu how to transform one or more CSV datasets into RDF knowledge graph structure. It's the essential bridge between:
- **Raw Datasets**: Multiple CSV files with different schemas
- **RDF Graph**: Unified, connected semantic data with URIs and relationships

### Key Mapping Concepts

#### 1. Column Configuration
Each CSV column needs to be configured in the mapping with:

- **`name`**: The display name for the column (usually matches CSV column name)
- **`type`**: Data type (string, integer, etc.)
- **`is_anchor`**: Whether this column helps create the entity's unique ID  
- **`is_fk`**: Whether this column is a foreign key to another dataset
- **`is_multi_value`**: Whether the column contains multiple values (separated by delimiters)
- **`is_external_ontology`**: Whether this column links to external ontologies (ORCID, Wikidata, etc.)

**Property URI Generation**: The system uses the column's display name to generate property URIs. For example:
- Column "Rolle-ID" → Property URI: `{base_uri}/properties/rolle-id` (name is slugified)
- Column "VIAF-ID" → Property URI: `{base_uri}/properties/viaf-id` 
- Column "OrcID" → Property URI: `{base_uri}/properties/orcid`

**Note**: There's an internal `arkumu_type` field that defaults to the column name if not explicitly set, but in practice most mappings rely on the column name for property URI generation.

#### 2. Mapping Configuration Structure
```json
{
  "workspace_columns": {
    "fuk::Rolle::Rolle-ID": {
      "id": "fuk::Rolle::Rolle-ID",
      "name": "Rolle-ID",
      "type": "string",
      "is_fk": false,
      "source": "Rolle",
      "dataset": "Rolle", 
      "is_anchor": true,
      "is_multi_value": false
    },
    "fuk::AkteurIn::VIAF-ID": {
      "id": "fuk::AkteurIn::VIAF-ID", 
      "name": "VIAF-ID",
      "type": "string",
      "is_fk": false,
      "is_external_ontology": true,
      "external_ontologies": [{
        "uri_template": "https://viaf.org/viaf/{identifier}",
        "ontology_type": "viaf"
      }]
    },
    "fuk::Projekt::Ereignis": {
      "name": "Ereignis",
      "type": "string", 
      "is_fk": true,
      "fk_config": {
        "direction": "outbound",
        "target_column": "Ereignis-ID",
        "target_dataset": "Ereignis"
      },
      "is_multi_value": true
    }
  }
}
```

#### 3. Multi-Dataset Processing
Mappings can process multiple datasets together, which enables:
- **Cross-dataset relationships**: Foreign keys between different CSV files
- **Unified schema**: Consistent property definitions across all datasets
- **Coordinated import**: All datasets processed together to maintain referential integrity

Example: A mapping might process:
- `people.csv` → Creates person entities
- `organizations.csv` → Creates organization entities  
- `memberships.csv` → Creates relationships between people and organizations

#### 4. Entity ID Generation Strategy
Mappings define how to create unique identifiers for each row:
- **With anchor columns**: Uses specified column values as entity ID
- **Without anchors**: Uses row number (1-based) as entity ID
- Example: Row with Title="Ancient Vase" and anchor column → Entity ID: "ancient-vase"

### Complete Lifecycle Example

1. **Datasets Available**: `people.csv`, `organizations.csv`, `events.csv`
2. **User Creates Mapping**: Selects all 3 datasets, defines column mappings and relationships
3. **User Starts Import**: System processes the mapping
4. **Blueprint Generation**: Schema created automatically from mapping configuration
5. **Data Processing**: All 3 CSV files processed together using the blueprint
6. **Output**: Unified knowledge graph with people, organizations, events, and their relationships

## Blueprint System: Execution Planning

### What is a Blueprint?

A **Blueprint** is an automatically-generated execution plan that translates a mapping configuration into detailed processing instructions. It's created fresh for each import execution and serves as the complete execution template that defines:
- All property URIs (derived from column names in the mapping)
- Entity type definitions for each dataset
- Foreign key relationships between datasets  
- Processing order and validation rules

**Key Point**: Blueprints are temporary, in-memory objects created during import execution, not persistent database records.

### Mapping → Blueprint → Resources Flow

```
Mapping Config                Blueprint (Generated)           Final Resources
┌─────────────────────────┐   ┌─────────────────────────┐   ┌──────────────────┐
│ Datasets:               │   │ Execution Instructions: │   │ Knowledge Graph: │
│ - people.csv            │   │ - Create /datasets/     │   │ - Entity URIs    │
│ - orgs.csv              ├──►│   people URI            ├──►│ - Property triples│
│                         │   │ - Create /properties/   │   │ - Relationships  │
│ Columns:                │   │   name URI              │   │ - Type definitions│
│ - name → "name"         │   │ - Process FK relations  │   │                  │
│ - org_id → FK to orgs   │   │ - Generate entities     │   │                  │
└─────────────────────────┘   └─────────────────────────┘   └──────────────────┘
    (User-Created)               (Auto-Generated)              (Persistent)
```

### Blueprint Creation Process

1. **Triggered**: When user starts an import execution 
2. **Input**: Reads mapping configuration and selected datasets
3. **Schema-First Approach**: Creates complete execution plan before processing any data
4. **Four-Phase Generation**:
   - **Phase 1**: Plan dataset and entity type resource creation
   - **Phase 2**: Plan property definitions for all column names
   - **Phase 3**: Plan foreign key relationship processing
   - **Phase 4**: Plan schema metadata creation
5. **Output**: Complete execution blueprint ready for data processing
6. **Benefit**: Ensures consistent processing and data integrity across all datasets

### Why Use Blueprints?

- **Consistency**: Same mapping always produces same schema structure
- **Performance**: Pre-computed execution plan eliminates runtime decisions
- **Validation**: Schema conflicts detected before data processing begins
- **Multi-Dataset Coordination**: Ensures proper processing order for foreign key dependencies

## Dataset Import Process

### High-Level Workflow

1. **CSV Upload** → S3 bucket
2. **Task Creation** → Huey background job queued
3. **Mapping Load** → Configuration and blueprint retrieved
4. **Processing** → CSV rows transformed to RDF triples
5. **Storage** → Bulk insert into PostgreSQL

### Detailed Import Steps

#### Phase 1: Initialization
```python
run_mapping_aware_import_workflow(
    s3_bucket_name="data-bucket",
    s3_object_key="artifacts.csv",
    dataset_name="Artifact Collection",
    institution="museum-xyz",
    mapping_id="mapping-123",
    base_uri="http://arkumu.org/data"
)
```

#### Phase 2: Schema Creation
1. **Dataset Resource**
   ```
   URI: http://arkumu.org/data/museum-xyz/datasets/artifact-collection
   Type: Container for all resources from this CSV
   ```

2. **Entity Type Resource**
   ```
   URI: http://arkumu.org/data/types/artifact-collection-entity
   Purpose: Defines the type for all entities in this dataset
   ```

3. **Property Resources** (from mapping columns)
   ```
   URI: http://arkumu.org/data/properties/artifact-title
   URI: http://arkumu.org/data/properties/artifact-creator
   Purpose: Define relationships between entities and values
   ```

#### Phase 3: Data Processing (Per Row)
1. **Entity Creation**
   ```
   Row 1 → URI: http://arkumu.org/data/museum-xyz/entities/artifact-collection/1
   Row 2 → URI: http://arkumu.org/data/museum-xyz/entities/artifact-collection/2
   ```

2. **Value Resources** (literals)
   ```
   "Ancient Vase" → URI: http://arkumu.org/data/literals/a7b8c9d0
   "Modern Sculpture" → URI: http://arkumu.org/data/literals/f3e2d1c0
   ```

3. **Triple Generation**
   ```
   Subject: <entity-1>
   Predicate: <property-artifact-title>
   Object: <literal-"Ancient Vase">
   ```

#### Phase 4: Relationship Creation
- **Type relationships**: Entity → rdf:type → EntityType
- **Value relationships**: Entity → Property → Literal
- **Foreign keys**: Entity → Property → OtherEntity
- **Dataset membership**: Entity → isPartOf → Dataset

### Data Model Topology

The system uses an **entity-centric** approach:
- Each CSV row becomes an entity (not a "row" resource)
- Columns define properties (relationships)
- Values become literal resources or links to other entities
- No intermediate "cell" resources are created

## Technical Architecture

### Key Components

1. **ResourceManager** (`resource_manager.py`)
   - Generates all URI types
   - Creates resources in bulk
   - Manages deduplication
   - Handles triple creation

2. **MappingAwareProcessor** (`mapping_aware_processor.py`)
   - Orchestrates import workflow
   - Processes rows into entities
   - Handles column type logic
   - Manages relationships

3. **URI Generation Flow**
   ```
   CSV Row → Entity ID (anchor or row number)
           → slugify_uri_part()
           → mint_uri() with institution/dataset
           → Unique Entity URI
   
   Column Value → Property URI (from arkumu_type)
                → Literal URI (from value hash)
                → Triple (Entity-Property-Literal)
   ```

### Performance Optimizations

- **Bulk Operations**: Resources and triples created in batches of 500-1000
- **Deduplication**: Literals reused based on content hash
- **Streaming**: Large datasets processed in chunks
- **Caching**: Blueprint and property URIs cached

## Non-Technical Summary

### What Happens When You Import Data?

1. **Upload**: Your CSV file (spreadsheet) goes to cloud storage

2. **Mapping Configuration**: Before import, you must configure how each CSV column maps to semantic properties:
   - **Column Name**: What appears in your CSV header (e.g., "Title", "Creator")  
   - **arkumu_type**: The semantic identifier that becomes the RDF property (e.g., "artifact-title", "artifact-creator")
   - **Relationships**: How columns connect to other datasets
   - **Validation**: Data type and format requirements

3. **URI Creation**: Every piece of data gets a permanent web address:
   - Your organization: `/museum-xyz/`
   - Your dataset: `/datasets/artifacts/`
   - Each item: `/entities/artifacts/1` (from row number or anchor column)
   - Each property: `/properties/artifact-title` (from `arkumu_type` in mapping)

4. **Knowledge Graph**: Your flat spreadsheet becomes a connected graph where relationships are explicitly defined

5. **Benefits**:
   - **Permanent Links**: Data can be referenced forever with stable URIs
   - **Connections**: Link between datasets and organizations
   - **Standards**: Compatible with global semantic web standards
   - **Flexibility**: Query and combine data in ways spreadsheets can't support

### Example: Museum Collection Import (Corrected)

**Step 1: Input CSV**:
```
ID,Title,Creator,Date
001,Ancient Vase,Unknown,500 BCE
002,Modern Sculpture,Jane Doe,2023
```

**Step 2: Mapping Configuration** (Required before import):
```json
{
  "workspace_columns": {
    "museum::artifacts::ID": {
      "name": "ID",
      "type": "string",
      "is_anchor": true,
      "is_fk": false
    },
    "museum::artifacts::Title": {
      "name": "Title",
      "type": "string", 
      "is_fk": false
    },
    "museum::artifacts::Creator": {
      "name": "Creator", 
      "type": "string",
      "is_fk": false
    },
    "museum::artifacts::Date": {
      "name": "Date",
      "type": "string",
      "is_fk": false
    }
  }
}
```

**Step 3: Generated RDF Graph**:
```
Dataset: museum-xyz/datasets/artifacts  
  └── Entity: museum-xyz/entities/artifacts/001
       ├── title → "Ancient Vase"
       ├── creator → "Unknown"
       └── date → "500 BCE"
  └── Entity: museum-xyz/entities/artifacts/002
       ├── title → "Modern Sculpture"
       ├── creator → "Jane Doe"  
       └── date → "2023"
```

**Key Insight**: The property names in the graph (title, creator, date) are derived from the column names in the mapping configuration, which are then slugified for URI generation. The system uses the `name` field from the mapping, not the raw CSV column headers, allowing for clean, consistent property names across the knowledge graph.