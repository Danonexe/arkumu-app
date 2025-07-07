"""
Views for the new ingest data interface
"""
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from arkumu.users.mixins import general_login_required
from arkumu.users.models import Organization

logger = logging.getLogger(__name__)

# Session storage for selected files
SELECTED_FILES_SESSION_KEY = 'ingest_selected_files'


@general_login_required
def ingest_data(request):
    """
    Main view for the new ingest data interface with three-pane layout
    """
    # Get organizations for the user
    organizations = Organization.objects.all().order_by('name')
    
    context = {
        'organizations': organizations,
        'page_title': 'Data Ingestion Center'
    }
    
    return render(request, 'importer/ingest_data.html', context)


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
    
    # Return updated count
    count = len(selected_files)
    return HttpResponse(f'{count} file{"s" if count != 1 else ""}')


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
        return get_organization_files_for_ingest(request)
        
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
    return get_organization_files_for_ingest(request)


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