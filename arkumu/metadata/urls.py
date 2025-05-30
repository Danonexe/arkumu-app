from django.urls import path
from arkumu.metadata.views import dashboard_views, resource_views, triple_views, graph_views, bulk_editor_views, data_discovery_views

app_name = 'metadata'

urlpatterns = [
    # Dashboard
    path('dashboard/', dashboard_views.metadata_dashboard, name='metadata_dashboard'),
    path('dashboard/all-uploads/', dashboard_views.all_upload_sessions, name='all_upload_sessions'),
    path('dashboard/all-ingests/', dashboard_views.all_ingest_sessions, name='all_ingest_sessions'),
    
    # Resources
    path('resources/', resource_views.resource_list, name='resource_list'),
    path('resources/<uuid:resource_id>/', resource_views.resource_detail, name='resource_detail'),
    path('resources/<uuid:resource_id>/graph/', resource_views.resource_graph, name='resource_graph'),
    
    # Triples
    path('triples/search/', triple_views.triple_search, name='triple_search'),
    path('triples/', triple_views.triple_list, name='triple_list'),
    
    # Graph visualization
    path('triple-viewer/', graph_views.triple_viewer_view, name='triple_viewer'),
    path('tree/data/', graph_views.tree_data_view, name='tree_data'),
    path('tree/bucket/<str:bucket_name>/', graph_views.tree_bucket_content_view, name='tree_bucket_content'),
    path('tree/bucket/<str:bucket_name>/more/', graph_views.tree_bucket_more_view, name='tree_bucket_more'),
    path('tree/dataset/<uuid:dataset_id>/', graph_views.tree_dataset_view, name='tree_dataset'),
    path('tree/dataset/<uuid:dataset_id>/more/', graph_views.tree_dataset_more_view, name='tree_dataset_more'),
    path('tree/dataset/<uuid:dataset_id>/row/<uuid:row_id>/', graph_views.tree_row_view, name='tree_row'),
    path('graph/', graph_views.full_graph_view, name='full_graph_view'),
    path('graph/data/', graph_views.graph_data_view, name='graph_data'),
    
    # Bulk editor
    path('bulk-editor/', bulk_editor_views.bulk_triple_editor, name='bulk_triple_editor'),
    path('bulk-editor/query/', bulk_editor_views.query_relationships, name='query_relationships'),
    path('bulk-editor/create/', bulk_editor_views.create_bulk_triples, name='create_bulk_triples'),

    
    # Data Discovery
    path('data-discovery/', data_discovery_views.DataDiscoveryView.as_view(), name='data_discovery'),
    path('data-discovery/search-resources/', data_discovery_views.search_resources, name='search_resources'),
    path('data-discovery/link-file/', data_discovery_views.link_file_to_resource, name='link_file_to_resource'),
    path('data-discovery/batch-link/', data_discovery_views.batch_link_files, name='batch_link_files'),
    path('data-discovery/unlink-file/', data_discovery_views.unlink_file, name='unlink_file'),
    path('data-discovery/auto-link-all/', data_discovery_views.auto_link_all, name='auto_link_all'),
    ]
