import logging
import os
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from arkumu.storage.services.bucket_service import BucketService
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy
from arkumu.importer.tasks.import_metadata import run_csv_import_workflow
from arkumu.importer.models import IngestSession

logger = logging.getLogger(__name__)


@login_required
def ingest_file(request):
    """
    Ingest a CSV file using the ImportWorkflowService
    """
    if request.method == "POST":
        file_path = request.POST.get('file_path')
        organization_slug = request.POST.get('organization') # This is the org slug/short_name

        if not file_path or not organization_slug:
            return JsonResponse({'error': 'Missing file_path or organization'}, status=400)

        # Determine dataset name from file_path (e.g., remove extension)
        dataset_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Instantiate bucket service
        bucket_service = BucketService()
        
        # Get bucket name for organization
        s3_bucket_name = bucket_service.get_organization_bucket(organization_slug) # Renamed for clarity
        s3_object_key = file_path # Renamed for clarity
        
        # Check if it's a CSV file
        if not s3_object_key.lower().endswith('.csv'):
            # For HTMX, return a partial that can be swapped into the UI
            # This assumes you have a way to display this message in your poller or target div
            return render(request, 'importer/partials/task_status_poller.html', {
                'task_id': 'error-non-csv', # Provide a dummy or identifiable ID
                'task_info': {
                    'status': 'failed',
                    'message': 'Only CSV files can be ingested.',
                    'error_type': 'ValidationError'
                },
                'should_poll': False 
            }, status=400)

        logger.info(
            f"Preparing to enqueue ingest of S3 object {s3_bucket_name}/{s3_object_key} as dataset '{dataset_name}' for organization {organization_slug}"
        )

        User = get_user_model()
        user_instance = User.objects.get(pk=request.user.pk) if request.user.is_authenticated else None

        # Create an IngestSession record to track this CSV ingestion
        import uuid
        polling_task_id = str(uuid.uuid4())
        
        ingest_session = IngestSession.objects.create(
            user=user_instance,
            dataset_name=dataset_name,
            organization=organization_slug,
            s3_bucket=s3_bucket_name,
            s3_object_key=s3_object_key,
            status='pending',  # Will be updated when task starts
            delimiter=';',
            has_quoted_fields=True,
            base_uri="http://arkumu.org/data",
            task_id=polling_task_id,
        )
        
        # Enqueue the Huey task, now passing s3_bucket_name and s3_object_key, and ingest_session_id
        task_instance = run_csv_import_workflow(
            s3_bucket_name=s3_bucket_name,
            s3_object_key=s3_object_key,
            dataset_name=dataset_name,
            institution=organization_slug.upper(), # Convention from previous versions
            base_uri="http://arkumu.org/data",
            delimiter=';',
            has_quoted_fields=True,
            link_row_cells=True,
            link_to_first_column=False, # Default, or make configurable
            update_strategy=UpdateStrategy.SKIP_EXISTING, # Default, or make configurable
            task_id_for_cache=polling_task_id, # Pass the generated ID for caching
            upload_session_id=ingest_session.id # Pass the ID of the new IngestSession (keeping param name for compatibility)
        )
        
        # Update the ingest session with the Huey task ID
        ingest_session.huey_task_id = str(task_instance.id)
        ingest_session.save()
        
        # Store initial status for the HTMX poller
        cache_key = f"task_status_{polling_task_id}"
        initial_task_info = {
            "status": "pending", 
            "message": f"CSV ingestion for '{os.path.basename(s3_object_key)}' has been queued.",
            "progress": 0
        }
        cache.set(cache_key, initial_task_info, timeout=3600) # Cache for 1 hour

        logger.info(
            f"Enqueued CSV import task. Polling ID: {polling_task_id}, Huey Task ID: {task_instance.id} for S3 object '{s3_bucket_name}/{s3_object_key}'"
        )
        
        # Return the poller template immediately for HTMX
        return render(request, 'importer/partials/task_status_poller.html', {
            'task_id': polling_task_id,
            'task_info': initial_task_info,
            'should_poll': True # Start polling
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def reset_database(request):
    """
    Reset the database by deleting all Resource and Triple records.
    This is useful for development and testing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from arkumu.metadata.models.resource import Resource
        from arkumu.metadata.models.triples import Triple
        from django.db import transaction
        
        with transaction.atomic():
            # Delete all triples first (due to foreign key constraints)
            triple_count = Triple.objects.count()
            Triple.objects.all().delete()
            
            # Delete all resources
            resource_count = Resource.objects.count()
            Resource.objects.all().delete()
            
        logger.info(f"Database reset completed: deleted {triple_count} triples and {resource_count} resources")
        
        # Return HTMX-friendly response
        if request.headers.get('HX-Request') == 'true':
            from django.template.loader import render_to_string
            success_html = f"""
            <div class="alert alert-success">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                    <h3 class="font-bold">Database Reset Successful!</h3>
                    <div class="text-xs">Deleted {triple_count} triples and {resource_count} resources</div>
                </div>
            </div>
            """
            return HttpResponse(success_html)
        
        return JsonResponse({
            'success': True,
            'message': f'Database reset successful! Deleted {triple_count} triples and {resource_count} resources.',
            'triples_deleted': triple_count,
            'resources_deleted': resource_count
        })
        
    except Exception as e:
        error_message = f'Failed to reset database: {str(e)}'
        logger.error(f"Database reset error: {e}", exc_info=True)
        
        return JsonResponse({
            'error': error_message
        }, status=500)


@login_required
def task_status_view(request, task_id):
    """
    Provides the status of a background task for HTMX polling.
    Reads the status from Django's cache.
    """
    cache_key = f"task_status_{task_id}"
    task_info = cache.get(cache_key)

    if not task_info:
        task_info = {
            "status": "pending",
            "message": "Task status not yet available or task ID is invalid. Waiting for initialization...",
            "progress": 0
        }

    # Determine if polling should continue
    # Stop polling if status is 'completed' or 'failed'
    should_poll = task_info.get("status") not in ["completed", "failed"]
    
    # Default polling interval is 2 seconds, can be adjusted
    # If task is completed or failed, hx-trigger can be set to none or a very long interval if needed
    # but the template itself will handle not re-triggering via hx-swap conditional.

    return render(request, "importer/partials/task_status_poller.html", {
        "task_id": task_id,
        "task_info": task_info,
        "should_poll": should_poll 
    })


@login_required
def clear_upload_sessions(request):
    """
    Clear all UploadSession records.
    This is useful for development and testing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from arkumu.storage.models.upload_sessions import UploadSession
        from django.db import transaction
        
        with transaction.atomic():
            # Count before deletion
            upload_count = UploadSession.objects.count()
            # Delete all upload sessions
            UploadSession.objects.all().delete()
            
        logger.info(f"Upload sessions cleared: deleted {upload_count} upload sessions")
        
        # Return HTMX-friendly response
        if request.headers.get('HX-Request') == 'true':
            success_html = f"""
            <div class="alert alert-success">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                    <h3 class="font-bold">Upload Sessions Cleared!</h3>
                    <div class="text-xs">Deleted {upload_count} upload sessions</div>
                </div>
            </div>
            """
            return HttpResponse(success_html)
        
        return JsonResponse({
            'success': True,
            'message': f'Upload sessions cleared! Deleted {upload_count} upload sessions.',
            'upload_sessions_deleted': upload_count
        })
        
    except Exception as e:
        error_message = f'Failed to clear upload sessions: {str(e)}'
        logger.error(f"Clear upload sessions error: {e}", exc_info=True)
        
        return JsonResponse({
            'error': error_message
        }, status=500)


@login_required
def clear_ingest_sessions(request):
    """
    Clear all IngestSession records.
    This is useful for development and testing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from arkumu.importer.models.ingest_sessions import IngestSession
        from django.db import transaction
        
        with transaction.atomic():
            # Count before deletion
            ingest_count = IngestSession.objects.count()
            # Delete all ingest sessions
            IngestSession.objects.all().delete()
            
        logger.info(f"Ingest sessions cleared: deleted {ingest_count} ingest sessions")
        
        # Return HTMX-friendly response
        if request.headers.get('HX-Request') == 'true':
            success_html = f"""
            <div class="alert alert-success">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                    <h3 class="font-bold">Ingest Sessions Cleared!</h3>
                    <div class="text-xs">Deleted {ingest_count} ingest sessions</div>
                </div>
            </div>
            """
            return HttpResponse(success_html)
        
        return JsonResponse({
            'success': True,
            'message': f'Ingest sessions cleared! Deleted {ingest_count} ingest sessions.',
            'ingest_sessions_deleted': ingest_count
        })
        
    except Exception as e:
        error_message = f'Failed to clear ingest sessions: {str(e)}'
        logger.error(f"Clear ingest sessions error: {e}", exc_info=True)
        
        return JsonResponse({
            'error': error_message
        }, status=500) 