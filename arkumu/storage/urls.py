from django.urls import path

from . import views
from .views import direct_upload_views, streaming_upload_views, file_operations_views, dashboard_views

app_name = "storage"

urlpatterns = [
    # Main storage dashboard
    path("", dashboard_views.storage_dashboard, name="storage_dashboard"),
    
    # Upload endpoints
    path("upload/", views.upload_form, name="upload_form"),
    path("upload/process/", views.process_upload, name="process_upload"),
    # path('mark-uploads-complete/', views.mark_uploads_complete, name='mark_uploads_complete'), # Removed - incorrect view name
    path("upload/direct/", views.direct_upload, name="direct_upload"),
    path("upload/success/", views.upload_success, name="upload_success"),
    path('upload/complete/', direct_upload_views.upload_complete, name='upload_complete'),
    
    # New streaming upload endpoints
    path("upload/streaming/", streaming_upload_views.streaming_upload_form, name="streaming_upload_form"),
    path("upload/streaming/api/", streaming_upload_views.streaming_upload_api, name="streaming_upload_api"),
    path("upload/streaming/single/", streaming_upload_views.streaming_upload_single, name="streaming_upload_single"),
    path("file/info/", streaming_upload_views.file_info, name="file_info"),
    
    # Organization-specific views
    path("organizations/", file_operations_views.organization_dashboard, name="organization_dashboard"),
    # Handle organization selection via parameter (for HTMX) - MUST come before the generic pattern
    path("organizations/browse/", file_operations_views.organization_contents, name="organization_contents_browse"),
    path("organizations/<str:organization>/", file_operations_views.organization_contents, name="organization_contents"),
    
    # CSV ingest endpoint
    path("ingest-file/", file_operations_views.ingest_file, name="ingest_file"),
    
    # Database reset endpoint
    path("reset-database/", file_operations_views.reset_database, name="reset_database"),
    
    # Remove presigned URL and multipart upload API endpoints since they're no longer used
    # path("presigned-urls/", views.get_presigned_urls, name="get_presigned_urls"),
    # path("verify-uploads/", views.mark_uploads_complete, name="mark_uploads_complete"),
    # path("multipart/initialize/", views.initialize_multipart_upload, name="initialize_multipart_upload"),
    # path("multipart/get-part-urls/", views.get_part_upload_urls, name="get_part_upload_urls"),
    # path("multipart/complete/", views.complete_multipart_upload, name="complete_multipart_upload"),
    # path("multipart/abort/", views.abort_multipart_upload, name="abort_multipart_upload"),
    # path("multipart/list/", views.list_multipart_uploads, name="list_multipart_uploads"),
    
    # Archivist dashboard
    path("dashboard/", dashboard_views.archivist_dashboard, name="archivist_dashboard"),
    path("dashboard/folder-contents/<str:bucket_type>/<path:folder_path>/", views.load_folder_contents, name="load_folder_contents"),
    
    # File operations
    path("move-to-production/<path:folder_path>/", views.move_to_production, name="move_to_production"),
    path("file-content/<str:bucket_type>/<path:file_path>/", views.file_content, name="file_content"),
    path("delete/<str:bucket_type>/<str:object_type>/<path:object_path>/", views.delete_object, name="delete_object"),
    path("debug/presigned-url/", direct_upload_views.debug_presigned_url, name="debug_presigned_url"),
    path("upload/debug-error/", direct_upload_views.debug_upload_error, name="debug_upload_error"),

    # Add new route for dashboard content partials
    path("dashboard-content/<str:bucket_type>/", views.dashboard_content, name="dashboard_content"),
    
    # Organization bucket viewing with auto-creation
    path("view-organization-bucket/", dashboard_views.view_organization_bucket, name="view_organization_bucket"),
] 