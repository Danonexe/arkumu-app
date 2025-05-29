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

# Import UploadSession model and get_user_model
from arkumu.storage.models import UploadSession
from django.contrib.auth import get_user_model

# Django cache
from django.core.cache import cache

logger = logging.getLogger(__name__)


@login_required
def organization_dashboard(request):
    """
    Display a dashboard of all organizations and their buckets.
    """
    try:
        # Single bucket service instance - this is now optimized with singleton pattern
        bucket_service = BucketService()
        
        # Get available organizations (includes both existing and predefined)
        available_organizations = bucket_service.get_available_organizations()
        
        # Check if user wants detailed file counts (optional for performance)
        include_counts = request.GET.get('include_counts', 'false').lower() == 'true'
        
        # Prepare data for the template
        org_data = []
        for org_info in available_organizations:
            org_name = org_info.get('slug')
            org_display_name = org_info.get('name', org_name)
            org_description = org_info.get('description', '')
            exists = org_info.get('exists', False)
            
            org_entry = {
                "slug": org_name,
                "name": org_display_name,
                "description": org_description,
                "exists": exists,
                "bucket": bucket_service.get_organization_bucket(org_name) if exists else None,
                "file_count": 0,
                "folder_count": 0,
                "status": "active" if exists else "available"
            }
            
            # Only get file counts if requested and bucket exists (for performance)
            if include_counts and exists:
                try:
                    bucket_name = bucket_service.get_organization_bucket(org_name)
                    root_items = bucket_service.get_root_level_items(bucket_name)
                    org_entry["file_count"] = sum(1 for item in root_items.get('children', []) 
                                                  if item.get('type') == 'file')
                    org_entry["folder_count"] = sum(1 for item in root_items.get('children', []) 
                                                    if item.get('type') == 'folder')
                except Exception as e:
                    logger.warning(f"Error getting counts for org {org_name}: {str(e)}")
                    # Continue without counts instead of failing
                    org_entry["file_count"] = 0
                    org_entry["folder_count"] = 0
            
            org_data.append(org_entry)
        
        # Sort organizations: existing ones first, then by name
        org_data.sort(key=lambda x: (not x["exists"], x["name"]))
        
        return render(request, "dashboard/organization_dashboard.html", {
            "organizations": org_data,
            "total_orgs": len(org_data),
            "include_counts": include_counts,
            "existing_orgs": len([org for org in org_data if org["exists"]]),
            "available_orgs": len([org for org in org_data if not org["exists"]])
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