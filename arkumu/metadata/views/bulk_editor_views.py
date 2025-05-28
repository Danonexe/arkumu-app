from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import transaction
import logging

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def bulk_triple_editor(request):
    """Main view for the bulk triple editor interface."""
    return render(request, 'bulk_triple_editor.html')

@login_required
def query_relationships(request):
    """Handle HTMX requests for querying existing relationships."""
    subject = request.GET.get('query-subject', '').strip()
    predicate = request.GET.get('query-predicate', '').strip()
    object_value = request.GET.get('query-object', '').strip()
    page = request.GET.get('page', 1)
    
    # Start with all triples
    triples = Triple.objects.all().select_related('subject', 'predicate', 'object')
    
    query_performed = bool(subject or predicate or object_value)
    
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
    
    # Get total count before pagination
    total_count = triples.count()
    
    # Paginate
    paginator = Paginator(triples.order_by('-id'), 10)  # Smaller page size for query results
    page_obj = paginator.get_page(page)
    
    return render(request, 'partials/relationship_query_results.html', {
        'triples': page_obj.object_list,
        'page_obj': page_obj,
        'total_count': total_count,
        'query_performed': query_performed,
    })

@login_required 
def create_bulk_triples(request):
    """Handle the creation of multiple triples from the bulk editor."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    batch_triples = request.POST.get('batch-triples', '').strip()
    institution = request.POST.get('institution', 'DEFAULT').strip()
    base_uri = request.POST.get('base-uri', 'http://arkumu.org/data').strip()
    
    if not batch_triples:
        return render(request, 'partials/bulk_creation_results.html', {
            'error': 'No triples provided for creation'
        })
    
    # Parse triples
    lines = [line.strip() for line in batch_triples.split('\n') if line.strip()]
    parsed_triples = []
    errors = []
    
    for line_num, line in enumerate(lines, 1):
        parts = line.split('|')
        if len(parts) != 3:
            errors.append(f"Line {line_num}: Expected 3 parts (subject|predicate|object), got {len(parts)}")
            continue
        
        subject_str, predicate_str, object_str = [p.strip() for p in parts]
        if not all([subject_str, predicate_str, object_str]):
            errors.append(f"Line {line_num}: Empty components found")
            continue
        
        parsed_triples.append({
            'line_num': line_num,
            'subject': subject_str,
            'predicate': predicate_str,
            'object': object_str
        })
    
    if errors:
        return render(request, 'partials/bulk_creation_results.html', {
            'errors': errors,
            'total_lines': len(lines)
        })
    
    # Create the triples
    try:
        from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
        
        with transaction.atomic():
            created_resources = 0
            created_triples = 0
            skipped_triples = 0
            processing_errors = []
            
            # Common predicates mapping
            predicate_mappings = {
                'dc:name': 'http://purl.org/dc/terms/name',
                'dc:title': 'http://purl.org/dc/terms/title',
                'dc:creator': 'http://purl.org/dc/terms/creator',
                'dc:description': 'http://purl.org/dc/terms/description',
                'dcterms:hasPart': 'http://purl.org/dc/terms/hasPart',
                'dcterms:isPartOf': 'http://purl.org/dc/terms/isPartOf',
                'rdf:type': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type',
                'rdf:value': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#value',
                'rdfs:label': 'http://www.w3.org/2000/01/rdf-schema#label',
                'rdfs:comment': 'http://www.w3.org/2000/01/rdf-schema#comment',
            }
            
            # CIDOC predicates with full URIs
            cidoc_base = 'http://www.cidoc-crm.org/cidoc-crm/'
            for predicate in ['P14_carried_out_by', 'P11_had_participant', 'P2_has_type', 
                             'P1_is_identified_by', 'P4_has_time-span', 'P7_took_place_at']:
                predicate_mappings[f'cidoc:{predicate}'] = f'{cidoc_base}{predicate}'
                predicate_mappings[predicate] = f'{cidoc_base}{predicate}'
            
            for triple_data in parsed_triples:
                try:
                    line_num = triple_data['line_num']
                    
                    # Process subject
                    subject_str = triple_data['subject']
                    if subject_str.startswith('new:'):
                        # Create new resource
                        name = subject_str[4:]  # Remove 'new:' prefix
                        subject_uri = mint_uri(base_uri, institution, "entities", slugify_uri_part(name))
                        subject_resource, s_created = Resource.objects.get_or_create(
                            uri=subject_uri,
                            defaults={
                                'resource_type': ResourceType.IRI,
                                'name': name,
                                'source': institution
                            }
                        )
                        if s_created:
                            created_resources += 1
                    else:
                        # Find existing resource or create with provided URI
                        try:
                            subject_resource = Resource.objects.get(uri=subject_str)
                        except Resource.DoesNotExist:
                            # Assume it's a URI and create the resource
                            subject_resource, s_created = Resource.objects.get_or_create(
                                uri=subject_str,
                                defaults={
                                    'resource_type': ResourceType.IRI,
                                    'source': institution
                                }
                            )
                            if s_created:
                                created_resources += 1
                    
                    # Process predicate
                    predicate_str = triple_data['predicate']
                    if predicate_str.startswith('new:'):
                        # Create new property
                        name = predicate_str[4:]
                        predicate_uri = mint_uri(base_uri, institution, "properties", slugify_uri_part(name))
                        predicate_resource, p_created = Resource.objects.get_or_create(
                            uri=predicate_uri,
                            defaults={
                                'resource_type': ResourceType.PROPERTY,
                                'name': name,
                                'source': institution
                            }
                        )
                        if p_created:
                            created_resources += 1
                    else:
                        # Check mappings first
                        mapped_uri = predicate_mappings.get(predicate_str, predicate_str)
                        try:
                            predicate_resource = Resource.objects.get(uri=mapped_uri)
                        except Resource.DoesNotExist:
                            # Create with the URI (mapped or original)
                            predicate_resource, p_created = Resource.objects.get_or_create(
                                uri=mapped_uri,
                                defaults={
                                    'resource_type': ResourceType.PROPERTY,
                                    'name': predicate_str,
                                    'source': institution
                                }
                            )
                            if p_created:
                                created_resources += 1
                    
                    # Process object
                    object_str = triple_data['object']
                    if object_str.startswith('new:'):
                        # Create new resource
                        name = object_str[4:]
                        object_uri = mint_uri(base_uri, institution, "entities", slugify_uri_part(name))
                        object_resource, o_created = Resource.objects.get_or_create(
                            uri=object_uri,
                            defaults={
                                'resource_type': ResourceType.IRI,
                                'name': name,
                                'source': institution
                            }
                        )
                        if o_created:
                            created_resources += 1
                    elif object_str.startswith('http://') or object_str.startswith('https://'):
                        # Treat as URI
                        try:
                            object_resource = Resource.objects.get(uri=object_str)
                        except Resource.DoesNotExist:
                            object_resource, o_created = Resource.objects.get_or_create(
                                uri=object_str,
                                defaults={
                                    'resource_type': ResourceType.IRI,
                                    'source': institution
                                }
                            )
                            if o_created:
                                created_resources += 1
                    else:
                        # Treat as literal value
                        object_resource, o_created = Resource.objects.get_or_create(
                            resource_type=ResourceType.LITERAL,
                            value=object_str,
                            source=institution,
                            defaults={
                                'datatype': 'http://www.w3.org/2001/XMLSchema#string'
                            }
                        )
                        if o_created:
                            created_resources += 1
                    
                    # Create the triple
                    triple, t_created = Triple.objects.get_or_create(
                        subject=subject_resource,
                        predicate=predicate_resource,
                        object=object_resource
                    )
                    
                    if t_created:
                        created_triples += 1
                    else:
                        skipped_triples += 1
                        
                except Exception as e:
                    processing_errors.append(f"Line {line_num}: {str(e)}")
                    logger.error(f"Error processing line {line_num}: {e}", exc_info=True)
            
            return render(request, 'partials/bulk_creation_results.html', {
                'success': True,
                'created_resources': created_resources,
                'created_triples': created_triples,
                'skipped_triples': skipped_triples,
                'total_lines': len(parsed_triples),
                'processing_errors': processing_errors
            })
            
    except Exception as e:
        logger.error(f"Error in bulk triple creation: {e}", exc_info=True)
        return render(request, 'partials/bulk_creation_results.html', {
            'error': f'Database error: {str(e)}'
        }) 