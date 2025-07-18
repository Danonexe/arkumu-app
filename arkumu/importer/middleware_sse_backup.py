"""
SSE Authentication Middleware

This middleware ensures that users can only subscribe to SSE channels
for import sessions they own, providing security for the real-time
progress updates.
"""

import logging
from django.http import HttpResponseForbidden
from arkumu.importer.models import IngestSession

logger = logging.getLogger(__name__)


class SSEAuthMiddleware:
    """
    Verify user has permission to subscribe to import channels.
    
    This middleware intercepts requests to SSE stream endpoints and
    validates that the authenticated user has permission to access
    the requested import channel.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if this is an SSE stream request
        if request.path.startswith('/events/stream/'):
            channel = request.GET.get('channel', '')
            
            # Only check import channels
            if channel.startswith('import-'):
                try:
                    # Extract session primary key from channel
                    # Handle UUID format: import-4e5cf6df-e3de-45e1-9072-8ef12673d388
                    if channel.count('-') > 1:
                        # UUID format - take everything after 'import-'
                        session_pk_str = channel[7:]  # Skip 'import-'
                    else:
                        # Integer format - take the part after first hyphen
                        session_pk_str = channel.split('-')[1]
                    
                    # Convert to appropriate type (UUID or int)
                    try:
                        # Try UUID first (IngestSession uses UUID)
                        import uuid
                        session_pk = uuid.UUID(session_pk_str)
                    except ValueError:
                        # Fall back to int if not UUID
                        session_pk = int(session_pk_str)
                    
                    # Get the session
                    session = IngestSession.objects.get(pk=session_pk)
                    
                    # Check authentication and ownership
                    if not hasattr(request, 'user') or request.user is None or not request.user.is_authenticated:
                        logger.warning(f"Unauthenticated user attempted to access channel: {channel}")
                        return HttpResponseForbidden("Authentication required")
                    
                    if session.user != request.user:
                        logger.warning(f"User {request.user.username} attempted to access channel for session owned by {session.user.username}")
                        return HttpResponseForbidden("Unauthorized")
                    
                except (ValueError, IngestSession.DoesNotExist) as e:
                    logger.warning(f"Invalid channel requested: {channel} - {e}")
                    return HttpResponseForbidden("Invalid channel")
                except Exception as e:
                    logger.error(f"Error validating SSE channel access: {e}")
                    return HttpResponseForbidden("Access denied")
        
        return self.get_response(request)