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
    
    # Bulk editor
    path('bulk-editor/', bulk_editor_views.bulk_triple_editor, name='bulk_triple_editor'),
    path('bulk-editor/list-s3-csv/', bulk_editor_views.list_s3_csv_files, name='list_s3_csv_files'),
    path('bulk-editor/auto-analyze/', bulk_editor_views.auto_analyze_csv, name='auto_analyze_csv'),
    path('bulk-editor/preview-auto-mappings/', bulk_editor_views.preview_auto_mappings, name='preview_auto_mappings'),
    path('bulk-editor/apply-auto-mappings/', bulk_editor_views.apply_auto_mappings, name='apply_auto_mappings'),
    path('bulk-editor/query/', bulk_editor_views.query_relationships, name='query_relationships'),
    path('bulk-editor/create/', bulk_editor_views.create_bulk_triples, name='create_bulk_triples'),
    path('bulk-editor/find-matching/', bulk_editor_views.find_matching_resources, name='find_matching_resources'),
    path('bulk-editor/add-mapping/', bulk_editor_views.add_mapping_rule, name='add_mapping_rule'),
    path('bulk-editor/clear-mappings/', bulk_editor_views.clear_mapping_rules, name='clear_mapping_rules'),
    path('bulk-editor/apply-mappings/', bulk_editor_views.apply_mappings_to_batch, name='apply_mappings_to_batch'),
    path('bulk-editor/add-triple/', bulk_editor_views.add_triple_from_form, name='add_triple_from_form'),
    path('bulk-editor/validate/', bulk_editor_views.validate_batch_triples, name='validate_batch_triples'),
    path('bulk-editor/clear-batch/', bulk_editor_views.clear_batch_triples, name='clear_batch_triples'),
    path('bulk-editor/update-predicates/', bulk_editor_views.update_predicate_options, name='update_predicate_options'),
    # Step 2 transformation endpoints
    path('bulk-editor/list-datasets/', bulk_editor_views.list_datasets, name='list_datasets'),
    path('bulk-editor/dataset-info/', bulk_editor_views.get_dataset_info, name='get_dataset_info'),
    path('bulk-editor/preview-transformation/', bulk_editor_views.preview_dataset_transformation, name='preview_transformation'),
    path('bulk-editor/execute-transformation/', bulk_editor_views.execute_dataset_transformation, name='execute_transformation'),
    
    # Data Discovery
    path('data-discovery/', data_discovery_views.DataDiscoveryView.as_view(), name='data_discovery'),
    path('data-discovery/search-resources/', data_discovery_views.search_resources, name='search_resources'),
    path('data-discovery/link-file/', data_discovery_views.link_file_to_resource, name='link_file_to_resource'),
    path('data-discovery/batch-link/', data_discovery_views.batch_link_files, name='batch_link_files'),
    path('data-discovery/unlink-file/', data_discovery_views.unlink_file, name='unlink_file'),
    path('data-discovery/auto-link-all/', data_discovery_views.auto_link_all, name='auto_link_all'),
    path('data-discovery/rescan-s3/', data_discovery_views.rescan_s3_files, name='rescan_s3_files'),
    ]
