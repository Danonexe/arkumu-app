from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
import logging
import re
from arkumu.users.mixins import general_login_required

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)

def _build_search_filter(field_name, search_term, search_mode='contains'):
    """
    Build a Q object for searching with different modes.
    
    Args:
        field_name: The field to search (e.g., 'uri', 'name', 'value')
        search_term: The term to search for
        search_mode: 'contains', 'startswith', 'exact', or 'regex'
    
    Returns:
        Q object for the search filter
    """
    if not search_term:
        return Q()
    
    if search_mode == 'contains':
        return Q(**{f"{field_name}__icontains": search_term})
    elif search_mode == 'startswith':
        return Q(**{f"{field_name}__istartswith": search_term})
    elif search_mode == 'exact':
        return Q(**{f"{field_name}__iexact": search_term})
    elif search_mode == 'regex':
        try:
            # Validate regex before using it
            re.compile(search_term)
            return Q(**{f"{field_name}__iregex": search_term})
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{search_term}': {e}")
            # Fall back to contains search if regex is invalid
            return Q(**{f"{field_name}__icontains": search_term})
    else:
        # Default to contains if unknown mode
        return Q(**{f"{field_name}__icontains": search_term})

def _build_multi_field_search(fields, search_term, search_mode='contains'):
    """
    Build a Q object that searches across multiple fields with OR logic.
    
    Args:
        fields: List of field names to search
        search_term: The term to search for
        search_mode: 'contains', 'startswith', 'exact', or 'regex'
    
    Returns:
        Q object combining all field searches with OR
    """
    if not search_term:
        return Q()
    
    q_objects = [_build_search_filter(field, search_term, search_mode) for field in fields]
    # Combine with OR
    combined_q = q_objects[0] if q_objects else Q()
    for q_obj in q_objects[1:]:
        combined_q |= q_obj
    
    return combined_q


@general_login_required
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
    search_mode = request.GET.get('search_mode', 'contains')
    page = request.GET.get('page', 1)
    
    logger.info(f"Resources view: type='{resource_type}', institution='{institution}', q='{search_query}', mode='{search_mode}', page={page}")
    
    # Base queryset
    resources = Resource.objects.all()
    
    # Apply filters
    if resource_type:
        resources = resources.filter(resource_type=resource_type)
    if institution:
        resources = resources.filter(source=institution)
    if search_query:
        search_filter = _build_multi_field_search(['uri', 'value', 'name'], search_query, search_mode)
        resources = resources.filter(search_filter)
    
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
        'current_search_mode': search_mode,
    }

def _handle_triples_view(request):
    """Handle the triples view mode."""
    subject = request.GET.get('subject', '')
    predicate = request.GET.get('predicate', '')
    object_value = request.GET.get('object', '')
    institution = request.GET.get('institution', '')
    search_mode = request.GET.get('search_mode', 'contains')
    page = request.GET.get('page', 1)
    
    logger.info(f"Triples view: subject='{subject}', predicate='{predicate}', object='{object_value}', institution='{institution}', mode='{search_mode}', page={page}")
    
    # Don't load any triples if no search criteria provided
    if not any([subject, predicate, object_value, institution]):
        return {
            'page_obj': None,
            'is_paginated': False,
            'triples': [],
            'current_search_mode': search_mode,
        }
    
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    # Apply filters
    if subject:
        subject_filter = _build_multi_field_search(['subject__uri', 'subject__value', 'subject__name'], subject, search_mode)
        triples = triples.filter(subject_filter)
    if predicate:
        predicate_filter = _build_multi_field_search(['predicate__uri', 'predicate__value', 'predicate__name'], predicate, search_mode)
        triples = triples.filter(predicate_filter)
    if object_value:
        object_filter = _build_multi_field_search(['object__uri', 'object__value', 'object__name'], object_value, search_mode)
        triples = triples.filter(object_filter)
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
        'current_search_mode': search_mode,
    }

def _handle_unified_view(request):
    """Handle the unified search view mode."""
    search_term = request.GET.get('search', '')
    institution = request.GET.get('institution', '')
    include_resources = request.GET.get('include_resources', '1') == '1'
    include_triples = request.GET.get('include_triples', '1') == '1'
    search_mode = request.GET.get('search_mode', 'contains')
    page = request.GET.get('page', 1)
    
    logger.info(f"Unified view: search='{search_term}', institution='{institution}', resources={include_resources}, triples={include_triples}, mode='{search_mode}', page={page}")
    
    resources = []
    triples = []
    search_performed = bool(search_term.strip())
    
    if search_performed:
        # Search resources
        if include_resources:
            resource_query = Resource.objects.all()
            if search_term:
                search_filter = _build_multi_field_search(['uri', 'value', 'name'], search_term, search_mode)
                resource_query = resource_query.filter(search_filter)
            if institution:
                resource_query = resource_query.filter(source=institution)
            
            resources = resource_query.order_by('-id')[:50]  # Limit to 50 for performance
        
        # Search triples
        if include_triples:
            triple_query = Triple.objects.all().select_related('subject', 'predicate', 'object')
            if search_term:
                search_filter = _build_multi_field_search([
                    'subject__uri', 'subject__value', 'subject__name',
                    'predicate__uri', 'predicate__value', 'predicate__name',
                    'object__uri', 'object__value', 'object__name'
                ], search_term, search_mode)
                triple_query = triple_query.filter(search_filter)
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
        'current_search_mode': search_mode,
    } 