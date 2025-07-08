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
from arkumu.users.mixins import GeneralLoginRequiredMixin

from arkumu.metadata.views.csv_mapping.saved_mappings_api import LoadMappingView
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class LoadMappingHTMXView(GeneralLoginRequiredMixin, CSVMappingCoordinatorMixin, CSVMappingTemplateHelperMixin, View):
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
        
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Starting load request - org={organization_id}, mapping_id={mapping_id}")
        
        # Validate inputs
        if not organization_id:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Missing organization_id")
            return self._render_error_response("Organization ID is required")
        
        if not mapping_id:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Missing mapping_id")
            return self._render_error_response("Mapping ID is required")
        
        try:
            # Execute load operation via LoadMappingView (uses coordinator)
            logger.info(f"🔵 LOAD_MAPPING_HTMX: Executing load via LoadMappingView...")
            json_response = self._execute_load(request)
            logger.info(f"🔵 LOAD_MAPPING_HTMX: LoadMappingView returned status_code={json_response.status_code}")
            
            # Process response with consolidated UI updates
            logger.info(f"🔵 LOAD_MAPPING_HTMX: Processing load response...")
            return self._process_load_response(json_response, organization_id, mapping_id)
            
        except Exception as e:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Error processing request: {str(e)}", exc_info=True)
            return self._render_error_response(f"Failed to load mapping: {str(e)}")
    
    def _execute_load(self, request):
        """Execute load operation via LoadMappingView"""
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Creating LoadMappingView instance...")
        load_view = LoadMappingView()
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Calling LoadMappingView.post()...")
        response = load_view.post(request)
        logger.info(f"🔵 LOAD_MAPPING_HTMX: LoadMappingView.post() completed with status {response.status_code}")
        return response
    
    def _process_load_response(self, json_response, organization_id, mapping_id):
        """Process load response and return comprehensive consolidated HTMX updates"""
        try:
            logger.info(f"🔵 LOAD_MAPPING_HTMX: Parsing JSON response...")
            if hasattr(json_response, 'content'):
                data = json.loads(json_response.content)
                logger.info(f"🔵 LOAD_MAPPING_HTMX: Parsed JSON data: success={data.get('success')}, keys={list(data.keys())}")
            else:
                data = {}
                logger.warning(f"🟡 LOAD_MAPPING_HTMX: No content in response")
            
            if json_response.status_code == 200 and data.get('success'):
                logger.info(f"🟢 LOAD_MAPPING_HTMX: Success response - rendering UI updates...")
                return self._render_consolidated_load_success_response(data, organization_id)
            else:
                logger.error(f"🔴 LOAD_MAPPING_HTMX: Error response - status={json_response.status_code}, data={data}")
                return self._render_load_error_response(data)
                
        except Exception as e:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Error processing load response: {str(e)}", exc_info=True)
            return self._render_error_response("Failed to process load response")
    
    def _render_consolidated_load_success_response(self, data, organization_id):
        """Render load success - just update workspace and mapping controls"""
        mapping_id = data.get('mapping_id', '')
        mapping_name = data.get('mapping_name', 'Unknown')
        
        logger.info(f"🚀🚀🚀 _render_consolidated_load_success_response CALLED! mapping='{mapping_name}' (ID: {mapping_id}) 🚀🚀🚀")
        logger.info(f"🟢 LOAD_MAPPING_HTMX: Building success response for mapping '{mapping_name}' (ID: {mapping_id})")
        
        # CRITICAL: Ensure session is fully synchronized before rendering workspace
        # The LoadMappingView.post() modified the session, but we need to ensure
        # the current request context sees those changes
        self.request.session.save()
        
        # Verify workspace columns are actually in session before rendering
        workspace_columns = self.get_workspace_columns(self.request, organization_id)
        logger.info(f"🟢 LOAD_MAPPING_HTMX: Verified {len(workspace_columns)} workspace columns in session before rendering")
        
        # Just render the workspace since that's what has the loaded columns
        workspace_html = self.render_workspace_template(self.request, organization_id)
        
        # Get actual mapping from database for real updated time
        from arkumu.metadata.models.mappings import Mapping
        try:
            mapping_obj = Mapping.objects.get(id=mapping_id)
            updated_time = mapping_obj.updated_at.strftime('%Y-%m-%d %H:%M')
            validation_status = mapping_obj.validation_status
        except Mapping.DoesNotExist:
            updated_time = "Unknown"
            validation_status = "draft"
        
        # Render navbar controls with loaded mapping info
        navbar_context = {
            'organization_id': organization_id,
            'current_mapping_id': mapping_id,
            'current_mapping_name': mapping_name,
            'current_mapping_updated': updated_time,
            'current_mapping_status': validation_status,
            'csrf_token': get_token(self.request),
        }
        logger.info(f"🔍 LOAD_MAPPING: Rendering navbar with context: {navbar_context}")
        logger.info(f"🔍 LOAD_MAPPING: DETAILED CONTEXT VALUES:")
        logger.info(f"🔍   - current_mapping_id: '{mapping_id}' (type: {type(mapping_id)}, bool: {bool(mapping_id)})")
        logger.info(f"🔍   - current_mapping_name: '{mapping_name}' (type: {type(mapping_name)}, bool: {bool(mapping_name)})")
        logger.info(f"🔍   - current_mapping_updated: '{updated_time}' (type: {type(updated_time)}, bool: {bool(updated_time)})")
        logger.info(f"🔍   - current_mapping_status: '{validation_status}' (type: {type(validation_status)}, bool: {bool(validation_status)})")
        logger.info(f"🔍   - organization_id: '{organization_id}' (type: {type(organization_id)}, bool: {bool(organization_id)})")
        
        navbar_html = render_to_string(
            'csv_mapping/partials/navbar_mapping_controls.html',
            navbar_context,
            request=self.request
        )
        logger.info(f"🔍 LOAD_MAPPING: Navbar HTML length: {len(navbar_html)} chars")
        logger.info(f"🔍 LOAD_MAPPING: Navbar HTML preview: {navbar_html[:200]}...")
        
        # Build OOB updates for workspace and navbar
        oob_updates = {
            'workspace-content': workspace_html,
            'navbar-mapping-controls': navbar_html,
        }
        logger.info(f"🔍 LOAD_MAPPING: Building OOB response with targets: {list(oob_updates.keys())}")
        
        final_response = self.build_oob_response("", oob_updates)
        logger.info(f"🔍 LOAD_MAPPING: Final response length: {len(final_response)} chars")
        logger.info(f"🔍 LOAD_MAPPING: Final response preview: {final_response[:300]}...")
        
        return HttpResponse(final_response)
    
    def _generate_consolidated_load_oob_updates(self, organization_id, mapping_id, mapping_name):
        """Generate necessary OOB updates for mapping load (workspace and save section only)"""
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Rendering workspace template...")
        
        # CRITICAL: Ensure session is fully synchronized before rendering workspace
        self.request.session.save()
        
        # Verify workspace columns are actually in session before rendering
        workspace_columns = self.get_workspace_columns(self.request, organization_id)
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Verified {len(workspace_columns)} workspace columns in session before rendering")
        
        # Use template helper methods for consistent rendering
        try:
            workspace_html = self.render_workspace_template(self.request, organization_id)
            logger.info(f"🔵 LOAD_MAPPING_HTMX: Workspace template rendered - length: {len(workspace_html)} chars")
        except Exception as e:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Error rendering workspace template: {str(e)}", exc_info=True)
            workspace_html = '<div class="alert alert-error">Failed to render workspace</div>'
        
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Rendering save section template...")
        
        # Render save section with loaded mapping context
        try:
            save_section_html = self._render_save_section_content(
                organization_id, mapping_id, mapping_name
            )
            logger.info(f"🔵 LOAD_MAPPING_HTMX: Save section template rendered - length: {len(save_section_html)} chars")
        except Exception as e:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Error rendering save section template: {str(e)}", exc_info=True)
            save_section_html = '<div class="alert alert-error">Failed to render save section</div>'
        
        # Load mapping should only update workspace - mapping controls will get updated via main-content refresh
        # Dataset selection interface should remain unchanged  
        oob_updates = {
            'workspace-content': workspace_html,
        }
        
        logger.info(f"🔵 LOAD_MAPPING_HTMX: Building OOB response with {len(oob_updates)} updates")
        
        try:
            oob_response = self.build_oob_response("", oob_updates)
            logger.info(f"🔵 LOAD_MAPPING_HTMX: OOB response built - length: {len(oob_response)} chars")
            return oob_response
        except Exception as e:
            logger.error(f"🔴 LOAD_MAPPING_HTMX: Error building OOB response: {str(e)}", exc_info=True)
            return '<div class="alert alert-error">Failed to build response</div>'
    
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