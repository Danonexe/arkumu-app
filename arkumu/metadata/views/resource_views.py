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
    
    return render(request, 'resource_list.html', {
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
    
    return render(request, 'resource_graph.html', {
        'resource': resource,
        'graph_data': json.dumps(graph_data)
    })

class MapS3ToResourcesView(LoginRequiredMixin, View):
    template_name = 'map_s3_to_resources.html'
    success_url = reverse_lazy('metadata:map_s3_to_resources')

    def get(self, request, *args, **kwargs):
        # Retrieve bucket_name and prefix from query parameters to repopulate form if needed (e.g., after POST redirect)
        bucket_name = request.GET.get('bucket_name', '')
        prefix = request.GET.get('prefix', '')

        unmapped_files_qs = S3FileObject.objects.filter(related_resource__isnull=True).order_by('-created_at')
        
        paginator = Paginator(unmapped_files_qs, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'total_unmapped_count': unmapped_files_qs.count(),
            'form_data': {'bucket_name': bucket_name, 'prefix': prefix} # Pass form data back
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        bucket_name = request.POST.get('bucket_name')
        prefix = request.POST.get('prefix', "").strip() # Default to empty string and strip whitespace

        if not bucket_name:
            messages.error(request, "S3 Bucket Name is required.")
            return redirect(self.success_url) # Or render the form with an error

        service = FileResourceMatcherService(logger=messages.debug) # Pass messages.debug for detailed logging in template
        
        # Stage 1: Discover and Sync S3 Files
        try:
            messages.info(request, f"Starting S3 discovery and sync for bucket: <b>{bucket_name}</b>, prefix: <b>'{prefix if prefix else "(root)"}'</b>...", extra_tags='safe')
            synced_count, created_count, skipped_s3_count, error_s3_create_count = service.discover_and_sync_s3_files(bucket_name, prefix)
            messages.success(
                request, 
                f"S3 discovery and sync complete for <b>{bucket_name}</b>. "
                f"DB records in sync/already existed: {synced_count}, New S3FileObjects created: {created_count}, "
                f"Skipped S3 items (folders/invalid): {skipped_s3_count}, Errors during S3FileObject creation: {error_s3_create_count}.",
                extra_tags='safe'
            )
            if error_s3_create_count > 0:
                messages.warning(request, f"There were {error_s3_create_count} errors creating S3FileObject records. Check debug messages or server logs.")

        except Exception as e:
            messages.error(request, f"A critical error occurred during S3 discovery/sync: {e}")
            # Redirect with form data to allow user to see their input
            return redirect(f"{self.success_url}?bucket_name={bucket_name}&prefix={prefix}")

        # Stage 2: Match and Link Files to Resources
        try:
            messages.info(request, "Starting process to link S3FileObjects to Resources...", extra_tags='safe')
            processed_match_count, linked_count, ambiguous_match_count, error_match_count = service.match_and_link_by_filename_to_resource_value()
            
            messages.success(
                request, 
                f"File to Resource linking process completed. "
                f"S3FileObjects processed for linking: {processed_match_count}, Newly linked: {linked_count}, "
                f"Ambiguous matches (not linked): {ambiguous_match_count}, Errors during linking: {error_match_count}.",
                extra_tags='safe'
            )
            if error_match_count > 0:
                messages.warning(request, f"There were {error_match_count} errors during the linking process. Check debug messages or server logs.")
            if ambiguous_match_count > 0:
                messages.info(request, f"{ambiguous_match_count} files had ambiguous matches and were not linked. Consider refining Resource values or filenames for these.")
            if linked_count == 0 and processed_match_count > 0 and ambiguous_match_count == 0 and error_match_count == 0:
                 messages.info(request, "No new files were linked in this run. All unmapped files considered either had no match or were previously processed.")

        except Exception as e:
            messages.error(request, f"A critical error occurred during the linking service execution: {e}")
        
        # Redirect with form data to allow user to see their input and updated unmapped list
        return redirect(f"{self.success_url}?bucket_name={bucket_name}&prefix={prefix}") 