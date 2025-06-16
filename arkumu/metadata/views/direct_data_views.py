"""
Direct Data Views

Views that use S3DirectDataAnalyzer to provide fast table previews and analysis
directly from S3 source files, without requiring data to be imported into the database first.

This approach is more memory-efficient and faster than the traditional database-based approach.
"""

import logging
import json
import tempfile
import os
import re
from datetime import datetime
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string
from django.core.serializers.json import DjangoJSONEncoder

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.metadata.services.relationship_discovery.service import RelationshipDiscoveryService
from arkumu.metadata.models.mappings import Mapping, MappingType
from arkumu.metadata.services.mapping_executor import MappingExecutor

logger = logging.getLogger(__name__)


def get_organization_id_from_request(request):
    """Get the organization ID from the request (following the same pattern as other views)."""
    # Extract organization from GET or POST parameters, following the same pattern as other views
    organization = request.GET.get('organization') or request.POST.get('organization')
    
    # Handle both cases where organization might be passed
    if organization:
        return organization.strip()
    
    # For HTMX requests, try to extract organization from referrer URL
    if 'HX-Request' in request.headers:
        referrer = request.headers.get('Referer', '')
        if '?organization=' in referrer:
            # Extract organization from URL like "...?organization=rsh"
            try:
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(referrer)
                query_params = parse_qs(parsed_url.query)
                org_param = query_params.get('organization', [None])[0]
                if org_param:
                    return org_param.strip()
            except Exception as e:
                logger.warning(f"Could not extract organization from referrer URL: {e}")
    
    # Fallback: try to get from user if available (for future authentication integration)
    if hasattr(request, 'user') and hasattr(request.user, 'organization_id'):
        return getattr(request.user, 'organization_id', None)
    
    # Default fallback - you may want to raise an exception here instead
    return 'default-org'


def get_workspace_columns(request, organization_id):
    """
    Get workspace columns from session (single source of truth).
    No cache dependency - simple and consistent.
    """
    workspace_key = f"workspace_columns_{organization_id}"
    return request.session.get(workspace_key, [])


def update_workspace_columns(request, organization_id, columns):
    """
    Update workspace columns in session.
    Ensures session is marked as modified.
    """
    workspace_key = f"workspace_columns_{organization_id}"
    request.session[workspace_key] = columns
    request.session.modified = True
    logger.info(f"WORKSPACE: Updated workspace with {len(columns)} columns for org={organization_id}")


def clear_workspace_columns(request, organization_id):
    """
    Clear all workspace columns.
    """
    workspace_key = f"workspace_columns_{organization_id}"
    request.session[workspace_key] = []
    request.session.modified = True
    logger.info(f"WORKSPACE: Cleared workspace for org={organization_id}")


# Removed get_datasets_for_template() - datasets should come from main template context



def direct_split_table_graph_view(request):
    """
    Split view showing datasets directly from S3 source files with table previews and graph visualization.
    Uses S3DirectDataAnalyzer for efficient S3-based analysis.
    """
    try:
        # Log the incoming request details  
        logger.warning(f"🚀🚀🚀 DIRECT_SPLIT_VIEW CALLED - NEW CODE IS RUNNING! 🚀🚀🚀")
        logger.warning(f"DIRECT_SPLIT_VIEW: Method={request.method}, GET params={dict(request.GET)}")
        
        organization_id = get_organization_id_from_request(request)
        logger.info(f"DIRECT_SPLIT_VIEW: Extracted organization_id={organization_id}")
        
        # Discover available organizations from S3 buckets (like archivist dashboard)
        analyzer = S3DirectDataAnalyzer()
        
        # Cache the organization discovery to avoid checking all orgs every time
        cache_key = "available_organizations_s3"
        available_organizations = cache.get(cache_key)
        if available_organizations is None:
            logger.info(f"DIRECT_SPLIT_VIEW: Discovering available organizations (not cached)")
            available_organizations = _discover_available_organizations(analyzer)
            cache.set(cache_key, available_organizations, timeout=300)  # Cache for 5 minutes
        else:
            logger.info(f"DIRECT_SPLIT_VIEW: Using cached organization list")
        
        logger.info(f"DIRECT_SPLIT_VIEW: Found {len(available_organizations)} available organizations: {[org['id'] for org in available_organizations]}")
        
        # If no organization is provided, show helpful instructions with available orgs
        if not organization_id or organization_id == 'default-org':
            logger.warning(f"DIRECT_SPLIT_VIEW: No valid organization provided (organization_id={organization_id})")
            context = {
                'sources': [],
                'selected_source': '',
                'is_direct_mode': True,
                'organizations': available_organizations,
                'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL (e.g., ?organization=rsh)',
                'show_organization_help': True
            }
            return render(request, 'direct_split_table_graph.html', context)
        
        # Check if the selected organization actually exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        logger.info(f"DIRECT_SPLIT_VIEW: Organization '{organization_id}' exists in S3: {org_exists}")
        if not org_exists:
            context = {
                'sources': [],
                'selected_source': '',
                'is_direct_mode': True,
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            return render(request, 'direct_split_table_graph.html', context)
        
        # Discover available data sources from S3 for this organization
        logger.info(f"DIRECT_SPLIT_VIEW: Discovering data sources for organization '{organization_id}'")
        sources = analyzer.discover_s3_data_sources(organization_id)
        logger.info(f"DIRECT_SPLIT_VIEW: Found {len(sources)} data sources for organization '{organization_id}'")
        
        # Format sources for dropdown and collect CSV datasets
        sources_info = []
        csv_datasets = []
        
        logger.info(f"DIRECT_SPLIT_VIEW: Processing {len(sources)} sources to find CSV datasets...")
        
        for source in sources:
            dataset_names = analyzer.get_dataset_names_from_s3_source(source)
            logger.info(f"DIRECT_SPLIT_VIEW: Source={source.name}, Format={source.format}, Dataset_names={dataset_names}")
            
            # Collect CSV/parseable datasets from this source
            source_csv_datasets = []
            for dataset_name in dataset_names:
                dataset_lower = dataset_name.lower()
                logger.info(f"DIRECT_SPLIT_VIEW: Checking dataset '{dataset_name}' (lower: '{dataset_lower}')")
                
                is_csv = (dataset_lower.endswith(('.csv', '.tsv', '.txt')) or 
                         'csv' in dataset_lower or 
                         (source.format and source.format.lower() in ['csv', 'tsv', 'text']))
                
                logger.info(f"DIRECT_SPLIT_VIEW: Dataset '{dataset_name}' is_csv={is_csv}")
                
                if is_csv:
                    csv_dataset = {
                        'name': dataset_name,
                        'source': source.name,
                        'format': source.format or 'csv'
                    }
                    csv_datasets.append(csv_dataset)
                    source_csv_datasets.append(csv_dataset)
                    logger.info(f"DIRECT_SPLIT_VIEW: ✅ Added CSV dataset: {dataset_name} from source {source.name} (format: {source.format})")
                else:
                    logger.info(f"DIRECT_SPLIT_VIEW: ❌ Skipped non-CSV dataset: {dataset_name}")
            
            # Only add source to dropdown if it has CSV datasets
            if source_csv_datasets:
                sources_info.append({
                    'name': source.name,
                    'dataset_count': len(source_csv_datasets),
                    'display_name': source.name,
                    'format': source.format,
                    'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                    'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                })
                logger.info(f"DIRECT_SPLIT_VIEW: ✅ Added source '{source.name}' to dropdown with {len(source_csv_datasets)} CSV datasets")
            else:
                logger.info(f"DIRECT_SPLIT_VIEW: ❌ Skipped source '{source.name}' - no CSV datasets found")
        
        logger.info(f"Found {len(csv_datasets)} CSV datasets total: {[d['name'] for d in csv_datasets]}")
        
        # Load existing mappings from database (new structure)
        existing_mappings = Mapping.objects.filter(
            organization_id=organization_id
        ).order_by('-created_at')[:50]  # Get latest 50 mappings
        
        # Convert database mappings to template format
        mappings_data = []
        for mapping in existing_mappings:
            mapping_info = {
                'id': str(mapping.id),
                'name': mapping.name,
                'mapping_type': mapping.mapping_type,
                'mapping_type_display': mapping.get_mapping_type_display(),
                'source_dataset': mapping.source_dataset,
                'validation_status': mapping.validation_status,
                'created_at': mapping.created_at.isoformat(),
                'config': mapping.mapping_config,
                'execution_stats': mapping.execution_stats
            }
            mappings_data.append(mapping_info)
        
        # Get consolidated state
        state = get_organization_state(request, organization_id)
        
        context = {
            'sources': sources_info,
            'datasets': state['all_datasets'],
            'selected_datasets': state['active_dataset_names'],
            'selected_datasets_with_details': state['active_datasets'],
            'selected_columns': state['selected_columns'],
            'selected_source': request.GET.get('source', ''),
            'is_direct_mode': True,
            'organizations': available_organizations,
            'organization_id': organization_id,
            'mappings': mappings_data,
            'datasets_json': json.dumps(state['all_datasets'], cls=DjangoJSONEncoder) if state['all_datasets'] else '[]',
        }
        
        logger.info(f"DIRECT_SPLIT_VIEW: Rendering template with {len(csv_datasets)} datasets for organization '{organization_id}'")
        return render(request, 'direct_split_table_graph.html', context)
        
    except Exception as e:
        logger.error(f"Error in direct_split_table_graph_view: {e}")
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'sources': [],
            'selected_source': '',
            'error': f"Error loading data sources: {str(e)}",
            'is_direct_mode': True,
            'organizations': available_organizations,
        }
        return render(request, 'direct_split_table_graph.html', context)



def direct_load_source_data(request):
    """
    HTMX endpoint to load source data directly from S3 files using S3DirectDataAnalyzer.
    Provides fast previews without database import.
    """
    source_name = request.GET.get('source', '')
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DIRECT LOAD: Loading data for source={source_name}, org={organization_id}")
    
    if not source_name:
        empty_response = render(request, 'partials/empty_state.html')
        empty_response['HX-Trigger'] = 'sourceDataLoaded'
        return empty_response
    
    if not organization_id or organization_id == 'default-org':
        error_response = render(request, 'partials/empty_state.html', {
            'error': "Organization parameter required. Please add ?organization=YOUR_ORG to the URL."
        })
        return error_response
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Get source summary with all datasets from S3
        logger.info(f"DIRECT LOAD: Getting source summary for {source_name}")
        source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
        logger.info(f"DIRECT LOAD: Source summary: {len(source_summary.get('datasets', []))} datasets found")
        
        # Build datasets information for table display
        datasets_data = []
        for dataset_info in source_summary['datasets']:
            if 'error' not in dataset_info:
                logger.info(f"DIRECT LOAD: Processing dataset {dataset_info['name']}: {dataset_info['row_count']} rows, {dataset_info['column_count']} cols")
                datasets_data.append({
                    'name': dataset_info['name'],
                    'source': source_name,
                    'cell_count': dataset_info['row_count'] * dataset_info['column_count'],
                    'row_count': dataset_info['row_count'],
                    'column_count': dataset_info['column_count'],
                    'preview': {
                        'colHeaders': dataset_info['columns'],
                        'data': dataset_info['sample_data'],
                        'showing_rows': len(dataset_info['sample_data']),
                        'total_rows': dataset_info['row_count'],
                        'has_more': dataset_info['row_count'] > len(dataset_info['sample_data']),
                        'offset': 0
                    },
                    'multi_value_columns': dataset_info.get('multi_value_columns', [])
                })
            else:
                logger.error(f"DIRECT LOAD: Dataset {dataset_info.get('name', 'unknown')} has error: {dataset_info.get('error')}")
        
        logger.info(f"DIRECT LOAD: Built {len(datasets_data)} dataset entries for display")
        
        # Generate simplified graph data for direct mode
        # Note: Full relationship analysis is expensive, so we provide basic structure
        graph_data = _build_direct_graph_data(source_summary)
        
        cached_data = {
            'source': source_name,
            'datasets': datasets_data,
            'graph_data': graph_data,
            'is_direct_mode': True,
            'source_info': source_summary['source_info'],
            'organization_id': organization_id  # Add organization to context
        }
        
        response = render(request, 'partials/source_data.html', cached_data)
        response['HX-Trigger'] = 'sourceDataLoaded'
        return response
        
    except Exception as e:
        logger.error(f"DIRECT LOAD: Error loading source data: {e}", exc_info=True)
        
        error_response = render(request, 'partials/empty_state.html', {
            'error': f"Error loading source data: {str(e)}"
        })
        return error_response



def direct_load_all_datasets(request):
    """
    HTMX endpoint to load all available datasets from S3 for the dataset browser.
    Provides lazy loading of dataset cards for browsing.
    """
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DIRECT LOAD ALL DATASETS: Loading all datasets for org={organization_id}")
    
    if not organization_id or organization_id == 'default-org':
        return render(request, 'partials/datasets_grid.html', {
            'error': "Organization parameter required. Please add ?organization=YOUR_ORG to the URL.",
            'datasets': []
        })
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Discover all data sources from S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        logger.info(f"DIRECT LOAD ALL DATASETS: Found {len(sources)} sources")
        
        # Build datasets information from all sources
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                logger.info(f"DIRECT LOAD ALL DATASETS: Source {source.name} has {len(dataset_names)} datasets")
                
                for dataset_name in dataset_names:
                    try:
                        # Get basic preview for each dataset (limited for performance)
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'cell_count': preview.total_rows * len(preview.column_headers),
                            'preview': {
                                'colHeaders': preview.column_headers[:5],  # Show first 5 columns
                                'data': preview.data_rows,
                                'showing_rows': preview.showing_rows,
                                'total_rows': preview.total_rows,
                                'has_more': preview.has_more,
                                'offset': 0
                            },
                            'file_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            },
                            'multi_value_columns': preview.multi_value_columns[:3],  # Show first 3
                            'column_types': getattr(preview, 'column_types', {})
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"DIRECT LOAD ALL DATASETS: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        # Add error entry
                        all_datasets.append({
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'error': str(dataset_error),
                            'row_count': 0,
                            'column_count': 0,
                            'cell_count': 0
                        })
                        continue
                        
            except Exception as source_error:
                logger.error(f"DIRECT LOAD ALL DATASETS: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"DIRECT LOAD ALL DATASETS: Built {len(all_datasets)} dataset entries")
        
        return render(request, 'partials/datasets_grid.html', {
            'datasets': all_datasets,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets),
            'sources_count': len(sources)
        })
        
    except Exception as e:
        logger.error(f"DIRECT LOAD ALL DATASETS: Error loading all datasets: {e}", exc_info=True)
        
        return render(request, 'partials/datasets_grid.html', {
            'error': f"Error loading datasets: {str(e)}",
            'datasets': []
        })



def direct_get_dataset_card(request):
    """Get a dataset card with preview using direct S3 file analysis."""
    source_name = request.GET.get('source', '')
    dataset_name = request.GET.get('dataset_name', '')
    organization_id = get_organization_id_from_request(request)

    logger.info(f"🎯 DATASET CARD REQUEST: source={source_name}, dataset={dataset_name}, org={organization_id}")
    logger.info(f"🎯 DATASET CARD REQUEST: All GET params: {dict(request.GET)}")

    if not source_name or not dataset_name:
        logger.error(f"🎯 DATASET CARD ERROR: Missing parameters - source={source_name}, dataset={dataset_name}")
        return HttpResponseBadRequest("Missing source or dataset_name")

    if not organization_id or organization_id == 'default-org':
        logger.error(f"🎯 DATASET CARD ERROR: Invalid organization - {organization_id}")
        return HttpResponseBadRequest("Organization parameter required")

    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        logger.info(f"🎯 DATASET CARD: Discovering sources for org {organization_id}")
        sources = analyzer.discover_s3_data_sources(organization_id)
        logger.info(f"🎯 DATASET CARD: Found {len(sources)} sources: {[s.name for s in sources]}")
        
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            logger.error(f"🎯 DATASET CARD ERROR: Source '{source_name}' not found in available sources: {[s.name for s in sources]}")
            return HttpResponseBadRequest(f"Source '{source_name}' not found")
        
        # Get detailed preview for this dataset from S3
        logger.info(f"🎯 DATASET CARD: Getting preview for {dataset_name} from source {source_name}")
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=10)
        logger.info(f"🎯 DATASET CARD: Preview loaded - {preview.total_rows} rows, {len(preview.column_headers)} columns")
        
        dataset = {
            'name': dataset_name,
            'source': source_name,
            'cell_count': preview.total_rows * len(preview.column_headers),
            'row_count': preview.total_rows,
            'column_count': len(preview.column_headers),
            'preview': {
                'colHeaders': preview.column_headers,
                'data': preview.data_rows,
                'showing_rows': preview.showing_rows,
                'total_rows': preview.total_rows,
                'has_more': preview.has_more,
                'offset': preview.offset
            },
            'column_types': preview.column_types,
            'multi_value_columns': preview.multi_value_columns
        }

        # Track that this dataset is now loaded
        _track_dataset_loading(organization_id, dataset_name, source_name, preview.column_headers)
        
        # Get consolidated state for proper context
        state = get_organization_state(request, organization_id)
        
        # Get selected column names for this dataset to pass to template
        dataset_selected_columns = [col['column_name'] for col in state['selected_columns'] 
                                   if col.get('dataset_name') == dataset_name and col.get('source_name') == source_name]
        
        logger.info(f"🎯 DATASET CARD: Dataset {dataset_name} has {len(dataset_selected_columns)} selected columns: {dataset_selected_columns}")
        logger.info(f"🎯 DATASET CARD: Rendering template with dataset {dataset_name}")
        response = render(request, 'partials/dataset_card.html', {
            'dataset': dataset,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{i}" for i in range(len(preview.data_rows))],
            'source': source_name,
            'is_direct_mode': True,
            'organization_id': organization_id,
            'datasets_json': json.dumps(state['all_datasets'], cls=DjangoJSONEncoder) if state['all_datasets'] else '[]',
            'selected_columns': state['selected_columns'],
            'selected_datasets': state['active_dataset_names'],
            'dataset_selected_columns': dataset_selected_columns  # Pass selected columns for this dataset
        })
        logger.info(f"🎯 DATASET CARD SUCCESS: Template rendered for {dataset_name} with {len(state['all_datasets'])} datasets, {len(state['selected_columns'])} selected columns")
        return response
        
    except Exception as e:
        logger.error(f"🎯 DATASET CARD ERROR: Exception getting dataset card: {e}", exc_info=True)
        return HttpResponseBadRequest(f"Error: {str(e)}")



def direct_load_more_dataset_rows(request):
    """Load more rows using S3DirectDataAnalyzer pagination."""
    logger.info("=== LOAD MORE ROWS VIEW CALLED ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request path: {request.path}")
    logger.info(f"Request GET params: {dict(request.GET)}")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 20))
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"Parsed params - source: {source_name}, dataset: {dataset_name}, offset: {offset}, limit: {limit}, org: {organization_id}")
    
    if not source_name or not dataset_name:
        logger.error("Missing source_name or dataset_name parameters")
        return render(request, 'partials/table_rows.html', {'data': []})
    
    if not organization_id or organization_id == 'default-org':
        logger.error(f"Invalid organization_id: {organization_id}")
        return render(request, 'partials/table_rows.html', {'data': []})
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        logger.info(f"Discovering S3 data sources for org: {organization_id}")
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            logger.error(f"Source '{source_name}' not found in discovered sources: {[s.name for s in sources]}")
            return render(request, 'partials/table_rows.html', {'data': []})
        
        logger.info(f"Found source: {source_info.name}, getting preview with offset: {offset}, limit: {limit}")
        
        # Get the requested slice from S3
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, offset=offset, limit=limit)
        
        logger.info(f"Preview retrieved - data_rows: {len(preview.data_rows)}, has_more: {preview.has_more}, total_rows: {preview.total_rows}")
        
        response_context = {
            'data': preview.data_rows,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{offset + i}" for i in range(len(preview.data_rows))],
            'source': source_name,
            'dataset': dataset_name,
            'preview': {
                'showing_rows': offset + len(preview.data_rows),  # Total rows shown so far
                'total_rows': preview.total_rows,
                'has_more': preview.has_more,
                'offset': offset + len(preview.data_rows)  # Next offset
            },
            'is_direct_mode': True,
            'organization_id': organization_id  # Add organization to context
        }
        
        logger.info(f"Rendering response with context: {response_context['preview']}")
        
        return render(request, 'partials/load_more_response.html', response_context)
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}", exc_info=True)
        return render(request, 'partials/table_rows.html', {'data': []})



def direct_analyze_dataset_relationships(request):
    """
    Analyze relationships in a dataset using direct S3 file analysis.
    More expensive operation that includes full relationship discovery.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    organization_id = get_organization_id_from_request(request)
    
    if not source_name or not dataset_name:
        return JsonResponse({'error': 'Missing source or dataset parameters'}, status=400)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return JsonResponse({'error': f"Source '{source_name}' not found"}, status=404)
        
        # Perform complete analysis including relationships
        analysis = analyzer.analyze_s3_dataset_completely(
            source_info, 
            dataset_name, 
            include_relationships=True
        )
        
        # Format for JSON response
        result = {
            'dataset_name': dataset_name,
            'source_name': source_name,
            'analysis': {
                'row_count': analysis.row_count,
                'column_count': analysis.column_count,
                'column_types': analysis.column_types,
                'data_quality': analysis.data_quality_metrics,
                'suggested_strategy': analysis.suggested_import_strategy,
                'multi_value_analysis': analysis.multi_value_analysis
            }
        }
        
        # Include relationship analysis if available
        if analysis.relationship_analysis:
            result['relationships'] = analysis.relationship_analysis
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error analyzing dataset relationships: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def toggle_dataset_card(request):
    """
    Server-side toggle for dataset cards. Manages state in session.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")
    
    source_name = request.POST.get('source', '')
    dataset_name = request.POST.get('dataset_name', '')
    organization_id = request.POST.get('organization', '')
    
    logger.info(f"TOGGLE DATASET CARD: source={source_name}, dataset={dataset_name}, org={organization_id}")
    
    if not all([source_name, dataset_name, organization_id]):
        return HttpResponseBadRequest("Missing required parameters")
    
    try:
        # Get session state for selected datasets
        session_key = f"selected_datasets_{organization_id}"
        selected_datasets = request.session.get(session_key, [])
        
        # Toggle the dataset
        if dataset_name in selected_datasets:
            selected_datasets.remove(dataset_name)
            logger.info(f"TOGGLE: Removed {dataset_name} from selection")
        else:
            # Add to the beginning of the list to show it at the top
            selected_datasets.insert(0, dataset_name)
            logger.info(f"TOGGLE: Added {dataset_name} to selection (added to top)")
        
        # Save back to session
        request.session[session_key] = selected_datasets
        
        # Get consolidated state using the helper function
        state = get_organization_state(request, organization_id)
        
        # Render table content
        table_content_html = render_to_string('partials/table_content.html', {
            'selected_datasets_with_details': state['active_datasets'],
            'organization_id': organization_id,
        }, request=request)
        
        # Render updated dataset badges
        badges_html = render_to_string('partials/dataset_badges.html', {
            'datasets': state['all_datasets'],
            'selected_datasets': state['active_dataset_names'],
            'organization_id': organization_id,
            'csrf_token': request.META.get('CSRF_COOKIE')
        }, request=request)
        
        # Render updated relationship builder with active datasets
        relationship_builder_html = render_to_string('partials/relationship_builder.html', {
            'datasets': state['all_datasets'],
            'organization_id': organization_id,
            'selected_columns': state.get('selected_columns', []),
            'active_datasets': state['active_datasets'],
            'mappings': state.get('mappings', []),
            'anchor_column': state.get('anchor_column')
        }, request=request)
        
        # Return all updates using out-of-band swaps
        response_html = f"""
        {table_content_html}
        <div hx-swap-oob="innerHTML:#dataset-badges">
            {badges_html}
        </div>
        <div hx-swap-oob="innerHTML:#relationship-builder">
            {relationship_builder_html}
        </div>
        """
        
        logger.info(f"TOGGLE: Rendering table content with {len(state['active_datasets'])} active datasets and updated badges")
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"TOGGLE DATASET CARD ERROR: {e}", exc_info=True)
        return HttpResponseBadRequest(f"Error: {str(e)}")


def direct_get_import_preview(request):
    """
    Get a preview of what would happen if we imported this S3 dataset.
    Uses SmartBulkUpdater's analysis capabilities.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    organization_id = get_organization_id_from_request(request)
    
    if not source_name or not dataset_name:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Use the S3 import preview method
        import_preview = analyzer.get_s3_import_preview(organization_id, source_name, dataset_name)
        
        return JsonResponse(import_preview)
        
    except Exception as e:
        logger.error(f"Error getting import preview: {e}")
        return JsonResponse({'error': str(e)}, status=500)



def direct_analyze_column(request):
    """
    Analyze a specific column from a dataset using direct S3 file analysis.
    Provides data profiling, pattern detection, and linking suggestions.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    column_name = request.GET.get('column')
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"Column analysis request: source={source_name}, dataset={dataset_name}, column={column_name}, org={organization_id}")
    
    if not source_name or not dataset_name or not column_name:
        return HttpResponseBadRequest("Missing required parameters: source, dataset, and column")
    
    if not organization_id or organization_id == 'default-org':
        return HttpResponseBadRequest("Organization parameter required")
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return HttpResponseBadRequest(f"Source '{source_name}' not found")
        
        # Get column data and analysis
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=100)
        
        # Find column index
        try:
            column_index = preview.column_headers.index(column_name)
        except ValueError:
            return HttpResponseBadRequest(f"Column '{column_name}' not found in dataset")
        
        # Get full dataset for relationship analysis
        full_preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=1000)  # Larger sample for better analysis
        
        # Create temporary CSV file for relationship analysis
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            # Write headers
            temp_file.write(','.join(full_preview.column_headers) + '\n')
            # Write data rows
            for row in full_preview.data_rows:
                # Ensure all rows have the same number of columns
                padded_row = row + [None] * (len(full_preview.column_headers) - len(row))
                row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell is not None else '' for cell in padded_row])
                temp_file.write(row_str + '\n')
            temp_csv_path = temp_file.name
        
        try:
            # Use relationship discovery service for sophisticated analysis
            relationship_service = RelationshipDiscoveryService()
            dataset_analysis = relationship_service.analyze_dataset_relationships(temp_csv_path, sample_size=1000)
            
            # Extract column values for basic analysis
            column_values = [row[column_index] if column_index < len(row) else None for row in preview.data_rows]
            
            # Combine basic analysis with relationship insights
            basic_analysis = _analyze_column_data(column_name, column_values, preview.total_rows)
            relationship_insights = _extract_column_relationship_insights(column_name, dataset_analysis)
            
            # Merge analyses
            analysis = {**basic_analysis, **relationship_insights}
            
            # Add dataset context
            analysis['dataset_info'] = {
                'name': dataset_name,
                'source': source_name,
                'total_rows': preview.total_rows,
                'total_columns': len(preview.column_headers),
                'column_index': column_index
            }
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_csv_path)
            except Exception as cleanup_error:
                logger.warning(f"Could not clean up temp file: {cleanup_error}")
        
        # Render the analysis partial
        return render(request, 'partials/column_analysis.html', {
            'analysis': analysis,
            'column_name': column_name,
            'dataset_name': dataset_name,
            'source_name': source_name,
            'organization_id': organization_id
        })
        
    except Exception as e:
        logger.error(f"Error analyzing column: {e}", exc_info=True)
        return render(request, 'partials/column_analysis.html', {
            'error': f"Error analyzing column: {str(e)}",
            'column_name': column_name,
            'dataset_name': dataset_name,
            'source_name': source_name
        })


def _discover_available_organizations(analyzer):
    """
    Discover available organizations by checking S3 buckets.
    Similar to how archivist dashboard works.
    """
    try:
        # Standard organization list (same as archivist dashboard)
        standard_orgs = [
            {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
            {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
            {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
            {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
            {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
        ]
        
        # Check which organizations actually have S3 data
        for org in standard_orgs:
            try:
                # Try to discover sources for this organization
                sources = analyzer.discover_s3_data_sources(org['id'])
                if sources:  # If sources found, mark as active
                    org['status'] = 'active'
                else:
                    org['status'] = 'inactive'
            except Exception as e:
                logger.debug(f"Organization {org['id']} check failed: {e}")
                org['status'] = 'inactive'
        
        return standard_orgs
        
    except Exception as e:
        logger.error(f"Error discovering organizations: {e}")
        # Return standard list with unknown status if discovery fails
        return [
            {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
            {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
            {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
            {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
            {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
        ]


def _load_all_csv_datasets_data(analyzer, organization_id, sources, csv_datasets):
    """
    Load table data for all CSV datasets from all sources.
    Similar to direct_load_source_data but for all sources at once.
    """
    all_datasets_data = []
    
    # Group datasets by source for efficient loading
    datasets_by_source = {}
    for dataset in csv_datasets:
        source_name = dataset['source']
        if source_name not in datasets_by_source:
            datasets_by_source[source_name] = []
        datasets_by_source[source_name].append(dataset)
    
    # Load data for each source
    for source_name, source_datasets in datasets_by_source.items():
        try:
            logger.info(f"Loading data for source: {source_name} with {len(source_datasets)} datasets")
            
            # Get source summary for this source
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Build datasets information for table display
            for dataset_info in source_summary['datasets']:
                if 'error' not in dataset_info:
                    # Check if this dataset is in our CSV list
                    if any(d['name'] == dataset_info['name'] for d in source_datasets):
                        logger.info(f"Adding dataset {dataset_info['name']}: {dataset_info['row_count']} rows, {dataset_info['column_count']} cols")
                        all_datasets_data.append({
                            'name': dataset_info['name'],
                            'source': source_name,
                            'cell_count': dataset_info['row_count'] * dataset_info['column_count'],
                            'row_count': dataset_info['row_count'],
                            'column_count': dataset_info['column_count'],
                            'preview': {
                                'colHeaders': dataset_info['columns'],
                                'data': dataset_info['sample_data'],
                                'showing_rows': len(dataset_info['sample_data']),
                                'total_rows': dataset_info['row_count'],
                                'has_more': dataset_info['row_count'] > len(dataset_info['sample_data']),
                                'offset': 0
                            },
                            'multi_value_columns': dataset_info.get('multi_value_columns', [])
                        })
                else:
                    logger.error(f"Dataset {dataset_info.get('name', 'unknown')} has error: {dataset_info.get('error')}")
        
        except Exception as source_error:
            logger.error(f"Error loading source {source_name}: {source_error}")
            continue
    
    logger.info(f"Loaded {len(all_datasets_data)} datasets total for table display")
    return all_datasets_data


def _build_direct_graph_data(source_summary):
    """
    Build basic graph data from source summary for visualization.
    This provides structural information without expensive relationship analysis.
    """
    nodes = []
    links = []
    
    # Add source node
    source_info = source_summary['source_info']
    nodes.append({
        'id': f"source_{source_info.name}",
        'label': source_info.name,
        'type': 'source',
        'level': 0,
        'color': '#3B82F6',  # Blue for sources
        'size': 30
    })
    
    # Add dataset nodes and basic column nodes
    for i, dataset in enumerate(source_summary['datasets']):
        if 'error' in dataset:
            continue
            
        # Dataset node
        dataset_id = f"dataset_{dataset['name']}"
        nodes.append({
            'id': dataset_id,
            'label': dataset['name'],
            'type': 'dataset',
            'level': 1,
            'color': '#10B981',  # Green for datasets
            'size': 25,
            'row_count': dataset['row_count'],
            'column_count': dataset['column_count']
        })
        
        # Link source to dataset
        links.append({
            'from': f"source_{source_info.name}",
            'to': dataset_id,
            'type': 'contains'
        })
        
        # Add some column nodes (limit to avoid overwhelming the graph)
        for j, column in enumerate(dataset['columns'][:10]):  # Max 10 columns per dataset
            column_id = f"column_{dataset['name']}_{column}"
            nodes.append({
                'id': column_id,
                'label': column,
                'type': 'column',
                'level': 2,
                'color': '#F59E0B',  # Orange for columns
                'size': 15,
                'is_multi_value': column in dataset.get('multi_value_columns', [])
            })
            
            # Link dataset to column
            links.append({
                'from': dataset_id,
                'to': column_id,
                'type': 'has_column'
            })
    
    return {
        'nodes': json.dumps(nodes),
        'links': json.dumps(links),
        'source': source_info.name,
        'dataset_count': len([d for d in source_summary['datasets'] if 'error' not in d]),
        'total_nodes': len(nodes),
        'total_links': len(links),
        'is_direct_mode': True
    }


def _analyze_column_data(column_name, column_values, total_rows):
    """
    Analyze column data to provide insights for linking and preprocessing.
    """
    import re
    from collections import Counter, defaultdict
    
    # Filter out None/empty values
    non_empty_values = [str(v).strip() for v in column_values if v is not None and str(v).strip()]
    
    # Basic statistics
    total_values = len(column_values)
    non_empty_count = len(non_empty_values)
    empty_count = total_values - non_empty_count
    fill_rate = (non_empty_count / total_values) * 100 if total_values > 0 else 0
    
    # Value frequency analysis
    value_counts = Counter(non_empty_values)
    unique_count = len(value_counts)
    most_common = value_counts.most_common(10)
    
    # Data type detection
    data_type = _detect_data_type(non_empty_values)
    
    # Pattern analysis
    patterns = _analyze_patterns(non_empty_values)
    
    # Multi-value detection (values that might need splitting)
    multi_value_analysis = _analyze_multi_values(non_empty_values)
    
    # Linking suggestions
    linking_suggestions = _generate_linking_suggestions(column_name, non_empty_values, data_type)
    
    # Data quality issues
    quality_issues = _detect_quality_issues(non_empty_values, patterns)
    
    return {
        'basic_stats': {
            'total_values': total_values,
            'non_empty_count': non_empty_count,
            'empty_count': empty_count,
            'fill_rate': round(fill_rate, 1),
            'unique_count': unique_count,
            'duplicate_rate': round(((non_empty_count - unique_count) / non_empty_count) * 100, 1) if non_empty_count > 0 else 0
        },
        'data_type': data_type,
        'value_distribution': {
            'most_common': most_common[:5],
            'sample_values': non_empty_values[:10] if non_empty_values else []
        },
        'patterns': patterns,
        'multi_value_analysis': multi_value_analysis,
        'linking_suggestions': linking_suggestions,
        'quality_issues': quality_issues,
        'preprocessing_recommendations': _generate_preprocessing_recommendations(patterns, multi_value_analysis, quality_issues)
    }


def _detect_data_type(values):
    """Detect the primary data type of the column values."""
    if not values:
        return {'type': 'empty', 'confidence': 100}
    
    type_counts = {'integer': 0, 'float': 0, 'date': 0, 'url': 0, 'email': 0, 'text': 0}
    
    for value in values[:50]:  # Sample first 50 values for performance
        # Integer check
        if re.match(r'^-?\d+$', value):
            type_counts['integer'] += 1
        # Float check
        elif re.match(r'^-?\d+\.\d+$', value):
            type_counts['float'] += 1
        # Date check (basic patterns)
        elif re.match(r'\d{4}-\d{2}-\d{2}', value) or re.match(r'\d{2}/\d{2}/\d{4}', value):
            type_counts['date'] += 1
        # URL check
        elif re.match(r'https?://', value):
            type_counts['url'] += 1
        # Email check
        elif re.match(r'\S+@\S+\.\S+', value):
            type_counts['email'] += 1
        else:
            type_counts['text'] += 1
    
    # Determine primary type
    total_checked = sum(type_counts.values())
    if total_checked == 0:
        return {'type': 'empty', 'confidence': 100}
    
    primary_type = max(type_counts.keys(), key=lambda k: type_counts[k])
    confidence = round((type_counts[primary_type] / total_checked) * 100, 1)
    
    return {'type': primary_type, 'confidence': confidence, 'distribution': type_counts}


def _analyze_patterns(values):
    """Analyze common patterns in the values."""
    if not values:
        return {}
    
    # Length analysis
    lengths = [len(v) for v in values]
    
    # Common separators
    separators = {';': 0, ',': 0, '|': 0, '/': 0, '-': 0, ':': 0}
    for value in values:
        for sep in separators:
            if sep in value:
                separators[sep] += 1
    
    # Character patterns
    has_numbers = sum(1 for v in values if re.search(r'\d', v))
    has_special_chars = sum(1 for v in values if re.search(r'[^a-zA-Z0-9\s]', v))
    
    return {
        'length_stats': {
            'min': min(lengths) if lengths else 0,
            'max': max(lengths) if lengths else 0,
            'avg': round(sum(lengths) / len(lengths), 1) if lengths else 0
        },
        'common_separators': {k: v for k, v in separators.items() if v > 0},
        'character_analysis': {
            'has_numbers': has_numbers,
            'has_special_chars': has_special_chars,
            'numeric_percentage': round((has_numbers / len(values)) * 100, 1),
            'special_char_percentage': round((has_special_chars / len(values)) * 100, 1)
        }
    }


def _analyze_multi_values(values):
    """Detect if values contain multiple sub-values that might need splitting."""
    if not values:
        return {'needs_splitting': False}
    
    separators = [';', ',', '|', '/', ' and ', ' & ', ' + ']
    separator_analysis = {}
    
    for sep in separators:
        split_counts = []
        for value in values[:20]:  # Sample for performance
            if sep in value:
                parts = value.split(sep)
                if len(parts) > 1:
                    split_counts.append(len(parts))
        
        if split_counts:
            separator_analysis[sep] = {
                'occurrence_count': len(split_counts),
                'avg_splits': round(sum(split_counts) / len(split_counts), 1),
                'max_splits': max(split_counts)
            }
    
    # Determine if splitting is recommended
    needs_splitting = False
    recommended_separator = None
    
    for sep, analysis in separator_analysis.items():
        if analysis['occurrence_count'] > len(values) * 0.1:  # 10% threshold
            needs_splitting = True
            if not recommended_separator or analysis['occurrence_count'] > separator_analysis[recommended_separator]['occurrence_count']:
                recommended_separator = sep
    
    return {
        'needs_splitting': needs_splitting,
        'recommended_separator': recommended_separator,
        'separator_analysis': separator_analysis
    }


def _generate_linking_suggestions(column_name, values, data_type):
    """Generate suggestions for linking this column to other datasets."""
    suggestions = []
    
    # Name-based suggestions
    name_lower = column_name.lower()
    
    if 'id' in name_lower:
        suggestions.append({
            'type': 'identifier',
            'confidence': 'high',
            'description': 'This appears to be an identifier column - good for linking records',
            'action': 'Use as primary key for joins'
        })
    
    if any(term in name_lower for term in ['name', 'title', 'label']):
        suggestions.append({
            'type': 'text_match',
            'confidence': 'medium',
            'description': 'Text column that might match names/titles in other datasets',
            'action': 'Consider fuzzy matching with similar columns'
        })
    
    if any(term in name_lower for term in ['date', 'time', 'created', 'modified']):
        suggestions.append({
            'type': 'temporal',
            'confidence': 'medium',
            'description': 'Temporal column useful for time-based joins',
            'action': 'Link records within time ranges'
        })
    
    # Data type-based suggestions
    if data_type['type'] == 'url':
        suggestions.append({
            'type': 'url_reference',
            'confidence': 'high',
            'description': 'URLs can be matched exactly across datasets',
            'action': 'Direct URL matching'
        })
    
    if data_type['type'] == 'email':
        suggestions.append({
            'type': 'email_reference',
            'confidence': 'high',
            'description': 'Email addresses are unique identifiers',
            'action': 'Use for person/contact linking'
        })
    
    # Value pattern-based suggestions
    if not suggestions:
        suggestions.append({
            'type': 'general',
            'confidence': 'low',
            'description': 'General text column - may need preprocessing before linking',
            'action': 'Clean and standardize values first'
        })
    
    return suggestions


def _detect_quality_issues(values, patterns):
    """Detect potential data quality issues."""
    issues = []
    
    if not values:
        return [{'type': 'empty_column', 'severity': 'high', 'description': 'Column is completely empty'}]
    
    # Check for inconsistent formatting
    if patterns.get('length_stats', {}).get('max', 0) - patterns.get('length_stats', {}).get('min', 0) > 50:
        issues.append({
            'type': 'inconsistent_length',
            'severity': 'medium',
            'description': 'Values have very different lengths - possible formatting issues'
        })
    
    # Check for mixed separators
    separators = patterns.get('common_separators', {})
    if len([s for s in separators.values() if s > 0]) > 1:
        issues.append({
            'type': 'mixed_separators',
            'severity': 'medium',
            'description': 'Multiple separators used - standardization needed'
        })
    
    # Check for potential encoding issues
    encoding_issues = sum(1 for v in values if any(char in v for char in ['�', '\ufffd']))
    if encoding_issues > 0:
        issues.append({
            'type': 'encoding_issues',
            'severity': 'high',
            'description': f'{encoding_issues} values may have encoding problems'
        })
    
    return issues


def _generate_preprocessing_recommendations(patterns, multi_value_analysis, quality_issues):
    """Generate recommendations for preprocessing this column."""
    recommendations = []
    
    # Multi-value splitting
    if multi_value_analysis.get('needs_splitting'):
        sep = multi_value_analysis.get('recommended_separator', ';')
        recommendations.append({
            'type': 'split_values',
            'priority': 'high',
            'description': f'Split values using "{sep}" separator to create multiple records',
            'action': f'Apply split transformation with separator "{sep}"'
        })
    
    # Quality issue fixes
    for issue in quality_issues:
        if issue['type'] == 'mixed_separators':
            recommendations.append({
                'type': 'standardize_separators',
                'priority': 'medium',
                'description': 'Standardize all separators to a single type',
                'action': 'Replace all separators with semicolons'
            })
        elif issue['type'] == 'encoding_issues':
            recommendations.append({
                'type': 'fix_encoding',
                'priority': 'high',
                'description': 'Fix character encoding issues',
                'action': 'Re-encode data with UTF-8'
            })
    
    # Length normalization
    length_stats = patterns.get('length_stats', {})
    if length_stats.get('max', 0) - length_stats.get('min', 0) > 100:
        recommendations.append({
            'type': 'normalize_length',
            'priority': 'low',
            'description': 'Consider truncating very long values',
            'action': 'Limit values to reasonable length (e.g., 255 characters)'
        })
    
    return recommendations


def _track_dataset_loading(organization_id, dataset_name, source_name, columns):
    """
    Helper function to track when a dataset is loaded/viewed.
    This maintains the list of currently loaded datasets for the manual linking tool.
    """
    try:
        from datetime import datetime
        
        # Get current loaded datasets from cache
        loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
        loaded_datasets = cache.get(loaded_datasets_cache_key, [])
        
        # Create dataset info object
        dataset_info = {
            'name': dataset_name,
            'source_name': source_name,
            'columns': columns,
            'loaded_at': datetime.now().isoformat(),
        }
        
        # Remove if already exists (to update timestamp)
        loaded_datasets = [d for d in loaded_datasets if not (d['name'] == dataset_name and d['source_name'] == source_name)]
        
        # Add to beginning of list (most recently loaded first)
        loaded_datasets.insert(0, dataset_info)
        
        # Keep only last 15 loaded datasets to avoid cache bloat
        loaded_datasets = loaded_datasets[:15]
        
        # Save back to cache
        cache.set(loaded_datasets_cache_key, loaded_datasets, timeout=60*60*24)  # 24 hours
        
        logger.info(f"TRACK: Dataset {dataset_name} from {source_name} tracked as loaded ({len(loaded_datasets)} total)")
        
    except Exception as e:
        logger.warning(f"TRACK: Could not track dataset loading: {e}")


def _extract_column_relationship_insights(column_name, dataset_analysis):
    """
    Extract relationship insights for a specific column from the dataset analysis.
    Uses the sophisticated RelationshipDiscoveryService results.
    """
    insights = {
        'relationships': [],
        'semantic_clusters': [],
        'foreign_key_potential': False,
        'relationship_strength': 0.0,
        'suggested_predicates': []
    }
    
    # Find relationships involving this column
    column_relationships = []
    for relationship in dataset_analysis.relationships:
        if relationship.source_column == column_name or relationship.target_column == column_name:
            column_relationships.append({
                'partner_column': relationship.target_column if relationship.source_column == column_name else relationship.source_column,
                'type': relationship.relationship_type,
                'confidence': relationship.confidence,
                'evidence': relationship.evidence,
                'bidirectional': relationship.bidirectional,
                'suggested_predicate': relationship.suggested_predicate
            })
    
    insights['relationships'] = column_relationships
    
    # Check if column is in any semantic clusters
    for cluster in dataset_analysis.semantic_clusters:
        if column_name in cluster:
            insights['semantic_clusters'].append({
                'members': [col for col in cluster if col != column_name],
                'cluster_size': len(cluster)
            })
    
    # Check foreign key potential
    insights['foreign_key_potential'] = column_name in dataset_analysis.foreign_key_candidates
    
    # Calculate overall relationship strength (average confidence of relationships)
    if column_relationships:
        insights['relationship_strength'] = sum(rel['confidence'] for rel in column_relationships) / len(column_relationships)
    
    # Extract unique suggested predicates
    predicates = set()
    for rel in column_relationships:
        if rel['suggested_predicate']:
            predicates.add(rel['suggested_predicate'])
    insights['suggested_predicates'] = list(predicates)
    
    # Add quality metrics for this column if available
    quality_metrics = dataset_analysis.quality_metrics
    insights['quality_score'] = quality_metrics.get('overall_quality', 0.0)
    
    return insights



def direct_dataset_linking_view(request):
    """
    View for manually linking columns between different datasets.
    Allows users to select multiple datasets and define relationships between their columns.
    Can be used as a partial view for HTMX requests.
    """
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DATASET LINKING: Initializing view for org={organization_id}")
    
    # Check if this is a partial request (HTMX)
    is_partial = 'HX-Request' in request.headers
    
    if not organization_id or organization_id == 'default-org':
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL.',
            'organizations': available_organizations,
            'show_organization_help': True
        }
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        
        # Check if the selected organization exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        if not org_exists:
            context = {
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
            return render(request, template, context)
        
        # Discover available data sources from S3 for this organization
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Build a list of all datasets with their columns for selection
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                
                for dataset_name in dataset_names:
                    try:
                        # Get preview to get column information
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'columns': preview.column_headers,
                            'source_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            }
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"DATASET LINKING: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        continue
                        
            except Exception as source_error:
                logger.error(f"DATASET LINKING: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"DATASET LINKING: Found {len(all_datasets)} datasets for linking")
        
        context = {
            'datasets': all_datasets,
            'organizations': available_organizations,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets)
        }
        
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)
        
    except Exception as e:
        logger.error(f"DATASET LINKING: Error setting up linking view: {e}", exc_info=True)
        
        context = {
            'error': f"Error loading datasets: {str(e)}",
            'organizations': available_organizations,
            'organization_id': organization_id
        }
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)



def save_dataset_links(request):
    """
    AJAX endpoint to save manually created links between datasets.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        data = json.loads(request.body)
        links = data.get('links', [])
        organization_id = data.get('organization_id') or get_organization_id_from_request(request)
        
        logger.info(f"SAVE LINKS: Received {len(links)} dataset links for org={organization_id}")
        
        # Validate links format
        for link in links:
            if not all(k in link for k in ['source_dataset', 'source_column', 'target_dataset', 'target_column', 'relationship_type']):
                return JsonResponse({'error': 'Invalid link format'}, status=400)
        
        # Save links to cache for now (in production, this would go to a database)
        cache_key = f"manual_dataset_links_{organization_id}"
        existing_links = cache.get(cache_key, [])
        
        # Add new links, avoiding duplicates
        for link in links:
            if link not in existing_links:
                existing_links.append(link)
        
        # Save back to cache
        cache.set(cache_key, existing_links, timeout=60*60*24*30)  # 30 days
        
        return JsonResponse({
            'success': True,
            'message': f'Saved {len(links)} dataset links',
            'total_links': len(existing_links)
        })
        
    except Exception as e:
        logger.error(f"SAVE LINKS: Error saving dataset links: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def get_saved_dataset_links(request):
    """
    AJAX endpoint to retrieve saved links between datasets.
    """
    organization_id = request.GET.get('organization_id') or get_organization_id_from_request(request)
    
    logger.info(f"GET LINKS: Retrieving saved dataset links for org={organization_id}")
    
    try:
        # Get links from cache
        cache_key = f"manual_dataset_links_{organization_id}"
        links = cache.get(cache_key, [])
        
        return JsonResponse({
            'links': links,
            'count': len(links),
            'organization_id': organization_id
        })
        
    except Exception as e:
        logger.error(f"GET LINKS: Error retrieving dataset links: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def direct_relationship_discovery_view(request):
    """
    View for automated cross-dataset relationship discovery.
    Allows users to select datasets for automated relationship analysis.
    Can be used as a partial view for HTMX requests.
    """
    organization_id = get_organization_id_from_request(request)
    auto_discover = request.GET.get('auto_discover', False)
    
    logger.info(f"RELATIONSHIP DISCOVERY: Initializing view for org={organization_id}, auto_discover={auto_discover}")
    
    # Check if this is a partial request (HTMX)
    is_partial = 'HX-Request' in request.headers
    
    if not organization_id or organization_id == 'default-org':
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL.',
            'organizations': available_organizations,
            'show_organization_help': True
        }
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        
        # Check if the selected organization exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        if not org_exists:
            context = {
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
            return render(request, template, context)
        
        # Discover available data sources from S3 for this organization
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Build a list of all datasets for selection
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                
                for dataset_name in dataset_names:
                    try:
                        # Get basic preview for each dataset
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'columns': preview.column_headers,
                            'source_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            }
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"RELATIONSHIP DISCOVERY: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        continue
                        
            except Exception as source_error:
                logger.error(f"RELATIONSHIP DISCOVERY: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"RELATIONSHIP DISCOVERY: Found {len(all_datasets)} datasets for analysis")
        
        # If auto_discover is requested, automatically run discovery on all datasets
        discovery_results = None
        if auto_discover and all_datasets:
            try:
                logger.info("RELATIONSHIP DISCOVERY: Running auto-discovery")
                discovery_results = _run_auto_discovery(analyzer, organization_id, all_datasets[:5])  # Limit to first 5 for performance
            except Exception as discovery_error:
                logger.error(f"RELATIONSHIP DISCOVERY: Auto-discovery failed: {discovery_error}")
        
        context = {
            'datasets': all_datasets,
            'organizations': available_organizations,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets),
            'discovery_results': discovery_results,
            'auto_discover': auto_discover
        }
        
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)
        
    except Exception as e:
        logger.error(f"RELATIONSHIP DISCOVERY: Error setting up discovery view: {e}", exc_info=True)
        
        context = {
            'error': f"Error loading datasets: {str(e)}",
            'organizations': available_organizations,
            'organization_id': organization_id
        }
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)


def _run_auto_discovery(analyzer, organization_id, datasets, sample_size=500):
    """
    Helper function to run automated relationship discovery on selected datasets.
    """
    import tempfile
    import os
    
    temp_files = []
    
    try:
        # Create temporary CSV files for analysis
        for dataset_info in datasets:
            source_name = dataset_info.get('source_name')
            dataset_name = dataset_info.get('name')
            
            if not source_name or not dataset_name:
                continue
            
            try:
                # Find the source in S3
                sources = analyzer.discover_s3_data_sources(organization_id)
                source_info = next((s for s in sources if s.name == source_name), None)
                
                if not source_info:
                    continue
                
                # Get dataset preview for analysis
                preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=sample_size)
                
                # Create temporary CSV file for relationship analysis
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                    # Write headers
                    temp_file.write(','.join(preview.column_headers) + '\n')
                    
                    # Write data rows
                    for row in preview.data_rows:
                        # Ensure all rows have the same number of columns
                        padded_row = row + [''] * (len(preview.column_headers) - len(row))
                        row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell else '' for cell in padded_row])
                        temp_file.write(row_str + '\n')
                    
                    # Add to list of temporary files with dataset info
                    temp_files.append({
                        'path': temp_file.name,
                        'dataset_name': dataset_name,
                        'source_name': source_name
                    })
            
            except Exception as dataset_error:
                logger.warning(f"Auto-discovery: Error processing dataset {dataset_name} from {source_name}: {dataset_error}")
                continue
        
        if not temp_files:
            return {'error': 'Could not process any datasets for discovery'}
        
        # Run relationship discovery across datasets
        relationship_service = RelationshipDiscoveryService()
        dataset_paths = [temp_file['path'] for temp_file in temp_files]
        
        analysis_results = relationship_service.compare_datasets_relationships(dataset_paths, sample_size)
        
        # Format results for UI display
        cross_relationships = analysis_results.get('cross_dataset_relationships', [])
        
        # Format for visualization
        formatted_relationships = []
        for rel in cross_relationships:
            # Extract dataset and column names
            source_parts = rel['source_column'].split('.')
            target_parts = rel['target_column'].split('.')
            
            source_dataset = source_parts[0]
            source_column = '.'.join(source_parts[1:])
            target_dataset = target_parts[0]
            target_column = '.'.join(target_parts[1:])
            
            formatted_rel = {
                'source_dataset': source_dataset,
                'source_column': source_column,
                'target_dataset': target_dataset,
                'target_column': target_column,
                'relationship_type': rel['relationship_type'],
                'confidence_score': rel['confidence_score'],
                'relationship_description': rel.get('relationship_description', ''),
                'sample_values': rel.get('sample_values', [])
            }
            
            formatted_relationships.append(formatted_rel)
        
        return {
            'relationships': formatted_relationships,
            'total_relationships': len(formatted_relationships),
            'datasets_analyzed': len(temp_files)
        }
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file['path'])
            except Exception:
                pass



def run_relationship_discovery(request):
    """
    AJAX endpoint to run automated relationship discovery across selected datasets.
    Supports both manual selection and "analyze all" modes.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        data = json.loads(request.body)
        selected_datasets = data.get('datasets', [])
        organization_id = data.get('organization_id') or get_organization_id_from_request(request)
        sample_size = int(data.get('sample_size', 500))
        analyze_all = data.get('analyze_all', 'false').lower() == 'true'
        
        logger.info(f"RUN DISCOVERY: analyze_all={analyze_all}, manual_datasets={len(selected_datasets)}, org={organization_id}")
        
        # Handle "Analyze All" mode
        if analyze_all:
            logger.info("RUN DISCOVERY: Running in 'analyze all' mode")
            try:
                analyzer = S3DirectDataAnalyzer()
                sources = analyzer.discover_s3_data_sources(organization_id)
                
                # Get all datasets from all sources
                all_datasets = []
                for source in sources:
                    try:
                        dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                        for dataset_name in dataset_names:
                            # Add basic dataset info for analysis
                            all_datasets.append({
                                'name': dataset_name,
                                'source_name': source.name
                            })
                    except Exception as source_error:
                        logger.warning(f"RUN DISCOVERY: Error processing source {source.name}: {source_error}")
                        continue
                
                # Limit to reasonable number for performance (first 10 datasets)
                selected_datasets = all_datasets[:10]
                logger.info(f"RUN DISCOVERY: Analyze all mode selected {len(selected_datasets)} datasets from {len(all_datasets)} total")
                
            except Exception as all_error:
                logger.error(f"RUN DISCOVERY: Error in analyze all mode: {all_error}")
                return JsonResponse({'error': f'Error discovering all datasets: {str(all_error)}'}, status=500)
        
        # Validate we have datasets to analyze
        if not selected_datasets:
            return JsonResponse({'error': 'No datasets available for analysis'}, status=400)
        
        # Create temporary CSV files for analysis
        analyzer = S3DirectDataAnalyzer()
        temp_files = []
        
        for dataset_info in selected_datasets:
            source_name = dataset_info.get('source_name')
            dataset_name = dataset_info.get('name')
            
            if not source_name or not dataset_name:
                continue
            
            try:
                # Find the source in S3
                sources = analyzer.discover_s3_data_sources(organization_id)
                source_info = next((s for s in sources if s.name == source_name), None)
                
                if not source_info:
                    logger.warning(f"RUN DISCOVERY: Source '{source_name}' not found")
                    continue
                
                # Get dataset preview for analysis
                preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=sample_size)
                
                # Create temporary CSV file for relationship analysis
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                    # Write headers
                    temp_file.write(','.join(preview.column_headers) + '\n')
                    
                    # Write data rows
                    for row in preview.data_rows:
                        # Ensure all rows have the same number of columns
                        padded_row = row + [''] * (len(preview.column_headers) - len(row))
                        row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell else '' for cell in padded_row])
                        temp_file.write(row_str + '\n')
                    
                    # Add to list of temporary files with dataset info
                    temp_files.append({
                        'path': temp_file.name,
                        'dataset_name': dataset_name,
                        'source_name': source_name
                    })
                    
                    logger.info(f"RUN DISCOVERY: Created temp file for {dataset_name} from {source_name}")
            
            except Exception as dataset_error:
                logger.warning(f"RUN DISCOVERY: Error processing dataset {dataset_name} from {source_name}: {dataset_error}")
                continue
        
        if not temp_files:
            return JsonResponse({'error': 'Could not process any of the selected datasets'}, status=400)
        
        try:
            # Run relationship discovery across datasets  
            relationship_service = RelationshipDiscoveryService()
            dataset_paths = [temp_file['path'] for temp_file in temp_files]
            
            logger.info(f"RUN DISCOVERY: Running relationship discovery on {len(dataset_paths)} datasets")
            analysis_results = relationship_service.compare_datasets_relationships(dataset_paths, sample_size)
            
            # Create a lookup map from path to dataset name
            dataset_name_lookup = {temp_file['path']: temp_file['dataset_name'] for temp_file in temp_files}
            source_name_lookup = {temp_file['path']: temp_file['source_name'] for temp_file in temp_files}
            
            # Format results for UI display - focus on cross-dataset relationships
            cross_relationships = analysis_results.get('cross_dataset_relationships', [])
            
            # Format for visualization
            formatted_relationships = []
            for rel in cross_relationships:
                # Extract dataset and column names
                source_parts = rel['source_column'].split('.')
                target_parts = rel['target_column'].split('.')
                
                source_dataset = source_parts[0]
                source_column = '.'.join(source_parts[1:])
                target_dataset = target_parts[0]
                target_column = '.'.join(target_parts[1:])
                
                # Format for visualization
                formatted_rel = {
                    'source_dataset': source_dataset,
                    'source_column': source_column,
                    'target_dataset': target_dataset,
                    'target_column': target_column,
                    'relationship_type': rel['relationship_type'],
                    'confidence': rel['confidence'],
                    'evidence': rel.get('evidence', {}),
                    'source': {
                        'dataset': source_dataset,
                        'source_name': next((source_name_lookup.get(path) for path, name in dataset_name_lookup.items() if name == source_dataset), ""),
                    },
                    'target': {
                        'dataset': target_dataset,
                        'source_name': next((source_name_lookup.get(path) for path, name in dataset_name_lookup.items() if name == target_dataset), ""),
                    }
                }
                
                formatted_relationships.append(formatted_rel)
            
            # Filter to only reasonably confident relationships
            confident_relationships = [r for r in formatted_relationships if r['confidence'] >= 0.3]
            
            # Store results in cache
            cache_key = f"discovery_results_{organization_id}"
            cache.set(cache_key, {
                'relationships': formatted_relationships,
                'confident_relationships': confident_relationships,
                'analysis_timestamp': analysis_results.get('analysis_timestamp'),
                'total_datasets': len(dataset_paths),
                'sample_size': sample_size
            }, timeout=60*60*24)  # 24 hours
            
            # Return partial template for HTMX or JSON for regular requests
            if request.headers.get('HX-Request'):
                return render(request, 'partials/relationship_discovery_results.html', {
                    'relationships': confident_relationships[:20],  # Limit initial response size
                    'total_relationships': len(formatted_relationships),
                    'confident_relationships': len(confident_relationships),
                    'total_datasets': len(dataset_paths),
                    'organization_id': organization_id,
                    'analysis_timestamp': analysis_results.get('analysis_timestamp')
                })
            else:
                return JsonResponse({
                    'success': True,
                    'relationships': confident_relationships[:20],  # Limit initial response size
                    'total_relationships': len(formatted_relationships),
                    'confident_relationships': len(confident_relationships),
                    'analysis_timestamp': analysis_results.get('analysis_timestamp')
                })
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file['path'])
                except Exception as cleanup_error:
                    logger.warning(f"RUN DISCOVERY: Could not clean up temp file: {cleanup_error}")
        
    except Exception as e:
        logger.error(f"RUN DISCOVERY: Error in relationship discovery: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def get_discovery_results(request):
    """
    AJAX endpoint to retrieve the results of a previous relationship discovery run.
    """
    organization_id = request.GET.get('organization_id') or get_organization_id_from_request(request)
    include_all = request.GET.get('include_all', 'false').lower() == 'true'
    
    logger.info(f"GET DISCOVERY: Retrieving relationship discovery results for org={organization_id}")
    
    try:
        # Get results from cache
        cache_key = f"discovery_results_{organization_id}"
        results = cache.get(cache_key, {})
        
        if not results:
            return JsonResponse({'error': 'No discovery results found. Please run a new analysis.'}, status=404)
        
        # Return either all relationships or just confident ones
        if include_all:
            relationships = results.get('relationships', [])
        else:
            relationships = results.get('confident_relationships', [])
        
        # Return partial template for HTMX or JSON for regular requests
        if request.headers.get('HX-Request'):
            # Use relationships list partial for toggle updates
            return render(request, 'partials/relationships_list.html', {
                'relationships': relationships,
                'organization_id': organization_id
            })
        else:
            return JsonResponse({
                'relationships': relationships,
                'total_relationships': len(results.get('relationships', [])),
                'confident_relationships': len(results.get('confident_relationships', [])),
                'analysis_timestamp': results.get('analysis_timestamp'),
                'sample_size': results.get('sample_size', 500),
                'total_datasets': results.get('total_datasets', 0)
            })
        
    except Exception as e:
        logger.error(f"GET DISCOVERY: Error retrieving discovery results: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def get_loaded_datasets(request):
    """
    AJAX endpoint to get the datasets currently loaded in the left panel.
    This checks what datasets have been loaded/opened by the user in the current session.
    """
    organization_id = request.GET.get('organization_id') or get_organization_id_from_request(request)
    
    logger.info(f"GET LOADED DATASETS: Retrieving loaded datasets for org={organization_id}")
    
    if not organization_id or organization_id == 'default-org':
        return JsonResponse({'error': 'Organization parameter required'}, status=400)
    
    try:
        # Get loaded datasets from session/cache (based on what's been loaded in left panel)
        # We'll check for recently accessed datasets from the cache keys
        loaded_datasets = []
        
        analyzer = S3DirectDataAnalyzer()
        
        # Strategy 1: Check for dataset cards that have been loaded recently
        # Look for cache keys that indicate dataset loading activity
        dataset_cache_pattern = f"dataset_card_{organization_id}_*"
        
        # Strategy 2: Since we don't have direct session tracking, 
        # we'll provide a way to track loaded datasets via cache
        loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
        cached_loaded_datasets = cache.get(loaded_datasets_cache_key, [])
        
        if cached_loaded_datasets:
            logger.info(f"GET LOADED DATASETS: Found {len(cached_loaded_datasets)} cached loaded datasets")
            return JsonResponse({
                'success': True,
                'datasets': cached_loaded_datasets,
                'count': len(cached_loaded_datasets),
                'source': 'cache'
            })
        
        # If no cached data, return empty list with instruction
        logger.info("GET LOADED DATASETS: No loaded datasets found in cache")
        return JsonResponse({
            'success': True,
            'datasets': [],
            'count': 0,
            'message': 'No datasets currently loaded. Load datasets in the left panel first.',
            'source': 'empty'
        })
        
    except Exception as e:
        logger.error(f"GET LOADED DATASETS: Error retrieving loaded datasets: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def track_loaded_dataset(request):
    """
    AJAX endpoint to track when a dataset is loaded in the left panel.
    This should be called whenever a dataset card is opened/viewed.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        data = json.loads(request.body)
        organization_id = data.get('organization_id') or get_organization_id_from_request(request)
        dataset_name = data.get('dataset_name')
        source_name = data.get('source_name')
        columns = data.get('columns', [])
        
        logger.info(f"TRACK LOADED DATASET: Tracking {dataset_name} from {source_name} for org={organization_id}")
        
        if not dataset_name or not source_name:
            return JsonResponse({'error': 'Missing dataset_name or source_name'}, status=400)
        
        # Get current loaded datasets from cache
        loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
        loaded_datasets = cache.get(loaded_datasets_cache_key, [])
        
        # Create dataset info object
        dataset_info = {
            'name': dataset_name,
            'source_name': source_name,
            'columns': columns,
            'loaded_at': datetime.now().isoformat(),  # Track when it was loaded
        }
        
        # Remove if already exists (to update timestamp)
        loaded_datasets = [d for d in loaded_datasets if not (d['name'] == dataset_name and d['source_name'] == source_name)]
        
        # Add to beginning of list (most recently loaded first)
        loaded_datasets.insert(0, dataset_info)
        
        # Keep only last 10 loaded datasets to avoid cache bloat
        loaded_datasets = loaded_datasets[:10]
        
        # Save back to cache
        cache.set(loaded_datasets_cache_key, loaded_datasets, timeout=60*60*24)  # 24 hours
        
        return JsonResponse({
            'success': True,
            'message': f'Tracked loading of {dataset_name}',
            'total_loaded': len(loaded_datasets)
        })
        
    except Exception as e:
        logger.error(f"TRACK LOADED DATASET: Error tracking loaded dataset: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)




def add_column_to_workspace(request):
    """
    HTMX endpoint to add a column to the relationship building workspace.
    Uses session storage as single source of truth - no cache dependency.
    """
    logger.info(f"ADD_COLUMN: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"ADD_COLUMN: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("ADD_COLUMN: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"ADD COLUMN: {column_id} for org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Missing column_id'}, status=400)
        
        # Session-based workspace storage (single source of truth)
        workspace_key = f"workspace_columns_{organization_id}"
        workspace_columns = request.session.get(workspace_key, [])
        
        # Parse column info from ID (format: dataset_source_column) - needed for both cases
        parts = column_id.split('_')
        logger.info(f"ADD COLUMN: Parsing column_id {column_id} into parts: {parts}")
        
        if len(parts) < 3:
            logger.error(f"ADD COLUMN: Invalid column_id format - expected at least 3 parts, got {len(parts)}: {parts}")
            return JsonResponse({'error': 'Invalid column_id format'}, status=400)
        
        # Extract column name (last part)
        column_name = parts[-1]
        logger.info(f"ADD COLUMN: Extracted column_name: {column_name}")
        
        # Get dataset information from request data (no cache dependency!)
        datasets_json = request.POST.get('datasets', '[]')
        try:
            available_datasets = json.loads(datasets_json) if datasets_json != '[]' else []
            logger.info(f"ADD COLUMN: Found {len(available_datasets)} datasets from request data")
        except json.JSONDecodeError as e:
            logger.error(f"ADD COLUMN: Failed to parse datasets JSON: {e}")
            return JsonResponse({'error': 'Invalid datasets data in request'}, status=400)
        
        # Debug: log all available datasets
        for i, dataset in enumerate(available_datasets):
            cols = dataset.get('preview', {}).get('colHeaders', [])
            logger.info(f"ADD COLUMN: Dataset[{i}]: name='{dataset.get('name')}', source='{dataset.get('source')}', columns={len(cols)}")
        
        # Find the dataset and source for this column
        dataset_name = None
        source_name = None
        for dataset in available_datasets:
            dataset_cols = dataset.get('preview', {}).get('colHeaders', [])
            logger.info(f"ADD COLUMN: Checking dataset '{dataset.get('name')}' with {len(dataset_cols)} columns")
            
            for col in dataset_cols:
                # Reconstruct the column ID to match
                test_id = f"{dataset.get('name')}_{dataset.get('source')}_{col}"
                logger.debug(f"ADD COLUMN: Comparing test_id '{test_id}' with target '{column_id}'")
                
                if test_id == column_id:
                    dataset_name = dataset.get('name')
                    source_name = dataset.get('source')
                    column_name = col
                    logger.info(f"ADD COLUMN: ✅ Found match! dataset='{dataset_name}', source='{source_name}', column='{column_name}'")
                    break
            if dataset_name:
                break
        
        if not dataset_name:
            logger.error(f"ADD COLUMN: ❌ Could not find dataset info for column '{column_id}'")
            logger.error(f"ADD COLUMN: Available datasets: {[d.get('name') for d in available_datasets]}")
            logger.error(f"ADD COLUMN: Searched for pattern: dataset_source_{column_name}")
            return JsonResponse({'error': f'Column not found in request datasets: {column_id}'}, status=400)

        # Check if column already exists
        if any(col.get('id') == column_id for col in workspace_columns):
            logger.info(f"ADD COLUMN: Column {column_id} already in workspace")
        else:
            # Add column to workspace
            new_column = {
                'id': column_id,
                'name': column_name,
                'dataset': dataset_name,
                'source': source_name,
                'is_anchor': False,
                'is_fk': False,
                'is_multi_value': False,
            }
            
            workspace_columns.append(new_column)
            request.session[workspace_key] = workspace_columns
            request.session.modified = True
            
            logger.info(f"ADD COLUMN: Added {column_id} to workspace, total columns: {len(workspace_columns)}")
        
        # Get datasets from request data (we already parsed this above)
        try:
            datasets = available_datasets  # Use the datasets we already parsed
        except NameError:
            # Fallback if we somehow didn't parse it above
            datasets_json = request.POST.get('datasets', '[]')
            try:
                datasets = json.loads(datasets_json)
            except json.JSONDecodeError:
                datasets = []
                # If no datasets in request, get from state as fallback
                state = get_organization_state(request, organization_id)
                datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'
        
        # Ensure we have datasets_json for the template
        if 'datasets_json' not in locals():
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)

        # Return only the specific dataset section for HTMX targeting
        # Find the dataset object for the added column - try HTMX datasets first, then state
        target_dataset = None
        for dataset in datasets:
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        # If not found in HTMX datasets, try state as fallback
        if not target_dataset:
            state = get_organization_state(request, organization_id)
            for dataset in state.get('all_datasets', []):
                if dataset.get('name') == dataset_name:
                    target_dataset = dataset
                    break
        
        if not target_dataset:
            logger.error(f"ADD COLUMN: Could not find dataset {dataset_name} in HTMX datasets or state")
            return JsonResponse({'error': f'Dataset {dataset_name} not found'}, status=400)
        
        # Get the active datasets from the organization state (for the workspace container)
        state = get_organization_state(request, organization_id)
        active_datasets = state.get('active_datasets', [])
        
        # Calculate selected columns for this specific dataset
        dataset_selected_columns = [col['name'] for col in workspace_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': workspace_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Render updated column badges with new selection state
        column_badges_html = render_to_string('partials/column_badges.html', {
            'dataset': target_dataset,
            'dataset_selected_columns': dataset_selected_columns,
            'datasets_json': datasets_json,
            'selected_columns': workspace_columns,
            'organization_id': organization_id,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Return both updates using HTMX out-of-band swaps
        from django.utils.text import slugify
        dataset_slug = slugify(target_dataset['name'])
        response_html = f"""
        {dataset_section_html}
        <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
            {column_badges_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"ADD COLUMN: Error adding column to workspace: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)




def remove_column_from_workspace(request):
    """
    HTMX endpoint to remove a column from the relationship builder workspace.
    Uses session storage as single source of truth - no cache dependency.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"REMOVE COLUMN: {column_id} for org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Missing column_id'}, status=400)
        
        # Get current workspace from session (single source of truth)
        workspace_columns = get_workspace_columns(request, organization_id)
        
        # Find the dataset of the column being removed
        removed_column = next((col for col in workspace_columns if col.get('id') == column_id), None)
        if not removed_column:
            return JsonResponse({'error': 'Column not found in workspace'}, status=404)
        
        dataset_name = removed_column.get('dataset')
        
        # Remove column by ID
        updated_columns = [col for col in workspace_columns if col.get('id') != column_id]
        
        # Update workspace in session
        update_workspace_columns(request, organization_id, updated_columns)
        
        logger.info(f"REMOVE COLUMN: Removed {column_id} from dataset {dataset_name}, workspace now has {len(updated_columns)} columns")
        
        # Get datasets from request data (passed via HTMX)
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Find the target dataset object - look in HTMX datasets first, then state
        target_dataset = None
        
        # First, try to find in the datasets passed via HTMX (from current page)
        for dataset in datasets:
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        # If not found, try state as fallback
        if not target_dataset:
            state = get_organization_state(request, organization_id)
            for dataset in state.get('all_datasets', []):
                if dataset.get('name') == dataset_name:
                    target_dataset = dataset
                    break
        
        # We can update column badges if we found the dataset in either location
        update_column_badges = target_dataset is not None
        
        if not target_dataset:
            # Create a minimal dataset object just for workspace rendering
            target_dataset = {
                'name': dataset_name,
                'source': removed_column.get('source', 'unknown') if removed_column else 'unknown',
                'preview': {
                    'colHeaders': []  # Empty since we don't have the real dataset
                }
            }
            logger.warning(f"REMOVE COLUMN: Dataset {dataset_name} not found in HTMX datasets or state, will not update column badges")

        # Debug logging for workspace state
        logger.info(f"REMOVE COLUMN: After removal, workspace columns:")
        for i, col in enumerate(updated_columns):
            logger.info(f"  [{i}] {col.get('id')} | {col.get('dataset')}.{col.get('name')}")
        
        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Calculate selected columns for this specific dataset
        dataset_selected_columns = [col['name'] for col in updated_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': updated_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Only update column badges if we have the real dataset with all columns
        if update_column_badges:
            try:
                column_badges_html = render_to_string('partials/column_badges.html', {
                    'dataset': target_dataset,
                    'dataset_selected_columns': dataset_selected_columns,
                    'datasets_json': datasets_json,
                    'selected_columns': updated_columns,
                    'organization_id': organization_id,
                    'csrf_token': csrf_token,
                }, request=request)
                
                # Return both updates using HTMX out-of-band swaps
                from django.utils.text import slugify
                dataset_slug = slugify(target_dataset['name'])
                
                response_html = f"""
                {dataset_section_html}
                <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
                    {column_badges_html}
                </div>
                """
                
                logger.info(f"REMOVE COLUMN: Updated both workspace and column badges for {dataset_name}")
                return HttpResponse(response_html)
                
            except Exception as template_error:
                logger.error(f"REMOVE COLUMN: Error rendering column badges: {template_error}", exc_info=True)
                # Fall through to return just workspace section
        else:
            logger.info(f"REMOVE COLUMN: Dataset not available, only updating workspace section")
        
        # Return only workspace section if dataset not available or badge rendering failed
        return HttpResponse(dataset_section_html)
        
    except Exception as e:
        logger.error(f"REMOVE COLUMN: Error removing column: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)



def create_mapping(request):
    """
    HTMX endpoint to create a new mapping definition.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        
        # Get form data
        mapping_name = request.POST.get('mapping_name', '').strip()
        mapping_type = request.POST.get('mapping_type')
        source_dataset = request.POST.get('source_dataset', '').strip()
        
        logger.info(f"CREATE MAPPING: {mapping_name} ({mapping_type}) for dataset {source_dataset}, org={organization_id}")
        
        if not all([mapping_name, mapping_type, source_dataset]):
            return JsonResponse({'error': 'Missing required fields: name, type, and source dataset'}, status=400)
        
        if mapping_type not in [choice[0] for choice in MappingType.choices]:
            return JsonResponse({'error': f'Invalid mapping type: {mapping_type}'}, status=400)
        
        # Build mapping configuration based on type
        mapping_config = {}
        
        if mapping_type == MappingType.ENTITY:
            # Entity mapping configuration
            subject_column = request.POST.get('subject_column', '').strip()
            predicate_mappings_json = request.POST.get('predicate_mappings', '{}')
            
            if not subject_column:
                return JsonResponse({'error': 'Entity mapping requires subject column'}, status=400)
            
            try:
                predicate_mappings = json.loads(predicate_mappings_json)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid predicate mappings JSON'}, status=400)
            
            mapping_config = {
                'subject_column': subject_column,
                'predicate_mappings': predicate_mappings,
                'base_uri_template': f'http://arkumu.org/data/{organization_id}/{source_dataset}/entities/{{subject}}'
            }
            
        elif mapping_type == MappingType.LOOKUP:
            # Lookup mapping configuration
            source_column = request.POST.get('source_column', '').strip()
            target_column = request.POST.get('target_column', '').strip()
            source_dataset_ref = request.POST.get('source_dataset_ref', '').strip()
            target_dataset_ref = request.POST.get('target_dataset_ref', '').strip()
            relationship_property = request.POST.get('relationship_property', '').strip()
            
            if not all([source_column, target_column, source_dataset_ref, target_dataset_ref, relationship_property]):
                return JsonResponse({'error': 'Lookup mapping requires all lookup configuration fields'}, status=400)
            
            mapping_config = {
                'lookup_config': {
                    'source_column': source_column,
                    'target_column': target_column,
                    'source_dataset': source_dataset_ref,
                    'target_dataset': target_dataset_ref,
                    'relationship_property': relationship_property
                }
            }
        
        # Create the mapping
        mapping = Mapping.objects.create(
            name=mapping_name,
            mapping_type=mapping_type,
            organization_id=organization_id,
            source_dataset=source_dataset,
            mapping_config=mapping_config,
            validation_status='draft',
            created_by=f'user_{request.user.id}' if request.user.is_authenticated else 'anonymous'
        )
        
        logger.info(f"CREATE MAPPING: Created mapping {mapping.id} - {mapping_name}")
        
        # Get updated mappings for template
        updated_mappings = Mapping.objects.filter(
            organization_id=organization_id
        ).order_by('-created_at')[:50]
        
        mappings_data = []
        for m in updated_mappings:
            mapping_info = {
                'id': str(m.id),
                'name': m.name,
                'mapping_type': m.mapping_type,
                'mapping_type_display': m.get_mapping_type_display(),
                'source_dataset': m.source_dataset,
                'validation_status': m.validation_status,
                'created_at': m.created_at.isoformat(),
                'config': m.mapping_config,
                'execution_stats': m.execution_stats
            }
            mappings_data.append(mapping_info)
        
        # Return updated mappings partial
        return render(request, 'partials/mappings_section.html', {
            'mappings': mappings_data,
            'organization_id': organization_id,
            'message': f'Created {mapping.get_mapping_type_display()}: {mapping_name}'
        })
        
    except Exception as e:
        logger.error(f"CREATE MAPPING: Error creating mapping: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def preview_mapping(request):
    """
    HTMX endpoint to generate a JSON preview of the mapping configuration.
    Shows what the mapping would look like before creation.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        
        # Get form data
        mapping_name = request.POST.get('mapping_name', '').strip()
        anchor_column = request.POST.get('anchor_column', '').strip()
        fk_columns = request.POST.getlist('fk_columns')
        multi_value_columns = request.POST.getlist('multi_value_columns')
        
        logger.info(f"PREVIEW MAPPING: {mapping_name} with anchor={anchor_column}, fk={fk_columns}, multi={multi_value_columns}")
        
        # Get current workspace from cache for context
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        selected_columns = workspace.get('columns', [])
        
        # Get current dataset name from selected columns
        current_dataset = selected_columns[0].get('dataset') if selected_columns else 'current_dataset'
        
        # Build preview mapping structure
        preview_mapping = {
            "mapping_name": mapping_name or "Untitled Mapping",
            "organization_id": organization_id,
            "created_at": datetime.now().isoformat(),
            "column_configuration": {
                "anchor_column": {
                    "name": anchor_column,
                    "role": "entity_creator",
                    "description": "Creates unique entities/resources from this column's values"
                } if anchor_column else None,
                "foreign_key_columns": [],
                "multi_value_columns": [],
                "regular_columns": []
            },
            "relationship_mappings": [],
            "import_strategy": {
                "dependency_order": [],
                "validation_rules": []
            }
        }
        
        # Process FK columns and their targets
        for fk_col in fk_columns:
            fk_direction = request.POST.get(f'fk_direction_{fk_col}', 'outbound')
            fk_target_dataset = request.POST.get(f'fk_target_dataset_{fk_col}', '')
            fk_target_column = request.POST.get(f'fk_target_column_{fk_col}', '')
            
            if fk_direction == 'outbound':
                description = f"This column '{fk_col}' points TO {fk_target_dataset}.{fk_target_column}" if fk_target_dataset and fk_target_column else "Target not specified - this column will reference another dataset"
                role = "source_foreign_key"
            else:  # inbound
                description = f"Another dataset's column points TO this column '{fk_col}'" if fk_target_dataset and fk_target_column else "Source not specified - another dataset will reference this column"
                role = "target_foreign_key"
            
            fk_config = {
                "name": fk_col,
                "role": role,
                "direction": fk_direction,
                "target_dataset": fk_target_dataset,
                "target_column": fk_target_column,
                "description": description
            }
            preview_mapping["column_configuration"]["foreign_key_columns"].append(fk_config)
            
            # Add relationship mapping
            if fk_target_dataset and fk_target_column:
                if fk_direction == 'outbound':
                    relationship = {
                        "source_column": fk_col,
                        "source_dataset": current_dataset,
                        "target_dataset": fk_target_dataset,
                        "target_column": fk_target_column,
                        "relationship_type": "outbound_reference",
                        "direction": "source_to_target",
                        "dependency": f"Requires {fk_target_dataset} to be imported first",
                        "description": f"{current_dataset}.{fk_col} → {fk_target_dataset}.{fk_target_column}"
                    }
                    # Add to dependency order - target must be imported first
                    if fk_target_dataset not in preview_mapping["import_strategy"]["dependency_order"]:
                        preview_mapping["import_strategy"]["dependency_order"].append(fk_target_dataset)
                else:  # inbound
                    relationship = {
                        "source_column": fk_col,
                        "source_dataset": current_dataset,
                        "target_dataset": fk_target_dataset,
                        "target_column": fk_target_column,
                        "relationship_type": "inbound_reference",
                        "direction": "target_to_source",
                        "dependency": f"This dataset must be imported before {fk_target_dataset}",
                        "description": f"{fk_target_dataset}.{fk_target_column} → {current_dataset}.{fk_col}"
                    }
                    # For inbound, current dataset should be imported first
                    # Don't add target to dependency order as it depends on us
                
                preview_mapping["relationship_mappings"].append(relationship)
        
        # Process multi-value columns
        for mv_col in multi_value_columns:
            mv_config = {
                "name": mv_col,
                "role": "multi_value",
                "split_strategy": "comma_separated",
                "description": "Will be split into multiple values/relationships"
            }
            preview_mapping["column_configuration"]["multi_value_columns"].append(mv_config)
        
        # Process regular columns (not anchor, FK, or multi-value)
        for col in selected_columns:
            col_name = col.get('name')
            if (col_name != anchor_column and 
                col_name not in fk_columns and 
                col_name not in multi_value_columns):
                
                regular_config = {
                    "name": col_name,
                    "role": "property",
                    "description": "Will be added as a property of the entity"
                }
                preview_mapping["column_configuration"]["regular_columns"].append(regular_config)
        
        # Add validation rules
        if anchor_column:
            preview_mapping["import_strategy"]["validation_rules"].append(
                f"Anchor column '{anchor_column}' must have unique values"
            )
        
        for fk_config in preview_mapping["column_configuration"]["foreign_key_columns"]:
            if fk_config["target_dataset"] and fk_config["target_column"]:
                preview_mapping["import_strategy"]["validation_rules"].append(
                    f"FK column '{fk_config['name']}' values must exist in {fk_config['target_dataset']}.{fk_config['target_column']}"
                )
        
        # Add current dataset to end of dependency order
        current_dataset = selected_columns[0].get('dataset') if selected_columns else 'current_dataset'
        preview_mapping["import_strategy"]["dependency_order"].append(current_dataset)
        
        # Render the preview template
        return render(request, 'partials/mapping_preview.html', {
            'preview_mapping': preview_mapping,
            'preview_json': json.dumps(preview_mapping, indent=2),
            'organization_id': organization_id,
        })
        
    except Exception as e:
        logger.error(f"PREVIEW MAPPING: Error generating preview: {e}", exc_info=True)
        return render(request, 'partials/mapping_preview.html', {
            'error': str(e),
            'organization_id': organization_id,
        })


def clear_workspace(request):
    """
    HTMX endpoint to clear all columns from the relationship builder workspace.
    Syncs selection state across all templates.
    """
    logger.info(f"CLEAR_WORKSPACE: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"CLEAR_WORKSPACE: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("CLEAR_WORKSPACE: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"CLEAR WORKSPACE: Clearing workspace for org={organization_id}")
        
        # Clear workspace cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        cache.delete(workspace_cache_key)
        
        # Also clear selected datasets from session
        session_key = f"selected_datasets_{organization_id}"
        request.session[session_key] = []
        
        logger.info("CLEAR WORKSPACE: Workspace and dataset selection cleared")
        
        # Get updated state to render all partials with empty state
        state = get_organization_state(request, organization_id)
        
        # Generate workspace HTML
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': [],
            'anchor_column': None,
            'organization_id': organization_id,
        }, request=request)
        
        # Generate updated dataset badges (all unselected)
        badges_html = render_to_string('partials/dataset_badges.html', {
            'datasets': state['all_datasets'],
            'selected_datasets': [],
            'organization_id': organization_id,
            'csrf_token': request.META.get('CSRF_COOKIE')
        }, request=request)
        
        # Generate updated relationship builder (no active datasets)
        relationship_builder_html = render_to_string('partials/relationship_builder.html', {
            'datasets': state['all_datasets'],
            'organization_id': organization_id,
            'selected_columns': [],
            'active_datasets': [],
            'mappings': [],
            'anchor_column': None
        }, request=request)
        
        # HTMX response with main target + out-of-band updates to clear all selections
        response_html = f"""
        {workspace_html}
        <div hx-swap-oob="innerHTML:#dataset-badges">
            {badges_html}
        </div>
        <div hx-swap-oob="innerHTML:#relationship-builder">
            {relationship_builder_html}
        </div>
        
        <script hx-swap-oob="true" type="text/hyperscript">
            -- Clear all column selections across the page
            repeat for element in <.column-badge/>
                remove .selected from element
                add .badge-outline to element
            end
            repeat for element in <.column-header/>
                remove .selected from element
            end
        </script>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"CLEAR WORKSPACE: Error clearing workspace: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def deselect_all_columns(request):
    """
    HTMX endpoint to deselect all columns from workspace without affecting dataset badges.
    Uses session storage as single source of truth - no cache dependency.
    """
    logger.info(f"DESELECT_ALL_COLUMNS: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"DESELECT_ALL_COLUMNS: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("DESELECT_ALL_COLUMNS: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"DESELECT ALL COLUMNS: Clearing column selections for org={organization_id}")
        
        # Clear workspace from session (single source of truth)
        clear_workspace_columns(request, organization_id)
        
        logger.info("DESELECT ALL COLUMNS: Column selections cleared")
        
        # Get datasets from request if available
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json) if datasets_json != '[]' else []
        except json.JSONDecodeError:
            datasets = []
        
        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)

        # Generate updated workspace HTML with empty state
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': [],
            'anchor_column': None,
            'organization_id': organization_id,
            'datasets': datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Generate script to update column visual states across all dataset cards
        deselect_script = """
        <script hx-swap-oob="true" type="text/hyperscript">
            -- Deselect all column headers in all dataset cards
            repeat for element in <.column-header.selected/>
                remove .selected from element
                remove .bg-primary from element
                remove .text-primary-content from element
            end
            -- Deselect all column badges in all dataset cards  
            repeat for element in <.column-badge.selected/>
                remove .selected from element
                add .badge-outline to element
            end
        </script>
        """
        
        # Return workspace update with column deselection script
        response_html = f"{workspace_html}{deselect_script}"
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"DESELECT ALL COLUMNS: Error deselecting columns: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def clear_all_datasets(request):
    """
    HTMX endpoint to clear all selected datasets from active state.
    Keeps all datasets visible but unselected, clears left/right panes.
    """
    logger.info(f"CLEAR_ALL_DATASETS: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"CLEAR_ALL_DATASETS: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("CLEAR_ALL_DATASETS: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"CLEAR ALL DATASETS: Clearing all datasets for org={organization_id}")
        
        # Clear selected datasets from session
        session_key = f"selected_datasets_{organization_id}"
        request.session[session_key] = []
        
        # Clear workspace columns from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        if cache.get(workspace_cache_key):
            logger.info(f"CLEAR_ALL_DATASETS: Clearing workspace cache {workspace_cache_key}")
            cache.delete(workspace_cache_key)
        
        logger.info("CLEAR ALL DATASETS: Dataset selection and workspace cleared")
        
        # Try to get datasets from the form data (passed via hx-include) first
        datasets_json = request.POST.get('datasets', '[]')
        try:
            all_datasets = json.loads(datasets_json) if datasets_json != '[]' else []
            logger.info(f"CLEAR_ALL_DATASETS: Got {len(all_datasets)} datasets from form")
        except json.JSONDecodeError:
            logger.warning("CLEAR_ALL_DATASETS: Failed to parse datasets from form, falling back to state discovery")
            all_datasets = []
        
        # If no datasets from request, try to get from state (fallback)
        if not all_datasets:
            state = get_organization_state(request, organization_id)
            all_datasets = state['all_datasets']
            logger.info(f"CLEAR_ALL_DATASETS: Retrieved {len(all_datasets)} datasets from state")
        
        # Generate empty table content
        table_content_html = render_to_string('partials/table_empty_state.html', {
            'organization_id': organization_id,
        }, request=request)
        
        # Generate updated dataset badges (all unselected)
        badges_html = render_to_string('partials/dataset_badges.html', {
            'datasets': all_datasets,
            'selected_datasets': [],
            'organization_id': organization_id,
            'csrf_token': request.META.get('CSRF_COOKIE'),
            'datasets_json': json.dumps(all_datasets, cls=DjangoJSONEncoder) if all_datasets else '[]'
        }, request=request)
        
        # Generate updated relationship builder (no active datasets)
        relationship_builder_html = render_to_string('partials/relationship_builder.html', {
            'datasets': all_datasets,
            'organization_id': organization_id,
            'selected_columns': [],
            'active_datasets': [],
            'mappings': [],
            'anchor_column': None
        }, request=request)
        
        # HTMX response with badges as main target (since button targets #dataset-badges) + out-of-band updates
        response_html = f"""
        {badges_html}
        <div hx-swap-oob="innerHTML:#table-content">
            {table_content_html}
        </div>
        <div hx-swap-oob="innerHTML:#relationship-builder">
            {relationship_builder_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"CLEAR ALL DATASETS: Error clearing datasets: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def set_anchor_column(request):
    """
    HTMX endpoint to set/unset a column as the anchor column.
    Only one column can be the anchor at a time.
    """
    logger.info(f"SET_ANCHOR_COLUMN: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"SET_ANCHOR_COLUMN: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("SET_ANCHOR_COLUMN: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"SET ANCHOR COLUMN: {column_id} for org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Missing column_id'}, status=400)
        
        # Get current workspace from session (consistent with other functions)
        existing_columns = get_workspace_columns(request, organization_id)
        anchor_set = False
        dataset_name = None
        
        for col in existing_columns:
            if col.get('id') == column_id:
                # Toggle anchor status for this column
                col['is_anchor'] = not col.get('is_anchor', False)
                anchor_set = col['is_anchor']
                dataset_name = col.get('dataset')
                logger.info(f"SET ANCHOR: Column {column_id} anchor status: {anchor_set}")
            else:
                # Clear anchor status for all other columns (only one anchor allowed)
                if anchor_set:
                    col['is_anchor'] = False
        
        if not dataset_name:
            return JsonResponse({'error': 'Column not found in workspace'}, status=404)
        
        # Save back to session
        update_workspace_columns(request, organization_id, existing_columns)
        
        logger.info(f"SET ANCHOR: Updated workspace, anchor_set={anchor_set}")
        
        # Get datasets from request data (passed via HTMX)
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Find the target dataset object
        target_dataset = None
        state = get_organization_state(request, organization_id)
        for dataset in state.get('all_datasets', []):
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        if not target_dataset:
            return JsonResponse({'error': f'Dataset {dataset_name} not found'}, status=404)

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Calculate selected columns for this specific dataset
        dataset_selected_columns = [col['name'] for col in existing_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': existing_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Render updated column badges with new selection state
        column_badges_html = render_to_string('partials/column_badges.html', {
            'dataset': target_dataset,
            'dataset_selected_columns': dataset_selected_columns,
            'datasets_json': datasets_json,
            'selected_columns': existing_columns,
            'organization_id': organization_id,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Return both updates using HTMX out-of-band swaps
        from django.utils.text import slugify
        dataset_slug = slugify(target_dataset['name'])
        response_html = f"""
        {dataset_section_html}
        <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
            {column_badges_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"SET ANCHOR: Error setting anchor column: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def toggle_all_columns(request):
    """
    HTMX endpoint to toggle all columns from a dataset in/out of the workspace.
    More efficient than individual column selections.
    """
    logger.info("="*50)
    logger.info("TOGGLE_ALL_COLUMNS: ENDPOINT HIT!")
    logger.info(f"TOGGLE_ALL_COLUMNS: Method={request.method}")
    logger.info(f"TOGGLE_ALL_COLUMNS: Content-Type={request.content_type}")
    logger.info(f"TOGGLE_ALL_COLUMNS: Headers={dict(request.headers)}")
    logger.info(f"TOGGLE_ALL_COLUMNS: POST data: {dict(request.POST)}")
    logger.info(f"TOGGLE_ALL_COLUMNS: User: {request.user}")
    logger.info(f"TOGGLE_ALL_COLUMNS: Path: {request.path}")
    logger.info("="*50)
    
    if request.method != 'POST':
        logger.error("TOGGLE_ALL_COLUMNS: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        dataset_name = request.POST.get('dataset_name')
        source_name = request.POST.get('source_name')
        column_names_str = request.POST.get('column_names', '')
        organization_id = get_organization_id_from_request(request)
        
        column_names = [name.strip() for name in column_names_str.split(',') if name.strip()]
        
        logger.info(f"TOGGLE ALL COLUMNS: {len(column_names)} columns from {dataset_name}/{source_name} for org={organization_id}")
        
        if not all([dataset_name, source_name]) or not column_names:
            return JsonResponse({'error': 'Missing required parameters'}, status=400)
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        existing_columns = workspace.get('columns', [])
        
        # Check if any columns from this dataset are already in workspace
        dataset_columns_in_workspace = [
            col for col in existing_columns 
            if col.get('dataset_name') == dataset_name and col.get('source_name') == source_name
        ]
        
        if dataset_columns_in_workspace:
            # Remove all columns from this dataset (toggle off)
            existing_columns = [
                col for col in existing_columns 
                if not (col.get('dataset_name') == dataset_name and col.get('source_name') == source_name)
            ]
            action = 'removed_all'
            logger.info(f"TOGGLE ALL: Removed {len(dataset_columns_in_workspace)} columns from {dataset_name}")
        else:
            # Add all columns from this dataset (toggle on)
            for i, column_name in enumerate(column_names):
                column_info = {
                    'id': f"{dataset_name}_{source_name}_{column_name}".replace(' ', '_').replace('-', '_'),
                    'dataset': dataset_name,
                    'name': column_name,
                    'source': source_name,
                    'index': i,
                    'added_at': datetime.now().isoformat(),
                    'is_anchor': False,
                    'is_multi_value': False,  # Default multi-value status
                    # Internal fields for backend use
                    'dataset_name': dataset_name,
                    'source_name': source_name,
                    'column_name': column_name,
                    'column_index': i
                }
                existing_columns.append(column_info)
            
            action = 'added_all'
            logger.info(f"TOGGLE ALL: Added {len(column_names)} columns from {dataset_name}")
        
        # Keep only last 100 columns to avoid cache bloat while allowing larger datasets
        existing_columns = existing_columns[-100:]
        workspace['columns'] = existing_columns
        
        # Save back to cache
        cache.set(workspace_cache_key, workspace, timeout=60*60*24)  # 24 hours
        
        logger.info(f"TOGGLE ALL: {action}, workspace now has {len(workspace['columns'])} columns")
        
        # Get consolidated state and render workspace + dataset card updates
        state = get_organization_state(request, organization_id)
        
        # Get selected column names for this dataset to pass to template
        dataset_selected_columns = [col['column_name'] for col in state['selected_columns'] 
                                   if col.get('dataset_name') == dataset_name and col.get('source_name') == source_name]
        
        logger.info(f"TOGGLE ALL: Dataset {dataset_name} has {len(dataset_selected_columns)} selected columns: {dataset_selected_columns}")
        
        # Render the updated selected columns workspace
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': state['selected_columns'],
            'anchor_column': next((col for col in state['selected_columns'] if col.get('is_anchor')), None),
            'organization_id': organization_id,
            'datasets': state['all_datasets'],
            'active_datasets': state['active_datasets'],
            'datasets_json': json.dumps(state['all_datasets'], cls=DjangoJSONEncoder) if state['all_datasets'] else '[]',
            'csrf_token': request.META.get('CSRF_COOKIE')
        }, request=request)
        
        # Also render updated relationship builder to sync the Active Datasets section
        relationship_builder_html = render_to_string('partials/relationship_builder.html', {
            'datasets': state['all_datasets'],
            'organization_id': organization_id,
            'selected_columns': state['selected_columns'],
            'active_datasets': state['active_datasets'],
            'mappings': state.get('mappings', []),
            'anchor_column': next((col for col in state['selected_columns'] if col.get('is_anchor')), None)
        }, request=request)
        
        # Render updated column badges for this dataset
        try:
            analyzer = S3DirectDataAnalyzer()
            sources = analyzer.discover_s3_data_sources(organization_id)
            source_info = next((s for s in sources if s.name == source_name), None)
            
            if source_info:
                # Get dataset preview to re-render the column badges
                preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=10)
                
                dataset = {
                    'name': dataset_name,
                    'source': source_name,
                    'preview': {
                        'colHeaders': preview.column_headers,
                    }
                }
                
                # Render updated column badges with selection state
                column_badges_html = render_to_string('partials/column_badges.html', {
                    'dataset': dataset,
                    'organization_id': organization_id,
                    'datasets_json': json.dumps(state['all_datasets'], cls=DjangoJSONEncoder) if state['all_datasets'] else '[]',
                    'selected_columns': state['selected_columns'],
                    'dataset_selected_columns': dataset_selected_columns,  # Pass selected columns for this dataset
                    'csrf_token': request.META.get('CSRF_COOKIE')
                }, request=request)
                
                # Create slugified dataset name for the ID
                import re
                dataset_slug = re.sub(r'[^a-zA-Z0-9\-_]', '-', dataset_name.lower())
                
                # Return workspace + relationship builder + column badges updates
                response_html = f"""
                {workspace_html}
                <div hx-swap-oob="innerHTML:#relationship-builder">
                    {relationship_builder_html}
                </div>
                <div hx-swap-oob="innerHTML:#column-badges-{dataset_slug}">
                    {column_badges_html}
                </div>
                """
                
                logger.info(f"TOGGLE ALL: Rendering workspace + relationship builder + column badges update for {dataset_name}")
                return HttpResponse(response_html)
                
        except Exception as badges_error:
            logger.warning(f"TOGGLE ALL: Could not update column badges: {badges_error}")
        
        # Fallback: return workspace + relationship builder updates only
        response_html = f"""
        {workspace_html}
        <div hx-swap-oob="innerHTML:#relationship-builder">
            {relationship_builder_html}
        </div>
        """
        
        logger.info(f"TOGGLE ALL: Rendering workspace + relationship builder only with {len(state['selected_columns'])} selected columns")
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"TOGGLE ALL: Error toggling all columns: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def export_mappings(request):
    """
    Export saved column mappings as JSON for download.
    """
    try:
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"EXPORT MAPPINGS: Exporting mappings for org={organization_id}")
        
        # Get mappings from database
        db_mappings = Mapping.objects.filter(
            organization_id=organization_id,
            scope='multi_dataset'
        ).order_by('-created_at')
        
        mappings = [mapping.mapping_data for mapping in db_mappings]
        
        # Create export data
        export_data = {
            'organization_id': organization_id,
            'export_timestamp': json.loads(json.dumps(datetime.now(), default=str)),
            'total_mappings': len(mappings),
            'mappings': mappings
        }
        
        # Create JSON response for download
        response = JsonResponse(export_data, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="column_mappings_{organization_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
        
        logger.info(f"EXPORT MAPPINGS: Exported {len(mappings)} mappings")
        
        return response
        
    except Exception as e:
        logger.error(f"EXPORT MAPPINGS: Error exporting mappings: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def toggle_multi_value_column(request):
    """
    HTMX endpoint to toggle the multi-value status of a column.
    Multi-value columns will be split during mapping execution.
    """
    logger.info(f"TOGGLE_MULTI_VALUE: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"TOGGLE_MULTI_VALUE: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("TOGGLE_MULTI_VALUE: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"TOGGLE MULTI-VALUE: {column_id} for org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Missing column_id'}, status=400)
        
        # Get current workspace from session (single source of truth)
        workspace_columns = get_workspace_columns(request, organization_id)
        
        # Find the column and its dataset
        column_found = False
        dataset_name = None
        
        for col in workspace_columns:
            if col.get('id') == column_id:
                # Toggle multi-value status
                current_status = col.get('is_multi_value', False)
                col['is_multi_value'] = not current_status
                column_found = True
                dataset_name = col.get('dataset')
                logger.info(f"TOGGLE MULTI-VALUE: Column {column_id} multi-value status: {col['is_multi_value']}")
                break
        
        if not column_found:
            return JsonResponse({'error': 'Column not found in workspace'}, status=400)
        
        # Update workspace in session
        update_workspace_columns(request, organization_id, workspace_columns)
        
        logger.info(f"TOGGLE MULTI-VALUE: Updated workspace")
        
        # Get datasets from request data (passed via HTMX) or get from state
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Find the target dataset object
        target_dataset = None
        state = get_organization_state(request, organization_id)
        for dataset in state.get('all_datasets', []):
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        if not target_dataset:
            return JsonResponse({'error': f'Dataset {dataset_name} not found'}, status=404)

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Calculate selected columns for this specific dataset
        dataset_selected_columns = [col['name'] for col in workspace_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': workspace_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Render updated column badges with new selection state
        column_badges_html = render_to_string('partials/column_badges.html', {
            'dataset': target_dataset,
            'dataset_selected_columns': dataset_selected_columns,
            'datasets_json': datasets_json,
            'selected_columns': workspace_columns,
            'organization_id': organization_id,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Return both updates using HTMX out-of-band swaps
        from django.utils.text import slugify
        dataset_slug = slugify(target_dataset['name'])
        response_html = f"""
        {dataset_section_html}
        <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
            {column_badges_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"TOGGLE MULTI-VALUE: Error toggling multi-value status: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def filter_workspace(request):
    """
    HTMX endpoint to filter workspace columns by dataset.
    """
    try:
        organization_id = get_organization_id_from_request(request)
        filter_dataset = request.GET.get('filter_dataset', 'all')
        
        logger.info(f"FILTER WORKSPACE: Filtering by dataset={filter_dataset}, org={organization_id}")
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        selected_columns = workspace.get('columns', [])
        
        # Filter columns if needed
        if filter_dataset and filter_dataset != 'all':
            filtered_columns = [col for col in selected_columns if col.get('dataset') == filter_dataset]
        else:
            filtered_columns = selected_columns
        
        logger.info(f"FILTER WORKSPACE: Showing {len(filtered_columns)} columns (filtered from {len(selected_columns)})")
        
        # Render the filtered workspace
        return render(request, 'partials/filtered_column_workspace.html', {
            'selected_columns': filtered_columns,
            'filter_dataset': filter_dataset,
            'organization_id': organization_id,
            'datasets': [],  # Will be passed from main template context
        })
        
    except Exception as e:
        logger.error(f"FILTER WORKSPACE: Error filtering workspace: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error filtering workspace</div>')


def expand_dataset(request):
    """
    HTMX endpoint to expand/collapse dataset columns in the Active Datasets panel.
    Shows ALL columns from the dataset with their current selection state.
    """
    try:
        organization_id = get_organization_id_from_request(request)
        dataset_name = request.GET.get('dataset', '')
        
        logger.info(f"EXPAND DATASET: Expanding dataset={dataset_name}, org={organization_id}")
        
        if not dataset_name:
            return HttpResponse('<div class="text-error text-xs p-2">Dataset name required</div>')
        
        # Get loaded datasets from cache
        loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
        active_datasets = cache.get(loaded_datasets_cache_key, [])
        
        # Find the specific dataset
        target_dataset = None
        for dataset in active_datasets:
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        if not target_dataset:
            return HttpResponse('<div class="text-error text-xs p-2">Dataset not found</div>')
        
        # Get current workspace columns to determine selection state
        workspace_columns = get_workspace_columns(request, organization_id)
        
        # Create set of selected column IDs for fast lookup
        selected_column_ids = {col.get('id') for col in workspace_columns}
        
        logger.info(f"EXPAND DATASET: Found {len(workspace_columns)} total workspace columns, {len(selected_column_ids)} selected IDs")
        
        # Get ALL columns from the target dataset and mark their selection state
        dataset_columns = target_dataset.get('columns', [])
        columns_with_state = []
        
        for col in dataset_columns:
            # Create column ID (dataset_source_column format)
            source_name = target_dataset.get('source', 'unknown')
            column_id = f"{dataset_name}_{source_name}_{col}"
            
            # Check if this column is currently selected in workspace
            is_selected = column_id in selected_column_ids
            
            # Find workspace column data if selected
            workspace_col_data = None
            if is_selected:
                workspace_col_data = next((wcol for wcol in workspace_columns if wcol.get('id') == column_id), None)
            
            column_data = {
                'id': column_id,
                'name': col,
                'dataset': dataset_name,
                'source': source_name,
                'is_selected': is_selected,
                'is_anchor': workspace_col_data.get('is_anchor', False) if workspace_col_data else False,
                'is_fk': workspace_col_data.get('is_fk', False) if workspace_col_data else False,
                'is_multi_value': workspace_col_data.get('is_multi_value', False) if workspace_col_data else False,
            }
            columns_with_state.append(column_data)
        
        logger.info(f"EXPAND DATASET: Prepared {len(columns_with_state)} columns for {dataset_name}, {sum(1 for c in columns_with_state if c['is_selected'])} selected")
        
        # Get all datasets for context (needed for forms)
        state = get_organization_state(request, organization_id)
        all_datasets = state['all_datasets']
        datasets_json = json.dumps(all_datasets, cls=DjangoJSONEncoder) if all_datasets else '[]'
        
        # Generate CSRF token
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Render dataset column selection interface
        return render(request, 'partials/dataset_column_selector.html', {
            'dataset': target_dataset,
            'columns': columns_with_state,
            'organization_id': organization_id,
            'datasets': all_datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        })
        
    except Exception as e:
        logger.error(f"EXPAND DATASET: Error expanding dataset: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-xs p-2">Error loading dataset columns</div>')


def mapping_config(request):
    """
    Simple view that loads mapping configuration based on type.
    Uses template-driven logic to include the appropriate configuration partial.
    """
    mapping_type = request.GET.get('type')
    anchor_column_id = request.GET.get('anchor_column')
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"MAPPING CONFIG: Loading config for type={mapping_type}, anchor_column={anchor_column_id}, org={organization_id}")
    
    # Handle reset type - return empty state
    if mapping_type == 'reset':
        logger.info("MAPPING CONFIG: Resetting to empty state")
        return HttpResponse('''
            <div class="text-center py-4 text-base-content opacity-50">
                <svg class="w-8 h-8 mx-auto mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <p class="text-sm">Select a mapping type above to configure</p>
            </div>
        ''')
    
    # Validate mapping type
    if mapping_type not in ['entity', 'lookup', 'vocabulary', 'junction']:
        logger.error(f"MAPPING CONFIG: Invalid mapping type: {mapping_type}")
        return HttpResponseBadRequest("Invalid mapping type")
    
    # Get current workspace from cache for context
    workspace_cache_key = f"relationship_workspace_{organization_id}"
    workspace = cache.get(workspace_cache_key, {'columns': []})
    selected_columns = workspace.get('columns', [])
    
    # Find anchor column if provided
    anchor_column = None
    if anchor_column_id:
        anchor_column = next((col for col in selected_columns if col.get('id') == anchor_column_id), None)
        logger.info(f"MAPPING CONFIG: Found anchor column: {anchor_column.get('name') if anchor_column else 'None'}")
    
    # Extract FK columns for target specification
    fk_columns = [col for col in selected_columns if col.get('is_fk', False)]
    logger.info(f"MAPPING CONFIG: Found {len(fk_columns)} FK columns: {[col.get('name') for col in fk_columns]}")
    
    # Get active datasets from cache (loaded datasets)
    loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
    active_datasets = cache.get(loaded_datasets_cache_key, [])
    
    context = {
        'mapping_type': mapping_type,
        'selected_columns': selected_columns,
        'anchor_column': anchor_column,
        'fk_columns': fk_columns,
        'active_datasets': active_datasets,
        'organization_id': organization_id,
    }
    
    logger.info(f"MAPPING CONFIG: Rendering config for {mapping_type} with {len(selected_columns)} selected columns")
    
    return render(request, 'partials/mapping_config_loader.html', context)


def tooltip_view(request):
    """
    Simple HTMX view to serve tooltip content based on type parameter.
    """
    tooltip_type = request.GET.get('type')
    
    logger.info(f"TOOLTIP: Serving tooltip for type={tooltip_type}")
    
    # Map tooltip types to template names
    tooltip_templates = {
        'workflow': 'partials/tooltips/mapping_workflow_help.html',
        'anchor_column': 'partials/tooltips/anchor_column_help.html', 
        'fk_column': 'partials/tooltips/fk_column_help.html',
        'fk_target': 'partials/tooltips/fk_target_help.html',
        'column_role': 'partials/tooltips/column_role_help.html',
    }
    
    template_name = tooltip_templates.get(tooltip_type)
    if not template_name:
        logger.error(f"TOOLTIP: Unknown tooltip type: {tooltip_type}")
        return HttpResponse('<div class="text-error text-xs">Unknown tooltip type</div>')
    
    try:
        return render(request, template_name)
    except Exception as e:
        logger.error(f"TOOLTIP: Error rendering tooltip {tooltip_type}: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-xs">Error loading tooltip</div>')


def toggle_fk_column(request):
    """
    HTMX endpoint to toggle the FK (foreign key) status of a column.
    FK columns will need target specification during mapping creation.
    """
    logger.info(f"TOGGLE_FK: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"TOGGLE_FK: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("TOGGLE_FK: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"TOGGLE FK: {column_id} for org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Missing column_id'}, status=400)
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        
        # Update FK status
        existing_columns = workspace.get('columns', [])
        column_found = False
        
        for col in existing_columns:
            if col.get('id') == column_id:
                # Toggle FK status
                current_status = col.get('is_fk', False)
                col['is_fk'] = not current_status
                column_found = True
                logger.info(f"TOGGLE FK: Column {column_id} FK status: {col['is_fk']}")
                break
        
        if not column_found:
            return JsonResponse({'error': 'Column not found in workspace'}, status=400)
        
        workspace['columns'] = existing_columns
        
        # Save back to cache
        cache.set(workspace_cache_key, workspace, timeout=60*60*24)  # 24 hours
        
        logger.info(f"TOGGLE FK: Updated workspace")
        
        # Get datasets from request data (passed via HTMX) or get from state
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Generate workspace HTML with updated FK status
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': workspace['columns'],
            'anchor_column': next((col for col in workspace['columns'] if col.get('is_anchor')), None),
            'organization_id': organization_id,
            'datasets': datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        return HttpResponse(workspace_html)
        
    except Exception as e:
        logger.error(f"TOGGLE FK: Error toggling FK status: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def configure_fk(request):
    """
    HTMX endpoint to open FK configuration modal for a specific column.
    """
    try:
        column_id = request.GET.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"CONFIGURE FK: Opening modal for column={column_id}, org={organization_id}")
        
        if not column_id:
            return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        selected_columns = workspace.get('columns', [])
        
        # Find the specific column
        column = next((col for col in selected_columns if col.get('id') == column_id), None)
        if not column:
            return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
        
        # TODO: Get available datasets from the existing template context
        # The datasets are already loaded in direct_split_table_graph_view
        # For now, use a placeholder list - this needs to be passed from the template context
        available_datasets = [
            {'name': 'Dataset1', 'source': 'source1'},
            {'name': 'Dataset2', 'source': 'source2'},
            {'name': 'Dataset3', 'source': 'source3'},
        ]
        # Filter out current dataset
        available_datasets = [d for d in available_datasets if d['name'] != column.get('dataset')]
        
        logger.info(f"CONFIGURE FK: Using placeholder datasets - needs template context integration")
        
        # Get current FK configuration if exists
        fk_config = column.get('fk_config', {})
        current_direction = fk_config.get('direction')
        target_dataset = fk_config.get('target_dataset')
        target_column = fk_config.get('target_column')
        
        logger.info(f"CONFIGURE FK: Column {column.get('name')} current config: {fk_config}")
        
        context = {
            'column': column,
            'available_datasets': available_datasets,  # Full dataset objects with names and sources
            'current_direction': current_direction,
            'target_dataset': target_dataset,
            'target_column': target_column,
            'organization_id': organization_id,
        }
        
        return render(request, 'partials/fk_config_modal.html', context)
        
    except Exception as e:
        logger.error(f"CONFIGURE FK: Error opening modal: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error opening FK configuration</div>')


def update_fk_columns(request):
    """
    HTMX endpoint to update available columns when target dataset changes.
    Uses the same S3DirectDataAnalyzer logic as direct_dataset_card.
    """
    try:
        column_id = request.POST.get('column_id')
        direction = request.POST.get('direction')
        target_dataset = request.POST.get('target_dataset')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"UPDATE FK COLUMNS: column={column_id}, direction={direction}, target_dataset={target_dataset}, org={organization_id}")
        
        if not all([column_id, direction, target_dataset]):
            return HttpResponse('<div class="text-error text-sm">Missing required parameters</div>')
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        selected_columns = workspace.get('columns', [])
        
        # Find the specific column
        column = next((col for col in selected_columns if col.get('id') == column_id), None)
        if not column:
            return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
        
        # TODO: Get target dataset columns from existing template context
        # The columns should be available in dataset.preview.colHeaders
        # For now, use placeholder columns - this needs template context integration
        target_columns = [
            {'name': 'id', 'type': 'integer'},
            {'name': 'name', 'type': 'text'},
            {'name': 'created_at', 'type': 'date'},
        ]
        
        logger.info(f"UPDATE FK COLUMNS: Using placeholder columns for {target_dataset} - needs template context integration")
        
        logger.info(f"UPDATE FK COLUMNS: Processed {len(target_columns)} target columns")
        
        context = {
            'column': column,
            'target_dataset': target_dataset,
            'target_column': None,  # Reset column selection when dataset changes
            'direction': direction,
            'organization_id': organization_id,
            'target_columns': target_columns,
        }
        
        return render(request, 'partials/fk_target_columns.html', context)
        
    except Exception as e:
        logger.error(f"UPDATE FK COLUMNS: Error updating columns: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error updating FK columns</div>')


def save_fk_config(request):
    """
    HTMX endpoint to save FK configuration for a column.
    """
    logger.info("="*60)
    logger.info("SAVE FK CONFIG: ENDPOINT HIT!")
    logger.info(f"SAVE FK CONFIG: Method={request.method}")
    logger.info(f"SAVE FK CONFIG: Content-Type={request.content_type}")
    logger.info(f"SAVE FK CONFIG: Headers={dict(request.headers)}")
    logger.info(f"SAVE FK CONFIG: Raw POST data: {dict(request.POST)}")
    logger.info(f"SAVE FK CONFIG: POST keys: {list(request.POST.keys())}")
    logger.info(f"SAVE FK CONFIG: POST values: {list(request.POST.values())}")
    logger.info("="*60)
    
    if request.method != 'POST':
        logger.error("SAVE FK CONFIG: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        fk_direction = request.POST.get('fk_direction')
        target_dataset = request.POST.get('target_dataset')
        target_column = request.POST.get('target_column')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"SAVE FK CONFIG: EXTRACTED PARAMETERS:")
        logger.info(f"  - column_id: '{column_id}' (type: {type(column_id)})")
        logger.info(f"  - fk_direction: '{fk_direction}' (type: {type(fk_direction)})")
        logger.info(f"  - target_dataset: '{target_dataset}' (type: {type(target_dataset)})")
        logger.info(f"  - target_column: '{target_column}' (type: {type(target_column)})")
        logger.info(f"  - organization_id: '{organization_id}' (type: {type(organization_id)})")
        
        # Check each parameter individually
        missing_params = []
        if not column_id:
            missing_params.append('column_id')
        if not fk_direction:
            missing_params.append('fk_direction')
        if not target_dataset:
            missing_params.append('target_dataset')
        if not target_column:
            missing_params.append('target_column')
        
        logger.info(f"SAVE FK CONFIG: Validation check:")
        logger.info(f"  - Missing parameters: {missing_params}")
        logger.info(f"  - All required present: {len(missing_params) == 0}")
        
        if not all([column_id, fk_direction, target_dataset, target_column]):
            error_msg = f'Missing required FK configuration fields: {", ".join(missing_params)}'
            logger.error(f"SAVE FK CONFIG: VALIDATION FAILED - {error_msg}")
            return JsonResponse({'error': error_msg}, status=400)
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        logger.info(f"SAVE FK CONFIG: Getting workspace from cache key: {workspace_cache_key}")
        workspace = cache.get(workspace_cache_key, {'columns': []})
        existing_columns = workspace.get('columns', [])
        logger.info(f"SAVE FK CONFIG: Found {len(existing_columns)} columns in workspace")
        
        # Log existing columns for debugging
        for i, col in enumerate(existing_columns):
            logger.info(f"SAVE FK CONFIG: Column {i}: id='{col.get('id')}', name='{col.get('name')}', dataset='{col.get('dataset')}'")
        
        # Update the column with FK configuration
        column_found = False
        for col in existing_columns:
            if col.get('id') == column_id:
                logger.info(f"SAVE FK CONFIG: FOUND MATCHING COLUMN: {col}")
                col['is_fk'] = True
                col['fk_config'] = {
                    'direction': fk_direction,
                    'target_dataset': target_dataset,
                    'target_column': target_column,
                }
                column_found = True
                logger.info(f"SAVE FK CONFIG: Updated column {column_id} with FK config: {col['fk_config']}")
                break
        
        if not column_found:
            logger.error(f"SAVE FK CONFIG: COLUMN NOT FOUND - Looking for column_id: '{column_id}' in {len(existing_columns)} columns")
            return JsonResponse({'error': 'Column not found in workspace'}, status=400)
        
        workspace['columns'] = existing_columns
        
        # Save back to cache
        logger.info(f"SAVE FK CONFIG: Saving workspace back to cache with {len(existing_columns)} columns")
        cache.set(workspace_cache_key, workspace, timeout=60*60*24)  # 24 hours
        
        logger.info(f"SAVE FK CONFIG: Generating workspace HTML template")
        
        # Get datasets from request data (passed via HTMX) or get from state
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Generate workspace HTML with updated FK configuration
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': workspace['columns'],
            'anchor_column': next((col for col in workspace['columns'] if col.get('is_anchor')), None),
            'organization_id': organization_id,
            'datasets': datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        logger.info(f"SAVE FK CONFIG: Generated workspace HTML (length: {len(workspace_html)})")
        
        logger.info(f"SAVE FK CONFIG: SUCCESS - Updated workspace with FK configuration")
        return HttpResponse(workspace_html)
        
    except Exception as e:
        logger.error(f"SAVE FK CONFIG: EXCEPTION OCCURRED!")
        logger.error(f"SAVE FK CONFIG: Exception type: {type(e)}")
        logger.error(f"SAVE FK CONFIG: Exception message: {str(e)}")
        logger.error(f"SAVE FK CONFIG: Full traceback:", exc_info=True)
        logger.error(f"SAVE FK CONFIG: Request POST data at exception: {dict(request.POST)}")
        return JsonResponse({'error': str(e)}, status=500)


def remove_fk_config(request):
    """
    HTMX endpoint to remove FK configuration from a column.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        column_id = request.POST.get('column_id')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"REMOVE FK CONFIG: column={column_id}, org={organization_id}")
        
        if not column_id:
            return JsonResponse({'error': 'Column ID required'}, status=400)
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        existing_columns = workspace.get('columns', [])
        
        # Remove FK configuration from the column
        column_found = False
        for col in existing_columns:
            if col.get('id') == column_id:
                col['is_fk'] = False
                col.pop('fk_config', None)  # Remove FK config entirely
                column_found = True
                logger.info(f"REMOVE FK CONFIG: Removed FK config from column {column_id}")
                break
        
        if not column_found:
            return JsonResponse({'error': 'Column not found in workspace'}, status=400)
        
        workspace['columns'] = existing_columns
        
        # Save back to cache
        cache.set(workspace_cache_key, workspace, timeout=60*60*24)  # 24 hours
        
        logger.info(f"REMOVE FK CONFIG: Updated workspace")
        
        # Get datasets from request data (passed via HTMX) or get from state
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []
            # If no datasets in request, get from state as fallback
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
        
        # Generate workspace HTML with updated configuration
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': workspace['columns'],
            'anchor_column': next((col for col in workspace['columns'] if col.get('is_anchor')), None),
            'organization_id': organization_id,
            'datasets': datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        return HttpResponse(workspace_html)
        
    except Exception as e:
        logger.error(f"REMOVE FK CONFIG: Error removing configuration: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def close_fk_modal(request):
    """
    HTMX endpoint to close the FK configuration modal.
    """
    return HttpResponse('')  # Empty response to clear the modal


def update_fk_targets(request):
    """
    HTMX endpoint to update FK targets section when direction changes.
    """
    try:
        column_id = request.GET.get('column_id')
        direction = request.GET.get('direction')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"UPDATE FK TARGETS: column={column_id}, direction={direction}, org={organization_id}")
        
        if not column_id or not direction:
            return HttpResponse('<div class="text-error text-sm">Column ID and direction required</div>')
        
        # Get current workspace from cache
        workspace_cache_key = f"relationship_workspace_{organization_id}"
        workspace = cache.get(workspace_cache_key, {'columns': []})
        selected_columns = workspace.get('columns', [])
        
        # Find the specific column
        column = next((col for col in selected_columns if col.get('id') == column_id), None)
        if not column:
            return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
        
        # TODO: Get available datasets from existing template context  
        # Use placeholder datasets - needs template context integration
        available_datasets = [
            {'name': 'Dataset1', 'source': 'source1'},
            {'name': 'Dataset2', 'source': 'source2'},
            {'name': 'Dataset3', 'source': 'source3'},
        ]
        # Filter out current dataset
        available_datasets = [d for d in available_datasets if d['name'] != column.get('dataset')]
        
        # Get current FK configuration if exists
        fk_config = column.get('fk_config', {})
        target_dataset = fk_config.get('target_dataset') if fk_config.get('direction') == direction else None
        target_column = fk_config.get('target_column') if fk_config.get('direction') == direction else None
        
        logger.info(f"UPDATE FK TARGETS: Available datasets: {available_datasets}, current target: {target_dataset}")
        
        # TODO: Get target columns from existing template context
        # The columns should be available in dataset.preview.colHeaders for the target_dataset
        target_columns = []
        if target_dataset:
            # Placeholder columns - needs template context integration
            target_columns = [
                {'name': 'id', 'type': 'integer'},
                {'name': 'name', 'type': 'text'},
                {'name': 'created_at', 'type': 'date'},
            ]
            logger.info(f"UPDATE FK TARGETS: Using placeholder columns for {target_dataset}")
        
        context = {
            'column': column,
            'direction': direction,
            'available_datasets': available_datasets,
            'target_dataset': target_dataset,
            'target_column': target_column,
            'target_columns': target_columns,  # Include target columns
            'organization_id': organization_id,
        }
        
        return render(request, 'partials/fk_targets_section.html', context)
        
    except Exception as e:
        logger.error(f"UPDATE FK TARGETS: Error updating targets: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error updating FK targets</div>')


def toggle_fk_form(request):
    """
    HTMX endpoint to toggle inline FK configuration form for a column.
    Shows the form if hidden, hides it if shown.
    """
    logger.info("="*80)
    logger.info("TOGGLE FK FORM: ENDPOINT HIT!")
    logger.info(f"TOGGLE FK FORM: Method={request.method}")
    logger.info(f"TOGGLE FK FORM: Content-Type={request.content_type}")
    logger.info(f"TOGGLE FK FORM: Headers={dict(request.headers)}")
    logger.info(f"TOGGLE FK FORM: GET data: {dict(request.GET)}")
    logger.info(f"TOGGLE FK FORM: POST data: {dict(request.POST)}")
    logger.info(f"TOGGLE FK FORM: POST keys: {list(request.POST.keys())}")
    logger.info(f"TOGGLE FK FORM: POST values: {list(request.POST.values())}")
    
    try:
        column_id = request.POST.get('column_id') or request.GET.get('column_id')
        organization_id = request.POST.get('organization_id') or get_organization_id_from_request(request)
        datasets_json = request.POST.get('datasets', '[]')
        
        logger.info(f"TOGGLE FK FORM: EXTRACTED PARAMETERS:")
        logger.info(f"  - column_id: '{column_id}' (type: {type(column_id)})")
        logger.info(f"  - organization_id: '{organization_id}' (type: {type(organization_id)})")
        logger.info(f"  - datasets_json: '{datasets_json}' (type: {type(datasets_json)}, length: {len(datasets_json)})")
        logger.info(f"  - datasets_json first 200 chars: '{datasets_json[:200]}...'")
        logger.info("="*80)
        
        if not column_id:
            return HttpResponse('<div class="text-error text-sm">Column ID required</div>')
        
        # Get current workspace from session (consistent with other views)
        selected_columns = get_workspace_columns(request, organization_id)
        
        # Find the specific column
        column = next((col for col in selected_columns if col.get('id') == column_id), None)
        if not column:
            logger.error(f"TOGGLE FK FORM: Column '{column_id}' not found in workspace")
            logger.error(f"TOGGLE FK FORM: Available columns: {[col.get('id') for col in selected_columns]}")
            return HttpResponse('<div class="text-error text-sm">Column not found in workspace</div>')
        
        # Parse datasets from the template context
        logger.info(f"TOGGLE FK FORM: PARSING JSON:")
        logger.info(f"  - Raw datasets_json: '{datasets_json}'")
        logger.info(f"  - datasets_json type: {type(datasets_json)}")
        logger.info(f"  - datasets_json length: {len(datasets_json)}")
        
        try:
            import json
            datasets = json.loads(datasets_json)
            logger.info(f"TOGGLE FK FORM: JSON PARSING SUCCESS!")
            logger.info(f"  - Parsed datasets type: {type(datasets)}")
            logger.info(f"  - Parsed datasets length: {len(datasets)}")
            logger.info(f"  - First dataset sample: {datasets[0] if datasets else 'No datasets'}")
            if datasets:
                for i, dataset in enumerate(datasets[:3]):  # Log first 3 datasets
                    logger.info(f"  - Dataset {i}: name='{dataset.get('name')}', source='{dataset.get('source')}', preview_cols={len(dataset.get('preview', {}).get('colHeaders', []))}")
        except json.JSONDecodeError as e:
            logger.error(f"TOGGLE FK FORM: JSON PARSING FAILED!")
            logger.error(f"  - JSONDecodeError: {str(e)}")
            logger.error(f"  - Raw datasets_json: '{datasets_json}'")
            datasets = []
        except Exception as e:
            logger.error(f"TOGGLE FK FORM: UNEXPECTED PARSING ERROR!")
            logger.error(f"  - Exception type: {type(e)}")
            logger.error(f"  - Exception message: {str(e)}")
            datasets = []
        
        # Get current FK configuration if exists
        fk_config = column.get('fk_config', {})
        current_direction = fk_config.get('direction', 'outbound')  # Default to outbound
        target_dataset = fk_config.get('target_dataset', '')
        target_column = fk_config.get('target_column', '')
        
        logger.info(f"TOGGLE FK FORM: FINAL CONTEXT PREPARATION:")
        logger.info(f"  - Column name: '{column.get('name')}'")
        logger.info(f"  - Current direction: '{current_direction}'")
        logger.info(f"  - Target dataset: '{target_dataset}'")
        logger.info(f"  - Target column: '{target_column}'")
        logger.info(f"  - Datasets count in context: {len(datasets)}")
        logger.info(f"  - Organization ID: '{organization_id}'")
        
        context = {
            'column': column,
            'datasets': datasets,
            'datasets_json': json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]',
            'current_direction': current_direction,
            'target_dataset': target_dataset,
            'target_column': target_column,
            'organization_id': organization_id,
            'csrf_token': request.META.get('CSRF_COOKIE')
        }
        
        logger.info(f"TOGGLE FK FORM: RENDERING TEMPLATE with context keys: {list(context.keys())}")
        logger.info(f"TOGGLE FK FORM: Context datasets sample: {[d.get('name') for d in datasets[:3]] if datasets else 'No datasets'}")
        
        return render(request, 'partials/inline_fk_form.html', context)
        
    except Exception as e:
        logger.error(f"TOGGLE FK FORM: Error toggling form: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error opening FK configuration</div>')


def hide_fk_form(request):
    """
    HTMX endpoint to hide the inline FK configuration form.
    """
    try:
        column_id = request.GET.get('column_id')
        logger.info(f"HIDE FK FORM: column={column_id}")
        
        # Return empty div to hide the form
        return HttpResponse(f'<div id="fk-form-{column_id}"></div>')
        
    except Exception as e:
        logger.error(f"HIDE FK FORM: Error hiding form: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-sm">Error hiding FK form</div>')


def update_fk_target_columns(request):
    """
    HTMX endpoint to update target columns when target dataset selection changes.
    """
    logger.info("="*80)
    logger.info("UPDATE FK TARGET COLUMNS: ENDPOINT HIT!")
    logger.info(f"UPDATE FK TARGET COLUMNS: Method={request.method}")
    logger.info(f"UPDATE FK TARGET COLUMNS: Content-Type={request.content_type}")
    logger.info(f"UPDATE FK TARGET COLUMNS: GET data: {dict(request.GET)}")
    logger.info(f"UPDATE FK TARGET COLUMNS: POST data: {dict(request.POST)}")
    logger.info(f"UPDATE FK TARGET COLUMNS: POST keys: {list(request.POST.keys())}")
    
    try:
        column_id = request.POST.get('column_id') or request.GET.get('column_id')
        target_dataset = request.POST.get('target_dataset') or request.GET.get('target_dataset')
        organization_id = request.POST.get('organization_id') or get_organization_id_from_request(request)
        datasets_json = request.POST.get('datasets', '[]')
        
        logger.info(f"UPDATE FK TARGET COLUMNS: EXTRACTED PARAMETERS:")
        logger.info(f"  - column_id: '{column_id}'")
        logger.info(f"  - target_dataset: '{target_dataset}'")
        logger.info(f"  - organization_id: '{organization_id}'")
        logger.info(f"  - datasets_json length: {len(datasets_json)}")
        logger.info(f"  - datasets_json first 100 chars: '{datasets_json[:100]}...'")
        logger.info("="*80)
        
        if not column_id or not target_dataset:
            return HttpResponse('<option value="">Select target column...</option>')
        
        # Parse datasets from the template context
        try:
            import json
            datasets = json.loads(datasets_json)
            logger.info(f"UPDATE FK TARGET COLUMNS: Received {len(datasets)} datasets from template")
        except json.JSONDecodeError:
            logger.error(f"UPDATE FK TARGET COLUMNS: Failed to parse datasets JSON: {datasets_json}")
            return HttpResponse('<option value="">Error parsing datasets</option>')
        
        # Find the target dataset and get its columns
        logger.info(f"UPDATE FK TARGET COLUMNS: SEARCHING FOR DATASET:")
        logger.info(f"  - Looking for dataset with name: '{target_dataset}'")
        logger.info(f"  - Available datasets: {[d.get('name') for d in datasets]}")
        
        target_dataset_obj = next((d for d in datasets if d.get('name') == target_dataset), None)
        
        if not target_dataset_obj:
            logger.error(f"UPDATE FK TARGET COLUMNS: DATASET NOT FOUND!")
            logger.error(f"  - Target dataset: '{target_dataset}'")
            logger.error(f"  - Available datasets: {[d.get('name') for d in datasets]}")
            return HttpResponse('<option value="">Dataset not found</option>')
        
        logger.info(f"UPDATE FK TARGET COLUMNS: DATASET FOUND!")
        logger.info(f"  - Dataset object keys: {list(target_dataset_obj.keys())}")
        logger.info(f"  - Dataset name: '{target_dataset_obj.get('name')}'")
        logger.info(f"  - Dataset has preview: {'preview' in target_dataset_obj}")
        
        # Get columns from the dataset preview
        preview = target_dataset_obj.get('preview', {})
        logger.info(f"UPDATE FK TARGET COLUMNS: PREVIEW ANALYSIS:")
        logger.info(f"  - Preview keys: {list(preview.keys())}")
        logger.info(f"  - Has colHeaders: {'colHeaders' in preview}")
        
        columns = preview.get('colHeaders', [])
        logger.info(f"UPDATE FK TARGET COLUMNS: COLUMNS EXTRACTION:")
        logger.info(f"  - Found {len(columns)} columns for {target_dataset}")
        logger.info(f"  - Columns: {columns}")
        
        # Build options HTML
        options_html = '<option value="">Select target column...</option>\n'
        for column_name in columns:
            options_html += f'<option value="{column_name}">{column_name}</option>\n'
            
        logger.info(f"UPDATE FK TARGET COLUMNS: GENERATED OPTIONS HTML (length: {len(options_html)})")
        logger.info(f"UPDATE FK TARGET COLUMNS: First 200 chars of options: '{options_html[:200]}...')")
        
        return HttpResponse(options_html)
        
    except Exception as e:
        logger.error(f"UPDATE FK TARGET COLUMNS: Error updating columns: {e}", exc_info=True)
        return HttpResponse('<option value="">Error loading columns</option>')


def save_inline_fk_config(request):
    """
    HTMX endpoint to save FK configuration from the inline form.
    Similar to save_fk_config but designed for the inline form.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        # Extract form data
        column_id = request.POST.get('column_id')
        fk_direction = request.POST.get('fk_direction')
        target_dataset = request.POST.get('target_dataset')
        target_column = request.POST.get('target_column')
        organization_id = get_organization_id_from_request(request)
        
        logger.info(f"SAVE INLINE FK CONFIG: column={column_id}, direction={fk_direction}, target={target_dataset}.{target_column}, org={organization_id}")
        
        if not all([column_id, fk_direction, target_dataset, target_column]):
            missing = [name for name, val in [('column_id', column_id), ('fk_direction', fk_direction), ('target_dataset', target_dataset), ('target_column', target_column)] if not val]
            error_msg = f'Missing required fields: {", ".join(missing)}'
            logger.error(f"SAVE INLINE FK CONFIG: VALIDATION FAILED - {error_msg}")
            return HttpResponse(f'<div class="text-error text-xs p-2">{error_msg}</div>')
        
        # Get current workspace from session (consistent with other views)
        existing_columns = get_workspace_columns(request, organization_id)
        
        # Debug: Log all column IDs in workspace
        logger.info(f"SAVE INLINE FK CONFIG: DEBUGGING WORKSPACE CONTENTS:")
        logger.info(f"  - Looking for column_id: '{column_id}'")
        logger.info(f"  - Workspace has {len(existing_columns)} columns:")
        for i, col in enumerate(existing_columns):
            logger.info(f"    [{i}] ID: '{col.get('id')}' | Dataset: '{col.get('dataset')}' | Source: '{col.get('source')}' | Column: '{col.get('name')}'")
        
        # Update the column with FK configuration
        column_found = False
        for col in existing_columns:
            if col.get('id') == column_id:
                col['is_fk'] = True
                col['fk_config'] = {
                    'direction': fk_direction,
                    'target_dataset': target_dataset,
                    'target_column': target_column,
                }
                column_found = True
                logger.info(f"SAVE INLINE FK CONFIG: ✅ FOUND and updated column {column_id} with FK config: {col['fk_config']}")
                break
        
        if not column_found:
            logger.error(f"SAVE INLINE FK CONFIG: ❌ Column not found: '{column_id}'")
            logger.error(f"SAVE INLINE FK CONFIG: Available column IDs: {[col.get('id') for col in existing_columns]}")
            return HttpResponse('<div class="text-error text-xs p-2">Column not found in workspace</div>')
        
        # Save back to session (consistent with other views)
        update_workspace_columns(request, organization_id, existing_columns)
        
        logger.info(f"SAVE INLINE FK CONFIG: Successfully updated FK configuration")
        
        # Get datasets from request data (passed via HTMX)
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json)
        except json.JSONDecodeError:
            datasets = []

        # Generate CSRF token for the template
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)

        # Refresh the entire workspace to show updated FK status
        workspace_html = render_to_string('partials/selected_columns_workspace.html', {
            'selected_columns': existing_columns,
            'anchor_column': next((col for col in existing_columns if col.get('is_anchor')), None),
            'organization_id': organization_id,
            'datasets': datasets,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        return HttpResponse(workspace_html)
        
    except Exception as e:
        logger.error(f"SAVE INLINE FK CONFIG: Error saving configuration: {e}", exc_info=True)
        return HttpResponse('<div class="text-error text-xs p-2">Error saving FK configuration</div>')


def get_organization_state(request, organization_id):
    """
    Helper function to get consolidated state for an organization.
    Returns all datasets, active datasets, and selected columns.
    Now includes cached preview data for FK forms.
    """
    try:
        # Check cache first for datasets with preview data
        datasets_cache_key = f"organization_datasets_{organization_id}"
        cached_datasets = cache.get(datasets_cache_key)
        
        if cached_datasets:
            logger.info(f"GET ORG STATE: Using cached datasets for {organization_id}: {len(cached_datasets)} datasets")
            all_datasets = cached_datasets
        else:
            logger.info(f"GET ORG STATE: Loading datasets for {organization_id} and caching with preview data...")
            
            # Get all available datasets with preview data (like dataset_card.html)
            analyzer = S3DirectDataAnalyzer()
            sources = analyzer.discover_s3_data_sources(organization_id)
            
            all_datasets = []
            for source in sources:
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                for dataset_name in dataset_names:
                    dataset_lower = dataset_name.lower()
                    is_csv = (dataset_lower.endswith(('.csv', '.tsv', '.txt')) or 
                             'csv' in dataset_lower or 
                             (source.format and source.format.lower() in ['csv', 'tsv', 'text']))
                    
                    if is_csv:
                        try:
                            # Load minimal preview (just column headers) for FK functionality
                            preview = analyzer.get_s3_table_preview(source, dataset_name, limit=1)
                            
                            dataset_info = {
                                'name': dataset_name,
                                'source': source.name,
                                'format': source.format or 'csv',
                                'preview': {
                                    'colHeaders': preview.column_headers,
                                    'total_rows': preview.total_rows,
                                }
                            }
                            all_datasets.append(dataset_info)
                            logger.debug(f"GET ORG STATE: Loaded {dataset_name} with {len(preview.column_headers)} columns")
                            
                        except Exception as preview_error:
                            logger.warning(f"GET ORG STATE: Could not load preview for {dataset_name}: {preview_error}")
                            # Fallback to basic info without preview
                            all_datasets.append({
                                'name': dataset_name,
                                'source': source.name,
                                'format': source.format or 'csv'
                            })
            
            # Cache the datasets with preview data for 1 hour
            cache.set(datasets_cache_key, all_datasets, timeout=60*60)
            logger.info(f"GET ORG STATE: Cached {len(all_datasets)} datasets with preview data")
        
        # Get active datasets from session
        session_key = f"selected_datasets_{organization_id}"
        active_dataset_names = request.session.get(session_key, [])
        
        # Create active datasets with details
        active_datasets = []
        for dataset_name in active_dataset_names:
            for dataset in all_datasets:
                if dataset['name'] == dataset_name:
                    active_datasets.append(dataset)
                    break
        
        # Get selected columns from session (single source of truth)
        selected_columns = get_workspace_columns(request, organization_id)
        
        return {
            'all_datasets': all_datasets,
            'active_datasets': active_datasets,
            'active_dataset_names': active_dataset_names,
            'selected_columns': selected_columns,
            'organization_id': organization_id
        }
    except Exception as e:
        logger.error(f"Error getting organization state: {e}", exc_info=True)
        return {
            'all_datasets': [],
            'active_datasets': [],
            'active_dataset_names': [],
            'selected_columns': [],
            'organization_id': organization_id
        }


def select_all_dataset_columns(request):
    """
    HTMX endpoint to select all columns from a specific dataset.
    """
    logger.info(f"SELECT_ALL_DATASET: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"SELECT_ALL_DATASET: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("SELECT_ALL_DATASET: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        dataset_name = request.POST.get('dataset')
        
        if not dataset_name:
            return JsonResponse({'error': 'Missing dataset name'}, status=400)
        
        logger.info(f"SELECT ALL DATASET COLUMNS: {dataset_name} for org={organization_id}")
        
        # Get datasets from form data first, fallback to cache
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json) if datasets_json != '[]' else []
        except json.JSONDecodeError:
            datasets = []
        
        # If no datasets from form, try cache as fallback
        if not datasets:
            loaded_datasets_cache_key = f"loaded_datasets_{organization_id}"
            datasets = cache.get(loaded_datasets_cache_key, [])
        
        # Find target dataset
        target_dataset = None
        for dataset in datasets:
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        if not target_dataset:
            logger.error(f"SELECT ALL DATASET: Dataset '{dataset_name}' not found in available datasets")
            return JsonResponse({'error': 'Dataset not found'}, status=400)
        
        # Get current workspace from session
        existing_columns = get_workspace_columns(request, organization_id)
        
        # Create column IDs for all columns in the dataset
        source_name = target_dataset.get('source', 'unknown')
        # Get columns from the correct location in the dataset structure
        dataset_columns = target_dataset.get('preview', {}).get('colHeaders', [])
        
        # Get set of existing column IDs
        existing_column_ids = {col.get('id') for col in existing_columns}
        
        # Add all columns from this dataset that aren't already in workspace
        new_columns = []
        for col_name in dataset_columns:
            column_id = f"{dataset_name}_{source_name}_{col_name}"
            
            if column_id not in existing_column_ids:
                column_data = {
                    'id': column_id,
                    'name': col_name,
                    'dataset': dataset_name,
                    'source': source_name,
                    'is_anchor': False,
                    'is_fk': False,
                    'is_multi_value': False,
                }
                new_columns.append(column_data)
        
        # Add new columns to workspace
        all_columns = existing_columns + new_columns
        
        # Update workspace in session
        update_workspace_columns(request, organization_id, all_columns)
        
        logger.info(f"SELECT ALL DATASET: Added {len(new_columns)} new columns from {dataset_name}, total={len(all_columns)}")
        
        # Use datasets already parsed from form data
        # If still empty, fallback to state discovery
        if not datasets:
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)

        # Calculate selected columns for this specific dataset
        dataset_selected_columns = [col['name'] for col in all_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': all_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Render updated column badges with new selection state
        column_badges_html = render_to_string('partials/column_badges.html', {
            'dataset': target_dataset,
            'dataset_selected_columns': dataset_selected_columns,
            'datasets_json': datasets_json,
            'selected_columns': all_columns,
            'organization_id': organization_id,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Return both updates using HTMX out-of-band swaps
        from django.utils.text import slugify
        dataset_slug = slugify(target_dataset['name'])
        response_html = f"""
        {dataset_section_html}
        <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
            {column_badges_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"SELECT ALL DATASET: Error selecting all columns: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


def deselect_all_dataset_columns(request):
    """
    HTMX endpoint to deselect all columns from a specific dataset.
    """
    logger.info(f"DESELECT_ALL_DATASET: Method={request.method}, Content-Type={request.content_type}")
    logger.info(f"DESELECT_ALL_DATASET: POST data: {dict(request.POST)}")
    
    if request.method != 'POST':
        logger.error("DESELECT_ALL_DATASET: Only POST method allowed")
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        organization_id = get_organization_id_from_request(request)
        dataset_name = request.POST.get('dataset')
        
        if not dataset_name:
            return JsonResponse({'error': 'Missing dataset name'}, status=400)
        
        logger.info(f"DESELECT ALL DATASET COLUMNS: {dataset_name} for org={organization_id}")
        
        # Get current workspace from session
        existing_columns = get_workspace_columns(request, organization_id)
        
        # Remove all columns from this dataset
        filtered_columns = [col for col in existing_columns if col.get('dataset') != dataset_name]
        
        # Update workspace in session
        update_workspace_columns(request, organization_id, filtered_columns)
        
        removed_count = len(existing_columns) - len(filtered_columns)
        logger.info(f"DESELECT ALL DATASET: Removed {removed_count} columns from {dataset_name}, remaining={len(filtered_columns)}")
        
        # Get datasets from form data first, fallback to state discovery
        datasets_json = request.POST.get('datasets', '[]')
        try:
            datasets = json.loads(datasets_json) if datasets_json != '[]' else []
        except json.JSONDecodeError:
            datasets = []
            
        # If no datasets from form, fallback to state discovery
        if not datasets:
            state = get_organization_state(request, organization_id)
            datasets = state['all_datasets']
            datasets_json = json.dumps(datasets, cls=DjangoJSONEncoder) if datasets else '[]'

        # Generate CSRF token
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)

        # Find the target dataset for rendering the updated section
        target_dataset = None
        for dataset in datasets:
            if dataset.get('name') == dataset_name:
                target_dataset = dataset
                break
        
        if not target_dataset:
            logger.error(f"DESELECT ALL DATASET: Dataset '{dataset_name}' not found for rendering")
            return JsonResponse({'error': 'Dataset not found for rendering'}, status=400)
        
        # Calculate selected columns for this specific dataset (should be empty after deselecting all)
        dataset_selected_columns = [col['name'] for col in filtered_columns if col['dataset'] == dataset_name]
        
        # Render the dataset workspace section
        dataset_section_html = render_to_string('partials/dataset_workspace_section.html', {
            'dataset': target_dataset,
            'selected_columns': filtered_columns,
            'datasets': datasets,
            'organization_id': organization_id,
            'datasets_json': datasets_json,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Render updated column badges with new selection state
        column_badges_html = render_to_string('partials/column_badges.html', {
            'dataset': target_dataset,
            'dataset_selected_columns': dataset_selected_columns,
            'datasets_json': datasets_json,
            'selected_columns': filtered_columns,
            'organization_id': organization_id,
            'csrf_token': csrf_token,
        }, request=request)
        
        # Return both updates using HTMX out-of-band swaps
        from django.utils.text import slugify
        dataset_slug = slugify(target_dataset['name'])
        response_html = f"""
        {dataset_section_html}
        <div id="column-badges-{dataset_slug}" hx-swap-oob="innerHTML">
            {column_badges_html}
        </div>
        """
        
        return HttpResponse(response_html)
        
    except Exception as e:
        logger.error(f"DESELECT ALL DATASET: Error deselecting all columns: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)