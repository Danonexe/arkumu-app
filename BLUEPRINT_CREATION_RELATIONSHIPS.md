# Blueprint Creation and Relationship Handling in Arkumu

This document explains how the Arkumu import system creates blueprints and handles different types of relationships during the mapping process.

## Overview

The Arkumu mapping system uses a **Schema-First** approach with a sophisticated blueprint creation method that handles multiple relationship types beyond simple Foreign Keys. The system processes mappings in two distinct phases:

1. **Schema Initialization Phase**: Creates complete blueprints for all datasets
2. **Data Processing Phase**: Uses blueprints to process actual CSV data

## Blueprint Creation Method

### Core Process Flow

```python
def _create_complete_schema_blueprints(execution_config):
    # Phase 1: Dataset & Entity Type Resources
    _create_all_dataset_resources(execution_config.datasets)
    
    # Phase 2: Property Definitions (includes relationship properties)
    _create_all_property_definitions(execution_config.datasets)
    
    # Phase 3: FK Relationship Mapping
    _map_all_fk_relationships(execution_config.datasets)
    
    # Phase 4: Schema Metadata Triples
    _create_all_schema_metadata_triples()
```

### Blueprint Structure

Each dataset blueprint contains:

```python
{
    'dataset_name': str,
    'dataset_resource': Resource,  # The dataset container
    'entity_type_resource': Resource,  # What type of entities (e.g., Person, Artwork)
    'property_resources': {  # Column mappings
        'column_name': Resource  # Property definition
    },
    'fk_relationships': [  # Foreign key definitions
        {
            'source_dataset': str,
            'source_column': str,
            'target_dataset': str,
            'target_column': str,
            'relationship_type': str,
            'is_multi_value': bool,
            'fk_config': FKConfig
        }
    ],
    'created_at': datetime
}
```

### Caching Strategy

- Blueprints are cached by `mapping_id` for 1 hour
- All datasets from same mapping share blueprints
- Cache key: `schema_blueprints_mapping_{mapping_id}`

## Relationship Types Handled

The mapping system handles **five distinct relationship types**:

### 1. Foreign Key Relationships (`fk_relationships`)

**Configuration Structure:**
```python
"fk_relationships": {
    "fk_id_1": {
        "source_dataset": "authors",
        "source_column": "author_id", 
        "target_dataset": "people",
        "target_column": "person_id"
    }
}
```

**Blueprint Processing:**
- ✅ **Included in blueprints** during schema-first phase
- Cached with mapping blueprints
- Schema defined before data processing

**Data Processing:**
```python
# Creates: source_entity → property → target_entity
self.resource_manager.create_relationship_triple(
    source_entity, property_uri, target_entity
)
```

### 2. Relationship Contexts (`relationship_contexts`) - Junction Tables

**Configuration Structure:**
```python
"relationship_contexts": {
    "context_id_1": {
        "dataset_name": "author_book_relationships",
        "context_type": "junction",
        "primary_fk": "author_id",
        "secondary_fk": "book_id", 
        "context_columns": ["collaboration_type", "contribution_level", "start_date"]
    }
}
```

**Blueprint Processing:**
- ❌ **NOT included in blueprints**
- Processed during data import phase only
- No pre-schema creation

**Data Processing:**
```python
# Creates: junction_entity with properties
junction_entity = self.resource_manager.create_entity_resource(junction_uri)

# Adds context attributes
for context_column in rel_context.context_columns:
    self.resource_manager.create_property_triple(
        junction_entity, property_uri, value
    )

# Links to both entities
self.resource_manager.create_relationship_triple(
    junction_entity, "involves_primary", primary_entity
)
self.resource_manager.create_relationship_triple(
    junction_entity, "involves_secondary", secondary_entity
)
```

### 3. Multi-Value Columns (Implicit Relationships)

**Configuration:**
```python
{
    "column_type": "multi_value",
    "multi_value_separator": ",",
    # Creates multiple triples from one cell: "Python,Java,SQL" → 3 relationships
}
```

**Processing:**
- Splits single cell value into multiple relationships
- Each value becomes a separate triple
- Example: `skills: "Python,Java,SQL"` creates 3 separate skill relationships

### 4. External Ontology Integration

**Configuration Structure:**
```python
"external_ontologies": {
    "orcid_integration": {
        "column_name": "researcher_orcid",
        "ontology_type": "orcid",
        "uri_template": "https://orcid.org/{value}"
    }
}
```

**Processing:**
- Links entities to external URIs (ORCID, Wikidata, Dublin Core, etc.)
- Generates URIs based on templates
- Creates cross-dataset semantic links

### 5. Anchor Columns (Entity Identification)

**Purpose:**
- Define primary keys for entity URI generation
- Support custom entity identification strategies
- Enable stable URI generation across imports

## Data Processing Phases

### Phase 1: Schema Blueprint Creation

```python
# 1. Dataset & Entity Type Resources
for dataset_config in datasets:
    dataset_resource = create_dataset_resource(dataset_config.dataset_name)
    entity_type_resource = create_entity_type_resource(dataset_config)
    
    blueprint = {
        'dataset_name': dataset_config.dataset_name,
        'dataset_resource': dataset_resource,
        'entity_type_resource': entity_type_resource,
        'property_resources': {},
        'fk_relationships': []
    }

# 2. Property Definitions
for column in dataset_config.columns:
    property_resource = create_property_resource(column)
    blueprint['property_resources'][column.column_name] = property_resource

# 3. FK Relationship Mapping
for column in dataset_config.columns:
    if hasattr(column, 'fk_config') and column.fk_config:
        fk_relationship = create_fk_relationship_definition(column)
        blueprint['fk_relationships'].append(fk_relationship)
```

### Phase 2: Data Import with All Relationship Types

```python
def _process_streaming_entity_centric(context):
    # For each dataset:
    for dataset_config in execution_config.datasets:
        # Group columns by type
        column_groups = {
            'regular': [],
            'anchor': [],
            'foreign_key': [],
            'multi_value': [],
            'relationship_context': [],  # Junction table attributes
            'external_ontology': []
        }
        
        # Process each row with all relationship types
        for row_data in csv_data:
            entity_uri = generate_entity_uri(row_data, anchor_columns)
            entity_resource = create_entity_resource(entity_uri)
            
            # Process different column types
            _process_regular_columns(entity_resource, row_data, column_groups['regular'])
            _process_anchor_columns(entity_resource, row_data, column_groups['anchor'])
            _process_multi_value_columns(entity_resource, row_data, column_groups['multi_value'])
            _queue_fk_relationships(entity_uri, row_data, column_groups['foreign_key'])
    
    # Process junction tables separately
    _process_all_relationship_contexts(context)
    
    # Resolve all pending FK relationships
    _resolve_pending_relationships(context)
```

### Phase 3: Junction Table Processing

```python
def _process_all_relationship_contexts(context):
    for rel_context in execution_config.relationship_contexts:
        # For each row in junction dataset:
        for row_data in junction_csv:
            # Generate junction entity URI
            primary_value = row_data.get(rel_context.primary_fk)
            secondary_value = row_data.get(rel_context.secondary_fk)
            
            junction_uri = generate_junction_uri(
                rel_context.dataset_name,
                primary_value,
                secondary_value
            )
            
            # Create junction entity
            junction_entity = create_entity_resource(junction_uri)
            
            # Add context attributes (additional properties)
            for context_column in rel_context.context_columns:
                value = row_data.get(context_column)
                if value:
                    create_property_triple(
                        junction_entity,
                        f"context_{context_column}",
                        value
                    )
            
            # Link to primary and secondary entities
            create_relationship_triple(
                junction_entity, 
                "involves_primary", 
                primary_entity
            )
            create_relationship_triple(
                junction_entity, 
                "involves_secondary", 
                secondary_entity
            )
```

## Key Differences Between Relationship Types

| Relationship Type | Blueprint Phase | Data Phase | Entity Creation | Notes |
|------------------|----------------|------------|-----------------|--------|
| **FK Relationships** | ✅ Included | Deferred Resolution | Direct entity→entity | Simple references |
| **Relationship Contexts** | ❌ Not Included | Immediate Processing | Junction entities | Many-to-many with attributes |
| **Multi-Value Columns** | ✅ Property Defined | Multiple Triples | No new entities | One→many relationships |
| **External Ontology** | ✅ Property Defined | URI Generation | External links | Cross-dataset semantics |
| **Anchor Columns** | ✅ Entity Type Defined | URI Generation | Primary entities | Entity identification |

## Benefits of Schema-First Approach

1. **Consistency**: Schema defined before any data processing
2. **FK Integrity**: Relationships work even if target data isn't loaded yet
3. **Caching**: Efficient reuse across dataset imports
4. **Validation**: Early detection of schema inconsistencies
5. **Flexibility**: Supports complex relationship patterns
6. **Performance**: Pre-compiled schema reduces processing overhead

## Example: Complete Relationship Mapping

```json
{
  "workspace_datasets": [
    {
      "id": "authors",
      "name": "Authors Dataset",
      "columns": [
        {"name": "author_id", "arkumu_type": "author_identifier", "anchor": true},
        {"name": "name", "arkumu_type": "person_name"},
        {"name": "orcid", "arkumu_type": "orcid_identifier", "is_external_ontology": true}
      ]
    },
    {
      "id": "books", 
      "name": "Books Dataset",
      "columns": [
        {"name": "book_id", "arkumu_type": "book_identifier", "anchor": true},
        {"name": "title", "arkumu_type": "book_title"},
        {"name": "genres", "arkumu_type": "book_genre", "is_multi_value": true}
      ]
    },
    {
      "id": "authorships",
      "name": "Author-Book Relationships",
      "columns": [
        {"name": "author_id", "arkumu_type": "author_ref"},
        {"name": "book_id", "arkumu_type": "book_ref"},
        {"name": "role", "arkumu_type": "authorship_role"},
        {"name": "contribution_percent", "arkumu_type": "contribution_level"}
      ]
    }
  ],
  "fk_relationships": {
    "author_book_fk": {
      "source_dataset": "authorships",
      "source_column": "author_id",
      "target_dataset": "authors", 
      "target_column": "author_id"
    }
  },
  "relationship_contexts": {
    "authorship_context": {
      "dataset_name": "authorships",
      "context_type": "junction",
      "primary_fk": "author_id",
      "secondary_fk": "book_id",
      "context_columns": ["role", "contribution_percent"]
    }
  },
  "external_ontologies": {
    "orcid_links": {
      "column_name": "orcid",
      "ontology_type": "orcid",
      "uri_template": "https://orcid.org/{value}"
    }
  }
}
```

This creates:
- **Entities**: Authors, Books, Authorship relationships
- **Simple Properties**: Names, titles
- **Multi-value relationships**: Books→multiple genres
- **FK relationships**: Authorships→Authors, Authorships→Books  
- **Junction entities**: Authorship with role and contribution data
- **External links**: Authors→ORCID profiles

The blueprint ensures all these relationship patterns are properly handled during import, creating a rich, interconnected knowledge graph.