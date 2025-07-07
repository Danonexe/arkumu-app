"""
Views for the new ingest data interface
"""
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from arkumu.users.mixins import general_login_required
from arkumu.users.models import Organization

logger = logging.getLogger(__name__)


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
        
        context = {
            'organization': organization,
            'file_tree': file_tree,
            'total_files': len(csv_files)
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