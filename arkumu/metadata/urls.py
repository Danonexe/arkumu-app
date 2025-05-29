from django.urls import path
from arkumu.metadata.views import dashboard_views, resource_views, triple_views, graph_views, bulk_editor_views

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
    path('graph/', graph_views.full_graph_view, name='full_graph_view'),
    path('graph/data/', graph_views.graph_data_view, name='graph_data'),
    
    # Bulk editor
    path('bulk-editor/', bulk_editor_views.bulk_triple_editor, name='bulk_triple_editor'),
    path('bulk-editor/query/', bulk_editor_views.query_relationships, name='query_relationships'),
    path('bulk-editor/create/', bulk_editor_views.create_bulk_triples, name='create_bulk_triples'),

    # Map S3 Files to Resources (New Path)
    path('map-s3-to-resources/', resource_views.MapS3ToResourcesView.as_view(), name='map_s3_to_resources'),
]
