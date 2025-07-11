import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views import View
from arkumu.storage.services.bucket_service import BucketService
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from arkumu.users.mixins import GeneralLoginRequiredMixin, general_login_required
from arkumu.common.mixins.base_coordinator import BaseCoordinatorMixin

logger = logging.getLogger(__name__)


@general_login_required
def storage_dashboard(request):
    """
    Main storage dashboard - redirects to the archivist dashboard 
    which is the primary interface for organization bucket management.
    """
    from django.shortcuts import redirect
    return redirect('storage:archivist_dashboard')


class ArchivistDashboardView(GeneralLoginRequiredMixin, BaseCoordinatorMixin, View):
    """
    Dashboard for archivists to manage organization buckets.
    
    Now uses BaseCoordinatorMixin for cross-view session persistence with 
    CSV mapping editor and Metadata Ingestion.
    """
    
    def get(self, request):
        """Handle GET requests for the archivist dashboard."""
        logger.info(f"Archivist dashboard view called. Request method: {request.method}, User: {request.user}")
        try:
            logger.info("Attempting to initialize BucketService...")
            bucket_service = BucketService()
            logger.info("BucketService initialized.")
            
            # Handle organization parameter from URL (support both 'org' and 'organization')
            org_param = request.GET.get('org') or request.GET.get('organization')
            if org_param:
                # Set organization using BaseCoordinatorMixin
                self.set_current_organization(request, org_param)
            
            # Get current organization using BaseCoordinatorMixin
            current_org = self.get_current_organization(request)
            selected_org_slug = current_org['code'] if current_org else None
            
            logger.info("Attempting to get available organizations...")
            # Get organizations from database instead of hardcoded bucket service
            from arkumu.users.models import Organization
            organizations = list(Organization.objects.filter(is_active=True))
            logger.info(f"Got {len(organizations)} available organizations from database.")
            
            organization_count = len(organizations)
            
            total_files_display = "N/A"
            storage_used_display = "N/A"
            
            organization_structure = None
            selected_org_data = None

            if selected_org_slug:
                logger.info(f"Selected organization slug: {selected_org_slug}")
                try:
                    selected_org_data = next((org for org in organizations if org.code == selected_org_slug), None)

                    if selected_org_data:
                        logger.info(f"Fetching structure for existing org: {selected_org_slug}")
                        bucket_name = bucket_service.get_organization_bucket(selected_org_slug)
                        organization_structure = bucket_service.get_root_level_items(bucket_name)
                        logger.info(f"Structure fetched for {selected_org_slug}")
                    else:
                        logger.warning(f"Requested organization '{selected_org_slug}' not found in available organizations.")

                except Exception as e:
                    logger.error(f"Error loading organization structure for {selected_org_slug}: {str(e)}")
            
            logger.info("Preparing to render archivist_dashboard.html")
            return render(request, "dashboard/archivist_dashboard.html", {
                "organizations": organizations,
                "organization_count": organization_count,
                "total_files_display": total_files_display,
                "storage_used_display": storage_used_display,
                "organization_structure": organization_structure,
                "selected_org_data": selected_org_data, 
                "selected_org_slug": selected_org_slug
            })
        except Exception as e:
            logger.exception(f"Outer exception in archivist_dashboard: {str(e)}")
            return render(request, "dashboard/archivist_dashboard.html", {
                "error": f"An error occurred while loading the dashboard: {str(e)}",
                "organizations": [],
                "organization_count": 0,
                "total_files_display": "Error",
                "storage_used_display": "Error",
                "selected_org_slug": selected_org_slug if 'selected_org_slug' in locals() else request.GET.get('org') 
            })


@general_login_required
def archivist_dashboard(request):
    """
    Function-based wrapper for ArchivistDashboardView (for URL compatibility).
    """
    view = ArchivistDashboardView()
    return view.get(request)


@general_login_required
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


@general_login_required
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


@require_http_methods(["POST"])
@general_login_required
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