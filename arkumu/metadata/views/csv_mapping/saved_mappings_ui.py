"""
CSV Mapping HTMX Views

This module contains pure HTMX views for UI state management in the CSV mapping interface.
These views complement the JSON-based persistence views by providing HTML responses 
for button states, status messages, and other UI elements.
"""

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
                    hx-trigger="click, updateState from:#mapping-select"
                    hx-get="/metadata/csv-update-button-state/"
                    hx-vals='{{"button": "load"}}'
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
                    hx-trigger="click, updateState from:#mapping-select"
                    hx-get="/metadata/csv-update-button-state/"
                    hx-vals='{{"button": "delete"}}'
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
                status_html = f'''
                <div class="alert alert-success alert-sm">
                    <span>{data['message']}</span>
                </div>
                <script>
                    // Clear input and refresh mappings
                    document.getElementById('mapping-name-input').value = '';
                    htmx.trigger('body', 'refreshMappings');
                </script>
                '''
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <span>{error_msg}</span>
                </div>
                '''
        except:
            status_html = '''
            <div class="alert alert-error alert-sm">
                <span>Failed to save mapping</span>
            </div>
            '''
        
        return HttpResponse(status_html)


class LoadMappingHTMXView(View):
    """HTMX wrapper for load mapping that returns HTML status"""
    
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
                    warnings_list = ''.join([f'<li>{w}</li>' for w in data['warnings']])
                    warnings_html = f'<ul class="text-sm mt-2">{warnings_list}</ul>'
                
                # Get organization ID for UI refresh
                organization_id = request.POST.get('organization', '')
                
                status_html = f'''
                <div class="alert alert-success alert-sm">
                    <span>{data['message']}</span>
                    {warnings_html}
                </div>
                <script>
                    // Comprehensive UI refresh after mapping load
                    setTimeout(() => {{
                        console.log('Loading mapping - refreshing workspace and UI');
                        
                        // 1. Refresh the main workspace area to show loaded columns
                        htmx.ajax('GET', '/metadata/csv-refresh-workspace/?organization={organization_id}', {{
                            target: '#selected-columns-workspace',
                            swap: 'innerHTML'
                        }});
                        
                        // 2. Refresh dataset selection badges to show selected datasets
                        htmx.ajax('GET', '/metadata/csv-refresh-dataset-badges/?organization={organization_id}', {{
                            target: '#dataset-badges',
                            swap: 'innerHTML'
                        }});
                        
                        // 3. Refresh any data preview areas
                        htmx.trigger('body', 'mappingLoaded');
                        
                        // 4. Clear the mapping name input (if exists)
                        const mappingInput = document.getElementById('mapping-name-input');
                        if (mappingInput) mappingInput.value = '';
                        
                        // 5. Refresh mappings dropdown
                        htmx.trigger('body', 'refreshMappings');
                        
                        console.log('Mapping loaded successfully - UI refreshed');
                    }}, 500);
                </script>
                '''
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <span>{error_msg}</span>
                </div>
                '''
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
                <script>
                    // Refresh mappings and clear selection
                    htmx.trigger('body', 'refreshMappings');
                    document.getElementById('mapping-select').value = '';
                </script>
                '''
            else:
                error_msg = data.get('error', 'Unknown error occurred')
                status_html = f'''
                <div class="alert alert-error alert-sm">
                    <span>{error_msg}</span>
                </div>
                '''
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