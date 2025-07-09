"""
Views for the new ingest data interface
"""
import os
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views import View
from arkumu.users.mixins import GeneralLoginRequiredMixin, general_login_required
from arkumu.users.models import Organization
from arkumu.importer.mixins.ingest_coordinator import IngestCoordinatorMixin

logger = logging.getLogger(__name__)

# Session storage for selected files
SELECTED_FILES_SESSION_KEY = 'ingest_selected_files'


class IngestDataView(GeneralLoginRequiredMixin, IngestCoordinatorMixin, View):
    """
    Main view for the new ingest data interface with three-pane layout
    
    Uses mixins in the same pattern as CSV mapping:
    - IngestCoordinatorMixin: Coordinating file selection and mapping
      (inherits from BaseCoordinatorMixin for organization management)
    """
    template_name = 'importer/ingest_data.html'
    
    def get(self, request):
        """Handle GET requests for the ingest data interface"""
        # Handle organization parameter from URL - set in session if provided
        organization_param = request.GET.get('organization')
        if organization_param:
            self.set_current_organization(request, organization_param)
        
        # Get current organization from session (works for both URL param and navigation)
        current_org = self.get_current_organization(request)
        if not current_org:
            # No organization selected - still render template but with no data
            # Get all organizations for dropdown
            organizations = Organization.objects.all().order_by('name')
            organizations_list = [
                {
                    'id': org.code,  # Use code for compatibility with templates
                    'name': org.name,
                    'status': 'active'  # Template expects status
                }
                for org in organizations
            ]
            
            context = {
                **self.get_base_template_context(request),
                'organization_id': None,
                'organization_code': None,
                'organization_name': None,
                'organization_numeric_id': None,
                'organizations': organizations_list,
                'selected_files': [],
                'selected_mapping': None,
                'available_mappings': [],
                'page_title': 'Metadata Ingestion',
            }
            if request.headers.get('HX-Request'):
                return render(request, 'importer/partials/main_ingest_content.html', context)
            return render(request, self.template_name, context)
        
        # Get ingest-specific context using IngestCoordinatorMixin
        ingest_context = self.get_ingest_context(request)
        
        # Get all organizations for dropdown
        organizations = Organization.objects.all().order_by('name')
        organizations_list = [
            {
                'id': org.code,  # Use code for compatibility with templates
                'name': org.name,
                'status': 'active'  # Template expects status
            }
            for org in organizations
        ]
        
        # Build context using BaseCoordinatorMixin
        context = {
            **self.get_base_template_context(request),
            'organization_id': current_org['code'],  # Use organization code for compatibility
            'organization_code': current_org['code'],
            'organization_name': current_org['name'],
            'organization_numeric_id': current_org['id'],
            'organizations': organizations_list,
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
        
        # Get current organization using BaseCoordinatorMixin
        current_org = self.get_current_organization(request)
        organization_id = current_org['id'] if current_org else None
        
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
                # Initialize ingestion context - use organization code for consistency with CSV mapping editor
                context_key = f'ingestion_context_{organization.code}'
                ingestion_context = request.session.get(context_key, {})
                
                # Get mapping details
                try:
                    from arkumu.metadata.models import Mapping
                    selected_mapping = Mapping.objects.get(
                        id=mapping_id,
                        organization_id=organization.code  # Use organization code for mapping lookup
                    )
                    
                    # Use the shared set_current_mapping method from BaseCoordinatorMixin
                    self.set_current_mapping(request, mapping_id, selected_mapping.name, organization.id)
                    
                    # Keep ingestion context for backward compatibility if needed
                    ingestion_context['selected_mapping_id'] = mapping_id
                    ingestion_context['selected_mapping_name'] = selected_mapping.name
                    ingestion_context['organization_id'] = organization.id
                    ingestion_context['organization_code'] = organization.code
                    
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
                    # Clear mapping using shared method
                    self.clear_current_mapping(request)
                    
                    # Clear mapping from ingestion context for backward compatibility
                    ingestion_context.pop('selected_mapping_id', None)
                    ingestion_context.pop('selected_mapping_name', None)
                    request.session[context_key] = ingestion_context
                    request.session.modified = True
                    
                    context = {
                        'selected_mapping': None,
                        'organization_id': organization.id,
                        'organization_code': organization.code,
                        'ingestion_context': ingestion_context
                    }
            else:
                logger.warning(f"Missing mapping_id or organization: mapping_id={mapping_id}, organization={organization}")
                # Clear any previously stored mapping using shared method
                self.clear_current_mapping(request)
                
                if organization:
                    context_key = f'ingestion_context_{organization.code}'
                    ingestion_context = request.session.get(context_key, {})
                    ingestion_context.pop('selected_mapping_id', None)
                    ingestion_context.pop('selected_mapping_name', None)
                    request.session[context_key] = ingestion_context
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
        
        # Initialize ingestion context in session if not exists - use organization code for consistency
        context_key = f'ingestion_context_{organization.code}'
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
            # Try legacy session keys for backward compatibility - prioritize organization code
            mapping_id = request.session.get(f'selected_mapping_{organization.code}')
            if not mapping_id:
                mapping_id = request.session.get(f'selected_mapping_{organization.id}')
            
            # If still not found, try to get from CSV mapping editor's loaded mapping context
            if not mapping_id:
                loaded_mapping_key = f'loaded_mapping_{organization.code}'
                loaded_mapping_context = request.session.get(loaded_mapping_key)
                if loaded_mapping_context:
                    mapping_id = loaded_mapping_context.get('mapping_id')
                    logger.info(f"INGEST_EXECUTION_STATUS: Found mapping from CSV editor context: {mapping_id}")
            
            # If found in any legacy location, update context
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
        
        # Also check for workspace columns from CSV mapping editor for better integration
        workspace_columns_count = 0
        if organization.code:
            workspace_columns_key = f'workspace_columns_{organization.code}'
            workspace_columns = request.session.get(workspace_columns_key, [])
            workspace_columns_count = len(workspace_columns)
            if workspace_columns_count > 0:
                logger.info(f"INGEST_EXECUTION_STATUS: Found {workspace_columns_count} workspace columns from CSV mapping editor")
        
        logger.info(f"Execution status - Org: {organization.name}, Files: {len(selected_files)}, Mapping: {selected_mapping}, Workspace columns: {workspace_columns_count}")
        
        context = {
            'selected_files': selected_files,
            'selected_mapping': selected_mapping,
            'organization_id': organization.id,
            'ingestion_context': ingestion_context,
            'workspace_columns_count': workspace_columns_count,
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


@general_login_required
def analyze_mapping(request):
    """
    HTMX endpoint to analyze selected mapping and match it to selected files.
    
    This view:
    1. Analyzes selected mapping and matches it to selected files
    2. Uses MappingAdapter.translate_to_execution_config()
    3. Analyzes dataset requirements vs available files
    4. Returns execution strategy recommendations
    5. Provides JSON response for HTMX consumption
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    try:
        # Get current organization using IngestCoordinatorMixin pattern
        view_instance = IngestDataView()
        current_org = view_instance.get_current_organization(request)
        
        if not current_org:
            return JsonResponse({
                'success': False,
                'error': 'No organization selected',
                'analysis': {}
            }, status=400)
        
        organization_id = current_org['id']
        organization_code = current_org['code']
        
        # Get current mapping from session
        current_mapping = view_instance.get_current_mapping(request)
        
        if not current_mapping:
            return JsonResponse({
                'success': False,
                'error': 'No mapping selected',
                'analysis': {}
            }, status=400)
        
        mapping_id = current_mapping['mapping_id']
        
        # Get selected files from session
        selected_files = request.session.get(SELECTED_FILES_SESSION_KEY, [])
        
        if not selected_files:
            return JsonResponse({
                'success': False,
                'error': 'No files selected',
                'analysis': {}
            }, status=400)
        
        # Import services
        from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
        
        # Initialize mapping adapter
        mapping_adapter = MappingAdapter()
        
        # Get mapping info and execution config
        mapping_info = mapping_adapter.get_mapping_info(mapping_id)
        execution_config = mapping_adapter.translate_to_execution_config(mapping_id)
        
        # Analyze selected files
        file_analysis = _analyze_selected_files(selected_files, organization_code)
        
        # Match mapping datasets to files
        dataset_file_matching = _match_datasets_to_files(
            execution_config.datasets, 
            file_analysis['files_by_dataset']
        )
        
        # Analyze mapping complexity
        complexity_analysis = _analyze_mapping_complexity(execution_config, mapping_info)
        
        # Determine execution strategy
        execution_strategy = _determine_execution_strategy(
            execution_config, 
            dataset_file_matching, 
            complexity_analysis
        )
        
        # Build comprehensive analysis response
        analysis_result = {
            'success': True,
            'mapping_info': {
                'id': mapping_info.id,
                'name': mapping_info.name,
                'organization': mapping_info.organization,
                'datasets': mapping_info.datasets,
                'total_columns': mapping_info.total_columns,
                'fk_relationships': mapping_info.fk_relationships,
                'external_ontologies': mapping_info.external_ontologies,
                'version': mapping_info.version
            },
            'file_analysis': file_analysis,
            'dataset_matching': dataset_file_matching,
            'complexity_analysis': complexity_analysis,
            'execution_strategy': execution_strategy,
            'processing_phases': _generate_processing_phases(execution_config, dataset_file_matching),
            'recommendations': _generate_recommendations(
                execution_config, 
                dataset_file_matching, 
                complexity_analysis
            ),
            'readiness_status': _assess_readiness_status(
                dataset_file_matching, 
                complexity_analysis
            )
        }
        
        logger.info(f"Mapping analysis completed for mapping {mapping_id} with {len(selected_files)} files")
        
        return JsonResponse(analysis_result)
        
    except Exception as e:
        logger.error(f"Error analyzing mapping: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'analysis': {}
        }, status=500)


def _analyze_selected_files(selected_files, organization_code):
    """
    Analyze selected files to extract dataset information and file metadata.
    
    Args:
        selected_files: List of selected file paths
        organization_code: Organization code for bucket access
        
    Returns:
        Dictionary with file analysis results
    """
    from arkumu.storage.services.bucket_service import BucketService
    
    bucket_service = BucketService()
    bucket_name = bucket_service.get_organization_bucket(organization_code)
    
    files_by_dataset = {}
    file_metadata = {}
    
    for file_path in selected_files:
        try:
            # Extract dataset name from file path
            file_name = file_path.split('/')[-1]
            dataset_name = file_name.replace('.csv', '').lower()
            
            # Get file metadata
            file_info = bucket_service.get_file_info(bucket_name, file_path)
            
            # Group files by dataset
            if dataset_name not in files_by_dataset:
                files_by_dataset[dataset_name] = []
            
            files_by_dataset[dataset_name].append({
                'file_path': file_path,
                'file_name': file_name,
                'dataset_name': dataset_name,
                'size': file_info.get('size', 0),
                'last_modified': file_info.get('last_modified')
            })
            
            file_metadata[file_path] = file_info
            
        except Exception as e:
            logger.warning(f"Could not analyze file {file_path}: {e}")
    
    return {
        'total_files': len(selected_files),
        'files_by_dataset': files_by_dataset,
        'unique_datasets': list(files_by_dataset.keys()),
        'file_metadata': file_metadata
    }


def _match_datasets_to_files(execution_datasets, files_by_dataset):
    """
    Match mapping datasets to available files.
    
    Args:
        execution_datasets: List of DatasetConfig objects from execution config
        files_by_dataset: Dictionary mapping dataset names to file lists
        
    Returns:
        Dictionary with matching results
    """
    matched_datasets = []
    missing_datasets = []
    extra_files = []
    
    # Get mapping dataset names
    mapping_dataset_names = [dataset.dataset_name.lower() for dataset in execution_datasets]
    file_dataset_names = list(files_by_dataset.keys())
    
    # Check each mapping dataset
    for dataset in execution_datasets:
        dataset_name = dataset.dataset_name.lower()
        
        if dataset_name in files_by_dataset:
            matched_datasets.append({
                'dataset_name': dataset.dataset_name,
                'files': files_by_dataset[dataset_name],
                'column_count': len(dataset.columns),
                'has_dependencies': bool(dataset.dependencies),
                'dependencies': dataset.dependencies,
                'primary_key_columns': dataset.primary_key_columns
            })
        else:
            missing_datasets.append({
                'dataset_name': dataset.dataset_name,
                'column_count': len(dataset.columns),
                'dependencies': dataset.dependencies,
                'is_required': True  # All mapping datasets are required
            })
    
    # Check for extra files not in mapping
    for file_dataset_name in file_dataset_names:
        if file_dataset_name not in mapping_dataset_names:
            extra_files.append({
                'dataset_name': file_dataset_name,
                'files': files_by_dataset[file_dataset_name],
                'is_extra': True
            })
    
    return {
        'matched_datasets': matched_datasets,
        'missing_datasets': missing_datasets,
        'extra_files': extra_files,
        'match_percentage': (len(matched_datasets) / len(execution_datasets)) * 100 if execution_datasets else 0,
        'is_complete_match': len(missing_datasets) == 0,
        'total_mapping_datasets': len(execution_datasets),
        'total_matched': len(matched_datasets)
    }


def _analyze_mapping_complexity(execution_config, mapping_info):
    """
    Analyze mapping complexity to determine processing requirements.
    
    Args:
        execution_config: ExecutionConfig object
        mapping_info: MappingInfo object
        
    Returns:
        Dictionary with complexity analysis
    """
    # Count column types
    column_types = {}
    for col_config in execution_config.column_configurations.values():
        col_type = col_config.column_type.value
        column_types[col_type] = column_types.get(col_type, 0) + 1
    
    # Calculate complexity score
    complexity_score = 0
    
    # Dataset complexity
    if len(execution_config.datasets) > 3:
        complexity_score += 2
    elif len(execution_config.datasets) > 1:
        complexity_score += 1
    
    # Column complexity
    if mapping_info.total_columns > 20:
        complexity_score += 2
    elif mapping_info.total_columns > 10:
        complexity_score += 1
    
    # Relationship complexity
    if len(execution_config.fk_relationships) > 5:
        complexity_score += 2
    elif len(execution_config.fk_relationships) > 0:
        complexity_score += 1
    
    # External ontology complexity
    if len(execution_config.external_ontologies) > 0:
        complexity_score += 1
    
    # Multi-value columns complexity
    multi_value_count = column_types.get('multi_value', 0)
    if multi_value_count > 0:
        complexity_score += 1
    
    # Determine complexity level
    if complexity_score >= 6:
        complexity_level = "high"
    elif complexity_score >= 3:
        complexity_level = "medium"
    else:
        complexity_level = "low"
    
    return {
        'complexity_score': complexity_score,
        'complexity_level': complexity_level,
        'column_types': column_types,
        'dataset_count': len(execution_config.datasets),
        'relationship_count': len(execution_config.fk_relationships),
        'external_ontology_count': len(execution_config.external_ontologies),
        'multi_value_columns': multi_value_count,
        'anchor_columns': column_types.get('anchor', 0),
        'regular_columns': column_types.get('regular', 0)
    }


def _determine_execution_strategy(execution_config, dataset_matching, complexity_analysis):
    """
    Determine optimal execution strategy based on mapping and file analysis.
    
    Args:
        execution_config: ExecutionConfig object
        dataset_matching: Dataset matching results
        complexity_analysis: Complexity analysis results
        
    Returns:
        Dictionary with execution strategy recommendations
    """
    strategy = execution_config.processing_strategy.value
    
    # Determine if we should override the strategy
    recommended_strategy = strategy
    
    # Check for dataset dependencies
    has_dependencies = any(
        dataset.dependencies for dataset in execution_config.datasets
    )
    
    # Check complexity factors
    complexity_level = complexity_analysis['complexity_level']
    dataset_count = len(execution_config.datasets)
    relationship_count = len(execution_config.fk_relationships)
    
    # Strategy recommendations
    if has_dependencies or relationship_count > 3:
        recommended_strategy = "multi_phase"
        strategy_reason = "Multiple datasets with dependencies require phased processing"
    elif complexity_level == "high":
        recommended_strategy = "streaming_entity_centric"
        strategy_reason = "High complexity mapping benefits from streaming approach"
    elif dataset_count == 1 and relationship_count == 0:
        recommended_strategy = "entity_centric"
        strategy_reason = "Single dataset with no relationships is ideal for entity-centric processing"
    else:
        strategy_reason = "Default strategy suitable for current mapping configuration"
    
    return {
        'current_strategy': strategy,
        'recommended_strategy': recommended_strategy,
        'strategy_reason': strategy_reason,
        'should_change_strategy': strategy != recommended_strategy,
        'processing_approach': _get_processing_approach(recommended_strategy),
        'expected_phases': _calculate_expected_phases(execution_config, dataset_matching)
    }


def _get_processing_approach(strategy):
    """Get human-readable processing approach description."""
    approaches = {
        'entity_centric': 'Process all data as a single entity-focused workflow',
        'streaming_entity_centric': 'Stream data processing for memory efficiency',
        'multi_phase': 'Process in multiple phases respecting dependencies',
        'auto': 'Automatically determine optimal processing approach'
    }
    return approaches.get(strategy, 'Unknown processing approach')


def _calculate_expected_phases(execution_config, dataset_matching):
    """Calculate expected number of processing phases."""
    if not dataset_matching['matched_datasets']:
        return 1
    
    # Check for dependencies
    has_dependencies = any(
        dataset.dependencies for dataset in execution_config.datasets
    )
    
    if has_dependencies:
        # Calculate dependency depth
        max_depth = 1
        for dataset in execution_config.datasets:
            if dataset.dependencies:
                max_depth = max(max_depth, len(dataset.dependencies) + 1)
        return max_depth
    
    return 1


def _generate_processing_phases(execution_config, dataset_matching):
    """
    Generate expected processing phases based on dataset dependencies.
    
    Args:
        execution_config: ExecutionConfig object
        dataset_matching: Dataset matching results
        
    Returns:
        List of processing phase descriptions
    """
    phases = []
    
    if not dataset_matching['matched_datasets']:
        return [{
            'phase': 1,
            'name': 'Setup Phase',
            'description': 'No datasets matched - setup and validation only',
            'datasets': [],
            'estimated_duration': 'Short'
        }]
    
    # Build dependency graph
    dependency_graph = {}
    for dataset in execution_config.datasets:
        dependency_graph[dataset.dataset_name] = dataset.dependencies
    
    # Sort datasets by dependency order
    processed = set()
    phase_num = 1
    
    while len(processed) < len(execution_config.datasets):
        current_phase_datasets = []
        
        # Find datasets that can be processed in this phase
        for dataset in execution_config.datasets:
            if dataset.dataset_name not in processed:
                # Check if all dependencies are satisfied
                dependencies_satisfied = all(
                    dep in processed for dep in dataset.dependencies
                )
                
                if dependencies_satisfied:
                    current_phase_datasets.append(dataset.dataset_name)
        
        if current_phase_datasets:
            # Determine phase characteristics
            phase_complexity = 'Low'
            if len(current_phase_datasets) > 2:
                phase_complexity = 'Medium'
            
            # Check if any dataset in this phase has relationships
            has_relationships = any(
                any(fk.source_dataset == dataset_name or fk.target_dataset == dataset_name 
                    for fk in execution_config.fk_relationships)
                for dataset_name in current_phase_datasets
            )
            
            if has_relationships:
                phase_complexity = 'High'
            
            phases.append({
                'phase': phase_num,
                'name': f'Phase {phase_num}',
                'description': f'Process {len(current_phase_datasets)} dataset(s): {", ".join(current_phase_datasets)}',
                'datasets': current_phase_datasets,
                'complexity': phase_complexity,
                'estimated_duration': 'Medium' if phase_complexity == 'High' else 'Short'
            })
            
            processed.update(current_phase_datasets)
            phase_num += 1
        else:
            # Circular dependency or error - break
            break
    
    return phases


def _generate_recommendations(execution_config, dataset_matching, complexity_analysis):
    """
    Generate processing recommendations based on analysis.
    
    Args:
        execution_config: ExecutionConfig object
        dataset_matching: Dataset matching results
        complexity_analysis: Complexity analysis results
        
    Returns:
        List of recommendation objects
    """
    recommendations = []
    
    # Check for missing datasets
    if dataset_matching['missing_datasets']:
        recommendations.append({
            'type': 'error',
            'title': 'Missing Required Datasets',
            'description': f"The mapping requires {len(dataset_matching['missing_datasets'])} dataset(s) that are not available in selected files",
            'details': [f"• {dataset['dataset_name']}" for dataset in dataset_matching['missing_datasets']],
            'action': 'Select additional files containing the missing datasets'
        })
    
    # Check for extra files
    if dataset_matching['extra_files']:
        recommendations.append({
            'type': 'warning',
            'title': 'Extra Files Detected',
            'description': f"Found {len(dataset_matching['extra_files'])} file(s) that are not required by the mapping",
            'details': [f"• {file['dataset_name']}" for file in dataset_matching['extra_files']],
            'action': 'Consider removing unnecessary files or updating the mapping'
        })
    
    # Complexity recommendations
    if complexity_analysis['complexity_level'] == 'high':
        recommendations.append({
            'type': 'info',
            'title': 'High Complexity Mapping',
            'description': 'This mapping has high complexity and may require more processing time',
            'details': [
                f"• {complexity_analysis['dataset_count']} datasets",
                f"• {complexity_analysis['relationship_count']} relationships",
                f"• {execution_config.column_configurations.__len__()} total columns"
            ],
            'action': 'Consider processing in smaller batches or during off-peak hours'
        })
    
    # Strategy recommendations
    if len(execution_config.fk_relationships) > 0:
        recommendations.append({
            'type': 'info',
            'title': 'Foreign Key Relationships Detected',
            'description': f"Found {len(execution_config.fk_relationships)} foreign key relationships",
            'details': [
                f"• {fk.source_dataset}.{fk.source_column} → {fk.target_dataset}.{fk.target_column}"
                for fk in execution_config.fk_relationships[:3]  # Show first 3
            ],
            'action': 'Ensure dependent datasets are processed in correct order'
        })
    
    # Performance recommendations
    if complexity_analysis['multi_value_columns'] > 0:
        recommendations.append({
            'type': 'info',
            'title': 'Multi-Value Columns Detected',
            'description': f"Found {complexity_analysis['multi_value_columns']} multi-value columns",
            'details': ['Multi-value columns require additional processing time'],
            'action': 'Consider increasing batch size for better performance'
        })
    
    return recommendations


def _assess_readiness_status(dataset_matching, complexity_analysis):
    """
    Assess overall readiness for import execution.
    
    Args:
        dataset_matching: Dataset matching results
        complexity_analysis: Complexity analysis results
        
    Returns:
        Dictionary with readiness assessment
    """
    issues = []
    warnings = []
    
    # Check for missing datasets
    if dataset_matching['missing_datasets']:
        issues.append(f"Missing {len(dataset_matching['missing_datasets'])} required dataset(s)")
    
    # Check match percentage
    if dataset_matching['match_percentage'] < 100:
        issues.append(f"Only {dataset_matching['match_percentage']:.1f}% of datasets matched")
    
    # Check for complexity warnings
    if complexity_analysis['complexity_level'] == 'high':
        warnings.append("High complexity mapping may require extended processing time")
    
    if complexity_analysis['relationship_count'] > 5:
        warnings.append("Many relationships detected - verify dependency order")
    
    # Determine overall status
    if issues:
        status = 'not_ready'
        status_message = f"Cannot proceed: {len(issues)} issue(s) found"
    elif warnings:
        status = 'ready_with_warnings'
        status_message = f"Ready to proceed with {len(warnings)} warning(s)"
    else:
        status = 'ready'
        status_message = "All checks passed - ready for import"
    
    return {
        'status': status,
        'status_message': status_message,
        'issues': issues,
        'warnings': warnings,
        'can_proceed': len(issues) == 0,
        'match_percentage': dataset_matching['match_percentage'],
        'complexity_level': complexity_analysis['complexity_level']
    }


@general_login_required
def run_pre_execution_validation(request):
    """
    HTMX endpoint to run comprehensive pre-execution validation.
    
    This endpoint:
    1. Gets current mapping and selected files
    2. Runs PreExecutionValidator service
    3. Returns validation results for display
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    try:
        # Get current organization using IngestCoordinatorMixin pattern
        view_instance = IngestDataView()
        current_org = view_instance.get_current_organization(request)
        
        if not current_org:
            return JsonResponse({
                'success': False,
                'error': 'No organization selected',
                'validation_results': {}
            }, status=400)
        
        organization_id = current_org['id']
        organization_code = current_org['code']
        
        # Get current mapping from session
        current_mapping = view_instance.get_current_mapping(request)
        
        if not current_mapping:
            return JsonResponse({
                'success': False,
                'error': 'No mapping selected',
                'validation_results': {}
            }, status=400)
        
        mapping_id = current_mapping['mapping_id']
        
        # Get selected files from session
        selected_files = request.session.get(SELECTED_FILES_SESSION_KEY, [])
        
        if not selected_files:
            return JsonResponse({
                'success': False,
                'error': 'No files selected',
                'validation_results': {}
            }, status=400)
        
        # Import validation services
        from arkumu.importer.services.pre_execution_validation.pre_execution_validator import PreExecutionValidator
        from arkumu.importer.services.mapping_consumer.mapping_adapter import MappingAdapter
        from arkumu.storage.services.bucket_service import BucketService
        
        # Initialize services
        mapping_adapter = MappingAdapter()
        validator = PreExecutionValidator(mapping_adapter=mapping_adapter)
        bucket_service = BucketService()
        
        # Get mapping configuration
        mapping_config = mapping_adapter.get_mapping_config(mapping_id)
        
        # For now, use the file paths as-is for validation
        # In a full implementation, we might download files to temp locations
        # or modify the validator to work with S3 paths directly
        bucket_name = bucket_service.get_organization_bucket(organization_code)
        
        # Run pre-execution validation with S3 paths
        # Note: The validator will need to be enhanced to handle S3 paths
        validation_result = validator.validate_mapping_execution(
            mapping_config=mapping_config,
            file_paths=selected_files
        )
        
        # Convert validation result to dict for JSON response
        validation_dict = validation_result.to_dict()
        
        # Store validation results in session for later retrieval
        validation_session_key = f'validation_results_{organization_code}'
        request.session[validation_session_key] = validation_dict
        request.session.modified = True
        
        # Return validation results
        return JsonResponse({
            'success': True,
            'validation_results': validation_dict,
            'mapping_id': mapping_id,
            'organization_code': organization_code,
            'files_validated': len(selected_files)
        })
        
    except Exception as e:
        logger.error(f"Pre-execution validation failed: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'validation_results': {}
        }, status=500)


@general_login_required
def validation_results_display(request):
    """
    HTMX endpoint to display validation results in the template.
    
    This endpoint can be used to:
    1. Show validation results from a previous validation run
    2. Display validation status when no validation has been run
    3. Integrate with the execution status flow
    """
    if request.method != 'GET':
        return HttpResponse('Method not allowed', status=405)
    
    try:
        # Get current organization
        view_instance = IngestDataView()
        current_org = view_instance.get_current_organization(request)
        
        if not current_org:
            return render(request, 'importer/partials/validation_results.html', {
                'validation_results': None,
                'has_validation': False,
                'error': 'No organization selected'
            })
        
        # Get validation results from session if available
        validation_session_key = f'validation_results_{current_org["code"]}'
        validation_results = request.session.get(validation_session_key)
        
        context = {
            'validation_results': validation_results,
            'has_validation': validation_results is not None,
            'organization_code': current_org['code'],
            'organization_id': current_org['id']
        }
        
        return render(request, 'importer/partials/validation_results.html', context)
        
    except Exception as e:
        logger.error(f"Error displaying validation results: {e}")
        return render(request, 'importer/partials/validation_results.html', {
            'validation_results': None,
            'has_validation': False,
            'error': str(e)
        })