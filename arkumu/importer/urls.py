from django.urls import path
from .views import import_views, ingest_views

app_name = "importer"

urlpatterns = [
    # New ingest data interface
    path("ingest/", ingest_views.ingest_data, name="ingest_data"),
    path("ingest/get-files/", ingest_views.get_organization_files_for_ingest, name="get_organization_files"),
    path("ingest/toggle-file-selection/", ingest_views.toggle_file_selection, name="toggle_file_selection"),
    path("ingest/select-all-files/", ingest_views.select_all_files, name="select_all_files"),
    path("ingest/deselect-all-files/", ingest_views.deselect_all_files, name="deselect_all_files"),
    path("ingest/toggle-folder/", ingest_views.toggle_folder, name="toggle_folder"),
    path("ingest/list-mappings-dropdown/", ingest_views.list_mappings_dropdown, name="list_mappings_dropdown"),
    path("ingest/navbar-controls/", ingest_views.navbar_controls, name="navbar_controls"),
    path("ingest/execution-status/", ingest_views.execution_status, name="execution_status"),
    path("ingest/analyze-mapping/", ingest_views.analyze_mapping, name="analyze_mapping"),
    path("ingest/correlation-analysis/", ingest_views.correlation_analysis, name="correlation_analysis"),
    path("ingest/run-validation/", ingest_views.run_pre_execution_validation, name="run_validation"),
    path("ingest/validation-results/", ingest_views.validation_results_display, name="validation_results"),
    # Organization changes now handled in main ingest_data view
    
    # CSV ingest endpoint (existing)
    path("ingest-file/", import_views.ingest_file, name="ingest_file"),
    
    # Directory import endpoint
    path("start-directory-import/", import_views.start_directory_import, name="start_directory_import"),
    
    # Task status polling endpoint  
    path("task-status/<str:task_id>/", import_views.task_status_view, name="task_status"),
    
    # Database management endpoints (development utilities)
    path("reset-database/", import_views.reset_database, name="reset_database"),
    path("clear-upload-sessions/", import_views.clear_upload_sessions, name="clear_upload_sessions"),
    path("clear-ingest-sessions/", import_views.clear_ingest_sessions, name="clear_ingest_sessions"),
] 