from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
import logging

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)

@login_required
def data_explorer(request):
    """Unified data explorer for browsing resources and triples."""
    view_mode = request.GET.get('view', 'resources')
    
    # Common data needed for all views
    institutions = Resource.objects.values_list('source', flat=True).distinct().order_by('source')
    
    context = {
        'institutions': institutions,
        'resource_types': ResourceType.choices,
        'view_mode': view_mode,
    }
    
    # Handle different view modes
    if view_mode == 'resources':
        context.update(_handle_resources_view(request))
    elif view_mode == 'triples':
        context.update(_handle_triples_view(request))
    elif view_mode == 'unified':
        context.update(_handle_unified_view(request))
    
    # Return appropriate template based on request type
    if request.headers.get('HX-Request'):
        # Return partial content for HTMX requests
        if view_mode == 'resources':
            return render(request, 'partials/resource_list.html', context)
        elif view_mode == 'triples':
            return render(request, 'partials/triple_list.html', context)
        elif view_mode == 'unified':
            return render(request, 'partials/unified_results.html', context)
    
    return render(request, 'data_explorer.html', context)

def _handle_resources_view(request):
    """Handle the resources view mode."""
    # Get filter parameters
    resource_type = request.GET.get('resource_type', '')
    institution = request.GET.get('institution', '')
    search_query = request.GET.get('q', '')
    page = request.GET.get('page', 1)
    
    logger.info(f"Resources view: type='{resource_type}', institution='{institution}', q='{search_query}', page={page}")
    
    # Base queryset
    resources = Resource.objects.all()
    
    # Apply filters
    if resource_type:
        resources = resources.filter(resource_type=resource_type)
    if institution:
        resources = resources.filter(source=institution)
    if search_query:
        resources = resources.filter(
            Q(uri__icontains=search_query) | 
            Q(value__icontains=search_query) |
            Q(name__icontains=search_query)
        )
    
    # Get total count before pagination
    total_count = resources.count()
    
    # Paginate
    paginator = Paginator(resources.order_by('-id'), 20)
    page_obj = paginator.get_page(page)
    
    logger.info(f"Resources query returned {total_count} total results, showing page {page}")
    
    return {
        'page_obj': page_obj,
        'total_count': total_count,
        'current_type': resource_type,
        'current_institution': institution,
        'current_query': search_query,
    }

def _handle_triples_view(request):
    """Handle the triples view mode."""
    subject = request.GET.get('subject', '')
    predicate = request.GET.get('predicate', '')
    object_value = request.GET.get('object', '')
    institution = request.GET.get('institution', '')
    page = request.GET.get('page', 1)
    
    logger.info(f"Triples view: subject='{subject}', predicate='{predicate}', object='{object_value}', institution='{institution}', page={page}")
    
    # Don't load any triples if no search criteria provided
    if not any([subject, predicate, object_value, institution]):
        return {
            'page_obj': None,
            'is_paginated': False,
            'triples': [],
        }
    
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    # Apply filters
    if subject:
        triples = triples.filter(
            Q(subject__uri__icontains=subject) | 
            Q(subject__value__icontains=subject) | 
            Q(subject__name__icontains=subject)
        )
    if predicate:
        triples = triples.filter(
            Q(predicate__uri__icontains=predicate) | 
            Q(predicate__value__icontains=predicate) | 
            Q(predicate__name__icontains=predicate)
        )
    if object_value:
        triples = triples.filter(
            Q(object__uri__icontains=object_value) | 
            Q(object__value__icontains=object_value) | 
            Q(object__name__icontains=object_value)
        )
    if institution:
        triples = triples.filter(
            Q(subject__source=institution) | 
            Q(object__source=institution)
        )
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 20)
    page_obj = paginator.get_page(page)
    
    logger.info(f"Triples query returned {triples.count()} total results, showing page {page}")
    
    return {
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'triples': page_obj.object_list,
    }

def _handle_unified_view(request):
    """Handle the unified search view mode."""
    search_term = request.GET.get('search', '')
    institution = request.GET.get('institution', '')
    include_resources = request.GET.get('include_resources', '1') == '1'
    include_triples = request.GET.get('include_triples', '1') == '1'
    page = request.GET.get('page', 1)
    
    logger.info(f"Unified view: search='{search_term}', institution='{institution}', resources={include_resources}, triples={include_triples}, page={page}")
    
    resources = []
    triples = []
    search_performed = bool(search_term.strip())
    
    if search_performed:
        # Search resources
        if include_resources:
            resource_query = Resource.objects.all()
            if search_term:
                resource_query = resource_query.filter(
                    Q(uri__icontains=search_term) | 
                    Q(value__icontains=search_term) |
                    Q(name__icontains=search_term)
                )
            if institution:
                resource_query = resource_query.filter(source=institution)
            
            resources = resource_query.order_by('-id')[:50]  # Limit to 50 for performance
        
        # Search triples
        if include_triples:
            triple_query = Triple.objects.all().select_related('subject', 'predicate', 'object')
            if search_term:
                triple_query = triple_query.filter(
                    Q(subject__uri__icontains=search_term) | 
                    Q(subject__value__icontains=search_term) |
                    Q(subject__name__icontains=search_term) |
                    Q(predicate__uri__icontains=search_term) | 
                    Q(predicate__value__icontains=search_term) |
                    Q(predicate__name__icontains=search_term) |
                    Q(object__uri__icontains=search_term) | 
                    Q(object__value__icontains=search_term) |
                    Q(object__name__icontains=search_term)
                )
            if institution:
                triple_query = triple_query.filter(
                    Q(subject__source=institution) | 
                    Q(object__source=institution)
                )
            
            triples = triple_query.order_by('-id')[:50]  # Limit to 50 for performance
    
    logger.info(f"Unified search found {len(resources)} resources and {len(triples)} triples")
    
    return {
        'resources': resources,
        'triples': triples,
        'search_performed': search_performed,
        'search_term': search_term,
        'current_institution': institution,
        'include_resources': include_resources,
        'include_triples': include_triples,
    } 