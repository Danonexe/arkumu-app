from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q
from django.core.paginator import Paginator
import json

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import S3FileObject
from arkumu.metadata.services.map_resources_to_files import FileResourceMatcherService

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
    
    # Check if HTMX request for pagination/filtering
    if request.headers.get('HX-Request') and request.GET.get('page'):
        return render(request, 'partials/resource_list.html', {
            'page_obj': page_obj,
        })
    
    return render(request, 'metadata/resource_list.html', {
        'page_obj': page_obj,
        'resource_types': ResourceType.choices,
        'institutions': Resource.objects.values_list('source', flat=True).distinct().order_by('source'),
        'current_type': resource_type,
        'current_institution': institution,
        'current_query': search_query,
    })

@login_required
def resource_detail(request, resource_id):
    """Detailed view of a single resource with its triples."""
    resource = Resource.objects.get(id=resource_id)
    
    # Get related triples
    subject_triples = Triple.objects.filter(subject=resource).select_related('predicate', 'object')
    object_triples = Triple.objects.filter(object=resource).select_related('subject', 'predicate')
    
    # Find linked files using the ForeignKey
    linked_files = S3FileObject.objects.filter(related_resource=resource)
    
    return render(request, 'metadata/resource_detail.html', {
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
    node_ids = set()

    def add_node(res_obj, group_val):
        if res_obj.id not in node_ids:
            nodes.append({
                'id': str(res_obj.id),
                'name': str(res_obj),
                'type': res_obj.resource_type,
                'group': group_val
            })
            node_ids.add(res_obj.id)

    # Add center node
    add_node(resource, 1)
    
    # Add subject triples (resource is subject)
    for triple in subject_triples:
        add_node(triple.object, 2)
        links.append({
            'source': str(resource.id),
            'target': str(triple.object.id),
            'value': 1,
            'label': str(triple.predicate)
        })
    
    # Add object triples (resource is object)
    for triple in object_triples:
        add_node(triple.subject, 3)
        links.append({
            'source': str(triple.subject.id),
            'target': str(resource.id),
            'value': 1,
            'label': str(triple.predicate)
        })
        
    graph_data = {
        'nodes': nodes,
        'links': links
    }
    
    return render(request, 'metadata/resource_graph.html', {
        'resource': resource,
        'graph_data': json.dumps(graph_data)
    })

class MapS3ToResourcesView(LoginRequiredMixin, View):
    template_name = 'metadata/map_s3_to_resources.html'
    success_url = reverse_lazy('metadata:map_s3_to_resources')

    def get(self, request, *args, **kwargs):
        unmapped_files_qs = S3FileObject.objects.filter(related_resource__isnull=True).order_by('-created_at')
        
        paginator = Paginator(unmapped_files_qs, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'total_unmapped_count': unmapped_files_qs.count(),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        service = FileResourceMatcherService(logger=messages.debug)
        
        try:
            processed_count, linked_count, ambiguous_count, error_count = service.match_and_link_by_filename_to_resource_value()
            
            messages.success(request, 
                             f"File to Resource mapping process completed. "
                             f"Processed: {processed_count}, Linked: {linked_count}, "
                             f"Ambiguous Matches (not linked): {ambiguous_count}, Errors: {error_count}."
                            )
            if error_count > 0:
                messages.warning(request, f"There were {error_count} errors during the process. Check server logs or debug messages for details.")
            if ambiguous_count > 0:
                messages.info(request, f"{ambiguous_count} files had ambiguous matches and were not linked. Consider refining Resource values or filenames.")
            if linked_count == 0 and processed_count > 0 and ambiguous_count == 0 and error_count == 0:
                 messages.info(request, "No new files were linked. All unmapped files either had no match or were already processed.")

        except Exception as e:
            messages.error(request, f"A critical error occurred during the mapping service execution: {e}")
        
        return redirect(self.success_url) 