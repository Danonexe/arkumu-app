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
                if parsed and parsed['dataset'] == dataset_name and parsed['source'] == source_name:
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
                                if parsed['dataset'] == dataset['name'] and parsed['source'] == dataset['source']:
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
            
            # Always return full table content + update badges via OOB - simpler and more reliable
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
            
            # DEBUG: Proof the coordinator is being called
            logger.info(f"🔥 ADD_COLUMN VIEW CALLED! Coordinator is working!")
            logger.info(f"🔥 POST Data: {dict(request.POST)}")
            logger.info(f"🔥 Organization ID: {organization_id}")
            
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
            
            # Use coordinator for validated column addition
            logger.info(f"🔥 CALLING COORDINATOR: add_column_with_validation({column_name}, {dataset_name}, {source_name})")
            success, new_column, total_columns, error_message = self.add_column_with_validation(
                request, organization_id, column_name, dataset_name, source_name
            )
            logger.info(f"🔥 COORDINATOR RESULT: success={success}, error={error_message}")
            
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
            
            # Prepare workspace update data with preserved FK configurations
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Debug: Log FK configurations before preparing datasets
            fk_columns_after = [col for col in workspace_columns if col.get('is_fk', False)]
            logger.info(f"🔥🔥🔥 ADD_COLUMN: AFTER adding column '{column_name}' from '{dataset_name}':")
            logger.info(f"  - Updated workspace: {len(workspace_columns)} columns")
            logger.info(f"  - FK columns after: {len(fk_columns_after)}")
            
            for col in workspace_columns:
                if col.get('is_fk', False):
                    logger.info(f"    - FK Column '{col.get('id')}': FK_config={col.get('fk_config', {})}")
            
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # Render workspace update (back to original working approach)
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Combine both updates using hx-swap-oob
            combined_response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            return HttpResponse(combined_response)
            
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
            
            # Generate column ID using coordinator format
            column_id = self.generate_column_id(dataset_name, column_name, source_name)
            
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
            return HttpResponse(response)
            
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
            
            # Validate that dataset is selected
            if not self._is_dataset_selected(request, organization_id, dataset_name):
                return HttpResponse(f'<div class="alert alert-warning">Dataset "{dataset_name}" is not selected</div>')
            
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
            
            # Add all columns to workspace using coordinator
            columns_added = 0
            for column_name in dataset_preview.get('columns', []):
                success, _, _, _ = self.add_column_with_validation(
                    request, organization_id, column_name, dataset_name, source_name
                )
                if success:
                    columns_added += 1
            
            # Get updated workspace columns and filter for this dataset
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
            
            # Only update the specific dataset workspace section instead of the entire workspace
            # This preserves open FK forms in other dataset sections
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
            
            return HttpResponse(combined_response)
            
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
            
            return HttpResponse(combined_response)
            
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
            
            return HttpResponse(column_html)
            
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
            
            return HttpResponse(workspace_html)
            
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
# COORDINATOR ARCHITECTURE COMPLETE - Dataset-Column Relationships Solved! 
# ==============================================================================
#
# ✅ PROBLEM SOLVED: Dataset-column relationships are now properly managed
# ✅ STATE CONSISTENCY: Coordinator ensures no orphaned columns 
# ✅ CASCADE OPERATIONS: Dataset deselection removes related columns
# ✅ VALIDATION: Cannot add columns from unselected datasets
# ✅ MAINTENANCE: Consistency checking and cleanup operations
#
# The CSVMappingCoordinatorMixin provides:
# - generate_column_id() / parse_column_id() for dataset-aware IDs
# - toggle_dataset_selection_with_cascade() for safe dataset operations
# - add_column_with_validation() for validated column operations
# - get_workspace_summary() for comprehensive state overview
# - cleanup_orphaned_columns() for consistency maintenance
#
# This solves the core architectural challenge you identified!
# ==============================================================================

class ClearAllDatasetsView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """
    Clear all dataset selections view using coordinator-based architecture.
    
    USES: CSVMappingCoordinatorMixin for proper dataset clearing with column cascade
    """
    
    def post(self, request):
        """Handle POST requests for clearing all dataset selections."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # DETECT WHICH BUTTON WAS CLICKED based on HTTP headers
            hx_target = request.headers.get('HX-Target', '')
            is_badges_button = hx_target == 'dataset-badges'
            is_workspace_button = hx_target == 'selected-columns-workspace'
            
            logger.info(f"CLEAR_ALL_DATASETS: Called from {'badges' if is_badges_button else 'workspace' if is_workspace_button else 'unknown'} button, target='{hx_target}'")
            
            # Get current selected datasets (names only - more efficient)
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            
            # DEBUG: Log selected datasets state
            logger.info(f"CLEAR_ALL_DATASETS: Found {len(selected_datasets)} selected datasets")
            
            # Check if there are workspace columns to clear as well
            workspace_columns = self.get_workspace_columns(request, organization_id)
            logger.info(f"CLEAR_ALL_DATASETS: Found {len(workspace_columns)} workspace columns")
            
            if not selected_datasets and not workspace_columns:
                # Nothing to clear - return appropriate empty state
                if is_badges_button:
                    # Return empty badges
                    csv_datasets = self.get_csv_datasets_for_organization(organization_id)
                    context = {
                        'datasets': csv_datasets,
                        'selected_datasets': [],  # Already empty
                        'organization_id': organization_id,
                        'csrf_token': request.META.get('CSRF_COOKIE'),
                    }
                    return render(request, 'csv_mapping/partials/dataset_badges.html', context)
                else:
                    # Return empty workspace state (default)
                    workspace_context = {
                        'datasets_with_columns': [],  # Already empty
                        'organization_id': organization_id,
                        'csrf_token': request.META.get('CSRF_COOKIE'),
                    }
                    return render(request, 'csv_mapping/partials/selected_columns_workspace.html', workspace_context)
            
            # TRUE COORDINATOR RESET: Use coordinator's complete state reset method
            logger.info(f"CLEAR_ALL_DATASETS: Using coordinator COMPLETE RESET for {len(selected_datasets)} datasets")
            
            # Execute complete coordinator state reset
            datasets_cleared, columns_cleared, reset_summary = self.reset_all_coordinator_state(
                request, organization_id
            )
            
            # Log reset results
            logger.info(f"CLEAR_ALL_DATASETS: COORDINATOR RESET RESULTS:")
            logger.info(f"  - Datasets cleared: {datasets_cleared}")
            logger.info(f"  - Columns cleared: {columns_cleared}")
            logger.info(f"  - Complete reset: {reset_summary['is_completely_clean']}")
            logger.info(f"  - Final state: {reset_summary['final_datasets_count']} datasets, {reset_summary['final_workspace_count']} columns")
            
            # Use cleared counts for response
            total_columns_removed = columns_cleared
            
            # COORDINATOR RESPONSE: Use coordinator's unified tracking for consistent UI updates
            # The button targets #selected-columns-workspace, so we need to return workspace HTML
            
            # COORDINATOR: Get updated workspace columns and prepare datasets structure
            updated_workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(updated_workspace_columns)
            
            # Prepare workspace context using coordinator data
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,  # Should be empty after clearing all
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # COORDINATOR VERIFICATION: Log final state
            logger.info(f"CLEAR_ALL_DATASETS: Final coordinator state - {len(datasets_with_columns)} dataset groups, {len(updated_workspace_columns)} total columns")
            
            # Get updated CSV datasets for badges update
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            badges_context = {
                'datasets': csv_datasets,
                'selected_datasets': [],  # Empty after clearing all
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Also update table content to show empty state
            table_context = {
                'selected_datasets_with_details': [],  # Empty after clearing all
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            from django.template.loader import render_to_string
            
            # UPDATE ALL RELATED UI COMPONENTS: workspace, badges, table, AND column badges in dataset cards
            
            # Get ALL available datasets to update their column badges
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            
            # Prepare column badge updates for EACH dataset card (all should show unselected state)
            column_badge_updates = []
            for dataset in csv_datasets:
                # Create context for each dataset's column badges (empty selected columns)
                dataset_context_for_badges = {
                    'dataset': dataset,
                    'dataset_selected_columns': [],  # Empty after clear all
                    'organization_id': organization_id,
                    'csrf_token': request.META.get('CSRF_COOKIE'),
                }
                
                # Render column badges for this dataset
                column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', dataset_context_for_badges, request=request)
                
                # Add OOB update for this dataset's column badges (using Django's slugify)
                from django.utils.text import slugify
                dataset_slug = slugify(dataset['name'])
                target_id = f'column-badges-{dataset_slug}'
                
                # DEBUG: Log what we're targeting
                logger.info(f"CLEAR_ALL_DATASETS: Creating OOB update for dataset '{dataset['name']}' -> target ID: '{target_id}'")
                
                column_badge_updates.append(f'<div id="{target_id}" hx-swap-oob="innerHTML">{column_badges_html}</div>')
            
            # RETURN APPROPRIATE CONTENT based on which button was clicked
            if is_badges_button:
                # BADGES BUTTON: Return updated badges as main response + ALL other components as OOB updates
                badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', badges_context, request=request)
                workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
                table_html = render_to_string('csv_mapping/partials/table_content.html', table_context, request=request)
                
                # DEBUG: Log badges button structure
                logger.info(f"CLEAR_ALL_DATASETS: BADGES BUTTON creating {len(column_badge_updates)} column badge updates")
                
                # Combine all updates
                all_oob_updates = [
                    f'<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>',
                    f'<div id="table-content" hx-swap-oob="innerHTML">{table_html}</div>'
                ] + column_badge_updates
                
                response = badges_html + ''.join(all_oob_updates)
                
                # DEBUG: Log badges button OOB targets
                logger.info(f"CLEAR_ALL_DATASETS: BADGES BUTTON OOB targets: {[update.split('id=\"')[1].split('\"')[0] for update in all_oob_updates if 'id=\"' in update]}")
                
            else:
                # WORKSPACE BUTTON: Match badges button pattern exactly
                # Main response goes to target + OOB updates for everything else
                workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
                badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', badges_context, request=request)
                table_html = render_to_string('csv_mapping/partials/table_content.html', table_context, request=request)
                
                # OOB updates for everything EXCEPT the workspace (which is main response)
                all_oob_updates = [
                    f'<div id="dataset-badges" hx-swap-oob="innerHTML">{badges_html}</div>',
                    f'<div id="table-content" hx-swap-oob="innerHTML">{table_html}</div>'
                ] + column_badge_updates
                
                # Main response (workspace) + OOB updates (everything else)
                response = workspace_html + ''.join(all_oob_updates)
                
                # DEBUG: Log response structure
                logger.info(f"CLEAR_ALL_DATASETS: WORKSPACE BUTTON Response includes {len(all_oob_updates)} OOB updates")
                logger.info(f"CLEAR_ALL_DATASETS: OOB update targets: {[update.split('id=\"')[1].split('\"')[0] for update in all_oob_updates if 'id=\"' in update]}")
            
            logger.info(f"CLEAR_ALL_DATASETS: Cleared {len(selected_datasets)} datasets, removed {total_columns_removed} columns, responded to {'badges' if is_badges_button else 'workspace'} button")
            return HttpResponse(response)
            
        except Exception as e:
            logger.error(f"CLEAR_ALL_DATASETS: Error clearing datasets: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



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
            
            # Use S3DirectDataAnalyzer to get more rows
            analyzer = S3DirectDataAnalyzer()
            
            # Get the dataset with more data
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Find the specific dataset
            dataset_preview = None
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    # Create S3DataSourceInfo object from the dataset info
                    source_info = S3DataSourceInfo(
                        bucket_name=dataset_info.get('bucket_name', ''),
                        object_key=dataset_info.get('object_key', ''),
                        name=dataset_info.get('name', dataset_name),
                        format=dataset_info.get('format', 'csv'),
                        size_bytes=dataset_info.get('size_bytes'),
                        modified_date=dataset_info.get('modified_date')
                    )
                    
                    # Get more data with offset and limit using the correct method
                    table_preview = analyzer.get_s3_table_preview(source_info, dataset_name, offset=offset, limit=limit)
                    if table_preview and table_preview.data_rows:
                        # Convert to the expected format
                        dataset_preview = {'sample_data': table_preview.data_rows}
                    break
            
            if not dataset_preview or not dataset_preview.get('sample_data'):
                return HttpResponse('<tr><td colspan="100%" class="text-info">No more rows available</td></tr>')
            
            # Return just the table rows
            context = {
                'data': dataset_preview['sample_data'],
                'dataset': dataset_name,
                'source': source_name,
            }
            
            return render(request, 'csv_mapping/partials/table_rows.html', context)
            
        except Exception as e:
            logger.error(f"LOAD_MORE_ROWS: Error loading more dataset rows: {e}", exc_info=True)
            return HttpResponse(f'<tr><td colspan="100%" class="text-danger">Error: {str(e)}</td></tr>')
