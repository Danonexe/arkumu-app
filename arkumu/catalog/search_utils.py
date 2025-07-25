"""
Optimized search utilities leveraging the GIN trigram index on Resource.value
"""

from django.db.models import Q, F, Value
from django.contrib.postgres.search import TrigramSimilarity, TrigramDistance
from django.core.cache import cache
from typing import List, Dict, Optional

from arkumu.metadata.models import Resource, Triple, ResourceType


class HybridSearchEngine:
    """
    Intelligent search engine that combines GIN trigram index with B-tree prefix search.
    Automatically chooses the optimal strategy based on query characteristics.
    """
    
    def __init__(self, similarity_threshold: float = 0.3):
        self.similarity_threshold = similarity_threshold
    
    def search_resources(self, query: str, user, limit: int = 100) -> List[Resource]:
        """
        Intelligent search that chooses optimal strategy based on query characteristics.
        Uses B-tree index for prefix searches, GIN trigram for fuzzy searches.
        """
        if not query or len(query) < 2:
            return []
        
        query = query.strip()
        
        # Cache key for search results
        strategy = self._determine_strategy(query)
        cache_key = f"search:{strategy}:{query}:{user.organization.id if user.is_authenticated else 'anon'}"
        cached_ids = cache.get(cache_key)
        
        if cached_ids is not None:
            return list(Resource.objects.filter(id__in=cached_ids))
        
        # Choose search strategy based on query characteristics
        if strategy == 'prefix':
            matches = self._prefix_search(query, user, limit)
        else:
            matches = self._trigram_search(query, user, limit)
        
        # Cache the result IDs
        result_ids = [r.id for r in matches]
        cache.set(cache_key, result_ids, 300)  # 5 minute cache
        
        return matches
    
    def _determine_strategy(self, query: str) -> str:
        """Determine optimal search strategy based on query characteristics."""
        # Short single words: use prefix search (B-tree index)
        if len(query) <= 4 and ' ' not in query and query.isalnum():
            return 'prefix'
        
        # Long queries or multiple words: use trigram search (GIN index)
        return 'trigram'
    
    def _prefix_search(self, query: str, user, limit: int) -> List[Resource]:
        """Fast prefix search using B-tree index (requires additional index)."""
        # This would use a B-tree varchar_pattern_ops index if available
        # For now, using trigram as fallback until you add the B-tree index
        return Resource.objects.for_user(user).filter(
            resource_type=ResourceType.LITERAL,
            value__istartswith=query  # Will be fast with varchar_pattern_ops index
        ).order_by('value')[:limit]
    
    def _trigram_search(self, query: str, user, limit: int) -> List[Resource]:
        """Fuzzy search using GIN trigram index."""
        # Search in literal values using GIN index
        literal_matches = Resource.objects.for_user(user).filter(
            resource_type=ResourceType.LITERAL
        ).annotate(
            similarity=TrigramSimilarity('value', query)
        ).filter(
            similarity__gt=self.similarity_threshold
        ).order_by('-similarity')[:limit]
        
        # Also search in resource names and URIs
        name_matches = Resource.objects.for_user(user).exclude(
            resource_type=ResourceType.LITERAL
        ).annotate(
            similarity=TrigramSimilarity('name', query)
        ).filter(
            similarity__gt=self.similarity_threshold
        ).order_by('-similarity')[:limit//2]  # Limit name matches
        
        # Combine results
        all_matches = list(literal_matches) + list(name_matches)
        
        # Sort by similarity and deduplicate
        seen = set()
        unique_matches = []
        for match in sorted(all_matches, key=lambda x: x.similarity, reverse=True):
            if match.id not in seen:
                seen.add(match.id)
                unique_matches.append(match)
        
        return unique_matches[:limit]
    
    def search_with_context(self, query: str, user, expand_triples: bool = True) -> Dict:
        """
        Search and return resources with their triple context.
        This provides richer results for display.
        """
        # Get matching resources
        resources = self.search_resources(query, user)
        
        if not expand_triples:
            return {
                'results': resources,
                'count': len(resources)
            }
        
        # Expand to find resources that use these literals
        resource_ids = [r.id for r in resources if r.resource_type == ResourceType.LITERAL]
        
        if resource_ids:
            # Find subjects that have these literals as objects
            subjects = Resource.objects.for_user(user).filter(
                subject_triples__object_id__in=resource_ids
            ).distinct().prefetch_related(
                'subject_triples__predicate',
                'subject_triples__object'
            )[:50]
            
            return {
                'literal_matches': resources,
                'resource_matches': list(subjects),
                'count': len(resources) + len(subjects)
            }
        
        return {
            'results': resources,
            'count': len(resources)
        }
    
    def suggest_completions(self, prefix: str, user, limit: int = 10) -> List[str]:
        """
        Optimized autocomplete that uses the best index for the prefix length.
        """
        if not prefix or len(prefix) < 2:
            return []
        
        # For short prefixes, use starts-with (B-tree index when available)
        if len(prefix) <= 4:
            suggestions = Resource.objects.for_user(user).filter(
                resource_type=ResourceType.LITERAL,
                value__istartswith=prefix  # Uses B-tree varchar_pattern_ops index
            ).values_list('value', flat=True).distinct()[:limit]
        else:
            # For longer prefixes, combine both approaches
            # Exact prefix matches first
            prefix_suggestions = Resource.objects.for_user(user).filter(
                resource_type=ResourceType.LITERAL,
                value__istartswith=prefix
            ).values_list('value', flat=True)[:limit//2]
            
            # Similar matches using GIN trigram index
            trigram_suggestions = Resource.objects.for_user(user).filter(
                resource_type=ResourceType.LITERAL
            ).annotate(
                similarity=TrigramSimilarity('value', prefix)
            ).filter(
                similarity__gt=0.4  # Higher threshold for autocomplete
            ).values_list('value', flat=True)[:limit//2]
            
            # Combine and deduplicate while preserving order
            suggestions = list(dict.fromkeys(list(prefix_suggestions) + list(trigram_suggestions)))
        
        return list(suggestions)[:limit]
    
    def similar_values(self, value: str, user, limit: int = 10) -> List[Resource]:
        """
        Find similar literal values using trigram distance.
        Useful for data quality checks and deduplication.
        """
        return Resource.objects.for_user(user).filter(
            resource_type=ResourceType.LITERAL
        ).annotate(
            distance=TrigramDistance('value', value)
        ).filter(
            distance__lt=0.7  # Distance threshold
        ).order_by('distance')[:limit]


class FacetedSearch:
    """
    Combine trigram search with faceted filtering.
    """
    
    def __init__(self):
        self.search_engine = TrigramSearchEngine()
    
    def search_with_facets(self, query: str, filters: Dict, user) -> Dict:
        """
        Perform search with facet filters applied.
        """
        # Start with search results if query provided
        if query:
            base_results = self.search_engine.search_with_context(query, user)
            if 'resource_matches' in base_results:
                queryset = Resource.objects.filter(
                    id__in=[r.id for r in base_results['resource_matches']]
                )
            else:
                queryset = Resource.objects.filter(
                    id__in=[r.id for r in base_results['results']]
                )
        else:
            # No search query, start with all accessible resources
            queryset = Resource.objects.for_user(user)
        
        # Apply facet filters
        for predicate_uri, values in filters.items():
            queryset = queryset.filter(
                subject_triples__predicate__uri=predicate_uri,
                subject_triples__object__id__in=values
            ).distinct()
        
        # Get results with prefetching
        results = queryset.prefetch_related(
            'subject_triples__predicate',
            'subject_triples__object'
        )[:100]
        
        return {
            'results': list(results),
            'count': queryset.count(),
            'query': query,
            'filters': filters
        }


# Optimized search view functions

def htmx_search_view(request):
    """
    HTMX endpoint for instant search using GIN index.
    """
    from django.http import JsonResponse
    from django.template.loader import render_to_string
    
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'html': '', 'count': 0})
    
    engine = TrigramSearchEngine()
    results = engine.search_with_context(query, request.user, expand_triples=True)
    
    # Render results
    html = render_to_string('catalog/partials/search_results.html', {
        'results': results.get('resource_matches', results.get('results', [])),
        'query': query,
        'count': results['count']
    })
    
    return JsonResponse({
        'html': html,
        'count': results['count']
    })


def autocomplete_view(request):
    """
    Fast autocomplete endpoint using GIN index.
    """
    from django.http import JsonResponse
    
    prefix = request.GET.get('q', '').strip()
    if len(prefix) < 2:
        return JsonResponse({'suggestions': []})
    
    engine = TrigramSearchEngine()
    suggestions = engine.suggest_completions(prefix, request.user)
    
    return JsonResponse({
        'suggestions': suggestions
    })