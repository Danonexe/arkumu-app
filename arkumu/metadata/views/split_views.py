from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.db.models import Q, Count, Prefetch
from django.core.cache import cache
import logging
from collections import defaultdict
from datetime import datetime
import traceback
import json

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.services.relationship_discovery import RelationshipDiscoveryService

logger = logging.getLogger(__name__)



def split_table_graph_view(request):
    """Split view showing all datasets from a source with table previews and graph visualization."""
    
    # Get all distinct sources first
    sources = Resource.objects.values_list('source', flat=True).distinct().order_by('source')
    
    # Simplified and more accurate dataset counting
    sources_info = []
    for source in sources:
        if not source:  # Skip empty sources
            continue
            
        # Count datasets by looking for URIs that match the exact dataset pattern
        # Datasets have the pattern: source/datasets/dataset_name
        # And don't have additional path components like /column_name/row_id
        dataset_count = Resource.objects.filter(
            source=source,
            uri__contains=f"{source}/datasets/",
            resource_type=ResourceType.IRI
        ).filter(
            # This regex ensures we only match the exact dataset URI pattern
            # Looking for URIs that end after the dataset name without more components
            uri__regex=r'/datasets/[^/]+$'
        ).count()
        
        # Only include sources that actually have datasets
        if dataset_count > 0:
            sources_info.append({
                'name': source,
                'dataset_count': dataset_count,
                'display_name': f"{source} ({dataset_count} dataset{'s' if dataset_count != 1 else ''})"
            })
    
    context = {
        'sources': sources_info,
        'selected_source': request.GET.get('source', ''),
    }
    
    return render(request, 'split_table_graph.html', context)


def _get_all_datasets_for_source_optimized(source):
    """Get all datasets for a source using efficient database queries."""
    from django.db import connection
    
    logger.info(f"OPTIMIZED: Finding datasets for source '{source}'")
    
    # Use raw SQL for efficient dataset extraction
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                SUBSTRING(uri FROM %s) as dataset_name,
                COUNT(*) as cell_count
            FROM metadata_resource
            WHERE 
                source = %s
                AND uri LIKE %s
                AND uri ~ %s
                AND resource_type = %s
            GROUP BY dataset_name
            ORDER BY dataset_name
        """, [
            '.*/datasets/([^/]+)/.*',  # Regex to extract dataset name
            source,
            '%/datasets/%',
            '/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
            ResourceType.IRI
        ])
        
        results = cursor.fetchall()
    
    datasets = []
    for dataset_name, cell_count in results:
        if dataset_name:  # Skip null results
            datasets.append({
                'name': dataset_name,
                'source': source,
                'cell_count': cell_count,
                'preview': None
            })
    
    return datasets


def _get_dataset_preview_optimized(source, dataset_name, max_rows=5, offset=0):
    """
    Get preview data using a highly optimized query strategy that avoids loading
    the entire dataset into memory for pagination.
    """
    logger.info(f"V3 OPTIMIZED: Getting preview for dataset '{dataset_name}'")

    # Step 1: Efficiently get all cell URIs to determine row and column structure.
    # This is a lightweight query, returning only strings.
    all_cell_uris = Resource.objects.filter(
        source=source,
        uri__contains=f'/datasets/{dataset_name}/',
        resource_type=ResourceType.IRI
    ).exclude(
        Q(uri__contains='/columns/') | Q(uri__contains='/rows/')
    ).values_list('uri', flat=True)

    # Step 2: Extract unique row and column IDs in Python. This is fast.
    row_ids = set()
    columns = set()
    for uri in all_cell_uris:
        parts = uri.split('/')
        if len(parts) >= 2:
            columns.add(parts[-2])
            row_ids.add(parts[-1])
            
    sorted_row_ids = sorted(list(row_ids))
    sorted_columns = sorted(list(columns))
    total_rows = len(sorted_row_ids)

    # Step 3: Paginate the row IDs.
    paginated_row_ids = sorted_row_ids[offset:offset + max_rows]
    if not paginated_row_ids:
        return {
            'colHeaders': sorted_columns, 
            'data': [], 
            'showing_rows': 0, 
            'total_rows': total_rows, 
            'offset': offset, 
            'has_more': False,
            'rowIds': []
        }

    # Step 4: Build a regex to fetch only the cells for the required rows.
    # This is the key optimization to limit the main query.
    row_id_pattern = '|'.join(paginated_row_ids)
    uri_regex = f'/({row_id_pattern})$'

    # Step 5: Fetch only the cells for the required page and prefetch their values.
    cells_for_page = Resource.objects.filter(
        source=source,
        uri__contains=f'/datasets/{dataset_name}/',
        resource_type=ResourceType.IRI,
        uri__regex=uri_regex
    ).prefetch_related(
        Prefetch(
            'subject_triples',
            queryset=Triple.objects.filter(
                predicate__uri='http://www.w3.org/1999/02/22-rdf-syntax-ns#value'
            ).select_related('object'),
            to_attr='value_triples'
        )
    )

    # Step 6: Process the small, paginated set of cells into a dictionary.
    cell_data = defaultdict(dict)
    for cell in cells_for_page:
        uri_parts = cell.uri.split('/')
        if len(uri_parts) >= 2:
            column_name = uri_parts[-2]
            row_id = uri_parts[-1]
            value = ""
            if hasattr(cell, 'value_triples') and cell.value_triples:
                value = cell.value_triples[0].object.value or ""
            cell_data[row_id][column_name] = value

    # Step 7: Build the final table data in the correct row and column order.
    table_data = []
    for row_id in paginated_row_ids:
        row_list = []
        for column in sorted_columns:
            row_list.append(cell_data.get(row_id, {}).get(column, ""))
        table_data.append(row_list)

    return {
        'colHeaders': sorted_columns,
        'data': table_data,
        'showing_rows': len(table_data),
        'total_rows': total_rows,
        'offset': offset,
        'has_more': offset + len(table_data) < total_rows,
        'rowIds': paginated_row_ids  # Include the row IDs for template access
    }


def _build_single_dataset_graph_data_optimized(source, dataset_name):
    """
    Build graph data with efficient queries, prefetching, and intelligent sampling
    to create a representative visualization of the dataset structure.
    """
    try:
        # Step 1: Get all cell URIs to understand dataset structure for sampling.
        all_cell_uris = Resource.objects.filter(
            source=source,
            uri__contains=f'/datasets/{dataset_name}/',
            resource_type=ResourceType.IRI
        ).exclude(
            Q(uri__contains='/columns/') | Q(uri__contains='/rows/')
        ).values_list('uri', flat=True)

        rows = defaultdict(list)
        columns = set()
        for uri in all_cell_uris:
            parts = uri.split('/')
            if len(parts) >= 3:
                column_name = parts[-2]
                row_id = parts[-1]
                columns.add(column_name)
                rows[row_id].append(column_name)
        
        if not rows:
            return {'nodes': [], 'links': [], 'dataset_name': dataset_name}

        # Step 2: Sample complete rows for a more representative graph.
        # This is better than just taking the first 100 cells.
        import random
        all_row_ids = list(rows.keys())
        sample_size = min(len(all_row_ids), 10) # Visualize max 10 rows
        sampled_row_ids = random.sample(all_row_ids, sample_size)
        
        # Step 3: Fetch data only for the sampled rows.
        row_id_pattern = '|'.join(sampled_row_ids)
        uri_regex = f'/({row_id_pattern})$'
        
        cells_for_graph = Resource.objects.filter(
            source=source,
            uri__contains=f'/datasets/{dataset_name}/',
            resource_type=ResourceType.IRI,
            uri__regex=uri_regex
        ).prefetch_related(
            Prefetch(
                'subject_triples',
                queryset=Triple.objects.filter(
                    predicate__uri='http://www.w3.org/1999/02/22-rdf-syntax-ns#value'
                ).select_related('object'),
                to_attr='value_triples'
            )
        )
        
        # Step 4: Process sampled cells to get their values.
        cell_values = {} # (row_id, column_name) -> value
        for cell in cells_for_graph:
            uri_parts = cell.uri.split('/')
            if len(uri_parts) >= 3:
                column_name = uri_parts[-2]
                row_id = uri_parts[-1]
                value = ""
                if hasattr(cell, 'value_triples') and cell.value_triples:
                    value = cell.value_triples[0].object.value or ""
                cell_values[(row_id, column_name)] = value
        
        # Step 5: Build visualization nodes and links.
        nodes = []
        links = []
        
        # Dataset node
        nodes.append({
            'id': f'dataset_{dataset_name}', 'label': dataset_name, 'type': 'dataset',
            'color': '#2563eb', 'shape': 'diamond'
        })
        
        # Column nodes
        for column in sorted(columns):
            nodes.append({
                'id': f'column_{column}', 'label': column, 'type': 'column',
                'color': '#059669', 'shape': 'box'
            })
            links.append({'from': f'dataset_{dataset_name}', 'to': f'column_{column}', 'label': 'hasColumn'})
        
        # Row and Cell nodes from the sample
        for row_id in sampled_row_ids:
            nodes.append({
                'id': f'row_{row_id}', 'label': f'Row {row_id}', 'type': 'row',
                'color': '#dc2626', 'shape': 'ellipse'
            })
            links.append({'from': f'dataset_{dataset_name}', 'to': f'row_{row_id}', 'label': 'hasRow'})
            
            for column in rows[row_id]:
                cell_id = f'cell_{row_id}_{column}'
                cell_value = cell_values.get((row_id, column), "")
                
                nodes.append({
                    'id': cell_id,
                    'label': str(cell_value)[:20] + ('...' if len(str(cell_value)) > 20 else ''),
                    'type': 'cell', 'color': '#7c3aed', 'shape': 'dot'
                })
                
                links.append({'from': f'row_{row_id}', 'to': cell_id, 'label': column})
                links.append({'from': f'column_{column}', 'to': cell_id, 'label': 'contains'})
        
        return {
            'nodes': nodes, 'links': links, 'dataset_name': dataset_name,
            'row_count': len(all_row_ids), 'column_count': len(columns)
        }
        
    except Exception as e:
        logger.error(f"Error building graph data: {e}")
        return {
            'nodes': [], 'links': [], 'dataset_name': dataset_name
        }



def load_source_data(request):
    """HTMX endpoint to load source data with comprehensive graph."""
    source = request.GET.get('source', '')
    
    logger.info(f"LOAD SOURCE: Loading comprehensive data for source={source}")
    print(f"LOAD SOURCE: Loading comprehensive data for source={source}")
    
    if not source:
        empty_response = render(request, 'partials/empty_state.html')
        empty_response['HX-Trigger'] = 'sourceDataLoaded'
        return empty_response
    
    try:
        # Get all datasets for this source
        datasets_data = _get_all_datasets_for_source_optimized(source)
        logger.info(f"LOAD SOURCE: Found {len(datasets_data)} datasets")
        print(f"LOAD SOURCE: Found {len(datasets_data)} datasets")
        
        # Build comprehensive graph with ALL datasets and columns
        comprehensive_graph = _build_comprehensive_source_graph(source, datasets_data)
        logger.info(f"LOAD SOURCE: Built graph with {len(comprehensive_graph['nodes'])} nodes, {len(comprehensive_graph['links'])} links")
        print(f"LOAD SOURCE: Built graph with {len(comprehensive_graph['nodes'])} nodes, {len(comprehensive_graph['links'])} links")
        
        # Prepare data for templates
        # JSON serialize the graph data to ensure Python booleans become JavaScript booleans
        graph_data_json = {
            'nodes': json.dumps(comprehensive_graph['nodes']),
            'links': json.dumps(comprehensive_graph['links']),
            'source': comprehensive_graph.get('source'),
            'dataset_count': comprehensive_graph.get('dataset_count'),
            'total_nodes': comprehensive_graph.get('total_nodes'),
            'total_links': comprehensive_graph.get('total_links'),
        }
        
        cached_data = {
            'source': source,
            'datasets': datasets_data,
            'graph_data': graph_data_json
        }
        
        # Use OOB swaps to update both table and graph
        response = render(request, 'partials/source_data.html', cached_data)
        response['HX-Trigger'] = 'sourceDataLoaded'
        return response
        
    except Exception as e:
        logger.error(f"LOAD SOURCE: Error loading source data: {e}", exc_info=True)
        print(f"LOAD SOURCE: Error loading source data: {e}")
        
        error_response = render(request, 'partials/empty_state.html', {
            'error': f"Error loading source data: {str(e)}"
        })
        return error_response



def get_dataset_card(request):
    """Get a single dataset card with preview."""
    source = request.GET.get('source', '')
    dataset_name = request.GET.get('dataset_name', '')

    if not source or not dataset_name:
        return HttpResponseBadRequest("Missing source or dataset_name")

    # Use optimized cell counting
    cell_count = Resource.objects.filter(
        source=source,
        uri__contains=f"/datasets/{dataset_name}/",
        resource_type=ResourceType.IRI
    ).exclude(
        Q(uri__contains='/columns/') | Q(uri__contains='/rows/')
    ).count()

    # Get preview data with row IDs
    preview_data = _get_dataset_preview_optimized(source, dataset_name, max_rows=5)

    dataset = {
        'name': dataset_name,
        'source': source,
        'cell_count': cell_count,
        'preview': preview_data
    }

    return render(request, 'partials/dataset_card.html', {
        'dataset': dataset,
        'colHeaders': preview_data['colHeaders'],
        'rowIds': preview_data.get('rowIds', []),
        'source': source
    })



def get_graph_data(request):
    """Generate graph data for visualization."""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    
    if not source:
        return JsonResponse({'error': 'Source parameter required'}, status=400)
    
    try:
        if dataset:
            graph_data_raw = _build_single_dataset_graph_data_optimized(source, dataset)
            # JSON serialize the graph data to ensure Python booleans become JavaScript booleans
            graph_data = {
                'nodes': json.dumps(graph_data_raw['nodes']),
                'links': json.dumps(graph_data_raw['links']),
                'dataset_name': graph_data_raw.get('dataset_name'),
                'row_count': graph_data_raw.get('row_count'),
                'column_count': graph_data_raw.get('column_count'),
            }
        else:
            graph_data = {
                'nodes': json.dumps([]),
                'links': json.dumps([]),
                'message': 'Select a dataset to view its graph'
            }
        
        return render(request, 'partials/graph_visualization.html', {'graph_data': graph_data})
    except Exception as e:
        logger.error(f"Error generating graph data: {e}")
        return render(request, 'partials/graph_visualization.html', {
            'error': str(e),
            'graph_data': {'nodes': json.dumps([]), 'links': json.dumps([])}
        })



def load_more_dataset_rows(request):
    """Load more rows using optimized preview function."""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 20))
    
    if not source or not dataset:
        return render(request, 'partials/table_rows.html', {'data': []})
    
    try:
        preview_data = _get_dataset_preview_optimized(source, dataset, max_rows=limit, offset=offset)
        
        if not preview_data:
            return render(request, 'partials/table_rows.html', {'data': []})
        
        return render(request, 'partials/table_rows.html', {
            'data': preview_data['data'],
            'colHeaders': preview_data['colHeaders'],
            'rowIds': preview_data.get('rowIds', []),
            'source': source,
            'dataset': dataset,
            'preview': preview_data  # Include full preview data for completeness
        })
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}")
        return render(request, 'partials/table_rows.html', {'data': []})



def debug_database(request):
    """Debug endpoint to inspect database contents."""
    logger.info("DEBUG: Inspecting database contents")
    
    # Clear all cache first
    cache.clear()
    
    # Get all sources
    sources = Resource.objects.values_list('source', flat=True).distinct()
    
    debug_info = {
        'total_resources': Resource.objects.count(),
        'total_triples': Triple.objects.count(),
        'sources': list(sources),
        'resource_types': dict(Resource.objects.values('resource_type').annotate(count=Count('resource_type')).values_list('resource_type', 'count')),
        'cache_cleared': True
    }
    
    return JsonResponse(debug_info, indent=2)



def highlight_column_in_graph(request):
    """
    HTMX endpoint to return updated graph visualization with highlighted column.
    """
    source = request.GET.get('source')
    dataset = request.GET.get('dataset') 
    column_name = request.GET.get('column_name')
    
    logger.info(f"COLUMN FOCUS: Request for source={source}, dataset={dataset}, column={column_name}")
    print(f"COLUMN FOCUS: Request for source={source}, dataset={dataset}, column={column_name}")
    
    if not all([source, dataset, column_name]):
        error_msg = f"Missing parameters: source={source}, dataset={dataset}, column={column_name}"
        logger.error(f"COLUMN FOCUS ERROR: {error_msg}")
        print(f"COLUMN FOCUS ERROR: {error_msg}")
        
        return render(request, 'partials/graph_visualization.html', {
            'error': error_msg,
            'graph_data': {'nodes': json.dumps([]), 'links': json.dumps([])}
        })
    
    try:
        # Get all datasets for the source to build comprehensive graph
        datasets_data = _get_all_datasets_for_source_optimized(source)
        
        # Build comprehensive graph with highlighted column
        comprehensive_graph = _build_comprehensive_source_graph(source, datasets_data)
        
        # JSON serialize the graph data
        graph_data_json = {
            'nodes': json.dumps(comprehensive_graph['nodes']),
            'links': json.dumps(comprehensive_graph['links']),
            'source': comprehensive_graph.get('source'),
            'dataset_count': comprehensive_graph.get('dataset_count'),
            'total_nodes': comprehensive_graph.get('total_nodes'),
            'total_links': comprehensive_graph.get('total_links'),
        }
        
        logger.info(f"COLUMN FOCUS: Built graph with {len(comprehensive_graph['nodes'])} nodes, highlighting column {column_name}")
        print(f"COLUMN FOCUS: Built graph with {len(comprehensive_graph['nodes'])} nodes, highlighting column {column_name}")
        
        # Return graph visualization with highlighted column
        return render(request, 'partials/graph_visualization.html', {
            'graph_data': graph_data_json,
            'highlighted_column': f'{dataset}_{column_name}',  # This will become 'column_{dataset}_{column_name}' in template
            'source': source,
            'layout': 'force'
        })
        
    except Exception as e:
        logger.error(f"COLUMN FOCUS: Error focusing column: {e}", exc_info=True)
        print(f"COLUMN FOCUS: Error focusing column: {e}")
        
        return render(request, 'partials/graph_visualization.html', {
            'error': f"Error focusing column: {str(e)}",
            'graph_data': {'nodes': json.dumps([]), 'links': json.dumps([])}
        })



def highlight_cell_in_graph(request):
    """
    HTMX endpoint to update the graph visualization with a highlighted cell,
    which highlights both its row and column.
    """
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    column_index = request.GET.get('column')
    row_index = request.GET.get('row')
    
    if not all([source, dataset, column_index, row_index]):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    try:
        # Convert to integers if they're passed as string indices
        column_index = int(column_index) if column_index.isdigit() else column_index
        row_index = int(row_index) if row_index.isdigit() else row_index
        
        # Get preview data to find actual column and row IDs
        preview_data = _get_dataset_preview_optimized(source, dataset)
        
        # Map indices to actual column and row names if needed
        if isinstance(column_index, int) and preview_data['colHeaders']:
            if column_index < len(preview_data['colHeaders']):
                column = preview_data['colHeaders'][column_index]
            else:
                column = f"column_{column_index}"
        else:
            column = column_index
            
        if isinstance(row_index, int) and preview_data.get('rowIds'):
            if row_index < len(preview_data['rowIds']):
                row = preview_data['rowIds'][row_index]
            else:
                row = f"row_{row_index}"
        else:
            row = row_index
        
        # Build graph data with cell highlighting
        graph_data_raw = _build_graph_with_highlight(
            source, dataset, 
            highlight_column=column,
            highlight_row=row
        )
        
        # JSON serialize the graph data to ensure Python booleans become JavaScript booleans
        graph_data = {
            'nodes': json.dumps(graph_data_raw['nodes']),
            'links': json.dumps(graph_data_raw['links']),
            'dataset_name': graph_data_raw.get('dataset_name'),
            'row_count': graph_data_raw.get('row_count'),
            'column_count': graph_data_raw.get('column_count'),
            'highlighted_column': graph_data_raw.get('highlighted_column'),
            'highlighted_row': graph_data_raw.get('highlighted_row'),
        }
        
        # Return just the graph visualization partial
        return render(request, 'partials/graph_visualization.html', {
            'graph_data': graph_data,
            'highlighted_column': column,
            'highlighted_row': row
        })
    except Exception as e:
        logger.error(f"Error highlighting cell in graph: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def _build_graph_with_highlight(source, dataset_name, highlight_column=None, highlight_row=None):
    """
    Build graph data with highlighting for specific columns or rows.
    This extends the _build_single_dataset_graph_data_optimized function.
    """
    logger.info(f"BUILD GRAPH: Starting for {source}/{dataset_name} with highlight_column={highlight_column}")
    try:
        # Step 1: Get all cell URIs to understand dataset structure for sampling.
        all_cell_uris = Resource.objects.filter(
            source=source,
            uri__contains=f'/datasets/{dataset_name}/',
            resource_type=ResourceType.IRI
        ).exclude(
            Q(uri__contains='/columns/') | Q(uri__contains='/rows/')
        ).values_list('uri', flat=True)

        rows = defaultdict(list)
        columns = set()
        for uri in all_cell_uris:
            parts = uri.split('/')
            if len(parts) >= 3:
                column_name = parts[-2]
                row_id = parts[-1]
                columns.add(column_name)
                rows[row_id].append(column_name)
        
        if not rows:
            return {'nodes': [], 'links': [], 'dataset_name': dataset_name}

        # Step 2: Determine rows to sample
        # If highlighting a specific row, make sure it's included
        import random
        all_row_ids = list(rows.keys())
        
        # For highlighting a specific row, make sure it's included
        if highlight_row and highlight_row in all_row_ids:
            # Always include the highlighted row and sample the rest
            remaining_rows = [r for r in all_row_ids if r != highlight_row]
            sample_size = min(len(remaining_rows), 9)  # 9 + 1 highlighted = 10 max
            if sample_size > 0:
                sampled_row_ids = random.sample(remaining_rows, sample_size)
                sampled_row_ids.append(highlight_row)
            else:
                sampled_row_ids = [highlight_row]
        else:
            # Regular sampling if no row highlight
            sample_size = min(len(all_row_ids), 10)
            sampled_row_ids = random.sample(all_row_ids, sample_size)
        
        # Step 3: Fetch data only for the sampled rows.
        row_id_pattern = '|'.join(sampled_row_ids)
        uri_regex = f'/({row_id_pattern})$'
        
        cells_for_graph = Resource.objects.filter(
            source=source,
            uri__contains=f'/datasets/{dataset_name}/',
            resource_type=ResourceType.IRI,
            uri__regex=uri_regex
        ).prefetch_related(
            Prefetch(
                'subject_triples',
                queryset=Triple.objects.filter(
                    predicate__uri='http://www.w3.org/1999/02/22-rdf-syntax-ns#value'
                ).select_related('object'),
                to_attr='value_triples'
            )
        )
        
        # Step 4: Process sampled cells to get their values.
        cell_values = {}  # (row_id, column_name) -> value
        for cell in cells_for_graph:
            uri_parts = cell.uri.split('/')
            if len(uri_parts) >= 3:
                column_name = uri_parts[-2]
                row_id = uri_parts[-1]
                value = ""
                if hasattr(cell, 'value_triples') and cell.value_triples:
                    value = cell.value_triples[0].object.value or ""
                cell_values[(row_id, column_name)] = value
        
        # Step 5: Build visualization nodes and links with highlighting.
        nodes = []
        links = []
        
        # Dataset node
        nodes.append({
            'id': f'dataset_{dataset_name}', 
            'label': dataset_name, 
            'type': 'dataset',
            'color': '#2563eb', 
            'shape': 'diamond'
        })
        
        # Column nodes with highlighting for the specified column
        for column in sorted(columns):
            is_highlighted = column == highlight_column
            if is_highlighted:
                logger.info(f"BUILD GRAPH: Highlighting column {column}")
                
            nodes.append({
                'id': f'column_{column}', 
                'label': column, 
                'type': 'column',
                # Highlight the selected column with a brighter color
                'color': '#ff5733' if is_highlighted else '#059669',
                'shape': 'box',
                'highlighted': is_highlighted
            })
            links.append({
                'from': f'dataset_{dataset_name}', 
                'to': f'column_{column}', 
                'label': 'hasColumn'
            })
        
        logger.info(f"BUILD GRAPH: Added {len(nodes)-1} column nodes, highlighted: {highlight_column}")
        
        # Row and Cell nodes with highlighting
        for row_id in sampled_row_ids:
            is_highlighted_row = row_id == highlight_row
            nodes.append({
                'id': f'row_{row_id}', 
                'label': f'Row {row_id}', 
                'type': 'row',
                # Highlight the selected row with a brighter color
                'color': '#ff5733' if is_highlighted_row else '#dc2626',
                'shape': 'ellipse',
                'highlighted': is_highlighted_row
            })
            links.append({
                'from': f'dataset_{dataset_name}', 
                'to': f'row_{row_id}', 
                'label': 'hasRow'
            })
            
            for column in rows[row_id]:
                cell_id = f'cell_{row_id}_{column}'
                cell_value = cell_values.get((row_id, column), "")
                
                # Determine if this cell should be highlighted (both row and column match)
                is_highlighted_cell = (column == highlight_column) or (row_id == highlight_row)
                is_doubly_highlighted = (column == highlight_column) and (row_id == highlight_row)
                
                nodes.append({
                    'id': cell_id,
                    'label': str(cell_value)[:20] + ('...' if len(str(cell_value)) > 20 else ''),
                    'type': 'cell', 
                    # Different colors for different highlight states
                    'color': '#ff3366' if is_doubly_highlighted else 
                             '#ff9966' if is_highlighted_cell else '#7c3aed',
                    'shape': 'dot',
                    'highlighted': is_highlighted_cell,
                    'value': cell_value
                })
                
                links.append({
                    'from': f'row_{row_id}', 
                    'to': cell_id, 
                    'label': column
                })
                links.append({
                    'from': f'column_{column}', 
                    'to': cell_id, 
                    'label': 'contains'
                })
        
        result = {
            'nodes': nodes, 
            'links': links, 
            'dataset_name': dataset_name,
            'row_count': len(all_row_ids), 
            'column_count': len(columns),
            'highlighted_column': highlight_column,
            'highlighted_row': highlight_row
        }
        
        logger.info(f"BUILD GRAPH: Completed for {source}/{dataset_name} with {len(nodes)} nodes, {len(links)} links")
        return result
        
    except Exception as e:
        logger.error(f"BUILD GRAPH: Error for {source}/{dataset_name}: {e}", exc_info=True)
        return {
            'nodes': [], 'links': [], 'dataset_name': dataset_name
        }



def refresh_graph(request):
    """Refresh the graph data for a dataset."""
    source = request.POST.get('source', '')
    dataset = request.POST.get('dataset', '')
    
    if not source or not dataset:
        return JsonResponse({'error': 'Missing source or dataset parameters'}, status=400)
    
    try:
        # Build graph data with the same function used for highlight
        graph_data = _build_graph_with_highlight(source, dataset)
        
        return render(request, 'partials/graph_visualization.html', {
            'graph_data': graph_data
        })
    except Exception as e:
        logger.error(f"Error refreshing graph: {e}")
        return JsonResponse({'error': str(e)}, status=500)



def toggle_layout(request):
    """Toggle between different graph layout options."""
    source = request.POST.get('source', '')
    dataset = request.POST.get('dataset', '')
    
    if not source or not dataset:
        return JsonResponse({'error': 'Missing source or dataset parameters'}, status=400)
    
    try:
        # Get the current layout type from the request or default to 'hierarchical'
        layout_type = request.POST.get('layout', 'hierarchical')
        
        # Build graph data
        graph_data = _build_graph_with_highlight(source, dataset)
        
        # Add layout information to the graph data
        graph_data['layout'] = 'force' if layout_type == 'hierarchical' else 'hierarchical'
        
        return render(request, 'partials/graph_visualization.html', {
            'graph_data': graph_data,
            'layout': graph_data['layout']
        })
    except Exception as e:
        logger.error(f"Error toggling layout: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def _build_comprehensive_source_graph(source, datasets_data):
    """
    Build a lightweight graph with ONLY source, datasets, and columns.
    No individual cells or rows - just the structure needed for column highlighting.
    """
    logger.info(f"COMPREHENSIVE GRAPH: Starting lightweight graph for source={source} with {len(datasets_data)} datasets")
    print(f"COMPREHENSIVE GRAPH: Starting lightweight graph for source={source} with {len(datasets_data)} datasets")
    
    try:
        nodes = []
        links = []
        
        # Source node (root)
        nodes.append({
            'id': f'source_{source}',
            'label': source,
            'type': 'source',
            'color': '#1e40af',
            'shape': 'star',
            'size': 35
        })
        
        # Limit datasets to prevent graph explosion
        limited_datasets = datasets_data[:20]  # Max 20 datasets
        if len(datasets_data) > 20:
            logger.info(f"COMPREHENSIVE GRAPH: Limited datasets from {len(datasets_data)} to 20")
            print(f"COMPREHENSIVE GRAPH: Limited datasets from {len(datasets_data)} to 20")
        
        # Process each dataset
        for dataset_info in limited_datasets:
            dataset_name = dataset_info['name']
            
            # Dataset node
            dataset_id = f'dataset_{dataset_name}'
            nodes.append({
                'id': dataset_id,
                'label': dataset_name,
                'type': 'dataset',
                'color': '#2563eb',
                'shape': 'diamond',
                'size': 28,
                'cell_count': dataset_info.get('cell_count', 0)
            })
            
            # Link source to dataset
            links.append({
                'from': f'source_{source}',
                'to': dataset_id,
                'label': 'contains',
                'color': '#1e40af'
            })
            
            # Get ONLY column names (no cells or rows)
            logger.info(f"COMPREHENSIVE GRAPH: Getting columns for dataset {dataset_name}")
            
            # Query for column information by looking at unique column names from cell URIs
            # Use DISTINCT and LIMIT to get only unique column names efficiently
            cell_uris = Resource.objects.filter(
                source=source,
                uri__contains=f'/datasets/{dataset_name}/',
                resource_type=ResourceType.IRI
            ).exclude(
                Q(uri__contains='/columns/') | Q(uri__contains='/rows/')
            ).values_list('uri', flat=True)[:50]  # Only sample 50 cells to extract column names
            
            # Extract unique column names
            columns = set()
            for uri in cell_uris:
                parts = uri.split('/')
                if len(parts) >= 3:
                    column_name = parts[-2]  # Second to last part is column name
                    columns.add(column_name)
                    
                # Limit columns per dataset to prevent explosion
                if len(columns) >= 20:  # Max 20 columns per dataset
                    break
            
            logger.info(f"COMPREHENSIVE GRAPH: Found {len(columns)} columns for {dataset_name}")
            print(f"COMPREHENSIVE GRAPH: Found {len(columns)} columns for {dataset_name}")
            
            # Add column nodes (using unique IDs per dataset)
            for column_name in sorted(columns):
                column_id = f'column_{dataset_name}_{column_name}'  # Unique ID per dataset
                nodes.append({
                    'id': column_id,
                    'label': column_name,
                    'type': 'column',
                    'color': '#059669',
                    'shape': 'box',
                    'size': 20,
                    'dataset': dataset_name,
                    'column': column_name
                })
                
                # Link dataset to column
                links.append({
                    'from': dataset_id,
                    'to': column_id,
                    'label': 'hasColumn',
                    'color': '#2563eb'
                })
        
        result = {
            'nodes': nodes,
            'links': links,
            'source': source,
            'dataset_count': len(limited_datasets),
            'total_nodes': len(nodes),
            'total_links': len(links)
        }
        
        logger.info(f"COMPREHENSIVE GRAPH: Completed lightweight graph with {len(nodes)} nodes, {len(links)} links")
        print(f"COMPREHENSIVE GRAPH: Completed lightweight graph with {len(nodes)} nodes, {len(links)} links")
        
        return result
        
    except Exception as e:
        logger.error(f"COMPREHENSIVE GRAPH: Error building lightweight graph: {e}", exc_info=True)
        print(f"COMPREHENSIVE GRAPH: Error building lightweight graph: {e}")
        return {
            'nodes': [],
            'links': [],
            'source': source,
            'error': str(e)
        }


  
def analyze_dataset_relationships(request):
    """Analyze relationships within a dataset and return relationship matrix."""
    source = request.GET.get('source', '')
    dataset_name = request.GET.get('dataset_name', '')
    
    if not source or not dataset_name:
        return HttpResponseBadRequest("Missing source or dataset_name")
    
    try:
        # Initialize services
        relationship_service = RelationshipDiscoveryService(None)
        
        # Create a temporary CSV file for analysis
        # For now, we'll create a simple dataset from our Resource data
        temp_analysis = _create_temp_dataset_analysis(source, dataset_name)
        
        if not temp_analysis:
            return render(request, 'partials/relationship_matrix.html', {
                'error': 'Could not analyze dataset relationships',
                'dataset_name': dataset_name
            })
        
        # Prepare context for template
        context = {
            'dataset_name': dataset_name,
            'source': source,
            'analysis': temp_analysis,
            'columns': temp_analysis.get('columns', []),
            'relationships': temp_analysis.get('relationships', []),
            'relationship_matrix': temp_analysis.get('relationship_matrix', {}),
            'relationship_details': temp_analysis.get('relationship_details', {})
        }
        
        return render(request, 'partials/relationship_matrix.html', context)
        
    except Exception as e:
        logger.error(f"Error analyzing dataset relationships: {e}", exc_info=True)
        return render(request, 'partials/relationship_matrix.html', {
            'error': f"Error analyzing relationships: {str(e)}",
            'dataset_name': dataset_name
        })


def _create_temp_dataset_analysis(source, dataset_name):
    """Create a temporary analysis of dataset relationships based on existing data."""
    try:
        # Get preview data to understand column structure
        preview_data = _get_dataset_preview_optimized(source, dataset_name, max_rows=100)
        
        if not preview_data or not preview_data.get('colHeaders'):
            return None
        
        columns = preview_data['colHeaders']
        
        # Create mock relationships based on column name similarity and patterns
        relationships = []
        relationship_matrix = {}
        relationship_details = {}
        
        # Initialize matrix with zeros
        for col1 in columns:
            for col2 in columns:
                relationship_matrix[f"{col1}-{col2}"] = 0.0
        
        # Simple semantic similarity analysis
        semantic_groups = {
            'identifier': ['id', 'key', 'uuid', 'code', 'ref'],
            'person': ['person', 'author', 'creator', 'artist', 'name'],
            'place': ['place', 'location', 'city', 'country', 'site'],
            'time': ['date', 'time', 'year', 'created', 'modified'],
            'description': ['title', 'description', 'text', 'label', 'note']
        }
        
        # Find semantically related columns
        column_semantics = {}
        for col in columns:
            col_lower = col.lower()
            for semantic_type, keywords in semantic_groups.items():
                for keyword in keywords:
                    if keyword in col_lower:
                        if col not in column_semantics:
                            column_semantics[col] = []
                        column_semantics[col].append(semantic_type)
        
        # Create relationships
        for i, col1 in enumerate(columns):
            for j, col2 in enumerate(columns):
                if i != j:
                    confidence = 0.0
                    relationship_type = None
                    evidence = {}
                    
                    # Check semantic similarity
                    if col1 in column_semantics and col2 in column_semantics:
                        common_semantics = set(column_semantics[col1]) & set(column_semantics[col2])
                        if common_semantics:
                            confidence = len(common_semantics) / max(len(column_semantics[col1]), len(column_semantics[col2]))
                            relationship_type = 'semantic_similar'
                            evidence = {'common_semantics': list(common_semantics)}
                    
                    # Check name similarity (simple character overlap)
                    if confidence == 0:
                        col1_lower = col1.lower()
                        col2_lower = col2.lower()
                        
                        # Simple substring matching
                        if col1_lower in col2_lower or col2_lower in col1_lower:
                            confidence = 0.7
                            relationship_type = 'pattern_match'
                            evidence = {'name_similarity': 'substring_match'}
                        elif len(set(col1_lower) & set(col2_lower)) / len(set(col1_lower) | set(col2_lower)) > 0.5:
                            confidence = 0.4
                            relationship_type = 'pattern_match'
                            evidence = {'name_similarity': 'character_overlap'}
                    
                    if confidence > 0.1:  # Only include relationships with some confidence
                        relationship = {
                            'source_column': col1,
                            'target_column': col2,
                            'relationship_type': relationship_type,
                            'confidence': confidence,
                            'evidence': evidence,
                            'suggested_predicate': 'dcterms:relation',
                            'bidirectional': True
                        }
                        relationships.append(relationship)
                        relationship_matrix[f"{col1}-{col2}"] = confidence
                        relationship_details[f"{col1}-{col2}"] = relationship
        
        # Calculate quality metrics
        total_possible = len(columns) * (len(columns) - 1) / 2
        high_confidence = len([r for r in relationships if r['confidence'] > 0.7])
        avg_confidence = sum(r['confidence'] for r in relationships) / len(relationships) if relationships else 0
        
        quality_metrics = {
            'coverage': len(relationships) / total_possible if total_possible > 0 else 0,
            'average_confidence': avg_confidence,
            'high_confidence_ratio': high_confidence / len(relationships) if relationships else 0,
            'total_relationships': len(relationships)
        }
        
        # Find semantic clusters (simple grouping by semantic type)
        semantic_clusters = []
        for semantic_type in semantic_groups.keys():
            cluster_columns = [col for col, semantics in column_semantics.items() if semantic_type in semantics]
            if len(cluster_columns) > 1:
                semantic_clusters.append(cluster_columns)
        
        return {
            'dataset_name': dataset_name,
            'column_count': len(columns),
            'row_count': preview_data.get('total_rows', 0),
            'columns': columns,
            'relationships': relationships,
            'relationship_matrix': relationship_matrix,
            'relationship_details': relationship_details,
            'semantic_clusters': semantic_clusters,
            'quality_metrics': quality_metrics
        }
        
    except Exception as e:
        logger.error(f"Error creating temp analysis: {e}")
        return None 