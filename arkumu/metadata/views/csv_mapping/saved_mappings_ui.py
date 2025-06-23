"""
Enhanced CSV Mapping HTMX Views with Full Coordinator Integration

This module provides HTMX-enabled views for mapping management that properly
integrate with the CSVMappingCoordinatorMixin for state consistency.

Architecture:
- Pure HTMX (no JavaScript)
- Full coordinator mixin integration  
- Proper state validation and updates
- Clean separation of concerns
"""

import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.middleware.csrf import get_token

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.saved_mappings_api import (
    SaveMappingView, UpdateMappingView, LoadMappingView, DeleteMappingView
)
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin

logger = logging.getLogger(__name__)


class ValidateMappingNameView(CSVMappingCoordinatorMixin, View):
    """
    Validate mapping names with full coordinator context awareness.
    
    This view properly handles both create and update scenarios by:
    1. Checking current workspace state via coordinator
    2. Validating name uniqueness with proper exclusions
    3. Determining appropriate button state and text
    """
    
    def get(self, request):
        """Validate mapping name and return dynamic save button HTML"""
        # Extract parameters
        mapping_name = request.GET.get('mapping_name', '').strip()
        organization_id = request.GET.get('organization')
        current_mapping_id = request.GET.get('current_mapping_id', '').strip()
        
        # Validate inputs
        if not organization_id:
            return self._render_error_button("Organization required")
        
        # Determine operation mode
        is_update_mode = bool(current_mapping_id)
        is_name_valid = bool(mapping_name)
        
        # Check for duplicates with proper exclusion logic
        is_duplicate = False
        if is_name_valid:
            duplicate_query = Mapping.objects.filter(
                organization_id=organization_id,
                name=mapping_name
            )
            
            # Exclude current mapping in update mode
            if is_update_mode:
                duplicate_query = duplicate_query.exclude(id=current_mapping_id)
            
            is_duplicate = duplicate_query.exists()
        
        # Get workspace state for additional validation
        workspace_columns = self.get_workspace_columns(request, organization_id)
        has_workspace_content = len(workspace_columns) > 0
        
        # Determine button state
        button_config = self._determine_button_config(
            is_name_valid, is_duplicate, is_update_mode, has_workspace_content
        )
        
        # Render button
        return self._render_save_button(
            button_config, organization_id, current_mapping_id, mapping_name
        )
    
    def _determine_button_config(self, is_name_valid, is_duplicate, is_update_mode, has_workspace_content):
        """Determine button configuration based on validation state"""
        
        # Invalid name
        if not is_name_valid:
            return {
                'enabled': False,
                'text': _("Update") if is_update_mode else _("Save"),
                'class': 'btn btn-sm btn-disabled',
                'message': _("Enter mapping name")
            }
        
        # Duplicate name
        if is_duplicate:
            return {
                'enabled': False, 
                'text': _("Update") if is_update_mode else _("Save"),
                'class': 'btn btn-sm btn-error',
                'message': _("Name already exists")
            }
        
        # Empty workspace (warn but allow)
        if not has_workspace_content:
            return {
                'enabled': True,
                'text': _("Update") if is_update_mode else _("Save"), 
                'class': 'btn btn-sm btn-warning',
                'message': _("Workspace is empty")
            }
        
        # Valid state
        return {
            'enabled': True,
            'text': _("Update") if is_update_mode else _("Save"),
            'class': 'btn btn-sm btn-success',
            'message': None
        }
    
    def _render_save_button(self, config, organization_id, current_mapping_id, mapping_name):
        """Render the save button with proper HTMX configuration"""
        csrf_token = get_token(self.request) if hasattr(self, 'request') else ''
        
        button_html = f'''
        <button class="{config['class']}" 
                id="save-mapping-btn"
                hx-post="/metadata/csv-save-mapping-htmx/"
                hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{csrf_token}"}}'
                hx-include="#mapping-name-input, #current-mapping-id"
                hx-target="#mapping-status"
                hx-swap="innerHTML"
                {'disabled' if not config['enabled'] else ''}>
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="{'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12' if current_mapping_id else 'M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3-3m0 0l-3 3m3-3v12'}"></path>
            </svg>
            {config['text']}
            {f'<span class="text-xs ml-1">({config["message"]})</span>' if config.get('message') else ''}
            <span class="loading loading-spinner loading-xs htmx-indicator ml-1"></span>
        </button>
        '''
        
        return HttpResponse(button_html)
    
    def _render_error_button(self, message):
        """Render disabled button with error message"""
        return HttpResponse(f'''
        <button class="btn btn-sm btn-disabled" disabled>
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            {message}
        </button>
        ''')


class UpdateButtonStateView(View):
    """Update load/delete button states based on mapping selection"""
    
    def get(self, request):
        """Return button HTML with enabled/disabled state based on selection"""
        button_type = request.GET.get('button')  # 'load' or 'delete'
        mapping_id = request.GET.get('mapping_id', '')
        organization_id = request.GET.get('organization')
        
        if button_type not in ['load', 'delete']:
            return HttpResponse("Invalid button type", status=400)
        
        has_selection = bool(mapping_id)
        csrf_token = get_token(request)
        
        if button_type == 'load':
            return self._render_load_button(has_selection, organization_id, csrf_token)
        else:
            return self._render_delete_button(has_selection, organization_id, csrf_token)
    
    def _render_load_button(self, enabled, organization_id, csrf_token):
        """Render load button with proper state"""
        button_class = "btn btn-sm btn-info flex-1" if enabled else "btn btn-sm btn-info flex-1 btn-disabled"
        
        return HttpResponse(f'''
        <button class="{button_class}" 
                id="load-mapping-btn"
                hx-post="/metadata/csv-load-mapping-htmx/"
                hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{csrf_token}"}}'
                hx-include="#mapping-select"
                hx-target="#mapping-status"
                hx-swap="innerHTML"
                hx-confirm="{_('This will replace your current mapping configuration. Continue?')}"
                {'disabled' if not enabled else ''}>
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"></path>
            </svg>
            {_("Load")}
            <span class="loading loading-spinner loading-xs htmx-indicator ml-1"></span>
        </button>
        ''')
    
    def _render_delete_button(self, enabled, organization_id, csrf_token):
        """Render delete button with proper state"""
        button_class = "btn btn-sm btn-error btn-outline" if enabled else "btn btn-sm btn-error btn-outline btn-disabled"
        
        return HttpResponse(f'''
        <button class="{button_class}" 
                id="delete-mapping-btn"
                hx-post="/metadata/csv-delete-mapping-htmx/"
                hx-vals='{{"organization": "{organization_id}", "csrfmiddlewaretoken": "{csrf_token}"}}'
                hx-include="#mapping-select"
                hx-target="#mapping-status"
                hx-swap="innerHTML"
                hx-confirm="{_('Are you sure you want to delete this mapping? This action cannot be undone.')}"
                {'disabled' if not enabled else ''}>
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
            </svg>
            <span class="hidden sm:inline">{_("Delete")}</span>
            <span class="loading loading-spinner loading-xs htmx-indicator ml-1"></span>
        </button>
        ''')


class SaveMappingHTMXView(CSVMappingCoordinatorMixin, View):
    """
    HTMX wrapper for save/update mapping with full coordinator integration.
    
    This view:
    1. Detects create vs update mode via current_mapping_id
    2. Delegates to appropriate backend view (SaveMappingView or UpdateMappingView)
    3. Returns proper HTMX responses with out-of-band updates
    4. Maintains UI state consistency
    """
    
    def post(self, request):
        """Process save/update request and return HTMX response"""
        # Extract parameters
        current_mapping_id = request.POST.get('current_mapping_id', '').strip()
        organization_id = request.POST.get('organization', '')
        mapping_name = request.POST.get('mapping_name', '').strip()
        
        # Validate inputs
        if not organization_id:
            return self._render_error_response("Organization ID is required")
        
        if not mapping_name:
            return self._render_error_response("Mapping name is required")
        
        # Determine operation mode and delegate
        is_update = bool(current_mapping_id)
        
        try:
            if is_update:
                json_response = self._execute_update(request, current_mapping_id)
            else:
                json_response = self._execute_create(request)
            
            # Process response
            return self._process_backend_response(
                json_response, organization_id, is_update, mapping_name
            )
            
        except Exception as e:
            logger.error(f"SAVE_MAPPING_HTMX: Error processing request: {str(e)}")
            return self._render_error_response(f"Failed to save mapping: {str(e)}")
    
    def _execute_update(self, request, mapping_id):
        """Execute update operation via UpdateMappingView"""
        # Prepare request for UpdateMappingView
        request.POST = request.POST.copy()
        request.POST['mapping_id'] = mapping_id
        
        update_view = UpdateMappingView()
        return update_view.post(request)
    
    def _execute_create(self, request):
        """Execute create operation via SaveMappingView"""
        save_view = SaveMappingView()
        return save_view.post(request)
    
    def _process_backend_response(self, json_response, organization_id, is_update, mapping_name):
        """Process backend JSON response and return HTMX HTML response"""
        try:
            data = json_response.json() if hasattr(json_response, 'json') else {}
            
            if json_response.status_code == 200 and data.get('success'):
                return self._render_success_response(data, organization_id, is_update)
            else:
                return self._render_validation_error_response(data)
                
        except Exception as e:
            logger.error(f"Error processing backend response: {str(e)}")
            return self._render_error_response("Failed to process response")
    
    def _render_success_response(self, data, organization_id, is_update):
        """Render success response with proper out-of-band updates"""
        mapping_id = data.get('mapping_id', '')
        mapping_name = data.get('mapping_name', 'Unknown')
        action_text = 'Updated' if is_update else 'Created'
        
        # Build main status message
        status_html = f'''
        <div class="alert alert-success alert-sm">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span>{data['message']}</span>
            </div>
            <div class="text-xs mt-1 opacity-75">
                {action_text} mapping: <strong>{mapping_name}</strong>
            </div>
        </div>
        '''
        
        # Add out-of-band updates
        oob_updates = self._generate_oob_updates(organization_id, is_update, mapping_id, mapping_name)
        
        # Combine main response with out-of-band updates
        complete_response = status_html + oob_updates
        
        # Create response with HTMX triggers
        response = HttpResponse(complete_response)
        response['HX-Trigger-After-Swap'] = json.dumps({
            'mappingSaved': {
                'mapping_id': mapping_id,
                'mapping_name': mapping_name, 
                'is_update': is_update
            },
            'refreshMappings': True
        })
        
        return response
    
    def _generate_oob_updates(self, organization_id, is_update, mapping_id, mapping_name):
        """Generate out-of-band HTML updates for UI consistency"""
        oob_html = ""
        
        # Update save section based on operation
        if is_update:
            # Keep in update mode
            save_section_html = self._render_save_section(organization_id, mapping_id, mapping_name)
        else:
            # Reset to create mode
            save_section_html = self._render_save_section(organization_id)
        
        oob_html += f'''
        <div id="save-section" hx-swap-oob="outerHTML">
            {save_section_html}
        </div>
        '''
        
        return oob_html
    
    def _render_save_section(self, organization_id, current_mapping_id=None, current_mapping_name=None):
        """Render save section with current context"""
        try:
            context = {
                'organization_id': organization_id,
                'csrf_token': get_token(self.request) if hasattr(self, 'request') else '',
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
            }
            
            return render_to_string(
                'csv_mapping/partials/mapping_save_section.html',
                context,
                request=getattr(self, 'request', None)
            )
        except Exception as e:
            logger.error(f"Error rendering save section: {str(e)}")
            return '<div class="alert alert-error">Failed to render save section</div>'
    
    def _render_validation_error_response(self, data):
        """Render validation error response"""
        error_msg = data.get('error', 'Unknown error occurred')
        validation_errors = data.get('validation_errors', [])
        validation_warnings = data.get('validation_warnings', [])
        
        # Build error details
        error_details = ''
        if validation_errors:
            error_list = ''.join([f'<li class="text-sm">{err}</li>' for err in validation_errors])
            error_details += f'<ul class="mt-2 ml-4 list-disc text-error">{error_list}</ul>'
        
        if validation_warnings:
            warning_list = ''.join([f'<li class="text-sm">{warn}</li>' for warn in validation_warnings])
            error_details += f'<div class="mt-2"><strong>Warnings:</strong><ul class="ml-4 list-disc text-warning">{warning_list}</ul></div>'
        
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>{error_msg}</span>
            </div>
            {error_details}
        </div>
        ''')
    
    def _render_error_response(self, message):
        """Render generic error response"""
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm">
            <span>{message}</span>
        </div>
        ''')


class LoadMappingHTMXView(CSVMappingCoordinatorMixin, View):
    """
    HTMX wrapper for load mapping with full coordinator integration.
    
    This view:
    1. Loads mapping via LoadMappingView (which uses coordinator.deserialize_mapping_state)
    2. Returns comprehensive HTMX response with multiple out-of-band updates
    3. Updates save section to show "update" mode with loaded mapping context
    4. Refreshes all UI components to reflect loaded state
    """
    
    def post(self, request):
        """Load mapping and return comprehensive HTMX response"""
        # Extract parameters
        organization_id = request.POST.get('organization', '')
        mapping_id = request.POST.get('mapping_id', '')
        
        # Validate inputs
        if not organization_id:
            return self._render_error_response("Organization ID is required")
        
        if not mapping_id:
            return self._render_error_response("Mapping ID is required")
        
        try:
            # Execute load operation via LoadMappingView (uses coordinator)
            json_response = self._execute_load(request)
            
            # Process response
            return self._process_load_response(json_response, organization_id, mapping_id)
            
        except Exception as e:
            logger.error(f"LOAD_MAPPING_HTMX: Error processing request: {str(e)}")
            return self._render_error_response(f"Failed to load mapping: {str(e)}")
    
    def _execute_load(self, request):
        """Execute load operation via LoadMappingView"""
        load_view = LoadMappingView()
        return load_view.post(request)
    
    def _process_load_response(self, json_response, organization_id, mapping_id):
        """Process load response and return comprehensive HTMX updates"""
        try:
            if hasattr(json_response, 'content'):
                import json
                data = json.loads(json_response.content)
            else:
                data = {}
            
            if json_response.status_code == 200 and data.get('success'):
                return self._render_load_success_response(data, organization_id)
            else:
                return self._render_load_error_response(data)
                
        except Exception as e:
            logger.error(f"Error processing load response: {str(e)}")
            return self._render_error_response("Failed to process load response")
    
    def _render_load_success_response(self, data, organization_id):
        """Render success response with comprehensive out-of-band updates"""
        mapping_id = data.get('mapping_id', '')
        mapping_name = data.get('mapping_name', 'Unknown')
        summary = data.get('summary', {})
        warnings = data.get('warnings', [])
        
        # Build main status message
        status_html = self._build_load_status_message(data, summary, warnings)
        
        # Generate all out-of-band updates
        oob_updates = self._generate_load_oob_updates(organization_id, mapping_id, mapping_name)
        
        # Combine response
        complete_response = status_html + oob_updates
        
        # Create response with HTMX triggers
        response = HttpResponse(complete_response)
        response['HX-Trigger-After-Swap'] = json.dumps({
            'mappingLoaded': {
                'mapping_id': mapping_id,
                'mapping_name': mapping_name,
                'organization_id': organization_id
            },
            'refreshMappings': True
        })
        
        return response
    
    def _build_load_status_message(self, data, summary, warnings):
        """Build the main status message for successful load"""
        warnings_html = ''
        if warnings:
            warnings_list = ''.join([f'<li class="text-sm">{w}</li>' for w in warnings])
            warnings_html = f'<ul class="text-sm mt-2 ml-4 list-disc text-warning">{warnings_list}</ul>'
        
        # Build summary information
        summary_html = ''
        if summary:
            summary_items = []
            if summary.get('datasets_restored', 0) > 0:
                summary_items.append(f"{summary['datasets_restored']} datasets")
            if summary.get('columns_restored', 0) > 0:
                summary_items.append(f"{summary['columns_restored']} columns")
            if summary.get('fk_relationships_restored', 0) > 0:
                summary_items.append(f"{summary['fk_relationships_restored']} FK relationships")
            
            if summary_items:
                summary_html = f'<div class="text-sm text-success mt-1">Restored: {", ".join(summary_items)}</div>'
        
        return f'''
        <div class="alert alert-success alert-sm">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span>{data['message']}</span>
            </div>
            {summary_html}
            {warnings_html}
        </div>
        '''
    
    def _generate_load_oob_updates(self, organization_id, mapping_id, mapping_name):
        """Generate all out-of-band updates for successful mapping load"""
        oob_html = ""
        
        # 1. Update save section to show "update" mode
        save_section_html = self._render_save_section(organization_id, mapping_id, mapping_name)
        oob_html += f'''
        <div id="save-section" hx-swap-oob="outerHTML">
            {save_section_html}
        </div>
        '''
        
        # 2. Update workspace content
        workspace_html = self._get_workspace_content(organization_id)
        oob_html += f'''
        <div id="selected-columns-workspace" hx-swap-oob="innerHTML">
            {workspace_html}
        </div>
        '''
        
        # 3. Update dataset badges
        badges_html = self._get_badges_content(organization_id)
        oob_html += f'''
        <div id="dataset-badges" hx-swap-oob="innerHTML">
            {badges_html}
        </div>
        '''
        
        # 4. Update table content (dataset cards)
        table_html = self._get_table_content(organization_id)
        oob_html += f'''
        <div id="table-content" hx-swap-oob="innerHTML">
            {table_html}
        </div>
        '''
        
        return oob_html
    
    def _render_save_section(self, organization_id, current_mapping_id=None, current_mapping_name=None):
        """Render save section with current context"""
        try:
            context = {
                'organization_id': organization_id,
                'csrf_token': get_token(self.request) if hasattr(self, 'request') else '',
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
            }
            
            return render_to_string(
                'csv_mapping/partials/mapping_save_section.html',
                context,
                request=getattr(self, 'request', None)
            )
        except Exception as e:
            logger.error(f"Error rendering save section: {str(e)}")
            return '<div class="alert alert-error">Failed to render save section</div>'
    
    def _get_workspace_content(self, organization_id):
        """Get workspace content using coordinator methods"""
        try:
            # Use coordinator to get current workspace state
            workspace_columns = self.get_workspace_columns(self.request, organization_id)
            selected_datasets = self.get_selected_dataset_names(self.request, organization_id)
            datasets_with_columns = self._prepare_datasets_with_columns(workspace_columns)
            
            context = {
                'datasets_with_columns': datasets_with_columns,
                'organization_id': organization_id,
                'csrf_token': get_token(self.request),
                'selected_datasets': selected_datasets,
                'workspace_columns': workspace_columns
            }
            
            return render_to_string(
                'csv_mapping/partials/selected_columns_workspace.html',
                context,
                request=self.request
            )
        except Exception as e:
            logger.error(f"Error getting workspace content: {str(e)}")
            return '<div class="alert alert-error">Failed to load workspace</div>'
    
    def _get_badges_content(self, organization_id):
        """Get badges content for out-of-band update"""
        try:
            selected_datasets = self.get_selected_dataset_names(self.request, organization_id)
            all_datasets = self.get_csv_datasets_for_organization(organization_id)
            
            context = {
                'datasets': all_datasets,
                'selected_datasets': selected_datasets,
                'organization_id': organization_id,
                'csrf_token': get_token(self.request),
            }
            
            return render_to_string(
                'csv_mapping/partials/dataset_badges.html',
                context,
                request=self.request
            )
        except Exception as e:
            logger.error(f"Error getting badges content: {str(e)}")
            return '<div class="alert alert-error">Failed to load badges</div>'
    
    def _get_save_section_content(self, request, organization_id, current_mapping_id=None, current_mapping_name=None):
        """Get save section content with current mapping context"""
        try:
            from django.middleware.csrf import get_token
            context = {
                'organization_id': organization_id,
                'csrf_token': get_token(request),
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
            }
            
            return render_to_string(
                'csv_mapping/partials/mapping_save_section.html',
                context,
                request=request
            )
        except Exception as e:
            logger.error(f"Error getting save section content: {str(e)}")
            return '<div class="alert alert-error">Failed to load save section</div>'

    def _get_table_content(self, organization_id):
        """Get table content (dataset cards) for out-of-band update"""
        try:
            selected_datasets = self.get_selected_dataset_names(self.request, organization_id)
            
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
            workspace_columns = self.get_workspace_columns(self.request, organization_id)
            
            # Prepare dataset-specific selected columns for each dataset
            dataset_selected_columns_map = {}
            for dataset in selected_datasets_with_details:
                dataset_name = dataset.get('name')
                
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
                
                context = {
                    'dataset': dataset,
                    'organization_id': organization_id,
                    'csrf_token': get_token(self.request),
                    'selected_columns': workspace_columns,
                    'dataset_selected_columns': dataset_selected_columns,
                }
                
                dataset_card_html = render_to_string(
                    'csv_mapping/partials/dataset_card.html',
                    context,
                    request=self.request
                )
                dataset_cards_html += dataset_card_html
            
            return dataset_cards_html
        except Exception as e:
            logger.error(f"Error getting table content: {str(e)}")
            return f'<div class="alert alert-error">Failed to load dataset cards: {str(e)}</div>'
    



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
                'csv_mapping/partials/selected_columns_workspace.html',
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
            
            # DEBUG: Log what RefreshDatasetBadgesView is finding
            logger.info(f"🔄 REFRESH_BADGES: Found {len(selected_datasets)} selected datasets: {selected_datasets}")
            logger.info(f"🔄 REFRESH_BADGES: Found {len(all_datasets)} total datasets")
            
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