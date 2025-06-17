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
from django.utils import timezone

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
    
    # ==========================================================================
    # Selected Dataset Retrieval (Direct Session Access)
    # ==========================================================================
    
    def get_selected_dataset_names(self, request, organization_id):
        """
        Get only the selected dataset names from session (lightweight).
        
        This is more efficient than get_selected_datasets_with_details() when
        you only need the names and not the full dataset objects.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            list: List of selected dataset names
        """
        selected_datasets_key = f"selected_datasets_{organization_id}"
        return request.session.get(selected_datasets_key, [])
    
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
        
        # Debug: Log current workspace state before adding column
        current_workspace = self.get_workspace_columns(request, organization_id)
        fk_columns_before = [col for col in current_workspace if col.get('is_fk', False)]
        anchor_columns_before = [col for col in current_workspace if col.get('is_anchor', False)]
        multi_value_columns_before = [col for col in current_workspace if col.get('is_multi_value', False)]
        
        logger.info(f"🔥🔥🔥 COORDINATOR: BEFORE adding column '{column_name}' from '{dataset_name}':")
        logger.info(f"  - Current workspace: {len(current_workspace)} columns")
        logger.info(f"  - FK columns before: {len(fk_columns_before)}")
        logger.info(f"  - Anchor columns before: {len(anchor_columns_before)}")
        logger.info(f"  - Multi-value columns before: {len(multi_value_columns_before)}")
        
        for col in current_workspace:
            logger.info(f"    - Column '{col.get('id')}': FK={col.get('is_fk', False)}, Anchor={col.get('is_anchor', False)}, Multi={col.get('is_multi_value', False)}, FK_config={col.get('fk_config', {})}")
        
        # CRITICAL: Store FK configurations snapshot before adding new column
        fk_configurations_snapshot = {}
        for col in current_workspace:
            if col.get('is_fk', False):
                fk_configurations_snapshot[col.get('id')] = {
                    'is_fk': col.get('is_fk', False),
                    'fk_config': col.get('fk_config', {}),
                }
        logger.info(f"🔥 COORDINATOR: FK SNAPSHOT - {len(fk_configurations_snapshot)} FK configs preserved")
        
        # 1. Validate that dataset is selected
        if not self._is_dataset_selected(request, organization_id, dataset_name):
            error_msg = f"Cannot add column '{column_name}': dataset '{dataset_name}' is not selected"
            logger.warning(f"COORDINATOR: {error_msg}")
            return False, None, 0, error_msg
        
        # 2. Generate proper column ID with dataset context
        column_id = self.generate_column_id(dataset_name, column_name, source_name)
        
        # 2.5. UNIFIED TRACKING: Validate workspace before adding column
        is_unique, duplicates, _ = self.validate_workspace_column_uniqueness(request, organization_id)
        if not is_unique:
            logger.warning(f"🔍 COORDINATOR: Found {len(duplicates)} duplicates before adding '{column_id}' - auto-cleaned")
        
        # 3. Add column using MappingWorkspaceMixin
        success, new_column, total_columns = self.add_column_to_workspace(
            request, organization_id, column_id, column_name, dataset_name, source_name
        )
        
        if success:
            # CRITICAL: Verify FK configurations are still intact after adding column
            updated_workspace = self.get_workspace_columns(request, organization_id)
            fk_columns_after = [col for col in updated_workspace if col.get('is_fk', False)]
            
            logger.info(f"🔥🔥🔥 COORDINATOR: AFTER adding column '{column_name}' to workspace:")
            logger.info(f"  - Total columns: {len(updated_workspace)}")
            logger.info(f"  - FK columns after: {len(fk_columns_after)}")
            
            # Verify FK configurations are preserved
            fk_configs_lost = 0
            for col_id, fk_data in fk_configurations_snapshot.items():
                current_col = next((col for col in updated_workspace if col.get('id') == col_id), None)
                if current_col:
                    if not current_col.get('is_fk', False) or not current_col.get('fk_config', {}):
                        fk_configs_lost += 1
                        logger.error(f"🔥 COORDINATOR: FK CONFIG LOST for column '{col_id}'")
                    else:
                        logger.info(f"🔥 COORDINATOR: FK CONFIG PRESERVED for column '{col_id}': {current_col.get('fk_config', {})}")
                else:
                    logger.error(f"🔥 COORDINATOR: COLUMN LOST: '{col_id}'")
            
            if fk_configs_lost > 0:
                logger.error(f"🔥🔥🔥 COORDINATOR: CRITICAL ERROR - {fk_configs_lost} FK configurations were lost during column addition!")
            else:
                logger.info(f"🔥 COORDINATOR: SUCCESS - All {len(fk_configurations_snapshot)} FK configurations preserved")
            
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
        selected_datasets = self.get_selected_dataset_names(request, organization_id)
        return dataset_name in selected_datasets
    
    # ==========================================================================
    # Unified Column Tracking & Validation (Single Source of Truth)
    # ==========================================================================
    
    def validate_workspace_column_uniqueness(self, request, organization_id):
        """
        Validate that all workspace columns have unique IDs.
        
        UNIFIED TRACKING: Ensures no duplicate column IDs exist in the workspace.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            tuple: (is_unique, duplicates_found, cleaned_columns)
        """
        workspace_columns = self.get_workspace_columns(request, organization_id)
        seen_ids = set()
        duplicates = []
        cleaned_columns = []
        
        for col in workspace_columns:
            if isinstance(col, dict):
                col_id = col.get('id')
                if col_id:
                    if col_id in seen_ids:
                        duplicates.append(col_id)
                        logger.warning(f"🔍 COORDINATOR: DUPLICATE DETECTED: '{col_id}'")
                    else:
                        seen_ids.add(col_id)
                        cleaned_columns.append(col)
                else:
                    logger.warning(f"🔍 COORDINATOR: Column without ID detected: {col}")
            else:
                logger.warning(f"🔍 COORDINATOR: Non-dict column detected: {col}")
        
        is_unique = len(duplicates) == 0
        
        # Auto-clean if duplicates found
        if not is_unique:
            logger.info(f"🔍 COORDINATOR: Auto-cleaning {len(duplicates)} duplicate columns")
            self.update_workspace_columns(request, organization_id, cleaned_columns)
        
        return is_unique, duplicates, cleaned_columns
    
    def get_unified_column_by_id(self, request, organization_id, column_id):
        """
        Get a column by ID from workspace with validation.
        
        UNIFIED TRACKING: Single method to retrieve columns by ID.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            column_id (str): Column ID to find
            
        Returns:
            dict or None: Column dictionary if found
        """
        workspace_columns = self.get_workspace_columns(request, organization_id)
        
        for col in workspace_columns:
            if isinstance(col, dict) and col.get('id') == column_id:
                return col
        
        logger.warning(f"🔍 COORDINATOR: Column '{column_id}' not found in workspace")
        return None

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
        
        # Get selected datasets (names only - more efficient)
        selected_datasets = self.get_selected_dataset_names(request, organization_id)
        
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
        
        UNIFIED TRACKING: This is the single source of truth for rendering datasets with columns.
        Ensures no duplicates and proper column ID consistency.
        
        Args:
            workspace_columns (list): List of workspace column dictionaries
            
        Returns:
            list: Datasets grouped with their columns
        """
        # Group columns by dataset with deduplication
        datasets_map = {}
        column_ids_seen = set()  # Track unique column IDs to prevent duplicates
        
        logger.info(f"🔍 COORDINATOR: _prepare_datasets_with_columns() called with {len(workspace_columns)} columns")
        
        for col_dict in workspace_columns:
            if isinstance(col_dict, dict):
                column_id = col_dict.get('id')
                dataset_name = col_dict.get('dataset')
                source_name = col_dict.get('source')
                
                # Skip invalid columns
                if not column_id or not dataset_name:
                    logger.warning(f"🔍 COORDINATOR: Skipping invalid column: id={column_id}, dataset={dataset_name}")
                    continue
                
                # Skip duplicate column IDs
                if column_id in column_ids_seen:
                    logger.warning(f"🔍 COORDINATOR: DUPLICATE COLUMN ID DETECTED: '{column_id}' - skipping duplicate")
                    continue
                
                column_ids_seen.add(column_id)
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
                
                logger.info(f"🔍 COORDINATOR: Added column '{column_id}' to dataset group '{dataset_key}'")
        
        # Convert to list and sort by dataset name
        datasets_with_columns = list(datasets_map.values())
        datasets_with_columns.sort(key=lambda x: x['name'])
        
        logger.info(f"🔍 COORDINATOR: Prepared {len(datasets_with_columns)} dataset groups with total {len(column_ids_seen)} unique columns")
        
        return datasets_with_columns

    # ==========================================================================
    # Coordinator State Reset (Complete Clear All)
    # ==========================================================================
    
    def reset_all_coordinator_state(self, request, organization_id):
        """
        Completely reset all coordinator state - datasets, columns, and relationships.
        
        UNIFIED RESET: This is the definitive "Clear All" method that resets everything.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            tuple: (datasets_cleared, columns_cleared, summary)
        """
        logger.info(f"🔄 COORDINATOR: COMPLETE STATE RESET for org='{organization_id}'")
        
        # 1. Get current state before reset
        current_workspace = self.get_workspace_columns(request, organization_id)
        selected_datasets = self.get_selected_dataset_names(request, organization_id)
        
        # 2. Clear ALL workspace columns first (most important)
        self.clear_workspace_columns(request, organization_id)
        columns_cleared = len(current_workspace)
        
        # 3. Clear ALL dataset selections
        self.clear_selected_datasets(request, organization_id)
        datasets_cleared = len(selected_datasets)
        
        # 4. Clear any cached FK datasets (optional cleanup)
        self.clear_fk_datasets_cache(request, organization_id)
        
        # 5. Verify complete reset
        final_workspace = self.get_workspace_columns(request, organization_id)
        final_datasets = self.get_selected_dataset_names(request, organization_id)
        
        is_clean = len(final_workspace) == 0 and len(final_datasets) == 0
        
        summary = {
            'datasets_cleared': datasets_cleared,
            'columns_cleared': columns_cleared,
            'is_completely_clean': is_clean,
            'final_workspace_count': len(final_workspace),
            'final_datasets_count': len(final_datasets)
        }
        
        logger.info(f"🔄 COORDINATOR: RESET COMPLETE - Cleared {datasets_cleared} datasets, {columns_cleared} columns, clean={is_clean}")
        
        return datasets_cleared, columns_cleared, summary

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
        selected_datasets = self.get_selected_dataset_names(request, organization_id)
        
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
        
    # ==========================================================================
    # FK Configuration Support (All Available Datasets with Session Caching)
    # ==========================================================================
    
    def get_all_datasets_with_columns_for_fk(self, request, organization_id, force_refresh=False):
        """
        Get ALL available datasets with their columns for FK configuration, with session caching.
        
        This method gets all datasets in the organization (not just selected ones)
        with their column information, formatted for FK form usage. Results are cached
        in session to avoid expensive S3 calls on every FK form open.
        
        Args:
            request: Django request object (for session access)
            organization_id (str): Organization ID
            force_refresh (bool): If True, bypass cache and refresh data
            
        Returns:
            list: All datasets with their column details
        """
        cache_key = f"all_datasets_fk_{organization_id}"
        
        # Check if we have cached data and don't need refresh
        if not force_refresh and cache_key in request.session:
            cached_data = request.session[cache_key]
            logger.info(f"COORDINATOR: Using cached FK datasets data, org='{organization_id}' ({len(cached_data)} datasets)")
            return cached_data
        
        logger.info(f"COORDINATOR: Loading ALL datasets with columns for FK configuration, org='{organization_id}'")
        
        try:
            from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
            analyzer = S3DirectDataAnalyzer()
            
            # Get all sources for the organization
            sources = analyzer.discover_s3_data_sources(organization_id)
            all_datasets_with_columns = []
            
            for source in sources:
                logger.info(f"COORDINATOR: Processing source '{source.name}'")
                
                try:
                    # Get source summary which includes all datasets with previews
                    source_summary = analyzer.get_s3_source_summary(organization_id, source.name)
                    
                    # Process each dataset in the source
                    for dataset_info in source_summary.get('datasets', []):
                        dataset_name = dataset_info.get('name')
                        
                        # Only include CSV-compatible datasets
                        if self._is_csv_dataset(dataset_name, source):
                            dataset_with_columns = {
                                'name': dataset_name,
                                'source': source.name,
                                'preview': {
                                    'colHeaders': dataset_info.get('columns', []),
                                    'data': dataset_info.get('sample_data', []),
                                    'total_rows': dataset_info.get('row_count', 0),
                                }
                            }
                            all_datasets_with_columns.append(dataset_with_columns)
                            
                except Exception as e:
                    logger.warning(f"COORDINATOR: Error processing source '{source.name}': {e}")
                    continue
            
            # Cache the results in session
            request.session[cache_key] = all_datasets_with_columns
            request.session.modified = True
            
            logger.info(f"COORDINATOR: Loaded and cached {len(all_datasets_with_columns)} datasets with columns for FK")
            return all_datasets_with_columns
            
        except Exception as e:
            logger.error(f"COORDINATOR: Error getting all datasets with columns: {e}", exc_info=True)
            return []
    
    def clear_fk_datasets_cache(self, request, organization_id):
        """
        Clear the cached FK datasets data for an organization.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
        """
        cache_key = f"all_datasets_fk_{organization_id}"
        if cache_key in request.session:
            del request.session[cache_key]
            request.session.modified = True
            logger.info(f"COORDINATOR: Cleared FK datasets cache for org='{organization_id}'")
    
    def refresh_fk_datasets_cache(self, request, organization_id):
        """
        Refresh the cached FK datasets data for an organization.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            list: Refreshed datasets data
        """
        logger.info(f"COORDINATOR: Refreshing FK datasets cache for org='{organization_id}'")
        return self.get_all_datasets_with_columns_for_fk(request, organization_id, force_refresh=True)
            
    def _is_csv_dataset(self, dataset_name, source):
        """
        Check if a dataset is a CSV/parseable format.
        
        Args:
            dataset_name (str): Name of the dataset
            source: Source object with format information
            
        Returns:
            bool: True if dataset is CSV-compatible
        """
        dataset_lower = dataset_name.lower()
        return (dataset_lower.endswith(('.csv', '.tsv', '.txt')) or 
                'csv' in dataset_lower or 
                (source.format and source.format.lower() in ['csv', 'tsv', 'text']))

    # ==========================================================================
    # Mapping Persistence (Save/Load State)
    # ==========================================================================
    
    def serialize_current_mapping_state(self, request, organization_id, mapping_name=None):
        """
        Serialize current coordinator state to a mapping configuration.
        
        This captures all current UI state including selected datasets,
        workspace columns, FK relationships, and entity configurations.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            mapping_name (str, optional): Name for the mapping
            
        Returns:
            dict: Serialized mapping configuration suitable for Mapping.mapping_config
        """
        logger.info(f"SERIALIZE_MAPPING: Starting serialization for organization {organization_id}")
        
        # Get current state
        selected_datasets = self.get_selected_dataset_names(request, organization_id)
        workspace_columns = self.get_workspace_columns(request, organization_id)
        
        # Serialize FK relationships from workspace columns
        fk_relationships = {}
        entity_mappings = {}
        
        for column_id, column_data in workspace_columns.items():
            # Extract FK configurations
            if column_data.get('fk_config'):
                fk_relationships[column_id] = {
                    'target_dataset': column_data['fk_config'].get('target_dataset'),
                    'target_column': column_data['fk_config'].get('target_column'),
                    'display_column': column_data['fk_config'].get('display_column'),
                    'relationship_type': column_data['fk_config'].get('relationship_type', 'reference')
                }
            
            # Extract RDF predicate mappings (if any)
            if column_data.get('rdf_predicate'):
                if 'predicate_mappings' not in entity_mappings:
                    entity_mappings['predicate_mappings'] = {}
                entity_mappings['predicate_mappings'][column_id] = column_data['rdf_predicate']
            
            # Extract subject column designation (if any)
            if column_data.get('is_subject_column'):
                entity_mappings['subject_column'] = column_id
        
        # Build complete mapping configuration
        mapping_config = {
            'version': '1.0',
            'created_at': timezone.now().isoformat(),
            'organization_id': organization_id,
            'selected_datasets': selected_datasets,
            'workspace_columns': workspace_columns,
            'fk_relationships': fk_relationships,
            'entity_mappings': entity_mappings,
            'metadata': {
                'total_datasets': len(selected_datasets),
                'total_columns': len(workspace_columns),
                'total_fk_relationships': len(fk_relationships),
                'mapping_name': mapping_name or f"Mapping_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
            }
        }
        
        logger.info(f"SERIALIZE_MAPPING: Serialized {len(selected_datasets)} datasets, {len(workspace_columns)} columns, {len(fk_relationships)} FK relationships")
        return mapping_config
    
    def deserialize_mapping_state(self, request, organization_id, mapping_config):
        """
        Restore coordinator state from a mapping configuration.
        
        This loads a saved mapping and restores all UI state including
        selected datasets, workspace columns, and FK relationships.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            mapping_config (dict): Mapping configuration from Mapping.mapping_config
            
        Returns:
            dict: Summary of restored state
        """
        logger.info(f"DESERIALIZE_MAPPING: Starting deserialization for organization {organization_id}")
        
        # Validate mapping config
        if not mapping_config or mapping_config.get('organization_id') != organization_id:
            raise ValueError(f"Invalid mapping config for organization {organization_id}")
        
        # Clear current state first
        self.reset_all_coordinator_state(request, organization_id)
        
        # Restore selected datasets
        selected_datasets = mapping_config.get('selected_datasets', [])
        if selected_datasets:
            selected_datasets_key = f"selected_datasets_{organization_id}"
            request.session[selected_datasets_key] = selected_datasets
            logger.info(f"DESERIALIZE_MAPPING: Restored {len(selected_datasets)} selected datasets")
        
        # Restore workspace columns
        workspace_columns = mapping_config.get('workspace_columns', {})
        if workspace_columns:
            workspace_key = f"workspace_columns_{organization_id}"
            request.session[workspace_key] = workspace_columns
            logger.info(f"DESERIALIZE_MAPPING: Restored {len(workspace_columns)} workspace columns")
        
        # Save session changes
        request.session.modified = True
        
        # Build restoration summary
        fk_relationships = mapping_config.get('fk_relationships', {})
        metadata = mapping_config.get('metadata', {})
        
        summary = {
            'datasets_restored': len(selected_datasets),
            'columns_restored': len(workspace_columns),
            'fk_relationships_restored': len(fk_relationships),
            'mapping_name': metadata.get('mapping_name', 'Unknown'),
            'original_created_at': mapping_config.get('created_at'),
            'version': mapping_config.get('version', 'Unknown')
        }
        
        logger.info(f"DESERIALIZE_MAPPING: Successfully restored mapping '{summary['mapping_name']}' with {summary['datasets_restored']} datasets and {summary['columns_restored']} columns")
        return summary
    
    def validate_mapping_compatibility(self, request, organization_id, mapping_config):
        """
        Validate that a mapping configuration is compatible with current datasets.
        
        This checks if the datasets and columns referenced in the mapping
        are still available in the current organization context.
        
        Args:
            request: Django request object  
            organization_id (str): Organization ID
            mapping_config (dict): Mapping configuration to validate
            
        Returns:
            dict: Validation results with warnings/errors
        """
        logger.info(f"VALIDATE_MAPPING: Validating mapping compatibility for organization {organization_id}")
        
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'errors': [],
            'missing_datasets': [],
            'missing_columns': []
        }
        
        # Get available datasets for this organization
        try:
            available_datasets = self.get_csv_datasets_for_organization(organization_id)
            available_dataset_names = [ds['name'] for ds in available_datasets]
        except Exception as e:
            validation_result['errors'].append(f"Failed to get available datasets: {str(e)}")
            validation_result['is_valid'] = False
            return validation_result
        
        # Check dataset availability
        required_datasets = mapping_config.get('selected_datasets', [])
        for dataset_name in required_datasets:
            if dataset_name not in available_dataset_names:
                validation_result['missing_datasets'].append(dataset_name)
                validation_result['is_valid'] = False
        
        # Check column availability
        workspace_columns = mapping_config.get('workspace_columns', {})
        for column_id in workspace_columns.keys():
            # Parse column ID: "source::dataset::column_name"
            parts = column_id.split('::', 2)
            if len(parts) == 3:
                source, dataset_name, column_name = parts
                if dataset_name not in available_dataset_names:
                    validation_result['missing_columns'].append(column_id)
                    if dataset_name not in validation_result['missing_datasets']:
                        validation_result['missing_datasets'].append(dataset_name)
        
        # Generate warnings/errors
        if validation_result['missing_datasets']:
            validation_result['errors'].append(f"Missing datasets: {', '.join(validation_result['missing_datasets'])}")
            validation_result['is_valid'] = False
        
        if validation_result['missing_columns']:
            validation_result['warnings'].append(f"Some columns may not be available: {len(validation_result['missing_columns'])} columns")
        
        logger.info(f"VALIDATE_MAPPING: Validation result - Valid: {validation_result['is_valid']}, Warnings: {len(validation_result['warnings'])}, Errors: {len(validation_result['errors'])}")
        return validation_result