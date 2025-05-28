from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
import json

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import S3FileObject

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