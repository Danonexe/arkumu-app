"""
Simple progress monitoring views for import tasks
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.utils import timezone
import json

from arkumu.importer.models import IngestSession
from arkumu.importer.services.task_manager import get_task_manager, CancellationReason


def progress_monitor_view(request, task_id):
    """Main progress monitoring view"""
    context = {
        'task_id': task_id,
        'session_id': request.GET.get('session_id'),
    }
    return render(request, 'importer/progress_monitor.html', context)


@require_http_methods(["GET"])
def task_status_api(request, task_id):
    """Get task status for HTMX polling"""
    try:
        # Get from cache first
        cache_key = f"task_state_{task_id}"
        task_data = cache.get(cache_key)
        
        if not task_data:
            # Fallback to session lookup
            session_id = request.GET.get('session_id')
            if session_id:
                try:
                    session = IngestSession.objects.get(id=session_id)
                    task_data = {
                        'task_id': task_id,
                        'state': session.status,
                        'progress': 0,
                        'phase': 'unknown',
                        'error_message': session.error_message,
                        'start_time': session.created_at.isoformat() if session.created_at else None,
                        'end_time': session.completed_at.isoformat() if session.completed_at else None,
                        'cancellation_requested': False,
                        'cancellation_reason': None,
                    }
                except IngestSession.DoesNotExist:
                    task_data = {
                        'task_id': task_id,
                        'state': 'not_found',
                        'progress': 0,
                        'phase': 'unknown',
                        'error_message': 'Task not found',
                    }
            else:
                # No session ID provided
                task_data = {
                    'task_id': task_id,
                    'state': 'not_found',
                    'progress': 0,
                    'phase': 'unknown',
                    'error_message': 'Task not found',
                }
        
        # Return HTML for HTMX
        return render(request, 'importer/progress_monitor.html', {
            'task_id': task_id,
            'task': task_data,
            'session_id': request.GET.get('session_id'),
        })
        
    except Exception as e:
        return render(request, 'importer/progress_monitor.html', {
            'task_id': task_id,
            'task': {
                'task_id': task_id,
                'state': 'error',
                'progress': 0,
                'phase': 'error',
                'error_message': str(e),
            },
            'session_id': request.GET.get('session_id'),
        })


@csrf_exempt
@require_http_methods(["POST"])
def cancel_task_api(request, task_id):
    """Cancel a task"""
    try:
        data = json.loads(request.body) if request.body else {}
        reason = data.get('reason', 'user_requested')
        
        # Map string reason to enum
        reason_mapping = {
            'user_requested': CancellationReason.USER_REQUESTED,
            'timeout': CancellationReason.TIMEOUT,
            'resource_exhausted': CancellationReason.RESOURCE_EXHAUSTED,
            'system_shutdown': CancellationReason.SYSTEM_SHUTDOWN,
            'error_threshold': CancellationReason.ERROR_THRESHOLD
        }
        
        cancellation_reason = reason_mapping.get(reason, CancellationReason.USER_REQUESTED)
        
        manager = get_task_manager()
        success = manager.request_cancellation(task_id, cancellation_reason)
        
        # Get updated task status
        cache_key = f"task_state_{task_id}"
        task_data = cache.get(cache_key, {})
        
        if success:
            task_data['state'] = 'cancelling'
            task_data['cancellation_requested'] = True
            task_data['cancellation_reason'] = reason
        
        # Return updated progress monitor
        return render(request, 'importer/progress_monitor.html', {
            'task_id': task_id,
            'task': task_data,
            'session_id': request.GET.get('session_id'),
        })
        
    except Exception as e:
        # Return error state
        return render(request, 'importer/progress_monitor.html', {
            'task_id': task_id,
            'task': {
                'task_id': task_id,
                'state': 'error',
                'progress': 0,
                'phase': 'error',
                'error_message': f'Failed to cancel: {str(e)}',
            },
            'session_id': request.GET.get('session_id'),
        })