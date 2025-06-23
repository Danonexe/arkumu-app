"""
CSV Mapping Utility Views

This module contains utility views for the CSV mapping interface:
- Clear operations (datasets, workspace, all mapping state)
- JSON export and configuration serialization
- Import strategy management

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
import json
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.metadata.views.csv_mapping.mixins.import_strategy import ImportStrategyMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


# ==============================================================================
# Clear Operations (Separated by Responsibility)
# ==============================================================================

class ClearSelectedDatasetsView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Clear ONLY selected datasets (preserve workspace columns).
    
    SPECIFIC PURPOSE: This is for the dataset badges "Clear Selected" button.
    It removes dataset selections but keeps all workspace columns and their configurations intact.
    """
    
    def post(self, request):
        """Handle POST requests for clearing only selected datasets."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for specific clear operation
            datasets_cleared, workspace_preserved = self.clear_selected_datasets_only(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            # Get context for response using coordinator
            context_data = self.get_clear_operation_context(request, organization_id)
            
            logger.info(f"CLEAR_DATASETS: Cleared {datasets_cleared} datasets, preserved {workspace_preserved} workspace columns")
            
            # CORRECTED: Only update selection interface (badges + table), NOT the workspace
            # The workspace is independent and should only be cleared by its own "Clear Workspace" button
            
            # Render dataset badges (now unselected)
            badges_html = self.render_dataset_badges_template(
                request, organization_id, 
                context_data['csv_datasets'], 
                context_data.get('selected_datasets', [])  # This will be empty after clear
            )
            
            # Render empty table content (no selected datasets to show)
            table_content_html = self.render_table_content_template(request, organization_id, [])
            
            # Build response using template helper (pure HTMX)
            oob_updates = {
                'dataset-badges': badges_html,
                'table-content': table_content_html
            }
            response = self.build_oob_response("", oob_updates)
            
            return HttpResponse(response)
            
        except Exception as e:
            logger.error(f"CLEAR_DATASETS: Error clearing selected datasets: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ClearWorkspaceColumnsView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Clear ONLY workspace columns (preserve selected datasets).
    
    SPECIFIC PURPOSE: This is for the workspace "Clear Workspace" button.
    It removes all workspace columns but keeps dataset selections intact.
    """
    
    def post(self, request):
        """Handle POST requests for clearing only workspace columns."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for specific clear operation
            columns_cleared, datasets_preserved = self.clear_workspace_columns_only(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            logger.info(f"CLEAR_WORKSPACE: Cleared {columns_cleared} workspace columns, preserved {datasets_preserved} selected datasets")
            
            # CORRECTED: Only update the workspace component, NOT the dataset selection interface
            # This preserves selected datasets and column selections in the browsing interface
            workspace_html = self.render_workspace_template(request, organization_id)
            
            # Build response with only workspace update
            oob_updates = {
                'workspace-content': workspace_html
            }
            response = self.build_oob_response("", oob_updates)
            
            return HttpResponse(response)
            
        except Exception as e:
            logger.error(f"CLEAR_WORKSPACE: Error clearing workspace columns: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ClearAllMappingStateView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    View
):
    """
    Clear ALL mapping state (datasets AND workspace columns).
    
    SPECIFIC PURPOSE: This is for a complete reset operation.
    It clears both dataset selections and workspace columns.
    """
    
    def post(self, request):
        """Handle POST requests for clearing all mapping state."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Use coordinator for complete reset operation
            datasets_cleared, columns_cleared, summary = self.reset_all_coordinator_state(request, organization_id)
            
            # Force session save
            request.session.modified = True
            
            logger.info(f"CLEAR_ALL: Complete reset - cleared {datasets_cleared} datasets, {columns_cleared} columns")
            
            # Use template helper for complete UI refresh (everything will be empty)
            response = self.build_standard_ui_refresh_response(request, organization_id)
            
            return HttpResponse(response)
            
        except Exception as e:
            logger.error(f"CLEAR_ALL: Error clearing all mapping state: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# Legacy view for backward compatibility (if needed)
class ClearAllDatasetsView(ClearSelectedDatasetsView):
    """
    Legacy view that now delegates to ClearSelectedDatasetsView.
    
    DEPRECATED: Use ClearSelectedDatasetsView, ClearWorkspaceColumnsView, or ClearAllMappingStateView instead.
    """
    pass


# ==============================================================================
# JSON Serialization Views
# ==============================================================================

class ExportMappingJSONView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Export current mapping configuration as JSON.
    
    Uses the coordinator's serialize_current_mapping_state method to provide
    a comprehensive JSON representation of the current mapping configuration.
    """
    
    def get(self, request):
        """Handle GET requests for exporting mapping JSON."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                return JsonResponse({
                    'error': 'Invalid organization',
                    'message': f'Organization "{organization_id}" not found'
                }, status=400)
            
            # Use coordinator to serialize current mapping state
            mapping_config = self.serialize_current_mapping_state(request, organization_id)
            
            # Add additional metadata
            mapping_config['export_timestamp'] = timezone.now().isoformat()
            mapping_config['exported_by'] = 'CSV Mapping Editor'
            
            # Get workspace summary for additional context
            workspace_summary = self.get_workspace_summary(request, organization_id)
            mapping_config['workspace_summary'] = workspace_summary
            
            # Add relationship context information
            relationship_contexts = {}
            workspace_columns = self.get_workspace_columns(request, organization_id)
            for col in workspace_columns:
                if col.get('is_relationship_context', False):
                    relationship_contexts[col.get('id')] = col.get('relationship_context', {})
            mapping_config['relationship_contexts'] = relationship_contexts
            
            # Return formatted JSON response
            return JsonResponse(mapping_config, json_dumps_params={'indent': 2})
            
        except Exception as e:
            logger.error(f"EXPORT_MAPPING_JSON: Error exporting mapping: {e}", exc_info=True)
            return JsonResponse({
                'error': 'Export failed',
                'message': str(e)
            }, status=500)


class GetMappingJSONViewView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Get JSON view partial template for HTMX tab switching.
    
    This view returns the JSON view partial template, following the HTMX pattern
    used throughout the CSV mapping interface.
    """
    
    def get(self, request):
        """Handle GET requests for JSON view partial."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                error_html = f'''
                <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                    <h3 class="text-lg font-semibold text-red-800 mb-2">Invalid Organization</h3>
                    <p class="text-red-700">Organization "{organization_id}" not found</p>
                </div>
                '''
                return HttpResponse(error_html)
            
            # Prepare context for the JSON view template
            context = {
                'organization_id': organization_id,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Return the JSON view partial template
            return render(request, 'csv_mapping/partials/json_view.html', context)
            
        except Exception as e:
            logger.error(f"GET_MAPPING_JSON_VIEW: Error loading JSON view: {e}", exc_info=True)
            error_html = f'''
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading JSON View</h3>
                <p class="text-red-700">{str(e)}</p>
            </div>
            '''
            return HttpResponse(error_html)


class GetMappingJSONContentView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    View
):
    """
    Get current mapping configuration as JSON content for display in the UI.
    
    This view returns formatted JSON content suitable for displaying in the
    JSON tab of the mapping workspace.
    """
    
    def get(self, request):
        """Handle GET requests for mapping JSON content."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Check if we have a valid organization
            org_context = self.get_organization_context(request)
            if not org_context['organization_exists']:
                error_json = {
                    'error': 'Invalid organization',
                    'message': f'Organization "{organization_id}" not found'
                }
                formatted_json = json.dumps(error_json, indent=2)
                return HttpResponse(f'<pre class="bg-gray-100 p-4 rounded text-sm overflow-auto max-h-96"><code>{formatted_json}</code></pre>')
            
            # Use coordinator to serialize current mapping state
            mapping_config = self.serialize_current_mapping_state(request, organization_id)
            
            # Add additional metadata for display
            mapping_config['export_timestamp'] = timezone.now().isoformat()
            mapping_config['exported_by'] = 'CSV Mapping Editor'
            
            # Get workspace summary for additional context
            workspace_summary = self.get_workspace_summary(request, organization_id)
            mapping_config['workspace_summary'] = workspace_summary
            
            # Format JSON with proper indentation
            formatted_json = json.dumps(mapping_config, indent=2, cls=DjangoJSONEncoder)
            
            # Return as HTML with proper formatting
            html_content = f'''
            <div class="bg-gray-50 border rounded-lg p-4">
                <div class="flex justify-between items-center mb-3">
                    <h3 class="text-lg font-semibold text-gray-800">Current Mapping Configuration</h3>
                    <div class="flex gap-2">
                        <button onclick="copyJsonToClipboard()" class="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
                            📋 Copy JSON
                        </button>
                        <a href="/metadata/csv-mapping/export-json/?organization={organization_id}" 
                           class="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700 no-underline">
                            💾 Download JSON
                        </a>
                    </div>
                </div>
                <div class="bg-white border rounded p-3 max-h-96 overflow-auto">
                    <pre id="json-content" class="text-sm text-gray-800 whitespace-pre-wrap"><code>{formatted_json}</code></pre>
                </div>
                <div class="mt-3 text-xs text-gray-600">
                    Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} | 
                    Datasets: {len(mapping_config.get('selected_datasets', []))} | 
                    Columns: {len(mapping_config.get('workspace_columns', {}))} |
                    FK Relations: {len(mapping_config.get('fk_relationships', {}))}
                </div>
            </div>
            '''
            
            return HttpResponse(html_content)
            
        except Exception as e:
            logger.error(f"GET_MAPPING_JSON_CONTENT: Error getting mapping JSON: {e}", exc_info=True)
            error_html = f'''
            <div class="bg-red-50 border border-red-200 rounded-lg p-4">
                <h3 class="text-lg font-semibold text-red-800 mb-2">Error Loading JSON</h3>
                <p class="text-red-700">{str(e)}</p>
            </div>
            '''
            return HttpResponse(error_html)


# ==============================================================================
# Import Strategy Management
# ==============================================================================

class UpdateImportStrategyView(
    OrganizationMixin, 
    ImportStrategyMixin, 
    View
):
    """
    Update import strategy configuration view using mixin-based architecture.
    
    READY TO USE: ImportStrategyMixin provides full functionality
    """
    
    def post(self, request):
        """Handle POST requests for import strategy updates."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Get strategy updates from POST data
            strategy_updates = {}
            for key in ['update_strategy', 'link_topology', 'multi_value_threshold', 'bulk_size']:
                if key in request.POST:
                    value = request.POST.get(key)
                    # Convert boolean strings
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    # Convert numeric strings
                    elif key in ['multi_value_threshold', 'bulk_size']:
                        try:
                            value = float(value) if key == 'multi_value_threshold' else int(value)
                        except ValueError:
                            pass
                    strategy_updates[key] = value
            
            # Validate and update strategy
            if strategy_updates:
                is_valid, errors = self.validate_import_strategy({**self.get_import_strategy(request, organization_id), **strategy_updates})
                if is_valid:
                    self.update_import_strategy(request, organization_id, strategy_updates)
                    return JsonResponse({'status': 'success', 'updated': strategy_updates})
                else:
                    return JsonResponse({'status': 'error', 'errors': errors}, status=400)
            
            return JsonResponse({'status': 'no_changes'})
            
        except Exception as e:
            logger.error(f"UPDATE_IMPORT_STRATEGY: Error updating strategy: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500) 