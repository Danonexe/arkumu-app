"""
Mapping Save Views - HTMX Integration

This module contains HTMX views specifically for saving and updating mappings.
Focused on create/update operations with consolidated OOB updates.

Architecture:
- Single responsibility: Save/Update operations only
- Consolidated OOB swaps for atomic UI updates
- Full coordinator mixin integration
"""

import json
import logging
from django.http import HttpResponse
from django.views import View
from django.template.loader import render_to_string
from django.middleware.csrf import get_token

from arkumu.metadata.views.csv_mapping.saved_mappings_api import (
    SaveMappingView, UpdateMappingView
)
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class SaveMappingHTMXView(CSVMappingCoordinatorMixin, CSVMappingTemplateHelperMixin, View):
    """
    HTMX wrapper for save/update mapping with full coordinator integration.
    
    This view:
    1. Detects create vs update mode via current_mapping_id
    2. Delegates to appropriate backend view (SaveMappingView or UpdateMappingView)
    3. Returns consolidated HTMX response with all UI updates in one go
    4. Maintains UI state consistency through OOB swaps
    """
    
    def post(self, request):
        """Process save/update request and return consolidated HTMX response"""
        # Store request for access in helper methods
        self.request = request
        
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
            
            # Process response with consolidated UI updates
            return self._process_backend_response(
                json_response, organization_id, is_update, mapping_name
            )
            
        except Exception as e:
            logger.error(f"SAVE_MAPPING_HTMX: Error processing request: {str(e)}")
            return self._render_error_response(f"Failed to save mapping: {str(e)}")
    
    def _execute_update(self, request, mapping_id):
        """Execute update operation via UpdateMappingView"""
        request.POST = request.POST.copy()
        request.POST['mapping_id'] = mapping_id
        
        update_view = UpdateMappingView()
        return update_view.post(request)
    
    def _execute_create(self, request):
        """Execute create operation via SaveMappingView"""
        save_view = SaveMappingView()
        return save_view.post(request)
    
    def _process_backend_response(self, json_response, organization_id, is_update, mapping_name):
        """Process backend JSON response and return consolidated HTMX HTML response"""
        try:
            data = json_response.json() if hasattr(json_response, 'json') else {}
            
            if json_response.status_code == 200 and data.get('success'):
                return self._render_consolidated_success_response(data, organization_id, is_update)
            else:
                return self._render_validation_error_response(data)
                
        except Exception as e:
            logger.error(f"Error processing backend response: {str(e)}")
            return self._render_error_response("Failed to process response")
    
    def _render_consolidated_success_response(self, data, organization_id, is_update):
        """Render success response with consolidated OOB updates for all UI components"""
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
        
        # Generate consolidated OOB updates
        oob_updates = self._generate_consolidated_oob_updates(
            organization_id, is_update, mapping_id, mapping_name
        )
        
        # Combine main response with all OOB updates
        complete_response = status_html + oob_updates
        
        return HttpResponse(complete_response)
    
    def _generate_consolidated_oob_updates(self, organization_id, is_update, mapping_id, mapping_name):
        """Generate all necessary OOB updates using template helpers"""
        # Use template helper methods for consistent rendering
        workspace_html = self.render_workspace_template(self.request, organization_id)
        badges_html = self.render_dataset_badges_template(self.request, organization_id)
        
        # Render save section with current context
        save_section_html = self._render_save_section_content(
            organization_id, 
            mapping_id if is_update else None,
            mapping_name if is_update else None
        )
        
        # Use template helper to build OOB response  
        oob_updates = {
            'save-section': save_section_html,
            'workspace-content': workspace_html,
            'dataset-badges-container': badges_html,
        }
        
        return self.build_oob_response("", oob_updates)
    
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