"""
Optimized search engine for handling long literal values without truncation.
Preserves complete data while maintaining search performance.
"""

from django.core.cache import cache
from django.db.models import Q, F, Value, IntegerField
from django.contrib.postgres.search import TrigramSimilarity, TrigramDistance
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from typing import List, Dict, Optional, Tuple
import re

from arkumu.metadata.models import Resource, ResourceType


class LongContentSearchEngine:
    """
    Search engine optimized for long literal values.
    Uses multi-stage search strategy to avoid truncation while maintaining performance.
    """
    
    def __init__(self, similarity_threshold: float = 0.3):
        self.similarity_threshold = similarity_threshold
        self.preview_threshold = 0.4  # Higher threshold for preview search
        
    def search_resources(self, query: str, user, limit: int = 100) -> List[Resource]:
        """
        Multi-stage search that handles long content efficiently.
        1. Fast preview search using smaller index
        2. Full content search for comprehensive results
        3. Intelligent ranking and deduplication
        """
        if not query or len(query) < 2:
            return []
        
        query = query.strip()
        cache_key = f"long_search:{query}:{user.organization.id if user.is_authenticated else 'anon'}"
        cached_results = cache.get(cache_key)
        
        if cached_results is not None:
            return list(Resource.objects.filter(id__in=cached_results))
        
        # Stage 1: Fast preview search
        preview_matches = self._search_previews(query, user, limit * 2)
        preview_ids = {r.id for r in preview_matches}
        
        # Stage 2: Full content search (only if we need more results)
        full_content_matches = []
        if len(preview_matches) < limit:
            remaining_limit = limit - len(preview_matches)
            full_content_matches = self._search_full_content(
                query, user, remaining_limit, exclude_ids=preview_ids
            )
        
        # Combine and rank results
        all_matches = list(preview_matches) + list(full_content_matches)
        ranked_results = self._rank_by_relevance(all_matches, query)[:limit]
        
        # Cache the result IDs
        result_ids = [r.id for r in ranked_results]
        cache.set(cache_key, result_ids, 300)
        
        return ranked_results
    
    def _search_previews(self, query: str, user, limit: int) -> List[Resource]:
        """
        Search using value_preview field for fast initial results.
        This uses a smaller GIN index for better performance.
        """
        return Resource.objects.for_user(user).filter(
            resource_type=ResourceType.LITERAL,
            value_preview__isnull=False
        ).annotate(
            similarity=TrigramSimilarity('value_preview', query),
            match_type=Value('preview', output_field=models.CharField())
        ).filter(
            similarity__gt=self.preview_threshold
        ).order_by('-similarity')[:limit]
    
    def _search_full_content(self, query: str, user, limit: int, exclude_ids: set) -> List[Resource]:
        """
        Search full content for long literals where preview search wasn't sufficient.
        Only searches content that wasn't already found in preview search.
        """
        base_query = Resource.objects.for_user(user).filter(
            resource_type=ResourceType.LITERAL,
            has_long_content=True  # Only search long content
        ).exclude(id__in=exclude_ids)
        
        # Use different strategies based on query characteristics
        if len(query) <= 4:
            # Short query - use contains for exact matches
            matches = base_query.filter(
                value__icontains=query
            ).annotate(
                similarity=Value(0.8, output_field=models.FloatField()),  # Fixed high similarity
                match_type=Value('full_exact', output_field=models.CharField())
            )[:limit]
        else:
            # Longer query - use trigram similarity
            matches = base_query.annotate(
                similarity=TrigramSimilarity('value', query),
                match_type=Value('full_trigram', output_field=models.CharField())
            ).filter(
                similarity__gt=self.similarity_threshold
            ).order_by('-similarity')[:limit]
        
        return list(matches)
    
    def _rank_by_relevance(self, resources: List[Resource], query: str) -> List[Resource]:
        """
        Rank search results by relevance, considering multiple factors.
        """
        def relevance_score(resource):
            # Base similarity score
            score = getattr(resource, 'similarity', 0.0)
            
            # Boost for exact matches
            if resource.value and query.lower() in resource.value.lower():
                score += 0.1
            
            # Boost for matches in preview (usually more relevant)
            if getattr(resource, 'match_type', '') == 'preview':
                score += 0.05
            
            # Boost for shorter content (often more focused)
            if resource.content_length and resource.content_length < 1000:
                score += 0.02
            
            return score
        
        return sorted(resources, key=relevance_score, reverse=True)
    
    def get_search_snippet(self, resource: Resource, query: str, max_length: int = 300) -> str:
        """
        Extract the most relevant snippet from long content around search terms.
        Preserves context while highlighting the match.
        """
        if not resource.value:
            return resource.value_preview or ""
        
        # For short content, return as-is
        if len(resource.value) <= max_length:
            return resource.value
        
        # Find the best snippet location
        snippet_start = self._find_best_snippet_position(resource.value, query, max_length)
        snippet_end = min(len(resource.value), snippet_start + max_length)
        
        # Extract snippet
        snippet = resource.value[snippet_start:snippet_end]
        
        # Add ellipsis indicators
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(resource.value):
            snippet = snippet + "..."
        
        return snippet
    
    def _find_best_snippet_position(self, content: str, query: str, max_length: int) -> int:
        """
        Find the best position to extract a snippet that includes the search query.
        """
        content_lower = content.lower()
        query_lower = query.lower()
        
        # Try to find exact query match
        query_pos = content_lower.find(query_lower)
        
        if query_pos != -1:
            # Center the snippet around the query match
            snippet_start = max(0, query_pos - max_length // 3)
            return snippet_start
        
        # If no exact match, try to find individual words
        query_words = query_lower.split()
        best_position = 0
        best_score = 0
        
        # Use sliding window to find position with most query words
        window_size = max_length
        for i in range(0, len(content) - window_size + 1, window_size // 4):
            window = content_lower[i:i + window_size]
            score = sum(1 for word in query_words if word in window)
            
            if score > best_score:
                best_score = score
                best_position = i
        
        return best_position
    
    def highlight_search_terms(self, text: str, query: str) -> str:
        """
        Highlight search terms in text while preserving original formatting.
        """
        if not query or not text:
            return text
        
        # Create regex pattern for case-insensitive matching
        words = re.findall(r'\w+', query)
        if not words:
            return text
        
        # Build pattern that matches any of the query words
        pattern = '|'.join(re.escape(word) for word in words)
        
        def highlight_match(match):
            return f'<mark class="search-highlight">{match.group()}</mark>'
        
        # Apply highlighting
        highlighted = re.sub(
            f'({pattern})', 
            highlight_match, 
            text, 
            flags=re.IGNORECASE
        )
        
        return mark_safe(highlighted)
    
    def get_content_stats(self, user) -> Dict:
        """
        Get statistics about content lengths for optimization insights.
        """
        cache_key = f"content_stats:{user.organization.id if user.is_authenticated else 'anon'}"
        stats = cache.get(cache_key)
        
        if stats is None:
            from django.db.models import Avg, Max, Min, Count
            
            literal_stats = Resource.objects.for_user(user).filter(
                resource_type=ResourceType.LITERAL,
                content_length__gt=0
            ).aggregate(
                total_count=Count('id'),
                avg_length=Avg('content_length'),
                max_length=Max('content_length'),
                min_length=Min('content_length'),
                long_content_count=Count('id', filter=Q(has_long_content=True)),
                short_content_count=Count('id', filter=Q(has_long_content=False))
            )
            
            stats = {
                'total_literals': literal_stats['total_count'] or 0,
                'average_length': int(literal_stats['avg_length'] or 0),
                'max_length': literal_stats['max_length'] or 0,
                'min_length': literal_stats['min_length'] or 0,
                'long_content_percentage': (
                    (literal_stats['long_content_count'] or 0) / 
                    max(literal_stats['total_count'] or 1, 1) * 100
                ),
            }
            
            cache.set(cache_key, stats, 3600)  # Cache for 1 hour
        
        return stats


# Template tags for long content handling
from django import template

register = template.Library()

@register.filter
def search_snippet(resource, query, max_length=300):
    """Generate search snippet from resource content."""
    engine = LongContentSearchEngine()
    snippet = engine.get_search_snippet(resource, query, max_length)
    return engine.highlight_search_terms(snippet, query)

@register.filter
def content_preview(resource, max_words=50):
    """Generate preview of content, using preview field if available."""
    if resource.value_preview:
        from django.template.defaultfilters import truncatewords
        return truncatewords(resource.value_preview, max_words)
    elif resource.value:
        from django.template.defaultfilters import truncatewords
        return truncatewords(resource.value, max_words)
    return ""

@register.simple_tag
def content_length_class(resource):
    """Return CSS class based on content length."""
    if not resource.content_length:
        return "content-empty"
    elif resource.content_length < 100:
        return "content-short"
    elif resource.content_length < 1000:
        return "content-medium"
    else:
        return "content-long"

@register.inclusion_tag('catalog/partials/content_expander.html')
def expandable_content(resource, search_query=None):
    """Render expandable content widget for long literals."""
    return {
        'resource': resource,
        'search_query': search_query,
        'has_long_content': resource.content_length > 500,
        'preview_available': bool(resource.value_preview),
    }