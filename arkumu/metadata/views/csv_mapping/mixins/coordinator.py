"""
Coordinator Mixin for CSV Mapping

This mixin coordinates between CSVDataMixin and MappingWorkspaceMixin to properly
handle the fundamental relationship between datasets and their columns.

Key principles:
- Columns belong to datasets (dataset-column relationship is explicit)
- Dataset deselection cascades to remove related columns
- Column addition validates dataset selection
- Column IDs include dataset context for uniqueness
"""

import logging
from .csv_data import CSVDataMixin
from .workspace import MappingWorkspaceMixin

logger = logging.getLogger(__name__)


class CSVMappingCoordinatorMixin(CSVDataMixin, MappingWorkspaceMixin):
    """
    Coordinator mixin that properly handles dataset-column relationships.
    
    This mixin inherits from both CSVDataMixin and MappingWorkspaceMixin to provide
    coordinated operations that maintain the integrity of dataset-column relationships.
    """
    
    # ==========================================================================
    # Column ID Management (Dataset-Aware)
    # ==========================================================================
    
    @staticmethod
    def generate_column_id(dataset_name, column_name, source_name=None):
        """
        Generate a unique column ID that includes dataset context.
        
        Args:
            dataset_name (str): Name of the dataset
            column_name (str): Name of the column
            source_name (str, optional): Source name for additional context
            
        Returns:
            str: Unique column ID like "dataset.csv::column_name" or "source::dataset.csv::column_name"
        """
        if source_name:
            return f"{source_name}::{dataset_name}::{column_name}"
        return f"{dataset_name}::{column_name}"
    
    @staticmethod
    def parse_column_id(column_id):
        """
        Parse a column ID to extract its components.
        
        Args:
            column_id (str): Column ID to parse
            
        Returns:
            dict: Parsed components with keys: source, dataset, column
        """
        parts = column_id.split("::")
        if len(parts) == 3:
            return {
                'source': parts[0],
                'dataset': parts[1], 
                'column': parts[2]
            }
        elif len(parts) == 2:
            return {
                'source': None,
                'dataset': parts[0],
                'column': parts[1]
            }
        else:
            # Fallback for legacy IDs
            return {
                'source': None,
                'dataset': None,
                'column': column_id
            }
    
    # ==========================================================================
    # Coordinated Dataset Selection (with Column Cascade)
    # ==========================================================================
    
    def toggle_dataset_selection_with_cascade(self, request, organization_id, dataset_name):
        """
        Toggle dataset selection and handle column cascade operations.
        
        When a dataset is deselected, all its columns are automatically removed
        from the workspace to maintain consistency.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            dataset_name (str): Dataset to toggle
            
        Returns:
            tuple: (updated_selected_datasets, was_added, columns_affected)
        """
        logger.info(f"COORDINATOR: Toggling dataset '{dataset_name}' with cascade for org='{organization_id}'")
        
        # Toggle dataset selection using CSVDataMixin
        selected_datasets, was_added = self.toggle_dataset_selection(
            request, organization_id, dataset_name
        )
        
        columns_affected = 0
        
        if not was_added:  # Dataset was REMOVED
            logger.info(f"COORDINATOR: Dataset '{dataset_name}' was deselected, cascading to remove columns")
            columns_affected = self._remove_columns_for_dataset(
                request, organization_id, dataset_name
            )
            logger.info(f"COORDINATOR: Removed {columns_affected} columns for dataset '{dataset_name}'")
        
        return selected_datasets, was_added, columns_affected
    
    def _remove_columns_for_dataset(self, request, organization_id, dataset_name):
        """
        Remove all workspace columns that belong to a specific dataset.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            dataset_name (str): Dataset name
            
        Returns:
            int: Number of columns removed
        """
        workspace_columns = self.get_workspace_columns(request, organization_id)
        initial_count = len(workspace_columns)
        
        # Filter out columns belonging to the deselected dataset
        remaining_columns = [
            col for col in workspace_columns 
            if col.get('dataset') != dataset_name
        ]
        
        # Update workspace
        self.update_workspace_columns(request, organization_id, remaining_columns)
        
        columns_removed = initial_count - len(remaining_columns)
        return columns_removed
    
    # ==========================================================================
    # Coordinated Column Management (with Dataset Validation)
    # ==========================================================================
    
    def add_column_with_validation(self, request, organization_id, column_name, dataset_name, source_name):
        """
        Add a column to workspace with proper dataset validation.
        
        This method ensures that:
        1. The dataset is currently selected
        2. The column ID includes dataset context
        3. The column doesn't already exist
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_name (str): Column name
            dataset_name (str): Dataset name
            source_name (str): Source name
            
        Returns:
            tuple: (success, new_column, total_columns, error_message)
        """
        logger.info(f"🎯 COORDINATOR MIXIN: add_column_with_validation() IS BEING CALLED!")
        logger.info(f"🎯 COORDINATOR: Adding column '{column_name}' from dataset '{dataset_name}' with validation")
        
        # 1. Validate that dataset is selected
        if not self._is_dataset_selected(request, organization_id, dataset_name):
            error_msg = f"Cannot add column '{column_name}': dataset '{dataset_name}' is not selected"
            logger.warning(f"COORDINATOR: {error_msg}")
            return False, None, 0, error_msg
        
        # 2. Generate proper column ID with dataset context
        column_id = self.generate_column_id(dataset_name, column_name, source_name)
        
        # 3. Add column using MappingWorkspaceMixin
        success, new_column, total_columns = self.add_column_to_workspace(
            request, organization_id, column_id, column_name, dataset_name, source_name
        )
        
        if success:
            logger.info(f"COORDINATOR: Successfully added column '{column_id}' to workspace")
            return True, new_column, total_columns, None
        else:
            error_msg = f"Column '{column_id}' already exists in workspace"
            return False, None, total_columns, error_msg
    
    def _is_dataset_selected(self, request, organization_id, dataset_name):
        """
        Check if a dataset is currently selected.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            dataset_name (str): Dataset name to check
            
        Returns:
            bool: True if dataset is selected
        """
        selected_datasets, _ = self.get_selected_datasets_with_details(
            request, organization_id, []  # We only need the selected list, not details
        )
        return dataset_name in selected_datasets
    
    # ==========================================================================
    # Enhanced Workspace Operations (Dataset-Aware)
    # ==========================================================================
    
    def get_columns_by_dataset(self, request, organization_id):
        """
        Get workspace columns grouped by dataset.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            dict: Columns grouped by dataset name
        """
        workspace_columns = self.get_workspace_columns(request, organization_id)
        columns_by_dataset = {}
        
        for col in workspace_columns:
            dataset_name = col.get('dataset', 'unknown')
            if dataset_name not in columns_by_dataset:
                columns_by_dataset[dataset_name] = []
            columns_by_dataset[dataset_name].append(col)
        
        return columns_by_dataset
    
    def get_workspace_summary(self, request, organization_id):
        """
        Get a comprehensive summary of the current workspace state.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            dict: Comprehensive workspace summary
        """
        # Get basic workspace statistics
        workspace_stats = self.get_workspace_statistics(request, organization_id)
        
        # Get columns grouped by dataset
        columns_by_dataset = self.get_columns_by_dataset(request, organization_id)
        
        # Get selected datasets
        selected_datasets, _ = self.get_selected_datasets_with_details(request, organization_id, [])
        
        # Calculate additional metrics
        datasets_with_columns = set(columns_by_dataset.keys())
        orphaned_datasets = datasets_with_columns - set(selected_datasets)
        
        return {
            **workspace_stats,
            'selected_datasets_count': len(selected_datasets),
            'datasets_with_columns': len(datasets_with_columns),
            'columns_by_dataset': {
                dataset: len(columns) for dataset, columns in columns_by_dataset.items()
            },
            'orphaned_datasets': list(orphaned_datasets),  # Datasets with columns but not selected
            'is_consistent': len(orphaned_datasets) == 0,  # True if no orphaned datasets
        }
    
    # ==========================================================================
    # Template Data Preparation
    # ==========================================================================
    
    def _prepare_datasets_with_columns(self, workspace_columns):
        """
        Prepare datasets_with_columns structure for templates.
        
        Args:
            workspace_columns (list): List of workspace column dictionaries
            
        Returns:
            list: Datasets grouped with their columns
        """
        # Group columns by dataset
        datasets_map = {}
        
        for col_dict in workspace_columns:
            if isinstance(col_dict, dict):
                dataset_name = col_dict.get('dataset')
                source_name = col_dict.get('source')
                
                if dataset_name:
                    dataset_key = f"{source_name}::{dataset_name}"
                    
                    if dataset_key not in datasets_map:
                        datasets_map[dataset_key] = {
                            'name': dataset_name,
                            'source': source_name,
                            'selected_count': 0,
                            'columns': []
                        }
                    
                    datasets_map[dataset_key]['columns'].append(col_dict)
                    datasets_map[dataset_key]['selected_count'] += 1
        
        # Convert to list and sort by dataset name
        datasets_with_columns = list(datasets_map.values())
        datasets_with_columns.sort(key=lambda x: x['name'])
        
        return datasets_with_columns

    # ==========================================================================
    # Consistency Maintenance
    # ==========================================================================
    
    def cleanup_orphaned_columns(self, request, organization_id):
        """
        Remove columns from workspace that belong to unselected datasets.
        
        This is a maintenance operation to fix any inconsistencies that might
        have occurred due to previous bugs or data migration.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            tuple: (columns_removed, remaining_columns_count)
        """
        logger.info(f"COORDINATOR: Cleaning up orphaned columns for org='{organization_id}'")
        
        # Get current state
        workspace_columns = self.get_workspace_columns(request, organization_id)
        selected_datasets, _ = self.get_selected_datasets_with_details(request, organization_id, [])
        
        # Find columns from unselected datasets
        valid_columns = [
            col for col in workspace_columns
            if col.get('dataset') in selected_datasets
        ]
        
        columns_removed = len(workspace_columns) - len(valid_columns)
        
        if columns_removed > 0:
            self.update_workspace_columns(request, organization_id, valid_columns)
            logger.info(f"COORDINATOR: Removed {columns_removed} orphaned columns")
        
        return columns_removed, len(valid_columns)
    
    def validate_workspace_consistency(self, request, organization_id):
        """
        Validate that the workspace is in a consistent state.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            tuple: (is_consistent, issues, suggestions)
        """
        workspace_summary = self.get_workspace_summary(request, organization_id)
        
        issues = []
        suggestions = []
        
        # Check for orphaned datasets
        if workspace_summary['orphaned_datasets']:
            issues.append(f"Columns exist for unselected datasets: {workspace_summary['orphaned_datasets']}")
            suggestions.append("Run cleanup_orphaned_columns() to remove orphaned columns")
        
        # Check for empty workspace with selected datasets
        if workspace_summary['selected_datasets_count'] > 0 and workspace_summary['total_columns'] == 0:
            issues.append("Datasets are selected but no columns are in workspace")
            suggestions.append("Add columns from selected datasets to workspace")
        
        # Check for anchor column consistency
        if workspace_summary['anchor_columns'] > 1:
            issues.append(f"Multiple anchor columns found ({workspace_summary['anchor_columns']})")
            suggestions.append("Only one anchor column should be set")
        
        is_consistent = len(issues) == 0
        
        return is_consistent, issues, suggestions 