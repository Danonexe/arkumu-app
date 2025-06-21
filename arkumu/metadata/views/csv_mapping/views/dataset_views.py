"""
CSV Mapping Dataset Views

This module contains views for dataset management in the CSV mapping interface:
- Dataset card display with preview data
- Dataset selection/deselection with cascade functionality  
- Load more dataset rows functionality

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
from django.shortcuts import render
from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class CSVDatasetCardView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    CSV dataset card view using coordinator-based architecture.
    
    Displays dataset preview with column headers, sample data, and selection state.
    Uses coordinator mixin for dataset preview + workspace with relationship integrity.
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


class ToggleDatasetSelectionView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Toggle dataset selection view using coordinator-based architecture.
    
    Handles dataset selection/deselection with automatic column cascade functionality.
    Uses coordinator for dataset management with column cascade and template helpers 
    for reduced rendering duplication.
    """
    
    def post(self, request):
        """Handle POST requests for toggling dataset selection with cascade."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            dataset_name = request.POST.get('dataset')
            action = request.POST.get('action', 'toggle')  # 'add', 'remove', or 'toggle'
            
            if not dataset_name:
                return HttpResponse('<div class="text-danger">Dataset parameter required</div>')
            
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
            
            # Get column selection state (not workspace) for dataset column selection info
            selection_key = f"column_selection_{organization_id}"
            column_selections = request.session.get(selection_key, {})
            
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
                        # Get selected columns from column selection session (not workspace)
                        dataset_key = f"{dataset['name']}::{dataset['source']}"
                        dataset_selected_columns = column_selections.get(dataset_key, [])
                        
                        # Transform to match template expectations
                        enhanced_dataset = {
                            **dataset,  # Keep original data
                            'cell_count': dataset_preview.get('row_count', 0) * dataset_preview.get('column_count', 0),
                            'dataset_selected_columns': dataset_selected_columns,  # From selection session
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
                'selected_columns': columns_affected,  # Global selected columns
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
                'was_added': was_added,
                'dataset_name': dataset_name,
            }
            
            # Handle different actions for pure HTMX approach
            if action == 'add' and was_added:
                # Return only the single new dataset card for prepending with OOB badge update
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
                    
                    # Use template helper for OOB badge update (pure HTMX)
                    badges_html = self.render_dataset_badges_template(request, organization_id)
                    oob_updates = {'dataset-badges': badges_html}
                    response_html = self.build_oob_response(single_card, oob_updates)
                    
                    return HttpResponse(response_html)
            
            elif action == 'remove' and not was_added:
                # Return empty response - HTMX will delete the target element
                # Check if no datasets remain, show empty state
                if not enhanced_datasets_with_details:
                    empty_state = self.render_table_content_template(request, organization_id, [])
                    
                    # Use template helper for OOB badge update (pure HTMX)
                    badges_html = self.render_dataset_badges_template(request, organization_id)
                    oob_updates = {'dataset-badges': badges_html}
                    response_html = self.build_oob_response(empty_state, oob_updates)
                    
                    return HttpResponse(response_html)
                else:
                    # Just return OOB badge update
                    badges_html = self.render_dataset_badges_template(request, organization_id)
                    oob_updates = {'dataset-badges': badges_html}
                    response_html = self.build_oob_response("", oob_updates)
                    
                    return HttpResponse(response_html)
            
            # Fallback: return full table content (for 'toggle' or error cases)
            table_content = self.render_table_content_template(request, organization_id, enhanced_datasets_with_details)
            
            # Use template helper for OOB badge update (pure HTMX)
            badges_html = self.render_dataset_badges_template(request, organization_id)
            oob_updates = {'dataset-badges': badges_html}
            response_html = self.build_oob_response(table_content, oob_updates)
            
            return HttpResponse(response_html)
            
        except Exception as e:
            logger.error(f"TOGGLE_DATASET: Error toggling dataset selection: {e}", exc_info=True)
            return HttpResponse(f'<div class="text-danger">Error: {str(e)}</div>')


class LoadMoreDatasetRowsView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Load more dataset rows view using coordinator-based architecture.
    
    Handles pagination for dataset preview tables, loading additional rows
    from S3 data sources as needed.
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


class GetDatasetBadgesView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Get dataset badges view using template helpers.
    
    Returns just the inner content of dataset badges for event-driven refreshes.
    """
    
    def get(self, request):
        """Handle GET requests for dataset badges content."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use template helper to render badges content
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            
            context = {
                'datasets': csv_datasets,
                'selected_datasets': selected_datasets,
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Render just the inner content for the HTMX refresh
            return HttpResponse(render_to_string(
                'csv_mapping/partials/dataset_badges_inner.html',
                context,
                request=request
            ))
            
        except Exception as e:
            logger.error(f"GET_BADGES: Error getting dataset badges: {e}", exc_info=True)
            return HttpResponse(f'<div class="text-danger">Error: {str(e)}</div>') 