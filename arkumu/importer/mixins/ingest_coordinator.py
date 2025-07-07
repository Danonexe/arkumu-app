"""
Ingest Coordinator Mixin

Manages state for the ingest interface including:
- Current organization selection
- Selected files for import
- Mapping selection
- Import configuration

Follows the same pattern as CSVMappingCoordinatorMixin but for ingest workflow.
"""

import logging
from django.core.cache import cache
from arkumu.users.models import Organization

logger = logging.getLogger(__name__)


class IngestCoordinatorMixin:
    """
    Coordinator mixin for ingest interface state management.
    
    Maintains server-side state for:
    - Current organization selection
    - Selected files
    - Mapping selection
    - Import configuration
    """
    
    # Session keys
    SELECTED_FILES_KEY = 'ingest_selected_files'
    CURRENT_ORG_KEY = 'ingest_current_organization'
    SELECTED_MAPPING_KEY = 'ingest_selected_mapping'
    
    def get_current_organization(self, request):
        """
        Get the currently selected organization from session.
        
        Returns:
            dict: Organization data with keys: id, code, name
            None: If no organization is selected
        """
        return request.session.get(self.CURRENT_ORG_KEY)
    
    def set_current_organization(self, request, organization_id):
        """
        Set the current organization in session.
        
        Args:
            request: Django request object
            organization_id: Organization ID (can be numeric ID or code string)
            
        Returns:
            dict: Organization data that was set
            None: If organization not found
        """
        try:
            # Try to parse as numeric ID first
            if organization_id.isdigit():
                organization = Organization.objects.get(id=int(organization_id))
            else:
                # Treat as organization code
                organization = Organization.objects.get(code=organization_id)
            
            org_data = {
                'id': organization.id,
                'code': organization.code,
                'name': organization.name
            }
            
            request.session[self.CURRENT_ORG_KEY] = org_data
            request.session.modified = True
            
            logger.info(f"INGEST_COORDINATOR: Set current organization to {org_data['name']} (code: {org_data['code']}, id: {org_data['id']})")
            return org_data
            
        except (Organization.DoesNotExist, ValueError):
            logger.warning(f"INGEST_COORDINATOR: Organization '{organization_id}' not found")
            return None
    
    def clear_current_organization(self, request):
        """Clear the current organization from session."""
        if self.CURRENT_ORG_KEY in request.session:
            del request.session[self.CURRENT_ORG_KEY]
            request.session.modified = True
            logger.info("INGEST_COORDINATOR: Cleared current organization")
    
    def get_organization_context(self, request):
        """
        Get organization context for templates.
        
        Returns:
            dict: Context with organization_id, organization_code, etc.
        """
        current_org = self.get_current_organization(request)
        if current_org:
            return {
                'organization_id': current_org['code'],  # Use code for mapping compatibility
                'organization_code': current_org['code'],
                'organization_name': current_org['name'],
                'organization_numeric_id': current_org['id']
            }
        else:
            return {
                'organization_id': None,
                'organization_code': None,
                'organization_name': None,
                'organization_numeric_id': None
            }
    
    def get_selected_files(self, request):
        """
        Get currently selected files from session.
        
        Returns:
            list: List of selected file paths
        """
        return request.session.get(self.SELECTED_FILES_KEY, [])
    
    def set_selected_files(self, request, file_paths):
        """
        Set selected files in session.
        
        Args:
            request: Django request object
            file_paths: List of file paths
        """
        request.session[self.SELECTED_FILES_KEY] = file_paths
        request.session.modified = True
        logger.info(f"INGEST_COORDINATOR: Set {len(file_paths)} selected files")
    
    def add_selected_file(self, request, file_path):
        """
        Add a file to the selection.
        
        Args:
            request: Django request object
            file_path: File path to add
            
        Returns:
            list: Updated selected files list
        """
        selected_files = set(self.get_selected_files(request))
        selected_files.add(file_path)
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files)
        return updated_files
    
    def remove_selected_file(self, request, file_path):
        """
        Remove a file from the selection.
        
        Args:
            request: Django request object
            file_path: File path to remove
            
        Returns:
            list: Updated selected files list
        """
        selected_files = set(self.get_selected_files(request))
        selected_files.discard(file_path)
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files)
        return updated_files
    
    def toggle_file_selection(self, request, file_path):
        """
        Toggle file selection state.
        
        Args:
            request: Django request object
            file_path: File path to toggle
            
        Returns:
            tuple: (updated_files_list, was_added)
        """
        selected_files = set(self.get_selected_files(request))
        
        if file_path in selected_files:
            selected_files.remove(file_path)
            was_added = False
        else:
            selected_files.add(file_path)
            was_added = True
        
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files)
        return updated_files, was_added
    
    def clear_selected_files(self, request):
        """Clear all selected files."""
        self.set_selected_files(request, [])
    
    def get_selected_mapping(self, request):
        """
        Get currently selected mapping from session.
        
        Returns:
            dict: Mapping data with keys: id, name, organization
            None: If no mapping is selected
        """
        return request.session.get(self.SELECTED_MAPPING_KEY)
    
    def set_selected_mapping(self, request, mapping_id, mapping_name=None):
        """
        Set the selected mapping in session.
        
        Args:
            request: Django request object
            mapping_id: Mapping ID
            mapping_name: Optional mapping name
        """
        current_org = self.get_current_organization(request)
        if not current_org:
            logger.warning("INGEST_COORDINATOR: Cannot set mapping without current organization")
            return None
        
        mapping_data = {
            'id': mapping_id,
            'name': mapping_name or f"Mapping {mapping_id}",
            'organization': current_org['code']
        }
        
        request.session[self.SELECTED_MAPPING_KEY] = mapping_data
        request.session.modified = True
        
        logger.info(f"INGEST_COORDINATOR: Set selected mapping to {mapping_data['name']} (id: {mapping_id})")
        return mapping_data
    
    def clear_selected_mapping(self, request):
        """Clear the selected mapping from session."""
        if self.SELECTED_MAPPING_KEY in request.session:
            del request.session[self.SELECTED_MAPPING_KEY]
            request.session.modified = True
            logger.info("INGEST_COORDINATOR: Cleared selected mapping")
    
    def handle_organization_change(self, request, new_organization_id):
        """
        Handle organization change with proper state cleanup.
        
        Args:
            request: Django request object
            new_organization_id: New organization ID
            
        Returns:
            dict: New organization data
        """
        logger.info(f"INGEST_COORDINATOR: Handling organization change to {new_organization_id}")
        
        # Clear state that depends on organization
        self.clear_selected_files(request)
        self.clear_selected_mapping(request)
        
        # Set new organization
        org_data = self.set_current_organization(request, new_organization_id)
        
        # Also store this organization for cross-view persistence (if OrganizationMixin is available)
        if hasattr(self, 'set_last_selected_organization'):
            self.set_last_selected_organization(request, new_organization_id)
        
        return org_data
    
    def get_file_browser_context(self, request, organization_id):
        """
        Get file browser context for a specific organization.
        
        Args:
            request: Django request object
            organization_id: Organization ID (code or numeric)
            
        Returns:
            dict: Context for file browser template
        """
        from arkumu.storage.services.bucket_service import BucketService
        
        if not organization_id:
            return {
                'organization': None,
                'file_tree': {},
                'total_files': 0,
                'selected_files': set(),
                'selected_count': 0
            }
        
        try:
            # Get organization
            try:
                if str(organization_id).isdigit():
                    organization = Organization.objects.get(id=int(organization_id))
                else:
                    organization = Organization.objects.get(code=organization_id)
            except (ValueError, Organization.DoesNotExist):
                logger.warning(f"INGEST_COORDINATOR: Organization '{organization_id}' not found")
                return {
                    'error': f'Organization "{organization_id}" not found',
                    'organization': organization_id
                }
            
            # Initialize bucket service
            bucket_service = BucketService()
            
            # Get organization bucket
            bucket_name = bucket_service.get_organization_bucket(organization.code)
            
            # List files in the organization's metadata folder
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
            selected_files = set(self.get_selected_files(request))
            
            return {
                'organization': organization,
                'file_tree': file_tree,
                'total_files': len(csv_files),
                'selected_files': selected_files,
                'selected_count': len(selected_files)
            }
            
        except Exception as e:
            logger.error(f"INGEST_COORDINATOR: Error getting file browser context: {e}")
            return {
                'error': str(e),
                'organization': organization_id
            }
    
    def get_ingest_context(self, request):
        """
        Get complete ingest context for templates.
        
        Returns:
            dict: Complete context including organization, files, mapping
        """
        org_context = self.get_organization_context(request)
        selected_files = self.get_selected_files(request)
        selected_mapping = self.get_selected_mapping(request)
        
        # Get file browser context if organization is selected
        if org_context['organization_id']:
            file_browser_context = self.get_file_browser_context(request, org_context['organization_id'])
        else:
            file_browser_context = {}
        
        return {
            **org_context,
            **file_browser_context,  # Include file browser data
            'selected_files': selected_files,
            'selected_files_count': len(selected_files),
            'selected_mapping': selected_mapping,
            'has_organization': org_context['organization_id'] is not None,
            'has_files': len(selected_files) > 0,
            'has_mapping': selected_mapping is not None,
            'ready_to_import': org_context['organization_id'] is not None and len(selected_files) > 0
        }
    
    def reset_ingest_state(self, request):
        """
        Reset all ingest state.
        
        Returns:
            dict: Summary of what was cleared
        """
        logger.info("INGEST_COORDINATOR: Resetting all ingest state")
        
        # Get current state for summary
        current_org = self.get_current_organization(request)
        selected_files_count = len(self.get_selected_files(request))
        had_mapping = self.get_selected_mapping(request) is not None
        
        # Clear all state
        self.clear_current_organization(request)
        self.clear_selected_files(request)
        self.clear_selected_mapping(request)
        
        summary = {
            'organization_cleared': current_org is not None,
            'files_cleared': selected_files_count,
            'mapping_cleared': had_mapping
        }
        
        logger.info(f"INGEST_COORDINATOR: Reset complete - {summary}")
        return summary