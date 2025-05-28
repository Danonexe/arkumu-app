from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
import logging

from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.triples import Triple

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def triple_search(request):
    """Search triples with advanced filtering."""
    subject = request.GET.get('subject', '')
    predicate = request.GET.get('predicate', '')
    object_value = request.GET.get('object', '')
    institution = request.GET.get('institution', '')
    
    # Log the search parameters
    logger.info(f"Triple search request: subject='{subject}', predicate='{predicate}', object='{object_value}', institution='{institution}'")
    logger.info(f"Headers: HX-Request: {request.headers.get('HX-Request')}, HX-Trigger: {request.headers.get('HX-Trigger')}")
    
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    if subject:
        triples = triples.filter(Q(subject__uri__icontains=subject) | Q(subject__value__icontains=subject) | Q(subject__name__icontains=subject))
    if predicate:
        triples = triples.filter(Q(predicate__uri__icontains=predicate) | Q(predicate__value__icontains=predicate) | Q(predicate__name__icontains=predicate))
    if object_value:
        triples = triples.filter(Q(object__uri__icontains=object_value) | Q(object__value__icontains=object_value) | Q(object__name__icontains=object_value))
    if institution:
        triples = triples.filter(Q(subject__source=institution) | Q(object__source=institution))
    
    # Log the query count
    result_count = triples.count()
    logger.info(f"Triple search found {result_count} results")
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)
    
    # Check if HTMX request
    if request.headers.get('HX-Request'):
        logger.info(f"Rendering partial template for HTMX request (page {page})")
        return render(request, 'partials/triple_list.html', {
            'page_obj': page_obj,
            'is_paginated': paginator.num_pages > 1,
            'triples': triples,
        })
    
    logger.info("Rendering full triple search template")
    return render(request, 'triple_search.html', {
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'triples': triples,
        'institutions': Resource.objects.values_list('source', flat=True).distinct(),
    })

@login_required
def triple_list(request):
    """Display a paginated list of all triples in the system."""
    # Get filter parameters
    institution = request.GET.get('institution', '')
    page = request.GET.get('page', 1)
    
    # Base queryset
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    # Apply filters
    if institution:
        triples = triples.filter(Q(subject__source=institution) | Q(object__source=institution))
    
    # Get stats
    total_triples = Triple.objects.count()
    institutions = Resource.objects.values_list('source', flat=True).distinct()
    institution_count = institutions.count()
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 20)
    page_obj = paginator.get_page(page)
    
    return render(request, 'triple_list.html', {
        'page_obj': page_obj,
        'total_triples': total_triples,
        'institutions': institutions,
        'institution_count': institution_count,
        'institution': institution,
    }) 