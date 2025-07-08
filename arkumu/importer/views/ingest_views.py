"""
Views for the new ingest data interface
"""
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views import View
from arkumu.users.mixins import GeneralLoginRequiredMixin, general_login_required
from arkumu.users.models import Organization
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.importer.mixins.ingest_coordinator import IngestCoordinatorMixin

logger = logging.getLogger(__name__)

# Session storage for selected files
SELECTED_FILES_SESSION_KEY = 'ingest_selected_files'


class IngestDataView(GeneralLoginRequiredMixin, OrganizationMixin, IngestCoordinatorMixin, View):
    """
    Main view for the new ingest data interface with three-pane layout
    
    Uses mixins in the same pattern as CSV mapping:
    - OrganizationMixin: Organization discovery and management
    - IngestCoordinatorMixin: Coordinating file selection and mapping
    """
    template_name = 'importer/ingest_data.html'
    
    def get(self, request):
        """Handle GET requests for the ingest data interface"""
        # Get organization context using OrganizationMixin (same as CSV mapping)
        org_context = self.get_organization_context(request)
        organization_id = org_context['organization_id']
        
        # Handle case where no valid organization is provided
        if not org_context['organization_exists']:
            # Clear any existing organization state
            if hasattr(self, 'clear_current_organization'):
                self.clear_current_organization(request)
            
            # Return template with no organization selected state
            context = {
                **org_context,
                'selected_files': [],
                'selected_mapping': None,
                'available_mappings': [],
                'page_title': 'Metadata Ingestion'
            }
            
            # Handle HTMX requests
            if request.headers.get('HX-Request'):
                return render(request, 'importer/partials/main_ingest_content.html', context)
            return render(request, self.template_name, context)
        
        # Organization exists - set it as current if it's different
        current_org = None
        if hasattr(self, 'get_current_organization'):
            current_org = self.get_current_organization(request)
        
        if not current_org or current_org['code'] != organization_id:
            # Organization changed - handle the change
            if hasattr(self, 'handle_organization_change'):
                self.handle_organization_change(request, organization_id)
        
        # Get ingest-specific context using IngestCoordinatorMixin
        ingest_context = self.get_ingest_context(request)
        
        # Merge contexts - org_context takes precedence for organization data
        context = {
            **org_context,  # organization_id, organizations, organization_exists
            **ingest_context,  # selected_files, mapping data, file browser data, etc.
            'page_title': 'Metadata Ingestion'
        }
        
        # Handle HTMX requests - return just the main content
        if request.headers.get('HX-Request'):
            # Return main content partial for organization changes
            return render(request, 'importer/partials/main_ingest_content.html', context)
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Handle POST requests for HTMX actions"""
        logger.info(f"POST request received. Headers: {dict(request.headers)}")
        logger.info(f"POST data: {dict(request.POST)}")
        logger.info(f"Is HTMX request: {request.headers.get('HX-Request')}")
        
        # Get organization context
        org_context = self.get_organization_context(request)
        organization_id = org_context.get('organization_id')
        
        # Handle load_mapping action
        if request.POST.get('action') == 'load_mapping':
            mapping_id = request.POST.get('mapping_id')
            logger.info(f"Loading mapping details: mapping_id={mapping_id}, organization_id={organization_id}")
            
            # Get organization object first
            from arkumu.users.models import Organization
            organization = None
            if organization_id:
                try:
                    # Handle both numeric ID and code
                    try:
                        organization = Organization.objects.get(id=int(organization_id))
                    except (ValueError, Organization.DoesNotExist):
                        organization = Organization.objects.get(code=organization_id)
                except Organization.DoesNotExist:
                    logger.error(f"Organization not found: {organization_id}")
            
            if mapping_id and organization:
                # Initialize ingestion context
                context_key = f'ingestion_context_{organization.id}'
                ingestion_context = request.session.get(context_key, {})
                
                # Get mapping details
                try:
                    from arkumu.metadata.models import Mapping
                    selected_mapping = Mapping.objects.get(
                        id=mapping_id,
                        organization_id=organization.code  # Use organization code for mapping lookup
                    )
                    
                    # Store selected mapping in ingestion context
                    ingestion_context['selected_mapping_id'] = mapping_id
                    ingestion_context['selected_mapping_name'] = selected_mapping.name
                    ingestion_context['organization_id'] = organization.id
                    ingestion_context['organization_code'] = organization.code
                    
                    # Also store in legacy session key for backward compatibility
                    request.session[f'selected_mapping_{organization.id}'] = mapping_id
                    
                    # Save ingestion context
                    request.session[context_key] = ingestion_context
                    request.session.modified = True
                    
                    context = {
                        'selected_mapping': selected_mapping,
                        'organization_id': organization.id,
                        'organization_code': organization.code,
                        'ingestion_context': ingestion_context
                    }
                    logger.info(f"Successfully loaded mapping: {selected_mapping.name}")
                except Mapping.DoesNotExist:
                    logger.warning(f"Mapping {mapping_id} not found for organization {organization.code}")
                    # Clear mapping from ingestion context
                    ingestion_context.pop('selected_mapping_id', None)
                    ingestion_context.pop('selected_mapping_name', None)
                    request.session[context_key] = ingestion_context
                    
                    # Clear legacy session key
                    request.session.pop(f'selected_mapping_{organization.id}', None)
                    request.session.modified = True
                    
                    context = {
                        'selected_mapping': None,
                        'organization_id': organization.id,
                        'organization_code': organization.code,
                        'ingestion_context': ingestion_context
                    }
            else:
                logger.warning(f"Missing mapping_id or organization: mapping_id={mapping_id}, organization={organization}")
                # Clear any previously stored mapping
                if organization:
                    context_key = f'ingestion_context_{organization.id}'
                    ingestion_context = request.session.get(context_key, {})
                    ingestion_context.pop('selected_mapping_id', None)
                    ingestion_context.pop('selected_mapping_name', None)
                    request.session[context_key] = ingestion_context
                    request.session.pop(f'selected_mapping_{organization.id}', None)
                    request.session.modified = True
                    
                context = {
                    'selected_mapping': None,
                    'organization_id': organization.id if organization else organization_id,
                    'organization_code': organization.code if organization else None,
                    'ingestion_context': ingestion_context if organization else {}
                }
            
            logger.info(f"Returning navbar_mapping_controls.html template with context: {list(context.keys())}")
            response = render(request, 'importer/partials/navbar_mapping_controls.html', context)
            # Trigger execution status update
            response['HX-Trigger'] = 'mappingSelected'
            return response
        
        # Check if it's an HTMX request but no action or unknown action
        if request.headers.get('HX-Request'):
            logger.warning(f"HTMX request but no valid action. Action: {request.POST.get('action')}")
            # Return empty response for unknown HTMX actions
            return HttpResponse("")
        
        # For non-HTMX POST requests, this might be causing the full page reload
        logger.warning("Non-HTMX POST request received - this might cause full page reload!")
        return HttpResponse("Invalid action", status=400)


@general_login_required
def ingest_data(request):
    """
    Function-based wrapper for IngestDataView (for URL compatibility)
    """
    view = IngestDataView()
    if request.method == 'POST':
        return view.post(request)
    return view.get(request)


@general_login_required
def get_organization_files_for_ingest(request):
    """
    HTMX endpoint to get organization files with checkboxes for selection
    """
    # Handle both GET (organization change) and POST (file selection toggle)
    if request.method == 'POST':
        organization_param = request.POST.get('organization')
        file_key = request.POST.get('file_key')
        toggle_selection = request.POST.get('toggle_selection')
        
        # Toggle file selection if requested
        if toggle_selection and file_key:
            selected_files = set(request.session.get(SELECTED_FILES_SESSION_KEY, []))
            if file_key in selected_files:
                selected_files.remove(file_key)
            else:
                selected_files.add(file_key)
            request.session[SELECTED_FILES_SESSION_KEY] = list(selected_files)
    else:
        organization_param = request.GET.get('organization')
    
    if not organization_param:
        return render(request, 'importer/partials/file_browser_empty.html')
    
    # Import the bucket service
    from arkumu.storage.services.bucket_service import BucketService
    
    try:
        # Get organization - handle both ID and code
        try:
            # First try as numeric ID
            organization = Organization.objects.get(id=int(organization_param))
        except (ValueError, Organization.DoesNotExist):
            # Fall back to code lookup
            try:
                organization = Organization.objects.get(code=organization_param)
                logger.info(f"INGEST: Found organization '{organization.name}' (code: {organization_param}, id: {organization.id})")
            except Organization.DoesNotExist:
                logger.warning(f"INGEST: Organization with code '{organization_param}' not found in database")
                return render(request, 'importer/partials/file_browser_error.html', {
                    'error': f'Organization "{organization_param}" not found',
                    'organization': organization_param
                })
        
        # Initialize service
        bucket_service = BucketService()
        
        # Get organization bucket
        bucket_name = bucket_service.get_organization_bucket(organization.code)
        
        # List files in the organization's metadata folder using bucket service
        files = bucket_service.list_bucket_contents(
            bucket_name=bucket_name,
            prefix='metadata/'
        )
        
        # Filter for CSV files only
        csv_files = []
        for file in files:
            if file['type'] == 'file' and file['name'].lower().endswith('.csv'):
                csv_files.append({
                    'key': file['path'],
                    'name': file['name'],
                    'size': file.get('size', 0),
                    'path_parts': file['path'].split('/')[1:]  # Remove 'metadata/' prefix
                })
        
        # Group files by directory
        file_tree = {}
        for file in csv_files:
            parts = file['path_parts']
            current = file_tree
            
            # Build directory structure
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {'files': [], 'dirs': {}}
                current = current[part]['dirs']
            
            # Add file to its directory
            if parts:
                parent = current
                if 'files' not in parent:
                    parent['files'] = []
                parent['files'].append(file)
        
        # Get selected files from session
        selected_files = set(request.session.get(SELECTED_FILES_SESSION_KEY, []))
        
        context = {
            'organization': organization,
            'file_tree': file_tree,
            'total_files': len(csv_files),
            'selected_files': selected_files,
            'selected_count': len(selected_files)
        }
        
        # Debug logging
        logger.info(f"INGEST DEBUG: organization={organization.name}, total_files={len(csv_files)}")
        logger.info(f"INGEST DEBUG: file_tree keys: {list(file_tree.keys())}")
        if 'files' in file_tree:
            logger.info(f"INGEST DEBUG: root files count: {len(file_tree['files'])}")
            logger.info(f"INGEST DEBUG: first few files: {[f['name'] for f in file_tree['files'][:3]]}")
        
        return render(request, 'importer/partials/file_browser_tree.html', context)
        
    except Organization.DoesNotExist:
        return render(request, 'importer/partials/file_browser_error.html', {
            'error': 'Organization not found'
        })
    except Exception as e:
        logger.error(f"Error listing organization files: {e}")
        return render(request, 'importer/partials/file_browser_error.html', {
            'error': str(e)
        })


@general_login_required
def toggle_file_selection(request):
    """
    HTMX endpoint to toggle file selection
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    file_key = request.POST.get('file_key')
    if not file_key:
        return HttpResponse('Missing file_key', status=400)
    
    # Get current selected files from session
    selected_files = set(request.session.get(SELECTED_FILES_SESSION_KEY, []))
    
    # Toggle selection
    if file_key in selected_files:
        selected_files.remove(file_key)
    else:
        selected_files.add(file_key)
    
    # Save back to session
    request.session[SELECTED_FILES_SESSION_KEY] = list(selected_files)
    
    # Return updated count with OOB swap for the counter
    count = len(selected_files)
    response = render(request, 'importer/partials/file_counter_oob.html', {
        'selected_count': count
    })
    
    # Add HX-Trigger header to notify execution status to update
    response['HX-Trigger'] = 'fileSelectionChanged'
    return response


@general_login_required 
def select_all_files(request):
    """
    HTMX endpoint to select all files for an organization
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    organization_param = request.POST.get('organization')
    if not organization_param:
        return render(request, 'importer/partials/file_browser_empty.html')
    
    try:
        # Get organization and files (reuse logic from get_organization_files_for_ingest)
        from arkumu.storage.services.bucket_service import BucketService
        
        try:
            organization = Organization.objects.get(id=int(organization_param))
        except (ValueError, Organization.DoesNotExist):
            organization = Organization.objects.get(code=organization_param)
        
        bucket_service = BucketService()
        bucket_name = bucket_service.get_organization_bucket(organization.code)
        
        files = bucket_service.list_bucket_contents(
            bucket_name=bucket_name,
            prefix='metadata/'
        )
        
        # Get all CSV file keys
        csv_file_keys = []
        for file in files:
            if file['type'] == 'file' and file['name'].lower().endswith('.csv'):
                csv_file_keys.append(file['path'])
        
        # Select all files
        request.session[SELECTED_FILES_SESSION_KEY] = csv_file_keys
        
        # Re-render the file browser with all files selected
        response = get_organization_files_for_ingest(request)
        
        # Add HX-Trigger header to notify execution status to update
        response['HX-Trigger'] = 'fileSelectionChanged'
        return response
        
    except Exception as e:
        logger.error(f"Error selecting all files: {e}")
        return render(request, 'importer/partials/file_browser_error.html', {
            'error': str(e)
        })


@general_login_required
def deselect_all_files(request):
    """
    HTMX endpoint to deselect all files
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    # Clear all selected files
    request.session[SELECTED_FILES_SESSION_KEY] = []
    
    # Re-render the file browser
    response = get_organization_files_for_ingest(request)
    
    # Add HX-Trigger header to notify execution status to update
    response['HX-Trigger'] = 'fileSelectionChanged'
    return response


# Note: change_organization view removed - organization changes are now handled 
# directly in IngestDataView.get() following the CSV mapping pattern


@general_login_required
def toggle_folder(request):
    """
    HTMX endpoint to toggle folder visibility (placeholder for now)
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    folder_id = request.POST.get('folder_id')
    if not folder_id:
        return HttpResponse('Missing folder_id', status=400)
    
    # For now, just return the folder with toggled class
    # This would need more sophisticated state management
    return HttpResponse(f'<div id="{folder_id}" class="folder-contents open"></div>')


@general_login_required
def navbar_controls(request):
    """
    HTMX endpoint to return navbar controls (mapping dropdown) for a specific organization
    """
    if request.method != 'GET':
        return HttpResponse('Method not allowed', status=405)
    
    organization_param = request.GET.get('organization')
    if not organization_param:
        return render(request, 'importer/partials/navbar_empty.html')
    
    try:
        # Get organization - handle both ID and code
        try:
            # First try as numeric ID
            organization = Organization.objects.get(id=int(organization_param))
        except (ValueError, Organization.DoesNotExist):
            # Fall back to code lookup
            try:
                organization = Organization.objects.get(code=organization_param)
            except Organization.DoesNotExist:
                return render(request, 'importer/partials/navbar_empty.html')
        
        # Render navbar controls with organization context
        context = {
            'organization_id': organization.id,
            'organization_code': organization.code,
            'selected_mapping': None,
        }
        
        return render(request, 'importer/partials/navbar_mapping_controls.html', context)
        
    except Exception as e:
        logger.error(f"Error rendering navbar controls: {e}")
        return render(request, 'importer/partials/navbar_empty.html')


@general_login_required
def execution_status(request):
    """
    HTMX endpoint to return execution status content (mapping and file status)
    """
    if request.method != 'GET':
        return HttpResponse('Method not allowed', status=405)
    
    organization_param = request.GET.get('organization')
    if not organization_param:
        return HttpResponse('Organization parameter required', status=400)
    
    try:
        # Get organization - handle both ID and code
        try:
            # First try as numeric ID
            organization = Organization.objects.get(id=int(organization_param))
        except (ValueError, Organization.DoesNotExist):
            # Fall back to code lookup
            try:
                organization = Organization.objects.get(code=organization_param)
            except Organization.DoesNotExist:
                return HttpResponse('Organization not found', status=404)
        
        # Initialize ingestion context in session if not exists
        context_key = f'ingestion_context_{organization.id}'
        ingestion_context = request.session.get(context_key, {})
        
        # Get selected files from session (backward compatibility)
        selected_files = request.session.get(SELECTED_FILES_SESSION_KEY, [])
        
        # Update context with current selected files count
        ingestion_context['selected_files_count'] = len(selected_files)
        ingestion_context['organization_id'] = organization.id
        ingestion_context['organization_code'] = organization.code
        
        # Get selected mapping from session
        mapping_id = ingestion_context.get('selected_mapping_id')
        selected_mapping = None
        
        if not mapping_id:
            # Try legacy session keys for backward compatibility
            mapping_id = request.session.get(f'selected_mapping_{organization.id}')
            if not mapping_id:
                mapping_id = request.session.get(f'selected_mapping_{organization.code}')
            
            # If found in legacy location, update context
            if mapping_id:
                ingestion_context['selected_mapping_id'] = mapping_id
        
        if mapping_id:
            try:
                from arkumu.metadata.models import Mapping
                selected_mapping = Mapping.objects.get(id=mapping_id)
                ingestion_context['selected_mapping_name'] = selected_mapping.name
            except Mapping.DoesNotExist:
                logger.warning(f"Mapping {mapping_id} not found")
                # Clear invalid mapping from context
                ingestion_context.pop('selected_mapping_id', None)
                ingestion_context.pop('selected_mapping_name', None)
                selected_mapping = None
        
        # Save updated context
        request.session[context_key] = ingestion_context
        request.session.modified = True
        
        logger.info(f"Execution status - Org: {organization.name}, Files: {len(selected_files)}, Mapping: {selected_mapping}")
        
        context = {
            'selected_files': selected_files,
            'selected_mapping': selected_mapping,
            'organization_id': organization.id,
            'ingestion_context': ingestion_context,
        }
        
        return render(request, 'importer/partials/execution_status.html', context)
        
    except Exception as e:
        logger.error(f"Error rendering execution status: {e}")
        return HttpResponse('Error rendering execution status', status=500)


@general_login_required
def list_mappings_dropdown(request):
    """
    HTMX endpoint to get mappings list for dropdown in navbar
    """
    if request.method != 'GET':
        return HttpResponse('Method not allowed', status=405)
    
    organization_param = request.GET.get('organization')
    if not organization_param:
        return render(request, 'importer/partials/mapping_dropdown_list.html', {
            'mappings': []
        })
    
    try:
        # Import here to avoid circular imports
        from arkumu.metadata.models.mappings import Mapping
        
        # Handle organization codes vs IDs (same logic as CSV mapping editor)
        organization_code = None
        try:
            # First try as numeric ID  
            organization_id = int(organization_param)
            # Look up organization by ID to get its code
            organization = Organization.objects.get(id=organization_id)
            organization_code = organization.code
        except (ValueError, Organization.DoesNotExist):
            # Handle organization codes like 'fuk', 'rsh', etc.
            organization_code = organization_param
            try:
                organization = Organization.objects.get(code=organization_code)
            except Organization.DoesNotExist:
                organization_code = None
        
        # Get mappings using the organization code (how they're stored)
        if organization_code:
            mappings = Mapping.objects.filter(
                organization_id=organization_code
            ).order_by('-created_at')
        else:
            mappings = Mapping.objects.none()
        
        return render(request, 'importer/partials/mapping_dropdown_list.html', {
            'mappings': mappings
        })
        
    except Exception as e:
        logger.error(f"Error listing mappings for dropdown: {e}")
        return render(request, 'importer/partials/mapping_dropdown_list.html', {
            'mappings': []
        })