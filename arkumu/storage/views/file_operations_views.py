import logging
import os
import mimetypes
import tempfile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse

from arkumu.storage.services.bucket_service import BucketService
from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy

logger = logging.getLogger(__name__)


@login_required
def organization_dashboard(request):
    """
    Display a dashboard of all organizations and their buckets.
    """
    try:
        bucket_service = BucketService()
        
        # Get all organizations
        organizations = bucket_service.get_organizations()
        
        # Prepare data for the template
        org_data = []
        for org_name in organizations:
            bucket_name = bucket_service.get_organization_bucket(org_name)
            
            # Get root level items for this organization's bucket
            try:
                root_items = bucket_service.get_root_level_items(bucket_name)
                file_count = sum(1 for item in root_items.get('children', []) 
                                if item.get('type') == 'file')
                folder_count = sum(1 for item in root_items.get('children', []) 
                                  if item.get('type') == 'folder')
            except Exception as e:
                logger.error(f"Error getting root items for org {org_name}: {str(e)}")
                root_items = {"children": []}
                file_count = 0
                folder_count = 0
            
            org_data.append({
                "name": org_name,
                "bucket": bucket_name,
                "file_count": file_count,
                "folder_count": folder_count
            })
        
        return render(request, "dashboard/organization_dashboard.html", {
            "organizations": org_data,
            "total_orgs": len(org_data)
        })
        
    except Exception as e:
        error_message = f"Error loading organization dashboard: {str(e)}"
        logger.exception(error_message)
        messages.error(request, error_message)
        return redirect("home")


@login_required
def organization_contents(request, organization=None):
    """
    Display the contents of an organization's bucket.
    Returns partial template for HTMX requests.
    """
    try:
        # Check if this is the browse URL (always get from query parameter)
        is_browse_url = request.resolver_match.url_name == 'organization_contents_browse'
        
        if is_browse_url:
            # For browse URL, always get organization from query parameter
            organization = request.GET.get('organization') or request.POST.get('organization')
        elif not organization:
            # For regular URL, get from URL parameter or form parameter
            organization = request.GET.get('organization') or request.POST.get('organization')
        
        if not organization:
            if request.headers.get('HX-Request') == 'true':
                return render(request, "dashboard/organization_files_empty.html")
            return redirect("storage:organization_dashboard")
        
        bucket_service = BucketService()
        
        # Ensure the organization bucket exists first
        bucket_result = bucket_service.ensure_organization_bucket_exists(organization)
        if not bucket_result.get('success', False):
            error_message = f"Failed to create/access bucket for {organization}: {bucket_result.get('error', 'Unknown error')}"
            if request.headers.get('HX-Request') == 'true':
                return render(request, "dashboard/organization_files_error.html", {
                    "error": error_message,
                    "organization": organization
                })
            messages.error(request, error_message)
            return redirect("storage:organization_dashboard")
        
        # Get the bucket for this organization
        bucket_name = bucket_service.get_organization_bucket(organization)
        
        # Get optional prefix from query params
        prefix = request.GET.get('prefix', '')
        
        # Get contents of the bucket with the given prefix
        contents = bucket_service.list_bucket_contents(bucket_name, prefix)
        
        # Check if HTMX request for partial content
        is_htmx_request = request.headers.get('HX-Request') == 'true'
        
        # Debug logging
        logger.info(f"Organization: {organization}")
        logger.info(f"Is browse URL: {is_browse_url}")
        
        if is_htmx_request or is_browse_url:
            # Return partial template for HTMX
            logger.info("Returning partial template for HTMX or browse URL")
            
            # If we have a prefix (navigating into subfolders), use the organization folder contents template
            # to avoid duplicating the header. Otherwise, use the full organization files template.
            if prefix:
                # Transform contents to match the organization_folder_contents_partial.html expected format
                structure = {
                    "children": contents
                }
                return render(request, "dashboard/organization_folder_contents_partial.html", {
                    "structure": structure,
                    "organization": organization,
                    "bucket_type": f"org-{organization}"
                })
            else:
                # Initial load - show full template with header
                return render(request, "dashboard/organization_files_partial.html", {
                    "organization": organization,
                    "bucket_name": bucket_name,
                    "contents": contents,
                    "prefix": prefix
                })
        
        # Prepare breadcrumbs for navigation
        breadcrumbs = []
        if prefix:
            parts = prefix.strip('/').split('/')
            current_path = ''
            for i, part in enumerate(parts):
                current_path += part + '/'
                breadcrumbs.append({
                    'name': part,
                    'path': current_path,
                    'is_last': i == len(parts) - 1
                })
        
        return render(request, "dashboard/organization_contents.html", {
            "organization": organization,
            "bucket_name": bucket_name,
            "contents": contents,
            "prefix": prefix,
            "breadcrumbs": breadcrumbs
        })
        
    except Exception as e:
        error_message = f"Error loading organization contents: {str(e)}"
        logger.exception(error_message)
        
        # Check if HTMX request
        is_htmx_request = request.headers.get('HX-Request') == 'true'
        
        if is_htmx_request:
            return render(request, "dashboard/organization_files_error.html", {
                "error": error_message,
                "organization": organization
            })
        
        messages.error(request, error_message)
        return redirect("storage:organization_dashboard")


@login_required
def move_to_production(request, folder_path):
    """
    Move a folder from the ingest bucket to the production bucket.
    
    This operation copies all files from the specified folder in the ingest bucket
    to the production bucket, maintaining the same folder structure.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})
    
    try:
        bucket_service = BucketService()
        
        # Add debug logging to trace the copying process
        logger.info(f"Preparing to move folder '{folder_path}' to production")
        
        # Trace the ingest bucket contents before copying
        ingest_contents = bucket_service.list_bucket_contents(bucket_service.ingest_bucket, folder_path)
        logger.info(f"Source folder contents in ingest bucket ({len(ingest_contents)} items):")
        for item in ingest_contents:
            logger.info(f"  {item.get('path')} - {'folder' if item.get('is_dir', False) else 'file'}")
        
        # Perform the direct move to production
        result = bucket_service.direct_move_to_production(folder_path)
        
        # Check the production bucket contents after copying
        if result.get("success", False):
            # Wait a moment for S3 consistency (especially important for MinIO)
            import time
            time.sleep(0.5)  # 500ms delay
            
            # Verify the production bucket contents
            production_contents = bucket_service.list_bucket_contents(bucket_service.production_bucket, folder_path)
            logger.info(f"Production bucket contents after copy ({len(production_contents)} items):")
            for item in production_contents:
                logger.info(f"  {item.get('path')} - {'folder' if item.get('is_dir', False) else 'file'}")
            
            # Trigger the ingestion pipeline for the copied collection
            try:
                # Import the task function
                # from lacos.ingest.tasks import process_s3_prefix
                
                # Ensure folder_path ends with a slash for proper prefix handling
                prefix = folder_path.rstrip('/') + '/'
                
                # Launch the ingestion task
                # task_result = process_s3_prefix(
                #     bucket=bucket_service.production_bucket,
                #     prefix=prefix
                # )
                
                # logger.info(f"Triggered ingestion pipeline for {bucket_service.production_bucket}/{prefix}, task: {task_result}")
                logger.info(f"Would trigger ingestion pipeline for {bucket_service.production_bucket}/{prefix}")
                
                # Add a message about ingestion being triggered
                messages.info(request, f"Moved to production successfully: '{folder_path}'")
                
            except Exception as e:
                # Log the error but don't fail the move operation
                logger.error(f"Error triggering ingestion for {folder_path}: {str(e)}")
                messages.warning(request, f"Moved to production successfully, but failed to trigger ingestion: {str(e)}")
        
        # Check if this is an HTMX request
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if result.get("success", False):
            success_message = f"Successfully moved folder '{folder_path}' to production"
            logger.info(success_message)
            messages.success(request, success_message)
            
            # If HTMX request, return the updated production bucket contents
            if is_htmx:
                try:
                    # Add debug logging
                    logger.info(f"Getting updated production structure after move")
                    
                    # Get updated production bucket structure
                    production_structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
                    
                    # Log the structure for debugging
                    logger.info(f"Production structure children count: {len(production_structure.get('children', []))}")
                    
                    # Return the complete rendered partial for the entire production bucket
                    response = render(request, 'dashboard/folder_structure_partial.html', {
                        'structure': production_structure,
                        'bucket_type': 'production'
                    })
                    
                    # Add a cache-busting header to force browser refresh
                    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    response['Pragma'] = 'no-cache'
                    response['Expires'] = '0'
                    
                    return response
                    
                except Exception as e:
                    logger.exception(f"Error refreshing production structure: {str(e)}")
                    # Fall back to redirect if there's an error updating the UI
                    redirect_url = reverse('storage:archivist_dashboard') + f"?message={success_message}"
                    return redirect(redirect_url)
            
            # Regular request - redirect to dashboard with success message
            redirect_url = reverse('storage:archivist_dashboard') + f"?message={success_message}"
            return redirect(redirect_url)
        else:
            error_message = f"Failed to move folder: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            # If HTMX request, return error message
            if is_htmx:
                return HttpResponse(error_message, status=400)
            
            # Regular request - redirect to dashboard
            return redirect(reverse('storage:archivist_dashboard'))
            
    except Exception as e:
        error_message = f"Error moving folder to production: {str(e)}"
        logger.exception(error_message)
        messages.error(request, error_message)
        
        # If HTMX request, return error message
        if request.headers.get('HX-Request') == 'true':
            return render(request, "partials/toast_notification.html", {
                "message": error_message,
                "type": "error"
            })
        
        # Regular request - redirect to dashboard
        return redirect(reverse('storage:archivist_dashboard'))


@login_required
def file_content(request, bucket_type, file_path):
    """
    Retrieve and display the content of a file from a bucket.
    
    This view serves the content of a file directly to the browser.
    For binary files (images, etc.), it streams the content with the
    appropriate content type. For text files, it renders the content
    in a readable format.
    """
    try:
        bucket_service = BucketService()
        
        # Determine which bucket to use
        bucket = bucket_service.ingest_bucket
        if bucket_type == "production":
            bucket = bucket_service.production_bucket
        elif bucket_type.startswith("org-"):
            # Handle organization-specific buckets
            org_name = bucket_type[4:]  # Remove 'org-' prefix
            bucket = bucket_service.get_organization_bucket(org_name)
        
        # Get file content and metadata
        result = bucket_service.get_file_content(bucket, file_path)
        
        if result.get("success", False):
            content_type = result.get("content_type", "application/octet-stream")
            content = result.get("content")
            
            # Return the file content with the appropriate content type
            response = HttpResponse(content, content_type=content_type)
            
            # Add content disposition header for download if requested
            if request.GET.get("download") == "true":
                filename = file_path.split("/")[-1]
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                
            return response
        else:
            error_message = f"Failed to retrieve file: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            return HttpResponse(error_message, status=404)
            
    except Exception as e:
        error_message = f"Error retrieving file content: {str(e)}"
        logger.exception(error_message)
        return HttpResponse(error_message, status=500)


@login_required
def delete_object(request, bucket_type, object_type, object_path):
    """
    Delete a file or folder from a bucket.
    
    This operation permanently deletes the specified object from the bucket.
    If the object is a folder, all contents will also be deleted.
    
    Args:
        bucket_type: "ingest", "production", or "org-{organization_name}"
        object_type: "file" or "folder"
        object_path: The path to the object within the bucket
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})
    
    try:
        bucket_service = BucketService()
        
        # Determine which bucket to use
        bucket_name = bucket_service.ingest_bucket
        if bucket_type == "production":
            bucket_name = bucket_service.production_bucket
        elif bucket_type.startswith("org-"):
            # Handle organization-specific buckets
            org_name = bucket_type[4:]  # Remove 'org-' prefix
            bucket_name = bucket_service.get_organization_bucket(org_name)
        
        # Delete the object based on its type
        if object_type == "folder":
            result = bucket_service.delete_folder(bucket_name, object_path)
        else:  # file
            result = bucket_service.delete_file(bucket_name, object_path)
        
        if result.get("success", False):
            success_message = f"Successfully deleted {object_type} '{object_path}'"
            logger.info(success_message)
            
            if request.headers.get('HX-Request') == 'true':
                # For HTMX requests, return a toast notification
                # The element will be removed from the DOM by hx-swap="outerHTML"
                # and the toast will show the success message
                return render(request, "partials/toast_notification.html", {
                    "message": success_message,
                    "type": "success"
                })
            
            # Only add Django messages for non-HTMX requests
            messages.success(request, success_message)
            return JsonResponse({"success": True, "message": success_message})
        else:
            error_message = f"Failed to delete {object_type}: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            
            if request.headers.get('HX-Request') == 'true':
                return render(request, "partials/toast_notification.html", {
                    "message": error_message,
                    "type": "error"
                })
                
            # Only add Django messages for non-HTMX requests
            messages.error(request, error_message)
            return JsonResponse({"success": False, "error": error_message})
            
    except Exception as e:
        error_message = f"Error deleting {object_type}: {str(e)}"
        logger.exception(error_message)
        
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse(error_message, status=500)
            
        # Only add Django messages for non-HTMX requests
        messages.error(request, error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
def ingest_file(request):
    """
    Ingest a CSV file using the ImportWorkflowService
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get parameters from POST data
        organization_slug = request.POST.get('organization')
        file_path = request.POST.get('file_path')
        
        if not organization_slug:
            return JsonResponse({'error': 'Organization parameter is required'}, status=400)
        
        if not file_path:
            return JsonResponse({'error': 'File path parameter is required'}, status=400)
        
        # Validate organization against predefined organizations
        bucket_service = BucketService()
        valid_orgs = [org['slug'] for org in bucket_service.PREDEFINED_ORGANIZATIONS]
        if organization_slug not in valid_orgs:
            return JsonResponse({'error': f'Invalid organization: {organization_slug}'}, status=400)
        
        # Get bucket name for organization
        bucket_name = bucket_service.get_organization_bucket(organization_slug)
        
        # Check if it's a CSV file
        if not file_path.lower().endswith('.csv'):
            return JsonResponse({'error': 'Only CSV files can be ingested'}, status=400)
        
        # Download file to temporary location
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.csv', delete=False) as temp_file:
            temp_path = temp_file.name
            
        try:
            # Download from S3 using bucket service
            bucket_service.s3_client.download_file(bucket_name, file_path, temp_path)
            
            # Extract dataset name from file path
            dataset_name = os.path.splitext(os.path.basename(file_path))[0]
            
            logger.info(f"Starting ingest of {file_path} as dataset '{dataset_name}' for organization {organization_slug}")
            
            # Import using ImportWorkflowService with smart updater to prevent duplicates
            result = ImportWorkflowService.import_csv(
                csv_path=temp_path,
                dataset_name=dataset_name,
                institution=organization_slug.upper(),
                base_uri="http://arkumu.org/data",
                delimiter=';',
                has_quoted_fields=True,
                link_row_cells=True,
                link_to_first_column=False,
                use_smart_updater=True,
                update_strategy=UpdateStrategy.SKIP_EXISTING
            )
            
            # Clean up temp file
            os.unlink(temp_path)
            
            # Return HTMX-friendly toast notification for success
            if request.headers.get('HX-Request') == 'true':
                return render(request, "partials/toast_notification.html", {
                    "message": f"Successfully ingested {dataset_name} from {file_path}",
                    "type": "success"
                })
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully ingested {dataset_name} from {file_path}',
                'file_path': file_path,
                'dataset_name': dataset_name,
                'stats': result
            })
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        
    except Exception as e:
        error_message = f'Failed to ingest {file_path}: {str(e)}'
        logger.error(f"Ingest error for {file_path}: {e}", exc_info=True)
        
        # Check if it's a database integrity error from concurrent imports
        if 'ForeignKeyViolation' in str(e) or 'IntegrityError' in str(e):
            error_message = f'Database conflict while ingesting {file_path}. This may be due to concurrent imports of the same data. Please try again.'
        
        # Return HTMX-friendly toast notification for error
        if request.headers.get('HX-Request') == 'true':
            return render(request, "partials/toast_notification.html", {
                "message": error_message,
                "type": "error"
            })
        
        return JsonResponse({
            'error': error_message,
            'file_path': file_path,
            'dataset_name': dataset_name if 'dataset_name' in locals() else 'unknown'
        }, status=500)


@login_required
def reset_database(request):
    """
    Reset the database by deleting all Resource and Triple records.
    This is useful for development and testing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from arkumu.metadata.models.resource import Resource
        from arkumu.metadata.models.triples import Triple
        from django.db import transaction
        
        with transaction.atomic():
            # Delete all triples first (due to foreign key constraints)
            triple_count = Triple.objects.count()
            Triple.objects.all().delete()
            
            # Delete all resources
            resource_count = Resource.objects.count()
            Resource.objects.all().delete()
            
        logger.info(f"Database reset completed: deleted {triple_count} triples and {resource_count} resources")
        
        # Return HTMX-friendly response
        if request.headers.get('HX-Request') == 'true':
            from django.template.loader import render_to_string
            success_html = f"""
            <div class="alert alert-success">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                    <h3 class="font-bold">Database Reset Successful!</h3>
                    <div class="text-xs">Deleted {triple_count} triples and {resource_count} resources</div>
                </div>
            </div>
            """
            return HttpResponse(success_html)
        
        return JsonResponse({
            'success': True,
            'message': f'Database reset successful! Deleted {triple_count} triples and {resource_count} resources.',
            'triples_deleted': triple_count,
            'resources_deleted': resource_count
        })
        
    except Exception as e:
        error_message = f'Failed to reset database: {str(e)}'
        logger.error(f"Database reset error: {e}", exc_info=True)
        
        # Return HTMX-friendly error response
        if request.headers.get('HX-Request') == 'true':
            error_html = f"""
            <div class="alert alert-error">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
                <div>
                    <h3 class="font-bold">Database Reset Failed!</h3>
                    <div class="text-xs">{error_message}</div>
                </div>
            </div>
            """
            return HttpResponse(error_html, status=500)
        
        return JsonResponse({
            'error': error_message
        }, status=500) 