"""
Progress Publisher Utility for HTMX Polling

This module provides utilities for publishing progress updates via cache-based storage
for HTMX polling. It replaces the previous SSE-based implementation with a simpler
cache-based approach.
"""

import logging
import time
from typing import Dict, Any
from arkumu.importer.services.progress_cache import ProgressCacheService

logger = logging.getLogger(__name__)


def publish_progress(
    session_pk: str, 
    payload: Dict[str, Any], 
    event: str = "progress"
) -> None:
    """
    Update progress data in cache for HTMX polling.
    
    Args:
        session_pk: Session primary key
        payload: Progress data
        event: Event type (progress, complete, error)
    """
    try:
        cache_service = ProgressCacheService()
        
        # Add event type and timestamp to payload
        progress_data = {
            **payload,
            'event_type': event,
            'timestamp': time.time()
        }
        
        cache_service.update_progress(session_pk, progress_data)
        logger.debug(f"Published {event} for session {session_pk}: {payload}")
    except Exception as e:
        logger.error(f"Failed to publish progress for session {session_pk}: {e}")
        # Don't raise exception to avoid breaking the import process


def create_channel_id(session_pk: int) -> str:
    """
    Generate consistent channel ID for a session.
    
    Args:
        session_pk: Primary key of the IngestSession
        
    Returns:
        Channel identifier string (maintained for backward compatibility)
    """
    return f"import-{session_pk}"