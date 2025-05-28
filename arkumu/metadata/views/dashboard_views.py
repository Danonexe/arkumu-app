from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.core.paginator import Paginator
import json
import logging
import re
from django.http import JsonResponse

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import UploadSession, S3FileObject

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def metadata_dashboard(request):
    """Main dashboard view for metadata visualization and analysis."""
    # Get basic statistics
    stats = {
        'total_resources': Resource.objects.count(),
        'total_triples': Triple.objects.count(),
        'iri_resources': Resource.objects.filter(resource_type=ResourceType.IRI).count(),
        'literal_resources': Resource.objects.filter(resource_type=ResourceType.LITERAL).count(),
        'class_resources': Resource.objects.filter(resource_type=ResourceType.CLASS).count(),
        'property_resources': Resource.objects.filter(resource_type=ResourceType.PROPERTY).count(),
        'uploads': UploadSession.objects.count(),
    }
    
    # Get recent uploads
    recent_uploads = UploadSession.objects.all().order_by('-created_at')[:5]
    
    # Get institutions with resource counts
    institutions = Resource.objects.values('source').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    return render(request, 'dashboard.html', {
        'stats': stats,
        'recent_uploads': recent_uploads,
        'institutions': institutions,
    })

@login_required
def resource_list(request):
    """Paginated list of resources with filters."""
    # Get filter parameters
    resource_type = request.GET.get('type', '')
    institution = request.GET.get('institution', '')
    search_query = request.GET.get('q', '')
    page = request.GET.get('page', 1)
    
    # Base queryset
    resources = Resource.objects.all()
    
    # Apply filters
    if resource_type:
        resources = resources.filter(resource_type=resource_type)
    if institution:
        resources = resources.filter(source=institution)
    if search_query:
        resources = resources.filter(
            Q(uri__icontains=search_query) | 
            Q(value__icontains=search_query) |
            Q(name__icontains=search_query)
        )
    
    # Paginate
    paginator = Paginator(resources.order_by('-id'), 20)
    page_obj = paginator.get_page(page)
    
    # Check if HTMX request
    if request.headers.get('HX-Request'):
        return render(request, 'partials/resource_list.html', {
            'page_obj': page_obj,
        })
    
    return render(request, 'resource_list.html', {
        'page_obj': page_obj,
        'resource_types': ResourceType.choices,
        'institutions': Resource.objects.values_list('source', flat=True).distinct(),
    })

@login_required
def resource_detail(request, resource_id):
    """Detailed view of a single resource with its triples."""
    resource = Resource.objects.get(id=resource_id)
    
    # Get related triples
    subject_triples = Triple.objects.filter(subject=resource).select_related('predicate', 'object')
    object_triples = Triple.objects.filter(object=resource).select_related('subject', 'predicate')
    
    # Find linked files
    linked_files = []
    if resource.resource_type == ResourceType.IRI and resource.uri:
        linked_files = S3FileObject.objects.filter(related_resource_uri=resource.uri)
    
    return render(request, 'resource_detail.html', {
        'resource': resource,
        'subject_triples': subject_triples,
        'object_triples': object_triples,
        'linked_files': linked_files,
    })

@login_required
def triple_search(request):
    """Search triples with advanced filtering."""
    subject = request.GET.get('subject', '')
    predicate = request.GET.get('predicate', '')
    object_value = request.GET.get('object', '')
    institution = request.GET.get('institution', '')
    
    # Log the search parameters
    logger.info(f"Triple search request: subject='{subject}', predicate='{predicate}', object='{object_value}', institution='{institution}'")
    logger.info(f"Headers: HX-Request: {request.headers.get('HX-Request')}, HX-Trigger: {request.headers.get('HX-Trigger')}")
    
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    if subject:
        triples = triples.filter(Q(subject__uri__icontains=subject) | Q(subject__value__icontains=subject) | Q(subject__name__icontains=subject))
    if predicate:
        triples = triples.filter(Q(predicate__uri__icontains=predicate) | Q(predicate__value__icontains=predicate) | Q(predicate__name__icontains=predicate))
    if object_value:
        triples = triples.filter(Q(object__uri__icontains=object_value) | Q(object__value__icontains=object_value) | Q(object__name__icontains=object_value))
    if institution:
        triples = triples.filter(Q(subject__source=institution) | Q(object__source=institution))
    
    # Log the query count
    result_count = triples.count()
    logger.info(f"Triple search found {result_count} results")
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Check if HTMX request
    if request.headers.get('HX-Request'):
        logger.info(f"Rendering partial template for HTMX request (page {page})")
        return render(request, 'partials/triple_list.html', {
            'page_obj': page_obj,
            'is_paginated': paginator.num_pages > 1,
            'triples': triples,
        })
    
    logger.info("Rendering full triple search template")
    return render(request, 'triple_search.html', {
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'triples': triples,
        'institutions': Resource.objects.values_list('source', flat=True).distinct(),
    })

@login_required
def resource_graph(request, resource_id):
    """Show a visual graph of relationships for a resource."""
    resource = Resource.objects.get(id=resource_id)
    
    # Get direct relationships (1 level)
    subject_triples = Triple.objects.filter(subject=resource).select_related('predicate', 'object')
    object_triples = Triple.objects.filter(object=resource).select_related('subject', 'predicate')
    
    # Build graph data for D3.js
    nodes = []
    links = []
    
    # Add center node
    nodes.append({
        'id': str(resource.id),
        'name': resource.name or 'Unnamed',
        'type': resource.resource_type,
        'uri': resource.uri,
        'value': resource.value,
        'group': 1
    })
    
    # Add subject triples
    for triple in subject_triples:
        # Add object node
        obj_id = str(triple.object.id)
        nodes.append({
            'id': obj_id,
            'name': triple.object.name or 'Unnamed',
            'type': triple.object.resource_type,
            'uri': triple.object.uri,
            'value': triple.object.value,
            'group': 2
        })
        
        # Add link
        links.append({
            'source': str(resource.id),
            'target': obj_id,
            'value': 1,
            'label': triple.predicate.name or triple.predicate.uri.split('/')[-1]
        })
    
    # Add object triples
    for triple in object_triples:
        # Add subject node
        subj_id = str(triple.subject.id)
        nodes.append({
            'id': subj_id,
            'name': triple.subject.name or 'Unnamed',
            'type': triple.subject.resource_type,
            'uri': triple.subject.uri,
            'value': triple.subject.value,
            'group': 3
        })
        
        # Add link
        links.append({
            'source': subj_id,
            'target': str(resource.id),
            'value': 1,
            'label': triple.predicate.name or triple.predicate.uri.split('/')[-1]
        })
    
    # Remove duplicate nodes
    unique_nodes = {node['id']: node for node in nodes}.values()
    
    graph_data = {
        'nodes': list(unique_nodes),
        'links': links
    }
    
    return render(request, 'resource_graph.html', {
        'resource': resource,
        'graph_data': json.dumps(graph_data)
    })

@login_required
def triple_list(request):
    """Display a paginated list of all triples in the system."""
    # Get filter parameters
    institution = request.GET.get('institution', '')
    page = request.GET.get('page', 1)
    
    # Base queryset
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    # Apply filters
    if institution:
        triples = triples.filter(Q(subject__source=institution) | Q(object__source=institution))
    
    # Get stats
    total_triples = Triple.objects.count()
    institutions = Resource.objects.values_list('source', flat=True).distinct()
    institution_count = institutions.count()
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 20)
    page_obj = paginator.get_page(page)
    
    return render(request, 'triple_list.html', {
        'page_obj': page_obj,
        'total_triples': total_triples,
        'institutions': institutions,
        'institution_count': institution_count,
        'institution': institution,
    })

@login_required
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
    
    return render(request, 'triple_viewer.html', {
        'graph_data_json': json.dumps({
            'tree_data': tree_data,
            'graph_data': graph_data
        })
    })

@login_required
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
            predicate_name = triple.predicate.name or triple.predicate.uri.split('/')[-1] if triple.predicate.uri else f"Pred {triple.predicate.id}"
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


