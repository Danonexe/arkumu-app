from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from arkumu.importer.models import IngestSession
from arkumu.importer.services.progress_cache import ProgressCacheService
import logging

logger = logging.getLogger(__name__)


@login_required
def import_progress_view(request, session_pk):
    """
    Get import progress for HTMX polling.
    
    Args:
        session_pk: IngestSession primary key
    """
    try:
        # Get the session and check ownership
        session = IngestSession.objects.get(pk=session_pk)
        
        if session.user != request.user:
            return HttpResponseForbidden("Unauthorized")
        
        # Get progress from cache
        cache_service = ProgressCacheService()
        progress_data = cache_service.get_progress(str(session_pk))
        
        if not progress_data:
            progress_data = {
                'status': 'pending',
                'message': 'Waiting to start...',
                'percentage': 0,
                'event_type': 'progress'
            }
        
        # Determine if polling should continue
        should_poll = progress_data.get('status') not in ['completed', 'failed']
        
        return render(request, 'importer/partials/progress_display_polling.html', {
            'session': session,
            'progress_data': progress_data,
            'should_poll': should_poll
        })
        
    except IngestSession.DoesNotExist:
        return HttpResponseForbidden("Session not found")
    except Exception as e:
        logger.error(f"Error getting progress for session {session_pk}: {e}")
        return HttpResponseForbidden("Error retrieving progress")