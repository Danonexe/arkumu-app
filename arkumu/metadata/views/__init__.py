# Metadata Views Package
# This package contains all view modules for the metadata application

# Dashboard views
from .dashboard_views import metadata_dashboard

# Resource views  
from .resource_views import resource_list, resource_detail, resource_graph

# Triple views
from .triple_views import triple_search, triple_list

# Graph views
from .graph_views import full_graph_view, graph_data_view

# Bulk editor views
from .bulk_editor_views import bulk_triple_editor, query_relationships, create_bulk_triples

__all__ = [
    # Dashboard
    'metadata_dashboard',
    
    # Resources
    'resource_list', 
    'resource_detail', 
    'resource_graph',
    
    # Triples
    'triple_search', 
    'triple_list',
    
    # Graph visualization
    'full_graph_view', 
    'graph_data_view',
    
    # Bulk editing
    'bulk_triple_editor', 
    'query_relationships', 
    'create_bulk_triples',
] 