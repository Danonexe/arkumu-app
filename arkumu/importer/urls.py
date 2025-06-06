from django.urls import path
from .views import import_views

app_name = "importer"

urlpatterns = [
    # CSV ingest endpoint
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