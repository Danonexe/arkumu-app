"""
Ingest Coordinator Mixin

Manages state for the ingest interface including:
- Current organization selection
- Selected files for import
- Mapping selection
- Import configuration
- Ingest workspace management
- State persistence for resuming imports
- Validation of ingest configurations

Inherits from BaseCoordinatorMixin for standardized organization management
and session key patterns. Provides ingest-specific state management while
leveraging shared coordinator functionality including:
- Enhanced session key management (5 methods)
- Generic workspace management (7 methods)
- Generic dataset selection management (7 methods)
- State serialization/persistence (7 methods)
- Validation and consistency checks (7 methods)
"""

import logging
from django.core.cache import cache
from django.utils import timezone
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
    - Enhanced session key management (5 methods)
    - Generic workspace management (7 methods)
    - Generic dataset selection management (7 methods)
    - State serialization/persistence (7 methods)
    - Validation and consistency checks (7 methods)
    
    Provides ingest-specific state for:
    - Selected files for import
    - Mapping selection
    - Import configuration
    - Ingest workspace management (staging files, import configs)
    - State persistence for resuming imports
    - Validation of ingest configurations
    """
    
    # Set the session prefix for this coordinator
    SESSION_PREFIX = 'ingest'
    
    # Organization management methods are inherited from BaseCoordinatorMixin
    # No need to reimplement - they use standardized session keys and patterns
    
    def get_selected_files(self, request, organization_id=None):
        """
        Get currently selected files from session for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
        
        Returns:
            list: List of selected file paths
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return []
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        return self.get_selected_datasets(request, organization_id, 'selected_files')
    
    def set_selected_files(self, request, file_paths, organization_id=None):
        """
        Set selected files in session for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            file_paths: List of file paths
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot set files without current organization")
                return
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        self.set_selected_datasets(request, organization_id, file_paths, 'selected_files')
        logger.info(f"INGEST_COORDINATOR: Set {len(file_paths)} selected files for org ID {organization_id}")
    
    def add_selected_file(self, request, file_path, organization_id=None):
        """
        Add a file to the selection for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            file_path: File path to add
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            list: Updated selected files list
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot add file without current organization")
                return []
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        result = self.add_selected_dataset(request, organization_id, file_path, 'selected_files')
        return result[1]  # Return the updated dataset list
    
    def remove_selected_file(self, request, file_path, organization_id=None):
        """
        Remove a file from the selection for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            file_path: File path to remove
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            list: Updated selected files list
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot remove file without current organization")
                return []
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        result = self.remove_selected_dataset(request, organization_id, file_path, 'selected_files')
        return result[1]  # Return the updated dataset list
    
    def toggle_file_selection(self, request, file_path, organization_id=None):
        """
        Toggle file selection state for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            file_path: File path to toggle
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            tuple: (updated_files_list, was_added)
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot toggle file without current organization")
                return [], False
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        result = self.toggle_dataset_selection(request, organization_id, file_path, 'selected_files')
        return result[1], result[0]  # Return (updated_files_list, was_added)
    
    def clear_selected_files(self, request, organization_id=None):
        """
        Clear all selected files for specific organization.
        
        This method now leverages the base coordinator's generic selection management
        while maintaining backward compatibility.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot clear files without current organization")
                return
            organization_id = current_org['id']  # Use numeric ID consistently
        
        # Use base coordinator's generic selection management
        self.clear_selected_datasets(request, organization_id, 'selected_files')
    
    # Mapping methods are now inherited from BaseCoordinatorMixin
    # get_current_mapping, set_current_mapping, clear_current_mapping are available
    
    # ==========================================================================
    # Ingest Workspace Management Methods
    # ==========================================================================
    
    def get_staging_files(self, request, organization_id=None):
        """
        Get staging files from ingest workspace.
        
        Staging files are files that have been validated and are ready for import.
        They include additional metadata like validation status, file size, etc.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            list: List of staging file objects with metadata
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return []
            organization_id = current_org['id']
        
        # Use base coordinator's generic workspace management
        return self.get_workspace_items(request, organization_id, 'staging_files')
    
    def add_staging_file(self, request, file_path, file_metadata=None, organization_id=None):
        """
        Add a file to the staging workspace with validation metadata.
        
        Args:
            request: Django request object
            file_path: File path to add to staging
            file_metadata: Additional metadata for the file (size, validation status, etc.)
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            tuple: (success, item_added, total_items, error_message)
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot add staging file without current organization")
                return False, None, 0, "No current organization"
            organization_id = current_org['id']
        
        # Create staging file item
        staging_item = {
            'id': file_path,
            'file_path': file_path,
            'added_at': timezone.now().isoformat(),
            'status': 'staged',
            'metadata': file_metadata or {}
        }
        
        # Use base coordinator's generic workspace management
        result = self.add_workspace_item(request, organization_id, staging_item, 'staging_files')
        
        if result[0]:
            logger.info(f"INGEST_COORDINATOR: Added staging file '{file_path}' for org {organization_id}")
        else:
            logger.warning(f"INGEST_COORDINATOR: Failed to add staging file '{file_path}': {result[3]}")
        
        return result
    
    def remove_staging_file(self, request, file_path, organization_id=None):
        """
        Remove a file from the staging workspace.
        
        Args:
            request: Django request object
            file_path: File path to remove from staging
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            bool: True if removed successfully, False otherwise
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot remove staging file without current organization")
                return False
            organization_id = current_org['id']
        
        # Get current staging files
        staging_files = self.get_staging_files(request, organization_id)
        
        # Remove the file
        updated_files = [item for item in staging_files if item.get('id') != file_path]
        
        # Update workspace
        self.update_workspace_items(request, organization_id, updated_files, 'staging_files')
        
        removed = len(staging_files) > len(updated_files)
        if removed:
            logger.info(f"INGEST_COORDINATOR: Removed staging file '{file_path}' for org {organization_id}")
        else:
            logger.warning(f"INGEST_COORDINATOR: Staging file '{file_path}' not found for org {organization_id}")
        
        return removed
    
    def clear_staging_files(self, request, organization_id=None):
        """
        Clear all staging files from workspace.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot clear staging files without current organization")
                return
            organization_id = current_org['id']
        
        # Use base coordinator's generic workspace management
        self.clear_workspace_items(request, organization_id, 'staging_files')
        logger.info(f"INGEST_COORDINATOR: Cleared all staging files for org {organization_id}")
    
    def get_import_configurations(self, request, organization_id=None):
        """
        Get saved import configurations from workspace.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            list: List of import configuration objects
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return []
            organization_id = current_org['id']
        
        # Use base coordinator's generic workspace management
        return self.get_workspace_items(request, organization_id, 'import_configs')
    
    def save_import_configuration(self, request, config_name, configuration, organization_id=None):
        """
        Save an import configuration to workspace.
        
        Args:
            request: Django request object
            config_name: Name for the configuration
            configuration: Configuration data to save
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            tuple: (success, item_added, total_items, error_message)
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot save import config without current organization")
                return False, None, 0, "No current organization"
            organization_id = current_org['id']
        
        # Create import config item
        config_item = {
            'id': config_name,
            'name': config_name,
            'configuration': configuration,
            'created_at': timezone.now().isoformat(),
            'updated_at': timezone.now().isoformat()
        }
        
        # Use base coordinator's generic workspace management
        result = self.add_workspace_item(request, organization_id, config_item, 'import_configs')
        
        if result[0]:
            logger.info(f"INGEST_COORDINATOR: Saved import config '{config_name}' for org {organization_id}")
        else:
            logger.warning(f"INGEST_COORDINATOR: Failed to save import config '{config_name}': {result[3]}")
        
        return result
    
    def load_import_configuration(self, request, config_name, organization_id=None):
        """
        Load an import configuration from workspace.
        
        Args:
            request: Django request object
            config_name: Name of the configuration to load
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Configuration data, or None if not found
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot load import config without current organization")
                return None
            organization_id = current_org['id']
        
        # Get import configurations
        configs = self.get_import_configurations(request, organization_id)
        
        # Find the requested configuration
        for config in configs:
            if config.get('id') == config_name:
                logger.info(f"INGEST_COORDINATOR: Loaded import config '{config_name}' for org {organization_id}")
                return config.get('configuration')
        
        logger.warning(f"INGEST_COORDINATOR: Import config '{config_name}' not found for org {organization_id}")
        return None
    
    def get_workspace_summary(self, request, organization_id=None):
        """
        Get a summary of all workspace items for the ingest coordinator.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Summary of workspace items
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return {
                    'staging_files': 0,
                    'import_configs': 0,
                    'total_items': 0
                }
            organization_id = current_org['id']
        
        # Get counts for each workspace type
        staging_files = self.get_staging_files(request, organization_id)
        import_configs = self.get_import_configurations(request, organization_id)
        
        return {
            'staging_files': len(staging_files),
            'import_configs': len(import_configs),
            'total_items': len(staging_files) + len(import_configs),
            'organization_id': organization_id
        }
    
    # ==========================================================================
    # Ingest State Persistence Methods
    # ==========================================================================
    
    def save_ingest_state(self, request, state_name, organization_id=None):
        """
        Save the current ingest state for later resumption.
        
        This method leverages the base coordinator's state serialization capabilities
        to save the complete ingest state including selected files, staging files,
        import configurations, and current mapping.
        
        Args:
            request: Django request object
            state_name: Name to save the state under
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Result of the save operation
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot save ingest state without current organization")
                return {
                    'success': False,
                    'error': 'No current organization',
                    'state_name': state_name
                }
            organization_id = current_org['id']
        
        # Configure what to include in ingest state
        ingest_state_config = {
            'include_keys': [
                'selected_files',
                'staging_files',
                'import_configs'
            ],
            'metadata': {
                'coordinator_type': 'IngestCoordinator',
                'state_name': state_name,
                'description': f'Ingest state saved as {state_name}',
                'version': '1.0'
            },
            'validation': True
        }
        
        # Use base coordinator's state serialization
        result = self.save_coordinator_state(request, organization_id, state_name, ingest_state_config)
        
        if result['success']:
            logger.info(f"INGEST_COORDINATOR: Saved ingest state '{state_name}' for org {organization_id}")
        else:
            logger.error(f"INGEST_COORDINATOR: Failed to save ingest state '{state_name}': {result.get('error')}")
        
        return result
    
    def load_ingest_state(self, request, state_name, organization_id=None):
        """
        Load a previously saved ingest state.
        
        This method leverages the base coordinator's state deserialization capabilities
        to restore the complete ingest state including selected files, staging files,
        import configurations, and current mapping.
        
        Args:
            request: Django request object
            state_name: Name of the state to load
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Result of the load operation
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot load ingest state without current organization")
                return {
                    'success': False,
                    'error': 'No current organization',
                    'state_name': state_name
                }
            organization_id = current_org['id']
        
        # Configure what to include in ingest state
        ingest_state_config = {
            'include_keys': [
                'selected_files',
                'staging_files',
                'import_configs'
            ],
            'validation': True
        }
        
        # Use base coordinator's state deserialization
        result = self.load_coordinator_state(request, organization_id, state_name, ingest_state_config)
        
        if result['success']:
            logger.info(f"INGEST_COORDINATOR: Loaded ingest state '{state_name}' for org {organization_id}")
        else:
            logger.error(f"INGEST_COORDINATOR: Failed to load ingest state '{state_name}': {result.get('error')}")
        
        return result
    
    def get_saved_ingest_states(self, request, organization_id=None):
        """
        Get metadata for all saved ingest states.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Metadata for all saved states
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return {
                    'success': False,
                    'error': 'No current organization',
                    'states': []
                }
            organization_id = current_org['id']
        
        # Use base coordinator's state metadata retrieval
        return self.get_state_metadata(request, organization_id)
    
    def clear_ingest_state(self, request, state_name=None, organization_id=None):
        """
        Clear saved ingest state(s).
        
        Args:
            request: Django request object
            state_name: Specific state to clear (if None, clears all states)
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Result of the clear operation
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot clear ingest state without current organization")
                return {
                    'success': False,
                    'error': 'No current organization'
                }
            organization_id = current_org['id']
        
        if state_name:
            # Clear specific state
            result = self.clear_coordinator_state(request, organization_id, {'state_name': state_name})
            if result['success']:
                logger.info(f"INGEST_COORDINATOR: Cleared ingest state '{state_name}' for org {organization_id}")
            else:
                logger.error(f"INGEST_COORDINATOR: Failed to clear ingest state '{state_name}': {result.get('error')}")
        else:
            # Clear all ingest states
            result = self.clear_coordinator_state(request, organization_id)
            if result['success']:
                logger.info(f"INGEST_COORDINATOR: Cleared all ingest states for org {organization_id}")
            else:
                logger.error(f"INGEST_COORDINATOR: Failed to clear all ingest states: {result.get('error')}")
        
        return result
    
    def serialize_ingest_state(self, request, organization_id=None):
        """
        Serialize the current ingest state for export or backup.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Serialized ingest state
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot serialize ingest state without current organization")
                return {
                    'success': False,
                    'error': 'No current organization'
                }
            organization_id = current_org['id']
        
        # Configure serialization for ingest state
        ingest_state_config = {
            'include_keys': [
                'selected_files',
                'staging_files',
                'import_configs'
            ],
            'metadata': {
                'coordinator_type': 'IngestCoordinator',
                'description': 'Exported ingest state',
                'version': '1.0'
            },
            'validation': True,
            'compression': False
        }
        
        # Use base coordinator's state serialization
        result = self.serialize_coordinator_state(request, organization_id, ingest_state_config)
        
        if result['success']:
            logger.info(f"INGEST_COORDINATOR: Serialized ingest state for org {organization_id}")
        else:
            logger.error(f"INGEST_COORDINATOR: Failed to serialize ingest state: {result.get('error_message')}")
        
        return result
    
    def deserialize_ingest_state(self, request, state_data, organization_id=None):
        """
        Deserialize and restore ingest state from exported data.
        
        Args:
            request: Django request object
            state_data: Serialized state data to restore
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Result of the deserialization operation
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                logger.warning("INGEST_COORDINATOR: Cannot deserialize ingest state without current organization")
                return {
                    'success': False,
                    'error': 'No current organization'
                }
            organization_id = current_org['id']
        
        # Configure deserialization for ingest state
        ingest_state_config = {
            'include_keys': [
                'selected_files',
                'staging_files',
                'import_configs'
            ],
            'validation': True
        }
        
        # Use base coordinator's state deserialization
        result = self.deserialize_coordinator_state(request, organization_id, state_data, ingest_state_config)
        
        if result['success']:
            logger.info(f"INGEST_COORDINATOR: Deserialized ingest state for org {organization_id}")
        else:
            logger.error(f"INGEST_COORDINATOR: Failed to deserialize ingest state: {result.get('error_message')}")
        
        return result
    
    # ==========================================================================
    # Ingest Validation Methods
    # ==========================================================================
    
    def validate_selected_files(self, request, organization_id=None):
        """
        Validate the currently selected files for ingest.
        
        This method checks file existence, format, accessibility, and basic integrity
        of the selected files for import.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Validation results with detailed findings
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return {
                    'is_valid': False,
                    'error': 'No current organization',
                    'files_validated': 0,
                    'validation_results': []
                }
            organization_id = current_org['id']
        
        selected_files = self.get_selected_files(request, organization_id)
        
        validation_results = {
            'is_valid': True,
            'organization_id': organization_id,
            'files_validated': len(selected_files),
            'valid_files': [],
            'invalid_files': [],
            'warnings': [],
            'errors': [],
            'summary': {
                'total_files': len(selected_files),
                'valid_count': 0,
                'invalid_count': 0,
                'warning_count': 0,
                'error_count': 0
            }
        }
        
        if not selected_files:
            validation_results['warnings'].append("No files selected for validation")
            validation_results['summary']['warning_count'] = 1
            return validation_results
        
        # Validate each file
        for file_path in selected_files:
            file_validation = self._validate_single_file(request, file_path, organization_id)
            
            if file_validation['is_valid']:
                validation_results['valid_files'].append(file_validation)
                validation_results['summary']['valid_count'] += 1
            else:
                validation_results['invalid_files'].append(file_validation)
                validation_results['summary']['invalid_count'] += 1
                validation_results['is_valid'] = False
            
            # Collect warnings and errors
            validation_results['warnings'].extend(file_validation.get('warnings', []))
            validation_results['errors'].extend(file_validation.get('errors', []))
        
        validation_results['summary']['warning_count'] = len(validation_results['warnings'])
        validation_results['summary']['error_count'] = len(validation_results['errors'])
        
        logger.info(f"INGEST_COORDINATOR: Validated {len(selected_files)} files for org {organization_id} - " +
                   f"Valid: {validation_results['summary']['valid_count']}, " +
                   f"Invalid: {validation_results['summary']['invalid_count']}")
        
        return validation_results
    
    def _validate_single_file(self, request, file_path, organization_id):
        """
        Validate a single file for ingest.
        
        Args:
            request: Django request object
            file_path: Path to the file to validate
            organization_id: Organization numeric ID
            
        Returns:
            dict: Validation result for the file
        """
        from arkumu.storage.services.bucket_service import BucketService
        
        file_validation = {
            'file_path': file_path,
            'is_valid': True,
            'warnings': [],
            'errors': [],
            'metadata': {}
        }
        
        try:
            # Get organization
            organization = Organization.objects.get(id=organization_id)
            
            # Initialize bucket service
            bucket_service = BucketService()
            bucket_name = bucket_service.get_organization_bucket(organization.code)
            
            # Check if file exists
            try:
                file_info = bucket_service.get_file_info(bucket_name, file_path)
                file_validation['metadata'] = file_info
                
                # Check file format
                if not file_path.lower().endswith('.csv'):
                    file_validation['errors'].append(f"File '{file_path}' is not a CSV file")
                    file_validation['is_valid'] = False
                
                # Check file size
                file_size = file_info.get('size', 0)
                if file_size == 0:
                    file_validation['errors'].append(f"File '{file_path}' is empty")
                    file_validation['is_valid'] = False
                elif file_size > 100 * 1024 * 1024:  # 100MB limit
                    file_validation['warnings'].append(f"File '{file_path}' is large ({file_size} bytes)")
                
                # Basic content validation (check if it's readable CSV)
                try:
                    content_sample = bucket_service.read_file_content(bucket_name, file_path, max_size=1024)
                    if content_sample:
                        # Check for basic CSV structure
                        lines = content_sample.split('\n')
                        if len(lines) < 2:
                            file_validation['warnings'].append(f"File '{file_path}' appears to have no data rows")
                        else:
                            # Check for consistent column count
                            header_cols = len(lines[0].split(','))
                            if header_cols == 0:
                                file_validation['errors'].append(f"File '{file_path}' has no columns")
                                file_validation['is_valid'] = False
                            elif header_cols > 100:
                                file_validation['warnings'].append(f"File '{file_path}' has many columns ({header_cols})")
                    
                except Exception as e:
                    file_validation['warnings'].append(f"Could not read content from '{file_path}': {str(e)}")
                
            except Exception as e:
                file_validation['errors'].append(f"File '{file_path}' not found or inaccessible: {str(e)}")
                file_validation['is_valid'] = False
        
        except Exception as e:
            file_validation['errors'].append(f"Error validating file '{file_path}': {str(e)}")
            file_validation['is_valid'] = False
        
        return file_validation
    
    def validate_import_configuration(self, request, configuration, organization_id=None):
        """
        Validate an import configuration for completeness and correctness.
        
        Args:
            request: Django request object
            configuration: Import configuration to validate
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Validation results
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return {
                    'is_valid': False,
                    'error': 'No current organization',
                    'validation_results': []
                }
            organization_id = current_org['id']
        
        validation_results = {
            'is_valid': True,
            'organization_id': organization_id,
            'configuration_valid': True,
            'required_fields': [],
            'optional_fields': [],
            'warnings': [],
            'errors': []
        }
        
        if not configuration or not isinstance(configuration, dict):
            validation_results['errors'].append("Configuration must be a valid dictionary")
            validation_results['is_valid'] = False
            validation_results['configuration_valid'] = False
            return validation_results
        
        # Define required fields for import configuration
        required_fields = ['mapping_id', 'target_dataset', 'import_mode']
        optional_fields = ['batch_size', 'skip_errors', 'validation_level', 'custom_settings']
        
        # Check required fields
        for field in required_fields:
            if field not in configuration:
                validation_results['errors'].append(f"Required field '{field}' missing from configuration")
                validation_results['is_valid'] = False
                validation_results['configuration_valid'] = False
            else:
                validation_results['required_fields'].append(field)
        
        # Check optional fields
        for field in optional_fields:
            if field in configuration:
                validation_results['optional_fields'].append(field)
        
        # Validate specific field values
        if 'mapping_id' in configuration:
            mapping_id = configuration['mapping_id']
            if not mapping_id:
                validation_results['errors'].append("Mapping ID cannot be empty")
                validation_results['is_valid'] = False
        
        if 'target_dataset' in configuration:
            target_dataset = configuration['target_dataset']
            if not target_dataset:
                validation_results['errors'].append("Target dataset cannot be empty")
                validation_results['is_valid'] = False
        
        if 'import_mode' in configuration:
            import_mode = configuration['import_mode']
            valid_modes = ['append', 'replace', 'update']
            if import_mode not in valid_modes:
                validation_results['errors'].append(f"Import mode '{import_mode}' not valid. Must be one of: {valid_modes}")
                validation_results['is_valid'] = False
        
        if 'batch_size' in configuration:
            batch_size = configuration['batch_size']
            if not isinstance(batch_size, int) or batch_size <= 0:
                validation_results['errors'].append("Batch size must be a positive integer")
                validation_results['is_valid'] = False
            elif batch_size > 10000:
                validation_results['warnings'].append(f"Batch size {batch_size} is very large and may cause performance issues")
        
        logger.info(f"INGEST_COORDINATOR: Validated import configuration for org {organization_id} - " +
                   f"Valid: {validation_results['is_valid']}")
        
        return validation_results
    
    def validate_ingest_consistency(self, request, organization_id=None):
        """
        Validate consistency of the complete ingest setup.
        
        This method performs comprehensive validation of the ingest state including
        file selections, staging files, import configurations, and their relationships.
        
        Args:
            request: Django request object
            organization_id (int, optional): Organization numeric ID. If not provided, uses current organization.
            
        Returns:
            dict: Comprehensive validation results
        """
        if not organization_id:
            current_org = self.get_current_organization(request)
            if not current_org:
                return {
                    'is_consistent': False,
                    'error': 'No current organization',
                    'validation_results': []
                }
            organization_id = current_org['id']
        
        # Use base coordinator's comprehensive validation
        base_validation = self.validate_coordinator_consistency(request, organization_id, {
            'auto_fix': False,
            'strict_mode': False,
            'include_components': ['session_keys', 'workspace', 'selections', 'state_integrity']
        })
        
        # Add ingest-specific validation
        selected_files = self.get_selected_files(request, organization_id)
        staging_files = self.get_staging_files(request, organization_id)
        import_configs = self.get_import_configurations(request, organization_id)
        current_mapping = self.get_current_mapping(request)
        
        ingest_validation = {
            'is_consistent': base_validation['is_consistent'],
            'organization_id': organization_id,
            'base_validation': base_validation,
            'ingest_specific': {
                'selected_files_count': len(selected_files),
                'staging_files_count': len(staging_files),
                'import_configs_count': len(import_configs),
                'has_current_mapping': current_mapping is not None,
                'consistency_checks': []
            },
            'warnings': [],
            'errors': []
        }
        
        # Check file consistency
        if selected_files and staging_files:
            staging_file_paths = [item.get('file_path') for item in staging_files]
            unstaged_files = [f for f in selected_files if f not in staging_file_paths]
            if unstaged_files:
                ingest_validation['warnings'].append(f"{len(unstaged_files)} selected files are not staged")
                ingest_validation['ingest_specific']['consistency_checks'].append({
                    'check': 'file_staging_consistency',
                    'status': 'warning',
                    'message': f"{len(unstaged_files)} selected files not staged",
                    'details': unstaged_files
                })
        
        # Check mapping consistency
        if selected_files and not current_mapping:
            ingest_validation['warnings'].append("Files selected but no mapping configured")
            ingest_validation['ingest_specific']['consistency_checks'].append({
                'check': 'mapping_consistency',
                'status': 'warning',
                'message': "Files selected but no mapping configured"
            })
        
        # Check import configuration consistency
        if import_configs and not current_mapping:
            ingest_validation['warnings'].append("Import configurations exist but no current mapping")
            ingest_validation['ingest_specific']['consistency_checks'].append({
                'check': 'config_mapping_consistency',
                'status': 'warning',
                'message': "Import configurations exist but no current mapping"
            })
        
        # Check readiness for import
        ready_for_import = (
            len(selected_files) > 0 and
            current_mapping is not None and
            len(import_configs) > 0
        )
        
        ingest_validation['ingest_specific']['ready_for_import'] = ready_for_import
        
        if not ready_for_import:
            missing_components = []
            if len(selected_files) == 0:
                missing_components.append("selected files")
            if current_mapping is None:
                missing_components.append("current mapping")
            if len(import_configs) == 0:
                missing_components.append("import configurations")
            
            ingest_validation['warnings'].append(f"Not ready for import - missing: {', '.join(missing_components)}")
        
        logger.info(f"INGEST_COORDINATOR: Validated ingest consistency for org {organization_id} - " +
                   f"Consistent: {ingest_validation['is_consistent']}, " +
                   f"Ready for import: {ready_for_import}")
        
        return ingest_validation
    
    def handle_organization_change(self, request, new_organization_id):
        """
        Handle organization change with proper state cleanup.
        
        Overrides BaseCoordinatorMixin to add ingest-specific cleanup.
        
        Args:
            request: Django request object
            new_organization_id: New organization ID or code
            
        Returns:
            tuple: (new_org_data, old_org_data) - New and old organization data
        """
        logger.info(f"INGEST_COORDINATOR: Handling organization change to {new_organization_id}")
        
        # Call parent implementation to handle organization change safely
        return super().handle_organization_change(request, new_organization_id)
    
    def get_file_browser_context(self, request, organization_id):
        """
        Get enhanced file browser context for a specific organization.
        
        Now includes validation status, workspace integration, and enhanced file metadata
        to provide a comprehensive view of the ingest state.
        
        Args:
            request: Django request object
            organization_id: Organization ID (code or numeric)
            
        Returns:
            dict: Enhanced context for file browser template
        """
        from arkumu.storage.services.bucket_service import BucketService
        
        if not organization_id:
            return {
                'organization': None,
                'file_tree': {},
                'total_files': 0,
                'selected_files': set(),
                'selected_count': 0,
                'staging_files': [],
                'staging_count': 0,
                'workspace_summary': {},
                'validation_summary': {},
                'error': 'No organization ID provided'
            }
        
        try:
            # Get organization
            try:
                if str(organization_id).isdigit():
                    organization = Organization.objects.get(id=int(organization_id))
                    organization_numeric_id = int(organization_id)
                else:
                    organization = Organization.objects.get(code=organization_id)
                    organization_numeric_id = organization.id
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
            
            # Filter for CSV files only and add enhanced metadata
            csv_files = []
            for file in files:
                if file['type'] == 'file' and file['name'].lower().endswith('.csv'):
                    enhanced_file = {
                        'key': file['path'],
                        'name': file['name'],
                        'size': file.get('size', 0),
                        'path_parts': file['path'].split('/')[1:],  # Remove 'metadata/' prefix
                        'last_modified': file.get('last_modified'),
                        'validation_status': 'unknown',  # Will be populated if validated
                        'is_staged': False,  # Will be populated from workspace
                        'stage_metadata': None  # Will be populated from workspace
                    }
                    csv_files.append(enhanced_file)
            
            # Get workspace data
            selected_files = set(self.get_selected_files(request, organization_numeric_id))
            staging_files = self.get_staging_files(request, organization_numeric_id)
            workspace_summary = self.get_workspace_summary(request, organization_numeric_id)
            
            # Create staging file lookup for faster access
            staging_file_lookup = {item.get('file_path'): item for item in staging_files}
            
            # Enhance file metadata with workspace information
            for file in csv_files:
                file_path = file['key']
                
                # Mark if file is selected
                file['is_selected'] = file_path in selected_files
                
                # Add staging information
                if file_path in staging_file_lookup:
                    file['is_staged'] = True
                    file['stage_metadata'] = staging_file_lookup[file_path].get('metadata', {})
                    file['staged_at'] = staging_file_lookup[file_path].get('added_at')
                    file['validation_status'] = staging_file_lookup[file_path].get('status', 'staged')
            
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
            
            # Get validation summary for selected files
            validation_summary = {}
            if selected_files:
                validation_results = self.validate_selected_files(request, organization_numeric_id)
                validation_summary = {
                    'total_files': validation_results['files_validated'],
                    'valid_files': validation_results['summary']['valid_count'],
                    'invalid_files': validation_results['summary']['invalid_count'],
                    'warnings': validation_results['summary']['warning_count'],
                    'errors': validation_results['summary']['error_count'],
                    'is_valid': validation_results['is_valid']
                }
            
            # Get current mapping info
            current_mapping = self.get_current_mapping(request)
            
            # Calculate readiness indicators
            readiness_indicators = {
                'has_selected_files': len(selected_files) > 0,
                'has_staging_files': len(staging_files) > 0,
                'has_current_mapping': current_mapping is not None,
                'has_import_configs': workspace_summary.get('import_configs', 0) > 0,
                'validation_passed': validation_summary.get('is_valid', False) if selected_files else None,
                'ready_for_import': (
                    len(selected_files) > 0 and
                    current_mapping is not None and
                    workspace_summary.get('import_configs', 0) > 0 and
                    validation_summary.get('is_valid', False)
                )
            }
            
            # Enhanced context with all new features
            context = {
                'organization': organization,
                'organization_id': organization_numeric_id,
                'file_tree': file_tree,
                'total_files': len(csv_files),
                'selected_files': selected_files,
                'selected_count': len(selected_files),
                'staging_files': staging_files,
                'staging_count': len(staging_files),
                'workspace_summary': workspace_summary,
                'validation_summary': validation_summary,
                'current_mapping': current_mapping,
                'readiness_indicators': readiness_indicators,
                'enhanced_metadata': True  # Flag to indicate this is enhanced context
            }
            
            logger.info(f"INGEST_COORDINATOR: Enhanced file browser context for org {organization_numeric_id} - " +
                       f"Files: {len(csv_files)}, Selected: {len(selected_files)}, Staged: {len(staging_files)}")
            
            return context
            
        except Exception as e:
            logger.error(f"INGEST_COORDINATOR: Error getting enhanced file browser context: {e}")
            return {
                'error': str(e),
                'organization': organization_id,
                'enhanced_metadata': False
            }
    
    def get_ingest_context(self, request):
        """
        Get complete enhanced ingest context for templates.
        
        Now includes workspace data, validation status, and comprehensive state information
        to provide a complete view of the ingest process.
        
        Returns:
            dict: Complete enhanced context including organization, files, mapping, workspace, and validation
        """
        org_context = self.get_organization_context(request)
        selected_files = self.get_selected_files(request)
        selected_mapping = self.get_current_mapping(request)  # Use shared mapping from base
        
        # Get enhanced file browser context if organization is selected
        if org_context['organization_id']:
            file_browser_context = self.get_file_browser_context(request, org_context['organization_id'])
        else:
            file_browser_context = {}
        
        # Get workspace summary if organization is selected
        workspace_summary = {}
        if org_context['organization_id']:
            workspace_summary = self.get_workspace_summary(request, org_context['organization_id'])
        
        # Get validation summary if files are selected
        validation_summary = {}
        if selected_files and org_context['organization_id']:
            validation_results = self.validate_selected_files(request, org_context['organization_id'])
            validation_summary = {
                'total_files': validation_results['files_validated'],
                'valid_files': validation_results['summary']['valid_count'],
                'invalid_files': validation_results['summary']['invalid_count'],
                'warnings': validation_results['summary']['warning_count'],
                'errors': validation_results['summary']['error_count'],
                'is_valid': validation_results['is_valid']
            }
        
        # Calculate comprehensive readiness indicators
        readiness_indicators = {
            'has_organization': org_context['organization_id'] is not None,
            'has_selected_files': len(selected_files) > 0,
            'has_staging_files': workspace_summary.get('staging_files', 0) > 0,
            'has_current_mapping': selected_mapping is not None,
            'has_import_configs': workspace_summary.get('import_configs', 0) > 0,
            'validation_passed': validation_summary.get('is_valid', False) if selected_files else None,
            'ready_for_import': (
                org_context['organization_id'] is not None and
                len(selected_files) > 0 and
                selected_mapping is not None and
                workspace_summary.get('import_configs', 0) > 0 and
                validation_summary.get('is_valid', False)
            )
        }
        
        # Enhanced context with all new features
        enhanced_context = {
            **org_context,
            **file_browser_context,  # Include enhanced file browser data
            'selected_files': selected_files,
            'selected_files_count': len(selected_files),
            'selected_mapping': selected_mapping,
            'workspace_summary': workspace_summary,
            'validation_summary': validation_summary,
            'readiness_indicators': readiness_indicators,
            
            # Legacy compatibility fields
            'has_files': len(selected_files) > 0,
            'has_mapping': selected_mapping is not None,
            'ready_to_import': readiness_indicators['ready_for_import'],
            
            # Enhancement flag
            'enhanced_context': True
        }
        
        logger.info(f"INGEST_COORDINATOR: Enhanced ingest context for org {org_context['organization_id']} - " +
                   f"Files: {len(selected_files)}, Ready: {readiness_indicators['ready_for_import']}")
        
        return enhanced_context
    
    def reset_ingest_state(self, request):
        """
        Reset all ingest state including workspace items.
        
        Now includes comprehensive cleanup of all ingest-related state including
        selected files, staging files, import configurations, and saved states.
        
        Returns:
            dict: Summary of what was cleared
        """
        logger.info("INGEST_COORDINATOR: Resetting comprehensive ingest state")
        
        # Get current state for summary
        current_org = self.get_current_organization(request)
        if not current_org:
            logger.warning("INGEST_COORDINATOR: No current organization to reset")
            return {
                'organization_cleared': False,
                'files_cleared': 0,
                'mapping_cleared': False,
                'staging_files_cleared': 0,
                'import_configs_cleared': 0,
                'saved_states_cleared': 0
            }
        
        org_id = current_org['id']
        
        # Get current state counts for summary
        selected_files_count = len(self.get_selected_files(request, org_id))
        staging_files_count = len(self.get_staging_files(request, org_id))
        import_configs_count = len(self.get_import_configurations(request, org_id))
        had_mapping = self.get_current_mapping(request) is not None
        
        # Get saved states count
        saved_states_result = self.get_saved_ingest_states(request, org_id)
        saved_states_count = len(saved_states_result.get('states', [])) if saved_states_result.get('success') else 0
        
        # Clear all organization-specific state
        self.clear_organization_specific_state(request, org_id)
        
        # Clear saved states
        if saved_states_count > 0:
            self.clear_ingest_state(request, organization_id=org_id)
        
        # Clear current organization
        self.clear_current_organization(request)
        
        summary = {
            'organization_cleared': True,
            'files_cleared': selected_files_count,
            'mapping_cleared': had_mapping,
            'staging_files_cleared': staging_files_count,
            'import_configs_cleared': import_configs_count,
            'saved_states_cleared': saved_states_count,
            'organization_id': org_id
        }
        
        logger.info(f"INGEST_COORDINATOR: Comprehensive reset complete - {summary}")
        return summary
    
    def clear_organization_specific_state(self, request, organization_id):
        """
        Clear all ingest state specific to an organization.
        
        Overrides BaseCoordinatorMixin to provide comprehensive ingest-specific cleanup
        including selected files, staging files, import configurations, and workspace items.
        
        Args:
            request: Django request object
            organization_id (int): Organization numeric ID to clear state for
        """
        logger.info(f"INGEST_COORDINATOR: Clearing comprehensive organization-specific state for org ID {organization_id}")
        
        # Clear selected files for this specific organization
        self.clear_selected_files(request, organization_id)
        
        # Clear staging files workspace
        self.clear_staging_files(request, organization_id)
        
        # Clear import configurations workspace
        self.clear_workspace_items(request, organization_id, 'import_configs')
        
        # Note: Mapping is now shared and cleared at the base level when organization changes
        
        # Call parent implementation to clear base coordinator state
        super().clear_organization_specific_state(request, organization_id)
        
        logger.info(f"INGEST_COORDINATOR: Comprehensive organization-specific state cleared for org ID {organization_id}")