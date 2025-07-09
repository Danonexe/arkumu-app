"""
CSV Mapping Core Editor Views

This module contains the main CSV mapping editor view that serves as the entry point
for the CSV mapping interface. This is the primary view that orchestrates the entire
mapping workflow.

ARCHITECTURE: Uses coordinator-based architecture with template helpers to minimize duplication.
"""

import logging
import json
from django.shortcuts import render
from django.views import View
from django.http import JsonResponse, HttpResponse
from arkumu.users.mixins import GeneralLoginRequiredMixin, general_login_required

from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.import_strategy import ImportStrategyMixin
from arkumu.metadata.views.csv_mapping.mixins.template_helpers import CSVMappingTemplateHelperMixin

logger = logging.getLogger(__name__)


class CSVMappingEditorView(GeneralLoginRequiredMixin, 
    CSVMappingCoordinatorMixin, 
    CSVMappingTemplateHelperMixin,
    ImportStrategyMixin, 
    View):
    """
    Main CSV mapping editor view using coordinator-based architecture.
    
    REFACTORED FROM: csv_mapping_editor_view function
    ARCHITECTURE: Uses coordinator mixin for proper dataset-column relationships:
    - CSVMappingCoordinatorMixin: Coordinates CSV data + workspace with dataset-column relationships
      (inherits from BaseCoordinatorMixin for organization management)
    - CSVMappingTemplateHelperMixin: Reduces template rendering duplication
    - ImportStrategyMixin: Import configuration and strategy management
    
    The coordinator mixin inherits from BaseCoordinatorMixin, CSVDataMixin and MappingWorkspaceMixin, 
    providing all their functionality plus relationship management.
    """
    
    template_name = 'csv_mapping/main_editor.html'
    
    def get(self, request):
        """Handle GET requests for the CSV mapping editor."""
        try:
            logger.info(f"🚀 CSV_MAPPING_EDITOR: CSV mapping editor called! 🚀")
            logger.info(f"CSV_MAPPING_EDITOR: Method={request.method}, GET params={dict(request.GET)}")
            
            # Get organization context using BaseCoordinatorMixin
            logger.info(f"🔍 CORE_EDITOR: Getting organization context...")
            logger.info(f"🔍 CORE_EDITOR: URL parameters: {dict(request.GET)}")
            logger.info(f"🔍 CORE_EDITOR: Session keys: {list(request.session.keys())}")
            logger.info(f"🔍 CORE_EDITOR: Session current_organization: {request.session.get('current_organization')}")
            
            # Handle organization parameter from URL - set in session if provided
            organization_param = request.GET.get('organization')
            if organization_param:
                org_data = self.set_current_organization(request, organization_param)
                logger.info(f"🔍 CORE_EDITOR: Set organization from URL param: {org_data}")
            
            # Get current organization from session (works for both URL param and navigation)
            current_org = self.get_current_organization(request)
            logger.info(f"🔍 CORE_EDITOR: Current organization from session: {current_org}")
            
            if not current_org:
                # No organization selected - still render template but with no data
                # Get all organizations for dropdown
                from arkumu.users.models import Organization
                organizations = Organization.objects.all().order_by('name')
                organizations_list = [
                    {
                        'id': org.code,  # Use code for compatibility with templates
                        'name': org.name,
                        'status': 'active'  # Template expects status
                    }
                    for org in organizations
                ]
                
                context = {
                    **self.get_base_template_context(request),
                    'organization_id': None,
                    'organization_code': None,
                    'organization_name': None,
                    'organization_numeric_id': None,
                    'organizations': organizations_list,
                    'datasets': [],
                    'csv_datasets': [],
                    'selected_datasets': [],
                    'selected_datasets_with_details': [],
                    'selected_columns': [],
                    'import_strategy': {},
                    'import_strategy_summary': {},
                    'workspace_summary': {},
                    'current_mapping_id': None,
                    'current_mapping_name': None,
                    'current_mapping_description': None,
                    'current_mapping_updated': None,
                    'current_mapping_status': None,
                }
                return render(request, self.template_name, context)
            
            # Use organization code for dataset discovery (maintains compatibility)
            organization_id = current_org['code']
            
            logger.info(f"🔍 CORE_EDITOR: Current organization: {current_org}")
            logger.info(f"🔍 CORE_EDITOR: Organization ID (code): {organization_id}")
            
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
            
            # Get current mapping info using BaseCoordinatorMixin (proper session key)
            current_mapping_id = None
            current_mapping_name = None
            current_mapping_description = None
            current_mapping_updated = None
            current_mapping_status = None
            
            # Check if there's a loaded mapping using the shared session key
            current_mapping = self.get_current_mapping(request)
            logger.info(f"🔍 CORE_EDITOR: Checking for current mapping using BaseCoordinatorMixin")
            logger.info(f"🔍 CORE_EDITOR: Session keys: {list(request.session.keys())}")
            
            if current_mapping:
                current_mapping_id = current_mapping.get('id')
                current_mapping_name = current_mapping.get('name')
                current_mapping_description = current_mapping.get('description', '')
                
                # Get actual mapping from database for real updated time
                if current_mapping_id:
                    from arkumu.metadata.models.mappings import Mapping
                    try:
                        mapping_obj = Mapping.objects.get(id=current_mapping_id)
                        current_mapping_updated = mapping_obj.updated_at.strftime('%Y-%m-%d %H:%M')
                        current_mapping_status = mapping_obj.validation_status
                        
                        # Restore the full mapping state (workspace columns, FK relationships)
                        logger.info(f"🔄 CORE_EDITOR: Restoring mapping state for {current_mapping_name}")
                        self.deserialize_mapping_state(
                            request, 
                            organization_id, 
                            mapping_obj.mapping_config,
                            mapping_id=current_mapping_id,
                            mapping_name=current_mapping_name
                        )
                        
                        # Update coordinator context after restoration - refresh the data
                        # Need to get csv_datasets first for other methods
                        csv_datasets = self.get_csv_datasets_for_organization(organization_id)
                        selected_datasets, selected_datasets_with_details = self.get_selected_datasets_with_details(
                            request, organization_id, csv_datasets
                        )
                        selected_columns = self.get_workspace_columns(request, organization_id)
                        import_strategy = self.get_import_strategy(request, organization_id)
                        import_strategy_summary = self.get_import_strategy_summary(request, organization_id)
                        workspace_summary = self.get_workspace_summary(request, organization_id)
                        
                    except Mapping.DoesNotExist:
                        logger.error(f"🔴 CORE_EDITOR: Mapping {current_mapping_id} not found in database")
                        current_mapping_updated = "Unknown"
                        current_mapping_status = "draft"
                
                logger.info(f"🟢 CORE_EDITOR: Found loaded mapping: {current_mapping_name} (ID: {current_mapping_id}) updated: {current_mapping_updated}")
            else:
                logger.info(f"🟡 CORE_EDITOR: No loaded mapping found in session")
            
            # Get all organizations for dropdown
            from arkumu.users.models import Organization
            organizations = Organization.objects.all().order_by('name')
            organizations_list = [
                {
                    'id': org.code,  # Use code for compatibility with templates
                    'name': org.name,
                    'status': 'active'  # Template expects status
                }
                for org in organizations
            ]
            
            # Build complete context using BaseCoordinatorMixin
            context = {
                **self.get_base_template_context(request),
                'organization_id': organization_id,  # Use organization code for compatibility
                'organization_code': current_org['code'],
                'organization_name': current_org['name'],
                'organization_numeric_id': current_org['id'],
                'organizations': organizations_list,
                'datasets': csv_datasets,  # For template compatibility
                'csv_datasets': csv_datasets,
                'selected_datasets': selected_datasets,
                'selected_datasets_with_details': selected_datasets_with_details,
                'selected_columns': selected_columns,
                'import_strategy': import_strategy,
                'import_strategy_summary': import_strategy_summary,
                'workspace_summary': workspace_summary,
                'current_mapping_id': current_mapping_id,
                'current_mapping_name': current_mapping_name,
                'current_mapping_description': current_mapping_description,
                'current_mapping_updated': current_mapping_updated,
                'current_mapping_status': current_mapping_status,
                'error': None,  # Clear any error state on successful load
                'success': True,  # Indicate successful load
            }
            
            # Handle HTMX requests - return just the partial content
            if request.headers.get('HX-Request'):
                logger.info(f"🔍 CORE_EDITOR: HTMX request detected")
                logger.info(f"🔍 CORE_EDITOR: HX-Target: {request.headers.get('HX-Target')}")
                logger.info(f"🔍 CORE_EDITOR: HX-Trigger: {request.headers.get('HX-Trigger')}")
                
                # Check if this is a tab request
                tab = request.GET.get('tab')
                if tab == 'workspace':
                    # Use template helper to render workspace content properly
                    workspace_content = self.render_workspace_template(request, organization_id)
                    
                    # Wrap in the workspace-content div that HTMX targets expect
                    wrapped_content = f'<div id="workspace-content" class="h-full overflow-y-auto flex-1 flex flex-col bg-base-50/30 rounded-lg border border-base-300/50">{workspace_content}</div>'
                    from django.http import HttpResponse
                    return HttpResponse(wrapped_content)
                else:
                    logger.info(f"🔍 CORE_EDITOR: Handling main content HTMX request")
                    # Return main content for other HTMX requests + inject navbar controls
                    from django.template.loader import render_to_string
                    from django.http import HttpResponse
                    
                    # Render main content
                    main_content = render(request, 'csv_mapping/partials/main_content.html', context).content.decode()
                    logger.info(f"🔍 CORE_EDITOR: Main content length: {len(main_content)} chars")
                    
                    # Render navbar controls
                    navbar_context = {
                        'organization_id': organization_id,
                        'current_mapping_id': current_mapping_id,
                        'current_mapping_name': current_mapping_name,
                        'current_mapping_updated': current_mapping_updated,
                        'current_mapping_status': current_mapping_status,
                        'csrf_token': context['csrf_token'],
                    }
                    navbar_controls = render_to_string(
                        'csv_mapping/partials/navbar_mapping_controls.html',
                        navbar_context,
                        request=request
                    )
                    
                    # Use template helper to build proper OOB response
                    oob_updates = {
                        'navbar-mapping-controls': navbar_controls
                    }
                    response_html = self.build_oob_response(main_content, oob_updates)
                    
                    return HttpResponse(response_html)
            else:
                return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"CSV_MAPPING_EDITOR: Error loading editor: {e}", exc_info=True)
            context = {
                **self.get_base_template_context(request),
                'organization_id': None,
                'organization_code': None,
                'organization_name': None,
                'organization_numeric_id': None,
                'organizations': [],
                'datasets': [],
                'csv_datasets': [],
                'selected_datasets': [],
                'selected_datasets_with_details': [],
                'selected_columns': [],
                'import_strategy': {},
                'import_strategy_summary': {},
                'workspace_summary': {},
                'current_mapping_id': None,
                'current_mapping_name': None,
                'current_mapping_description': None,
                'current_mapping_updated': None,
                'current_mapping_status': None,
                'error': f'Error loading CSV mapping editor: {str(e)}'
            }
            
            # Handle HTMX requests differently to avoid template duplication
            if request.headers.get('HX-Request'):
                logger.error(f"🔍 CORE_EDITOR: Handling error for HTMX request")
                # Return just the main content partial for HTMX requests
                from django.template.loader import render_to_string
                from django.http import HttpResponse
                
                # Render error state in main content
                main_content = render(request, 'csv_mapping/partials/main_content.html', context).content.decode()
                
                # Clear navbar controls for error state
                navbar_controls = render_to_string(
                    'csv_mapping/partials/navbar_mapping_controls.html',
                    {'organization_id': None, 'csrf_token': context['csrf_token']},
                    request=request
                )
                
                # Use template helper to build proper OOB response
                oob_updates = {
                    'navbar-mapping-controls': navbar_controls
                }
                response_html = self.build_oob_response(main_content, oob_updates)
                
                return HttpResponse(response_html)
            else:
                return render(request, self.template_name, context)


# ==============================================================================
# Function-based view wrapper for URL compatibility
# ==============================================================================

@general_login_required
def csv_mapping_editor_view(request):
    """
    Function-based wrapper for the class-based CSVMappingEditorView.
    Maintains compatibility with existing URL patterns.
    """
    view = CSVMappingEditorView()
    return view.get(request)


class MappingGraphDataView(GeneralLoginRequiredMixin, CSVMappingCoordinatorMixin, View):
    """
    Provides graph visualization data for CSV mapping relationships.
    
    Returns JSON data in Cytoscape.js format containing:
    - Dataset nodes
    - Column nodes 
    - Relationship edges (FK, anchors, junction tables)
    """
    
    def get(self, request):
        """Generate graph data for current mapping configuration."""
        try:
            # Get current organization using BaseCoordinatorMixin
            current_org = self.get_current_organization(request)
            if not current_org:
                if request.headers.get('HX-Request'):
                    context = {
                        'graph_data': {'nodes': [], 'edges': []},
                        'mapping_name': None,
                        'mapping_description': None,
                        'error': 'No organization selected'
                    }
                    return render(request, 'csv_mapping/partials/mapping_graph_content.html', context)
                else:
                    return JsonResponse({'error': 'No organization selected'}, status=400)
            
            # Use organization code for compatibility
            organization_id = current_org['code']
            
            # Check if specific mapping ID is requested
            mapping_id = request.GET.get('mapping_id')
            
            if mapping_id:
                # Load mapping from database
                from arkumu.metadata.models.mappings import Mapping
                try:
                    mapping = Mapping.objects.get(id=mapping_id)
                    selected_columns = mapping.mapping_config.get('workspace_columns', {})
                    
                    # Safely handle logging to avoid errors with mock objects in tests
                    try:
                        logger.info(f"MAPPING_GRAPH: Loaded mapping {mapping_id} with {len(selected_columns)} columns")
                        logger.info(f"MAPPING_GRAPH: Mapping config keys: {list(mapping.mapping_config.keys())}")
                        if selected_columns:
                            logger.info(f"MAPPING_GRAPH: Selected columns sample: {dict(list(selected_columns.items())[:3])}")
                    except (TypeError, AttributeError):
                        # Handle mock objects or invalid data gracefully
                        logger.info(f"MAPPING_GRAPH: Loaded mapping {mapping_id} with workspace columns")
                except Mapping.DoesNotExist:
                    if request.headers.get('HX-Request'):
                        context = {
                            'graph_data': {'nodes': [], 'edges': []},
                            'mapping_name': None,
                            'mapping_description': None,
                            'error': f'Mapping {mapping_id} not found'
                        }
                        return render(request, 'csv_mapping/partials/mapping_graph_content.html', context)
                    else:
                        return JsonResponse({'error': 'Mapping not found'}, status=404)
            else:
                # Get workspace columns from current session
                selected_columns = self.get_workspace_columns(request, organization_id)
                logger.info(f"MAPPING_GRAPH: Using current workspace with {len(selected_columns)} columns")
            
            # Generate graph data
            graph_data = self._generate_cytoscape_data(selected_columns, organization_id)
            
            # Return as HTMX template or JSON based on request
            if request.headers.get('HX-Request'):
                # Prepare context for HTMX template
                # Serialize graph_data to JSON string for JavaScript consumption
                import json
                context = {
                    'graph_data_json': json.dumps(graph_data),
                    'graph_data': graph_data,  # Keep original for debugging
                    'mapping_name': None,
                    'mapping_description': None,
                    'error': None
                }
                
                # Add mapping info if available
                if mapping_id:
                    try:
                        mapping = Mapping.objects.get(id=mapping_id)
                        context['mapping_name'] = mapping.name
                        context['mapping_description'] = mapping.description
                    except Mapping.DoesNotExist:
                        pass
                
                return render(request, 'csv_mapping/partials/mapping_graph_modal_open.html', context)
            else:
                return JsonResponse(graph_data)
                
        except Exception as e:
            logger.error(f"MAPPING_GRAPH: Error generating graph data: {e}", exc_info=True)
            
            # Return appropriate error response based on request type
            if request.headers.get('HX-Request'):
                context = {
                    'graph_data': {'nodes': [], 'edges': []},
                    'mapping_name': None,
                    'mapping_description': None,
                    'error': str(e)
                }
                return render(request, 'csv_mapping/partials/mapping_graph_content.html', context)
            else:
                return JsonResponse({'error': str(e)}, status=500)
    
    def _generate_cytoscape_data(self, selected_columns, organization_id):
        """Convert workspace columns into Cytoscape.js graph format."""
        try:
            logger.info(f"MAPPING_GRAPH: _generate_cytoscape_data called with {len(selected_columns)} columns")
        except (TypeError, AttributeError):
            logger.info(f"MAPPING_GRAPH: _generate_cytoscape_data called with workspace columns")
        nodes = []
        edges = []
        
        # Track datasets and columns
        datasets = {}
        columns_by_dataset = {}
        
        # Process workspace columns
        processed_count = 0
        for col_id, col_data in selected_columns.items():
            dataset_name = col_data.get('dataset', '')
            column_name = col_data.get('name', '')
            processed_count += 1
            
            if processed_count <= 3:  # Log first 3 for debugging
                logger.info(f"MAPPING_GRAPH: Processing column {processed_count}: {col_id} -> {dataset_name}.{column_name}")
            
            # Create dataset node if not exists
            if dataset_name not in datasets:
                datasets[dataset_name] = {
                    'id': f"dataset_{dataset_name}",
                    'label': f"{dataset_name}.csv",
                    'type': 'dataset',
                    'column_count': 0
                }
                columns_by_dataset[dataset_name] = []
            
            # Add column to dataset
            datasets[dataset_name]['column_count'] += 1
            columns_by_dataset[dataset_name].append(col_data)
            
            # Create column node
            column_node = {
                'id': col_id,
                'label': column_name,
                'type': 'column',
                'dataset': dataset_name,
                'is_anchor': col_data.get('is_anchor', False),
                'is_fk': col_data.get('is_fk', False),
                'is_multi_value': col_data.get('is_multi_value', False),
                'is_relationship_context': col_data.get('is_relationship_context', False),
                'is_external_ontology': col_data.get('is_external_ontology', False)
            }
            nodes.append(column_node)
            
            # Create edge from dataset to column
            edges.append({
                'id': f"edge_{dataset_name}_to_{col_id}",
                'source': f"dataset_{dataset_name}",
                'target': col_id,
                'type': 'contains'
            })
            
            # Create FK relationship edges
            if col_data.get('is_fk') and col_data.get('fk_config'):
                fk_config = col_data['fk_config']
                target_dataset = fk_config.get('target_dataset')
                target_column = fk_config.get('target_column')
                direction = fk_config.get('direction', 'outbound')
                
                if target_dataset and target_column:
                    target_col_id = f"{organization_id}::{target_dataset}::{target_column}"
                    
                    edges.append({
                        'id': f"fk_{col_id}_to_{target_col_id}",
                        'source': col_id if direction == 'outbound' else target_col_id,
                        'target': target_col_id if direction == 'outbound' else col_id,
                        'type': 'foreign_key',
                        'direction': direction
                    })
            
            # Create relationship context edges (junction tables)
            if col_data.get('is_relationship_context') and col_data.get('relationship_context'):
                rel_context = col_data['relationship_context']
                primary_fk = rel_context.get('primary_fk_dataset')
                secondary_fk = rel_context.get('secondary_fk_dataset')
                predicate = rel_context.get('context_predicate', 'related_to')
                
                if primary_fk and secondary_fk:
                    edges.append({
                        'id': f"junction_{col_id}_{primary_fk}_{secondary_fk}",
                        'source': f"dataset_{primary_fk}",
                        'target': f"dataset_{secondary_fk}",
                        'type': 'junction_relationship',
                        'predicate': predicate,
                        'junction_column': col_id
                    })
        
        # Add dataset nodes
        for dataset_data in datasets.values():
            nodes.append(dataset_data)
        
        logger.info(f"MAPPING_GRAPH: Generated {len(nodes)} nodes and {len(edges)} edges")
        logger.info(f"MAPPING_GRAPH: Datasets created: {list(datasets.keys())}")
        
        return {
            'nodes': nodes,
            'edges': edges
        }


@general_login_required
def mapping_graph_data_view(request):
    """Function-based wrapper for MappingGraphDataView."""
    view = MappingGraphDataView()
    return view.get(request)


class MappingOverviewDataView(GeneralLoginRequiredMixin, CSVMappingCoordinatorMixin, View):
    """
    Provides text-based overview of CSV mapping configuration.
    
    Returns a detailed text summary showing:
    - Datasets with their columns
    - Anchor columns
    - Foreign key relationships
    - External ontology connections
    - Multi-value columns
    - Relationship contexts (junction tables)
    """
    
    def get(self, request):
        """Generate text overview for current mapping configuration."""
        try:
            # Get current organization using BaseCoordinatorMixin
            current_org = self.get_current_organization(request)
            if not current_org:
                if request.headers.get('HX-Request'):
                    context = {
                        'overview_data': None,
                        'mapping_name': None,
                        'mapping_description': None,
                        'error': 'No organization selected'
                    }
                    return render(request, 'csv_mapping/partials/mapping_overview_content.html', context)
                else:
                    return JsonResponse({'error': 'No organization selected'}, status=400)
            
            # Use organization code for compatibility
            organization_id = current_org['code']
            
            # Check if specific mapping ID is requested
            mapping_id = request.GET.get('mapping_id')
            
            if mapping_id:
                # Load mapping from database
                from arkumu.metadata.models.mappings import Mapping
                try:
                    mapping = Mapping.objects.get(id=mapping_id)
                    selected_columns = mapping.mapping_config.get('workspace_columns', {})
                    logger.info(f"MAPPING_OVERVIEW: Loaded mapping {mapping_id} with {len(selected_columns)} columns")
                except Mapping.DoesNotExist:
                    if request.headers.get('HX-Request'):
                        context = {
                            'overview_data': None,
                            'mapping_name': None,
                            'mapping_description': None,
                            'error': f'Mapping {mapping_id} not found'
                        }
                        return render(request, 'csv_mapping/partials/mapping_overview_content.html', context)
                    else:
                        return JsonResponse({'error': 'Mapping not found'}, status=404)
            else:
                # Get workspace columns from current session
                selected_columns = self.get_workspace_columns(request, organization_id)
                logger.info(f"MAPPING_OVERVIEW: Using current workspace with {len(selected_columns)} columns")
            
            # Generate overview data
            overview_data = self._generate_overview_data(selected_columns, organization_id)
            
            # Return as HTMX template or JSON based on request
            if request.headers.get('HX-Request'):
                context = {
                    'overview_data': overview_data,
                    'mapping_name': None,
                    'mapping_description': None,
                    'error': None
                }
                
                # Add mapping info if available
                if mapping_id:
                    try:
                        mapping = Mapping.objects.get(id=mapping_id)
                        context['mapping_name'] = mapping.name
                        context['mapping_description'] = mapping.description
                    except Mapping.DoesNotExist:
                        pass
                
                return render(request, 'csv_mapping/partials/mapping_overview_modal_open.html', context)
            else:
                return JsonResponse(overview_data)
                
        except Exception as e:
            logger.error(f"MAPPING_OVERVIEW: Error generating overview data: {e}", exc_info=True)
            
            # Return appropriate error response based on request type
            if request.headers.get('HX-Request'):
                context = {
                    'overview_data': None,
                    'mapping_name': None,
                    'mapping_description': None,
                    'error': str(e)
                }
                return render(request, 'csv_mapping/partials/mapping_overview_content.html', context)
            else:
                return JsonResponse({'error': str(e)}, status=500)
    
    def _generate_overview_data(self, selected_columns, organization_id):
        """Convert workspace columns into structured overview data."""
        logger.info(f"MAPPING_OVERVIEW: _generate_overview_data called with {len(selected_columns)} columns")
        
        # Group columns by dataset
        datasets = {}
        for col_id, col_data in selected_columns.items():
            dataset_name = col_data.get('dataset', '')
            
            if dataset_name not in datasets:
                datasets[dataset_name] = {
                    'name': dataset_name,
                    'columns': [],
                    'anchor_columns': [],
                    'foreign_keys': [],
                    'external_ontologies': [],
                    'multi_value_columns': [],
                    'relationship_contexts': []
                }
            
            column_info = {
                'name': col_data.get('name', ''),
                'id': col_id,
                'arkumu_type': col_data.get('arkumu_type', 'literal'),
                'is_anchor': col_data.get('is_anchor', False),
                'is_fk': col_data.get('is_fk', False),
                'is_multi_value': col_data.get('is_multi_value', False),
                'is_external_ontology': col_data.get('is_external_ontology', False),
                'is_relationship_context': col_data.get('is_relationship_context', False),
                'predicate_uri': col_data.get('predicate_uri', ''),
                'fk_config': col_data.get('fk_config', {}),
                'external_ontology': col_data.get('external_ontology', {}),
                'relationship_context': col_data.get('relationship_context', {})
            }
            
            datasets[dataset_name]['columns'].append(column_info)
            
            # Categorize special columns
            if column_info['is_anchor']:
                datasets[dataset_name]['anchor_columns'].append(column_info)
            
            if column_info['is_fk']:
                datasets[dataset_name]['foreign_keys'].append(column_info)
            
            if column_info['is_external_ontology']:
                datasets[dataset_name]['external_ontologies'].append(column_info)
            
            if column_info['is_multi_value']:
                datasets[dataset_name]['multi_value_columns'].append(column_info)
            
            if column_info['is_relationship_context']:
                datasets[dataset_name]['relationship_contexts'].append(column_info)
        
        # Sort datasets by name
        sorted_datasets = dict(sorted(datasets.items()))
        
        # Generate summary statistics
        total_datasets = len(sorted_datasets)
        total_columns = sum(len(ds['columns']) for ds in sorted_datasets.values())
        total_anchors = sum(len(ds['anchor_columns']) for ds in sorted_datasets.values())
        total_fks = sum(len(ds['foreign_keys']) for ds in sorted_datasets.values())
        total_external_ontologies = sum(len(ds['external_ontologies']) for ds in sorted_datasets.values())
        total_multi_value = sum(len(ds['multi_value_columns']) for ds in sorted_datasets.values())
        total_relationship_contexts = sum(len(ds['relationship_contexts']) for ds in sorted_datasets.values())
        
        logger.info(f"MAPPING_OVERVIEW: Generated overview for {total_datasets} datasets, {total_columns} columns")
        
        return {
            'datasets': sorted_datasets,
            'summary': {
                'total_datasets': total_datasets,
                'total_columns': total_columns,
                'total_anchors': total_anchors,
                'total_foreign_keys': total_fks,
                'total_external_ontologies': total_external_ontologies,
                'total_multi_value': total_multi_value,
                'total_relationship_contexts': total_relationship_contexts
            }
        }


@general_login_required
def mapping_overview_data_view(request):
    """Function-based wrapper for MappingOverviewDataView."""
    view = MappingOverviewDataView()
    return view.get(request) 