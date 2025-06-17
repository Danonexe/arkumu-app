"""
Workspace Mixins for CSV Mapping

Contains mixins for handling column workspace and session management:
- MappingWorkspaceMixin: Column workspace and session management functionality
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MappingWorkspaceMixin:
    """
    Mixin for handling column workspace and session management.
    Provides methods for managing selected columns, workspace state, and column configurations.
    """
    
    def get_workspace_columns(self, request, organization_id):
        """
        Get workspace columns from session (single source of truth).
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            list: List of workspace columns
        """
        workspace_key = f"workspace_columns_{organization_id}"
        return request.session.get(workspace_key, [])
    
    def update_workspace_columns(self, request, organization_id, columns):
        """
        Update workspace columns in session.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            columns (list): List of column configurations
        """
        workspace_key = f"workspace_columns_{organization_id}"
        request.session[workspace_key] = columns
        request.session.modified = True
        logger.info(f"WORKSPACE_MIXIN: Updated workspace with {len(columns)} columns for org={organization_id}")
    
    def clear_workspace_columns(self, request, organization_id):
        """
        Clear all workspace columns.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
        """
        workspace_key = f"workspace_columns_{organization_id}"
        request.session[workspace_key] = []
        request.session.modified = True
        logger.info(f"WORKSPACE_MIXIN: Cleared workspace for org={organization_id}")
    
    def add_column_to_workspace(self, request, organization_id, column_id, column_name, dataset_name, source_name):
        """
        Add a column to the mapping workspace.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_id (str): Unique column identifier
            column_name (str): Column name
            dataset_name (str): Dataset name
            source_name (str): Source name
            
        Returns:
            tuple: (success, new_column, total_columns)
        """
        # Get current workspace columns
        existing_columns = self.get_workspace_columns(request, organization_id)
        
        # Debug: Log ALL configurations before adding new column
        fk_columns_before = [col for col in existing_columns if col.get('is_fk', False)]
        anchor_columns_before = [col for col in existing_columns if col.get('is_anchor', False)]
        multi_value_columns_before = [col for col in existing_columns if col.get('is_multi_value', False)]
        
        logger.info(f"🔥🔥🔥 WORKSPACE_MIXIN: BEFORE adding column '{column_id}':")
        logger.info(f"  - Existing columns: {len(existing_columns)}")
        logger.info(f"  - FK columns before: {len(fk_columns_before)}")
        logger.info(f"  - Anchor columns before: {len(anchor_columns_before)}")
        logger.info(f"  - Multi-value columns before: {len(multi_value_columns_before)}")
        
        for col in existing_columns:
            logger.info(f"    - Column '{col.get('id')}': FK={col.get('is_fk', False)}, Anchor={col.get('is_anchor', False)}, Multi={col.get('is_multi_value', False)}, FK_config={col.get('fk_config', {})}")
        
        # Check if column already exists (UNIFIED TRACKING ENFORCEMENT)
        column_exists = any(col.get('id') == column_id for col in existing_columns)
        if column_exists:
            logger.warning(f"🔍 WORKSPACE_MIXIN: DUPLICATE PREVENTED - Column '{column_id}' already exists in workspace")
            # Return the existing column instead of None for consistency
            existing_column = next((col for col in existing_columns if col.get('id') == column_id), None)
            return False, existing_column, len(existing_columns)
        
        # Create new column entry
        new_column = {
            'id': column_id,
            'name': column_name,
            'dataset': dataset_name,
            'source': source_name,
            'type': 'string',  # Could be enhanced with type detection
            'is_fk': False,
            'is_anchor': False,
            'is_multi_value': False,
            'added_at': datetime.now().isoformat()
        }
        
        existing_columns.append(new_column)
        
        # Debug: Log ALL configurations after adding new column
        fk_columns_after = [col for col in existing_columns if col.get('is_fk', False)]
        anchor_columns_after = [col for col in existing_columns if col.get('is_anchor', False)]
        multi_value_columns_after = [col for col in existing_columns if col.get('is_multi_value', False)]
        
        logger.info(f"🔥🔥🔥 WORKSPACE_MIXIN: AFTER adding column '{column_id}':")
        logger.info(f"  - Total columns: {len(existing_columns)}")
        logger.info(f"  - FK columns after: {len(fk_columns_after)}")
        logger.info(f"  - Anchor columns after: {len(anchor_columns_after)}")
        logger.info(f"  - Multi-value columns after: {len(multi_value_columns_after)}")
        
        for col in existing_columns:
            logger.info(f"    - Column '{col.get('id')}': FK={col.get('is_fk', False)}, Anchor={col.get('is_anchor', False)}, Multi={col.get('is_multi_value', False)}, FK_config={col.get('fk_config', {})}")
        
        self.update_workspace_columns(request, organization_id, existing_columns)
        
        logger.info(f"WORKSPACE_MIXIN: Added column {column_id} to workspace")
        return True, new_column, len(existing_columns)
    
    def remove_column_from_workspace(self, request, organization_id, column_id):
        """
        Remove a column from the mapping workspace.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_id (str): Column ID to remove
            
        Returns:
            tuple: (success, total_columns)
        """
        # Get current workspace columns
        existing_columns = self.get_workspace_columns(request, organization_id)
        
        # Remove the column
        updated_columns = [col for col in existing_columns if col.get('id') != column_id]
        
        if len(updated_columns) == len(existing_columns):
            logger.warning(f"WORKSPACE_MIXIN: Column {column_id} not found in workspace")
            return False, len(existing_columns)
        
        self.update_workspace_columns(request, organization_id, updated_columns)
        
        logger.info(f"WORKSPACE_MIXIN: Removed column {column_id} from workspace")
        return True, len(updated_columns)
    
    def update_column_configuration(self, request, organization_id, column_id, **config_updates):
        """
        Update configuration for a specific column.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_id (str): Column ID to update
            **config_updates: Configuration updates (e.g., is_fk=True, is_anchor=True)
            
        Returns:
            tuple: (success, updated_column)
        """
        existing_columns = self.get_workspace_columns(request, organization_id)
        
        # Find and update the column
        updated_column = None
        for col in existing_columns:
            if col.get('id') == column_id:
                col.update(config_updates)
                updated_column = col
                break
        
        if updated_column is None:
            logger.warning(f"WORKSPACE_MIXIN: Column {column_id} not found for configuration update")
            return False, None
        
        self.update_workspace_columns(request, organization_id, existing_columns)
        logger.info(f"WORKSPACE_MIXIN: Updated column {column_id} configuration: {config_updates}")
        return True, updated_column
    
    def set_anchor_column(self, request, organization_id, column_id):
        """
        Set a column as the anchor column (only one anchor allowed).
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_id (str): Column ID to set as anchor
            
        Returns:
            tuple: (success, updated_columns)
        """
        existing_columns = self.get_workspace_columns(request, organization_id)
        
        # Clear all anchors first, then set the new one
        anchor_found = False
        for col in existing_columns:
            if col.get('id') == column_id:
                col['is_anchor'] = True
                anchor_found = True
            else:
                col['is_anchor'] = False
        
        if not anchor_found:
            logger.warning(f"WORKSPACE_MIXIN: Column {column_id} not found for anchor setting")
            return False, existing_columns
        
        self.update_workspace_columns(request, organization_id, existing_columns)
        logger.info(f"WORKSPACE_MIXIN: Set column {column_id} as anchor")
        return True, existing_columns
    
    def get_workspace_statistics(self, request, organization_id):
        """
        Get statistics about the current workspace.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            dict: Workspace statistics
        """
        columns = self.get_workspace_columns(request, organization_id)
        
        stats = {
            'total_columns': len(columns),
            'anchor_columns': len([col for col in columns if col.get('is_anchor', False)]),
            'fk_columns': len([col for col in columns if col.get('is_fk', False)]),
            'multi_value_columns': len([col for col in columns if col.get('is_multi_value', False)]),
            'datasets_represented': len(set(col.get('dataset') for col in columns if col.get('dataset'))),
        }
        
        return stats
    
    def get_dataset_selected_columns(self, request, organization_id, dataset_name, source_name):
        """
        Get selected columns for a specific dataset.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            dataset_name (str): Dataset name
            source_name (str): Source name
            
        Returns:
            list: List of selected column names for the dataset
        """
        workspace_columns = self.get_workspace_columns(request, organization_id)
        return [
            col['name'] for col in workspace_columns 
            if col.get('dataset') == dataset_name and col.get('source') == source_name
        ] 