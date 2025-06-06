from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Q, Count, Prefetch
from django.core.cache import cache
import logging
from collections import defaultdict

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)


@login_required
def split_table_graph_view(request):
    """Split view showing all datasets from a source with table previews and graph visualization."""
    
    # OPTIMIZATION: Use database aggregation instead of Python processing
    sources_with_datasets = Resource.objects.filter(
        uri__contains='/datasets/',
        resource_type=ResourceType.IRI
    ).exclude(
        uri__contains='/columns/'
    ).exclude(
        uri__contains='/rows/'
    ).values('source').annotate(
        resource_count=Count('id')
    ).order_by('source')
    
    # Get dataset counts per source efficiently
    sources_info = []
    for source_data in sources_with_datasets:
        source = source_data['source']
        
        # Count unique datasets using database aggregation
        dataset_count = Resource.objects.filter(
            source=source,
            uri__contains='/datasets/',
            resource_type=ResourceType.IRI
        ).exclude(
            uri__contains='/columns/'
        ).exclude(
            uri__contains='/rows/'
        ).extra(
            select={'dataset_name': "SUBSTRING(uri FROM '.*/datasets/([^/]+)/.*')"}
        ).values('dataset_name').distinct().count()
        
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
            'colHeaders': sorted_columns, 'data': [], 'showing_rows': 0, 
            'total_rows': total_rows, 'offset': offset, 'has_more': False
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
        'has_more': offset + len(table_data) < total_rows
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


@login_required
def load_source_data(request):
    """HTMX endpoint to load source data."""
    source = request.GET.get('source', '')
    
    if not source:
        return render(request, 'partials/empty_state.html')
    
    # Use optimized dataset fetching
    datasets_data = _get_all_datasets_for_source_optimized(source)
    
    # Build simple graph nodes
    graph_nodes = []
    for dataset in datasets_data:
        graph_nodes.append({
            'id': f"dataset_{dataset['name']}",
            'label': dataset['name'],
            'type': 'dataset',
            'cell_count': dataset.get('cell_count', 0)
        })
    
    # Don't generate previews here - load them on demand
    cached_data = {
        'source': source,
        'datasets': datasets_data,
        'graph_nodes': graph_nodes,
        'graph_edges': []
    }
    
    return render(request, 'partials/source_data.html', cached_data)


@login_required
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

    dataset = {
        'name': dataset_name,
        'source': source,
        'cell_count': cell_count,
        'preview': _get_dataset_preview_optimized(source, dataset_name, max_rows=5)
    }

    return render(request, 'partials/dataset_card.html', {'dataset': dataset})


@login_required
def get_graph_data(request):
    """Generate graph data for visualization."""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    
    if not source:
        return JsonResponse({'error': 'Source parameter required'}, status=400)
    
    try:
        if dataset:
            graph_data = _build_single_dataset_graph_data_optimized(source, dataset)
        else:
            graph_data = {
                'nodes': [],
                'links': [],
                'message': 'Select a dataset to view its graph'
            }
        
        return render(request, 'partials/graph_visualization.html', {'graph_data': graph_data})
    except Exception as e:
        logger.error(f"Error generating graph data: {e}")
        return render(request, 'partials/graph_visualization.html', {
            'error': str(e),
            'graph_data': {'nodes': [], 'links': []}
        })


@login_required
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
            'data': preview_data['data']
        })
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}")
        return render(request, 'partials/table_rows.html', {'data': []})


@login_required
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