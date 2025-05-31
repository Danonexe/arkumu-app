from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import transaction
import logging
import re

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

# Set up logger
logger = logging.getLogger(__name__)

@login_required
def bulk_triple_editor(request):
    """Main view for the bulk triple editor interface."""
    mapping_rules = request.session.get('mapping_rules', [])
    return render(request, 'bulk_triple_editor.html', {
        'mapping_rules': mapping_rules
    })

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

@login_required
def find_matching_resources(request):
    """HTMX endpoint for finding resources that match a pattern."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    pattern_type = request.POST.get('pattern_type', '').strip()
    pattern_value = request.POST.get('pattern_value', '').strip()
    search_source = request.POST.get('search_source', 'current_batch').strip()
    sample_uris = request.POST.get('sample_uris', '').strip()
    
    if not pattern_value:
        return render(request, 'partials/pattern_exploration_results.html', {
            'error': 'Pattern value is required'
        })
    
    matching_resources = []
    total_checked = 0
    
    try:
        if search_source == 'sample_uris' and sample_uris:
            # Test against provided sample URIs
            uri_list = [uri.strip() for uri in sample_uris.split('\n') if uri.strip()]
            total_checked = len(uri_list)
            
            for uri in uri_list:
                if _pattern_matches(pattern_type, pattern_value, uri):
                    matching_resources.append(uri)
        else:
            # Test against current batch triples (resources in database)
            resources = Resource.objects.all()[:1000]  # Limit to avoid performance issues
            total_checked = resources.count()
            
            for resource in resources:
                test_value = resource.uri or resource.value or resource.name or ''
                if _pattern_matches(pattern_type, pattern_value, test_value):
                    matching_resources.append({
                        'uri': resource.uri,
                        'name': resource.name,
                        'value': resource.value,
                        'type': resource.get_resource_type_display()
                    })
    
    except Exception as e:
        logger.error(f"Error in pattern matching: {e}", exc_info=True)
        return render(request, 'partials/pattern_exploration_results.html', {
            'error': f'Error during pattern matching: {str(e)}'
        })
    
    return render(request, 'partials/pattern_exploration_results.html', {
        'matching_resources': matching_resources,
        'total_checked': total_checked,
        'pattern_type': pattern_type,
        'pattern_value': pattern_value,
        'match_count': len(matching_resources)
    })

def _pattern_matches(pattern_type, pattern_value, test_string):
    """Helper function to test if a string matches a given pattern."""
    if not test_string:
        return False
        
    try:
        if pattern_type == 'prefix':
            return test_string.startswith(pattern_value)
        elif pattern_type == 'contains':
            return pattern_value.lower() in test_string.lower()
        elif pattern_type == 'regex':
            return bool(re.search(pattern_value, test_string))
        elif pattern_type == 'column':
            # For column/dataset matching, look for pattern in the string
            return pattern_value.lower() in test_string.lower()
        else:
            return False
    except re.error:
        # Invalid regex pattern
        return False

@login_required
def add_mapping_rule(request):
    """HTMX endpoint for adding a new type mapping rule."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    pattern_type = request.POST.get('rule_pattern_type', '').strip()
    pattern_value = request.POST.get('rule_pattern_value', '').strip()
    arkumu_type = request.POST.get('rule_arkumu_type', '').strip()
    
    if not all([pattern_type, pattern_value, arkumu_type]):
        return render(request, 'partials/mapping_rules_display.html', {
            'error': 'All fields are required for mapping rule'
        })
    
    # Get existing rules from session or initialize
    mapping_rules = request.session.get('mapping_rules', [])
    
    # Check for duplicate rules
    for rule in mapping_rules:
        if rule['pattern_type'] == pattern_type and rule['pattern_value'] == pattern_value:
            return render(request, 'partials/mapping_rules_display.html', {
                'error': f'Rule with pattern "{pattern_value}" already exists',
                'mapping_rules': mapping_rules
            })
    
    # Add new rule
    new_rule = {
        'pattern_type': pattern_type,
        'pattern_value': pattern_value,
        'arkumu_type': arkumu_type
    }
    mapping_rules.append(new_rule)
    
    # Save to session
    request.session['mapping_rules'] = mapping_rules
    request.session.modified = True
    
    return render(request, 'partials/mapping_rules_display.html', {
        'mapping_rules': mapping_rules,
        'success': f'Added mapping rule: {pattern_value} → {arkumu_type}'
    })

@login_required
def clear_mapping_rules(request):
    """HTMX endpoint for clearing all mapping rules."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # Clear rules from session
    request.session['mapping_rules'] = []
    request.session.modified = True
    
    return render(request, 'partials/mapping_rules_display.html', {
        'mapping_rules': [],
        'success': 'All mapping rules cleared'
    })

@login_required
def apply_mappings_to_batch(request):
    """HTMX endpoint for applying defined mappings to the batch."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    batch_triples = request.POST.get('batch-triples', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    
    if not batch_triples:
        return render(request, 'partials/batch_mapping_results.html', {
            'error': 'No batch triples found to apply mappings to'
        })
    
    if not mapping_rules:
        return render(request, 'partials/batch_mapping_results.html', {
            'error': 'No mapping rules defined. Please add mapping rules first.'
        })
    
    # Parse existing triples
    lines = [line.strip() for line in batch_triples.split('\n') if line.strip()]
    updated_triples = []
    added_type_triples = []
    
    for line in lines:
        updated_triples.append(line)  # Keep original triple
        
        # Extract subject from the line
        parts = line.split('|')
        if len(parts) >= 1:
            subject = parts[0].strip()
            
            # Check if subject matches any mapping rules
            for rule in mapping_rules:
                if _pattern_matches(rule['pattern_type'], rule['pattern_value'], subject):
                    # Add type triple
                    type_triple = f"{subject}|rdf:type|{rule['arkumu_type']}"
                    # Check if this exact triple is already in the batch
                    if type_triple not in updated_triples:
                        added_type_triples.append({
                            'subject': subject,
                            'predicate': 'rdf:type',
                            'object': rule['arkumu_type'],
                            'full_triple': type_triple
                        })
                        updated_triples.append(type_triple)
                    break  # Only apply first matching rule
    
    updated_batch = '\n'.join(updated_triples)
    
    return render(request, 'partials/batch_mapping_results.html', {
        'updated_batch': updated_batch,
        'added_count': len(added_type_triples),
        'added_triples': added_type_triples,
        'total_triples': len(updated_triples),
        'success': True
    }) 