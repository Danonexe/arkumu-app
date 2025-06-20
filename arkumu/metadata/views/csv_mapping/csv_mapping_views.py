"""
CSV Mapping Views - Coordinator-Based Architecture

This module contains views for the CSV mapping editor that use a coordinator mixin
to properly handle dataset-column relationships and state consistency.

ARCHITECTURE STATUS:
✅ Step 1: Main editor view → Uses CSVMappingCoordinatorMixin 
✅ Step 2: Dataset card views → IMPLEMENTED with cascade functionality
✅ Step 3: Column workspace management → IMPLEMENTED with validation
⏳ Step 4: FK relationship configuration

KEY INNOVATION: CSVMappingCoordinatorMixin enforces dataset-column relationships:
- Column IDs include dataset context (dataset.csv::column_name)
- Dataset deselection cascades to remove related columns  
- Column addition validates dataset selection
- Consistency checking and maintenance operations
"""

import logging
import json
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.core.serializers.json import DjangoJSONEncoder
from django.template.loader import render_to_string
from django.utils import timezone

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer, S3DataSourceInfo


from .mixins import OrganizationMixin, CSVDataMixin, MappingWorkspaceMixin, ImportStrategyMixin, CSVMappingCoordinatorMixin

logger = logging.getLogger(__name__)


# ==============================================================================
# STEP 1: Main CSV Mapping Editor View (Mixin-Based Architecture)
# ==============================================================================

class CSVMappingEditorView(OrganizationMixin, CSVMappingCoordinatorMixin, ImportStrategyMixin, View):
    """
    Main CSV mapping editor view using coordinator-based architecture.
    
    REFACTORED FROM: csv_mapping_editor_view function
    ARCHITECTURE: Uses coordinator mixin for proper dataset-column relationships:
    - OrganizationMixin: Organization discovery and management
    - CSVMappingCoordinatorMixin: Coordinates CSV data + workspace with dataset-column relationships
    - ImportStrategyMixin: Import configuration and strategy management
    
    The coordinator mixin inherits from CSVDataMixin and MappingWorkspaceMixin, 
    providing all their functionality plus relationship management.
    """
    
    template_name = 'csv_mapping/main_editor.html'
    
    def get(self, request):
        """Handle GET requests for the CSV mapping editor."""
        try:
            logger.info(f"🚀 CSV_MAPPING_EDITOR: CSV mapping editor called! 🚀")
            logger.info(f"CSV_MAPPING_EDITOR: Method={request.method}, GET params={dict(request.GET)}")
            
            # Get organization context using OrganizationMixin
            org_context = self.get_organization_context(request)
            organization_id = org_context['organization_id']
            
            # Handle case where no valid organization is provided
            if not org_context['organization_exists']:
                if not organization_id or organization_id == 'default-org':
                    error_msg = 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL (e.g., ?organization=rsh)'
                else:
                    available_orgs = ", ".join([org["id"] for org in org_context['organizations']])
                    error_msg = f'Organization "{organization_id}" not found in S3. Available organizations: {available_orgs}'
                
                context = {
                    **org_context,
                    'sources': [],
                    'selected_source': '',
                    'error': error_msg,
                    'show_organization_help': True
                }
                return render(request, self.template_name, context)
            
            # Discover CSV datasets using CSVDataMixin
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            logger.info(f"CSV_MAPPING_EDITOR: Found {len(csv_datasets)} CSV datasets")
            
            # Get selected datasets and workspace columns using mixins
            selected_datasets, selected_datasets_with_details = self.get_selected_datasets_with_details(
                request, organization_id, csv_datasets
            )
            selected_columns = self.get_workspace_columns(request, organization_id)
            
            # Get import strategy using ImportStrategyMixin
            import_strategy = self.get_import_strategy(request, organization_id)
            import_strategy_summary = self.get_import_strategy_summary(request, organization_id)
            
            # Get enhanced workspace summary using coordinator
            workspace_summary = self.get_workspace_summary(request, organization_id)
            
            # Build complete context
            context = {
                **org_context,
                'datasets': csv_datasets,  # For template compatibility
                'csv_datasets': csv_datasets,
                'selected_datasets': selected_datasets,
                'selected_datasets_with_details': selected_datasets_with_details,
                'selected_columns': selected_columns,
                'import_strategy': import_strategy,
                'import_strategy_summary': import_strategy_summary,
                'workspace_summary': workspace_summary,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Handle HTMX requests - return just the partial content
            if request.headers.get('HX-Request'):
                # Check if this is a tab request
                tab = request.GET.get('tab')
                if tab == 'workspace':
                    # Return just the workspace content for tab switching
                    workspace_context = {
                        'datasets_with_columns': self._prepare_datasets_with_columns(selected_columns),
                        'organization_id': organization_id,
                        'csrf_token': request.META.get('CSRF_COOKIE'),
                    }
                    return render(request, 'csv_mapping/partials/selected_columns_workspace.html', workspace_context)
                else:
                    # Return main content for other HTMX requests
                    return render(request, 'csv_mapping/partials/main_content.html', context)
            else:
                return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"CSV_MAPPING_EDITOR: Error loading editor: {e}", exc_info=True)
            context = {
                'organizations': [],
                'error': f'Error loading CSV mapping editor: {str(e)}'
            }
            return render(request, self.template_name, context)


# ==============================================================================
# Function-based view wrapper for URL compatibility
# ==============================================================================

def csv_mapping_editor_view(request):
    """
    Function-based wrapper for the class-based CSVMappingEditorView.
    Maintains compatibility with existing URL patterns.
    """
    view = CSVMappingEditorView()
    return view.get(request)


# ==============================================================================
# STEP 2: Dataset Card Views (To be implemented using mixins)
# ==============================================================================

class CSVDatasetCardView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    CSV dataset card view using coordinator-based architecture.
    
    TODO: Implement in Step 2
    USES: CSVMappingCoordinatorMixin for dataset preview + workspace with relationship integrity
    """
    
    def get(self, request):
        """Handle GET requests for dataset card preview."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.GET.get('dataset_name') or request.GET.get('dataset')
            source_name = request.GET.get('source')
            
            if not dataset_name or not source_name:
                return HttpResponse('<div class="text-danger">Dataset and source parameters required</div>')
            
            # Use S3DirectDataAnalyzer to get the full dataset preview
            analyzer = S3DirectDataAnalyzer()
            
            # Get the source summary which contains dataset previews
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Find the specific dataset in the source
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
            
            if not dataset_preview or 'error' in dataset_preview:
                return HttpResponse(f'<div class="text-danger">Failed to load dataset "{dataset_name}" from source "{source_name}"</div>')
            
            # Transform the data to match the template expectations
            dataset = {
                'name': dataset_name,
                'source': source_name,
                'cell_count': dataset_preview.get('row_count', 0) * dataset_preview.get('column_count', 0),
                'preview': {
                    'colHeaders': dataset_preview.get('columns', []),
                    'data': dataset_preview.get('sample_data', []),
                    'total_rows': dataset_preview.get('row_count', 0),
                    'showing_rows': len(dataset_preview.get('sample_data', [])),
                    'has_more': dataset_preview.get('row_count', 0) > len(dataset_preview.get('sample_data', [])),
                }
            }
            
            # Get selected columns for this dataset using coordinator
            selected_columns = self.get_workspace_columns(request, organization_id)
            
            # Filter to get only columns from this specific dataset using coordinator column ID format
            dataset_selected_columns = []
            for col_id in selected_columns:
                # Parse the coordinator column ID format: "source::dataset.csv::column_name"
                parsed = self.parse_column_id(col_id)
                if parsed and parsed['dataset'] == dataset_name and parsed['source'] == organization_id:
                    dataset_selected_columns.append(parsed['column'])
            
            context = {
                'dataset': dataset,
                'selected_columns': selected_columns,
                'dataset_selected_columns': dataset_selected_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
                'is_direct_mode': True,  # For the template logic
            }
            
            return render(request, 'csv_mapping/partials/dataset_card.html', context)
            
        except Exception as e:
            logger.error(f"DATASET_CARD: Error loading dataset card: {e}", exc_info=True)
            return HttpResponse(f'<div class="text-danger">Error: {str(e)}</div>')


class ToggleDatasetSelectionView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Toggle dataset selection view using coordinator-based architecture.
    
    TODO: Implement in Step 2  
    USES: CSVMappingCoordinatorMixin for dataset management with column cascade
    """
    
    def post(self, request):
        """Handle POST requests for toggling dataset selection with cascade."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.POST.get('dataset')
            action = request.POST.get('action', 'toggle')  # 'add', 'remove', or 'toggle'
            
            if not dataset_name:
                return JsonResponse({'status': 'error', 'message': 'Dataset parameter required'}, status=400)
            
            # Use coordinator for dataset toggle with column cascade
            selected_datasets, was_added, columns_affected = self.toggle_dataset_selection_with_cascade(
                request, organization_id, dataset_name
            )
            
            # Get updated datasets and workspace information
            workspace_summary = self.get_workspace_summary(request, organization_id)
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            selected_datasets_new, selected_datasets_with_details = self.get_selected_datasets_with_details(
                request, organization_id, csv_datasets
            )
            
            # ENHANCEMENT: Load full preview data for each selected dataset
            enhanced_datasets_with_details = []
            analyzer = S3DirectDataAnalyzer()
            
            # Get workspace columns for dataset-specific column selection info
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            for dataset in selected_datasets_with_details:
                try:
                    # Get the full dataset preview using the same logic as CSVDatasetCardView
                    source_summary = analyzer.get_s3_source_summary(organization_id, dataset['source'])
                    
                    # Find the specific dataset in the source
                    dataset_preview = None
                    for dataset_info in source_summary.get('datasets', []):
                        if dataset_info.get('name') == dataset['name']:
                            dataset_preview = dataset_info
                            break
                    
                    if dataset_preview and 'error' not in dataset_preview:
                        # Get selected columns for this specific dataset using coordinator parsing
                        dataset_selected_columns = []
                        for col_dict in workspace_columns:
                            # Extract the column ID string from the dictionary
                            col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                            if col_id:
                                                            parsed = self.parse_column_id(col_id)
                            if parsed['dataset'] == dataset['name'] and parsed['source'] == organization_id:
                                    dataset_selected_columns.append(parsed['column'])
                        
                        # Transform to match template expectations
                        enhanced_dataset = {
                            **dataset,  # Keep original data
                            'cell_count': dataset_preview.get('row_count', 0) * dataset_preview.get('column_count', 0),
                            'dataset_selected_columns': dataset_selected_columns,  # ADD THIS
                            'preview': {
                                'colHeaders': dataset_preview.get('columns', []),
                                'data': dataset_preview.get('sample_data', []),
                                'total_rows': dataset_preview.get('row_count', 0),
                                'showing_rows': len(dataset_preview.get('sample_data', [])),
                                'has_more': dataset_preview.get('row_count', 0) > len(dataset_preview.get('sample_data', [])),
                            }
                        }
                        enhanced_datasets_with_details.append(enhanced_dataset)
                    else:
                        # Fallback: dataset without preview (will trigger lazy loading)
                        enhanced_datasets_with_details.append(dataset)
                        
                except Exception as e:
                    logger.warning(f"TOGGLE_DATASET: Could not load preview for {dataset['name']}: {e}")
                    # Fallback: dataset without preview
                    enhanced_datasets_with_details.append(dataset)
            
            # Build context for both table content and dataset badges
            context = {
                'selected_datasets_with_details': enhanced_datasets_with_details,  # Use enhanced data
                'datasets': csv_datasets,  # For dataset badges
                'csv_datasets': csv_datasets,  # For template compatibility
                'selected_datasets': selected_datasets_new,  # Updated selection list
                'selected_columns': workspace_columns,  # Global selected columns
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
                'was_added': was_added,
                'dataset_name': dataset_name,
            }
            
            # Handle different actions for pure HTMX approach
            if action == 'add' and was_added:
                # Return only the single new dataset card for prepending
                new_dataset = None
                for dataset in enhanced_datasets_with_details:
                    if dataset['name'] == dataset_name:
                        new_dataset = dataset
                        break
                
                if new_dataset:
                    single_context = {
                        **context,
                        'dataset': new_dataset,
                        'dataset_selected_columns': new_dataset.get('dataset_selected_columns', [])
                    }
                    single_card = render_to_string('csv_mapping/partials/dataset_card.html', single_context, request=request)
                    
                    # Update badges via OOB
                    dataset_badges = render_to_string('csv_mapping/partials/dataset_badges.html', context, request=request)
                    
                    response_html = f'{single_card}<div id="dataset-badges" hx-swap-oob="innerHTML">{dataset_badges}</div>'
                    return HttpResponse(response_html)
            
            elif action == 'remove' and not was_added:
                # Return empty response - HTMX will delete the target element
                # Update badges via OOB
                dataset_badges = render_to_string('csv_mapping/partials/dataset_badges.html', context, request=request)
                
                # Check if no datasets remain, show empty state
                if not enhanced_datasets_with_details:
                    empty_state = render_to_string('csv_mapping/partials/table_content.html', context, request=request)
                    response_html = f'{empty_state}<div id="dataset-badges" hx-swap-oob="innerHTML">{dataset_badges}</div>'
                    return HttpResponse(response_html)
                else:
                    response_html = f'<div id="dataset-badges" hx-swap-oob="innerHTML">{dataset_badges}</div>'
                    return HttpResponse(response_html)
            
            # Fallback: return full table content (for 'toggle' or error cases)
            table_content = render_to_string('csv_mapping/partials/table_content.html', context, request=request)
            
            # Update dataset badges via OOB
            dataset_badges = render_to_string('csv_mapping/partials/dataset_badges.html', context, request=request)
            
            response_html = f'{table_content}<div id="dataset-badges" hx-swap-oob="innerHTML">{dataset_badges}</div>'
            
            return HttpResponse(response_html)
            
        except Exception as e:
            logger.error(f"TOGGLE_DATASET: Error toggling dataset selection: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# STEP 3: Column Workspace Management Views (To be implemented using mixins)
# ==============================================================================

class AddColumnToWorkspaceView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Add column to workspace view using coordinator-based architecture.
    
    TODO: Implement in Step 3
    USES: CSVMappingCoordinatorMixin for validated column addition with dataset checking
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
            
            # Get updated dataset with column selection state
            analyzer = S3DirectDataAnalyzer()
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Find the dataset and get its column info
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
            
            if not dataset_preview:
                return HttpResponse(f'<div class="alert alert-error">Dataset not found</div>')
            
            # Get workspace columns and filter for this dataset
            workspace_columns = self.get_workspace_columns(request, organization_id)
            dataset_selected_columns = []
            for col_dict in workspace_columns:
                # Extract the column ID string from the dictionary
                col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                if col_id:
                    parsed = self.parse_column_id(col_id)
                    if parsed['dataset'] == dataset_name and parsed['source'] == source_name:
                        dataset_selected_columns.append(parsed['column'])
            
            # Build dataset context for column badges template
            dataset_context = {
                'name': dataset_name,
                'source': source_name,
                'preview': {
                    'colHeaders': dataset_preview.get('columns', [])
                }
            }
            
            context = {
                'dataset': dataset_context,
                'dataset_selected_columns': dataset_selected_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated column badges HTML with workspace update via hx-swap-oob
            from django.template.loader import render_to_string
            
            # Prepare workspace update data efficiently
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            # DEBUG: Verify workspace template data
            logger.info(f"🔍 SELECT_ALL_DEBUG: Workspace template will receive {len(datasets_with_columns)} dataset groups:")
            for i, group in enumerate(datasets_with_columns):
                logger.info(f"  [{i}] Dataset '{group['name']}' (source: {group['source']}) with {len(group.get('columns', []))} columns")
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # SIMPLIFIED APPROACH: Always update the entire workspace for reliability
            # This ensures the workspace shows newly added columns even when starting from empty state
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            combined_response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(combined_response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"ADD_COLUMN: Error adding column to workspace: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class RemoveColumnFromWorkspaceView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Remove column from workspace view using coordinator-based architecture.
    
    COORDINATOR IMPLEMENTATION: Remove columns with dataset relationship awareness
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
            
            # Get updated dataset with column selection state
            analyzer = S3DirectDataAnalyzer()
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Find the dataset and get its column info
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
            
            if not dataset_preview:
                return HttpResponse(f'<div class="alert alert-error">Dataset not found</div>')
            
            # Get updated workspace columns and filter for this dataset
            updated_workspace_columns = self.get_workspace_columns(request, organization_id)
            dataset_selected_columns = []
            for col_dict in updated_workspace_columns:
                # Extract the column ID string from the dictionary
                col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                if col_id:
                    parsed = self.parse_column_id(col_id)
                    if parsed['dataset'] == dataset_name and parsed['source'] == source_name:
                        dataset_selected_columns.append(parsed['column'])
            
            # Build dataset context for column badges template
            dataset_context = {
                'name': dataset_name,
                'source': source_name,
                'preview': {
                    'colHeaders': dataset_preview.get('columns', [])
                }
            }
            
            context = {
                'dataset': dataset_context,
                'dataset_selected_columns': dataset_selected_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated column badges HTML with workspace update via hx-swap-oob
            from django.template.loader import render_to_string
            
            # Prepare workspace update data
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # DEBUG: Log FK configurations before preparing datasets
            logger.info(f"🔥 ADD_COLUMN DEBUG: Workspace has {len(workspace_columns)} columns before rendering:")
            fk_columns = [col for col in workspace_columns if col.get('is_fk')]
            logger.info(f"🔥 ADD_COLUMN DEBUG: Found {len(fk_columns)} FK columns:")
            for col in fk_columns:
                logger.info(f"  - {col.get('id')} has FK config: {col.get('fk_config')}")
            
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            # DEBUG: Log FK configurations after preparing datasets
            logger.info(f"🔥 ADD_COLUMN DEBUG: After preparing datasets, found {len(datasets_with_columns)} dataset groups:")
            for dataset_group in datasets_with_columns:
                fk_columns_in_group = [col for col in dataset_group['columns'] if col.get('is_fk')]
                logger.info(f"  - Dataset '{dataset_group['name']}' has {len(fk_columns_in_group)} FK columns:")
                for col in fk_columns_in_group:
                    logger.info(f"    - {col.get('id')} has FK config: {col.get('fk_config')}")
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # Render workspace update
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Return workspace update as main response + column badges update via OOB
            # The workspace remove button targets the individual column, so we need to return empty content
            # plus update both the workspace and the corresponding dataset's column badges
            workspace_update = f'<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            # Use Django's slugify to match template format
            from django.utils.text import slugify
            column_badges_update = f'<div id="column-badges-{slugify(dataset_name)}" hx-swap-oob="innerHTML">{column_badges_html}</div>'
            
            # Use the same pattern as working views - return column badges as main response
            # The workspace update happens via OOB
            response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"REMOVE_COLUMN: Error removing column from workspace: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class SelectAllDatasetColumnsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Select all columns from a dataset using coordinator-based architecture.
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
            
            # DEBUG: Verify workspace state after batch operation
            workspace_columns_after = self.get_workspace_columns(request, organization_id)
            dataset_columns_after = [col for col in workspace_columns_after if isinstance(col, dict) and col.get('dataset') == dataset_name]
            logger.info(f"🔍 SELECT_ALL_DEBUG: After batch operation - workspace has {len(workspace_columns_after)} total columns")
            logger.info(f"🔍 SELECT_ALL_DEBUG: Dataset '{dataset_name}' now has {len(dataset_columns_after)} columns in workspace")
            
            # Get updated workspace columns and filter for this dataset
            workspace_columns = self.get_workspace_columns(request, organization_id)
            dataset_selected_columns = []
            for col_dict in workspace_columns:
                # Extract the column ID string from the dictionary
                col_id = col_dict.get('id') if isinstance(col_dict, dict) else col_dict
                if col_id:
                    parsed = self.parse_column_id(col_id)
                    if parsed['dataset'] == dataset_name and parsed['source'] == organization_id:
                        dataset_selected_columns.append(parsed['column'])
            
            logger.info(f"🔍 SELECT_ALL_DEBUG: Found {len(dataset_selected_columns)} selected columns for badge rendering: {dataset_selected_columns}")
            
            # Build dataset context for column badges template
            dataset_context = {
                'name': dataset_name,
                'source': source_name,
                'preview': {
                    'colHeaders': dataset_preview.get('columns', [])
                }
            }
            
            context = {
                'dataset': dataset_context,
                'dataset_selected_columns': dataset_selected_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated column badges HTML with workspace update via hx-swap-oob
            from django.template.loader import render_to_string
            
            # Prepare workspace update data efficiently
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            # DEBUG: Verify workspace template data
            logger.info(f"🔍 SELECT_ALL_DEBUG: Workspace template will receive {len(datasets_with_columns)} dataset groups:")
            for i, group in enumerate(datasets_with_columns):
                logger.info(f"  [{i}] Dataset '{group['name']}' (source: {group['source']}) with {len(group.get('columns', []))} columns")
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # SIMPLIFIED APPROACH: Always update the entire workspace for reliability
            # This ensures the workspace shows newly added columns even when starting from empty state
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            combined_response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(combined_response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"SELECT_ALL_DATASET_COLUMNS: Error selecting all columns: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


class DeselectAllDatasetColumnsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Deselect all columns from a dataset using coordinator-based architecture.
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
            
            # Get dataset preview to rebuild column badges
            analyzer = S3DirectDataAnalyzer()
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
            
            if not dataset_preview:
                return HttpResponse(f'<div class="alert alert-error">Dataset not found</div>')
            
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
            
            # Build dataset context for column badges template
            dataset_context = {
                'name': dataset_name,
                'source': source_name,
                'preview': {
                    'colHeaders': dataset_preview.get('columns', [])
                }
            }
            
            context = {
                'dataset': dataset_context,
                'dataset_selected_columns': dataset_selected_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated column badges HTML with workspace update via hx-swap-oob
            from django.template.loader import render_to_string
            
            # Prepare workspace update data efficiently
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # For deselect all: if no columns left, remove the entire dataset section
            # Otherwise, update the specific dataset section to preserve FK forms in other sections
            if not dataset_selected_columns:
                # Dataset section should be removed entirely
                from django.utils.text import slugify
                dataset_section_remove = f'<div id="dataset-workspace-{slugify(dataset_name)}" hx-swap-oob="delete"></div>'
                combined_response = f'{column_badges_html}{dataset_section_remove}'
            else:
                # Update the specific dataset section instead of the entire workspace
                specific_dataset_group = None
                for group in datasets_with_columns:
                    if group['name'] == dataset_name and group['source'] == source_name:
                        specific_dataset_group = group
                        break
                
                if specific_dataset_group:
                    # Render only the specific dataset section
                    dataset_section_context = {
                        'dataset_group': specific_dataset_group,
                        'organization_id': organization_id,
                        'csrf_token': request.META.get('CSRF_COOKIE'),
                    }
                    dataset_section_html = render_to_string('csv_mapping/partials/dataset_workspace_section.html', dataset_section_context, request=request)
                    
                    # Update both the column badges and the specific dataset section via hx-swap-oob
                    from django.utils.text import slugify
                    dataset_section_update = f'<div id="dataset-workspace-{slugify(dataset_name)}" hx-swap-oob="outerHTML">{dataset_section_html}</div>'
                    combined_response = f'{column_badges_html}{dataset_section_update}'
                else:
                    # Fallback: update entire workspace if dataset group not found
                    workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
                    combined_response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(combined_response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"DESELECT_ALL_DATASET_COLUMNS: Error deselecting all columns: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


# ==============================================================================
# STEP 4: FK Configuration Views (To be implemented using mixins)
# ==============================================================================

class ToggleFKFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Toggle FK form view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for toggling FK forms."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id') or request.GET.get('column_id')
            
            logger.info(f"CSV_TOGGLE_FK_FORM: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
            
            # Get workspace columns using coordinator
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # DEBUG: Log workspace contents for FK form debugging
            logger.info(f"CSV_TOGGLE_FK_FORM: WORKSPACE DEBUG for org='{organization_id}':")
            logger.info(f"  - Total workspace columns: {len(workspace_columns)}")
            logger.info(f"  - Looking for column_id: '{column_id}'")
            for i, col in enumerate(workspace_columns):
                logger.info(f"    [{i}] ID: '{col.get('id')}' | Name: '{col.get('name')}' | Dataset: '{col.get('dataset')}' | FK: {col.get('is_fk', False)}")
            
            # UNIFIED TRACKING: Use coordinator method to find column
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                # Also validate workspace for duplicates and auto-clean
                is_unique, duplicates, cleaned = self.validate_workspace_column_uniqueness(request, organization_id)
                if not is_unique:
                    logger.error(f"CSV_TOGGLE_FK_FORM: Found {len(duplicates)} workspace duplicates - auto-cleaned and retrying")
                    column = self.get_unified_column_by_id(request, organization_id, column_id)
                
                if not column:
                    logger.error(f"CSV_TOGGLE_FK_FORM: Column '{column_id}' not found even after cleanup")
                    available_ids = [col.get('id') for col in self.get_workspace_columns(request, organization_id)]
                    logger.error(f"CSV_TOGGLE_FK_FORM: Available column IDs: {available_ids}")
                    return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
            
            # Get ALL available datasets with their columns for FK configuration using coordinator
            all_datasets_with_columns = self.get_all_datasets_with_columns_for_fk(request, organization_id)
            
            # Get current FK configuration if exists
            fk_config = column.get('fk_config', {})
            current_direction = fk_config.get('direction', 'outbound')
            target_dataset = fk_config.get('target_dataset', '')
            target_column = fk_config.get('target_column', '')
            
            context = {
                'column': column,
                'datasets': all_datasets_with_columns,
                'current_direction': current_direction,
                'target_dataset': target_dataset,
                'target_column': target_column,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE')
            }
            
            return render(request, 'csv_mapping/partials/inline_fk_form.html', context)
            
        except Exception as e:
            logger.error(f"CSV_TOGGLE_FK_FORM: Error toggling form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error opening FK configuration</div>')


class HideFKFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Hide FK form view using coordinator-based architecture.
    """
    
    def get(self, request):
        """Handle GET requests for hiding FK forms."""
        try:
            column_id = request.GET.get('column_id')
            logger.info(f"CSV_HIDE_FK_FORM: column={column_id}")
            
            # Return empty div to hide the form
            return HttpResponse(f'<div id="fk-form-{column_id}"></div>')
            
        except Exception as e:
            logger.error(f"CSV_HIDE_FK_FORM: Error hiding form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error hiding FK form</div>')


class UpdateFKTargetColumnsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Update FK target columns view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for updating FK target columns."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id') or request.GET.get('column_id')
            target_dataset = request.POST.get('target_dataset') or request.GET.get('target_dataset')
            
            logger.info(f"CSV_UPDATE_FK_TARGET_COLUMNS: column_id='{column_id}', target_dataset='{target_dataset}', org='{organization_id}'")
            
            if not column_id or not target_dataset:
                return HttpResponse('<option value="">Select target column...</option>')
            
            # Get ALL available datasets using coordinator
            all_datasets_with_columns = self.get_all_datasets_with_columns_for_fk(request, organization_id)
            
            # Find the target dataset and get its columns
            target_dataset_obj = next((d for d in all_datasets_with_columns if d.get('name') == target_dataset), None)
            
            if not target_dataset_obj:
                logger.error(f"CSV_UPDATE_FK_TARGET_COLUMNS: Dataset '{target_dataset}' not found")
                return HttpResponse('<option value="">Dataset not found</option>')
            
            # Get columns from the dataset preview
            preview = target_dataset_obj.get('preview', {})
            columns = preview.get('colHeaders', [])
            
            logger.info(f"CSV_UPDATE_FK_TARGET_COLUMNS: Found {len(columns)} columns for {target_dataset}")
            
            # Build options HTML
            options_html = '<option value="">Select target column...</option>\n'
            for column_name in columns:
                options_html += f'<option value="{column_name}">{column_name}</option>\n'
            
            return HttpResponse(options_html)
            
        except Exception as e:
            logger.error(f"CSV_UPDATE_FK_TARGET_COLUMNS: Error updating columns: {e}", exc_info=True)
            return HttpResponse('<option value="">Error loading columns</option>')


class SaveInlineFKConfigView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Save inline FK configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for saving FK configurations."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract form data
            column_id = request.POST.get('column_id')
            fk_direction = request.POST.get('fk_direction')
            target_dataset = request.POST.get('target_dataset')
            target_column = request.POST.get('target_column')
            
            logger.info(f"CSV_SAVE_INLINE_FK_CONFIG: column_id='{column_id}', direction='{fk_direction}', target='{target_dataset}.{target_column}', org='{organization_id}'")
            
            if not all([column_id, fk_direction, target_dataset, target_column]):
                missing = [name for name, val in [('column_id', column_id), ('fk_direction', fk_direction), ('target_dataset', target_dataset), ('target_column', target_column)] if not val]
                error_msg = f'Missing required fields: {", ".join(missing)}'
                logger.error(f"CSV_SAVE_INLINE_FK_CONFIG: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column with FK configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_fk'] = True
                    col['fk_config'] = {
                        'direction': fk_direction,
                        'target_dataset': target_dataset,
                        'target_column': target_column,
                    }
                    updated_column = col
                    logger.info(f"CSV_SAVE_INLINE_FK_CONFIG: ✅ Updated column '{column_id}' with FK config")
                    break
            
            if not updated_column:
                logger.error(f"CSV_SAVE_INLINE_FK_CONFIG: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            logger.info(f"CSV_SAVE_INLINE_FK_CONFIG: Successfully updated FK configuration")
            
            # Generate CSRF token for the template
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return just the updated column item
            from django.template.loader import render_to_string
            column_html = render_to_string('csv_mapping/partials/column_item.html', {
                'column': updated_column,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_SAVE_INLINE_FK_CONFIG: Error saving configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error saving FK configuration</div>')


class RemoveFKConfigView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Remove FK configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for removing FK configurations."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"CSV_REMOVE_FK_CONFIG: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-xs p-2">Column ID required</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column to remove FK configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_fk'] = False
                    col['fk_config'] = {}
                    updated_column = col
                    logger.info(f"CSV_REMOVE_FK_CONFIG: ✅ Removed FK config from column '{column_id}'")
                    break
            
            if not updated_column:
                logger.error(f"CSV_REMOVE_FK_CONFIG: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            # Prepare workspace update data
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated workspace
            from django.template.loader import render_to_string
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(workspace_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_REMOVE_FK_CONFIG: Error removing configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error removing FK configuration</div>')


class ConfigureFKRelationshipView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    FK relationship configuration view using coordinator-based architecture.
    
    TODO: Implement in Step 4
    USES: CSVMappingCoordinatorMixin for FK configuration with dataset relationship awareness
    """
    
    def post(self, request):
        """Handle POST requests for FK relationship configuration."""
        # TODO: Implement in Step 4
        return JsonResponse({'status': 'Step 4 implementation pending'})


# ==============================================================================
# Import Strategy Management Views (Ready to implement)
# ==============================================================================

class UpdateImportStrategyView(OrganizationMixin, ImportStrategyMixin, View):
    """
    Update import strategy configuration view using mixin-based architecture.
    
    READY TO USE: ImportStrategyMixin provides full functionality
    """
    
    def post(self, request):
        """Handle POST requests for import strategy updates."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Get strategy updates from POST data
            strategy_updates = {}
            for key in ['update_strategy', 'link_topology', 'multi_value_threshold', 'bulk_size']:
                if key in request.POST:
                    value = request.POST.get(key)
                    # Convert boolean strings
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    # Convert numeric strings
                    elif key in ['multi_value_threshold', 'bulk_size']:
                        try:
                            value = float(value) if key == 'multi_value_threshold' else int(value)
                        except ValueError:
                            pass
                    strategy_updates[key] = value
            
            # Validate and update strategy
            if strategy_updates:
                is_valid, errors = self.validate_import_strategy({**self.get_import_strategy(request, organization_id), **strategy_updates})
                if is_valid:
                    self.update_import_strategy(request, organization_id, strategy_updates)
                    return JsonResponse({'status': 'success', 'updated': strategy_updates})
                else:
                    return JsonResponse({'status': 'error', 'errors': errors}, status=400)
            
            return JsonResponse({'status': 'no_changes'})
            
        except Exception as e:
            logger.error(f"UPDATE_IMPORT_STRATEGY: Error updating strategy: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# JSON Serialization Views
# ==============================================================================

class ExportMappingJSONView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Export current mapping configuration as JSON.
    
    Uses the coordinator's serialize_current_mapping_state method to provide
    a comprehensive JSON representation of the current mapping configuration.
    """
    
    def get(self, request):
        """Handle GET requests for exporting mapping JSON."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                return JsonResponse({
                    'error': 'Invalid organization',
                    'message': f'Organization "{organization_id}" not found'
                }, status=400)
            
            # Use coordinator to serialize current mapping state
            mapping_config = self.serialize_current_mapping_state(request, organization_id)
            
            # Add additional metadata
            mapping_config['export_timestamp'] = timezone.now().isoformat()
            mapping_config['exported_by'] = 'CSV Mapping Editor'
            
            # Get workspace summary for additional context
            workspace_summary = self.get_workspace_summary(request, organization_id)
            mapping_config['workspace_summary'] = workspace_summary
            
            # Add relationship context information
            relationship_contexts = {}
            workspace_columns = self.get_workspace_columns(request, organization_id)
            for col in workspace_columns:
                if col.get('is_relationship_context', False):
                    relationship_contexts[col.get('id')] = col.get('relationship_context', {})
            mapping_config['relationship_contexts'] = relationship_contexts
            
            # Return formatted JSON response
            return JsonResponse(mapping_config, json_dumps_params={'indent': 2})
            
        except Exception as e:
            logger.error(f"EXPORT_MAPPING_JSON: Error exporting mapping: {e}", exc_info=True)
            return JsonResponse({
                'error': 'Export failed',
                'message': str(e)
            }, status=500)


class GetMappingJSONViewView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Get JSON view partial template for HTMX tab switching.
    
    This view returns the JSON view partial template, following the HTMX pattern
    used throughout the CSV mapping interface.
    """
    
    def get(self, request):
        """Handle GET requests for JSON view partial."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                error_html = f'''
                <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                    <h3 class="text-lg font-semibold text-red-800 mb-2">Invalid Organization</h3>
                    <p class="text-red-700">Organization "{organization_id}" not found</p>
                </div>
                '''
                return HttpResponse(error_html)
            
            # Prepare context for the JSON view template
            context = {
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return the JSON view partial template
            return render(request, 'csv_mapping/partials/json_view.html', context)
            
        except Exception as e:
            logger.error(f"GET_MAPPING_JSON_VIEW: Error loading JSON view: {e}", exc_info=True)
            error_html = f'''
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading JSON View</h3>
                <p class="text-red-700">{str(e)}</p>
            </div>
            '''
            return HttpResponse(error_html)


class GetMappingJSONContentView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Get current mapping configuration as JSON content for display in the UI.
    
    This view returns formatted JSON content suitable for displaying in the
    JSON tab of the mapping workspace.
    """
    
    def get(self, request):
        """Handle GET requests for mapping JSON content."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                error_json = {
                    'error': 'Invalid organization',
                    'message': f'Organization "{organization_id}" not found'
                }
                formatted_json = json.dumps(error_json, indent=2)
                return HttpResponse(f'<pre class="bg-gray-100 p-4 rounded text-sm overflow-auto max-h-96"><code>{formatted_json}</code></pre>')
            
            # Use coordinator to serialize current mapping state
            mapping_config = self.serialize_current_mapping_state(request, organization_id)
            
            # Add additional metadata for display
            mapping_config['export_timestamp'] = timezone.now().isoformat()
            mapping_config['exported_by'] = 'CSV Mapping Editor'
            
            # Get workspace summary for additional context
            workspace_summary = self.get_workspace_summary(request, organization_id)
            mapping_config['workspace_summary'] = workspace_summary
            
            # Format JSON with proper indentation
            formatted_json = json.dumps(mapping_config, indent=2, cls=DjangoJSONEncoder)
            
            # Return as HTML with proper formatting
            html_content = f'''
            <div class="bg-gray-50 border rounded-lg p-4">
                <div class="flex justify-between items-center mb-3">
                    <h3 class="text-lg font-semibold text-gray-800">Current Mapping Configuration</h3>
                    <div class="flex gap-2">
                        <button onclick="copyJsonToClipboard()" class="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
                            📋 Copy JSON
                        </button>
                        <a href="/metadata/csv-mapping/export-json/?organization={organization_id}" 
                           class="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700 no-underline">
                            💾 Download JSON
                        </a>
                    </div>
                </div>
                <div class="bg-white border rounded p-3 max-h-96 overflow-auto">
                    <pre id="json-content" class="text-sm text-gray-800 whitespace-pre-wrap"><code>{formatted_json}</code></pre>
                </div>
                <div class="mt-3 text-xs text-gray-600">
                    Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                    Datasets: {len(mapping_config.get('selected_datasets', []))} | 
                    Columns: {len(mapping_config.get('workspace_columns', {}))} |
                    FK Relations: {len(mapping_config.get('fk_relationships', {}))}
                </div>
            </div>
            '''
            
            return HttpResponse(html_content)
            
        except Exception as e:
            logger.error(f"GET_MAPPING_JSON_CONTENT: Error getting mapping JSON: {e}", exc_info=True)
            error_html = f'''
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading JSON</h3>
                <p class="text-red-700">{str(e)}</p>
            </div>
            '''
            return HttpResponse(error_html)


# ==============================================================================
# COORDINATOR ARCHITECTURE COMPLETE - Dataset-Column Relationships Solved!
# ==============================================================================

# ==============================================================================
# CLEAR OPERATIONS (Separated by Responsibility)
# ==============================================================================

class ClearSelectedDatasetsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Clear ONLY selected datasets (preserve workspace columns).
    
    SPECIFIC PURPOSE: This is for the dataset badges "Clear Selected" button.
    It removes dataset selections but keeps all workspace columns and their configurations intact.
    """
    
    def post(self, request):
        """Handle POST requests for clearing only selected datasets."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for specific clear operation
            datasets_cleared, workspace_preserved = self.clear_selected_datasets_only(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            # Get context for response using coordinator
            context_data = self.get_clear_operation_context(request, organization_id)
            
            logger.info(f"CLEAR_DATASETS: Cleared {datasets_cleared} datasets, preserved {workspace_preserved} workspace columns")
            
            # Render templates using context from coordinator
            from django.template.loader import render_to_string
            badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', context_data['badges_context'], request=request)
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', context_data['workspace_context'], request=request)
            
            # CRITICAL: Render table_content with empty datasets to remove cards from right side
            table_content_html = render_to_string('csv_mapping/partials/table_content.html', context_data['table_content_context'], request=request)
            
            # Main response: badges, OOB updates: workspace (preserved columns) + table content (remove cards)
            response = badges_html + f'<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div><div id="table-content" hx-swap-oob="innerHTML">{table_content_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CLEAR_DATASETS: Error clearing selected datasets: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ClearWorkspaceColumnsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Clear ONLY workspace columns (preserve selected datasets).
    
    SPECIFIC PURPOSE: This is for the workspace "Clear Workspace" button.
    It removes all workspace columns but keeps dataset selections intact.
    """
    
    def post(self, request):
        """Handle POST requests for clearing only workspace columns."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for specific clear operation
            columns_cleared, datasets_preserved = self.clear_workspace_columns_only(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            # Get context for response using coordinator
            context_data = self.get_clear_operation_context(request, organization_id)
            
            logger.info(f"CLEAR_WORKSPACE: Cleared {columns_cleared} workspace columns, preserved {datasets_preserved} selected datasets")
            
            # Render templates using context from coordinator
            from django.template.loader import render_to_string
            badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', context_data['badges_context'], request=request)
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', context_data['workspace_context'], request=request)
            
            # Main response: workspace, OOB update: badges (to show preserved selections)
            response = workspace_html + f'<div id="dataset-badges" hx-swap-oob="innerHTML">{badges_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CLEAR_WORKSPACE: Error clearing workspace columns: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ClearAllMappingStateView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Clear ALL mapping state (datasets AND workspace columns).
    
    SPECIFIC PURPOSE: This is for a complete reset operation.
    It clears both dataset selections and workspace columns.
    """
    
    def post(self, request):
        """Handle POST requests for clearing all mapping state."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for complete reset operation
            datasets_cleared, columns_cleared, summary = self.reset_all_coordinator_state(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            # Get context for response using coordinator
            context_data = self.get_clear_operation_context(request, organization_id)
            
            logger.info(f"CLEAR_ALL: Complete reset - cleared {datasets_cleared} datasets, {columns_cleared} columns")
            
            # Render templates using context from coordinator
            from django.template.loader import render_to_string
            badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', context_data['badges_context'], request=request)
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', context_data['workspace_context'], request=request)
            
            # Return both updated templates
            response = badges_html + f'<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(response)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CLEAR_ALL: Error clearing all mapping state: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# Legacy view for backward compatibility (if needed)
class ClearAllDatasetsView(ClearSelectedDatasetsView):
    """
    Legacy view that now delegates to ClearSelectedDatasetsView.
    
    DEPRECATED: Use ClearSelectedDatasetsView, ClearWorkspaceColumnsView, or ClearAllMappingStateView instead.
    """
    pass



class LoadMoreDatasetRowsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Load more dataset rows view using coordinator-based architecture.
    
    COORDINATOR IMPLEMENTATION: Pure coordinator-based dataset row loading
    """
    
    def get(self, request):
        """Handle GET requests for loading more dataset rows."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.GET.get('dataset')
            source_name = request.GET.get('source')
            offset = int(request.GET.get('offset', 0))
            limit = int(request.GET.get('limit', 10))
            
            if not dataset_name or not source_name:
                return HttpResponse('<tr><td colspan="100%" class="text-danger">Dataset and source parameters required</td></tr>')
            
            # Use S3DirectDataAnalyzer to get more rows - using the working pattern from direct_data_views.py
            analyzer = S3DirectDataAnalyzer()
            
            # Find the source in S3 directly (like direct_data_views.py does)
            sources = analyzer.discover_s3_data_sources(organization_id)
            source_info = next((s for s in sources if s.name == source_name), None)
            
            if not source_info:
                return HttpResponse('<tr><td colspan="100%" class="text-danger">Source not found</td></tr>')
            
            # Get more data with offset and limit using the complete source_info
            table_preview = analyzer.get_s3_table_preview(source_info, dataset_name, offset=offset, limit=limit)
            
            if not table_preview or not table_preview.data_rows:
                return HttpResponse('<tr><td colspan="100%" class="text-info">No more rows available</td></tr>')
            
            # Return both table rows AND updated button (like direct_data_views.py does)
            context = {
                'data': table_preview.data_rows,
                'dataset': dataset_name,
                'source': source_name,
                'preview': {
                    'showing_rows': offset + len(table_preview.data_rows),  # Total rows shown so far
                    'total_rows': table_preview.total_rows,
                    'has_more': table_preview.has_more,
                    'offset': offset + len(table_preview.data_rows)  # Next offset
                },
                'is_direct_mode': False,  # This is CSV mapping mode, not direct mode
                'organization_id': organization_id
            }
            
            return render(request, 'partials/load_more_response.html', context)
            
        except Exception as e:
            logger.error(f"LOAD_MORE_ROWS: Error loading more dataset rows: {e}", exc_info=True)
            return HttpResponse(f'<tr><td colspan="100%" class="text-danger">Error: {str(e)}</td></tr>')


class SetAnchorColumnView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Set a column as the anchor column using the coordinator mixin.
    Only one column can be anchor at a time.
    """
    
    def post(self, request):
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"🚨 SET_ANCHOR: Received column_id='{column_id}' for org='{organization_id}'")
            logger.info(f"🚨 SET_ANCHOR: POST data: {dict(request.POST)}")
            
            # DEBUG: Check session directly
            workspace_key = f"workspace_columns_{organization_id}"
            session_workspace = request.session.get(workspace_key, [])
            logger.info(f"🚨 SET_ANCHOR: Direct session check - workspace_key='{workspace_key}', columns={len(session_workspace)}")
            logger.info(f"🚨 SET_ANCHOR: Session keys: {list(request.session.keys())}")
            for col in session_workspace:
                logger.info(f"  - Session column: '{col.get('id')}' from dataset '{col.get('dataset')}'")
            
            if not column_id:
                return JsonResponse({'error': 'Missing column_id'}, status=400)
            
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
                    available_ids = [col.get('id') for col in self.get_workspace_columns(request, organization_id)]
                    logger.error(f"CSV_SET_ANCHOR: Available column IDs: {available_ids}")
                    return JsonResponse({'error': 'Column not found in workspace'}, status=404)
            
            # Use mixin method to toggle anchor column (consistent with FK approach)
            success, updated_columns = self.toggle_anchor_column(request, organization_id, column_id)
            
            if not success:
                return JsonResponse({'error': 'Failed to toggle anchor column'}, status=500)
            
            # Find the updated column to return just that column item (like FK save does)
            target_column = next((col for col in updated_columns if col.get('id') == column_id), None)
            if not target_column:
                return JsonResponse({'error': 'Updated column not found'}, status=500)
            
            # Generate CSRF token
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return just the updated column item (same approach as SaveInlineFKConfigView)
            column_html = render_to_string('csv_mapping/partials/column_item.html', {
                'column': target_column,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"Error setting anchor column: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)


class ToggleMultiValueColumnView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Toggle the multi-value status of a column using the coordinator mixin.
    """
    
    def post(self, request):
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"🚨 TOGGLE_MULTI_VALUE: Received column_id='{column_id}' for org='{organization_id}'")
            logger.info(f"🚨 TOGGLE_MULTI_VALUE: POST data: {dict(request.POST)}")
            
            # DEBUG: Check session directly
            workspace_key = f"workspace_columns_{organization_id}"
            session_workspace = request.session.get(workspace_key, [])
            logger.info(f"🚨 TOGGLE_MULTI_VALUE: Direct session check - workspace_key='{workspace_key}', columns={len(session_workspace)}")
            logger.info(f"🚨 TOGGLE_MULTI_VALUE: Session keys: {list(request.session.keys())}")
            for col in session_workspace:
                logger.info(f"  - Session column: '{col.get('id')}' from dataset '{col.get('dataset')}'")
            
            if not column_id:
                return JsonResponse({'error': 'Missing column_id'}, status=400)
            
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
                    available_ids = [col.get('id') for col in self.get_workspace_columns(request, organization_id)]
                    logger.error(f"CSV_TOGGLE_MULTI_VALUE: Available column IDs: {available_ids}")
                    return JsonResponse({'error': 'Column not found in workspace'}, status=400)
            
            # Use mixin method to toggle multi-value column (consistent with FK approach)
            success, updated_columns = self.toggle_multi_value_column(request, organization_id, column_id)
            
            if not success:
                return JsonResponse({'error': 'Failed to toggle multi-value column'}, status=500)
            
            # Find the updated column to return just that column item (like FK save does)
            updated_column = next((col for col in updated_columns if col.get('id') == column_id), None)
            if not updated_column:
                return JsonResponse({'error': 'Updated column not found'}, status=500)
            
            # Generate CSRF token
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return just the updated column item (same approach as SaveInlineFKConfigView)
            column_html = render_to_string('csv_mapping/partials/column_item.html', {
                'column': updated_column,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"Error toggling multi-value column: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)


# ==============================================================================
# STEP 5: Relationship Context Views (Junction Tables with Attributes)
# ==============================================================================

class ToggleRelationshipContextFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Toggle relationship context form view using coordinator-based architecture.
    
    Handles junction tables where columns represent relationship attributes
    rather than simple FK references. Examples:
    - Person-Project-Role relationships
    - Subject-Predicate-Context relationships
    - Any many-to-many with additional qualifying attributes
    """
    
    def post(self, request):
        """Handle POST requests for toggling relationship context forms."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id') or request.GET.get('column_id')
            
            logger.info(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
            
            # Get workspace columns using coordinator
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # DEBUG: Log workspace contents for relationship context debugging
            logger.info(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: WORKSPACE DEBUG for org='{organization_id}':")
            logger.info(f"  - Total workspace columns: {len(workspace_columns)}")
            logger.info(f"  - Looking for column_id: '{column_id}'")
            for i, col in enumerate(workspace_columns):
                context_info = col.get('relationship_context', {})
                logger.info(f"    [{i}] ID: '{col.get('id')}' | Name: '{col.get('name')}' | Dataset: '{col.get('dataset')}' | RelContext: {bool(context_info)}")
            
            # UNIFIED TRACKING: Use coordinator method to find column
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                # Also validate workspace for duplicates and auto-clean
                is_unique, duplicates, cleaned = self.validate_workspace_column_uniqueness(request, organization_id)
                if not is_unique:
                    logger.error(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: Found {len(duplicates)} workspace duplicates - auto-cleaned and retrying")
                    column = self.get_unified_column_by_id(request, organization_id, column_id)
                
                if not column:
                    logger.error(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: Column '{column_id}' not found even after cleanup")
                    available_ids = [col.get('id') for col in self.get_workspace_columns(request, organization_id)]
                    logger.error(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: Available column IDs: {available_ids}")
                    return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
            
            # Get ALL workspace columns to identify potential FK pairs for this relationship context
            fk_columns = [col for col in workspace_columns if col.get('is_fk', False)]
            
            # Get available datasets using coordinator for dataset/column selection
            datasets = self.get_all_datasets_with_columns_for_fk(request, organization_id)
            
            # Get current relationship context configuration if exists
            relationship_context = column.get('relationship_context', {})
            primary_fk_dataset = relationship_context.get('primary_fk_dataset', '')
            primary_fk_column = relationship_context.get('primary_fk_column', '')
            secondary_fk_dataset = relationship_context.get('secondary_fk_dataset', '')
            secondary_fk_column = relationship_context.get('secondary_fk_column', '')
            context_predicate = relationship_context.get('context_predicate', '')
            
            context = {
                'column': column,
                'datasets': datasets,
                'fk_columns': fk_columns,
                'primary_fk_dataset': primary_fk_dataset,
                'primary_fk_column': primary_fk_column,
                'secondary_fk_dataset': secondary_fk_dataset,
                'secondary_fk_column': secondary_fk_column,
                'context_predicate': context_predicate,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE')
            }
            
            return render(request, 'csv_mapping/partials/inline_relationship_context_form.html', context)
            
        except Exception as e:
            logger.error(f"CSV_TOGGLE_RELATIONSHIP_CONTEXT_FORM: Error toggling form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error opening relationship context configuration</div>')


class SaveInlineRelationshipContextView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Save inline relationship context configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for saving relationship context configurations."""
        try:
            # Debug: Log all POST parameters
            logger.info(f"CSV_SAVE_RELATIONSHIP_CONTEXT: POST params: {dict(request.POST)}")
            
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract form data
            column_id = request.POST.get('column_id')
            primary_fk_dataset = request.POST.get('primary_fk_dataset')
            primary_fk_column = request.POST.get('primary_fk_column')
            secondary_fk_dataset = request.POST.get('secondary_fk_dataset')
            secondary_fk_column = request.POST.get('secondary_fk_column')
            context_predicate = request.POST.get('context_predicate')
            
            logger.info(f"CSV_SAVE_RELATIONSHIP_CONTEXT: column_id='{column_id}', primary_fk='{primary_fk_dataset}.{primary_fk_column}', secondary_fk='{secondary_fk_dataset}.{secondary_fk_column}', predicate='{context_predicate}', org='{organization_id}'")
            
            if not all([column_id, context_predicate]):
                missing = [name for name, val in [('column_id', column_id), ('context_predicate', context_predicate)] if not val]
                error_msg = f'Missing required fields: {", ".join(missing)}'
                logger.error(f"CSV_SAVE_RELATIONSHIP_CONTEXT: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column with relationship context configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_relationship_context'] = True
                    col['relationship_context'] = {
                        'primary_fk_dataset': primary_fk_dataset,
                        'primary_fk_column': primary_fk_column,
                        'secondary_fk_dataset': secondary_fk_dataset,
                        'secondary_fk_column': secondary_fk_column,
                        'context_predicate': context_predicate,
                    }
                    updated_column = col
                    logger.info(f"CSV_SAVE_RELATIONSHIP_CONTEXT: ✅ Updated column '{column_id}' with relationship context config")
                    break
            
            if not updated_column:
                logger.error(f"CSV_SAVE_RELATIONSHIP_CONTEXT: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            logger.info(f"CSV_SAVE_RELATIONSHIP_CONTEXT: Successfully updated relationship context configuration")
            
            # Generate CSRF token for the template
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return just the updated column item
            from django.template.loader import render_to_string
            column_html = render_to_string('csv_mapping/partials/column_item.html', {
                'column': updated_column,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_SAVE_RELATIONSHIP_CONTEXT: Error saving configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error saving relationship context configuration</div>')


class HideRelationshipContextFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Hide relationship context form view using coordinator-based architecture.
    """
    
    def get(self, request):
        """Handle GET requests for hiding relationship context forms."""
        try:
            column_id = request.GET.get('column_id')
            logger.info(f"CSV_HIDE_RELATIONSHIP_CONTEXT_FORM: column={column_id}")
            
            # Return empty div to hide the form (using slugified ID to match template)
            from django.utils.text import slugify
            slugified_id = slugify(column_id) if column_id else 'unknown'
            return HttpResponse(f'<div id="relationship-context-form-{slugified_id}"></div>')
            
        except Exception as e:
            logger.error(f"CSV_HIDE_RELATIONSHIP_CONTEXT_FORM: Error hiding form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error hiding relationship context form</div>')


class RemoveRelationshipContextView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Remove relationship context configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for removing relationship context configurations."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"CSV_REMOVE_RELATIONSHIP_CONTEXT: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-xs p-2">Column ID required</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column to remove relationship context configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_relationship_context'] = False
                    col['relationship_context'] = {}
                    updated_column = col
                    logger.info(f"CSV_REMOVE_RELATIONSHIP_CONTEXT: ✅ Removed relationship context config from column '{column_id}'")
                    break
            
            if not updated_column:
                logger.error(f"CSV_REMOVE_RELATIONSHIP_CONTEXT: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            # Prepare workspace update data
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return updated workspace
            from django.template.loader import render_to_string
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(workspace_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_REMOVE_RELATIONSHIP_CONTEXT: Error removing configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error removing relationship context configuration</div>')


# ==============================================================================
# Enhanced JSON Serialization with Relationship Context Support
# ==============================================================================


class UpdateRelationshipContextColumnsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Update relationship context columns based on selected dataset (HTMX endpoint).
    """
    
    def post(self, request):
        """Handle POST requests for updating relationship context column options."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            field_type = request.POST.get('field_type')  # 'primary' or 'secondary'
            
            # Determine which FK we're updating based on field_type and get the corresponding dataset
            if field_type == 'primary':
                target_dataset = request.POST.get('primary_fk_dataset')
                field_name = "primary_fk_column"
            elif field_type == 'secondary':
                target_dataset = request.POST.get('secondary_fk_dataset')
                field_name = "secondary_fk_column"
            else:
                logger.error(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: Invalid field_type '{field_type}'")
                return HttpResponse('<option value="">Choose column...</option>')
            
            logger.info(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: column_id='{column_id}', field_type='{field_type}', target_dataset='{target_dataset}', field='{field_name}', org='{organization_id}'")
            
            if not column_id or not target_dataset:
                logger.error(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: Missing required fields - column_id='{column_id}', target_dataset='{target_dataset}'")
                return HttpResponse('<option value="">Select target column...</option>')
            
            # Get available datasets using coordinator
            datasets = self.get_all_datasets_with_columns_for_fk(request, organization_id)
            
            # Find the target dataset and get its columns
            target_dataset_obj = next((d for d in datasets if d.get('name') == target_dataset), None)
            
            if not target_dataset_obj:
                logger.error(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: Dataset '{target_dataset}' not found")
                return HttpResponse('<option value="">Dataset not found</option>')
            
            # Get columns from the dataset preview
            preview = target_dataset_obj.get('preview', {})
            columns = preview.get('colHeaders', [])
            
            logger.info(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: Found {len(columns)} columns for {target_dataset}")
            
            # Build options HTML
            options_html = '<option value="">Select target column...</option>\n'
            for column_name in columns:
                options_html += f'<option value="{column_name}">{column_name}</option>\n'
            
            return HttpResponse(options_html)
            
        except Exception as e:
            logger.error(f"CSV_UPDATE_RELATIONSHIP_CONTEXT_COLUMNS: Error updating columns: {e}", exc_info=True)
            return HttpResponse('<option value="">Error loading columns</option>')


# =============================================================================
# External Ontology Column Views
# =============================================================================

class ToggleExternalOntologyFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Toggle external ontology configuration form view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for toggling external ontology forms."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id') or request.GET.get('column_id')
            
            logger.info(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
            
            # Get workspace columns using coordinator
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Find column using coordinator method
            column = self.get_unified_column_by_id(request, organization_id, column_id)
            if not column:
                logger.error(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: Column '{column_id}' not found")
                return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
            
            # Get current external ontology configuration if exists
            external_ontology = column.get('external_ontology', {})
            ontology_type = external_ontology.get('ontology_type', '')
            uri_template = external_ontology.get('uri_template', '')
            identifier_pattern = external_ontology.get('identifier_pattern', '')
            validation_enabled = external_ontology.get('validation_enabled', True)
            
            # Define common ontology types with their templates and patterns
            ontology_presets = {
                'orcid': {
                    'name': 'ORCID',
                    'uri_template': 'https://orcid.org/{identifier}',
                    'identifier_pattern': r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
                    'example': '0000-0002-1825-0097',
                    'description': 'ORCID researcher identifiers'
                },
                'wikidata': {
                    'name': 'Wikidata',
                    'uri_template': 'https://www.wikidata.org/entity/{identifier}',
                    'identifier_pattern': r'^Q\d+$',
                    'example': 'Q42',
                    'description': 'Wikidata entity IDs'
                },
                'gnd': {
                    'name': 'GND (German National Library)',
                    'uri_template': 'https://d-nb.info/gnd/{identifier}',
                    'identifier_pattern': r'^\d{8,9}[\dX]?$',
                    'example': '118501429',
                    'description': 'German National Library authority file'
                },
                'viaf': {
                    'name': 'VIAF',
                    'uri_template': 'https://viaf.org/viaf/{identifier}',
                    'identifier_pattern': r'^\d+$',
                    'example': '12347231',
                    'description': 'Virtual International Authority File'
                },
                'loc': {
                    'name': 'Library of Congress',
                    'uri_template': 'http://id.loc.gov/authorities/names/{identifier}',
                    'identifier_pattern': r'^[a-z]{1,2}\d{8,10}$',
                    'example': 'n80057250',
                    'description': 'Library of Congress Name Authority File'
                },
                'isni': {
                    'name': 'ISNI',
                    'uri_template': 'https://isni.org/isni/{identifier}',
                    'identifier_pattern': r'^\d{15}[\dX]$',
                    'example': '0000000121032683',
                    'description': 'International Standard Name Identifier'
                },
                'custom': {
                    'name': 'Custom Ontology',
                    'uri_template': '',
                    'identifier_pattern': '',
                    'example': '',
                    'description': 'Custom ontology with user-defined template'
                }
            }
            
            context = {
                'column': column,
                'ontology_type': ontology_type,
                'uri_template': uri_template,
                'identifier_pattern': identifier_pattern,
                'validation_enabled': validation_enabled,
                'ontology_presets': ontology_presets,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE')
            }
            
            return render(request, 'csv_mapping/partials/inline_external_ontology_form.html', context)
            
        except Exception as e:
            logger.error(f"CSV_TOGGLE_EXTERNAL_ONTOLOGY_FORM: Error toggling form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error opening external ontology configuration</div>')


class SaveInlineExternalOntologyView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Save inline external ontology configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for saving external ontology configurations."""
        try:
            # Debug: Log all POST parameters
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: POST params: {dict(request.POST)}")
            
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract form data
            column_id = request.POST.get('column_id')
            ontology_type = request.POST.get('ontology_type')
            uri_template = request.POST.get('uri_template')
            identifier_pattern = request.POST.get('identifier_pattern')
            validation_enabled = request.POST.get('validation_enabled') == 'on'
            
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: column_id='{column_id}', type='{ontology_type}', template='{uri_template}', org='{organization_id}'")
            
            # Validate required fields
            if not all([column_id, ontology_type]):
                missing = []
                if not column_id: missing.append('column_id')
                if not ontology_type: missing.append('ontology_type')
                error_msg = f'Missing required fields: {", ".join(missing)}'
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # For custom ontology, require URI template
            if ontology_type == 'custom' and not uri_template:
                error_msg = 'URI template is required for custom ontologies'
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: VALIDATION FAILED - {error_msg}")
                return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column with external ontology configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_external_ontology'] = True
                    col['external_ontology'] = {
                        'ontology_type': ontology_type,
                        'uri_template': uri_template,
                        'identifier_pattern': identifier_pattern,
                        'validation_enabled': validation_enabled,
                    }
                    updated_column = col
                    logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: ✅ Updated column '{column_id}' with external ontology config")
                    break
            
            if not updated_column:
                logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            logger.info(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Successfully updated external ontology configuration")
            
            # Generate CSRF token for the template
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return just the updated column item
            from django.template.loader import render_to_string
            column_html = render_to_string('csv_mapping/partials/column_item.html', {
                'column': updated_column,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(column_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_SAVE_EXTERNAL_ONTOLOGY: Error saving configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error saving external ontology configuration</div>')


class HideExternalOntologyFormView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Hide external ontology form view using coordinator-based architecture.
    """
    
    def get(self, request):
        """Handle GET requests for hiding external ontology forms."""
        try:
            column_id = request.GET.get('column_id')
            logger.info(f"CSV_HIDE_EXTERNAL_ONTOLOGY_FORM: column={column_id}")
            
            # Return empty div to hide the form (using slugified ID to match template)
            from django.utils.text import slugify
            slugified_id = slugify(column_id) if column_id else 'unknown'
            return HttpResponse(f'<div id="external-ontology-form-{slugified_id}"></div>')
            
        except Exception as e:
            logger.error(f"CSV_HIDE_EXTERNAL_ONTOLOGY_FORM: Error hiding form: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-sm">Error hiding external ontology form</div>')


class RemoveExternalOntologyView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Remove external ontology configuration view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for removing external ontology configurations."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            column_id = request.POST.get('column_id')
            
            logger.info(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: column_id='{column_id}', org='{organization_id}'")
            
            if not column_id:
                return HttpResponse('<div class="text-error text-xs p-2">Column ID required</div>')
            
            # Get current workspace using coordinator methods
            existing_columns = self.get_workspace_columns(request, organization_id)
            
            # Find and update the column to remove external ontology configuration
            updated_column = None
            for col in existing_columns:
                if col.get('id') == column_id:
                    col['is_external_ontology'] = False
                    col['external_ontology'] = {}
                    updated_column = col
                    logger.info(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: ✅ Removed external ontology config from column '{column_id}'")
                    break
            
            if not updated_column:
                logger.error(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: Column '{column_id}' not found in workspace")
                return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
            
            # Save back to session using coordinator methods
            self.update_workspace_columns(request, organization_id, existing_columns)
            
            # Prepare workspace update data for response
            workspace_datasets = self._prepare_datasets_with_columns(existing_columns)
            
            # Generate CSRF token for the template
            from django.middleware.csrf import get_token
            csrf_token = get_token(request)
            
            # Return the updated workspace content
            from django.template.loader import render_to_string
            workspace_html = render_to_string('csv_mapping/partials/workspace_content.html', {
                'workspace_datasets': workspace_datasets,
                'organization_id': organization_id,
                'csrf_token': csrf_token,
            }, request=request)
            
            # Add workspace update trigger for JSON view synchronization
            final_response = self.add_workspace_update_trigger(workspace_html)
            return HttpResponse(final_response)
            
        except Exception as e:
            logger.error(f"CSV_REMOVE_EXTERNAL_ONTOLOGY: Error removing configuration: {e}", exc_info=True)
            return HttpResponse('<div class="text-error text-xs p-2">Error removing external ontology configuration</div>')


class ValidateExternalOntologyIdentifierView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Validate external ontology identifier view using coordinator-based architecture.
    """
    
    def post(self, request):
        """Handle POST requests for validating external ontology identifiers."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Extract validation data
            column_id = request.POST.get('column_id')
            identifier = request.POST.get('identifier')
            ontology_type = request.POST.get('ontology_type')
            identifier_pattern = request.POST.get('identifier_pattern')
            
            logger.info(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: column_id='{column_id}', type='{ontology_type}', identifier='{identifier}', org='{organization_id}'")
            
            if not all([column_id, identifier, ontology_type]):
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required fields for validation'
                })
            
            # Validate identifier format
            is_valid = True
            validation_message = ''
            
            if identifier_pattern:
                import re
                if not re.match(identifier_pattern, identifier):
                    is_valid = False
                    validation_message = f'Identifier does not match expected pattern for {ontology_type}'
                else:
                    validation_message = f'Valid {ontology_type} identifier format'
            else:
                validation_message = f'No validation pattern available for {ontology_type}'
            
            logger.info(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: Validation result - Valid: {is_valid}, Message: {validation_message}")
            
            return JsonResponse({
                'success': True,
                'is_valid': is_valid,
                'message': validation_message,
                'identifier': identifier,
                'ontology_type': ontology_type
            })
            
        except Exception as e:
            logger.error(f"CSV_VALIDATE_EXTERNAL_ONTOLOGY: Error validating identifier: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Error validating external ontology identifier'
            })



