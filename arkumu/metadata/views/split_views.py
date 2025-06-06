from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.cache import cache
import json
import logging
from hashlib import md5
import re

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)


@login_required
def split_table_graph_view(request):
    """Split view showing all datasets from a source with table previews and graph visualization."""
    
    logger.info("STEP 0: Starting split_table_graph_view")
    
    # Database inspection for debugging
    total_resources = Resource.objects.count()
    total_triples = Triple.objects.count()
    logger.info(f"STEP 0.1: Database contains {total_resources} resources and {total_triples} triples")
    
    # Show resource type breakdown
    resource_types = Resource.objects.values('resource_type').annotate(count=Count('resource_type'))
    logger.info(f"STEP 0.2: Resource types: {dict((r['resource_type'], r['count']) for r in resource_types)}")
    
    # Show some sample resource URIs
    sample_resources = Resource.objects.all()[:10]
    logger.info(f"STEP 0.3: Sample resource URIs:")
    for i, res in enumerate(sample_resources):
        logger.info(f"STEP 0.3.{i+1}: {res.uri} (type: {res.resource_type}, source: {res.source})")
    
    # Get available sources with dataset counts (using cell resources to find sources)
    logger.info("STEP 0.4: Looking for sources with cell resources")
    sources_with_cells = Resource.objects.filter(
        uri__contains='/datasets/',
        uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
        resource_type=ResourceType.IRI
    ).values('source').annotate(
        cell_count=Count('id')
    ).order_by('source')
    
    logger.info(f"STEP 0.5: Found {sources_with_cells.count()} sources with cell resources")
    
    # Get unique dataset names per source for counting
    sources_info = []
    for source_data in sources_with_cells:
        source = source_data['source']
        logger.info(f"STEP 0.6: Processing source '{source}' with {source_data['cell_count']} cells")
        
        # Get cell resources for this source to extract dataset names
        cell_resources = Resource.objects.filter(
            source=source,
            uri__contains='/datasets/',
            uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
            resource_type=ResourceType.IRI
        )
        
        logger.info(f"STEP 0.6.1: Found {cell_resources.count()} cell resources for source '{source}'")
        
        # Extract unique dataset names from cell URIs
        dataset_names = set()
        for cell in cell_resources:  # Process all cells to find all datasets
            try:
                # Parse URI: {source}/datasets/{dataset_name}/{column_name}/{row_id}
                uri_parts = cell.uri.split('/')
                if 'datasets' in uri_parts:
                    datasets_index = uri_parts.index('datasets')
                    if datasets_index + 1 < len(uri_parts):
                        dataset_name = uri_parts[datasets_index + 1]
                dataset_names.add(dataset_name)
            except (IndexError, ValueError):
                continue
        
        sources_info.append({
            'name': source,
            'dataset_count': len(dataset_names),
            'display_name': f"{source} ({len(dataset_names)} dataset{'s' if len(dataset_names) != 1 else ''})"
        })
        
        logger.info(f"STEP 0.6.2: Source '{source}' has datasets: {sorted(list(dataset_names))}")
    
    logger.info(f"STEP 0.7: Final sources list: {[s['name'] for s in sources_info]}")
    
    context = {
        'sources': sources_info,
        'selected_source': request.GET.get('source', ''),
    }
    
    return render(request, 'split_table_graph.html', context)


@login_required
def get_table_data(request):
    """Get table data for multiple datasets from a source with 5-row previews."""
    source = request.GET.get('source', '')
    
    if not source:
        return JsonResponse({'error': 'No source specified'}, status=400)
    
    # Check cache first
    cache_key = f"table_data:{md5(source.encode()).hexdigest()}"
    datasets_data = cache.get(cache_key)
    
    if datasets_data is None:
        # Get all datasets for this source
        datasets_data = _get_all_datasets_for_source(source)
        # Cache for 5 minutes
        cache.set(cache_key, datasets_data, 300)
    
    return JsonResponse({'datasets': datasets_data})


@login_required
def get_dataset_preview(request):
    """Get preview of dataset data for table view"""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    
    if not source or not dataset:
        return JsonResponse({'error': 'Missing source or dataset parameter'}, status=400)
    
    table_data = _reconstruct_table_from_graph(source)
    
    return JsonResponse({
        'config': table_data
    })


@login_required
def load_more_dataset_rows(request):
    """Load more rows for a dataset with pagination"""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 20))
    
    if not source or not dataset:
        return render(request, 'partials/table_rows.html', {'data': []})
    
    logger.info(f"Loading more rows for {source}/{dataset} - offset: {offset}, limit: {limit}")
    
    try:
        preview_data = _get_dataset_preview(source, dataset, max_rows=limit, offset=offset)
        
        if not preview_data:
            return render(request, 'partials/table_rows.html', {'data': []})
        
        return render(request, 'partials/table_rows.html', {
            'data': preview_data['data']
        })
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}")
        return render(request, 'partials/table_rows.html', {'data': []})


@login_required
def get_all_dataset_previews(request):
    """Get 5-row previews for all datasets in a source at once."""
    source = request.GET.get('source', '')
    
    if not source:
        return JsonResponse({'error': 'No source specified'}, status=400)
    
    # Check cache first
    cache_key = f"all_previews:{md5(source.encode()).hexdigest()}"
    all_previews = cache.get(cache_key)
    
    if all_previews is None:
        # Get all datasets for this source
        datasets_data = _get_all_datasets_for_source(source)
        
        # Generate previews for each dataset
        all_previews = {}
        for dataset in datasets_data:
            dataset_name = dataset['name']
            preview_data = _get_dataset_preview(source, dataset_name, max_rows=5)
            all_previews[dataset_name] = preview_data
        
        # Cache for 10 minutes
        cache.set(cache_key, all_previews, 600)
    
    return JsonResponse({'previews': all_previews})


@login_required
def load_source_data(request):
    """HTMX endpoint to load source data and render split view."""
    source = request.GET.get('source', '')
    
    logger.info(f"STEP 1: Loading source data - source parameter: '{source}'")
    
    if not source:
        logger.warning("STEP 1.1: No source provided, returning empty state")
        return render(request, 'partials/empty_state.html')
    
    logger.info(f"STEP 2: Cache disabled - building fresh data")
    # Cache disabled temporarily for debugging
    cached_data = None
    
    if True:  # Always build fresh data
        logger.info("STEP 2.1: No cached data found, building fresh data")
        
        logger.info("STEP 3: Getting all datasets for source")
        # Get all datasets for this source
        datasets_data = _get_all_datasets_for_source(source)
        logger.info(f"STEP 3.1: Found {len(datasets_data)} datasets: {[d.get('name', 'unnamed') for d in datasets_data]}")
        
        # Get simple graph data (nodes and relationships)
        graph_nodes = []
        graph_edges = []
        
        logger.info("STEP 4: Building simple dataset nodes")
        # Build simple dataset nodes
        for i, dataset in enumerate(datasets_data):
            dataset_name = dataset.get('name', f'unnamed_{i}')
            logger.info(f"STEP 4.{i+1}: Creating node for dataset '{dataset_name}' with {dataset.get('cell_count', 0)} cells")
            graph_nodes.append({
                'id': f"dataset_{dataset_name}",
                'label': dataset_name,
                'type': 'dataset',
                'cell_count': dataset.get('cell_count', 0)
            })
        
        logger.info("STEP 5: Generating table previews for datasets")
        # Generate table previews and attach to datasets
        for i, dataset in enumerate(datasets_data):
            dataset_name = dataset['name']
            logger.info(f"STEP 5.{i+1}: Getting preview for dataset '{dataset_name}'")
            preview_data = _get_dataset_preview(source, dataset_name, max_rows=5)
            logger.info(f"STEP 5.{i+1}.1: Preview data for '{dataset_name}': {len(preview_data.get('data', []))} rows, {len(preview_data.get('colHeaders', []))} columns")
            dataset['preview'] = preview_data
        
        cached_data = {
            'source': source,
            'datasets': datasets_data,
            'graph_nodes': graph_nodes,
            'graph_edges': graph_edges
        }
        
        logger.info(f"STEP 6: Cache disabled - not caching data for source '{source}' with {len(datasets_data)} datasets")
        # Cache disabled temporarily for debugging
    
    logger.info(f"STEP 7: Rendering source_data.html template with {len(cached_data.get('datasets', []))} datasets")
    return render(request, 'partials/source_data.html', cached_data)


@login_required  
def get_graph_data(request):
    """Generate graph data for visualization"""
    source = request.GET.get('source')
    dataset = request.GET.get('dataset')  # New parameter for specific dataset
    
    logger.info(f"STEP 8: Getting graph data - source: '{source}', dataset: '{dataset}'")
    
    if not source:
        logger.warning("STEP 8.1: No source parameter provided")
        return JsonResponse({'error': 'Source parameter required'}, status=400)
    
    try:
        if dataset:
            logger.info(f"STEP 8.2: Loading graph for specific dataset '{dataset}'")
            # Load graph for specific dataset only
            graph_data = _build_single_dataset_graph_data(source, dataset)
            logger.info(f"STEP 8.2.1: Single dataset graph data: {len(graph_data.get('nodes', []))} nodes, {len(graph_data.get('links', []))} links")
        else:
            logger.info(f"STEP 8.3: Loading graph for all datasets in source '{source}'")
            # Load all datasets for source (fallback behavior)
            graph_data = _build_graph_data(source)
            logger.info(f"STEP 8.3.1: All datasets graph data: {len(graph_data.get('nodes', []))} nodes, {len(graph_data.get('links', []))} links")
        
        logger.info(f"STEP 8.4: Rendering graph visualization template")
        return render(request, 'partials/graph_visualization.html', {'graph_data': graph_data})
    except Exception as e:
        logger.error(f"STEP 8.ERROR: Error generating graph data: {e}")
        import traceback
        logger.error(f"STEP 8.ERROR.1: Traceback: {traceback.format_exc()}")
        return render(request, 'partials/graph_visualization.html', {
            'error': str(e),
            'graph_data': {'nodes': [], 'links': []}
        })


def _reconstruct_table_from_graph(source):
    """Reconstruct table structure from graph data for a given source."""
    
    # Find dataset resources for this source (URI pattern: .../datasets/...)
    dataset_resources = Resource.objects.filter(
        source=source,
        uri__contains='/datasets/',
        resource_type=ResourceType.IRI
    ).exclude(uri__contains='/columns/').exclude(uri__contains='/rows/')
    
    if not dataset_resources.exists():
        # If no datasets found, return basic structure
        return _build_basic_table_structure(source)
    
    # For now, take the first dataset (you might want to show a list later)
    dataset_resource = dataset_resources.first()
    dataset_name = _extract_dataset_name_from_uri(dataset_resource.uri)
    
    if not dataset_name:
        return _build_basic_table_structure(source)
    
    # Find cell resources for this dataset (URI pattern: .../datasets/{name}/{column}/{row})
    cell_resources = Resource.objects.filter(
        source=source,
        uri__contains=f'/datasets/{dataset_name}/',
        resource_type=ResourceType.IRI
    ).exclude(uri__contains='/columns/').exclude(uri__contains='/rows/')
    
    if not cell_resources.exists():
        return _build_basic_table_structure(source)
    
    # Extract table data from cell resources
    rows_data, columns_data = _extract_table_data_from_cells(cell_resources, dataset_name)
    
    # Build table structure
    table_structure = {
        'data': rows_data,
        'columns': columns_data,
        'colHeaders': [col['title'] for col in columns_data],
        'rowHeaders': True,
        'width': '100%',
        'height': '400px',
        'stretchH': 'all',
        'contextMenu': True,
        'manualColumnResize': True,
        'manualRowResize': True,
        'filters': True,
        'dropdownMenu': True,
        'hiddenColumns': {
            'indicators': True
        },
        'licenseKey': 'non-commercial-and-evaluation'
    }
    
    return table_structure


def _extract_dataset_name_from_uri(uri):
    """Extract dataset name from dataset URI."""
    # URI pattern: {base_uri}/{institution}/datasets/{dataset_name}
    try:
        parts = uri.split('/')
        if 'datasets' in parts:
            datasets_index = parts.index('datasets')
            if datasets_index + 1 < len(parts):
                return parts[datasets_index + 1]
    except (IndexError, ValueError):
        pass
    return None


def _extract_table_data_from_cells(cell_resources, dataset_name, max_rows=None):
    """Extract table data from cell resources."""
    
    # Parse all cell URIs to get structure
    cell_data = {}  # {row_id: {column_name: value}}
    all_columns = set()
    
    for cell in cell_resources:
        # Parse URI: .../datasets/{dataset_name}/{column_name}/{row_id}
        try:
            parts = cell.uri.split('/')
            if 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 3 < len(parts):
                    found_dataset = parts[datasets_index + 1]
                    if found_dataset == dataset_name:
                        column_name = parts[datasets_index + 2]
                        row_id = parts[datasets_index + 3]
                        
                        # Get the actual value via rdf:value triple
                        value = _get_cell_value(cell)
                        
                        if row_id not in cell_data:
                            cell_data[row_id] = {}
                        
                        cell_data[row_id][column_name] = value
                        all_columns.add(column_name)
        except (IndexError, ValueError) as e:
            logger.warning(f"Could not parse cell URI: {cell.uri} - {e}")
            continue
    
    # Sort columns and rows for consistent display
    sorted_columns = sorted(all_columns)
    sorted_rows = sorted(cell_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
    
    # Apply row limit if specified
    if max_rows is not None:
        sorted_rows = sorted_rows[:max_rows]
    
    # Build rows data
    rows_data = []
    for row_id in sorted_rows:
        row_data = {}
        for column_name in sorted_columns:
            row_data[column_name] = cell_data[row_id].get(column_name, '')
        rows_data.append(row_data)
    
    # Build columns data
    columns_data = []
    for column_name in sorted_columns:
        columns_data.append({
            'data': column_name,
            'title': column_name,
            'type': 'text',
            'width': 120
        })
    
    return rows_data, columns_data


def _get_cell_value(cell_resource):
    """Get the actual value of a cell via rdf:value triple."""
    try:
        # Look for rdf:value triple where this cell is the subject
        value_triple = Triple.objects.filter(
            subject=cell_resource,
            predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
        ).first()
        
        if value_triple and value_triple.object:
            return value_triple.object.value or ''
        
        # Fallback to cell resource's own value if no triple found
        return cell_resource.value or ''
        
    except Exception as e:
        logger.warning(f"Error getting value for cell {cell_resource.uri}: {e}")
        return ''


def _get_all_datasets_for_source(source):
    """Get all datasets for a given source using Django ORM"""
    logger.info(f"STEP 3.1: Finding datasets for source '{source}'")
    
    try:
        # Find all cell resources for this source and extract unique dataset names
        # Cell URI pattern: http://arkumu.org/data/{source}/datasets/{dataset_name}/{column_name}/{row_id}
        logger.info(f"STEP 3.1.1: Searching for cell resources with source '{source}' and pattern '/datasets/*'")
        cell_resources = Resource.objects.filter(
            source=source,
            uri__contains="/datasets/",
            uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
            resource_type=ResourceType.IRI
        )
        
        cell_count = cell_resources.count()
        logger.info(f"STEP 3.1.2: Found {cell_count} cell resources")
        
        if cell_count == 0:
            logger.warning(f"STEP 3.1.3: No cell resources found for source '{source}'")
            # Let's check what resources we actually have for this source
            all_source_resources = Resource.objects.filter(uri__startswith=source)
            logger.warning(f"STEP 3.1.3.1: Total resources for source: {all_source_resources.count()}")
            for i, res in enumerate(all_source_resources[:10]):  # Log first 10
                logger.debug(f"STEP 3.1.3.1.{i+1}: Resource URI: {res.uri}, Type: {res.resource_type}")
            return []
        
        # Extract unique dataset names from cell URIs
        logger.info(f"STEP 3.1.4: Extracting dataset names from {cell_count} cell URIs")
        dataset_names = set()
        
        for cell in cell_resources:  # Process all cells to find all datasets
            try:
                # Parse URI: {source}/datasets/{dataset_name}/{column_name}/{row_id}
                uri_parts = cell.uri.split('/')
                if 'datasets' in uri_parts:
                    datasets_index = uri_parts.index('datasets')
                    if datasets_index + 1 < len(uri_parts):
                        dataset_name = uri_parts[datasets_index + 1]
                        dataset_names.add(dataset_name)
            except (IndexError, ValueError) as e:
                logger.debug(f"STEP 3.1.4.X: Could not parse cell URI: {cell.uri} - {e}")
                continue
        
        logger.info(f"STEP 3.1.5: Found {len(dataset_names)} unique datasets: {sorted(list(dataset_names))}")
        
        # Build dataset info for each unique dataset
        datasets = []
        for i, dataset_name in enumerate(sorted(dataset_names)):
            logger.info(f"STEP 3.2.{i+1}: Processing dataset '{dataset_name}'")
            
            # Count cells for this specific dataset
            dataset_cell_count = Resource.objects.filter(
                source=source,
                uri__contains=f"/datasets/{dataset_name}/",
                uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
                resource_type=ResourceType.IRI
            ).count()
            logger.info(f"STEP 3.2.{i+1}.1: Found {dataset_cell_count} cells for dataset '{dataset_name}'")
            
            # Get preview data for this dataset
            logger.info(f"STEP 3.2.{i+1}.2: Getting preview for dataset '{dataset_name}'")
            preview = _get_dataset_preview(source, dataset_name)
            logger.info(f"STEP 3.2.{i+1}.3: Preview result for '{dataset_name}': {preview is not None}")
            if preview:
                logger.info(f"STEP 3.2.{i+1}.3.1: Preview has {len(preview.get('data', []))} rows and {len(preview.get('colHeaders', []))} columns")
            
            datasets.append({
                'name': dataset_name,
                'source': source,
                'cell_count': dataset_cell_count,
                'preview': preview
            })
        
        logger.info(f"STEP 3.3: Returning {len(datasets)} datasets with total cells: {sum(d['cell_count'] for d in datasets)}")
        return datasets
    except Exception as e:
        logger.error(f"STEP 3.ERROR: Error getting datasets for source {source}: {e}")
        import traceback
        logger.error(f"STEP 3.ERROR.1: Traceback: {traceback.format_exc()}")
        return []


def _get_dataset_preview(source, dataset_name, max_rows=5, offset=0):
    """Get preview data for a dataset using Django ORM with efficient pagination"""
    logger.info(f"STEP 5.X: Getting preview for dataset '{dataset_name}' from source '{source}' (max_rows={max_rows}, offset={offset})")
    
    try:
        # First, get a limited set of row IDs to minimize data fetching
        logger.info(f"STEP 5.X.1: Finding row IDs for dataset '{dataset_name}' with pagination")
        
        # Get unique row IDs from cell URIs efficiently
        cell_uris = Resource.objects.filter(
            source=source,
            uri__contains=f"/datasets/{dataset_name}/",
            uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
            resource_type=ResourceType.IRI
        ).values_list('uri', flat=True)[:1000]  # Limit initial URI fetch
        
        # Extract row IDs from URIs
        row_ids = set()
        for uri in cell_uris:
            try:
                row_id = uri.split('/')[-1]
                row_ids.add(row_id)
            except:
                continue
        
        # Sort and paginate row IDs
        sorted_row_ids = sorted(list(row_ids))
        paginated_row_ids = sorted_row_ids[offset:offset + max_rows]
        
        logger.info(f"STEP 5.X.2: Found {len(row_ids)} total rows, showing {len(paginated_row_ids)} rows (offset={offset})")
        
        if not paginated_row_ids:
            logger.warning(f"STEP 5.X.3: No rows found for dataset '{dataset_name}' at offset {offset}")
            return None
        
        # Get only cells for the specific rows we want to display
        row_specific_cells = []
        for row_id in paginated_row_ids:
            cells = Resource.objects.filter(
                source=source,
                uri__contains=f"/datasets/{dataset_name}/",
                uri__endswith=f"/{row_id}",
                resource_type=ResourceType.IRI
            )
            row_specific_cells.extend(cells)
        
        logger.info(f"STEP 5.X.4: Found {len(row_specific_cells)} cells for {len(paginated_row_ids)} rows")
        
        # Get the rdf:value property
        logger.info(f"STEP 5.X.5: Looking for rdf:value property")
        rdf_value_prop = Resource.objects.filter(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        if not rdf_value_prop:
            logger.warning(f"STEP 5.X.6: rdf:value property not found")
            return None
        else:
            logger.info(f"STEP 5.X.6: Found rdf:value property: {rdf_value_prop.uri}")
        
        # Get cell values through rdf:value triples - only for our limited cell set
        logger.info(f"STEP 5.X.7: Querying triples for cell values (limited set)")
        cell_data = {}
        value_triples = Triple.objects.filter(
            subject__in=row_specific_cells,
            predicate=rdf_value_prop
        ).select_related('subject', 'object')
        
        triple_count = value_triples.count()
        logger.info(f"STEP 5.X.8: Found {triple_count} value triples for {len(paginated_row_ids)} rows")
        
        columns = set()
        
        for triple in value_triples:
            cell_uri = triple.subject.uri
            cell_value = triple.object.value if triple.object else ""
            
            # Parse cell URI: {source}/datasets/{dataset_name}/{column_name}/{row_id}
            uri_parts = cell_uri.split('/')
            if len(uri_parts) >= 3:
                column_name = uri_parts[-2]
                row_id = uri_parts[-1]
                
                columns.add(column_name)
                
                if row_id not in cell_data:
                    cell_data[row_id] = {}
                cell_data[row_id][column_name] = cell_value
        
        logger.info(f"STEP 5.X.9: Extracted {len(columns)} columns for dataset '{dataset_name}'")
        
        if not cell_data:
            logger.warning(f"STEP 5.X.10: No cell data extracted for dataset '{dataset_name}'")
            return None
        
        # Sort columns and use our paginated rows
        sorted_columns = sorted(list(columns))
        logger.info(f"STEP 5.X.11: Building preview with {len(sorted_columns)} columns and {len(paginated_row_ids)} rows")
        
        # Build table data in the order of our paginated row IDs
        table_data = []
        for row_id in paginated_row_ids:
            row_data = []
            for column in sorted_columns:
                cell_value = cell_data.get(row_id, {}).get(column, "")
                row_data.append(cell_value)
            table_data.append(row_data)
        
        result = {
            'colHeaders': sorted_columns,
            'data': table_data,
            'showing_rows': len(table_data),
            'total_rows': len(row_ids),
            'offset': offset,
            'has_more': offset + len(table_data) < len(row_ids)
        }
        
        logger.info(f"STEP 5.X.12: Successfully built preview for dataset '{dataset_name}': {len(sorted_columns)} cols, {len(table_data)} rows, total: {len(row_ids)}")
        return result
        
    except Exception as e:
        logger.error(f"STEP 5.X.ERROR: Error getting preview for dataset {dataset_name}: {e}")
        import traceback
        logger.error(f"STEP 5.X.ERROR.1: Traceback: {traceback.format_exc()}")
        return None


def _extract_rows_data(source):
    """Extract row data from the graph structure."""
    
    # Find all row resources
    row_resources = Resource.objects.filter(
        source=source,
        name__icontains='row'
    )
    
    rows_data = []
    
    for row_resource in row_resources:
        # Get all cells in this row through triples
        cell_triples = Triple.objects.filter(
            subject=row_resource,
            predicate__name__icontains='contains'
        ).select_related('object')
        
        row_data = {}
        for triple in cell_triples:
            cell = triple.object
            # Try to find column info for this cell
            column_triples = Triple.objects.filter(
                object=cell,
                predicate__name__icontains='column'
            ).select_related('subject')
            
            if column_triples.exists():
                column_name = column_triples.first().subject.name or f"col_{cell.id}"
                row_data[column_name] = cell.value or cell.uri
        
        if row_data:
            rows_data.append(row_data)
    
    return rows_data


def _extract_columns_data(source):
    """Extract column structure from the graph."""
    
    # Find all column resources
    column_resources = Resource.objects.filter(
        source=source,
        name__icontains='column'
    ).order_by('name')
    
    columns_data = []
    
    for i, column in enumerate(column_resources):
        columns_data.append({
            'data': column.name or f'col_{i}',
            'title': column.value or column.name or f'Column {i+1}',
            'type': 'text',
            'width': 120
        })
    
    # If no explicit columns found, create basic structure
    if not columns_data:
        columns_data = [
            {'data': 'col_0', 'title': 'Column 1', 'type': 'text'},
            {'data': 'col_1', 'title': 'Column 2', 'type': 'text'},
            {'data': 'col_2', 'title': 'Column 3', 'type': 'text'},
        ]
    
    return columns_data


def _build_basic_table_structure(source):
    """Build a basic table structure if no clear dataset structure is found."""
    
    resources = Resource.objects.filter(source=source)[:100]  # Limit for performance
    
    # Create a simple key-value table
    data = []
    for resource in resources:
        data.append({
            'uri': resource.uri or '',
            'name': resource.name or '',
            'value': resource.value or '',
            'type': resource.get_resource_type_display()
        })
    
    columns = [
        {'data': 'uri', 'title': 'URI', 'type': 'text'},
        {'data': 'name', 'title': 'Name', 'type': 'text'},
        {'data': 'value', 'title': 'Value', 'type': 'text'},
        {'data': 'type', 'title': 'Type', 'type': 'text'},
    ]
    
    return {
        'data': data,
        'columns': columns,
        'colHeaders': [col['title'] for col in columns],
        'rowHeaders': True,
        'width': '100%',
        'height': '400px',
        'stretchH': 'all',
        'contextMenu': True,
        'manualColumnResize': True,
        'manualRowResize': True,
        'filters': True,
        'dropdownMenu': True,
        'licenseKey': 'non-commercial-and-evaluation'
    }


def _build_graph_data(source):
    """Build graph data for all datasets in a source using Django ORM"""
    try:
        datasets = _get_all_datasets_for_source(source)
        
        # For now, just return empty if no specific dataset is selected
        # This encourages users to select a specific dataset
        return {
            'nodes': [],
            'links': [],
            'message': 'Select a dataset to view its graph'
        }
        
    except Exception as e:
        logger.error(f"Error building graph data for source {source}: {e}")
        return {
            'nodes': [],
            'links': []
        }


def _build_single_dataset_graph_data(source, dataset_name):
    """Build graph data for a specific dataset using Django ORM"""
    try:
        # Get the dataset resource
        dataset_uri = f"{source}/datasets/{dataset_name}"
        dataset_resource = Resource.objects.filter(
            uri=dataset_uri,
            resource_type=ResourceType.IRI
        ).first()
        
        if not dataset_resource:
            return {
                'nodes': [],
                'links': [],
                'dataset_name': dataset_name
            }
        
        # Get cell resources for this dataset
        cell_pattern = f"{source}/datasets/{dataset_name}/"
        cell_resources = Resource.objects.filter(
            uri__startswith=cell_pattern,
            uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$',  # Cell pattern
            resource_type=ResourceType.IRI
        )
        
        # Get the rdf:value property
        rdf_value_prop = Resource.objects.filter(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        if not rdf_value_prop:
            return {
                'nodes': [],
                'links': [],
                'dataset_name': dataset_name
            }
        
        # Get cell values through rdf:value triples
        value_triples = Triple.objects.filter(
            subject__in=cell_resources,
            predicate=rdf_value_prop
        ).select_related('subject', 'object')
        
        # Group cells by row and column
        rows = {}
        columns = set()
        
        for triple in value_triples:
            cell_uri = triple.subject.uri
            cell_value = triple.object.value if triple.object else ""
            
            # Parse cell URI: {source}/datasets/{dataset_name}/{column_name}/{row_id}
            uri_parts = cell_uri.split('/')
            if len(uri_parts) >= 3:
                column_name = uri_parts[-2]
                row_id = uri_parts[-1]
                
                columns.add(column_name)
                
                if row_id not in rows:
                    rows[row_id] = {}
                rows[row_id][column_name] = cell_value
        
        columns = sorted(list(columns))
        
        # Create nodes for dataset, columns, rows, and cells
        nodes = []
        links = []
        
        # Dataset node (center)
        dataset_node = {
            'id': f'dataset_{dataset_name}',
            'label': dataset_name,
            'type': 'dataset',
            'color': '#2563eb',
            'shape': 'diamond'
        }
        nodes.append(dataset_node)
        
        # Column nodes
        for column in columns:
            column_node = {
                'id': f'column_{column}',
                'label': column,
                'type': 'column',
                'color': '#059669',
                'shape': 'box'
            }
            nodes.append(column_node)
            
            # Link dataset to column
            links.append({
                'from': f'dataset_{dataset_name}',
                'to': f'column_{column}',
                'label': 'hasColumn'
            })
        
        # Sample some rows for visualization (max 10 to avoid clutter)
        sample_rows = list(rows.items())[:10]
        
        for row_id, row_data in sample_rows:
            # Row node
            row_node = {
                'id': f'row_{row_id}',
                'label': f'Row {row_id}',
                'type': 'row',
                'color': '#dc2626',
                'shape': 'ellipse'
            }
            nodes.append(row_node)
            
            # Link dataset to row
            links.append({
                'from': f'dataset_{dataset_name}',
                'to': f'row_{row_id}',
                'label': 'hasRow'
            })
            
            # Cell nodes and links
            for column, cell_value in row_data.items():
                cell_id = f'cell_{row_id}_{column}'
                cell_node = {
                    'id': cell_id,
                    'label': str(cell_value)[:20] + ('...' if len(str(cell_value)) > 20 else ''),
                    'type': 'cell',
                    'color': '#7c3aed',
                    'shape': 'dot'
                }
                nodes.append(cell_node)
                
                # Link row to cell
                links.append({
                    'from': f'row_{row_id}',
                    'to': cell_id,
                    'label': column
                })
                
                # Link column to cell
                links.append({
                    'from': f'column_{column}',
                    'to': cell_id,
                    'label': 'contains'
                })
        
        # Calculate positions for nodes
        container_width = 800
        container_height = 600
        
        # Position dataset at center
        center_x = container_width // 2
        center_y = container_height // 2
        
        for node in nodes:
            if node['type'] == 'dataset':
                node['x'] = center_x
                node['y'] = center_y
            elif node['type'] == 'column':
                # Arrange columns in a circle around dataset
                import math
                angle = (2 * math.pi * columns.index(node['label'])) / len(columns)
                radius = 200
                node['x'] = center_x + radius * math.cos(angle)
                node['y'] = center_y + radius * math.sin(angle)
            elif node['type'] == 'row':
                # Arrange rows vertically on the left
                row_index = [r[0] for r in sample_rows].index(node['label'].replace('Row ', ''))
                node['x'] = 100
                node['y'] = 100 + (row_index * 50)
            elif node['type'] == 'cell':
                # Position cells near their row
                row_id = node['id'].split('_')[1]
                row_index = [r[0] for r in sample_rows].index(row_id)
                column = node['id'].split('_')[2]
                col_index = columns.index(column)
                node['x'] = 250 + (col_index * 80)
                node['y'] = 100 + (row_index * 50)
        
        # Calculate edge positions
        processed_links = []
        for link in links:
            from_node = next((n for n in nodes if n['id'] == link['from']), None)
            to_node = next((n for n in nodes if n['id'] == link['to']), None)
            
            if from_node and to_node:
                processed_links.append({
                    'from': link['from'],
                    'to': link['to'],
                    'from_x': from_node['x'],
                    'from_y': from_node['y'],
                    'to_x': to_node['x'],
                    'to_y': to_node['y'],
                    'mid_x': (from_node['x'] + to_node['x']) // 2,
                    'mid_y': (from_node['y'] + to_node['y']) // 2,
                    'label': link.get('label', '')
                })
        
        return {
            'nodes': nodes,
            'links': processed_links,
            'dataset_name': dataset_name,
            'row_count': len(rows),
            'column_count': len(columns)
        }
        
    except Exception as e:
        logger.error(f"Error building graph data for dataset {dataset_name}: {e}")
        return {
            'nodes': [],
            'links': [],
            'dataset_name': dataset_name
        }


def _get_node_color_by_type(resource_type):
    """Get node color based on resource type."""
    colors = {
        ResourceType.IRI: '#4CAF50',      # Green
        ResourceType.CLASS: '#2196F3',    # Blue  
        ResourceType.PROPERTY: '#FF9800', # Orange
        ResourceType.LITERAL: '#9C27B0'   # Purple
    }
    return colors.get(resource_type, '#757575')  # Default gray


@login_required
def select_node(request):
    """Handle node selection via HTMX."""
    if request.method == 'POST':
        node_id = request.POST.get('node_id', '')
        node_type = request.POST.get('node_type', '')
        dataset = request.POST.get('dataset', '')
        
        context = {
            'node_id': node_id,
            'node_type': node_type,
            'dataset': dataset,
        }
        
        return render(request, 'partials/node_details.html', context)
    
    return render(request, 'partials/node_details.html', {'error': 'Invalid request'})


@login_required
def refresh_graph(request):
    """Refresh graph data via HTMX."""
    source = request.POST.get('source', '')
    
    if not source:
        return render(request, 'partials/graph_error.html', {'error': 'No source specified'})
    
    # Clear cache and reload
    cache_key = f"graph_data:{md5(source.encode()).hexdigest()}"
    cache.delete(cache_key)
    
    # Redirect to the get_graph_data view
    from django.http import HttpRequest
    new_request = HttpRequest()
    new_request.method = 'GET'
    new_request.GET = {'source': source}
    new_request.user = request.user
    
    return get_graph_data(new_request)


@login_required
def toggle_layout(request):
    """Toggle between different graph layouts via HTMX."""
    source = request.POST.get('source', '')
    
    if not source:
        return render(request, 'partials/graph_error.html', {'error': 'No source specified'})
    
    # For now, just refresh with a different layout style
    # You could store layout preferences in session or database
    layout_style = request.session.get('graph_layout', 'grid')
    request.session['graph_layout'] = 'circular' if layout_style == 'grid' else 'grid'
    
    # Get fresh graph data with new layout
    from django.http import HttpRequest
    new_request = HttpRequest()
    new_request.method = 'GET' 
    new_request.GET = {'source': source}
    new_request.user = request.user
    new_request.session = request.session
    
    return get_graph_data(new_request)


@login_required
def create_connection(request):
    """Create a new connection between two resources."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        from_id = data.get('from')
        to_id = data.get('to')
        predicate_name = data.get('predicate', 'custom:relatedTo')
        
        if not from_id or not to_id:
            return JsonResponse({'error': 'Both from and to IDs required'}, status=400)
        
        # Get or create predicate
        predicate, created = Resource.objects.get_or_create(
            name=predicate_name,
            resource_type=ResourceType.PROPERTY,
            defaults={
                'source': 'user_created',
                'value': predicate_name
            }
        )
        
        # Get subject and object resources
        subject = get_object_or_404(Resource, id=from_id)
        obj = get_object_or_404(Resource, id=to_id)
        
        # Create triple
        triple, created = Triple.objects.get_or_create(
            subject=subject,
            predicate=predicate,
            object=obj
        )
        
        return JsonResponse({
            'success': True,
            'created': created,
            'triple_id': str(triple.id)
        })
        
    except Exception as e:
        logger.error(f"Error creating connection: {e}")
        return JsonResponse({'error': str(e)}, status=500) 


@login_required
def debug_database(request):
    """Debug endpoint to inspect database contents."""
    logger.info("DEBUG: Inspecting database contents")
    
    # Clear all cache first
    logger.info("DEBUG: Clearing all cache")
    cache.clear()
    
    # Get all sources
    sources = Resource.objects.values_list('source', flat=True).distinct()
    logger.info(f"DEBUG: All sources: {list(sources)}")
    
    debug_info = {
        'total_resources': Resource.objects.count(),
        'total_triples': Triple.objects.count(),
        'sources': list(sources),
        'resource_types': dict(Resource.objects.values('resource_type').annotate(count=Count('resource_type')).values_list('resource_type', 'count')),
        'sample_resources': [],
        'sample_triples': [],
        'dataset_analysis': {},
        'cache_cleared': True
    }
    
    # Sample resources
    for res in Resource.objects.all()[:20]:
        debug_info['sample_resources'].append({
            'id': res.id,
            'uri': res.uri,
            'source': res.source,
            'type': res.resource_type,
            'name': res.name,
            'value': res.value[:100] if res.value else None
        })
    
    # Sample triples
    for triple in Triple.objects.all()[:20]:
        debug_info['sample_triples'].append({
            'id': triple.id,
            'subject': triple.subject.uri if triple.subject else None,
            'predicate': triple.predicate.uri if triple.predicate else None,
            'object': triple.object.uri if triple.object else None
        })
    
    # Dataset analysis per source
    for source in sources:
        logger.info(f"DEBUG: Analyzing source '{source}'")
        
        # Resources containing 'datasets'
        dataset_resources = Resource.objects.filter(source=source, uri__contains='/datasets/')
        dataset_count = dataset_resources.count()
        
        # Resources with cell pattern
        cell_resources = Resource.objects.filter(
            source=source, 
            uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$'
        )
        cell_count = cell_resources.count()
        
        # rdf:value triples for this source
        rdf_value_triples = Triple.objects.filter(
            subject__source=source,
            predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
        )
        value_triple_count = rdf_value_triples.count()
        
        debug_info['dataset_analysis'][source] = {
            'total_resources': Resource.objects.filter(source=source).count(),
            'dataset_resources': dataset_count,
            'cell_resources': cell_count,
            'value_triples': value_triple_count,
            'sample_dataset_uris': [r.uri for r in dataset_resources[:5]],
            'sample_cell_uris': [r.uri for r in cell_resources[:5]]
        }
        
        logger.info(f"DEBUG: Source '{source}': {dataset_count} datasets, {cell_count} cells, {value_triple_count} value triples")
    
    return JsonResponse(debug_info, indent=2) 