"""
CSV Mapping Core Editor Views

This module contains the main CSV mapping editor view that serves as the entry point
for the CSV mapping interface. This is the primary view that orchestrates the entire
mapping workflow.

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
from django.shortcuts import render
from django.views import View

from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin
from arkumu.metadata.views.csv_mapping.mixins.import_strategy import ImportStrategyMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class CSVMappingEditorView(
    OrganizationMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    ImportStrategyMixin, 
    View
):
    """
    Main CSV mapping editor view using coordinator-based architecture.
    
    REFACTORED FROM: csv_mapping_editor_view function
    ARCHITECTURE: Uses coordinator mixin for proper dataset-column relationships:
    - OrganizationMixin: Organization discovery and management
    - CSVMappingCoordinatorMixin: Coordinates CSV data + workspace with dataset-column relationships
    - CSVMappingTemplateHelperMixin: Reduces template rendering duplication
    - ImportStrategyMixin: Import configuration and strategy management
    
    The coordinator mixin inherits from CSVDataMixin and MappingWorkspaceMixin, 
    providing all their functionality plus relationship management.
    """
    
    template_name = 'csv_mapping/main_editor.html'
    
    def get(self, request):
        """Handle GET requests for the CSV mapping editor."""
        try:
            logger.info(f"🚀 CSV_MAPPING_EDITOR: CSV mapping editor called! 🚀")
            logger.info(f"CSV_MAPPING_EDITOR: Method={request.method}, GET params={dict(request.GET)}")
            
            # Get organization context using OrganizationMixin
            org_context = self.get_organization_context(request)
            organization_id = org_context['organization_id']
            
            # Handle case where no valid organization is provided
            if not org_context['organization_exists']:
                if not organization_id or organization_id == 'default-org':
                    error_msg = 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL (e.g., ?organization=rsh)'
                else:
                    available_orgs = ", ".join([org["id"] for org in org_context['organizations']])
                    error_msg = f'Organization "{organization_id}" not found in S3. Available organizations: {available_orgs}'
                
                context = {
                    **org_context,
                    'sources': [],
                    'selected_source': '',
                    'error': error_msg,
                    'show_organization_help': True
                }
                return render(request, self.template_name, context)
            
            # Discover CSV datasets using CSVDataMixin
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            logger.info(f"CSV_MAPPING_EDITOR: Found {len(csv_datasets)} CSV datasets")
            
            # Get selected datasets and workspace columns using mixins
            selected_datasets, selected_datasets_with_details = self.get_selected_datasets_with_details(
                request, organization_id, csv_datasets
            )
            selected_columns = self.get_workspace_columns(request, organization_id)
            
            # Get import strategy using ImportStrategyMixin
            import_strategy = self.get_import_strategy(request, organization_id)
            import_strategy_summary = self.get_import_strategy_summary(request, organization_id)
            
            # Get enhanced workspace summary using coordinator
            workspace_summary = self.get_workspace_summary(request, organization_id)
            
            # Build complete context
            context = {
                **org_context,
                'datasets': csv_datasets,  # For template compatibility
                'csv_datasets': csv_datasets,
                'selected_datasets': selected_datasets,
                'selected_datasets_with_details': selected_datasets_with_details,
                'selected_columns': selected_columns,
                'import_strategy': import_strategy,
                'import_strategy_summary': import_strategy_summary,
                'workspace_summary': workspace_summary,
                'csrf_token': request.META.get('CSRF_COOKIE'),
            }
            
            # Handle HTMX requests - return just the partial content
            if request.headers.get('HX-Request'):
                # Check if this is a tab request
                tab = request.GET.get('tab')
                if tab == 'workspace':
                    # Return just the workspace content for tab switching using template helper
                    workspace_context = {
                        'datasets_with_columns': self._prepare_datasets_with_columns(selected_columns),
                        'organization_id': organization_id,
                        'csrf_token': request.META.get('CSRF_COOKIE'),
                    }
                    return render(request, 'csv_mapping/partials/selected_columns_workspace.html', workspace_context)
                else:
                    # Return main content for other HTMX requests
                    return render(request, 'csv_mapping/partials/main_content.html', context)
            else:
                return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"CSV_MAPPING_EDITOR: Error loading editor: {e}", exc_info=True)
            context = {
                'organizations': [],
                'error': f'Error loading CSV mapping editor: {str(e)}'
            }
            return render(request, self.template_name, context)


# ==============================================================================
# Function-based view wrapper for URL compatibility
# ==============================================================================

def csv_mapping_editor_view(request):
    """
    Function-based wrapper for the class-based CSVMappingEditorView.
    Maintains compatibility with existing URL patterns.
    """
    view = CSVMappingEditorView()
    return view.get(request) 