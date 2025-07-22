# URL Creation and Dataset Import Process in Arkumu

This document explains the URL/URI creation process and dataset import workflow in the Arkumu application, covering both technical implementation details and high-level concepts for non-technical users.

## Table of Contents

1. [Overview](#overview)
2. [URI Types and Their Usage](#uri-types-and-their-usage)
3. [URI Creation Process](#uri-creation-process)
4. [Blueprint System](#blueprint-system)
5. [Dataset Import Process](#dataset-import-process)
6. [Technical Architecture](#technical-architecture)
7. [Non-Technical Summary](#non-technical-summary)

## Overview

The Arkumu system transforms CSV data into RDF (Resource Description Framework) triples, creating a knowledge graph structure. During this process, every piece of data needs a unique identifier called a URI (Uniform Resource Identifier), similar to how every web page has a unique URL.

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

### URIs Defined But Not Used

#### Column URIs ❌
```
Pattern: {base_uri}/{institution}/datasets/{dataset_name}/columns/{column_name}
Status: Function exists (generate_column_uri) but not called during import
Reason: Properties are created as global URIs instead
```

#### Row URIs ❌
```
Pattern: {base_uri}/{institution}/datasets/{dataset_name}/rows/{row_id}
Status: Functions exist (generate_row_uri, create_row_resources) but disabled
Reason: System uses entity-centric approach where rows become entities
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

## Blueprint System

### What is a Blueprint?

A blueprint is a pre-computed schema representation of a dataset within a mapping. It serves as a template that defines:
- All properties (columns) and their datatypes
- Relationships between datasets (foreign keys)
- Entity types and their structure
- Validation rules and constraints

### Blueprint Creation Process

1. **Triggered**: When a mapping reaches "validated" or "active" status
2. **Created by**: `create_mapping_blueprint()` signal handler
3. **What it does**: Pre-creates dataset URIs for all datasets in the mapping
4. **Benefit**: Enables navigation to dataset pages before any data is imported

### Blueprint Usage During Import

The blueprint guides the import process by:
- Defining which columns become properties
- Specifying property datatypes
- Mapping foreign key relationships
- Validating data against schema constraints

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

2. **Mapping**: The system uses your pre-configured mapping to understand:
   - What each column represents
   - How data relates to other datasets
   - What validation rules apply

3. **URI Creation**: Every piece of data gets a permanent web address:
   - Your organization: `/museum-xyz/`
   - Your dataset: `/datasets/artifacts/`
   - Each item: `/entities/artifacts/vase-001`
   - Each property: `/properties/artifact-title`

4. **Knowledge Graph**: Your flat spreadsheet becomes a connected graph:
   ```
   Vase-001 --has-title--> "Ancient Vase"
   Vase-001 --created-by--> Person-123
   Vase-001 --found-at--> Location-456
   ```

5. **Benefits**:
   - **Permanent Links**: Data can be referenced forever
   - **Connections**: Link between datasets and organizations
   - **Standards**: Compatible with global standards
   - **Flexibility**: Query in ways spreadsheets can't support

### Example: Museum Collection Import

**Input CSV**:
```
ID,Title,Creator,Date
001,Ancient Vase,Unknown,500 BCE
002,Modern Sculpture,Jane Doe,2023
```

**Output Graph**:
```
Dataset: museum-xyz/datasets/artifacts
  └── Entity: museum-xyz/entities/artifacts/1
       ├── has-title → "Ancient Vase"
       ├── has-creator → "Unknown"
       └── has-date → "500 BCE"
  └── Entity: museum-xyz/entities/artifacts/2
       ├── has-title → "Modern Sculpture"
       ├── has-creator → "Jane Doe"
       └── has-date → "2023"
```

Each piece becomes findable, linkable, and combinable with data from any other institution using the same standards.