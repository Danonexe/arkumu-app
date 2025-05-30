# Metadata Views Package
# This package contains all view modules for the metadata application

# Dashboard views
from .dashboard_views import metadata_dashboard, all_upload_sessions, all_ingest_sessions

# Resource views  
from .resource_views import resource_list, resource_detail, resource_graph

# Triple views
from .triple_views import triple_search, triple_list

# Graph views
from .graph_views import full_graph_view, graph_data_view

# Bulk editor views
from .bulk_editor_views import bulk_triple_editor, query_relationships, create_bulk_triples


# Data discovery views
from .data_discovery_views import DataDiscoveryView, search_resources, link_file_to_resource, batch_link_files, unlink_file, auto_link_all

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

    # Data discovery
    'DataDiscoveryView',
    'search_resources',
    'link_file_to_resource',
    'batch_link_files',
    'unlink_file',
    'auto_link_all',
] 