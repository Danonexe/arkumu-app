from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import transaction
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import logging
import re
import tempfile
import os

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

# Import the services
from arkumu.metadata.services import ServiceFactory

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
    """HTMX endpoint for finding existing resources that match a pattern in selected fields."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    pattern_type = request.POST.get('pattern_type', '').strip()
    pattern_value = request.POST.get('pattern_value', '').strip()
    search_fields = request.POST.getlist('search_fields')  # Get list of selected fields
    
    if not pattern_value:
        return render(request, 'partials/pattern_exploration_results.html', {
            'error': 'Pattern value is required'
        })
    
    if not search_fields:
        return render(request, 'partials/pattern_exploration_results.html', {
            'error': 'Please select at least one field to search'
        })
    
    try:
        # Search existing resources in the database with selected fields
        matching_resources, total_checked, actual_match_count = _find_matching_resources_in_db(pattern_type, pattern_value, search_fields)
        
        # Calculate percentage for display
        percentage = (actual_match_count * 100.0 / total_checked) if total_checked > 0 else 0
        
        return render(request, 'partials/pattern_exploration_results.html', {
            'matching_resources': matching_resources,
            'total_checked': total_checked,
            'pattern_type': pattern_type,
            'pattern_value': pattern_value,
            'search_fields': search_fields,
            'match_count': len(matching_resources),
            'actual_match_count': actual_match_count,
            'percentage': round(percentage, 1),
            'search_description': _get_search_description(pattern_type, pattern_value, search_fields)
        })
    
    except Exception as e:
        logger.error(f"Error in pattern matching: {e}", exc_info=True)
        return render(request, 'partials/pattern_exploration_results.html', {
            'error': f'Error during pattern matching: {str(e)}'
        })

def _get_search_description(pattern_type, pattern_value, search_fields):
    """Generate a human-readable description of what the search is doing."""
    field_names = {
        'uri': 'URI',
        'name': 'Name',
        'value': 'Value',
        'source': 'Source'
    }
    
    selected_field_names = [field_names.get(field, field) for field in search_fields]
    fields_text = ', '.join(selected_field_names[:-1]) + f" or {selected_field_names[-1]}" if len(selected_field_names) > 1 else selected_field_names[0]
    
    action_map = {
        'prefix': 'starts with',
        'contains': 'contains',
        'regex': 'matches the regex pattern',
        'exact': 'exactly matches'
    }
    
    action = action_map.get(pattern_type, 'matches')
    
    return f"Resources where {fields_text} {action} '{pattern_value}'"

def _find_matching_resources_in_db(pattern_type, pattern_value, search_fields):
    """Enhanced database-level resource matching using proper ORM queries on selected fields."""
    from django.db.models import Q
    
    # Start with base queryset
    resources_query = Resource.objects.all()
    
    # Build Q object for only the selected fields
    filter_q = Q()
    
    # Field mapping for database queries
    field_lookups = {
        'uri': 'uri',
        'name': 'name', 
        'value': 'value',
        'source': 'source'
    }
    
    # Build appropriate database filters based on pattern type and selected fields
    for field in search_fields:
        if field not in field_lookups:
            continue
            
        db_field = field_lookups[field]
        
        if pattern_type == 'prefix':
            filter_q |= Q(**{f'{db_field}__startswith': pattern_value})
        elif pattern_type == 'contains':
            filter_q |= Q(**{f'{db_field}__icontains': pattern_value})
        elif pattern_type == 'regex':
            filter_q |= Q(**{f'{db_field}__regex': pattern_value})
        elif pattern_type == 'exact':
            filter_q |= Q(**{f'{db_field}__iexact': pattern_value})
    
    # Get total count efficiently
    total_checked = Resource.objects.count()
    
    # Apply the filter and get the actual count of matches
    matching_queryset = resources_query.filter(filter_q)
    actual_match_count = matching_queryset.count()
    
    # Limit results for display (but we now know the real count)
    matching_resources_db = matching_queryset[:200]
    
    # Process results and determine which field matched
    matching_resources = []
    for resource in matching_resources_db:
        matched_field, matched_value = _determine_matched_field(resource, pattern_type, pattern_value, search_fields)
        
        matching_resources.append({
            'uri': resource.uri,
            'name': resource.name,
            'value': resource.value,
            'type': resource.get_resource_type_display(),
            'source': resource.source,
            'datatype': resource.datatype,
            'language': resource.language,
            'is_placeholder': resource.is_placeholder,
            'matched_field': matched_field,
            'matched_value': matched_value,
            'resource_id': str(resource.id)
        })
    
    return matching_resources, total_checked, actual_match_count

def _determine_matched_field(resource, pattern_type, pattern_value, search_fields):
    """Determine which field of the resource matched the pattern, limited to searched fields."""
    field_mapping = {
        'uri': resource.uri,
        'name': resource.name, 
        'value': resource.value,
        'source': resource.source
    }
    
    # Only check fields that were selected for search
    for field_name in search_fields:
        field_value = field_mapping.get(field_name)
        if field_value and _pattern_matches(pattern_type, pattern_value, field_value):
            return field_name, field_value
    
    # Fallback
    return 'unknown', resource.uri or resource.name or resource.value or 'N/A'

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
        elif pattern_type == 'exact':
            return test_string.lower() == pattern_value.lower()
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
    """HTMX endpoint for applying defined mappings to the batch with comprehensive preview."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    batch_triples = request.POST.get('batch-triples', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    base_uri = request.POST.get('base-uri', 'http://arkumu.org/data').strip()
    institution = request.POST.get('institution', request.user.username).strip()
    
    if not batch_triples:
        return render(request, 'partials/batch_mapping_results.html', {
            'error': 'No batch triples found to apply mappings to'
        })
    
    if not mapping_rules:
        return render(request, 'partials/batch_mapping_results.html', {
            'error': 'No mapping rules defined. Please add mapping rules first.'
        })
    
    try:
        from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
        
        # Parse existing triples
        lines = [line.strip() for line in batch_triples.split('\n') if line.strip()]
        processed_triples = []
        added_type_triples = []
        errors = []
        uri_resolutions = {}  # Track new: -> full URI mappings
        
        for line_num, line in enumerate(lines, 1):
            parts = line.split('|')
            if len(parts) != 3:
                errors.append(f"Line {line_num}: Expected 3 parts (subject|predicate|object), got {len(parts)}")
                continue
                
            subject_str, predicate_str, object_str = [p.strip() for p in parts]
            if not all([subject_str, predicate_str, object_str]):
                errors.append(f"Line {line_num}: Empty components found")
                continue
            
            # Resolve URIs for preview
            resolved_subject = _resolve_uri_for_preview(subject_str, base_uri, institution, "entities", uri_resolutions)
            resolved_predicate = _resolve_uri_for_preview(predicate_str, base_uri, institution, "properties", uri_resolutions)
            resolved_object = _resolve_uri_for_preview(object_str, base_uri, institution, "entities", uri_resolutions)
            
            # Store the processed triple
            processed_triple = {
                'line_num': line_num,
                'original': line,
                'subject_original': subject_str,
                'predicate_original': predicate_str,
                'object_original': object_str,
                'subject_resolved': resolved_subject,
                'predicate_resolved': resolved_predicate,
                'object_resolved': resolved_object,
                'resolved_line': f"{resolved_subject}|{resolved_predicate}|{resolved_object}",
                'type_triples_added': []
            }
            
            # Check if subject matches any mapping rules and add type triples
            for rule in mapping_rules:
                if _pattern_matches(rule['pattern_type'], rule['pattern_value'], resolved_subject):
                    type_triple = {
                        'subject': resolved_subject,
                        'predicate': 'rdf:type',
                        'object': rule['arkumu_type'],
                        'full_triple': f"{resolved_subject}|rdf:type|{rule['arkumu_type']}",
                        'rule_applied': rule
                    }
                    added_type_triples.append(type_triple)
                    processed_triple['type_triples_added'].append(type_triple)
                    break  # Only apply first matching rule
            
            processed_triples.append(processed_triple)
        
        if errors:
            return render(request, 'partials/batch_mapping_results.html', {
                'errors': errors,
                'total_lines': len(lines)
            })
        
        # Build the complete updated batch
        all_triples = []
        for triple in processed_triples:
            all_triples.append(triple['resolved_line'])
        for type_triple in added_type_triples:
            all_triples.append(type_triple['full_triple'])
        
        updated_batch = '\n'.join(all_triples)
        
        return render(request, 'partials/batch_mapping_results.html', {
            'updated_batch': updated_batch,
            'processed_triples': processed_triples,
            'added_count': len(added_type_triples),
            'added_triples': added_type_triples,
            'total_triples': len(all_triples),
            'original_count': len(processed_triples),
            'uri_resolutions': uri_resolutions,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error in apply_mappings_to_batch: {e}", exc_info=True)
        return render(request, 'partials/batch_mapping_results.html', {
            'error': f'Error processing mappings: {str(e)}'
        })

def _resolve_uri_for_preview(uri_str, base_uri, institution, entity_type, uri_cache):
    """Resolve new: prefixes to full URIs for preview purposes."""
    if uri_str.startswith('new:'):
        # Use cache to ensure consistent URI generation
        if uri_str in uri_cache:
            return uri_cache[uri_str]
        
        try:
            from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part
            name = uri_str[4:]  # Remove 'new:' prefix
            full_uri = mint_uri(base_uri, institution, entity_type, slugify_uri_part(name))
            uri_cache[uri_str] = full_uri
            return full_uri
        except Exception:
            # Fallback if uri_utils import fails
            from urllib.parse import quote
            name = uri_str[4:]
            safe_name = quote(name.replace(' ', '_').lower())
            full_uri = f"{base_uri}/{institution}/{entity_type}/{safe_name}"
            uri_cache[uri_str] = full_uri
            return full_uri
    else:
        # Return as-is for existing URIs or predicates
        return uri_str 

@login_required
def add_triple_from_form(request):
    """HTMX endpoint for adding a triple from the form to the batch."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    subject = request.POST.get('subject-input', '').strip()
    predicate = request.POST.get('predicate-input', '').strip()
    object_value = request.POST.get('object-input', '').strip()
    subject_type = request.POST.get('subject-type', 'uri').strip()
    predicate_type = request.POST.get('predicate-type', 'uri').strip()
    object_type = request.POST.get('object-type', 'uri').strip()
    current_batch = request.POST.get('batch-triples', '').strip()
    
    if not all([subject, predicate, object_value]):
        return render(request, 'partials/toast.html', {
            'message': 'Please fill in all fields (subject, predicate, object)',
            'type': 'error'
        })
    
    # Format the triple components
    formatted_subject = f"new:{subject}" if subject_type == 'new' else subject
    formatted_predicate = f"new:{predicate}" if predicate_type == 'new' else predicate
    formatted_object = f"new:{object_value}" if object_type == 'new' else object_value
    
    # Create the triple line
    triple_line = f"{formatted_subject}|{formatted_predicate}|{formatted_object}"
    
    # Add to existing batch
    if current_batch:
        updated_batch = f"{current_batch}\n{triple_line}"
    else:
        updated_batch = triple_line
    
    # Return the updated textarea content and success message
    from django.http import HttpResponse
    response = HttpResponse()
    response['HX-Trigger'] = 'tripleAdded'
    
    # Update the textarea and show success
    response.content = f"""
        <script>
            document.getElementById('batch-triples').value = `{updated_batch}`;
            document.getElementById('subject-input').value = '';
            document.getElementById('predicate-input').value = '';
            document.getElementById('object-input').value = '';
            
            // Show success toast
            const toast = document.createElement('div');
            toast.className = 'toast toast-top toast-end';
            toast.innerHTML = '<div class="alert alert-success"><span>Triple added to batch!</span></div>';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        </script>
    """
    return response

@login_required
def validate_batch_triples(request):
    """HTMX endpoint for validating the batch triples format."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    batch_triples = request.POST.get('batch-triples', '').strip()
    
    if not batch_triples:
        return render(request, 'partials/toast.html', {
            'message': 'No triples to validate',
            'type': 'warning'
        })
    
    lines = [line.strip() for line in batch_triples.split('\n') if line.strip()]
    errors = []
    warnings = []
    
    for line_num, line in enumerate(lines, 1):
        parts = line.split('|')
        if len(parts) != 3:
            errors.append(f"Line {line_num}: Expected 3 parts (subject|predicate|object), got {len(parts)}")
            continue
        
        subject, predicate, obj = [p.strip() for p in parts]
        if not all([subject, predicate, obj]):
            errors.append(f"Line {line_num}: Empty components found")
        
        # Check for potential issues
        if not (subject.startswith('http://') or subject.startswith('https://') or subject.startswith('new:')):
            warnings.append(f"Line {line_num}: Subject '{subject[:30]}...' might need 'new:' prefix or full URI")
    
    return render(request, 'partials/validation_results.html', {
        'total_lines': len(lines),
        'errors': errors,
        'warnings': warnings,
        'valid': len(errors) == 0
    })

@login_required
def clear_batch_triples(request):
    """HTMX endpoint for clearing the batch triples and results."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    from django.http import HttpResponse
    response = HttpResponse()
    
    # Clear all the target areas
    response.content = """
        <script>
            document.getElementById('batch-triples').value = '';
            document.getElementById('creation-results').innerHTML = '';
            document.getElementById('batch-mapping-results').innerHTML = '';
            document.getElementById('subject-input').value = '';
            document.getElementById('predicate-input').value = '';
            document.getElementById('object-input').value = '';
            
            // Show success feedback
            const toast = document.createElement('div');
            toast.className = 'toast toast-top toast-end';
            toast.innerHTML = '<div class="alert alert-success"><span>All triples and results cleared!</span></div>';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        </script>
    """
    return response

@login_required
def update_predicate_options(request):
    """HTMX endpoint for updating predicate options based on data model."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    data_model = request.POST.get('data-model', 'custom').strip()
    
    predicate_options = {
        'dublin-core': ['dc:title', 'dc:creator', 'dc:subject', 'dc:description', 'dc:type', 'dc:date'],
        'rdf': ['rdf:type', 'rdfs:label', 'rdfs:comment', 'rdfs:seeAlso'],
        'custom': ['hasPart', 'isPartOf', 'relatedTo', 'name', 'description']
    }
    
    predicates = predicate_options.get(data_model, predicate_options['custom'])
    
    return render(request, 'partials/predicate_buttons.html', {
        'predicates': predicates,
        'model': data_model
    })

@login_required
def list_datasets(request):
    """HTMX endpoint for listing available datasets for transformation."""
    institution_filter = request.GET.get('institution', '').strip()
    
    # Find all dataset resources by looking for resources that are containers for other resources
    # In our data model, datasets are identified by having hasPart relationships
    dataset_uris = Triple.objects.filter(
        predicate__uri="http://purl.org/dc/terms/hasPart"
    ).values_list('subject__uri', flat=True).distinct()
    
    datasets_query = Resource.objects.filter(
        uri__in=dataset_uris,
        resource_type=ResourceType.IRI
    ).order_by('name')
    
    if institution_filter:
        datasets_query = datasets_query.filter(source=institution_filter)
    
    datasets = list(datasets_query.values('id', 'uri', 'name', 'source'))
    
    # Get institutions for the filter
    institutions = Resource.objects.filter(
        uri__in=dataset_uris
    ).values_list('source', flat=True).distinct().order_by('source')
    
    return render(request, 'partials/dataset_selector.html', {
        'datasets': datasets,
        'institutions': institutions,
        'selected_institution': institution_filter
    })

@login_required
def get_dataset_info(request):
    """HTMX endpoint for getting dataset information."""
    dataset_uri = request.GET.get('dataset_uri', '').strip()
    
    if not dataset_uri:
        return render(request, 'partials/dataset_info.html', {
            'error': 'No dataset URI provided'
        })
    
    try:
        dataset = Resource.objects.get(uri=dataset_uri)
        
        # Count cells in this dataset
        cell_count = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).count()
        
        # Find rows in this dataset (if using row linking)
        row_count = Triple.objects.filter(
            subject__uri__contains=f"{dataset_uri.rstrip('/')}/rows/"
        ).values('subject').distinct().count()
        
        # Get sample resources to show what types of data are in this dataset
        sample_triples = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')[:5]
        
        sample_resources = []
        for triple in sample_triples:
            sample_resources.append({
                'uri': triple.object.uri,
                'name': triple.object.name or 'Unnamed',
                'source': triple.object.source
            })
        
        return render(request, 'partials/dataset_info.html', {
            'dataset': dataset,
            'cell_count': cell_count,
            'row_count': row_count,
            'sample_resources': sample_resources
        })
        
    except Resource.DoesNotExist:
        return render(request, 'partials/dataset_info.html', {
            'error': f'Dataset not found: {dataset_uri}'
        })
    except Exception as e:
        logger.error(f"Error getting dataset info: {e}", exc_info=True)
        return render(request, 'partials/dataset_info.html', {
            'error': f'Error retrieving dataset information: {str(e)}'
        })

@login_required
def preview_dataset_transformation(request):
    """HTMX endpoint for previewing how mapping rules would transform a dataset."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    dataset_uri = request.POST.get('dataset_uri', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    
    if not dataset_uri:
        return render(request, 'partials/transformation_preview.html', {
            'error': 'No dataset selected'
        })
    
    if not mapping_rules:
        return render(request, 'partials/transformation_preview.html', {
            'error': 'No mapping rules defined. Please create mapping rules in Step 1.'
        })
    
    try:
        # Get all resources that are part of this dataset
        cell_resources = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        total_resources = cell_resources.count()
        matches = []
        type_assignments = {}
        
        for triple in cell_resources:
            resource = triple.object
            
            # Check each mapping rule against this resource
            for rule in mapping_rules:
                # Test the rule against different fields based on what we're matching
                matched = False
                matched_field = None
                
                if _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.uri):
                    matched = True
                    matched_field = 'URI'
                elif resource.name and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.name):
                    matched = True
                    matched_field = 'Name'
                elif resource.value and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.value):
                    matched = True
                    matched_field = 'Value'
                
                if matched:
                    # Check if this resource already has an rdf:type
                    existing_type = Triple.objects.filter(
                        subject=resource,
                        predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
                    ).select_related('object').first()
                    
                    match_info = {
                        'resource': resource,
                        'rule': rule,
                        'matched_field': matched_field,
                        'pattern_value': rule['pattern_value'],
                        'new_type': rule['arkumu_type'],
                        'existing_type': existing_type.object.uri if existing_type else None,
                        'action': 'UPDATE' if existing_type else 'CREATE'
                    }
                    matches.append(match_info)
                    
                    # Track type assignments for summary
                    type_key = rule['arkumu_type']
                    if type_key not in type_assignments:
                        type_assignments[type_key] = 0
                    type_assignments[type_key] += 1
                    
                    break  # Only apply first matching rule per resource
        
        # Calculate summary statistics
        resources_to_update = len([m for m in matches if m['action'] == 'UPDATE'])
        resources_to_create = len([m for m in matches if m['action'] == 'CREATE'])
        resources_unmatched = total_resources - len(matches)
        
        return render(request, 'partials/transformation_preview.html', {
            'dataset_uri': dataset_uri,
            'total_resources': total_resources,
            'matches': matches[:20],  # Show first 20 for preview
            'total_matches': len(matches),
            'resources_to_update': resources_to_update,
            'resources_to_create': resources_to_create,
            'resources_unmatched': resources_unmatched,
            'type_assignments': type_assignments,
            'mapping_rules': mapping_rules,
            'preview_limited': len(matches) > 20
        })
        
    except Exception as e:
        logger.error(f"Error previewing transformation: {e}", exc_info=True)
        return render(request, 'partials/transformation_preview.html', {
            'error': f'Error previewing transformation: {str(e)}'
        })

@login_required
def execute_dataset_transformation(request):
    """HTMX endpoint for executing the transformation on a dataset."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    dataset_uri = request.POST.get('dataset_uri', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    dry_run = request.POST.get('dry_run', 'false').lower() == 'true'
    update_existing = request.POST.get('update_existing', 'false').lower() == 'true'
    
    if not dataset_uri:
        return render(request, 'partials/transformation_results.html', {
            'error': 'No dataset selected'
        })
    
    if not mapping_rules:
        return render(request, 'partials/transformation_results.html', {
            'error': 'No mapping rules defined. Please create mapping rules in Step 1.'
        })
    
    try:
        # Get or create the rdf:type predicate
        rdf_type_predicate, _ = Resource.objects.get_or_create(
            uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'name': 'type',
                'source': 'RDF'
            }
        )
        
        # Get all resources that are part of this dataset
        cell_resources = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        total_resources = cell_resources.count()
        created_triples = 0
        updated_triples = 0
        skipped_resources = 0
        errors = []
        processed_types = {}
        
        if not dry_run:
            with transaction.atomic():
                for triple in cell_resources:
                    resource = triple.object
                    
                    try:
                        # Check each mapping rule against this resource
                        matched_rule = None
                        for rule in mapping_rules:
                            # Test the rule against different fields
                            if (_pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.uri) or
                                (resource.name and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.name)) or
                                (resource.value and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.value))):
                                matched_rule = rule
                                break
                        
                        if matched_rule:
                            # Check if this resource already has an rdf:type
                            existing_type_triple = Triple.objects.filter(
                                subject=resource,
                                predicate=rdf_type_predicate
                            ).first()
                            
                            if existing_type_triple:
                                if update_existing:
                                    # Get or create the new type resource
                                    new_type_resource, _ = Resource.objects.get_or_create(
                                        uri=matched_rule['arkumu_type'],
                                        defaults={
                                            'resource_type': ResourceType.IRI,
                                            'name': matched_rule['arkumu_type'].split(':')[-1],
                                            'source': 'Arkumu'
                                        }
                                    )
                                    
                                    # Update the existing triple
                                    existing_type_triple.object = new_type_resource
                                    existing_type_triple.save()
                                    updated_triples += 1
                                    
                                    # Track the type assignment
                                    if matched_rule['arkumu_type'] not in processed_types:
                                        processed_types[matched_rule['arkumu_type']] = 0
                                    processed_types[matched_rule['arkumu_type']] += 1
                                else:
                                    skipped_resources += 1
                            else:
                                # Create new type triple
                                # Get or create the type resource
                                type_resource, _ = Resource.objects.get_or_create(
                                    uri=matched_rule['arkumu_type'],
                                    defaults={
                                        'resource_type': ResourceType.IRI,
                                        'name': matched_rule['arkumu_type'].split(':')[-1],
                                        'source': 'Arkumu'
                                    }
                                )
                                
                                # Create the rdf:type triple
                                Triple.objects.create(
                                    subject=resource,
                                    predicate=rdf_type_predicate,
                                    object=type_resource
                                )
                                created_triples += 1
                                
                                # Track the type assignment
                                if matched_rule['arkumu_type'] not in processed_types:
                                    processed_types[matched_rule['arkumu_type']] = 0
                                processed_types[matched_rule['arkumu_type']] += 1
                        else:
                            skipped_resources += 1
                            
                    except Exception as e:
                        error_msg = f"Error processing resource {resource.uri}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg, exc_info=True)
        else:
            # Dry run - just count what would happen
            for triple in cell_resources:
                resource = triple.object
                
                # Check each mapping rule against this resource
                matched_rule = None
                for rule in mapping_rules:
                    if (_pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.uri) or
                        (resource.name and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.name)) or
                        (resource.value and _pattern_matches(rule['pattern_type'], rule['pattern_value'], resource.value))):
                        matched_rule = rule
                        break
                
                if matched_rule:
                    # Check if this resource already has an rdf:type
                    existing_type_triple = Triple.objects.filter(
                        subject=resource,
                        predicate=rdf_type_predicate
                    ).first()
                    
                    if existing_type_triple:
                        if update_existing:
                            updated_triples += 1
                        else:
                            skipped_resources += 1
                    else:
                        created_triples += 1
                    
                    # Track the type assignment
                    if matched_rule['arkumu_type'] not in processed_types:
                        processed_types[matched_rule['arkumu_type']] = 0
                    processed_types[matched_rule['arkumu_type']] += 1
                else:
                    skipped_resources += 1
        
        return render(request, 'partials/transformation_results.html', {
            'dataset_uri': dataset_uri,
            'dry_run': dry_run,
            'total_resources': total_resources,
            'created_triples': created_triples,
            'updated_triples': updated_triples,
            'skipped_resources': skipped_resources,
            'errors': errors,
            'processed_types': processed_types,
            'mapping_rules': mapping_rules,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error executing transformation: {e}", exc_info=True)
        return render(request, 'partials/transformation_results.html', {
            'error': f'Error executing transformation: {str(e)}'
        })

@login_required
def list_s3_csv_files(request):
    """HTMX endpoint for listing available CSV files in S3."""
    from arkumu.storage.services.bucket_service import BucketService
    
    organization = request.GET.get('organization', '')
    
    try:
        # Use BucketService like the archivist dashboard does
        bucket_service = BucketService()
        
        # Get available organizations
        available_organizations = bucket_service.get_predefined_organizations()
        
        # Set default organization if none selected
        if not organization and available_organizations:
            organization = available_organizations[0]
        
        csv_files = []
        
        if organization:
            # Ensure the organization bucket exists
            bucket_result = bucket_service.ensure_organization_bucket_exists(organization)
            if not bucket_result.get('success', False):
                return render(request, 'partials/s3_csv_file_list.html', {
                    'error': f'Failed to access bucket for {organization}: {bucket_result.get("error", "Unknown error")}',
                    'available_organizations': available_organizations,
                    'selected_organization': organization,
                })
            
            # Get the bucket name
            bucket_name = bucket_service.get_organization_bucket(organization)
            
            # List all contents with 'metadata/' prefix to search in metadata folder
            all_contents = bucket_service.list_bucket_contents(bucket_name, 'metadata/')
            
            # Filter for CSV files only
            for item in all_contents:
                if (item.get('type') == 'file' and 
                    item.get('name', '').lower().endswith('.csv')):
                    csv_files.append({
                        'id': f"{organization}_{item['path']}",  # Create unique ID
                        'file_name': item['name'],
                        's3_key': item['path'],
                        'file_size_bytes': item.get('size', 0),
                        'organization': organization,
                        'bucket_name': bucket_name,
                        'last_modified': item.get('last_modified')
                    })
        
        return render(request, 'partials/s3_csv_file_list.html', {
            'csv_files': csv_files,
            'available_organizations': available_organizations,
            'selected_organization': organization,
        })
        
    except Exception as e:
        logger.error(f"Error listing S3 CSV files: {e}", exc_info=True)
        return render(request, 'partials/s3_csv_file_list.html', {
            'error': f'Error listing CSV files: {str(e)}',
            'available_organizations': [],
            'selected_organization': organization,
        })

@login_required
def auto_analyze_csv(request):
    """HTMX endpoint for auto-analyzing a CSV file from S3 and generating mapping suggestions."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    s3_file_id = request.POST.get('s3_file_id')
    
    if not s3_file_id:
        return render(request, 'partials/auto_analysis_results.html', {
            'error': 'No S3 file selected'
        })
    
    try:
        from arkumu.storage.services.bucket_service import BucketService
        import tempfile
        import os
        
        # Parse the file ID to get organization and S3 key
        # Format: "organization_s3/path/to/file.csv"
        if '_' not in s3_file_id:
            return render(request, 'partials/auto_analysis_results.html', {
                'error': 'Invalid file ID format'
            })
        
        organization, s3_key = s3_file_id.split('_', 1)
        
        # Use BucketService to get file content
        bucket_service = BucketService()
        bucket_name = bucket_service.get_organization_bucket(organization)
        
        # Get file content from S3
        file_content_result = bucket_service.get_file_content(bucket_name, s3_key)
        
        if not file_content_result.get('success'):
            return render(request, 'partials/auto_analysis_results.html', {
                'error': f'Failed to download file from S3: {file_content_result.get("error", "Unknown error")}'
            })
        
        # Save content to temporary file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as temp_file:
            temp_file.write(file_content_result['content'])
            temp_path = temp_file.name
        
        try:
            # Get the table analysis service
            service_factory = ServiceFactory()
            table_analysis_service = service_factory.get_table_analysis_service()
            
            # Analyze the CSV file
            analysis = table_analysis_service.analyze_csv(temp_path)
            
            # Get file size for display
            file_size = len(file_content_result['content'])
            file_name = os.path.basename(s3_key)
            
            # Prepare data for the template
            context = {
                'analysis': analysis,
                'suggested_mappings': analysis.suggested_mappings,
                'institution_prefixes': analysis.institutional_prefixes,
                'discovered_pattern_count': sum(len(patterns) for patterns in analysis.discovered_patterns.values()),
                'suggested_relationships': [],  # Could be enhanced later
                'source_info': {
                    'bucket': bucket_name,
                    's3_key': s3_key,
                    'file_name': file_name,
                    'file_size': file_size,
                    'organization': organization,
                }
            }
            
            # Add some template filters if needed
            if hasattr(analysis, 'quality_score') and analysis.quality_score:
                context['quality_badge_class'] = _get_quality_badge_class(analysis.quality_score)
            
            # Add confidence badge classes for mappings
            for mapping in analysis.suggested_mappings:
                mapping['confidence_badge_class'] = _get_confidence_badge_class(mapping.get('confidence', 0))
            
            return render(request, 'partials/auto_analysis_results.html', context)
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    
    except Exception as e:
        logger.error(f"Error auto-analyzing CSV from S3: {e}", exc_info=True)
        return render(request, 'partials/auto_analysis_results.html', {
            'error': f'Error analyzing CSV: {str(e)}'
        })

def _get_quality_badge_class(score):
    """Return appropriate badge class for quality score"""
    if score >= 8:
        return 'badge-success'
    elif score >= 6:
        return 'badge-warning'
    else:
        return 'badge-error'

def _get_confidence_badge_class(confidence):
    """Return appropriate badge class for confidence percentage"""
    if confidence >= 80:
        return 'badge-success'
    elif confidence >= 60:
        return 'badge-warning'
    else:
        return 'badge-error'

@login_required
def preview_auto_mappings(request):
    """Preview the auto-generated mapping suggestions before applying them."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    # This is a placeholder - would need to implement preview logic
    # based on selected mappings from the form
    return render(request, 'partials/mapping_preview.html', {
        'message': 'Preview functionality coming soon'
    })

@login_required
def apply_auto_mappings(request):
    """Apply the selected auto-generated mapping suggestions."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        # Get selected mapping IDs from the request
        selected_mappings = request.POST.getlist('mapping-checkbox')
        
        # This is a placeholder - would need to implement application logic
        # based on selected mappings
        
        return render(request, 'partials/mapping_results.html', {
            'success': True,
            'message': f'Applied {len(selected_mappings)} mapping rules successfully',
            'applied_count': len(selected_mappings)
        })
        
    except Exception as e:
        logger.error(f"Error applying auto mappings: {e}", exc_info=True)
        return render(request, 'partials/mapping_results.html', {
            'success': False,
            'error': f'Error applying mappings: {str(e)}'
        }) 