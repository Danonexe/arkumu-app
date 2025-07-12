"""
Mapping Delete Views - HTMX Integration

This module contains HTMX views specifically for deleting mappings.
Focused on delete operations with simple JSON-to-HTML conversion.

Architecture:
- Single responsibility: Delete operations only
- Simple JSON wrapper that returns HTML status
- No complex OOB updates (delete is simple)
"""

import json
import logging
from django.http import HttpResponse
from django.views import View
from arkumu.users.mixins import GeneralLoginRequiredMixin

from arkumu.metadata.views.csv_mapping.saved_mappings_api import DeleteMappingView

logger = logging.getLogger(__name__)


class DeleteMappingHTMXView(GeneralLoginRequiredMixin, View):
    """
    HTMX wrapper for delete mapping that returns HTML status.
    
    This is a simple view that:
    1. Delegates to DeleteMappingView for the actual deletion
    2. Converts JSON response to HTML status
    3. Returns appropriate success/error HTML
    """
    
    def post(self, request):
        """Delete mapping and return HTML status message"""
        try:
            # Call the original JSON view
            delete_view = DeleteMappingView()
            json_response = delete_view.post(request)
            
            # Convert JSON response to HTML status
            return self._process_delete_response(json_response)
            
        except Exception as e:
            logger.error(f"DELETE_MAPPING_HTMX: Error processing request: {str(e)}")
            return self._render_error_response(f"Failed to delete mapping: {str(e)}")
    
    def _process_delete_response(self, json_response):
        """Process delete response and return appropriate HTML"""
        try:
            data = json_response.json() if hasattr(json_response, 'json') else {}
            
            if json_response.status_code == 200 and data.get('success'):
                return self._render_success_response(data)
            else:
                return self._render_delete_error_response(data)
                
        except Exception as e:
            logger.error(f"Error processing delete response: {str(e)}")
            return self._render_error_response("Failed to process delete response")
    
    def _render_success_response(self, data):
        """Render successful deletion HTML"""
        return HttpResponse(f'''
        <div class="alert alert-success alert-sm relative">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span>{data['message']}</span>
            </div>
            <button class="btn btn-sm btn-circle btn-ghost absolute top-2 right-2" onclick="this.parentElement.remove()">✕</button>
        </div>
        ''')
    
    def _render_delete_error_response(self, data):
        """Render deletion error HTML"""
        error_msg = data.get('error', 'Unknown error occurred during deletion')
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm relative">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>{error_msg}</span>
            </div>
            <button class="btn btn-sm btn-circle btn-ghost absolute top-2 right-2" onclick="this.parentElement.remove()">✕</button>
        </div>
        ''')
    
    def _render_error_response(self, message):
        """Render generic error response"""
        return HttpResponse(f'''
        <div class="alert alert-error alert-sm relative">
            <span>{message}</span>
            <button class="btn btn-sm btn-circle btn-ghost absolute top-2 right-2" onclick="this.parentElement.remove()">✕</button>
        </div>
        ''') 