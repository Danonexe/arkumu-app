"""
CSV Mapping Column Views

This module contains views for column workspace management in the CSV mapping interface:
- Add/remove individual columns to/from workspace
- Select/deselect all columns from a dataset
- Set anchor columns and toggle multi-value columns

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
from django.shortcuts import render
from django.http import HttpResponse
from django.views import View

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class AddColumnToWorkspaceView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Add column to workspace view using coordinator-based architecture.
    
    Uses coordinator for validated column addition with dataset checking and
    template helpers to reduce rendering duplication.
    """
    
    def post(self, request):
        """Handle POST requests for adding columns to workspace with validation."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Handle different POST data formats from the template
            column_name = request.POST.get('column') or request.POST.get('column_name')
            dataset_name = request.POST.get('dataset') or request.POST.get('dataset_name')
            source_name = request.POST.get('source') or request.POST.get('source_name')
            
            # Parse column_id if provided (format: "dataset_source_column")
            column_id = request.POST.get('column_id')
            if column_id and not all([column_name, dataset_name, source_name]):
                parts = column_id.split('_')
                if len(parts) >= 3:
                    dataset_name = parts[0]
                    source_name = parts[1]
                    column_name = '_'.join(parts[2:])  # Column name might contain underscores
            
            if not all([column_name, dataset_name, source_name]):
                return HttpResponse(f'<div class="alert alert-error">Column, dataset, and source parameters required</div>')
            
            # PERFORMANCE OPTIMIZATION: Use safe add method with automatic state correction
            success, new_column, total_columns, error_message = self.safe_add_column_with_validation(
                request, organization_id, column_name, dataset_name, source_name
            )
            
            if not success:
                return HttpResponse(f'<div class="alert alert-warning">{error_message}</div>')
            
            # Get updated dataset with column selection state using template helper
            column_badges_html = self.render_column_badges_template(
                request, organization_id, dataset_name, source_name
            )
            
            # PURE HTMX: Only return column badges, workspace self-refreshes via event
            # The workspace listens for 'workspaceUpdated' events and refreshes itself
            
            # Add workspace update trigger for both workspace and JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_badges_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"ADD_COLUMN: Error adding column to workspace: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class RemoveColumnFromWorkspaceView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Remove column from workspace view using coordinator-based architecture.
    
    Uses coordinator for column removal with dataset relationship awareness and
    template helpers to reduce rendering duplication.
    """
    
    def post(self, request):
        """Handle POST requests for removing columns from workspace."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Handle different POST data formats
            column_name = request.POST.get('column') or request.POST.get('column_name')
            dataset_name = request.POST.get('dataset') or request.POST.get('dataset_name')
            source_name = request.POST.get('source') or request.POST.get('source_name')
            
            if not all([column_name, dataset_name, source_name]):
                return HttpResponse(f'<div class="alert alert-error">Column, dataset, and source parameters required</div>')
            
            # Generate column ID using coordinator format (using organization_id as source)
            column_id = self.generate_column_id(dataset_name, column_name, organization_id)
            
            # Get current workspace columns
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Remove the column - handle both string and dict formats
            updated_columns = []
            for col in workspace_columns:
                if isinstance(col, dict):
                    col_id = col.get('id')
                    if col_id != column_id:
                        updated_columns.append(col)
                else:
                    if col != column_id:
                        updated_columns.append(col)
            self.update_workspace_columns(request, organization_id, updated_columns)
            
            # Return updated column badges HTML with workspace update via hx-swap-oob using template helpers
            column_badges_html = self.render_column_badges_template(
                request, organization_id, dataset_name, source_name
            )
            
            # Render workspace update using template helper
            workspace_html = self.render_workspace_template(request, organization_id)
            
            # Use template helper to build OOB response
            response = self.build_oob_response(column_badges_html, {
                'selected-columns-workspace': workspace_html
            })
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"REMOVE_COLUMN: Error removing column from workspace: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class SelectAllDatasetColumnsView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Select all columns from a dataset using coordinator-based architecture.
    
    Uses coordinator for batch column operations and template helpers for clean response building.
    """
    
    def post(self, request):
        """Handle POST requests for selecting all columns from a dataset."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.POST.get('dataset')
            source_name = request.POST.get('source')
            
            if not dataset_name or not source_name:
                return HttpResponse(f'<div class="alert alert-error">Dataset and source parameters required</div>')
            
            # Safe validation with auto-correction for dataset selection state
            is_valid, was_corrected, status_message = self.validate_and_fix_dataset_selection_state(
                request, organization_id, dataset_name, source_name
            )
            
            if not is_valid:
                return HttpResponse(f'<div class="alert alert-warning">{status_message}</div>')
            
            # Log if auto-correction was applied
            if was_corrected:
                logger.info(f"🔒 SELECT_ALL_COLUMNS: {status_message}")
                # Could optionally show a user-friendly message about the auto-correction
            
            # Get dataset preview to get all column names
            analyzer = S3DirectDataAnalyzer()
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
            
            if not dataset_preview:
                return HttpResponse(f'<div class="alert alert-error">Dataset "{dataset_name}" not found</div>')
            
            # PERFORMANCE OPTIMIZATION: Use batch operation instead of individual column adds
            column_names = dataset_preview.get('columns', [])
            total_added, skipped_duplicates, final_count, error_message = self.batch_add_columns_with_validation(
                request, organization_id, column_names, dataset_name, source_name
            )
            
            if error_message:
                return HttpResponse(f'<div class="alert alert-error">Error: {error_message}</div>')
            
            logger.info(f"🚀 SELECT_ALL_OPTIMIZED: Added {total_added} columns, skipped {skipped_duplicates} duplicates, final count: {final_count}")
            
            # Return updated column badges HTML with workspace update via hx-swap-oob using template helpers
            column_badges_html = self.render_column_badges_template(
                request, organization_id, dataset_name, source_name, dataset_preview
            )
            
            # PURE HTMX: Only return column badges, workspace self-refreshes via event
            # The workspace listens for 'workspaceUpdated' events and refreshes itself
            
            # Add workspace update trigger for both workspace and JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_badges_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"SELECT_ALL_DATASET_COLUMNS: Error selecting all columns: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class DeselectAllDatasetColumnsView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Deselect all columns from a dataset using coordinator-based architecture.
    
    Uses coordinator for batch column removal and template helpers for clean response building.
    """
    
    def post(self, request):
        """Handle POST requests for deselecting all columns from a dataset."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.POST.get('dataset')
            source_name = request.POST.get('source')
            
            if not dataset_name or not source_name:
                return HttpResponse(f'<div class="alert alert-error">Dataset and source parameters required</div>')
            
            # Get current workspace columns using coordinator
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Remove all columns belonging to this dataset using coordinator parsing
            columns_removed = 0
            updated_columns = []
            for col_dict in workspace_columns:
                # Extract the column ID string from the dictionary
                col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                if col_id:
                    parsed = self.parse_column_id(col_id)
                    if parsed['dataset'] == dataset_name and parsed['source'] == source_name:
                        columns_removed += 1
                    else:
                        updated_columns.append(col_dict)
                else:
                    updated_columns.append(col_dict)
            
            # Update workspace using coordinator
            self.update_workspace_columns(request, organization_id, updated_columns)
            
            # Get dataset preview to rebuild column badges using template helper
            column_badges_html = self.render_column_badges_template(
                request, organization_id, dataset_name, source_name
            )
            
            # Get updated workspace columns and filter for this dataset (should be empty now)
            updated_workspace_columns = self.get_workspace_columns(request, organization_id)
            dataset_selected_columns = []
            for col_dict in updated_workspace_columns:
                # Extract the column ID string from the dictionary
                col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                if col_id:
                    parsed = self.parse_column_id(col_id)
                    if parsed['dataset'] == dataset_name and parsed['source'] == source_name:
                        dataset_selected_columns.append(parsed['column'])
            
            # For deselect all: if no columns left, remove the entire dataset section
            # Otherwise, update the specific dataset section to preserve FK forms in other sections
            if not dataset_selected_columns:
                # Dataset section should be removed entirely
                from django.utils.text import slugify
                dataset_section_remove = f'<div id="dataset-workspace-{slugify(dataset_name)}" hx-swap-oob="delete"></div>'
                combined_response = f'{column_badges_html}{dataset_section_remove}'
            else:
                # Update the workspace using template helper
                workspace_html = self.render_workspace_template(request, organization_id)
                combined_response = self.build_oob_response(column_badges_html, {
                    'selected-columns-workspace': workspace_html
                })
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(combined_response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"DESELECT_ALL_DATASET_COLUMNS: Error deselecting all columns: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class SetAnchorColumnView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Set a column as the anchor column using the coordinator mixin.
    Only one column can be anchor at a time.
    
    Uses template helpers to reduce rendering duplication.
    """
    
    def post(self, request):
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"🚨 SET_ANCHOR: Received column_id='{column_id}' for org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="alert alert-error">Missing column_id</div>')
            
            # UNIFIED TRACKING: Use coordinator method to find column (same as FK system)
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                # Also validate workspace for duplicates and auto-clean (same as FK system)
                is_unique, duplicates, cleaned = self.validate_workspace_column_uniqueness(request, organization_id)
                if not is_unique:
                    logger.error(f"CSV_SET_ANCHOR: Found {len(duplicates)} workspace duplicates - auto-cleaned and retrying")
                    column = self.get_unified_column_by_id(request, organization_id, column_id)
                
                if not column:
                    logger.error(f"CSV_SET_ANCHOR: Column '{column_id}' not found even after cleanup")
                    return HttpResponse('<div class="alert alert-error">Column not found in workspace</div>')
            
            # Use mixin method to toggle anchor column (consistent with FK approach)
            success, updated_columns = self.toggle_anchor_column(request, organization_id, column_id)
            
            if not success:
                return HttpResponse('<div class="alert alert-error">Failed to toggle anchor column</div>')
            
            # Find the updated column to return just that column item (like FK save does)
            target_column = next((col for col in updated_columns if col.get('id') == column_id), None)
            if not target_column:
                return HttpResponse('<div class="alert alert-error">Updated column not found</div>')
            
            # Return just the updated column item using template helper
            column_html = self.render_column_item_template(request, organization_id, target_column)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"Error setting anchor column: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class ToggleMultiValueColumnView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Toggle the multi-value status of a column using the coordinator mixin.
    
    Uses template helpers to reduce rendering duplication.
    """
    
    def post(self, request):
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"🚨 TOGGLE_MULTI_VALUE: Received column_id='{column_id}' for org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="alert alert-error">Missing column_id</div>')
            
            # UNIFIED TRACKING: Use coordinator method to find column (same as FK system)
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                # Also validate workspace for duplicates and auto-clean (same as FK system)
                is_unique, duplicates, cleaned = self.validate_workspace_column_uniqueness(request, organization_id)
                if not is_unique:
                    logger.error(f"CSV_TOGGLE_MULTI_VALUE: Found {len(duplicates)} workspace duplicates - auto-cleaned and retrying")
                    column = self.get_unified_column_by_id(request, organization_id, column_id)
                
                if not column:
                    logger.error(f"CSV_TOGGLE_MULTI_VALUE: Column '{column_id}' not found even after cleanup")
                    return HttpResponse('<div class="alert alert-error">Column not found in workspace</div>')
            
            # Use mixin method to toggle multi-value column (consistent with FK approach)
            success, updated_columns = self.toggle_multi_value_column(request, organization_id, column_id)
            
            if not success:
                return HttpResponse('<div class="alert alert-error">Failed to toggle multi-value column</div>')
            
            # Find the updated column to return just that column item (like FK save does)
            updated_column = next((col for col in updated_columns if col.get('id') == column_id), None)
            if not updated_column:
                return HttpResponse('<div class="alert alert-error">Updated column not found</div>')
            
            # Return just the updated column item using template helper
            column_html = self.render_column_item_template(request, organization_id, updated_column)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"Error toggling multi-value column: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>') 