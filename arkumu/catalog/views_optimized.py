"""
Optimized views for the catalog app using triple-based data model.
These views demonstrate performance best practices with Redis caching and HTMX.
"""

from django.views.generic import ListView, DetailView
from django.http import HttpResponse
from django.shortcuts import render
from django.core.cache import cache
from django.db.models import Prefetch, Count, Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

from arkumu.metadata.models import Resource, Triple, ResourceType
from arkumu.catalog.template_utils import ComponentRenderer, FacetBuilder


class OptimizedCatalogView(LoginRequiredMixin, ListView):
    """Main catalog view with faceted navigation and infinite scroll."""
    
    model = Resource
    template_name = 'catalog/optimized_catalog.html'
    context_object_name = 'resources'
    paginate_by = 20
    
    def get_queryset(self):
        """Build optimized queryset with prefetching."""
        # Start with base queryset
        qs = Resource.objects.for_user(self.request.user)
        
        # Filter by resource class if specified
        resource_class = self.request.GET.get('resource_class', 'all')
        if resource_class != 'all':
            qs = qs.filter(
                subject_triples__predicate__uri='rdf:type',
                subject_triples__object__uri=resource_class
            ).distinct()
        
        # Apply facet filters
        filters = self.request.GET.getlist('filter')
        for filter_str in filters:
            if ':' in filter_str:
                predicate_id, value_id = filter_str.split(':', 1)
                qs = qs.filter(
                    subject_triples__predicate_id=predicate_id,
                    subject_triples__object_id=value_id
                )
        
        # Apply search
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(subject_triples__object__value__icontains=query)
            ).distinct()
        
        # Apply sorting
        sort = self.request.GET.get('sort', 'relevance')
        if sort == 'date_desc':
            qs = qs.order_by('-created_at')
        elif sort == 'date_asc':
            qs = qs.order_by('created_at')
        elif sort == 'title':
            qs = qs.order_by('name')
        
        # Prefetch related data for performance
        qs = qs.prefetch_related(
            Prefetch(
                'subject_triples',
                queryset=Triple.objects.select_related('predicate', 'object')
            )
        )
        
        return qs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get facets for current resource class
        resource_class = self.request.GET.get('resource_class', 
                                             'http://arkumu.org/ontology#Project')
        facet_builder = FacetBuilder(self.request.user)
        context['facets'] = facet_builder.get_facets_for_class(resource_class)
        
        # Parse active filters for display
        context['active_filters'] = self._parse_active_filters()
        
        # Add organization context
        context['organization'] = self.request.user.organization
        
        return context
    
    def _parse_active_filters(self):
        """Parse filter parameters into display format."""
        filters = []
        for filter_str in self.request.GET.getlist('filter'):
            if ':' in filter_str:
                pred_id, val_id = filter_str.split(':', 1)
                # Look up names from cache or database
                cache_key = f"filter_label:{pred_id}:{val_id}"
                label = cache.get(cache_key)
                
                if not label:
                    try:
                        predicate = Resource.objects.get(id=pred_id)
                        value = Resource.objects.get(id=val_id)
                        label = f"{predicate.name}: {value.name or value.value}"
                        cache.set(cache_key, label, 3600)
                    except Resource.DoesNotExist:
                        continue
                
                filters.append({
                    'id': filter_str,
                    'label': label
                })
        
        return filters


class LoadMoreView(OptimizedCatalogView):
    """HTMX endpoint for infinite scroll."""
    
    def get(self, request, *args, **kwargs):
        """Return just the resource cards for the next page."""
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        
        # Render just the cards
        renderer = ComponentRenderer()
        cards_html = ''.join(
            renderer.render_resource_cards(context['page_obj'], request.user)
        )
        
        return HttpResponse(cards_html)


class SearchView(OptimizedCatalogView):
    """HTMX endpoint for search results."""
    
    def get(self, request, *args, **kwargs):
        """Return search results."""
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        
        # Cache search results
        query = request.GET.get('q', '')
        if query:
            cache_key = f"search:{query}:{request.user.organization.id}"
            cache.set(cache_key, list(context['page_obj'].object_list.values_list('id', flat=True)), 300)
        
        return render(request, 'catalog/partials/results_grid.html', context)


class LoadFacetsView(LoginRequiredMixin, ListView):
    """HTMX endpoint to dynamically load facets."""
    
    def get(self, request, *args, **kwargs):
        """Return updated facets based on current filters."""
        resource_class = request.GET.get('resource_class', 
                                       'http://arkumu.org/ontology#Project')
        
        # Get current queryset to calculate facet counts
        catalog_view = OptimizedCatalogView()
        catalog_view.request = request
        current_qs = catalog_view.get_queryset()
        
        # Build facets with counts
        facet_builder = FacetBuilder(request.user)
        facets = facet_builder.get_facets_for_class(resource_class)
        
        # Update counts based on current filters
        for facet in facets:
            facet['values'] = self._update_facet_counts(facet, current_qs)
        
        return render(request, 'catalog/partials/facets.html', {'facets': facets})
    
    def _update_facet_counts(self, facet, queryset):
        """Update facet value counts based on current queryset."""
        predicate_id = facet['id']
        
        # Get counts for this facet's values
        value_counts = queryset.filter(
            subject_triples__predicate_id=predicate_id
        ).values(
            'subject_triples__object_id'
        ).annotate(
            count=Count('id')
        ).values_list('subject_triples__object_id', 'count')
        
        count_dict = dict(value_counts)
        
        # Update values with new counts
        updated_values = []
        for value in facet['values']:
            value['count'] = count_dict.get(value['id'], 0)
            if value['count'] > 0:
                updated_values.append(value)
        
        return updated_values


class ResourceDetailView(LoginRequiredMixin, DetailView):
    """Optimized detail view for resources."""
    
    model = Resource
    template_name = 'catalog/resource_detail.html'
    
    def get_queryset(self):
        """Ensure user has permission to view."""
        return Resource.objects.for_user(self.request.user)
    
    @method_decorator(cache_page(300))  # 5 minute cache
    def get(self, request, *args, **kwargs):
        """Cache the rendered detail view."""
        return super().get(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all triples for this resource
        cache_key = f"resource_detail:{self.object.id}"
        triples_data = cache.get(cache_key)
        
        if triples_data is None:
            # As subject
            subject_triples = Triple.objects.filter(
                subject=self.object
            ).select_related('predicate', 'object').order_by('predicate__name')
            
            # As object (incoming links)
            object_triples = Triple.objects.filter(
                object=self.object
            ).select_related('subject', 'predicate').order_by('predicate__name')
            
            triples_data = {
                'outgoing': list(subject_triples),
                'incoming': list(object_triples)
            }
            
            cache.set(cache_key, triples_data, 600)
        
        context.update(triples_data)
        
        # Get related resources
        context['related'] = self._get_related_resources()
        
        return context
    
    def _get_related_resources(self):
        """Get resources related through shared properties."""
        # This is expensive, so cache aggressively
        cache_key = f"related:{self.object.id}"
        related = cache.get(cache_key)
        
        if related is None:
            # Find resources that share properties
            shared_objects = Triple.objects.filter(
                subject=self.object
            ).values_list('object_id', flat=True)
            
            related = Resource.objects.for_user(self.request.user).filter(
                subject_triples__object_id__in=shared_objects
            ).exclude(
                id=self.object.id
            ).distinct()[:10]
            
            cache.set(cache_key, list(related), 1800)  # 30 min cache
        
        return related


# Utility views for HTMX actions

def add_filter(request):
    """Add a filter and return updated results."""
    filter_value = request.GET.get('filter')
    if filter_value:
        # Add to existing filters
        filters = request.GET.getlist('filter')
        if filter_value not in filters:
            filters.append(filter_value)
        
        # Redirect to catalog with new filters
        from django.http import QueryDict
        query = QueryDict(mutable=True)
        query.setlist('filter', filters)
        
        # Preserve other parameters
        for key in ['q', 'sort', 'resource_class']:
            if key in request.GET:
                query[key] = request.GET[key]
        
        return HttpResponse(
            status=200,
            headers={
                'HX-Push-Url': f"{request.path}?{query.urlencode()}",
                'HX-Trigger': 'facets-updated'
            }
        )
    
    return HttpResponse(status=400)


def remove_filter(request, filter_id):
    """Remove a filter and return updated results."""
    filters = request.GET.getlist('filter')
    if filter_id in filters:
        filters.remove(filter_id)
    
    # Build new query
    from django.http import QueryDict
    query = QueryDict(mutable=True)
    if filters:
        query.setlist('filter', filters)
    
    # Preserve other parameters
    for key in ['q', 'sort', 'resource_class']:
        if key in request.GET:
            query[key] = request.GET[key]
    
    return HttpResponse(
        status=200,
        headers={
            'HX-Push-Url': f"{request.path}?{query.urlencode()}",
            'HX-Trigger': 'facets-updated'
        }
    )


def load_contributors(request):
    """Lazy load contributors for a resource card."""
    resource_id = request.GET.get('resource')
    if not resource_id:
        return HttpResponse(status=400)
    
    try:
        resource = Resource.objects.get(id=resource_id)
        
        # Get contributor triples
        contributors = Triple.objects.filter(
            subject=resource,
            predicate__name__in=['dc:contributor', 'arkumu:hasContributor']
        ).select_related('object')
        
        return render(request, 'catalog/partials/contributors.html', {
            'contributors': contributors
        })
    
    except Resource.DoesNotExist:
        return HttpResponse(status=404)