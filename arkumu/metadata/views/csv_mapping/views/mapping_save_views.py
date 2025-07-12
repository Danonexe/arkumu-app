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
from django.utils import timezone
from arkumu.users.mixins import GeneralLoginRequiredMixin

from arkumu.metadata.views.csv_mapping.saved_mappings_api import (
    SaveMappingView, UpdateMappingView
)
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class SaveMappingHTMXView(GeneralLoginRequiredMixin, CSVMappingCoordinatorMixin, CSVMappingTemplateHelperMixin, View):
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
        logger.info(f"🚀 SAVE_MAPPING_HTMX: POST request received")
        logger.info(f"🚀 SAVE_MAPPING_HTMX: POST data: {dict(request.POST)}")
        logger.info(f"🚀 SAVE_MAPPING_HTMX: HTMX headers: {dict((k, v) for k, v in request.headers.items() if k.startswith('HX'))}")
        
        # Store request for access in helper methods
        self.request = request
        
        # Extract parameters
        current_mapping_id = request.POST.get('current_mapping_id', '').strip()
        organization_id = request.POST.get('organization', '')
        mapping_name = request.POST.get('mapping_name', '').strip()
        
        logger.info(f"🚀 SAVE_MAPPING_HTMX: Extracted params - org={organization_id}, name='{mapping_name}', current_id='{current_mapping_id}'")
        
        # Validate inputs
        if not organization_id:
            logger.error(f"🚀 SAVE_MAPPING_HTMX: Missing organization_id")
            return self._render_error_response("Organization ID is required")
        
        if not mapping_name:
            logger.error(f"🚀 SAVE_MAPPING_HTMX: Missing mapping_name")
            return self._render_error_response("Mapping name is required")
        
        # Determine operation mode and delegate
        is_update = bool(current_mapping_id)
        logger.info(f"🚀 SAVE_MAPPING_HTMX: Operation mode - is_update={is_update}")
        
        try:
            if is_update:
                logger.info(f"🚀 SAVE_MAPPING_HTMX: Executing update operation for mapping {current_mapping_id}")
                json_response = self._execute_update(request, current_mapping_id)
            else:
                logger.info(f"🚀 SAVE_MAPPING_HTMX: Executing create operation")
                json_response = self._execute_create(request)
            
            logger.info(f"🚀 SAVE_MAPPING_HTMX: Backend operation completed with status {json_response.status_code}")
            
            # Process response with consolidated UI updates
            return self._process_backend_response(
                json_response, organization_id, is_update, mapping_name
            )
            
        except Exception as e:
            logger.error(f"🔴 SAVE_MAPPING_HTMX: Error processing request: {str(e)}", exc_info=True)
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
        logger.info(f"🔄 PROCESS_BACKEND: Processing backend response - status={json_response.status_code}")
        
        try:
            import json as json_module
            
            logger.info(f"🔄 PROCESS_BACKEND: Response type: {type(json_response)}")
            logger.info(f"🔄 PROCESS_BACKEND: Response content: {getattr(json_response, 'content', 'No content attr')}")
            
            # Handle Django JsonResponse vs requests Response objects
            if hasattr(json_response, 'json') and callable(getattr(json_response, 'json')):
                # This is a requests Response object
                try:
                    data = json_response.json()
                    logger.info(f"🔄 PROCESS_BACKEND: Successfully parsed JSON via .json() method: {data}")
                except Exception as json_error:
                    logger.error(f"🔄 PROCESS_BACKEND: Failed to parse JSON via .json(): {json_error}")
                    data = {}
            elif hasattr(json_response, 'content'):
                # This is a Django Response object - parse content manually
                try:
                    content_str = json_response.content.decode('utf-8') if isinstance(json_response.content, bytes) else str(json_response.content)
                    data = json_module.loads(content_str)
                    logger.info(f"🔄 PROCESS_BACKEND: Successfully parsed JSON from content: {data}")
                except Exception as json_error:
                    logger.error(f"🔄 PROCESS_BACKEND: Failed to parse JSON from content: {json_error}")
                    logger.error(f"🔄 PROCESS_BACKEND: Raw content: {json_response.content}")
                    data = {}
            else:
                logger.warning(f"🔄 PROCESS_BACKEND: Unknown response type - no content or json method")
                data = {}
            
            logger.info(f"🔄 PROCESS_BACKEND: Final response data: {data}")
            
            if json_response.status_code == 200 and data.get('success'):
                logger.info(f"🔄 PROCESS_BACKEND: Success response detected, proceeding to consolidated success render")
                return self._render_consolidated_success_response(data, organization_id, is_update)
            else:
                logger.warning(f"🔄 PROCESS_BACKEND: Error response detected - status={json_response.status_code}, success={data.get('success')}")
                return self._render_validation_error_response(data)
                
        except Exception as e:
            logger.error(f"🔴 PROCESS_BACKEND: Error processing backend response: {str(e)}", exc_info=True)
            return self._render_error_response("Failed to process response")
    
    def _render_consolidated_success_response(self, data, organization_id, is_update):
        """Render success response using standard template helpers"""
        mapping_id = data.get('mapping_id', '')
        mapping_name = data.get('mapping_name', 'Unknown')
        updated_at = data.get('updated_at')
        validation_status = data.get('validation_status', 'draft')
        action_text = 'Updated' if is_update else 'Created'
        
        logger.info(f"🚀 SAVE_HTMX_SUCCESS: Starting consolidated success response - action={action_text}, mapping_id={mapping_id}, name={mapping_name}")
        logger.info(f"🚀 SAVE_HTMX_SUCCESS: Raw backend data: {data}")
        
        # Format the updated timestamp from database for display
        current_mapping_updated = None
        if updated_at:
            try:
                from datetime import datetime
                updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                current_mapping_updated = updated_dt.strftime('%b %d, %Y at %H:%M')
                logger.info(f"🕒 SAVE_HTMX_SUCCESS: Formatted timestamp: '{updated_at}' -> '{current_mapping_updated}'")
            except Exception as e:
                logger.warning(f"🕒 SAVE_HTMX_SUCCESS: Could not parse updated_at timestamp '{updated_at}': {e}")
                current_mapping_updated = "Just now"
        else:
            logger.warning(f"🕒 SAVE_HTMX_SUCCESS: No updated_at timestamp in backend response")
        
        # Update loaded mapping context in session if this was an update
        if is_update and mapping_id:
            # Use BaseCoordinatorMixin's set_current_mapping method for proper session management
            mapping_data = self.set_current_mapping(
                self.request, 
                mapping_id, 
                mapping_name, 
                organization_id
            )
            logger.info(f"💾 SAVE_HTMX_SUCCESS: Updated current mapping using BaseCoordinatorMixin: {mapping_data}")
            logger.info(f"💾 SAVE_HTMX_SUCCESS: Session updated successfully")
        
        # Build custom response that includes navbar update (no success message)
        success_message = ''  # Remove the success message
        logger.info(f"📝 SAVE_HTMX_SUCCESS: Success message removed (empty)")
        
        # Render ONLY navbar - save operation should not change workspace, badges, or table
        logger.info(f"🎯 SAVE_HTMX_SUCCESS: Rendering ONLY navbar (save should not modify workspace/badges/table)")
        logger.info(f"🎯 SAVE_HTMX_SUCCESS: About to render navbar with: mapping_id={mapping_id}, name={mapping_name}, updated={current_mapping_updated}, status={validation_status}")
        navbar_html = self._render_navbar_controls(
            organization_id, mapping_id, mapping_name, 
            current_mapping_updated, validation_status
        )
        logger.info(f"🎯 SAVE_HTMX_SUCCESS: Navbar template rendered ({len(navbar_html)} chars)")
        
        # Build OOB updates - ONLY navbar mapping controls
        oob_updates = {
            'navbar-mapping-controls': navbar_html,
        }
        logger.info(f"📦 SAVE_HTMX_SUCCESS: OOB updates prepared (navbar only): {list(oob_updates.keys())}")
        
        response_html = self.build_oob_response(success_message, oob_updates)
        logger.info(f"📤 SAVE_HTMX_SUCCESS: Final response built ({len(response_html)} chars)")
        
        final_response = self.add_workspace_update_trigger(response_html)
        logger.info(f"✅ SAVE_HTMX_SUCCESS: Final response with workspace trigger ready ({len(final_response.content)} bytes)")
        
        return final_response
    
    def _generate_consolidated_oob_updates(self, organization_id, is_update, mapping_id, mapping_name):
        """Generate all necessary OOB updates using template helpers and coordinator methods"""
        logger.info(f"OOB_UPDATES: Starting OOB generation for mapping_id='{mapping_id}', is_update={is_update}")
        
        # Update session state for loaded mapping using coordinator method
        if is_update and mapping_id:
            # Use coordinator method to properly set loaded mapping context
            # Use BaseCoordinatorMixin's set_current_mapping method for proper session management
            mapping_data = self.set_current_mapping(
                self.request, 
                mapping_id, 
                mapping_name, 
                organization_id
            )
            
            # Log session state after setting
            logger.info(f"OOB_UPDATES: Session after setting: {list(self.request.session.keys())}")
            logger.info(f"OOB_UPDATES: Set loaded mapping context using BaseCoordinatorMixin: {mapping_data}")
            
            # Verify it was set correctly
            retrieved_data = self.get_current_mapping(self.request)
            logger.info(f"OOB_UPDATES: Retrieved data verification: {retrieved_data}")
        
        # SIMPLIFIED: Don't render navbar controls yet - just update session
        # The issue might be that template rendering is triggering workspace operations
        logger.info(f"OOB_UPDATES: Skipping navbar update to isolate issue - just updating session state")
        
        # Return empty OOB response for now
        return self.build_oob_response("", {})
    
    def _render_navbar_controls(self, organization_id, current_mapping_id=None, current_mapping_name=None, 
                               current_mapping_updated=None, current_mapping_status=None):
        """Render navbar controls with current mapping context"""
        try:
            logger.info(f"🎯 RENDER_NAVBAR: Starting navbar render - org={organization_id}, mapping_id={current_mapping_id}")
            logger.info(f"🎯 RENDER_NAVBAR: Input params - name='{current_mapping_name}', updated='{current_mapping_updated}', status='{current_mapping_status}'")
            
            # Use provided updated timestamp and status, or get from database
            if current_mapping_id and (current_mapping_updated is None or current_mapping_status is None):
                logger.info(f"🎯 RENDER_NAVBAR: Missing data, querying database for mapping {current_mapping_id}")
                try:
                    from arkumu.metadata.models.mappings import Mapping
                    mapping_obj = Mapping.objects.get(id=current_mapping_id)
                    if current_mapping_updated is None:
                        current_mapping_updated = mapping_obj.updated_at.strftime('%b %d, %Y at %H:%M')
                        logger.info(f"🎯 RENDER_NAVBAR: Got updated_at from DB: {current_mapping_updated}")
                    if current_mapping_status is None:
                        current_mapping_status = mapping_obj.validation_status
                        logger.info(f"🎯 RENDER_NAVBAR: Got status from DB: {current_mapping_status}")
                except Mapping.DoesNotExist:
                    logger.warning(f"🎯 RENDER_NAVBAR: Mapping {current_mapping_id} not found in database")
                    current_mapping_updated = "Unknown"
                    current_mapping_status = "draft"
            
            context = {
                'organization_id': organization_id,
                'csrf_token': get_token(self.request),
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
                'current_mapping_status': current_mapping_status,
                'current_mapping_updated': current_mapping_updated,
            }
            
            logger.info(f"🎯 RENDER_NAVBAR: Final context: {context}")
            logger.info(f"🎯 RENDER_NAVBAR: DETAILED CONTEXT VALUES:")
            logger.info(f"🎯   - current_mapping_id: '{current_mapping_id}' (type: {type(current_mapping_id)}, bool: {bool(current_mapping_id)})")
            logger.info(f"🎯   - current_mapping_name: '{current_mapping_name}' (type: {type(current_mapping_name)}, bool: {bool(current_mapping_name)})")
            logger.info(f"🎯   - current_mapping_updated: '{current_mapping_updated}' (type: {type(current_mapping_updated)}, bool: {bool(current_mapping_updated)})")
            logger.info(f"🎯   - current_mapping_status: '{current_mapping_status}' (type: {type(current_mapping_status)}, bool: {bool(current_mapping_status)})")
            logger.info(f"🎯   - organization_id: '{organization_id}' (type: {type(organization_id)}, bool: {bool(organization_id)})")
            logger.info(f"🎯 RENDER_NAVBAR: About to render template 'csv_mapping/partials/navbar_mapping_controls.html'")
            
            rendered_html = render_to_string(
                'csv_mapping/partials/navbar_mapping_controls.html',
                context,
                request=self.request
            )
            
            logger.info(f"🎯 RENDER_NAVBAR: Template rendered successfully ({len(rendered_html)} chars)")
            logger.info(f"🎯 RENDER_NAVBAR: Rendered HTML preview: {rendered_html[:200]}...")
            
            return rendered_html
            
        except Exception as e:
            logger.error(f"🔴 RENDER_NAVBAR: Error rendering navbar controls: {str(e)}", exc_info=True)
            return '<div class="alert alert-error">Failed to render navbar controls</div>'
    

    
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
        <div class="alert alert-error alert-sm relative">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>{error_msg}</span>
            </div>
            {error_details}
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