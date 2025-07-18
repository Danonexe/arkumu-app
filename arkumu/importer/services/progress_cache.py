from typing import Dict, Any, Optional
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class ProgressCacheService:
    """Service for managing progress data in Django cache."""
    
    def __init__(self, cache_timeout: int = 3600):
        self.cache_timeout = cache_timeout
    
    def get_cache_key(self, session_pk: str) -> str:
        """Generate cache key for session progress."""
        return f"import_progress_{session_pk}"
    
    def update_progress(self, session_pk: str, progress_data: Dict[str, Any]) -> None:
        """Update progress data in cache."""
        cache_key = self.get_cache_key(session_pk)
        try:
            cache.set(cache_key, progress_data, timeout=self.cache_timeout)
            logger.debug(f"Updated progress for session {session_pk}: {progress_data}")
        except Exception as e:
            logger.error(f"Failed to update progress cache for session {session_pk}: {e}")
    
    def get_progress(self, session_pk: str) -> Optional[Dict[str, Any]]:
        """Get progress data from cache."""
        cache_key = self.get_cache_key(session_pk)
        return cache.get(cache_key)
    
    def clear_progress(self, session_pk: str) -> None:
        """Clear progress data from cache."""
        cache_key = self.get_cache_key(session_pk)
        cache.delete(cache_key)