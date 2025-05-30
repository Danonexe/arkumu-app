from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.decorators.http import require_http_methods
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Case, When, BooleanField
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.template.loader import render_to_string
import json

from arkumu.storage.models import S3FileObject, UploadSession
from arkumu.metadata.models import Resource
from arkumu.metadata.services.map_resources_to_files import FileResourceMatcherService


class DataDiscoveryView(LoginRequiredMixin, View):
    """Main data discovery interface showing S3 files and their linking status."""
    template_name = 'data_discovery.html'

    def get(self, request, *args, **kwargs):
        # Filter for files in "data" folders only (not metadata folders)
        s3_files = S3FileObject.objects.filter(
            s3_key__contains='/data/'
        ).select_related('related_resource', 'session', 'session__user').annotate(
            is_linked=Case(
                When(related_resource__isnull=False, then=True),
                default=False,
                output_field=BooleanField()
            )
        ).order_by('s3_key')

        # Group files by bucket (extract bucket from s3_key)
        files_by_bucket = {}
        for file in s3_files:
            # Extract bucket name from s3_key (assuming format: bucket/path/to/file)
            bucket_name = file.s3_key.split('/')[0] if '/' in file.s3_key else 'unknown'
            if bucket_name not in files_by_bucket:
                files_by_bucket[bucket_name] = []
            files_by_bucket[bucket_name].append(file)

        # Get statistics
        total_files = s3_files.count()
        linked_files = s3_files.filter(related_resource__isnull=False).count()
        unlinked_files = total_files - linked_files

        context = {
            'files_by_bucket': files_by_bucket,
            'total_files': total_files,
            'linked_files': linked_files,
            'unlinked_files': unlinked_files,
            'link_percentage': round((linked_files / total_files * 100) if total_files > 0 else 0, 1)
        }

        return render(request, self.template_name, context)


@login_required
@require_http_methods(["GET"])
def search_resources_api(request):
    """API endpoint to search for resources that could be linked to files."""
    query = request.GET.get('q', '').strip()
    
    if not query or len(query) < 2:
        return render(request, 'partials/search_results.html', {
            'resources': [],
            'query': query
        })

    # Search resources by value (case-insensitive)
    resources = Resource.objects.filter(
        Q(value__icontains=query) | Q(uri__icontains=query)
    )[:20]  # Limit results

    return render(request, 'partials/search_results.html', {
        'resources': resources,
        'query': query
    })


@login_required
@require_http_methods(["POST"])
def link_file_to_resource_api(request):
    """API endpoint to link a single file to a resource."""
    try:
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        file_id = data.get('file_id')
        resource_id = data.get('resource_id')

        if not file_id or not resource_id:
            return render(request, 'partials/toast.html', {
                'message': 'Missing file or resource information',
                'type': 'error'
            })

        # Get the objects
        s3_file = get_object_or_404(S3FileObject, id=file_id)
        resource = get_object_or_404(Resource, id=resource_id)

        # Link them
        s3_file.related_resource = resource
        s3_file.save()

        # Return updated files list
        return _get_files_list_response(request)

    except Exception as e:
        return render(request, 'partials/toast.html', {
            'message': f'Error linking file: {str(e)}',
            'type': 'error'
        })


@login_required
@require_http_methods(["POST"])
def batch_link_files_api(request):
    """API endpoint to batch link multiple files using the automated service."""
    try:
        # Get selected file IDs from form data
        file_ids = request.POST.getlist('selected_files')

        if not file_ids:
            return render(request, 'partials/toast.html', {
                'message': 'No files selected',
                'type': 'warning'
            })

        # Get the queryset of selected files
        selected_files = S3FileObject.objects.filter(id__in=file_ids)
        
        # Use the matching service for batch processing
        service = FileResourceMatcherService()
        processed, linked, ambiguous, errors = service.match_and_link_by_filename_to_resource_value(selected_files)

        # Return success toast and updated files list
        response = HttpResponse()
        response['HX-Refresh'] = 'true'  # Tell HTMX to refresh the page
        
        return render(request, 'partials/toast.html', {
            'message': f'Batch processing complete. Processed: {processed}, Linked: {linked}, Ambiguous: {ambiguous}, Errors: {errors}',
            'type': 'success' if errors == 0 else 'warning'
        })

    except Exception as e:
        return render(request, 'partials/toast.html', {
            'message': f'Batch linking failed: {str(e)}',
            'type': 'error'
        })


@login_required
@require_http_methods(["POST"])  
def unlink_file_api(request):
    """API endpoint to unlink a file from its resource."""
    try:
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
            
        file_id = data.get('file_id')

        if not file_id:
            return render(request, 'partials/toast.html', {
                'message': 'Missing file information',
                'type': 'error'
            })

        s3_file = get_object_or_404(S3FileObject, id=file_id)
        
        # Store the old resource for the message
        old_resource = s3_file.related_resource.value if s3_file.related_resource else None
        
        # Unlink
        s3_file.related_resource = None
        s3_file.save()

        # Return updated files list
        return _get_files_list_response(request)

    except Exception as e:
        return render(request, 'partials/toast.html', {
            'message': f'Error unlinking file: {str(e)}',
            'type': 'error'
        })


@login_required
@require_http_methods(["POST"])
def auto_link_all_api(request):
    """API endpoint to automatically link all unlinked files."""
    try:
        # Get all unlinked files in data folders
        unlinked_files = S3FileObject.objects.filter(
            s3_key__contains='/data/',
            related_resource__isnull=True
        )
        
        if not unlinked_files.exists():
            return render(request, 'partials/toast.html', {
                'message': 'No unlinked files found',
                'type': 'info'
            })
        
        # Use the matching service for batch processing
        service = FileResourceMatcherService()
        processed, linked, ambiguous, errors = service.match_and_link_by_filename_to_resource_value(unlinked_files)

        # Return success response and refresh page
        response = HttpResponse()
        response['HX-Refresh'] = 'true'  # Tell HTMX to refresh the page
        
        return render(request, 'partials/toast.html', {
            'message': f'Auto-linking complete. Processed: {processed}, Linked: {linked}, Ambiguous: {ambiguous}, Errors: {errors}',
            'type': 'success' if errors == 0 else 'warning'
        })

    except Exception as e:
        return render(request, 'partials/toast.html', {
            'message': f'Auto-linking failed: {str(e)}',
            'type': 'error'
        })


def _get_files_list_response(request):
    """Helper function to get updated files list HTML."""
    # Re-fetch files data
    s3_files = S3FileObject.objects.filter(
        s3_key__contains='/data/'
    ).select_related('related_resource', 'session', 'session__user').annotate(
        is_linked=Case(
            When(related_resource__isnull=False, then=True),
            default=False,
            output_field=BooleanField()
        )
    ).order_by('s3_key')

    # Group files by bucket
    files_by_bucket = {}
    for file in s3_files:
        bucket_name = file.s3_key.split('/')[0] if '/' in file.s3_key else 'unknown'
        if bucket_name not in files_by_bucket:
            files_by_bucket[bucket_name] = []
        files_by_bucket[bucket_name].append(file)

    return render(request, 'partials/files_list.html', {
        'files_by_bucket': files_by_bucket
    }) 