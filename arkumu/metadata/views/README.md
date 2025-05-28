# Metadata Views Structure

This directory contains all view modules for the metadata application, organized by functionality. The previous monolithic `dashboard_views.py` file (969 lines) has been split into focused, single-responsibility modules.

## File Organization

### 📊 `dashboard_views.py` (38 lines)
**Main dashboard and overview functionality**
- `metadata_dashboard()` - Main dashboard with statistics and recent activity

### 🗂️ `resource_views.py` (148 lines)  
**Resource listing, detail, and visualization**
- `resource_list()` - Paginated resource listing with filters
- `resource_detail()` - Detailed view of a single resource with triples
- `resource_graph()` - Individual resource graph visualization (D3.js)

### 🔗 `triple_views.py` (91 lines)
**Triple search and management**
- `triple_search()` - Advanced triple filtering and search
- `triple_list()` - Paginated list of all triples

### 📈 `graph_views.py` (442 lines)
**Complex graph visualization and data structures**
- `full_graph_view()` - Hierarchical tree + graph explorer for RDF data
- `graph_data_view()` - HTMX endpoint for dynamic graph data
- `get_dataset_graph()` - Helper for dataset-level graph data
- `get_row_graph()` - Helper for row-level graph data  
- `get_cell_graph()` - Helper for cell-level graph data

### ✏️ `bulk_editor_views.py` (286 lines)
**Bulk triple editing and creation**
- `bulk_triple_editor()` - Main bulk editing interface
- `query_relationships()` - HTMX endpoint for querying existing triples
- `create_bulk_triples()` - Handle bulk triple creation with validation

### 📦 `__init__.py` (40 lines)
**Package initialization and convenient imports**
- Exports all view functions for easy importing
- Maintains backward compatibility

## Benefits of This Structure

1. **Single Responsibility**: Each file has a clear, focused purpose
2. **Maintainability**: Easier to locate and modify specific functionality
3. **Team Development**: Multiple developers can work on different aspects without conflicts
4. **Testing**: Smaller, focused modules are easier to unit test
5. **Performance**: Only import what you need for specific functionality
6. **Documentation**: Each module can have targeted documentation

## Import Examples

```python
# Import specific views
from arkumu.metadata.views.resource_views import resource_list, resource_detail
from arkumu.metadata.views.graph_views import full_graph_view

# Import from package (recommended)
from arkumu.metadata.views import metadata_dashboard, resource_list, triple_search

# Import entire modules for complex use cases
from arkumu.metadata.views import graph_views
```

## Size Comparison

| File | Lines | Purpose |
|------|-------|---------|
| **Original** | **969** | **Everything** |
| `dashboard_views.py` | 38 | Dashboard overview |
| `resource_views.py` | 148 | Resource management |
| `triple_views.py` | 91 | Triple operations |
| `graph_views.py` | 442 | Graph visualization |
| `bulk_editor_views.py` | 286 | Bulk editing |
| `__init__.py` | 40 | Package setup |
| **Total** | **1,045** | **Organized structure** |

The slight increase in total lines is due to import statements and package organization, but each individual file is now much more manageable and focused. 