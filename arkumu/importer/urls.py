from django.urls import path
from .views import import_views

app_name = "importer"

urlpatterns = [
    # CSV ingest endpoint
    path("ingest-file/", import_views.ingest_file, name="ingest_file"),
    
    # Task status polling endpoint  
    path("task-status/<str:task_id>/", import_views.task_status_view, name="task_status"),
    
    # Database reset endpoint (development utility)
    path("reset-database/", import_views.reset_database, name="reset_database"),
] 