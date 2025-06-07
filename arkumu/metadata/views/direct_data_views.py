"""
Direct Data Views

Views that use S3DirectDataAnalyzer to provide fast table previews and analysis
directly from S3 source files, without requiring data to be imported into the database first.

This approach is more memory-efficient and faster than the traditional database-based approach.
"""

import logging
import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.core.cache import cache

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


def get_organization_id_from_request(request):
    """Get the organization ID from the request (following the same pattern as other views)."""
    # Extract organization from GET or POST parameters, following the same pattern as other views
    organization = request.GET.get('organization') or request.POST.get('organization')
    
    # Handle both cases where organization might be passed
    if organization:
        return organization.strip()
    
    # Fallback: try to get from user if available (for future authentication integration)
    if hasattr(request, 'user') and hasattr(request.user, 'organization_id'):
        return getattr(request.user, 'organization_id', None)
    
    # Default fallback - you may want to raise an exception here instead
    return 'default-org'


@login_required
def direct_split_table_graph_view(request):
    """
    Split view showing datasets directly from S3 source files with table previews and graph visualization.
    Uses S3DirectDataAnalyzer for efficient S3-based analysis.
    """
    try:
        organization_id = get_organization_id_from_request(request)
        
        # If no organization is provided, show helpful instructions
        if not organization_id or organization_id == 'default-org':
            context = {
                'sources': [],
                'selected_source': '',
                'is_direct_mode': True,
                'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL (e.g., ?organization=rsh)',
                'show_organization_help': True
            }
            return render(request, 'split_table_graph.html', context)
        
        analyzer = S3DirectDataAnalyzer()
        
        # Discover available data sources from S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Format sources for dropdown
        sources_info = []
        for source in sources:
            dataset_names = analyzer.get_dataset_names_from_s3_source(source)
            sources_info.append({
                'name': source.name,
                'dataset_count': len(dataset_names),
                'display_name': f"{source.name} ({len(dataset_names)} dataset{'s' if len(dataset_names) != 1 else ''})",
                'format': source.format,
                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
            })
        
        context = {
            'sources': sources_info,
            'selected_source': request.GET.get('source', ''),
            'is_direct_mode': True,  # Flag to indicate we're using direct mode
            'organization_id': organization_id,  # Include organization in context
        }
        
        return render(request, 'split_table_graph.html', context)
        
    except Exception as e:
        logger.error(f"Error in direct_split_table_graph_view: {e}")
        context = {
            'sources': [],
            'selected_source': '',
            'error': f"Error loading data sources: {str(e)}",
            'is_direct_mode': True
        }
        return render(request, 'split_table_graph.html', context)


@login_required
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


@login_required
def direct_get_dataset_card(request):
    """Get a dataset card with preview using direct S3 file analysis."""
    source_name = request.GET.get('source', '')
    dataset_name = request.GET.get('dataset_name', '')
    organization_id = get_organization_id_from_request(request)

    if not source_name or not dataset_name:
        return HttpResponseBadRequest("Missing source or dataset_name")

    if not organization_id or organization_id == 'default-org':
        return HttpResponseBadRequest("Organization parameter required")

    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return HttpResponseBadRequest(f"Source '{source_name}' not found")
        
        # Get detailed preview for this dataset from S3
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=10)
        
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

        return render(request, 'partials/dataset_card.html', {
            'dataset': dataset,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{i}" for i in range(len(preview.data_rows))],  # Generate row IDs
            'source': source_name,
            'is_direct_mode': True,
            'organization_id': organization_id  # Add organization to context
        })
        
    except Exception as e:
        logger.error(f"Error getting direct dataset card: {e}")
        return HttpResponseBadRequest(f"Error: {str(e)}")


@login_required
def direct_load_more_dataset_rows(request):
    """Load more rows using S3DirectDataAnalyzer pagination."""
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 20))
    organization_id = get_organization_id_from_request(request)
    
    if not source_name or not dataset_name:
        return render(request, 'partials/table_rows.html', {'data': []})
    
    if not organization_id or organization_id == 'default-org':
        return render(request, 'partials/table_rows.html', {'data': []})
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return render(request, 'partials/table_rows.html', {'data': []})
        
        # Get the requested slice from S3
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, offset=offset, limit=limit)
        
        return render(request, 'partials/table_rows.html', {
            'data': preview.data_rows,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{offset + i}" for i in range(len(preview.data_rows))],
            'source': source_name,
            'dataset': dataset_name,
            'preview': {
                'showing_rows': preview.showing_rows,
                'total_rows': preview.total_rows,
                'has_more': preview.has_more,
                'offset': offset + preview.showing_rows
            },
            'is_direct_mode': True,
            'organization_id': organization_id  # Add organization to context
        })
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}")
        return render(request, 'partials/table_rows.html', {'data': []})


@login_required
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


@login_required
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