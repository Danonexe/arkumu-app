from django.urls import path
from arkumu.metadata.views import dashboard_views, resource_views, triple_views, graph_views, bulk_editor_views, data_discovery_views, data_explorer_views

app_name = 'metadata'

urlpatterns = [
    # Dashboard
    path('dashboard/', dashboard_views.metadata_dashboard, name='metadata_dashboard'),
    path('dashboard/all-uploads/', dashboard_views.all_upload_sessions, name='all_upload_sessions'),
    path('dashboard/all-ingests/', dashboard_views.all_ingest_sessions, name='all_ingest_sessions'),
    
    # Data Explorer (unified resource and triple browsing)
    path('data-explorer/', data_explorer_views.data_explorer, name='data_explorer'),
    
    # Resource details (still needed for individual resource pages)
    path('resources/<uuid:resource_id>/', resource_views.resource_detail, name='resource_detail'),
    path('resources/<uuid:resource_id>/graph/', resource_views.resource_graph, name='resource_graph'),
    
    # Graph visualization
    path('triple-viewer/', graph_views.triple_viewer_view, name='triple_viewer'),
    path('tree/data/', graph_views.tree_data_view, name='tree_data'),
    path('tree/bucket/<str:bucket_name>/', graph_views.tree_bucket_content_view, name='tree_bucket_content'),
    path('tree/bucket/<str:bucket_name>/more/', graph_views.tree_bucket_more_view, name='tree_bucket_more'),
    path('tree/dataset/<uuid:dataset_id>/', graph_views.tree_dataset_view, name='tree_dataset'),
    path('tree/dataset/<uuid:dataset_id>/details/', graph_views.tree_dataset_details_view, name='tree_dataset_details'),
    path('tree/dataset/<uuid:dataset_id>/more/', graph_views.tree_dataset_more_view, name='tree_dataset_more'),
    path('tree/dataset/<uuid:dataset_id>/row/<uuid:row_id>/', graph_views.tree_row_view, name='tree_row'),
    path('tree/row/<uuid:row_id>/details/', graph_views.tree_row_details_view, name='tree_row_details'),
    path('tree/cell/<uuid:cell_id>/details/', graph_views.tree_cell_details_view, name='tree_cell_details'),
    path('graph/', graph_views.full_graph_view, name='full_graph_view'),
    path('graph/data/', graph_views.graph_data_view, name='graph_data'),
    
    # Bulk editor - Core functionality
    path('bulk-editor/', bulk_editor_views.bulk_triple_editor, name='bulk_triple_editor'),
    path('bulk-editor/list-s3-csv/', bulk_editor_views.list_s3_csv_files, name='list_s3_csv_files'),
    path('bulk-editor/auto-analyze/', bulk_editor_views.auto_analyze_csv, name='auto_analyze_csv'),
    path('bulk-editor/find-matching/', bulk_editor_views.find_matching_resources, name='find_matching_resources'),
    path('bulk-editor/add-mapping/', bulk_editor_views.add_mapping_rule, name='add_mapping_rule'),

    # Bulk editor - Dataset transformation
    path('bulk-editor/list-datasets/', bulk_editor_views.list_datasets, name='list_datasets'),
    path('bulk-editor/preview-transformation/', bulk_editor_views.preview_dataset_transformation, name='preview_transformation'),
    path('bulk-editor/execute-transformation/', bulk_editor_views.execute_dataset_transformation, name='execute_transformation'),
    
    # Bulk editor - Service-powered enhancements
    path('bulk-editor/smart-suggestions/', bulk_editor_views.smart_mapping_suggestions, name='smart_mapping_suggestions'),
    path('bulk-editor/apply-suggestions/', bulk_editor_views.apply_smart_suggestions, name='apply_smart_suggestions'),
    path('bulk-editor/enhanced-preview/', bulk_editor_views.enhanced_dataset_preview, name='enhanced_dataset_preview'),
    path('bulk-editor/service-execution/', bulk_editor_views.service_powered_execution, name='service_powered_execution'),
    path('bulk-editor/enhanced-validation/', bulk_editor_views.enhanced_validation_preview, name='enhanced_validation_preview'),
    path('bulk-editor/cross-dataset-resolution/', bulk_editor_views.cross_dataset_resolution, name='cross_dataset_resolution'),
    
    # Data Discovery
    path('data-discovery/', data_discovery_views.DataDiscoveryView.as_view(), name='data_discovery'),
    path('data-discovery/search-resources/', data_discovery_views.search_resources, name='search_resources'),
    path('data-discovery/link-file/', data_discovery_views.link_file_to_resource, name='link_file_to_resource'),
    path('data-discovery/batch-link/', data_discovery_views.batch_link_files, name='batch_link_files'),
    path('data-discovery/unlink-file/', data_discovery_views.unlink_file, name='unlink_file'),
    path('data-discovery/auto-link-all/', data_discovery_views.auto_link_all, name='auto_link_all'),
    path('data-discovery/rescan-s3/', data_discovery_views.rescan_s3_files, name='rescan_s3_files'),
    ]
