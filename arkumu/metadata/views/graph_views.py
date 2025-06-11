from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
import json
import logging
import re
from django.http import JsonResponse

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

# Set up logger
logger = logging.getLogger(__name__)


def full_graph_view(request):
    """Display a hierarchical tree + graph view for exploring RDF data structure."""
    
    # Get the hasPart and rdf:value predicates
    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    rdf_value_predicate = Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not has_part_predicate or not rdf_value_predicate:
        # Fallback if predicates not found
        tree_data = []
        graph_data = {'nodes': [], 'links': []}
    else:
        # Build tree structure: datasets -> rows -> cells
        tree_data = []
        
        # Get actual datasets (not individual rows) by looking for resources with URIs that end with /datasets/{name}
        # and that have hasPart relationships pointing to rows or cells
        datasets = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__regex=r'.*/datasets/[^/]+$',  # URI ends with /datasets/{dataset_name}
            subject_triples__predicate=has_part_predicate
        ).annotate(
            item_count=Count('subject_triples', filter=Q(
                subject_triples__predicate=has_part_predicate
            ))
        ).order_by('-item_count')[:10]  # Limit to top 10 datasets
        
        logger.info(f"Found {datasets.count()} actual datasets")
        
        for dataset in datasets:
            dataset_name = dataset.name or (dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}")
            logger.info(f"Processing dataset: {dataset_name} (URI: {dataset.uri})")
            
            dataset_data = {
                'id': str(dataset.id),
                'name': dataset_name,
                'type': 'dataset',
                'count': dataset.item_count,
                'rows': []
            }
            
            # Get rows for this dataset - look for rows with URI pattern /datasets/{name}/rows/{row_id}
            dataset_base_uri = dataset.uri  # e.g., "http://arkumu.org/data/institution/datasets/AkteurIn"
            rows_pattern = f"{dataset_base_uri}/rows/"
            
            # Fetch all rows first to sort them properly, then limit
            all_row_resources = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__startswith=rows_pattern,
                subject_triples__predicate=has_part_predicate
            ).annotate(
                cell_count=Count('subject_triples', filter=Q(
                    subject_triples__predicate=has_part_predicate
                ))
            )
            
            logger.info(f"Found {all_row_resources.count()} total rows for dataset {dataset_name}")
            
            # Convert to list and sort by extracting row number, then take first 20
            all_rows_for_sorting = []
            for row in all_row_resources:
                row_name = row.name or f"Row {row.id}"
                
                # Extract row number for sorting - improved logic
                row_number = None
                
                # Extract from URI first since it's more reliable: /rows/123
                if row.uri:
                    try:
                        # Pattern: .../datasets/name/rows/123
                        uri_parts = row.uri.split('/')
                        if 'rows' in uri_parts:
                            rows_index = uri_parts.index('rows')
                            if rows_index + 1 < len(uri_parts):
                                row_number = int(uri_parts[rows_index + 1])
                    except (ValueError, IndexError):
                        pass
                
                # Try multiple patterns for row number extraction from name if URI fails
                if row_number is None and row.name:
                    # Pattern 1: "Row 123" or "row 123" (case insensitive)
                    match = re.search(r'(?i)row\s*(\d+)', row.name)
                    if match:
                        row_number = int(match.group(1))
                    else:
                        # Pattern 2: Just digits "123"
                        match = re.search(r'(\d+)', row.name)
                        if match:
                            row_number = int(match.group(1))
                
                # Fallback to using the resource ID as sort key
                if row_number is None:
                    try:
                        row_number = int(str(row.id).replace('-', '')[:8], 16)  # Use part of UUID as number
                    except (ValueError, TypeError):
                        row_number = 999999
                
                all_rows_for_sorting.append({
                    'row': row,
                    'row_name': row_name,
                    'row_number': row_number,
                    'cell_count': row.cell_count
                })
            
            # Sort rows by row number and take first 20
            all_rows_for_sorting.sort(key=lambda x: x['row_number'])
            row_list = all_rows_for_sorting[:20]  # Take first 20 after sorting
            
            logger.info(f"After sorting, showing first 20 rows for dataset {dataset_name}")
            if row_list:
                logger.info(f"First row: {row_list[0]['row_name']} (#{row_list[0]['row_number']})")
                logger.info(f"Last row: {row_list[-1]['row_name']} (#{row_list[-1]['row_number']})")
            
            for row_data in row_list:
                row = row_data['row']
                row_name = row_data['row_name']
                cell_count = row_data['cell_count']
                
                row_info = {
                    'id': str(row.id),
                    'name': row_name,
                    'type': 'row',
                    'count': cell_count,
                    'cells': []
                }
                
                # Get cells for this row - cells have URI pattern /datasets/{name}/{column}/{row_id}
                # Extract row_id from row URI
                row_id = row.uri.split('/')[-1] if row.uri else str(row.id)
                
                # Find cells that belong to this row by looking for the row_id in the URI
                cell_resources = Resource.objects.filter(
                    resource_type=ResourceType.IRI,
                    uri__contains=f"/datasets/{dataset.uri.split('/')[-1]}/",  # Contains dataset name
                    uri__endswith=f"/{row_id}",  # Ends with row_id
                    subject_triples__predicate=rdf_value_predicate  # Has rdf:value (indicating it's a cell)
                )[:10]  # Limit to 10 cells per row
                
                # Sort cells alphabetically by column name (extracted from URI)
                cell_list = []
                for cell in cell_resources:
                    cell_name = cell.name or f"Cell {cell.id}"
                    # Extract column name from URI pattern: .../datasets/name/column/row_id
                    column_name = "unknown"
                    if cell.uri:
                        try:
                            uri_parts = cell.uri.split('/')
                            if 'datasets' in uri_parts:
                                datasets_index = uri_parts.index('datasets')
                                if datasets_index + 2 < len(uri_parts):
                                    column_name = uri_parts[datasets_index + 2]  # datasets/name/column/row_id
                        except (ValueError, IndexError):
                            pass
                    
                    cell_list.append({
                        'cell': cell,
                        'cell_name': f"{column_name}",  # Use column name as cell name
                        'column_name': column_name
                    })
                
                # Sort cells alphabetically by column name
                cell_list.sort(key=lambda x: x['column_name'])
                
                for cell_data in cell_list:
                    cell = cell_data['cell']
                    cell_name = cell_data['cell_name']
                    
                    cell_info = {
                        'id': str(cell.id),
                        'name': cell_name,
                        'type': 'cell'
                    }
                    
                    row_info['cells'].append(cell_info)
                
                dataset_data['rows'].append(row_info)
            
            tree_data.append(dataset_data)
        
        # Initial graph data (will be updated via JavaScript when user selects items)
        graph_data = {
            'nodes': [],
            'links': []
        }
    
    return render(request, 'dataset_viewer.html', {
        'graph_data_json': json.dumps({
            'tree_data': tree_data,
            'graph_data': graph_data
        })
    })


def graph_data_view(request):
    """Handle HTMX requests for graph data and return HTML content with embedded visualization."""
    
    # Get the hasPart and rdf:value predicates
    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    rdf_value_predicate = Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not has_part_predicate or not rdf_value_predicate:
        return render(request, 'partials/graph_content.html', {
            'error': 'Required predicates not found',
            'graph_data': json.dumps({'nodes': [], 'links': []})
        })
    
    # Get parameters
    level = request.GET.get('level')
    dataset_id = request.GET.get('dataset')
    row_id = request.GET.get('row')
    cell_id = request.GET.get('cell')
    
    graph_data = {'nodes': [], 'links': []}
    
    try:
        if level == 'dataset' and dataset_id:
            graph_data = get_dataset_graph(dataset_id, has_part_predicate)
        elif level == 'row' and row_id:
            graph_data = get_row_graph(row_id, has_part_predicate, rdf_value_predicate)
        elif level == 'cell' and cell_id:
            graph_data = get_cell_graph(cell_id, rdf_value_predicate)
        else:
            graph_data = {'nodes': [], 'links': [], 'error': 'Invalid parameters'}
            
    except Exception as e:
        logger.error(f"Error generating graph data: {e}")
        graph_data = {'nodes': [], 'links': [], 'error': str(e)}
    
    return render(request, 'partials/graph_content.html', {
        'graph_data': json.dumps(graph_data),
        'level': level,
        'dataset_id': dataset_id,
        'row_id': row_id,
        'cell_id': cell_id
    })

def get_dataset_graph(dataset_id, has_part_predicate):
    """Get graph data for a specific dataset showing its immediate relationships."""
    try:
        dataset = Resource.objects.get(id=dataset_id)
        
        nodes = [{
            'id': f"dataset_{dataset.id}",
            'name': dataset.name or f"Dataset {dataset.id}",
            'type': 'dataset',
            'group': 0
        }]
        
        links = []
        
        # Get sample of rows/cells connected to this dataset
        connected_items = Triple.objects.filter(
            subject=dataset,
            predicate=has_part_predicate
        ).select_related('object')[:15]  # Sample for visualization
        
        for triple in connected_items:
            obj = triple.object
            obj_name = obj.name or f"Item {obj.id}"
            
            # Determine if it's a row (has its own hasPart) or direct cell
            is_row = Triple.objects.filter(
                subject=obj,
                predicate=has_part_predicate
            ).exists()
            
            node_type = 'row' if is_row else 'cell'
            
            nodes.append({
                'id': f"{node_type}_{obj.id}",
                'name': obj_name,
                'type': node_type,
                'group': 1
            })
            
            links.append({
                'source': f"dataset_{dataset.id}",
                'target': f"{node_type}_{obj.id}",
                'label': 'hasPart',
                'value': 1
            })
        
        return {'nodes': nodes, 'links': links}
        
    except Resource.DoesNotExist:
        return {'nodes': [], 'links': [], 'error': 'Dataset not found'}

def get_row_graph(row_id, has_part_predicate, rdf_value_predicate):
    """Get graph data for a specific row showing its cells and values."""
    try:
        row = Resource.objects.get(id=row_id)
        
        nodes = [{
            'id': f"row_{row.id}",
            'name': row.name or f"Row {row.id}",
            'type': 'row',
            'group': 0
        }]
        
        links = []
        
        # Get cells in this row
        cell_triples = Triple.objects.filter(
            subject=row,
            predicate=has_part_predicate
        ).select_related('object')[:20]  # Limit for performance
        
        for cell_triple in cell_triples:
            cell = cell_triple.object
            cell_name = cell.name or f"Cell {cell.id}"
            
            nodes.append({
                'id': f"cell_{cell.id}",
                'name': cell_name,
                'type': 'cell',
                'group': 1
            })
            
            links.append({
                'source': f"row_{row.id}",
                'target': f"cell_{cell.id}",
                'label': 'hasPart',
                'value': 1
            })
            
            # Get values for this cell
            value_triples = Triple.objects.filter(
                subject=cell,
                predicate=rdf_value_predicate,
                object__resource_type=ResourceType.LITERAL
            ).select_related('object')
            
            for value_triple in value_triples:
                literal = value_triple.object
                display_value = (literal.value or "")[:30]
                if len(literal.value or "") > 30:
                    display_value += "..."
                
                nodes.append({
                    'id': f"literal_{literal.id}",
                    'name': display_value,
                    'type': 'literal',
                    'group': 2,
                    'full_value': literal.value
                })
                
                links.append({
                    'source': f"cell_{cell.id}",
                    'target': f"literal_{literal.id}",
                    'label': 'value',
                    'value': 1
                })
        
        return {'nodes': nodes, 'links': links}
        
    except Resource.DoesNotExist:
        return {'nodes': [], 'links': [], 'error': 'Row not found'}

def get_cell_graph(cell_id, rdf_value_predicate):
    """Get graph data for a specific cell showing its values and properties."""
    try:
        cell = Resource.objects.get(id=cell_id)
        
        nodes = [{
            'id': f"cell_{cell.id}",
            'name': cell.name or f"Cell {cell.id}",
            'type': 'cell',
            'group': 0
        }]
        
        links = []
        
        # Get all triples where this cell is the subject
        cell_triples = Triple.objects.filter(
            subject=cell
        ).select_related('predicate', 'object')[:20]
        
        for triple in cell_triples:
            # Always prioritize RDF notation from URI over stored name
            predicate_name = None
            
            # Try to create RDF notation from URI first
            if triple.predicate.uri:
                uri = triple.predicate.uri
                if uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#value":
                    predicate_name = "rdf:value"
                elif uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
                    predicate_name = "rdf:type"
                elif uri == "http://purl.org/dc/terms/hasPart":
                    predicate_name = "dcterms:hasPart"
                elif uri == "http://www.w3.org/2000/01/rdf-schema#label":
                    predicate_name = "rdfs:label"
                elif "http://www.w3.org/1999/02/22-rdf-syntax-ns#" in uri:
                    predicate_name = f"rdf:{uri.split('#')[-1]}"
                elif "http://purl.org/dc/terms/" in uri:
                    predicate_name = f"dcterms:{uri.split('/')[-1]}"
                elif "http://www.w3.org/2000/01/rdf-schema#" in uri:
                    predicate_name = f"rdfs:{uri.split('#')[-1]}"
                elif "http://www.w3.org/2002/07/owl#" in uri:
                    predicate_name = f"owl:{uri.split('#')[-1]}"
                else:
                    # For custom URIs, try to extract a meaningful name
                    predicate_name = uri.split('/')[-1] if '/' in uri else uri.split('#')[-1] if '#' in uri else uri
            
            # Fallback to stored name if URI conversion didn't produce anything
            if not predicate_name:
                predicate_name = triple.predicate.name
            
            # Final fallback if still no name
            if not predicate_name:
                predicate_name = f"Property {triple.predicate.id}"
            
            obj = triple.object
            
            if obj.resource_type == ResourceType.LITERAL:
                display_value = (obj.value or "")[:30]
                if len(obj.value or "") > 30:
                    display_value += "..."
                
                nodes.append({
                    'id': f"literal_{obj.id}",
                    'name': display_value,
                    'type': 'literal',
                    'group': 2,
                    'full_value': obj.value
                })
            else:
                obj_name = obj.name or obj.uri or f"Resource {obj.id}"
                nodes.append({
                    'id': f"resource_{obj.id}",
                    'name': obj_name,
                    'type': 'resource',
                    'group': 1
                })
            
            target_id = f"literal_{obj.id}" if obj.resource_type == ResourceType.LITERAL else f"resource_{obj.id}"
            links.append({
                'source': f"cell_{cell.id}",
                'target': target_id,
                'label': predicate_name,
                'value': 1
            })
        
        return {'nodes': nodes, 'links': links}
        
    except Resource.DoesNotExist:
        return {'nodes': [], 'links': [], 'error': 'Cell not found'}


def tree_cell_details_view(request, cell_id):
    """HTMX view for getting cell details and graph data."""
    logger.info(f"tree_cell_details_view called for cell_id: {cell_id}")
    
    # Get the rdf:value predicate
    rdf_value_predicate = Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not rdf_value_predicate:
        logger.error("rdf:value predicate not found")
        return render(request, 'partials/tree_error.html', {
            'error': 'Configuration error: rdf:value predicate missing'
        })
    
    # Get cell information and graph data
    try:
        cell = Resource.objects.get(id=cell_id)
        
        # Extract meaningful information from cell URI for display
        cell_display_info = {
            'dataset': None,
            'column': None,
            'row_id': None,
            'display_name': cell.name or "(unnamed)"
        }
        
        if cell.uri:
            # Expected URI pattern: http://arkumu.org/data/{institution}/datasets/{dataset}/{column}/{row_id}
            try:
                uri_parts = cell.uri.split('/')
                if len(uri_parts) >= 7 and 'datasets' in uri_parts:
                    datasets_index = uri_parts.index('datasets')
                    if datasets_index + 3 < len(uri_parts):
                        cell_display_info['dataset'] = uri_parts[datasets_index + 1]
                        cell_display_info['column'] = uri_parts[datasets_index + 2] 
                        cell_display_info['row_id'] = uri_parts[datasets_index + 3]
                        cell_display_info['display_name'] = f"{cell_display_info['column']} → Row {cell_display_info['row_id']}"
            except (ValueError, IndexError):
                logger.warning(f"Could not parse cell URI: {cell.uri}")
        
        # Get cell graph data
        graph_data = get_cell_graph(cell_id, rdf_value_predicate)
        
        if 'error' in graph_data:
            return render(request, 'partials/tree_error.html', {
                'error': graph_data['error']
            })
        
        # Get cell values/triples for display
        cell_triples = Triple.objects.filter(
            subject=cell
        ).select_related('predicate', 'object')[:10]
        
        cell_values = []
        for triple in cell_triples:
            # Always prioritize RDF notation from URI over stored name
            predicate_name = None
            
            # Try to create RDF notation from URI first
            if triple.predicate.uri:
                uri = triple.predicate.uri
                if uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#value":
                    predicate_name = "rdf:value"
                elif uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
                    predicate_name = "rdf:type"
                elif uri == "http://purl.org/dc/terms/hasPart":
                    predicate_name = "dcterms:hasPart"
                elif uri == "http://www.w3.org/2000/01/rdf-schema#label":
                    predicate_name = "rdfs:label"
                elif "http://www.w3.org/1999/02/22-rdf-syntax-ns#" in uri:
                    predicate_name = f"rdf:{uri.split('#')[-1]}"
                elif "http://purl.org/dc/terms/" in uri:
                    predicate_name = f"dcterms:{uri.split('/')[-1]}"
                elif "http://www.w3.org/2000/01/rdf-schema#" in uri:
                    predicate_name = f"rdfs:{uri.split('#')[-1]}"
                elif "http://www.w3.org/2002/07/owl#" in uri:
                    predicate_name = f"owl:{uri.split('#')[-1]}"
                else:
                    # For custom URIs, try to extract a meaningful name
                    predicate_name = uri.split('/')[-1] if '/' in uri else uri.split('#')[-1] if '#' in uri else uri
            
            # Fallback to stored name if URI conversion didn't produce anything
            if not predicate_name:
                predicate_name = triple.predicate.name
            
            # Final fallback if still no name
            if not predicate_name:
                predicate_name = f"Property {triple.predicate.id}"
            
            if triple.object.resource_type == ResourceType.LITERAL:
                value = triple.object.value or "(empty)"
            else:
                value = triple.object.name or triple.object.uri or f"Resource {triple.object.id}"
            
            cell_values.append({
                'predicate': predicate_name,
                'predicate_uri': triple.predicate.uri,  # Include full URI for reference
                'value': value,
                'is_literal': triple.object.resource_type == ResourceType.LITERAL
            })
        
        return render(request, 'partials/cell_details.html', {
            'cell': cell,
            'cell_values': cell_values,
            'graph_data': json.dumps(graph_data),
            'cell_display_info': cell_display_info
        })
        
    except Resource.DoesNotExist:
        return render(request, 'partials/tree_error.html', {
            'error': 'Cell not found'
        })


def dataset_viewer_view(request):
    """Display a hierarchical tree + graph view for exploring RDF data structure."""
    return render(request, 'dataset_viewer.html')


def tree_data_view(request):
    """HTMX endpoint for loading tree data organized by buckets."""
    
    logger.info("tree_data_view called")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Is HTMX request: {request.headers.get('HX-Request', False)}")
    
    # Get the hasPart and rdf:value predicates
    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    rdf_value_predicate = Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not has_part_predicate or not rdf_value_predicate:
        logger.error("Required predicates not found")
        return render(request, 'partials/tree_error.html', {
            'error': 'Required predicates not found'
        })
    
    # Get datasets and group by bucket (organization)
    datasets = Resource.objects.filter(
        resource_type=ResourceType.IRI,
        uri__regex=r'.*/datasets/[^/]+$',
        subject_triples__predicate=has_part_predicate
    ).annotate(
        item_count=Count('subject_triples', filter=Q(
            subject_triples__predicate=has_part_predicate
        ))
    ).order_by('-item_count')[:50]  # Get more datasets to group properly
    
    logger.info(f"Found {datasets.count()} datasets")
    
    # Group datasets by bucket (extract from URI)
    buckets = {}
    for dataset in datasets:
        # Extract bucket from URI pattern: http://arkumu.org/data/{bucket}/datasets/{name}
        bucket_name = "Default"
        if dataset.uri:
            try:
                uri_parts = dataset.uri.split('/')
                if 'data' in uri_parts:
                    data_index = uri_parts.index('data')
                    if data_index + 1 < len(uri_parts):
                        bucket_name = uri_parts[data_index + 1]  # The organization/bucket name
                        logger.debug(f"Extracted bucket '{bucket_name}' from URI: {dataset.uri}")
            except (ValueError, IndexError):
                logger.warning(f"Could not extract bucket from URI: {dataset.uri}")
                pass
        
        if bucket_name not in buckets:
            buckets[bucket_name] = []
        
        dataset_info = {
            'id': str(dataset.id),
            'name': dataset.name or dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}",
            'count': dataset.item_count,
            'uri': dataset.uri
        }
        
        buckets[bucket_name].append(dataset_info)
        logger.debug(f"Added dataset '{dataset_info['name']}' to bucket '{bucket_name}'")
    
    # Sort buckets and datasets within buckets
    for bucket_name in buckets:
        buckets[bucket_name].sort(key=lambda x: x['name'])
        logger.info(f"Bucket '{bucket_name}' has {len(buckets[bucket_name])} datasets")
    
    sorted_buckets = sorted(buckets.items())
    logger.info(f"Returning {len(sorted_buckets)} buckets: {[b[0] for b in sorted_buckets]}")
    
    bucket_list_for_template = []
    for bucket_name_key, dataset_list_val in sorted_buckets:
        bucket_list_for_template.append({
            'name': bucket_name_key,
            'dataset_count': len(dataset_list_val)
        })
    
    # Sort this final list by bucket name for consistent order
    bucket_list_for_template.sort(key=lambda b: b['name'])

    logger.info(f"Returning {len(bucket_list_for_template)} buckets for template: {[b['name'] for b in bucket_list_for_template]}")

    return render(request, 'partials/tree_buckets.html', {
        'buckets': bucket_list_for_template
    })


def tree_bucket_content_view(request, bucket_name):
    logger.info(f"=== tree_bucket_content_view called for bucket: '{bucket_name}' ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Is HTMX request: {request.headers.get('HX-Request', False)}")
    logger.info(f"Request headers: {dict(request.headers)}")

    # Pagination parameters
    PAGE_SIZE = 20
    offset = int(request.GET.get('offset', 0))

    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()

    if not has_part_predicate:
        logger.error("hasPart predicate not found in tree_bucket_content_view")
        return render(request, 'partials/tree_error.html', {'error': 'Configuration error: hasPart predicate missing'})

    def extract_source_from_uri(uri):
        """Extract source name from URI like http://arkumu.org/data/{source}/datasets/{name}"""
        if not uri:
            return "Unknown"
        try:
            uri_parts = uri.split('/')
            if 'data' in uri_parts:
                data_index = uri_parts.index('data')
                if data_index + 1 < len(uri_parts):
                    return uri_parts[data_index + 1]
        except (ValueError, IndexError):
            pass
        return "Unknown"

    datasets_in_bucket_final = []
    total_count = 0

    if bucket_name == "Default":
        logger.info("Processing 'Default' bucket...")
        # For "Default" bucket, iterate all datasets and apply extraction logic
        all_datasets_for_default_check = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__regex=r'.*/datasets/[^/]+$',
            subject_triples__predicate=has_part_predicate
        ).annotate(
            item_count=Count('subject_triples', filter=Q(subject_triples__predicate=has_part_predicate))
        ).order_by('name')

        # Get total count and paginated slice first, then filter for Default bucket
        total_query = all_datasets_for_default_check
        paginated_datasets = total_query[offset:offset + PAGE_SIZE]
        
        # Filter only those that belong to Default bucket  
        for dataset in paginated_datasets:
            extracted_bn = extract_source_from_uri(dataset.uri)
            if extracted_bn == "Unknown":
                extracted_bn = "Default"
            
            if extracted_bn == bucket_name: # Match "Default"
                 datasets_in_bucket_final.append({
                    'id': str(dataset.id),
                    'name': dataset.name or (dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}"),
                    'count': dataset.item_count, 
                    'uri': dataset.uri,
                    'source': extracted_bn
                })
        
        # Calculate actual total count for Default bucket specifically
        total_count = 0
        for dataset in all_datasets_for_default_check:
            extracted_bn = extract_source_from_uri(dataset.uri)
            if extracted_bn == "Unknown":
                extracted_bn = "Default"
            if extracted_bn == bucket_name:
                total_count += 1
    else:
        logger.info(f"Processing non-default bucket: '{bucket_name}'...")
        # For non-"Default" buckets, use a more precise regex
        # The bucket name could contain special regex characters, so escape it.
        # Pattern: http://arkumu.org/data/{bucket}/datasets/{name}
        precise_datasets_query = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__regex=rf'^.*/data/{re.escape(bucket_name)}/datasets/[^/]+$',
            subject_triples__predicate=has_part_predicate
        ).annotate(
            item_count=Count('subject_triples', filter=Q(
                subject_triples__predicate=has_part_predicate
            ))
        ).order_by('name')
        
        logger.info(f"Query for bucket '{bucket_name}': {precise_datasets_query.query}")
        
        # Get total count and paginated slice
        total_count = precise_datasets_query.count()
        paginated_datasets = precise_datasets_query[offset:offset + PAGE_SIZE]
        
        for dataset in paginated_datasets:
            source_name = extract_source_from_uri(dataset.uri)
            datasets_in_bucket_final.append({
                'id': str(dataset.id),
                'name': dataset.name or (dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}"),
                'count': dataset.item_count,
                'uri': dataset.uri,
                'source': source_name
            })
            logger.info(f"Added dataset: {dataset.name} (URI: {dataset.uri}, Source: {source_name})")

    # Check if there are more items to load
    has_more = (offset + PAGE_SIZE) < total_count
    next_offset = offset + PAGE_SIZE

    logger.info(f"=== Found {len(datasets_in_bucket_final)} datasets for bucket '{bucket_name}' (offset: {offset}, total: {total_count}, has_more: {has_more}) ===")
    
    return render(request, 'partials/tree_datasets_list.html', {
        'datasets': datasets_in_bucket_final,
        'bucket_name': bucket_name,
        'has_more': has_more,
        'next_offset': next_offset,
        'is_pagination': offset > 0  # Flag to determine if this is a paginated request
    })


def tree_bucket_more_view(request, bucket_name):
    """HTMX endpoint for loading more datasets in a bucket."""
    logger.info(f"=== tree_bucket_more_view called for bucket: '{bucket_name}' ===")
    
    # This view is identical to tree_bucket_content_view but returns a different template
    # that only contains the additional datasets without the container structure
    
    # Pagination parameters
    PAGE_SIZE = 20
    offset = int(request.GET.get('offset', 0))

    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()

    if not has_part_predicate:
        logger.error("hasPart predicate not found in tree_bucket_more_view")
        return render(request, 'partials/tree_error.html', {'error': 'Configuration error: hasPart predicate missing'})

    def extract_source_from_uri(uri):
        """Extract source name from URI like http://arkumu.org/data/{source}/datasets/{name}"""
        if not uri:
            return "Unknown"
        try:
            uri_parts = uri.split('/')
            if 'data' in uri_parts:
                data_index = uri_parts.index('data')
                if data_index + 1 < len(uri_parts):
                    return uri_parts[data_index + 1]
        except (ValueError, IndexError):
            pass
        return "Unknown"

    datasets_in_bucket_final = []
    total_count = 0

    if bucket_name == "Default":
        all_datasets_for_default_check = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__regex=r'.*/datasets/[^/]+$',
            subject_triples__predicate=has_part_predicate
        ).annotate(
            item_count=Count('subject_triples', filter=Q(subject_triples__predicate=has_part_predicate))
        ).order_by('name')

        paginated_datasets = all_datasets_for_default_check[offset:offset + PAGE_SIZE]
        total_count = all_datasets_for_default_check.count()

        for dataset in paginated_datasets:
            extracted_bn = extract_source_from_uri(dataset.uri)
            if extracted_bn == "Unknown":
                extracted_bn = "Default"
            
            if extracted_bn == bucket_name:
                 datasets_in_bucket_final.append({
                    'id': str(dataset.id),
                    'name': dataset.name or (dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}"),
                    'count': dataset.item_count, 
                    'uri': dataset.uri,
                    'source': extracted_bn
                })
    else:
        precise_datasets_query = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__regex=rf'^.*/data/{re.escape(bucket_name)}/datasets/[^/]+$',
            subject_triples__predicate=has_part_predicate
        ).annotate(
            item_count=Count('subject_triples', filter=Q(
                subject_triples__predicate=has_part_predicate
            ))
        ).order_by('name')
        
        total_count = precise_datasets_query.count()
        paginated_datasets = precise_datasets_query[offset:offset + PAGE_SIZE]
        
        for dataset in paginated_datasets:
            source_name = extract_source_from_uri(dataset.uri)
            datasets_in_bucket_final.append({
                'id': str(dataset.id),
                'name': dataset.name or (dataset.uri.split('/')[-1] if dataset.uri else f"Dataset {dataset.id}"),
                'count': dataset.item_count,
                'uri': dataset.uri,
                'source': source_name
            })

    # Check if there are more items to load
    has_more = (offset + PAGE_SIZE) < total_count
    next_offset = offset + PAGE_SIZE

    logger.info(f"tree_bucket_more_view returning {len(datasets_in_bucket_final)} datasets")
    
    return render(request, 'partials/tree_datasets_more.html', {
        'datasets': datasets_in_bucket_final,
        'bucket_name': bucket_name,
        'has_more': has_more,
        'next_offset': next_offset
    })


def tree_dataset_view(request, dataset_id):
    """HTMX endpoint for loading dataset rows."""
    
    logger.info(f"tree_dataset_view called with dataset_id: {dataset_id}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Is HTMX request: {request.headers.get('HX-Request', False)}")
    
    # Pagination parameters
    PAGE_SIZE = 20
    offset = int(request.GET.get('offset', 0))
    
    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not has_part_predicate:
        logger.error("hasPart predicate not found")
        return render(request, 'partials/tree_error.html', {
            'error': 'hasPart predicate not found'
        })
    
    try:
        dataset = Resource.objects.get(id=dataset_id)
        logger.info(f"Found dataset: {dataset.name} (URI: {dataset.uri})")
        
        # Get rows for this dataset
        dataset_base_uri = dataset.uri
        rows_pattern = f"{dataset_base_uri}/rows/"
        logger.info(f"Looking for rows with pattern: {rows_pattern}")
        
        # Get all rows (without pagination first to get count and sorting)
        all_rows_query = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__startswith=rows_pattern,
            subject_triples__predicate=has_part_predicate
        ).annotate(
            cell_count=Count('subject_triples', filter=Q(
                subject_triples__predicate=has_part_predicate
            ))
        )
        
        logger.info(f"Found {all_rows_query.count()} total rows for dataset {dataset.name}")
        
        # If no rows with predicate, try without predicate requirement
        if all_rows_query.count() == 0:
            logger.info("No rows with hasPart predicate, trying without predicate requirement")
            all_rows_query = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__startswith=rows_pattern
            ).annotate(
                cell_count=Count('subject_triples')
            )
        
        # Extract and sort by row number (do this for ALL rows to get proper sorting)
        all_rows_for_sorting = []
        for row in all_rows_query:
            row_name = row.name or f"Row {row.id}"
            
            # Extract row number for sorting
            row_number = 999999  # Default for sorting
            if row.uri:
                try:
                    uri_parts = row.uri.split('/')
                    if 'rows' in uri_parts:
                        rows_index = uri_parts.index('rows')
                        if rows_index + 1 < len(uri_parts):
                            row_number = int(uri_parts[rows_index + 1])
                except (ValueError, IndexError):
                    pass
            
            all_rows_for_sorting.append({
                'id': str(row.id),
                'name': row_name,
                'count': row.cell_count,
                'sort_key': row_number
            })
        
        # Sort by row number
        all_rows_for_sorting.sort(key=lambda x: x['sort_key'])
        
        # Apply pagination after sorting
        total_count = len(all_rows_for_sorting)
        paginated_rows = all_rows_for_sorting[offset:offset + PAGE_SIZE]
        has_more = (offset + PAGE_SIZE) < total_count
        next_offset = offset + PAGE_SIZE
        
        logger.info(f"Returning {len(paginated_rows)} sorted rows (offset: {offset}, total: {total_count}, has_more: {has_more})")
        if paginated_rows:
            logger.info(f"First row: {paginated_rows[0]['name']} (#{paginated_rows[0]['sort_key']})")
            logger.info(f"Last row: {paginated_rows[-1]['name']} (#{paginated_rows[-1]['sort_key']})")
        
        return render(request, 'partials/tree_rows.html', {
            'dataset_id': dataset_id,
            'rows': paginated_rows,
            'has_more': has_more,
            'next_offset': next_offset,
            'is_pagination': offset > 0
        })
        
    except Resource.DoesNotExist:
        logger.error(f"Dataset not found: {dataset_id}")
        return render(request, 'partials/tree_error.html', {
            'error': 'Dataset not found'
        })
    except Exception as e:
        logger.error(f"Error in tree_dataset_view: {e}")
        return render(request, 'partials/tree_error.html', {
            'error': f'Error loading dataset: {str(e)}'
        })

  
def tree_row_view(request, dataset_id, row_id):
    """HTMX endpoint for loading row cells."""
    
    rdf_value_predicate = Resource.objects.filter(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    try:
        dataset = Resource.objects.get(id=dataset_id)
        row = Resource.objects.get(id=row_id)
        
        # Get row_id from URI
        row_uri_id = row.uri.split('/')[-1] if row.uri else str(row.id)
        
        # Extract the full dataset path from the dataset URI to ensure source-specific filtering
        # Expected pattern: http://arkumu.org/data/{source}/datasets/{dataset_name}
        dataset_path_pattern = None
        if dataset.uri:
            try:
                # Extract everything up to and including the dataset name
                # e.g., "http://arkumu.org/data/RSH/datasets/Digitales_Objekt" -> "/data/RSH/datasets/Digitales_Objekt/"
                uri_parts = dataset.uri.split('/')
                if 'data' in uri_parts and 'datasets' in uri_parts:
                    data_index = uri_parts.index('data')
                    datasets_index = uri_parts.index('datasets')
                    if datasets_index + 1 < len(uri_parts):
                        # Reconstruct the path pattern: /data/{source}/datasets/{dataset_name}/
                        source = uri_parts[data_index + 1]
                        dataset_name = uri_parts[datasets_index + 1]
                        dataset_path_pattern = f"/data/{source}/datasets/{dataset_name}/"
                        logger.info(f"Using dataset path pattern: {dataset_path_pattern}")
            except (ValueError, IndexError):
                logger.warning(f"Could not extract dataset path pattern from URI: {dataset.uri}")
        
        # Find cells for this row using the specific dataset path pattern
        if dataset_path_pattern:
            # More precise filtering using the full source + dataset path
            cell_resources = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__contains=dataset_path_pattern,  # Must be from the same source/dataset
                uri__endswith=f"/{row_uri_id}",
                subject_triples__predicate=rdf_value_predicate
            )[:15]  # Limit to 15 cells
            logger.info(f"Found {cell_resources.count()} cells using dataset path pattern: {dataset_path_pattern}")
        else:
            # Fallback to the old method if URI parsing fails
            cell_resources = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__contains=f"/datasets/{dataset.uri.split('/')[-1]}/",
                uri__endswith=f"/{row_uri_id}",
                subject_triples__predicate=rdf_value_predicate
            )[:15]
            logger.warning(f"Using fallback method for cell filtering (dataset: {dataset.name})")
        
        # Extract column names and sort
        cells_data = []
        for cell in cell_resources:
            column_name = "unknown"
            if cell.uri:
                try:
                    uri_parts = cell.uri.split('/')
                    if 'datasets' in uri_parts:
                        datasets_index = uri_parts.index('datasets')
                        if datasets_index + 2 < len(uri_parts):
                            column_name = uri_parts[datasets_index + 2]
                except (ValueError, IndexError):
                    pass
            
            cells_data.append({
                'id': str(cell.id),
                'name': column_name,
                'column_name': column_name
            })
            logger.debug(f"Cell: {column_name} (URI: {cell.uri})")
        
        # Sort by column name
        cells_data.sort(key=lambda x: x['column_name'])
        
        logger.info(f"Returning {len(cells_data)} cells for row {row.name} in dataset {dataset.name}")
        
        return render(request, 'partials/tree_cells.html', {
            'dataset_id': dataset_id,
            'row_id': row_id,
            'cells': cells_data
        })
        
    except Resource.DoesNotExist:
        return render(request, 'partials/tree_error.html', {
            'error': 'Dataset or row not found'
        })


def tree_dataset_more_view(request, dataset_id):
    """HTMX endpoint for loading more rows in a dataset."""
    logger.info(f"tree_dataset_more_view called with dataset_id: {dataset_id}")
    
    # Pagination parameters
    PAGE_SIZE = 20
    offset = int(request.GET.get('offset', 0))
    
    has_part_predicate = Resource.objects.filter(
        uri="http://purl.org/dc/terms/hasPart",
        resource_type=ResourceType.PROPERTY
    ).first()
    
    if not has_part_predicate:
        logger.error("hasPart predicate not found")
        return render(request, 'partials/tree_error.html', {
            'error': 'hasPart predicate not found'
        })
    
    try:
        dataset = Resource.objects.get(id=dataset_id)
        
        # Get rows for this dataset
        dataset_base_uri = dataset.uri
        rows_pattern = f"{dataset_base_uri}/rows/"
        
        # Get all rows query
        all_rows_query = Resource.objects.filter(
            resource_type=ResourceType.IRI,
            uri__startswith=rows_pattern,
            subject_triples__predicate=has_part_predicate
        ).annotate(
            cell_count=Count('subject_triples', filter=Q(
                subject_triples__predicate=has_part_predicate
            ))
        )
        
        # If no rows with predicate, try without predicate requirement
        if all_rows_query.count() == 0:
            all_rows_query = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__startswith=rows_pattern
            ).annotate(
                cell_count=Count('subject_triples')
            )
        
        # Extract and sort by row number (do this for ALL rows to get proper sorting)
        all_rows_for_sorting = []
        for row in all_rows_query:
            row_name = row.name or f"Row {row.id}"
            
            # Extract row number for sorting
            row_number = 999999  # Default for sorting
            if row.uri:
                try:
                    uri_parts = row.uri.split('/')
                    if 'rows' in uri_parts:
                        rows_index = uri_parts.index('rows')
                        if rows_index + 1 < len(uri_parts):
                            row_number = int(uri_parts[rows_index + 1])
                except (ValueError, IndexError):
                    pass
            
            all_rows_for_sorting.append({
                'id': str(row.id),
                'name': row_name,
                'count': row.cell_count,
                'sort_key': row_number
            })
        
        # Sort by row number
        all_rows_for_sorting.sort(key=lambda x: x['sort_key'])
        
        # Apply pagination after sorting
        total_count = len(all_rows_for_sorting)
        paginated_rows = all_rows_for_sorting[offset:offset + PAGE_SIZE]
        has_more = (offset + PAGE_SIZE) < total_count
        next_offset = offset + PAGE_SIZE
        
        logger.info(f"Loading more: {len(paginated_rows)} rows for dataset {dataset.name} (offset: {offset}, has_more: {has_more})")
        
        return render(request, 'partials/tree_rows_more.html', {
            'dataset_id': dataset_id,
            'rows': paginated_rows,
            'has_more': has_more,
            'next_offset': next_offset
        })
        
    except Resource.DoesNotExist:
        logger.error(f"Dataset not found: {dataset_id}")
        return render(request, 'partials/tree_error.html', {
            'error': 'Dataset not found'
        })
    except Exception as e:
        logger.error(f"Error in tree_dataset_more_view: {e}")
        return render(request, 'partials/tree_error.html', {
            'error': f'Error loading more rows: {str(e)}'
        })


def tree_dataset_details_view(request, dataset_id):
    """HTMX view for getting dataset details to display in the details panel."""
    logger.info(f"tree_dataset_details_view called for dataset_id: {dataset_id}")
    
    try:
        dataset = Resource.objects.get(id=dataset_id)
        
        # Extract meaningful information from dataset URI for display
        dataset_display_info = {
            'source': 'Unknown',
            'institution': None,
            'display_name': dataset.name or "(unnamed)"
        }
        
        if dataset.uri:
            # Expected URI pattern: http://arkumu.org/data/{source}/datasets/{dataset_name}
            try:
                uri_parts = dataset.uri.split('/')
                if 'data' in uri_parts and 'datasets' in uri_parts:
                    data_index = uri_parts.index('data')
                    if data_index + 1 < len(uri_parts):
                        dataset_display_info['source'] = uri_parts[data_index + 1]
                        dataset_display_info['institution'] = uri_parts[data_index + 1]
            except (ValueError, IndexError):
                logger.warning(f"Could not parse dataset URI: {dataset.uri}")
        
        # Get dataset statistics
        has_part_predicate = Resource.objects.filter(
            uri="http://purl.org/dc/terms/hasPart",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        rdf_value_predicate = Resource.objects.filter(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        stats = {
            'total_rows': 0,
            'total_cells': 0
        }
        
        if has_part_predicate and dataset.uri:
            # Debug: Let's see what we're working with
            logger.info(f"Dataset URI: {dataset.uri}")
            dataset_path = dataset.uri.replace('http://arkumu.org', '')  # Remove domain
            cell_pattern = f"{dataset_path}/"
            logger.info(f"Cell pattern: {cell_pattern}")
            
            # Count rows using URI pattern (more reliable than hasPart counting)
            rows_pattern = f"{dataset.uri}/rows/"
            row_resources = Resource.objects.filter(
                resource_type=ResourceType.IRI,
                uri__startswith=rows_pattern
            )
            rows_count = row_resources.count()
            stats['total_rows'] = rows_count
            logger.info(f"Row resources found: {rows_count}")
            
            # Count cells more efficiently using URI pattern
            # Cell URIs follow pattern: {dataset_uri}/{column}/{row_id}
            # So they contain the dataset URI but are not direct hasPart children
            if rdf_value_predicate:
                # First, let's see what resources we find with the pattern
                all_matching_resources = Resource.objects.filter(
                    resource_type=ResourceType.IRI,
                    uri__contains=cell_pattern
                ).exclude(
                    uri=dataset.uri  # Exclude the dataset itself
                )
                
                logger.info(f"All resources matching pattern: {all_matching_resources.count()}")
                
                # Sample a few URIs to see the pattern
                sample_uris = list(all_matching_resources.values_list('uri', flat=True)[:5])
                logger.info(f"Sample URIs: {sample_uris}")
                
                # Now count those that have rdf:value (actual cells)
                cells_with_values = all_matching_resources.filter(
                    subject_triples__predicate=rdf_value_predicate
                ).distinct()
                
                cells_count = cells_with_values.count()
                logger.info(f"Cells with rdf:value: {cells_count}")
                
                stats['total_cells'] = cells_count
            else:
                logger.warning("rdf:value predicate not found, using fallback")
                # Fallback: count by URI pattern if rdf:value predicate not found
                cells_count = Resource.objects.filter(
                    resource_type=ResourceType.IRI,
                    uri__contains=cell_pattern,
                    uri__regex=r'.*/[^/]+/[^/]+/[0-9]+$'  # Pattern: .../dataset/column/row_number
                ).distinct().count()
                
                stats['total_cells'] = cells_count
        
        # Get any additional metadata triples for this dataset
        dataset_triples = Triple.objects.filter(
            subject=dataset
        ).exclude(
            predicate=has_part_predicate  # Exclude structural relationships
        ).select_related('predicate', 'object')[:10]
        
        dataset_metadata = []
        for triple in dataset_triples:
            # Create readable predicate name
            predicate_name = None
            if triple.predicate.uri:
                uri = triple.predicate.uri
                if uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
                    predicate_name = "rdf:type"
                elif uri == "http://www.w3.org/2000/01/rdf-schema#label":
                    predicate_name = "rdfs:label"
                elif "http://www.w3.org/1999/02/22-rdf-syntax-ns#" in uri:
                    predicate_name = f"rdf:{uri.split('#')[-1]}"
                elif "http://purl.org/dc/terms/" in uri:
                    predicate_name = f"dcterms:{uri.split('/')[-1]}"
                elif "http://www.w3.org/2000/01/rdf-schema#" in uri:
                    predicate_name = f"rdfs:{uri.split('#')[-1]}"
                else:
                    predicate_name = uri.split('/')[-1] if '/' in uri else uri.split('#')[-1] if '#' in uri else uri
            
            if not predicate_name:
                predicate_name = triple.predicate.name or f"Property {triple.predicate.id}"
            
            if triple.object.resource_type == ResourceType.LITERAL:
                value = triple.object.value or "(empty)"
            else:
                value = triple.object.name or triple.object.uri or f"Resource {triple.object.id}"
            
            dataset_metadata.append({
                'predicate': predicate_name,
                'predicate_uri': triple.predicate.uri,
                'value': value,
                'is_literal': triple.object.resource_type == ResourceType.LITERAL
            })
        
        return render(request, 'partials/dataset_details.html', {
            'dataset': dataset,
            'dataset_display_info': dataset_display_info,
            'stats': stats,
            'dataset_metadata': dataset_metadata
        })
        
    except Resource.DoesNotExist:
        return render(request, 'partials/tree_error.html', {
            'error': 'Dataset not found'
        }) 


def tree_row_details_view(request, row_id):
    """HTMX view for getting row details to display in the details panel."""
    logger.info(f"tree_row_details_view called for row_id: {row_id}")
    
    try:
        row = Resource.objects.get(id=row_id)
        
        # Extract meaningful information from row URI for display
        row_display_info = {
            'dataset': 'Unknown',
            'source': 'Unknown',
            'row_number': None,
            'display_name': row.name or "(unnamed)"
        }
        
        if row.uri:
            # Expected URI pattern: http://arkumu.org/data/{source}/datasets/{dataset}/rows/{row_number}
            try:
                uri_parts = row.uri.split('/')
                if 'data' in uri_parts and 'datasets' in uri_parts and 'rows' in uri_parts:
                    data_index = uri_parts.index('data')
                    datasets_index = uri_parts.index('datasets')
                    rows_index = uri_parts.index('rows')
                    
                    if (data_index + 1 < len(uri_parts) and 
                        datasets_index + 1 < len(uri_parts) and 
                        rows_index + 1 < len(uri_parts)):
                        
                        row_display_info['source'] = uri_parts[data_index + 1]
                        row_display_info['dataset'] = uri_parts[datasets_index + 1]
                        row_display_info['row_number'] = uri_parts[rows_index + 1]
                        row_display_info['display_name'] = f"Row {row_display_info['row_number']}"
            except (ValueError, IndexError):
                logger.warning(f"Could not parse row URI: {row.uri}")
        
        # Get row statistics - count cells in this row
        has_part_predicate = Resource.objects.filter(
            uri="http://purl.org/dc/terms/hasPart",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        rdf_value_predicate = Resource.objects.filter(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            resource_type=ResourceType.PROPERTY
        ).first()
        
        stats = {
            'total_cells': 0,
            'columns': []
        }
        
        # Count cells and get column information
        if rdf_value_predicate and row.uri:
            # Extract row number from URI for cell pattern matching
            row_uri_parts = row.uri.split('/')
            if 'rows' in row_uri_parts:
                rows_index = row_uri_parts.index('rows')
                if rows_index + 1 < len(row_uri_parts):
                    row_number = row_uri_parts[rows_index + 1]
                    
                    # Find cells that end with this row number and belong to this dataset
                    dataset_path = row.uri.replace('/rows/' + row_number, '')  # Remove /rows/123 part
                    
                    # Look for cells: {dataset_path}/{column}/{row_number}
                    cell_resources = Resource.objects.filter(
                        resource_type=ResourceType.IRI,
                        uri__startswith=dataset_path + '/',
                        uri__endswith='/' + row_number,
                        subject_triples__predicate=rdf_value_predicate
                    ).exclude(
                        uri=row.uri  # Exclude the row itself
                    )
                    
                    stats['total_cells'] = cell_resources.count()
                    
                    # Extract column names
                    columns = set()
                    for cell in cell_resources:
                        try:
                            # Extract column from URI: .../dataset/column/row_number
                            cell_parts = cell.uri.split('/')
                            if len(cell_parts) >= 2:
                                column = cell_parts[-2]  # Second to last part is column
                                columns.add(column)
                        except Exception:
                            pass
                    
                    stats['columns'] = sorted(list(columns))
        
        # Get any metadata triples for this row
        row_triples = Triple.objects.filter(
            subject=row
        ).exclude(
            predicate=has_part_predicate if has_part_predicate else None
        ).select_related('predicate', 'object')[:10]
        
        row_metadata = []
        for triple in row_triples:
            # Create readable predicate name
            predicate_name = None
            if triple.predicate.uri:
                uri = triple.predicate.uri
                if uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
                    predicate_name = "rdf:type"
                elif uri == "http://www.w3.org/2000/01/rdf-schema#label":
                    predicate_name = "rdfs:label"
                elif "http://www.w3.org/1999/02/22-rdf-syntax-ns#" in uri:
                    predicate_name = f"rdf:{uri.split('#')[-1]}"
                elif "http://purl.org/dc/terms/" in uri:
                    predicate_name = f"dcterms:{uri.split('/')[-1]}"
                elif "http://www.w3.org/2000/01/rdf-schema#" in uri:
                    predicate_name = f"rdfs:{uri.split('#')[-1]}"
                else:
                    predicate_name = uri.split('/')[-1] if '/' in uri else uri.split('#')[-1] if '#' in uri else uri
            
            if not predicate_name:
                predicate_name = triple.predicate.name or f"Property {triple.predicate.id}"
            
            if triple.object.resource_type == ResourceType.LITERAL:
                value = triple.object.value or "(empty)"
            else:
                value = triple.object.name or triple.object.uri or f"Resource {triple.object.id}"
            
            row_metadata.append({
                'predicate': predicate_name,
                'predicate_uri': triple.predicate.uri,
                'value': value,
                'is_literal': triple.object.resource_type == ResourceType.LITERAL
            })
        
        return render(request, 'partials/row_details.html', {
            'row': row,
            'row_display_info': row_display_info,
            'stats': stats,
            'row_metadata': row_metadata
        })
        
    except Resource.DoesNotExist:
        return render(request, 'partials/tree_error.html', {
            'error': 'Row not found'
        }) 