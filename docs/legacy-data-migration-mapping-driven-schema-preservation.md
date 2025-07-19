# Legacy Data Migration with Mapping-Driven Schema Preservation

## Overview

When migrating legacy data systems, you often face a common challenge: your mapping defines the complete target schema you want to achieve, but your legacy CSV files are incomplete or fragmented. Some datasets may be missing entirely, others may be empty, yet the relationships and structure defined in your mapping are crucial for building a coherent metadata system.

This document explains how the enhanced mapping-aware processor solves this challenge by treating the mapping as an authoritative schema blueprint and preserving referential integrity even when source data is incomplete.

## The Challenge

### Traditional Problem

📋 **Mapping Definition (Complete Schema):**
```
├── customers (id, name, email)
├── orders (id, customer_id → customers.id, amount)
├── products (id, name, price)
└── order_items (order_id → orders.id, product_id → products.id, quantity)
```

📁 **Available Legacy CSV Files:**
```
├── ✅ orders.csv (has data)
├── ❌ customers.csv (missing file)
├── ✅ products.csv (empty file)
└── ✅ order_items.csv (has data)
```

❌ **Traditional Result:**
- FK relationships break (orders.customer_id points nowhere)
- Schema incomplete (missing customer and product entity definitions)
- Import fails or creates orphaned references

### Enhanced Solution

📋 **Mapping as Schema Blueprint + CSV Data:**
```
├── 🏗️ customers (stub structure created from mapping)
├── ✅ orders (processed from CSV data)
├── 🏗️ products (stub structure created from mapping)
└── ✅ order_items (processed from CSV data)
```

✅ **Enhanced Result:**
- Complete schema structure preserved
- FK relationships maintained through stub entities
- Future data integration points established
- Referential integrity intact

## How It Works

### 1. Mapping as Authoritative Schema

The mapping configuration serves as the complete blueprint for your target metadata system:

```python
mapping_config = {
    "customers": {
        "entity_type": "customer_id",
        "properties": ["customer_name", "customer_email"],
        "relationships": ["referenced_by_orders"]
    },
    "orders": {
        "entity_type": "order_id",
        "properties": ["order_amount"],
        "foreign_keys": ["customer_id → customers.id"]
    }
}
```

### 2. Stub Dataset Structure Creation

When a dataset is skipped (missing or empty CSV), the system creates a metadata structure:

```python
def _create_stub_dataset_structure(self, skipped_dataset, orphaned_refs, context):
    """Create stub dataset structure to preserve FK integrity for legacy data migration."""
    
    # 1. Create dataset resource (metadata container)
    dataset_resource = self.resource_manager.create_dataset_resource(skipped_dataset)
    
    # 2. Extract entity type from mapping
    entity_columns = [col for col in dataset_config.columns if col.column_type == 'entity']
    if entity_columns:
        create_entity_type_definition(entity_columns[0].arkumu_type)
    
    # 3. Create property schema definitions
    for column in dataset_config.columns:
        create_property_definition(column.arkumu_type, column.datatype, column.cardinality)
```

**What Gets Created:**
- 📁 Dataset Resource: Metadata container for the missing dataset
- 🏷️ Entity Type Definition: Based on mapping configuration
- 📊 Property Schema: All column definitions with datatypes and cardinality
- 🔗 Relationship Placeholders: Ready for FK resolution

### 3. Enhanced FK Resolution with Stub Entities

Instead of failing or skipping FK relationships to missing datasets:

```python
def _resolve_pending_relationships(self, context):
    for relationship in self.pending_relationships:
        target_dataset = relationship['target_dataset']
        
        if target_dataset in skipped_datasets:
            if target_dataset in context.stub_datasets:
                # Create enhanced stub entity with mapping metadata
                stub_entity = self._create_enhanced_stub_entity(relationship, context)
                # Preserve FK relationship
                create_relationship_to_stub(source_entity, stub_entity)
            else:
                # Skip orphaned reference
                orphaned_count += 1
```

**Enhanced Stub Entities Include:**
- ✅ Entity Type: From mapping definition (customer_id, product_id, etc.)
- ✅ Primary Identifier: The FK target value (customer_id: "123")
- ✅ Legacy Migration Marker: legacy_migration_stub: true
- ✅ Original Dataset Reference: original_dataset: "customers"
- ✅ Schema Compliance: Follows mapping structure exactly

### 4. Complete Import Results

```
🏗️ PRESERVING FK INTEGRITY: Creating stub structure for skipped dataset 'customers'
   📁 Created dataset resource for 'customers' (metadata container)
   🏷️ Defined entity type 'customer_id' for dataset 'customers'
   📊 Created schema definitions for 3 columns
   📊 FK references preserved: 15

🏗️ PRESERVING FK INTEGRITY: Creating stub structure for skipped dataset 'products'
   📁 Created dataset resource for 'products' (metadata container)  
   🏷️ Defined entity type 'product_id' for dataset 'products'
   📊 Created schema definitions for 4 columns
   📊 FK references preserved: 8

FK resolution completed:
  ✅ Resolved: 150 (real data relationships)
  🔗 Stub entities created: 23 (preserved legacy references)
  ❌ Failed: 2 (actual errors)
  📊 Total processed: 175
```

## Benefits for Legacy Migration

### 1. Complete Schema Preservation

- Mapping structure becomes your new metadata schema
- No schema information lost due to missing data
- Full entity and property definitions preserved

### 2. Referential Integrity Maintained

- FK relationships preserved even when targets are missing
- Stub entities provide valid relationship endpoints
- No orphaned references or broken links

### 3. Incremental Migration Support

- Process available data immediately
- Stub entities provide integration points for future data
- Can replace stubs with real data later without breaking existing relationships

### 4. Future Data Integration

```python
# Later, when you get customer data:
customer_stub = find_entity(uri="customers/123")
if customer_stub.has_property("legacy_migration_stub"):
    # Replace stub with real data
    enhance_stub_with_real_data(customer_stub, new_customer_data)
    # All existing FK relationships automatically work
```

### 5. Clear Audit Trail

- Explicit distinction between real data and schema stubs
- Migration metadata preserved for tracking
- Complete traceability of data source and status

## Implementation Details

### Statistics Tracking

```python
final_stats = {
    "datasets_processed": 2,           # orders, order_items
    "datasets_skipped": 2,             # customers, products  
    "stub_entities_created": 23,       # FK target placeholders
    "relationships_preserved": 23,      # FK integrity maintained
    "schema_definitions_created": 7,    # Complete mapping structure
}
```

### Logging Output

```
Dataset 'customers' has no CSV data, skipping
🏗️ PRESERVING FK INTEGRITY: Creating stub structure for skipped dataset 'customers'
   📊 FK references preserved: 15
   🔧 Stub entities will be created during FK resolution for missing targets

Dataset 'products' is empty, skipping
🏗️ PRESERVING FK INTEGRITY: Creating stub structure for skipped dataset 'products'
   📊 FK references preserved: 8
   🔧 Stub entities will be created during FK resolution for missing targets
```

## Use Cases

### Perfect For:

- Legacy system migration with incomplete data exports
- Phased migration projects where data arrives over time
- Schema evolution where structure precedes data
- Data warehouse consolidation from multiple fragmented sources
- Reference data management where relationships matter more than completeness

### Example Scenario:

**Legacy ERP Migration:**
```
├── Core business entities (customers, products) → Missing/incomplete exports
├── Transactional data (orders, invoices) → Available and complete
├── Referential relationships → Critical for business logic
└── Target: Complete metadata system with preserved relationships
```

**Result:**
- ✅ Transactional data imported with full context
- ✅ Business entity stubs created from schema
- ✅ All relationships preserved and queryable
- ✅ Future data integration points established

## Conclusion

This enhanced mapping-aware processor transforms the challenge of incomplete legacy data into an opportunity for systematic schema-driven migration. By treating the mapping as an authoritative blueprint and creating intelligent stub structures, you can:

1. Preserve your complete intended schema regardless of data availability
2. Maintain referential integrity across all relationships
3. Support incremental migration with clear integration points
4. Build a coherent metadata system from fragmented legacy sources

The result is a robust foundation for your new system that respects both the structure you want to achieve and the reality of incomplete legacy data sources.