import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from arkumu.storage.services.bucket_service import BucketService
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

@login_required
def storage_dashboard(request):
    """
    Main storage dashboard - redirects to the archivist dashboard 
    which is the primary interface for organization bucket management.
    """
    from django.shortcuts import redirect
    return redirect('storage:archivist_dashboard')

@login_required
def archivist_dashboard(request):
    """
    Dashboard for archivists to manage organization buckets.
    """
    try:
        bucket_service = BucketService()
        
        # Get available organizations (existing and predefined)
        organizations = bucket_service.get_available_organizations()
        
        # Get organization count and file statistics
        organization_count = len([org for org in organizations if org.get('exists', False)])
        total_files = 0
        storage_used = "0 MB"  # TODO: Calculate actual storage usage
        
        # Try to get file counts from existing organization buckets
        for org in organizations:
            if org.get('exists', False):
                try:
                    bucket_name = bucket_service.get_organization_bucket(org['slug'])
                    root_items = bucket_service.get_root_level_items(bucket_name)
                    org_files = sum(1 for item in root_items.get('children', []) if item.get('type') == 'file')
                    total_files += org_files
                except Exception as e:
                    logger.warning(f"Error counting files for organization {org['slug']}: {str(e)}")
        
        # Get organization structure if a specific org is requested
        organization_structure = None
        selected_org = request.GET.get('org')
        if selected_org:
            try:
                # Ensure the organization bucket exists
                result = bucket_service.ensure_organization_bucket_exists(selected_org)
                if result['success']:
                    bucket_name = result['bucket_name']
                    organization_structure = bucket_service.get_root_level_items(bucket_name)
                else:
                    logger.error(f"Failed to ensure bucket for org {selected_org}: {result.get('error')}")
            except Exception as e:
                logger.error(f"Error loading organization structure for {selected_org}: {str(e)}")
        
        return render(request, "dashboard/archivist_dashboard.html", {
            "organizations": organizations,
            "organization_count": organization_count,
            "total_files": total_files,
            "storage_used": storage_used,
            "organization_structure": organization_structure,
            "selected_org": selected_org
        })
    except Exception as e:
        logger.exception(f"Error loading archivist dashboard: {str(e)}")
        return render(request, "dashboard/archivist_dashboard.html", {
            "error": str(e),
            "organizations": [],
            "organization_count": 0,
            "total_files": 0,
            "storage_used": "0 MB"
        })

@login_required
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load contents of a specific folder when expanded.
    """
    bucket_service = BucketService()
    bucket = bucket_service.ingest_bucket if bucket_type == 'ingest' else bucket_service.production_bucket
    
    try:
        # Clean up the folder path to handle double slashes
        folder_path = folder_path.replace('//', '/')
        logger.info(f"Loading folder contents for {bucket_type} bucket, path: {folder_path}")
        
        # Get folder contents
        folder_contents = bucket_service.get_folder_contents(bucket, folder_path)
        logger.info(f"Folder contents for {folder_path}: {folder_contents}")
        
    except Exception as e:
        logger.error(f"Error loading folder contents for {folder_path}: {str(e)}")
        # Return empty list on error
        folder_contents = []
    
    return render(
        request,
        "dashboard/folder_contents_partial.html",
        {
            "folder_contents": folder_contents,
            "bucket_type": bucket_type,
            "folder_path": folder_path,
        },
    )

@login_required
def dashboard_content(request, bucket_type):
    """
    Return only the structure content for a specific bucket type.
    This is used for AJAX/HTMX refreshes of just one section of the dashboard.
    
    Args:
        bucket_type (str): Either "ingest" or "production"
        
    Returns:
        Rendered partial template with the requested bucket structure
    """
    try:
        bucket_service = BucketService()
        
        if bucket_type == "ingest":
            structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket)
        elif bucket_type == "production":
            structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
        else:
            return HttpResponse("Invalid bucket type", status=400)
            
        logger.info(f"Refreshing {bucket_type} structure with {len(structure.get('children', []))} items")
        
        # Render just the folder structure partial
        return render(
            request,
            "dashboard/folder_structure_partial.html",
            {"structure": structure, "bucket_type": bucket_type}
        )
    except Exception as e:
        logger.exception(f"Error loading dashboard content for {bucket_type}: {str(e)}")
        return HttpResponse(f"Error: {str(e)}", status=500)

@login_required
@require_http_methods(["POST"])
def view_organization_bucket(request):
    """
    Handle organization bucket viewing, creating the bucket if it doesn't exist.
    """
    try:
        organization = request.POST.get('organization')
        if not organization:
            return JsonResponse({
                "success": False,
                "error": "Organization parameter is required"
            }, status=400)
        
        bucket_service = BucketService()
        
        # Ensure the organization bucket exists
        result = bucket_service.ensure_organization_bucket_exists(organization)
        
        if result['success']:
            # Get the bucket structure
            bucket_name = result['bucket_name']
            try:
                organization_structure = bucket_service.get_root_level_items(bucket_name)
                
                # Return the HTML structure for the organization bucket
                from django.template.loader import render_to_string
                html_content = render_to_string(
                    "dashboard/folder_structure_partial.html",
                    {
                        "structure": organization_structure,
                        "bucket_type": "organization"
                    }
                )
                
                return JsonResponse({
                    "success": True,
                    "bucket_name": bucket_name,
                    "organization": organization,
                    "html_content": html_content,
                    "message": result.get('message', f"Organization bucket '{bucket_name}' is ready"),
                    "redirect_url": f"/storage/organizations/{organization}/"
                })
                
            except Exception as e:
                logger.error(f"Error getting organization structure: {str(e)}")
                return JsonResponse({
                    "success": False,
                    "error": f"Bucket created but error loading contents: {str(e)}"
                }, status=500)
        else:
            return JsonResponse({
                "success": False,
                "error": result.get('error', 'Unknown error creating organization bucket')
            }, status=500)
            
    except Exception as e:
        logger.exception(f"Error in view_organization_bucket: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500) 