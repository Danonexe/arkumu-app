from django.urls import path
from arkumu.metadata.views import dashboard_views, resource_views, triple_views, graph_views, bulk_editor_views, data_discovery_views, data_explorer_views, split_views, direct_data_views
from arkumu.metadata.views.csv_mapping import csv_mapping_views, saved_mappings_api, saved_mappings_ui

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
    path('dataset-viewer/', graph_views.dataset_viewer_view, name='dataset_viewer'),
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
    
    # Semantic Graph Editor
    path('graph-editor/', bulk_editor_views.semantic_graph_editor, name='semantic_graph_editor'),
    path('graph-editor/table-data/', bulk_editor_views.graph_table_data, name='graph_table_data'),
    
    # Graph Connections Viewer
    path('graph-connections/', bulk_editor_views.graph_connections_view, name='graph_connections'),
    path('htmx/datasets/', bulk_editor_views.get_datasets_htmx, name='get_datasets_htmx'),
    path('htmx/dataset/<uuid:dataset_id>/columns/', bulk_editor_views.get_dataset_columns_htmx, name='get_dataset_columns_htmx'),
    path('htmx/column/<str:column_id>/cells/', bulk_editor_views.get_column_cells_htmx, name='get_column_cells_htmx'),
    path('htmx/cell/<uuid:cell_id>/connections/', bulk_editor_views.get_cell_connections_htmx, name='get_cell_connections_htmx'),
    
    # Data Discovery
    path('data-discovery/', data_discovery_views.DataDiscoveryView.as_view(), name='data_discovery'),
    path('data-discovery/search-resources/', data_discovery_views.search_resources, name='search_resources'),
    path('data-discovery/link-file/', data_discovery_views.link_file_to_resource, name='link_file_to_resource'),
    path('data-discovery/batch-link/', data_discovery_views.batch_link_files, name='batch_link_files'),
    path('data-discovery/unlink-file/', data_discovery_views.unlink_file, name='unlink_file'),
    path('data-discovery/auto-link-all/', data_discovery_views.auto_link_all, name='auto_link_all'),
    path('data-discovery/rescan-s3/', data_discovery_views.rescan_s3_files, name='rescan_s3_files'),
    
    # Split Table/Graph View (Database-based)
    path('split-view/', split_views.split_table_graph_view, name='split_table_graph'),
    path('split-view/load-source-data/', split_views.load_source_data, name='load_source_data'),
    path('split-view/dataset-card/', split_views.get_dataset_card, name='split_dataset_card'),
    path('split-view/load-more-rows/', split_views.load_more_dataset_rows, name='load_more_dataset_rows'),
    path('split-view/graph-data/', split_views.get_graph_data, name='split_graph_data'),
    path('split-view/debug-database/', split_views.debug_database, name='debug_database'),
    path('split-view/highlight-column/', split_views.highlight_column_in_graph, name='highlight_column'),
    path('split-view/highlight-cell/', split_views.highlight_cell_in_graph, name='highlight_cell'),
    path('split-view/refresh-graph/', split_views.refresh_graph, name='refresh_graph'),
    path('split-view/toggle-layout/', split_views.toggle_layout, name='toggle_layout'),
    path('split-view/analyze-relationships/', split_views.analyze_dataset_relationships, name='analyze_dataset_relationships'),
    path('split-view/clear-all-datasets/', split_views.clear_all_datasets, name='split_clear_all_datasets'),
    
    # Direct Data Analysis (File-based, faster)
    path('direct-analysis/', direct_data_views.direct_split_table_graph_view, name='direct_split_table_graph'),
    path('direct-analysis/load-source-data/', direct_data_views.direct_load_source_data, name='direct_load_source_data'),
    path('direct-analysis/load-all-datasets/', direct_data_views.direct_load_all_datasets, name='direct_load_all_datasets'),
    path('direct-analysis/dataset-card/', direct_data_views.direct_get_dataset_card, name='direct_dataset_card'),
    path('direct-analysis/toggle-dataset-card/', direct_data_views.toggle_dataset_card, name='toggle_dataset_card'),
    path('direct-analysis/load-more-rows/', direct_data_views.direct_load_more_dataset_rows, name='direct_load_more_dataset_rows'),
    path('direct-analysis/analyze-relationships/', direct_data_views.direct_analyze_dataset_relationships, name='direct_analyze_dataset_relationships'),
    path('direct-analysis/import-preview/', direct_data_views.direct_get_import_preview, name='direct_import_preview'),
    path('direct-analysis/analyze-column/', direct_data_views.direct_analyze_column, name='direct_analyze_column'),
    
    # Cross-Dataset Relationship Discovery
    path('direct-analysis/relationship-discovery/', direct_data_views.direct_relationship_discovery_view, name='direct_relationship_discovery'),
    path('direct-analysis/dataset-linking/', direct_data_views.direct_dataset_linking_view, name='direct_dataset_linking'),
    
    # Manual Relationship Builder
    path('add-column-to-workspace/', direct_data_views.add_column_to_workspace, name='add_column_to_workspace'),
    path('remove-column-from-workspace/', direct_data_views.remove_column_from_workspace, name='remove_column_from_workspace'),
    path('toggle-all-columns/', direct_data_views.toggle_all_columns, name='toggle_all_columns'),
    path('create-mapping/', direct_data_views.create_mapping, name='create_mapping'),
    path('preview-mapping/', direct_data_views.preview_mapping, name='preview_mapping'),
    path('mapping-config/', direct_data_views.mapping_config, name='mapping_config'),
    path('clear-workspace/', direct_data_views.clear_workspace, name='clear_workspace'),
    path('clear-all-datasets/', direct_data_views.clear_all_datasets, name='clear_all_datasets'),
    path('deselect-all-columns/', direct_data_views.deselect_all_columns, name='deselect_all_columns'),
    path('set-anchor-column/', direct_data_views.set_anchor_column, name='set_anchor_column'),
    path('toggle-multi-value-column/', direct_data_views.toggle_multi_value_column, name='toggle_multi_value_column'),
    path('toggle-fk-column/', direct_data_views.toggle_fk_column, name='toggle_fk_column'),
    path('configure-fk/', direct_data_views.configure_fk, name='configure_fk'),
    path('update-fk-targets/', direct_data_views.update_fk_targets, name='update_fk_targets'),
    path('update-fk-columns/', direct_data_views.update_fk_columns, name='update_fk_columns'),
    path('save-fk-config/', direct_data_views.save_fk_config, name='save_fk_config'),
    path('remove-fk-config/', direct_data_views.remove_fk_config, name='remove_fk_config'),
    path('close-fk-modal/', direct_data_views.close_fk_modal, name='close_fk_modal'),
    
    # Inline FK Configuration (replacement for modal approach)
    path('toggle-fk-form/', direct_data_views.toggle_fk_form, name='toggle_fk_form'),
    path('hide-fk-form/', direct_data_views.hide_fk_form, name='hide_fk_form'),
    path('update-fk-target-columns/', direct_data_views.update_fk_target_columns, name='update_fk_target_columns'),
    path('save-inline-fk-config/', direct_data_views.save_inline_fk_config, name='save_inline_fk_config'),
    
    path('export-mappings/', direct_data_views.export_mappings, name='export_mappings'),
    path('filter-workspace/', direct_data_views.filter_workspace, name='filter_workspace'),
    path('expand-dataset/', direct_data_views.expand_dataset, name='expand_dataset'),
    
    # Dataset column selection helpers
    path('select-all-dataset-columns/', direct_data_views.select_all_dataset_columns, name='select_all_dataset_columns'),
    path('deselect-all-dataset-columns/', direct_data_views.deselect_all_dataset_columns, name='deselect_all_dataset_columns'),
    
    # Tooltip helpers for HTMX
    path('tooltip/', direct_data_views.tooltip_view, name='tooltip'),
    
    # ==============================================================================
    # CSV Mapping Editor (Step-by-step extraction from direct_data_views)
    # ==============================================================================
    
    # Main CSV Mapping Editor
    path('csv-mapping-editor/', csv_mapping_views.csv_mapping_editor_view, name='csv_mapping_editor'),
    
    # Step 2: Dataset card views (implemented with coordinator)
    path('csv-dataset-card/', csv_mapping_views.CSVDatasetCardView.as_view(), name='csv_dataset_card'),
    path('toggle-csv-dataset/', csv_mapping_views.ToggleDatasetSelectionView.as_view(), name='csv_toggle_dataset_card'),
    path('csv-load-more-rows/', csv_mapping_views.LoadMoreDatasetRowsView.as_view(), name='csv_load_more_dataset_rows'),
    
    # Step 3: Column workspace management URLs (implemented with coordinator)
    path('csv-add-column/', csv_mapping_views.AddColumnToWorkspaceView.as_view(), name='csv_add_column_to_workspace'),
    path('csv-remove-column/', csv_mapping_views.RemoveColumnFromWorkspaceView.as_view(), name='csv_remove_column_from_workspace'),
    path('csv-select-all-dataset-columns/', csv_mapping_views.SelectAllDatasetColumnsView.as_view(), name='csv_select_all_dataset_columns'),
    path('csv-deselect-all-dataset-columns/', csv_mapping_views.DeselectAllDatasetColumnsView.as_view(), name='csv_deselect_all_dataset_columns'),
    
    # Step 4: FK configuration URLs (placeholder for now)
    path('csv-configure-fk/', csv_mapping_views.ConfigureFKRelationshipView.as_view(), name='configure_fk_relationship'),
    
    # Missing URLs that templates reference (now using proper CSV mapping views with coordinator mixins)
    path('csv-clear-all-datasets/', csv_mapping_views.ClearAllDatasetsView.as_view(), name='csv_clear_all_datasets'),
    
    # Mapping persistence endpoints (JSON API)
    path('csv-save-mapping/', saved_mappings_api.SaveMappingView.as_view(), name='csv_save_mapping'),
    path('csv-load-mapping/', saved_mappings_api.LoadMappingView.as_view(), name='csv_load_mapping'),
    path('csv-list-mappings/', saved_mappings_api.ListMappingsView.as_view(), name='csv_list_mappings'),
    path('csv-delete-mapping/', saved_mappings_api.DeleteMappingView.as_view(), name='csv_delete_mapping'),
    
    # Mapping persistence endpoints (HTMX UI)
    path('csv-validate-mapping-name/', saved_mappings_ui.ValidateMappingNameView.as_view(), name='csv_validate_mapping_name'),
    path('csv-update-button-state/', saved_mappings_ui.UpdateButtonStateView.as_view(), name='csv_update_button_state'),
    path('csv-save-mapping-htmx/', saved_mappings_ui.SaveMappingHTMXView.as_view(), name='csv_save_mapping_htmx'),
    path('csv-load-mapping-htmx/', saved_mappings_ui.LoadMappingHTMXView.as_view(), name='csv_load_mapping_htmx'),
    path('csv-delete-mapping-htmx/', saved_mappings_ui.DeleteMappingHTMXView.as_view(), name='csv_delete_mapping_htmx'),
    
    # Step 4: FK Configuration URLs (now using proper CSV mapping views with coordinator mixins)
    path('csv-toggle-fk-form/', csv_mapping_views.ToggleFKFormView.as_view(), name='csv_toggle_fk_form'),
    path('csv-hide-fk-form/', csv_mapping_views.HideFKFormView.as_view(), name='csv_hide_fk_form'),
    path('csv-update-fk-target-columns/', csv_mapping_views.UpdateFKTargetColumnsView.as_view(), name='csv_update_fk_target_columns'),
    path('csv-save-inline-fk-config/', csv_mapping_views.SaveInlineFKConfigView.as_view(), name='csv_save_inline_fk_config'),
    path('csv-remove-fk-config/', csv_mapping_views.RemoveFKConfigView.as_view(), name='remove_fk_config'),
    
    # Column configuration URLs (anchor and multi-value using coordinator mixins)
    path('csv-set-anchor-column/', csv_mapping_views.SetAnchorColumnView.as_view(), name='csv_set_anchor_column'),
    path('csv-toggle-multi-value-column/', csv_mapping_views.ToggleMultiValueColumnView.as_view(), name='csv_toggle_multi_value_column'),
    
    # JSON Export URLs (for mapping configuration serialization)
    path('csv-mapping/export-json/', csv_mapping_views.ExportMappingJSONView.as_view(), name='csv_export_mapping_json'),
    path('csv-mapping/json-content/', csv_mapping_views.GetMappingJSONContentView.as_view(), name='csv_get_mapping_json_content'),
    path('csv-mapping/json-view/', csv_mapping_views.GetMappingJSONViewView.as_view(), name='csv_get_mapping_json_view'),
    
    ]
