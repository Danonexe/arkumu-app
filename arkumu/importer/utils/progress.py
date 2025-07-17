"""
Progress Publisher Utility for SSE

This module provides utilities for publishing progress updates via Server-Sent Events (SSE)
using django-eventstream. It includes functions for sending progress updates and generating
consistent channel identifiers.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def publish_progress(
    channel: str, 
    payload: Dict[str, Any], 
    event: str = "progress"
) -> None:
    """
    Send a JSON-serializable payload over SSE.
    
    Args:
        channel: Channel identifier (e.g., 'import-123')
        payload: Data to send (must be JSON-serializable)
        event: Event type (default: 'progress')
    """
    try:
        from django_eventstream import send_event
        send_event(channel, event, payload)
        logger.debug(f"Published {event} event to channel {channel}: {payload}")
    except Exception as e:
        logger.error(f"Failed to publish progress to channel {channel}: {e}")
        # Don't raise exception to avoid breaking the import process
        # SSE is nice-to-have, not critical functionality


def create_channel_id(session_pk: int) -> str:
    """
    Generate consistent channel ID for a session.
    
    Args:
        session_pk: Primary key of the IngestSession
        
    Returns:
        Channel identifier string
    """
    return f"import-{session_pk}"