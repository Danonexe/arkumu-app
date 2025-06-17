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
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

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
            from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
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
            
            # Prepare workspace update data
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # Render workspace update
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
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # For individual column removal: return empty (removes the column) + update badges and header via OOB
            from django.template.loader import render_to_string
            
            # Get updated workspace data for header count
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            # Find the updated dataset group for header
            dataset_group = None
            for group in datasets_with_columns:
                if group['name'] == dataset_name and group['source'] == source_name:
                    dataset_group = group
                    break
            
            # Render updated column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # DEBUG: Check what we're rendering
            logger.info(f"🔥 REMOVE_COLUMN DEBUG: dataset_selected_columns={dataset_selected_columns}")
            logger.info(f"🔥 REMOVE_COLUMN DEBUG: colHeaders={dataset_preview.get('columns', [])}")
            logger.info(f"🔥 REMOVE_COLUMN DEBUG: column_badges_html length={len(column_badges_html)}")
            logger.info(f"🔥 REMOVE_COLUMN DEBUG: column_badges_html={column_badges_html[:200]}...")
            
            # Render updated dataset header
            if dataset_group:
                dataset_header_html = f'''
                    <div class="flex items-center gap-2 flex-1">
                        <!-- Dataset Info -->
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-medium text-success">{dataset_group['name']}</span>
                            <span class="badge badge-success badge-sm font-medium">
                                {dataset_group['selected_count']} column{'s' if dataset_group['selected_count'] != 1 else ''} selected
                            </span>
                            <span class="text-xs text-base-content opacity-50">from {dataset_group['source']}</span>
                        </div>
                    </div>
                '''
            else:
                # No columns left in dataset
                dataset_header_html = f'''
                    <div class="flex items-center gap-2 flex-1">
                        <div class="flex items-center gap-2">
                            <span class="text-sm font-medium text-success">{dataset_name}</span>
                            <span class="badge badge-success badge-sm font-medium">0 columns selected</span>
                            <span class="text-xs text-base-content opacity-50">from {source_name}</span>
                        </div>
                    </div>
                '''
            
            # Return updated column badges as main response + workspace update via OOB
            from django.template.loader import render_to_string
            
            # Prepare workspace update data
            workspace_columns = self.get_workspace_columns(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
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
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # Render workspace update
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Combine both updates using hx-swap-oob
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
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            workspace_context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render column badges
            column_badges_html = render_to_string('csv_mapping/partials/column_badges.html', context, request=request)
            
            # Render workspace update
            workspace_html = render_to_string('csv_mapping/partials/selected_columns_workspace.html', workspace_context, request=request)
            
            # Combine both updates using hx-swap-oob
            combined_response = f'{column_badges_html}<div id="selected-columns-workspace" hx-swap-oob="innerHTML">{workspace_html}</div>'
            return HttpResponse(combined_response)
            
        except Exception as e:
            logger.error(f"DESELECT_ALL_DATASET_COLUMNS: Error deselecting all columns: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-error">Error: {str(e)}</div>')


# ==============================================================================
# STEP 4: FK Configuration Views (To be implemented using mixins)
# ==============================================================================

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
            
            # Get current selected datasets
            selected_datasets, _ = self.get_selected_datasets_with_details(request, organization_id, [])
            
            if not selected_datasets:
                # No datasets to clear
                context = {
                    'datasets': [],
                    'selected_datasets': [],
                    'organization_id': organization_id,
                    'csrf_token': request.META.get('CSRF_COOKIE'),
                }
                return render(request, 'csv_mapping/partials/dataset_badges.html', context)
            
            # Clear all datasets by toggling each one off
            total_columns_removed = 0
            for dataset_name in selected_datasets[:]:  # Copy the list since we're modifying it
                _, was_added, columns_affected = self.toggle_dataset_selection_with_cascade(
                    request, organization_id, dataset_name
                )
                if not was_added:  # Dataset was removed
                    total_columns_removed += columns_affected
            
            # Get updated CSV datasets and context
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
            
            # Render both templates
            badges_html = render_to_string('csv_mapping/partials/dataset_badges.html', badges_context, request=request)
            table_html = render_to_string('csv_mapping/partials/table_content.html', table_context, request=request)
            
            # Return badges as main response + table update via OOB
            response = f'{badges_html}<div id="table-content" hx-swap-oob="innerHTML">{table_html}</div>'
            
            logger.info(f"CLEAR_ALL_DATASETS: Cleared {len(selected_datasets)} datasets, removed {total_columns_removed} columns")
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
                    # Get more data with offset and limit
                    full_data = analyzer.get_dataset_preview(source_name, dataset_name, limit=offset + limit)
                    if full_data and 'sample_data' in full_data:
                        # Extract only the new rows
                        all_rows = full_data['sample_data']
                        new_rows = all_rows[offset:offset + limit] if len(all_rows) > offset else []
                        dataset_preview = {'sample_data': new_rows}
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
