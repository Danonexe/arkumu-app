"""
Mapping Load Views - HTMX Integration

This module contains HTMX views specifically for loading mappings.
Focused on load operations with consolidated OOB updates.

Architecture:
- Single responsibility: Load operations only
- Consolidated OOB swaps for complete UI restoration
- Full coordinator mixin integration
"""

import json
import logging
from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string
from django.middleware.csrf import get_token

from arkumu.metadata.views.csv_mapping.saved_mappings_api import LoadMappingView
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class LoadMappingHTMXView(CSVMappingCoordinatorMixin, CSVMappingTemplateHelperMixin, View):
    """
    HTMX wrapper for load mapping with full coordinator integration.
    
    This view:
    1. Loads mapping via LoadMappingView (which uses coordinator.deserialize_mapping_state)
    2. Returns comprehensive HTMX response with multiple out-of-band updates
    3. Updates save section to show "update" mode with loaded mapping context
    4. Refreshes all UI components to reflect loaded state in one atomic response
    """
    
    def post(self, request):
        """Load mapping and return comprehensive consolidated HTMX response"""
        # Store request for access in helper methods
        self.request = request
        
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
            
            # Process response with consolidated UI updates
            return self._process_load_response(json_response, organization_id, mapping_id)
            
        except Exception as e:
            logger.error(f"LOAD_MAPPING_HTMX: Error processing request: {str(e)}")
            return self._render_error_response(f"Failed to load mapping: {str(e)}")
    
    def _execute_load(self, request):
        """Execute load operation via LoadMappingView"""
        load_view = LoadMappingView()
        return load_view.post(request)
    
    def _process_load_response(self, json_response, organization_id, mapping_id):
        """Process load response and return comprehensive consolidated HTMX updates"""
        try:
            if hasattr(json_response, 'content'):
                data = json.loads(json_response.content)
            else:
                data = {}
            
            if json_response.status_code == 200 and data.get('success'):
                return self._render_consolidated_load_success_response(data, organization_id)
            else:
                return self._render_load_error_response(data)
                
        except Exception as e:
            logger.error(f"Error processing load response: {str(e)}")
            return self._render_error_response("Failed to process load response")
    
    def _render_consolidated_load_success_response(self, data, organization_id):
        """Render load success with consolidated OOB updates for complete UI restoration"""
        mapping_id = data.get('mapping_id', '')
        mapping_name = data.get('mapping_name', 'Unknown')
        
        # Build main status message (goes to #mapping-status target)
        status_html = self._build_load_status_message(data, data.get('summary', {}), data.get('warnings', []))
        
        # Generate consolidated OOB updates for all affected UI components
        oob_updates = self._generate_consolidated_load_oob_updates(
            organization_id, mapping_id, mapping_name
        )
        
        # Combine main response with all OOB updates
        complete_response = status_html + oob_updates
        
        return HttpResponse(complete_response)
    
    def _generate_consolidated_load_oob_updates(self, organization_id, mapping_id, mapping_name):
        """Generate all necessary OOB updates using template helpers"""
        # Use template helper methods for consistent rendering
        workspace_html = self.render_workspace_template(self.request, organization_id)
        badges_html = self.render_dataset_badges_template(self.request, organization_id)
        table_html = self.render_table_content_template(self.request, organization_id)
        
        # Render save section with loaded mapping context
        save_section_html = self._render_save_section_content(
            organization_id, mapping_id, mapping_name
        )
        
        # Use template helper to build OOB response
        oob_updates = {
            'save-section': save_section_html,
            'workspace-content': workspace_html,
            'dataset-badges-container': badges_html,
            'table-content': table_html,
        }
        
        return self.build_oob_response("", oob_updates)
    
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
    
    def _render_save_section_content(self, organization_id, current_mapping_id=None, current_mapping_name=None):
        """Render save section with current context"""
        try:
            context = {
                'organization_id': organization_id,
                'csrf_token': get_token(self.request),
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
            }
            
            return render_to_string(
                'csv_mapping/partials/mapping_save_section.html',
                context,
                request=self.request
            )
        except Exception as e:
            logger.error(f"Error rendering save section: {str(e)}")
            return '<div class="alert alert-error">Failed to render save section</div>'
    

    
    def _render_load_error_response(self, data):
        """Render load error response"""
        error_msg = data.get('error', 'Unknown error occurred during load')
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>{error_msg}</span>
            </div>
        </div>
        ''')
    
    def _render_error_response(self, message):
        """Render generic error response"""
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm">
            <span>{message}</span>
        </div>
        ''') 