# Database Blueprint Navigation Guide

## Overview

This guide provides a systematic approach to navigate and explore the metadata blueprint structure that exists in your Arkumu database. The blueprint represents the complete schema created during data migration, including datasets, entities, relationships, and properties - regardless of whether the original CSV data was complete or missing.

## Core Architecture

### Resource Model
The foundation of the metadata system:
- **URI**: Unique identifier (`http://example.org/datasets/customers`)
- **Resource Type**: IRI, CLASS, PROPERTY, or LITERAL
- **Name**: Human-readable name
- **Value**: Literal values or descriptions
- **Source**: Organization code (e.g., 'FUK')

### Triple Model
RDF-style relationships connecting resources:
- **Subject**: Source resource (cannot be LITERAL)
- **Predicate**: Relationship type (must be PROPERTY)
- **Object**: Target resource

## Navigation Patterns

### 1. Dataset Discovery

```python
from arkumu.metadata.models import Resource, Triple, ResourceType

# Find all datasets in the system
def get_all_datasets(organization_code=None):
    """Get all dataset resources, optionally filtered by organization."""
    datasets = Resource.objects.filter(uri__contains='/datasets/')
    if organization_code:
        datasets = datasets.filter(source=organization_code)
    return datasets

# Example usage
datasets = get_all_datasets('FUK')
for dataset in datasets:
    print(f"Dataset: {dataset.name} ({dataset.uri})")
```

### 2. Dataset → Entity Navigation

```python
def get_dataset_entities(dataset_resource):
    """Get all entities that belong to a specific dataset."""
    # Find the isPartOf property
    isPartOf_prop = Resource.objects.filter(
        uri='http://purl.org/dc/terms/isPartOf'
    ).first()
    
    if not isPartOf_prop:
        return Resource.objects.none()
    
    # Find entities linked to this dataset
    entity_triples = Triple.objects.filter(
        predicate=isPartOf_prop,
        object=dataset_resource
    ).select_related('subject')
    
    return [triple.subject for triple in entity_triples]

# Example usage
dataset = Resource.objects.filter(uri__contains='/datasets/customers').first()
entities = get_dataset_entities(dataset)
for entity in entities:
    print(f"Entity: {entity.name} ({entity.uri})")
```

### 3. Entity Properties and Relationships

```python
def explore_entity_structure(entity_resource):
    """Explore all properties and relationships of an entity."""
    
    # Get all outgoing relationships (what this entity points to)
    outgoing = Triple.objects.filter(subject=entity_resource).select_related('predicate', 'object')
    
    # Get all incoming relationships (what points to this entity)
    incoming = Triple.objects.filter(object=entity_resource).select_related('subject', 'predicate')
    
    return {
        'entity': entity_resource,
        'outgoing_relationships': list(outgoing),
        'incoming_relationships': list(incoming),
        'total_connections': len(outgoing) + len(incoming)
    }

# Example usage
entity = Resource.objects.filter(uri__contains='/entities/customer').first()
structure = explore_entity_structure(entity)
print(f"Entity {structure['entity'].name} has {structure['total_connections']} connections")
```

### 4. Foreign Key Discovery

```python
def find_foreign_key_relationships(dataset_name=None):
    """Find all foreign key relationships in the system."""
    
    # Look for common FK relationship patterns
    fk_predicates = Resource.objects.filter(
        uri__in=[
            'http://purl.org/dc/terms/isPartOf',
            'http://schema.org/isPartOf',
            # Add other FK relationship URIs as needed
        ]
    )
    
    fk_relationships = []
    for predicate in fk_predicates:
        relationships = Triple.objects.filter(predicate=predicate).select_related('subject', 'object')
        
        for rel in relationships:
            if dataset_name:
                # Filter by dataset if specified
                if dataset_name not in rel.subject.uri and dataset_name not in rel.object.uri:
                    continue
            
            fk_relationships.append({
                'source': rel.subject,
                'relationship': predicate,
                'target': rel.object,
                'is_stub': 'stub' in rel.object.name.lower() if rel.object.name else False
            })
    
    return fk_relationships

# Example usage
fk_rels = find_foreign_key_relationships('customers')
for rel in fk_rels:
    stub_indicator = " [STUB]" if rel['is_stub'] else ""
    print(f"{rel['source'].name} → {rel['target'].name}{stub_indicator}")
```

## Advanced Navigation with Services

### ResourceRelationshipService

```python
from arkumu.metadata.services.resource_relationship_service import ResourceRelationshipService

def comprehensive_blueprint_analysis(dataset_uri, organization='FUK'):
    """Perform comprehensive analysis of a dataset's blueprint structure."""
    
    service = ResourceRelationshipService()
    
    # Get the complete relationship map
    relationships = service.get_related_resources(
        resource_uri=dataset_uri,
        max_depth=3,  # Traverse 3 levels deep
        organization=organization
    )
    
    # Find bidirectional relationships
    bidirectional = service.get_bidirectional_relationships(dataset_uri)
    
    # Analyze relationship patterns
    analysis = {
        'dataset_uri': dataset_uri,
        'total_related_resources': len(relationships),
        'bidirectional_relationships': len(bidirectional),
        'relationship_depth_map': {}
    }
    
    # Group by depth level
    for rel in relationships:
        depth = rel.get('depth', 0)
        if depth not in analysis['relationship_depth_map']:
            analysis['relationship_depth_map'][depth] = []
        analysis['relationship_depth_map'][depth].append(rel)
    
    return analysis

# Example usage
dataset_uri = "http://example.org/datasets/customers"
analysis = comprehensive_blueprint_analysis(dataset_uri)
print(f"Dataset {dataset_uri} has {analysis['total_related_resources']} related resources")
```

### Blueprint Schema Discovery

```python
def discover_blueprint_schema(organization_code='FUK'):
    """Discover the complete schema blueprint for an organization."""
    
    # Get all resources for the organization
    org_resources = Resource.objects.for_organization(organization_code)
    
    # Categorize resources
    schema = {
        'datasets': org_resources.filter(uri__contains='/datasets/'),
        'entities': org_resources.filter(resource_type=ResourceType.IRI),
        'properties': org_resources.filter(resource_type=ResourceType.PROPERTY),
        'literals': org_resources.filter(resource_type=ResourceType.LITERAL),
        'classes': org_resources.filter(resource_type=ResourceType.CLASS)
    }
    
    # Get relationship statistics
    all_triples = Triple.objects.filter(
        subject__source=organization_code
    ).select_related('predicate')
    
    # Count relationship types
    relationship_counts = {}
    for triple in all_triples:
        pred_name = triple.predicate.name or triple.predicate.uri
        relationship_counts[pred_name] = relationship_counts.get(pred_name, 0) + 1
    
    schema['relationship_statistics'] = relationship_counts
    schema['total_relationships'] = len(all_triples)
    
    return schema

# Example usage
blueprint = discover_blueprint_schema('FUK')
print(f"Organization FUK has:")
print(f"  - {blueprint['datasets'].count()} datasets")
print(f"  - {blueprint['entities'].count()} entities")
print(f"  - {blueprint['properties'].count()} properties")
print(f"  - {blueprint['total_relationships']} relationships")
```

## Systematic Exploration Workflow

### Step 1: Organization Overview

```python
def organization_blueprint_overview(org_code):
    """Get high-level overview of organization's blueprint."""
    
    print(f"\n=== BLUEPRINT OVERVIEW FOR {org_code} ===")
    
    # 1. Get basic resource counts
    schema = discover_blueprint_schema(org_code)
    
    print(f"📊 Resource Summary:")
    print(f"   Datasets: {schema['datasets'].count()}")
    print(f"   Entities: {schema['entities'].count()}")
    print(f"   Properties: {schema['properties'].count()}")
    print(f"   Total Relationships: {schema['total_relationships']}")
    
    # 2. List all datasets
    print(f"\n📁 Datasets:")
    for dataset in schema['datasets']:
        entity_count = len(get_dataset_entities(dataset))
        print(f"   - {dataset.name}: {entity_count} entities")
    
    # 3. Top relationship types
    print(f"\n🔗 Top Relationship Types:")
    sorted_rels = sorted(schema['relationship_statistics'].items(), 
                        key=lambda x: x[1], reverse=True)[:5]
    for rel_type, count in sorted_rels:
        print(f"   - {rel_type}: {count} instances")

# Usage
organization_blueprint_overview('FUK')
```

### Step 2: Dataset Deep Dive

```python
def dataset_deep_dive(dataset_name_or_uri):
    """Perform detailed analysis of a specific dataset."""
    
    # Find the dataset
    if dataset_name_or_uri.startswith('http'):
        dataset = Resource.objects.filter(uri=dataset_name_or_uri).first()
    else:
        dataset = Resource.objects.filter(
            uri__contains='/datasets/',
            name__icontains=dataset_name_or_uri
        ).first()
    
    if not dataset:
        print(f"Dataset '{dataset_name_or_uri}' not found")
        return
    
    print(f"\n=== DATASET ANALYSIS: {dataset.name} ===")
    print(f"URI: {dataset.uri}")
    
    # Get entities
    entities = get_dataset_entities(dataset)
    print(f"\n👥 Entities ({len(entities)}):")
    
    for entity in entities[:10]:  # Show first 10
        structure = explore_entity_structure(entity)
        print(f"   - {entity.name}: {structure['total_connections']} connections")
        
        # Show FK relationships
        fk_rels = find_foreign_key_relationships()
        entity_fks = [rel for rel in fk_rels if rel['source'] == entity]
        if entity_fks:
            for fk in entity_fks[:3]:  # Show first 3 FKs
                stub_note = " [STUB]" if fk['is_stub'] else ""
                print(f"     → {fk['target'].name}{stub_note}")
    
    if len(entities) > 10:
        print(f"   ... and {len(entities) - 10} more entities")

# Usage
dataset_deep_dive('customers')
```

### Step 3: Relationship Path Discovery

```python
def find_relationship_paths(from_dataset, to_dataset, org_code='FUK'):
    """Find all relationship paths between two datasets."""
    
    service = ResourceRelationshipService()
    
    # Get dataset URIs
    from_ds = Resource.objects.filter(
        uri__contains='/datasets/',
        name__icontains=from_dataset,
        source=org_code
    ).first()
    
    to_ds = Resource.objects.filter(
        uri__contains='/datasets/',
        name__icontains=to_dataset,
        source=org_code
    ).first()
    
    if not from_ds or not to_ds:
        print("One or both datasets not found")
        return
    
    print(f"\n=== RELATIONSHIP PATHS ===")
    print(f"From: {from_ds.name}")
    print(f"To: {to_ds.name}")
    
    # Find relationship chain
    try:
        chain = service.get_relationship_chain(
            from_uri=from_ds.uri,
            to_uri=to_ds.uri
        )
        
        if chain:
            print(f"\n🔗 Connection found:")
            for i, step in enumerate(chain):
                print(f"   {i+1}. {step.get('relationship', 'N/A')}")
        else:
            print("\n❌ No direct relationship path found")
            
    except Exception as e:
        print(f"\n⚠️ Error finding path: {e}")

# Usage
find_relationship_paths('customers', 'orders')
```

## Usage Examples

### Complete Blueprint Exploration

```python
# 1. Start with organization overview
organization_blueprint_overview('FUK')

# 2. Dive into specific datasets
dataset_deep_dive('customers')
dataset_deep_dive('orders')

# 3. Explore relationships between datasets
find_relationship_paths('customers', 'orders')

# 4. Find all stub entities (from incomplete migrations)
all_fks = find_foreign_key_relationships()
stubs = [rel for rel in all_fks if rel['is_stub']]
print(f"\nFound {len(stubs)} stub relationships from incomplete data")
```

### Access Control Considerations

```python
from arkumu.metadata.utils import get_user_accessible_resources

def user_accessible_blueprint(user):
    """Get blueprint structure accessible to a specific user."""
    
    accessible = get_user_accessible_resources(user)
    
    # Filter blueprint components by access control
    user_datasets = accessible.filter(uri__contains='/datasets/')
    user_entities = accessible.filter(resource_type=ResourceType.IRI)
    
    return {
        'datasets': user_datasets,
        'entities': user_entities,
        'total_accessible': accessible.count()
    }
```

## Key Properties and Relationships

### Standard Properties
- `http://purl.org/dc/terms/isPartOf` - Entity belongs to dataset
- `http://purl.org/dc/terms/hasPart` - Dataset contains entity
- `http://schema.org/isPartOf` - Alternative part-of relationship

### Stub Entity Markers
- Look for entities with `legacy_migration_stub: true` in properties
- Names containing "stub" indicate placeholder entities
- These represent FK targets from incomplete CSV data

## Best Practices

1. **Always filter by organization** to avoid cross-organization data leaks
2. **Use the ResourceRelationshipService** for complex traversals
3. **Check access permissions** when building user-facing tools
4. **Handle missing relationships gracefully** - not all FKs may resolve
5. **Cache relationship queries** for performance in production

This systematic approach allows you to fully explore and understand the blueprint structure that exists in your database, including both real data and the intelligent stub structures created during migration.