"""
Ingest Coordinator Mixin

Manages state for the ingest interface including:
- Current organization selection
- Selected files for import
- Mapping selection
- Import configuration

Inherits from BaseCoordinatorMixin for standardized organization management
and session key patterns. Provides ingest-specific state management while
leveraging shared coordinator functionality.
"""

import logging
from django.core.cache import cache
from arkumu.users.models import Organization
from arkumu.common.mixins.base_coordinator import BaseCoordinatorMixin

logger = logging.getLogger(__name__)


class IngestCoordinatorMixin(BaseCoordinatorMixin):
    """
    Coordinator mixin for ingest interface state management.
    
    Inherits from BaseCoordinatorMixin to leverage:
    - Standardized organization management
    - Organization-scoped session key patterns
    - Base organization change handling
    
    Provides ingest-specific state for:
    - Selected files for import
    - Mapping selection
    - Import configuration
    """
    
    # Set the session prefix for this coordinator
    SESSION_PREFIX = 'ingest'
    
    # Organization management methods are inherited from BaseCoordinatorMixin
    # No need to reimplement - they use standardized session keys and patterns
    
    def get_selected_files(self, request, organization_id=None):
        """
        Get currently selected files from session for specific organization.
        
        Args:
            request: Django request object
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        
        Returns:
            list: List of selected file paths
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return []
            organization_id = current_org['code']
        
        session_key = self.get_session_key('selected_files', organization_id)
        return request.session.get(session_key, [])
    
    def set_selected_files(self, request, file_paths, organization_id=None):
        """
        Set selected files in session for specific organization.
        
        Args:
            request: Django request object
            file_paths: List of file paths
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot set files without current organization")
                return
            organization_id = current_org['code']
        
        session_key = self.get_session_key('selected_files', organization_id)
        request.session[session_key] = file_paths
        request.session.modified = True
        logger.info(f"INGEST_COORDINATOR: Set {len(file_paths)} selected files for org {organization_id}")
    
    def add_selected_file(self, request, file_path, organization_id=None):
        """
        Add a file to the selection for specific organization.
        
        Args:
            request: Django request object
            file_path: File path to add
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
            
        Returns:
            list: Updated selected files list
        """
        selected_files = set(self.get_selected_files(request, organization_id))
        selected_files.add(file_path)
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files, organization_id)
        return updated_files
    
    def remove_selected_file(self, request, file_path, organization_id=None):
        """
        Remove a file from the selection for specific organization.
        
        Args:
            request: Django request object
            file_path: File path to remove
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
            
        Returns:
            list: Updated selected files list
        """
        selected_files = set(self.get_selected_files(request, organization_id))
        selected_files.discard(file_path)
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files, organization_id)
        return updated_files
    
    def toggle_file_selection(self, request, file_path, organization_id=None):
        """
        Toggle file selection state for specific organization.
        
        Args:
            request: Django request object
            file_path: File path to toggle
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
            
        Returns:
            tuple: (updated_files_list, was_added)
        """
        selected_files = set(self.get_selected_files(request, organization_id))
        
        if file_path in selected_files:
            selected_files.remove(file_path)
            was_added = False
        else:
            selected_files.add(file_path)
            was_added = True
        
        updated_files = list(selected_files)
        self.set_selected_files(request, updated_files, organization_id)
        return updated_files, was_added
    
    def clear_selected_files(self, request, organization_id=None):
        """
        Clear all selected files for specific organization.
        
        Args:
            request: Django request object
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        """
        self.set_selected_files(request, [], organization_id)
    
    def get_selected_mapping(self, request, organization_id=None):
        """
        Get currently selected mapping from session for specific organization.
        
        Args:
            request: Django request object
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        
        Returns:
            dict: Mapping data with keys: id, name, organization
            None: If no mapping is selected
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return None
            organization_id = current_org['code']
        
        session_key = self.get_session_key('selected_mapping', organization_id)
        return request.session.get(session_key)
    
    def set_selected_mapping(self, request, mapping_id, mapping_name=None, organization_id=None):
        """
        Set the selected mapping in session for specific organization.
        
        Args:
            request: Django request object
            mapping_id: Mapping ID
            mapping_name: Optional mapping name
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot set mapping without current organization")
                return None
            organization_id = current_org['code']
        
        mapping_data = {
            'id': mapping_id,
            'name': mapping_name or f"Mapping {mapping_id}",
            'organization': organization_id
        }
        
        session_key = self.get_session_key('selected_mapping', organization_id)
        request.session[session_key] = mapping_data
        request.session.modified = True
        
        logger.info(f"INGEST_COORDINATOR: Set selected mapping to {mapping_data['name']} (id: {mapping_id}) for org {organization_id}")
        return mapping_data
    
    def clear_selected_mapping(self, request, organization_id=None):
        """
        Clear the selected mapping from session for specific organization.
        
        Args:
            request: Django request object
            organization_id (str, optional): Organization ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return
            organization_id = current_org['code']
        
        session_key = self.get_session_key('selected_mapping', organization_id)
        if session_key in request.session:
            del request.session[session_key]
            request.session.modified = True
            logger.info(f"INGEST_COORDINATOR: Cleared selected mapping for org {organization_id}")
    
    def handle_organization_change(self, request, new_organization_id):
        """
        Handle organization change with proper state cleanup.
        
        Overrides BaseCoordinatorMixin to add ingest-specific cleanup.
        
        Args:
            request: Django request object
            new_organization_id: New organization ID
            
        Returns:
            dict: New organization data
        """
        logger.info(f"INGEST_COORDINATOR: Handling organization change to {new_organization_id}")
        
        # Get current organization to clear its specific state
        current_org = self.get_current_organization(request)
        if current_org:
            self.clear_organization_specific_state(request, current_org['code'])
        
        # Call parent implementation to set new organization
        org_data = super().handle_organization_change(request, new_organization_id)
        
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
            
            # Get selected files from session for current organization
            selected_files = set(self.get_selected_files(request, organization_id))
            
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
        selected_files_count = len(self.get_selected_files(request)) if current_org else 0
        had_mapping = self.get_selected_mapping(request) is not None if current_org else False
        
        # Clear organization-specific state if we have an organization
        if current_org:
            self.clear_organization_specific_state(request, current_org['code'])
        
        # Clear current organization
        self.clear_current_organization(request)
        
        summary = {
            'organization_cleared': current_org is not None,
            'files_cleared': selected_files_count,
            'mapping_cleared': had_mapping
        }
        
        logger.info(f"INGEST_COORDINATOR: Reset complete - {summary}")
        return summary
    
    def clear_organization_specific_state(self, request, organization_id):
        """
        Clear all ingest state specific to an organization.
        
        Overrides BaseCoordinatorMixin to provide ingest-specific cleanup.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID to clear state for
        """
        logger.info(f"INGEST_COORDINATOR: Clearing organization-specific state for {organization_id}")
        
        # Clear files and mapping for this specific organization
        self.clear_selected_files(request, organization_id)
        self.clear_selected_mapping(request, organization_id)
        
        # Call parent implementation
        super().clear_organization_specific_state(request, organization_id)