"""
CSV Mapping HTMX Views

This module contains pure HTMX views for UI state management in the CSV mapping interface.
These views complement the JSON-based persistence views by providing HTML responses 
for button states, status messages, and other UI elements.
"""

import json
import logging
from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.saved_mappings_api import (
    SaveMappingView, UpdateMappingView, LoadMappingView, DeleteMappingView
)
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin

logger = logging.getLogger(__name__)


class ValidateMappingNameView(View):
    """Validate mapping name and return save button with appropriate state"""
    
    def get(self, request):
        """Return save button HTML with enabled/disabled state based on name validation"""
        mapping_name = request.GET.get('mapping_name', '').strip()
        organization_id = request.GET.get('organization')
        
        # Check if name is valid
        is_valid = bool(mapping_name)
        is_duplicate = False
        
        if is_valid and organization_id:
            # Check for duplicates (avoid accessing description field)
            is_duplicate = Mapping.objects.filter(
                organization_id=organization_id,
                name=mapping_name
            ).exists()
        
        # Determine button state
        if not is_valid:
            button_class = "btn btn-xs btn-primary btn-disabled"
            disabled = True
        elif is_duplicate:
            button_class = "btn btn-xs btn-error"
            disabled = True
        else:
            button_class = "btn btn-xs btn-primary"
            disabled = False
        
        # Render button HTML
        context = {
            'button_class': button_class,
            'disabled': disabled,
            'is_duplicate': is_duplicate,
            'organization_id': organization_id,
            'csrf_token': request.META.get('CSRF_COOKIE')
        }
        
        button_html = f'''
        <button class="{button_class}" 
                id="save-mapping-btn"
                hx-post="/metadata/csv-save-mapping-htmx/"
                hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{context['csrf_token']}"}}'
                hx-include="#mapping-name-input"
                hx-target="#mapping-status"
                hx-swap="innerHTML"
                {'disabled' if disabled else ''}>
            {_("Save")}
            {'<span class="text-xs ml-1">(' + _("Name already exists") + ')</span>' if is_duplicate else ''}
            <span class="loading loading-spinner loading-xs htmx-indicator"></span>
        </button>
        '''
        
        return HttpResponse(button_html)


class UpdateButtonStateView(View):
    """Update button states based on selection"""
    
    def get(self, request):
        """Return button HTML with enabled/disabled state based on selection"""
        button_type = request.GET.get('button')  # 'load' or 'delete'
        mapping_id = request.GET.get('mapping_id', '')
        organization_id = request.GET.get('organization')
        
        has_selection = bool(mapping_id)
        
        if button_type == 'load':
            if has_selection:
                button_class = "btn btn-xs btn-secondary flex-1"
                disabled = False
            else:
                button_class = "btn btn-xs btn-secondary flex-1 btn-disabled"
                disabled = True
                
            button_html = f'''
            <button class="{button_class}" 
                    id="load-mapping-btn"
                    hx-post="/metadata/csv-load-mapping-htmx/"
                    hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{request.META.get('CSRF_COOKIE')}"}}'
                    hx-include="#mapping-select"
                    hx-target="#mapping-status"
                    hx-swap="innerHTML"
                    hx-confirm="{_('This will replace your current mapping configuration. Continue?')}"
                    {'disabled' if disabled else ''}>
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
                </svg>
                {_("Load")}
                <span class="loading loading-spinner loading-xs htmx-indicator"></span>
            </button>
            '''
            
        elif button_type == 'delete':
            if has_selection:
                button_class = "btn btn-xs btn-error btn-outline"
                disabled = False
            else:
                button_class = "btn btn-xs btn-error btn-outline btn-disabled"
                disabled = True
                
            button_html = f'''
            <button class="{button_class}" 
                    id="delete-mapping-btn"
                    hx-post="/metadata/csv-delete-mapping-htmx/"
                    hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{request.META.get('CSRF_COOKIE')}"}}'
                    hx-include="#mapping-select"
                    hx-target="#mapping-status"
                    hx-swap="innerHTML"
                    hx-confirm="{_('Are you sure you want to delete this mapping? This action cannot be undone.')}"
                    {'disabled' if disabled else ''}>
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
                {_("Delete")}
                <span class="loading loading-spinner loading-xs htmx-indicator"></span>
            </button>
            '''
        else:
            return HttpResponse("Invalid button type", status=400)
        
        return HttpResponse(button_html)


class SaveMappingHTMXView(View):
    """HTMX wrapper for save mapping that returns HTML status"""
    
    def post(self, request):
        """Save mapping and return HTML status message"""
        # Call the original JSON view
        save_view = SaveMappingView()
        json_response = save_view.post(request)
        
        # Convert JSON response to HTML status
        try:
            data = json_response.json() if hasattr(json_response, 'json') else {}
            
            if json_response.status_code == 200 and data.get('success'):
                # Extract additional information for better feedback
                mapping_name = data.get('mapping_name', 'Unknown')
                mapping_id = data.get('mapping_id', '')
                was_created = data.get('created', False)
                
                status_html = f'''
                <div class="alert alert-success alert-sm">
                    <div class="flex items-center gap-2">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                        </svg>
                        <span>{data['message']}</span>
                    </div>
                    <div class="text-xs mt-1 opacity-75">
                        {'Created new mapping' if was_created else 'Updated existing mapping'}: <strong>{mapping_name}</strong>
                    </div>
                </div>
                '''
                
                # Create response with HTMX trigger headers
                response = HttpResponse(status_html)
                trigger_data = {
                    'clearMappingInput': True,
                    'refreshMappings': True,
                    'mappingSaved': {
                        'mapping_id': mapping_id,
                        'mapping_name': mapping_name,
                        'created': was_created
                    }
                }
                response['HX-Trigger-After-Swap'] = json.dumps(trigger_data)
                return response
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                validation_errors = data.get('validation_errors', [])
                validation_warnings = data.get('validation_warnings', [])
                
                # Build detailed error message
                error_details = ''
                if validation_errors:
                    error_list = ''.join([f'<li class="text-sm">{err}</li>' for err in validation_errors])
                    error_details += f'<ul class="mt-2 ml-4 list-disc">{error_list}</ul>'
                
                if validation_warnings:
                    warning_list = ''.join([f'<li class="text-sm">{warn}</li>' for warn in validation_warnings])
                    error_details += f'<div class="mt-2"><strong>Warnings:</strong><ul class="ml-4 list-disc">{warning_list}</ul></div>'
                
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <div class="flex items-center gap-2">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <span>{error_msg}</span>
                    </div>
                    {error_details}
                </div>
                '''
                return HttpResponse(status_html)
        except Exception as e:
            logger.error(f"SAVE_MAPPING_HTMX: Error processing save response: {str(e)}")
            status_html = f'''
            <div class="alert alert-error alert-sm">
                <span>Failed to save mapping: {str(e)}</span>
            </div>
            '''
        return HttpResponse(status_html)


class LoadMappingHTMXView(CSVMappingCoordinatorMixin, View):
    """HTMX wrapper for load mapping that returns HTML status"""
    
    def _get_workspace_content(self, request, organization_id):
        """Get workspace content for out-of-band update"""
        try:
            workspace_columns = self.get_workspace_columns(request, organization_id)
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            from django.middleware.csrf import get_token
            context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': get_token(request),
                'selected_datasets': selected_datasets,
                'workspace_columns': workspace_columns
            }
            
            return render_to_string(
                'csv_mapping/partials/selected_columns_workspace_content.html',
                context,
                request=request
            )
        except Exception as e:
            logger.error(f"Error getting workspace content: {str(e)}")
            return '<div class="alert alert-error">Failed to load workspace</div>'
    
    def _get_badges_content(self, request, organization_id):
        """Get badges content for out-of-band update"""
        try:
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            all_datasets = self.get_csv_datasets_for_organization(organization_id)
            
            from django.middleware.csrf import get_token
            context = {
                'datasets': all_datasets,
                'selected_datasets': selected_datasets,
                'organization_id': organization_id,
                'csrf_token': get_token(request),
            }
            
            return render_to_string(
                'csv_mapping/partials/dataset_badges.html',
                context,
                request=request
            )
        except Exception as e:
            logger.error(f"Error getting badges content: {str(e)}")
            return '<div class="alert alert-error">Failed to load badges</div>'
    
    def _get_table_content(self, request, organization_id):
        """Get table content (dataset cards) for out-of-band update"""
        try:
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            
            # Get detailed dataset info for selected datasets
            selected_datasets_with_details = []
            if selected_datasets:
                all_datasets = self.get_csv_datasets_for_organization(organization_id)
                
                # Filter to only selected datasets
                basic_selected_datasets = [
                    ds for ds in all_datasets if ds.get('name') in selected_datasets
                ]
                
                # Load preview data for each selected dataset
                for dataset_info in basic_selected_datasets:
                    dataset_name = dataset_info.get('name')
                    source_name = dataset_info.get('source')
                    
                    # Get dataset preview using S3DirectDataAnalyzer
                    try:
                        from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
                        analyzer = S3DirectDataAnalyzer()
                        
                        # Get the source summary which contains dataset previews
                        source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
                        
                        # Find the specific dataset in the source
                        dataset_preview = None
                        for ds_info in source_summary.get('datasets', []):
                            if ds_info.get('name') == dataset_name:
                                dataset_preview = ds_info
                                break
                        
                        if dataset_preview:
                            # Transform the data to match the template expectations
                            detailed_dataset = {
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
                            selected_datasets_with_details.append(detailed_dataset)
                    except Exception as e:
                        logger.error(f"Error loading preview for dataset {dataset_name}: {str(e)}")
                        # Add basic dataset info without preview
                        dataset_info['preview'] = None
                        selected_datasets_with_details.append(dataset_info)
            
            # Get selected columns for highlighting in dataset cards
            workspace_columns = self.get_workspace_columns(request, organization_id)
            
            # Prepare dataset-specific selected columns for each dataset
            dataset_selected_columns_map = {}
            for dataset in selected_datasets_with_details:
                dataset_name = dataset.get('name')
                source_name = dataset.get('source')
                
                # Filter to get only columns from this specific dataset using coordinator's parse method
                columns_for_dataset = []
                for column in workspace_columns:
                    column_id = column.get('id', '')
                    if column_id:
                        parsed = self.parse_column_id(column_id)
                        if parsed and parsed.get('dataset') == dataset_name and parsed.get('source') == organization_id:
                            columns_for_dataset.append(parsed.get('column'))
                
                dataset_selected_columns_map[dataset_name] = columns_for_dataset
            
            # Render each dataset card separately with its specific selected columns
            dataset_cards_html = ""
            for dataset in selected_datasets_with_details:
                dataset_name = dataset.get('name')
                dataset_selected_columns = dataset_selected_columns_map.get(dataset_name, [])
                
                from django.middleware.csrf import get_token
                context = {
                    'dataset': dataset,
                    'organization_id': organization_id,
                    'csrf_token': get_token(request),
                    'selected_columns': workspace_columns,
                    'dataset_selected_columns': dataset_selected_columns,
                }
                
                dataset_card_html = render_to_string(
                    'csv_mapping/partials/dataset_card.html',
                    context,
                    request=request
                )
                dataset_cards_html += dataset_card_html
            
            return dataset_cards_html
        except Exception as e:
            logger.error(f"Error getting table content: {str(e)}")
            return f'<div class="alert alert-error">Failed to load dataset cards: {str(e)}</div>'
    
    def post(self, request):
        """Load mapping and return HTML status message"""
        # Call the original JSON view
        load_view = LoadMappingView()
        json_response = load_view.post(request)
        
        # Convert JSON response to HTML status
        try:
            if hasattr(json_response, 'content'):
                import json
                data = json.loads(json_response.content)
            else:
                data = {}
            
            if json_response.status_code == 200 and data.get('success'):
                warnings_html = ''
                if data.get('warnings'):
                    warnings_list = ''.join([f'<li class="text-sm">{w}</li>' for w in data['warnings']])
                    warnings_html = f'<ul class="text-sm mt-2 ml-4 list-disc">{warnings_list}</ul>'
                
                # Add summary information from the load operation
                summary = data.get('summary', {})
                summary_html = ''
                if summary:
                    summary_items = []
                    if summary.get('datasets_restored', 0) > 0:
                        summary_items.append(f"{summary['datasets_restored']} datasets")
                    if summary.get('columns_restored', 0) > 0:
                        summary_items.append(f"{summary['columns_restored']} columns")
                    if summary.get('fk_relationships_restored', 0) > 0:
                        summary_items.append(f"{summary['fk_relationships_restored']} FK relationships")
                    if summary.get('relationship_contexts_restored', 0) > 0:
                        summary_items.append(f"{summary['relationship_contexts_restored']} relationship contexts")
                    
                    if summary_items:
                        summary_html = f'<div class="text-sm text-success-content mt-1">Restored: {", ".join(summary_items)}</div>'
                
                # Get organization ID for UI refresh
                organization_id = request.POST.get('organization', '')
                
                # Get fresh workspace and badges content for out-of-band updates
                workspace_content = self._get_workspace_content(request, organization_id)
                badges_content = self._get_badges_content(request, organization_id)
                table_content = self._get_table_content(request, organization_id)
                
                status_html = f'''
                <div class="alert alert-success alert-sm">
                    <span>{data['message']}</span>
                    {summary_html}
                    {warnings_html}
                </div>
                <div id="selected-columns-workspace" hx-swap-oob="innerHTML">
                    {workspace_content}
                </div>
                <div id="dataset-badges" hx-swap-oob="innerHTML">
                    {badges_content}
                </div>
                <div id="table-content" hx-swap-oob="innerHTML">
                    {table_content}
                </div>
                '''
                
                # Create HttpResponse with HTMX trigger headers
                response = HttpResponse(status_html)
                # Use HX-Trigger header to trigger events after swap
                trigger_data = {
                    'mappingLoaded': {'organization': organization_id},
                    'refreshMappings': True,
                    'clearMappingInput': True
                }
                response['HX-Trigger-After-Swap'] = json.dumps(trigger_data)
                return response
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <span>{error_msg}</span>
                </div>
                '''
                return HttpResponse(status_html)
        except Exception as e:
            # Add detailed error information for debugging
            status_html = f'''
            <div class="alert alert-error alert-sm">
                <span>Failed to load mapping: {str(e)}</span>
                <br><small>Status: {json_response.status_code}, Content: {json_response.content[:200]}</small>
            </div>
            '''
        return HttpResponse(status_html)


class DeleteMappingHTMXView(View):
    """HTMX wrapper for delete mapping that returns HTML status"""
    
    def post(self, request):
        """Delete mapping and return HTML status message"""
        # Call the original JSON view
        delete_view = DeleteMappingView()
        json_response = delete_view.post(request)
        
        # Convert JSON response to HTML status
        try:
            data = json_response.json() if hasattr(json_response, 'json') else {}
            
            if json_response.status_code == 200 and data.get('success'):
                status_html = f'''
                <div class="alert alert-success alert-sm">
                    <span>{data['message']}</span>
                </div>
                '''
                
                # Create response with HTMX trigger headers
                response = HttpResponse(status_html)
                trigger_data = {
                    'refreshMappings': True,
                    'clearMappingSelection': True
                }
                response['HX-Trigger-After-Swap'] = json.dumps(trigger_data)
                return response
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <span>{error_msg}</span>
                </div>
                '''
                return HttpResponse(status_html)
        except:
            status_html = '''
            <div class="alert alert-error alert-sm">
                <span>Failed to delete mapping</span>
            </div>
            '''
        return HttpResponse(status_html)


class RefreshWorkspaceView(CSVMappingCoordinatorMixin, View):
    """Refresh workspace UI after mapping load"""
    
    def get(self, request):
        """Return updated workspace HTML based on current session state"""
        organization_id = request.GET.get('organization')
        
        if not organization_id:
            return HttpResponse('<div class="alert alert-error">Organization ID required</div>', status=400)
        
        try:
            # Get current workspace state from session
            workspace_columns = self.get_workspace_columns(request, organization_id)
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            
            # Prepare datasets with columns for template
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            # Render the workspace template
            from django.template.loader import render_to_string
            from django.middleware.csrf import get_token
            
            context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': get_token(request),
                'selected_datasets': selected_datasets,
                'workspace_columns': workspace_columns
            }
            
            workspace_html = render_to_string(
                'csv_mapping/partials/selected_columns_workspace_content.html',
                context,
                request=request
            )
            
            return HttpResponse(workspace_html)
            
        except Exception as e:
            logger.error(f"REFRESH_WORKSPACE: Error refreshing workspace: {str(e)}")
            return HttpResponse(
                f'<div class="alert alert-error">Failed to refresh workspace: {str(e)}</div>',
                status=500
            )


class RefreshDatasetBadgesView(CSVMappingCoordinatorMixin, View):
    """Refresh dataset badges UI after mapping load"""
    
    def get(self, request):
        """Return updated dataset badges HTML based on current session state"""
        organization_id = request.GET.get('organization')
        
        if not organization_id:
            return HttpResponse('<div class="alert alert-error">Organization ID required</div>', status=400)
        
        try:
            # Get current state from session
            selected_datasets = self.get_selected_dataset_names(request, organization_id)
            all_datasets = self.get_csv_datasets_for_organization(organization_id)
            
            # Render the dataset badges template
            from django.template.loader import render_to_string
            from django.middleware.csrf import get_token
            
            context = {
                'datasets': all_datasets,  # Template expects 'datasets' not 'csv_datasets'
                'selected_datasets': selected_datasets,
                'organization_id': organization_id,
                'csrf_token': get_token(request),
            }
            
            # Find the correct template for dataset badges
            badges_html = render_to_string(
                'csv_mapping/partials/dataset_badges.html',
                context,
                request=request
            )
            
            return HttpResponse(badges_html)
            
        except Exception as e:
            logger.error(f"REFRESH_BADGES: Error refreshing dataset badges: {str(e)}")
            return HttpResponse(
                f'<div class="alert alert-error">Failed to refresh dataset badges: {str(e)}</div>',
                status=500
            ) 