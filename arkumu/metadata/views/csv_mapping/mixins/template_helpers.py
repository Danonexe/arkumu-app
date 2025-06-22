"""
CSV Mapping Template Helpers

This mixin provides common template rendering and context preparation methods
to reduce code duplication across CSV mapping views.
"""

import logging
from django.template.loader import render_to_string
from django.middleware.csrf import get_token

logger = logging.getLogger(__name__)


class CSVMappingTemplateHelperMixin:
    """
    Mixin providing common template rendering methods for CSV mapping views.
    
    This reduces the significant code duplication found across csv_mapping_views.py
    and saved_mappings_ui.py where the same templates are rendered repeatedly
    with similar context preparation.
    """
    
    def render_workspace_template(self, request, organization_id, workspace_columns=None):
        """
        Render workspace template with standard context.
        
        Consolidates the repeated pattern:
        - Get workspace columns
        - Prepare datasets_with_columns 
        - Build context
        - Render template
        """
        if workspace_columns is None:
            workspace_columns = self.get_workspace_columns(request, organization_id)
        
        datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
        
        context = {
            'datasets_with_columns': datasets_with_columns,
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        return render_to_string(
            'csv_mapping/partials/selected_columns_workspace.html',
            context,
            request=request
        )
    
    def render_dataset_badges_template(self, request, organization_id, csv_datasets=None, selected_datasets=None):
        """
        Render dataset badges template with standard context.
        
        Consolidates the repeated pattern for dataset badges rendering.
        """
        if csv_datasets is None:
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
        
        if selected_datasets is None:
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
        
        context = {
            'datasets': csv_datasets,
            'selected_datasets': selected_datasets,
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        return render_to_string(
            'csv_mapping/partials/dataset_badges.html',
            context,
            request=request
        )
    
    def render_table_content_template(self, request, organization_id, selected_datasets_with_details=None):
        """
        Render table content template with standard context.
        
        Includes column selection state for each dataset.
        """
        if selected_datasets_with_details is None:
            # Get basic selected datasets info
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            selected_datasets_with_details = [
                ds for ds in csv_datasets if ds.get('name') in selected_datasets
            ]
        
        # Get column selection state for all datasets
        selection_key = f"column_selection_{organization_id}"
        column_selections = request.session.get(selection_key, {})
        
        # Add column selection context to each dataset
        enhanced_datasets = []
        for dataset in selected_datasets_with_details:
            dataset_key = f"{dataset.get('name')}::{dataset.get('source')}"
            dataset_selected_columns = column_selections.get(dataset_key, [])
            
            # Create enhanced dataset with selection context
            enhanced_dataset = {
                **dataset,
                'dataset_selected_columns': dataset_selected_columns
            }
            enhanced_datasets.append(enhanced_dataset)
        
        context = {
            'selected_datasets_with_details': enhanced_datasets,  # Include selection context
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        return render_to_string(
            'csv_mapping/partials/table_content.html',
            context,
            request=request
        )
    
    def render_column_badges_template(self, request, organization_id, dataset_name, source_name, dataset_preview=None):
        """
        Render column badges template for a specific dataset.
        
        Uses separate column selection session (not workspace) for pure selection interface.
        """
        # Get column selection state from separate session key (not workspace)
        selection_key = f"column_selection_{organization_id}"
        column_selections = request.session.get(selection_key, {})
        dataset_key = f"{dataset_name}::{source_name}"
        dataset_selected_columns = column_selections.get(dataset_key, [])
        
        # Get dataset preview if not provided
        if dataset_preview is None:
            from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
            analyzer = S3DirectDataAnalyzer()
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Find the specific dataset
            for dataset_info in source_summary.get('datasets', []):
                if dataset_info.get('name') == dataset_name:
                    dataset_preview = dataset_info
                    break
        
        # Build dataset context
        dataset_context = {
            'name': dataset_name,
            'source': source_name,
        }
        
        # Always add preview data for column badges to render
        if dataset_preview:
            dataset_context['preview'] = {
                'colHeaders': dataset_preview.get('columns', dataset_preview.get('colHeaders', []))
            }
        else:
            # Fallback to prevent template errors
            dataset_context['preview'] = {
                'colHeaders': []
            }
        
        context = {
            'dataset': dataset_context,
            'dataset_selected_columns': dataset_selected_columns,  # From selection interface, not workspace
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        return render_to_string(
            'csv_mapping/partials/column_badges.html',
            context,
            request=request
        )
    
    def render_column_item_template(self, request, organization_id, column):
        """
        Render individual column item template.
        
        Consolidates the repeated pattern for column item rendering.
        """
        context = {
            'column': column,
            'organization_id': organization_id,
            'csrf_token': get_token(request),
        }
        
        return render_to_string(
            'csv_mapping/partials/column_item.html',
            context,
            request=request
        )
    
    def build_oob_response(self, main_html, oob_updates=None):
        """
        Build response with out-of-band updates.
        
        Consolidates the repeated pattern:
        response = f'{main_html}<div id="target" hx-swap-oob="innerHTML">{content}</div>'
        
        Args:
            main_html (str): The main response HTML
            oob_updates (dict): Dict of {target_id: content} for OOB updates
        
        Returns:
            str: Complete HTML response with OOB updates
        """
        if not oob_updates:
            return main_html
        
        oob_html = ""
        for target_id, content in oob_updates.items():
            oob_html += f'<div id="{target_id}" hx-swap-oob="innerHTML">{content}</div>'
        
        return f'{main_html}{oob_html}'
    
    def add_workspace_update_trigger(self, html_content):
        """
        Add workspace update trigger for JSON view synchronization.
        
        This method adds an HX-Trigger header to fire a 'refreshJson' event
        that the JSON view listens for to update its content when workspace changes occur.
        
        Args:
            html_content (str): The HTML content to wrap in an HttpResponse
            
        Returns:
            HttpResponse: Response with HX-Trigger header for JSON synchronization
        """
        from django.http import HttpResponse
        import json
        
        response = HttpResponse(html_content)
        # Add HX-Trigger header to fire refreshJson event for JSON view synchronization
        trigger_data = {
            'refreshJson': True
        }
        response['HX-Trigger'] = json.dumps(trigger_data)
        return response
    
    def build_standard_ui_refresh_response(self, request, organization_id, main_html=""):
        """
        Build a standard response that refreshes all major UI components.
        
        This is commonly needed after operations that change the mapping state.
        Returns main_html + OOB updates for workspace, badges, and table content.
        """
        # Render all standard templates
        workspace_html = self.render_workspace_template(request, organization_id)
        badges_html = self.render_dataset_badges_template(request, organization_id)
        table_html = self.render_table_content_template(request, organization_id)
        
        # Build OOB updates
        oob_updates = {
            'selected-columns-workspace': workspace_html,
            'dataset-badges': badges_html,
            'table-content': table_html,
        }
        
        return self.build_oob_response(main_html, oob_updates) 