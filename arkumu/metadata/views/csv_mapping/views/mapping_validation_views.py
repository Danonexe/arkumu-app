"""
Mapping Validation Views - HTMX Integration

This module contains HTMX views specifically for mapping validation and UI state management.
Focused on validation operations and button state updates.

Architecture:
- Single responsibility: Validation and UI state management only
- Real-time validation feedback
- Dynamic button state management
- Full coordinator mixin integration
"""

import logging
from django.http import HttpResponse
from django.views import View
from django.utils.translation import gettext as _
from django.middleware.csrf import get_token

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class ValidateMappingNameView(CSVMappingCoordinatorMixin, CSVMappingTemplateHelperMixin, View):
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