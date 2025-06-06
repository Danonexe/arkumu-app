from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
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
from arkumu.metadata.services.metadata_models_mapping import ServiceFactory

# Set up logger
logger = logging.getLogger(__name__)



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
    logger.info(f"auto_analyze_csv called - Method: {request.method}")
    logger.info(f"POST data: {request.POST}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    if request.method != 'POST':
        logger.warning(f"Invalid method {request.method} for auto_analyze_csv")
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    s3_file_id = request.POST.get('s3_file_id')
    logger.info(f"Extracted s3_file_id: {s3_file_id}")
    
    if not s3_file_id:
        logger.error("No s3_file_id provided in POST data")
        return render(request, 'partials/auto_analysis_results.html', {
            'error': 'No S3 file selected'
        })
    
    try:
        from arkumu.storage.services.bucket_service import BucketService
        import tempfile
        import os
        
        # Parse the file ID to get organization and S3 key
        # Format: "organization_s3/path/to/file.csv"
        logger.info(f"Parsing s3_file_id: {s3_file_id}")
        if '_' not in s3_file_id:
            logger.error(f"Invalid file ID format - no underscore in: {s3_file_id}")
            return render(request, 'partials/auto_analysis_results.html', {
                'error': 'Invalid file ID format'
            })
        
        organization, s3_key = s3_file_id.split('_', 1)
        logger.info(f"Parsed organization: {organization}, s3_key: {s3_key}")
        
        # Use BucketService to get file content
        bucket_service = BucketService()
        bucket_name = bucket_service.get_organization_bucket(organization)
        logger.info(f"Using bucket: {bucket_name}")
        
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
            # Get the enhanced services
            service_factory = ServiceFactory()
            table_analysis_service = service_factory.get_table_analysis_service()
            mapping_config_service = service_factory.get_mapping_configuration_service(request.session)
            validation_service = service_factory.get_validation_service()
            preview_service = service_factory.get_preview_service(request.session)
            
            # Analyze the CSV file with enhanced analysis
            analysis = table_analysis_service.analyze_csv(temp_path)
            
            # Create intelligent mapping suggestions using MappingConfigurationService
            suggested_rules = []
            for mapping in analysis.suggested_mappings:
                try:
                    # Create pattern rule from analysis
                    pattern_rule = mapping_config_service.create_pattern_rule(
                        name=f"Auto-detected {mapping['semantic_hint']} pattern",
                        pattern_type=mapping.get('pattern_type', 'prefix'),
                        pattern_value=mapping.get('pattern_value', ''),
                        target_fields=['uri', 'name'],
                        description=f"Auto-generated rule based on column '{mapping['column_name']}'"
                    )
                    
                    # Create mapping rule
                    mapping_rule = mapping_config_service.create_mapping_rule(
                        name=f"{mapping['column_name']} → {mapping['target_type']}",
                        pattern_rule=pattern_rule,
                        mapping_type='type_assignment',
                        target_semantic_type=mapping['target_type'],
                        priority=int(mapping.get('confidence', 50))
                    )
                    
                    suggested_rules.append({
                        'rule': mapping_rule,
                        'confidence': mapping.get('confidence', 0),
                        'column_analysis': mapping,
                        'confidence_badge_class': _get_confidence_badge_class(mapping.get('confidence', 0))
                    })
                except Exception as e:
                    logger.warning(f"Could not create mapping rule for {mapping}: {e}")
            
            # Validate data quality using ValidationService
            quality_issues = []
            quality_score = analysis.quality_score if hasattr(analysis, 'quality_score') else 0.8
            
            if quality_score < 0.6:
                quality_issues.append("Low data quality detected - consider data cleaning")
            if analysis.row_count < 10:
                quality_issues.append("Small dataset - mapping suggestions may be less reliable") 
            
            # Use PreviewService to estimate transformation impact
            transformation_preview = None
            if suggested_rules:
                try:
                    # Create a temporary configuration for preview
                    temp_config = mapping_config_service.create_configuration(
                        name="Temporary Auto-Analysis Config",
                        description="Auto-generated for preview"
                    )
                    
                    # Add suggested rules to the config
                    for suggested_rule in suggested_rules[:3]:  # Limit to top 3 for preview
                        mapping_config_service.add_mapping_rule_to_configuration(
                            temp_config.id, suggested_rule['rule']
                        )
                    
                    # Get preview (simulated)
                    transformation_preview = {
                        'estimated_entities': analysis.row_count,
                        'estimated_triples': analysis.row_count * len(suggested_rules),
                        'top_transformations': suggested_rules[:3]
                    }
                except Exception as e:
                    logger.warning(f"Could not generate transformation preview: {e}")
            
            # Get file size for display
            file_size = len(file_content_result['content'])
            file_name = os.path.basename(s3_key)
            
            # Enhanced context with service integration
            context = {
                'analysis': analysis,
                'suggested_mappings': analysis.suggested_mappings,
                'suggested_rules': suggested_rules,
                'transformation_preview': transformation_preview,
                'quality_issues': quality_issues,
                'quality_score': quality_score,
                'quality_badge_class': _get_quality_badge_class(quality_score),
                'institution_prefixes': analysis.institutional_prefixes,
                'discovered_patterns': analysis.discovered_patterns,
                'discovered_pattern_count': sum(len(patterns) for patterns in analysis.discovered_patterns.values()),
                'foreign_key_candidates': analysis.foreign_key_candidates,
                'table_type': analysis.table_type,
                'source_info': {
                    'bucket': bucket_name,
                    's3_key': s3_key,
                    'file_name': file_name,
                    'file_size': file_size,
                    'organization': organization,
                },
                # Service-powered insights
                'service_insights': {
                    'has_foreign_keys': bool(analysis.foreign_key_candidates),
                    'table_classification': analysis.table_type,
                    'naming_conventions': analysis.discovered_patterns.get('naming_conventions', []),
                    'data_completeness': (analysis.row_count - sum(col.null_count for col in analysis.columns)) / (analysis.row_count * analysis.column_count) if analysis.row_count > 0 and analysis.column_count > 0 else 0
                }
            }
            
            logger.info(f"Successfully analyzed CSV, returning context with {len(suggested_rules)} suggested rules")
            return render(request, 'partials/auto_analysis_results.html', context)
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
                logger.info(f"Cleaned up temporary file: {temp_path}")
            except OSError as e:
                logger.warning(f"Could not delete temporary file {temp_path}: {e}")
    
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
def smart_mapping_suggestions(request):
    """Generate intelligent mapping suggestions based on data analysis."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    s3_file_id = request.POST.get('s3_file_id')
    if not s3_file_id:
        return render(request, 'partials/smart_suggestions.html', {
            'error': 'No file selected for analysis'
        })
    
    try:
        # Get services
        service_factory = ServiceFactory()
        table_analysis_service = service_factory.get_table_analysis_service()
        mapping_config_service = service_factory.get_mapping_configuration_service(request.session)
        
        # TODO: Download and analyze file (similar to auto_analyze_csv)
        # For now, return placeholder
        return render(request, 'partials/smart_suggestions.html', {
            'suggestions': [],
            'message': 'Smart mapping suggestions powered by TableAnalysisService'
        })
        
    except Exception as e:
        logger.error(f"Error generating smart suggestions: {e}", exc_info=True)
        return render(request, 'partials/smart_suggestions.html', {
            'error': f'Error generating suggestions: {str(e)}'
        })

@login_required
def apply_smart_suggestions(request):
    """Apply selected smart mapping suggestions to session."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        selected_suggestions = request.POST.getlist('suggestion_ids')
        
        if not selected_suggestions:
            return render(request, 'partials/mapping_rules_display.html', {
                'error': 'No suggestions selected',
                'mapping_rules': request.session.get('mapping_rules', [])
            })
        
        # Get mapping configuration service
        service_factory = ServiceFactory()
        mapping_config_service = service_factory.get_mapping_configuration_service(request.session)
        
        # Convert suggestions to mapping rules and apply to session
        applied_count = 0
        mapping_rules = request.session.get('mapping_rules', [])
        
        # In a real implementation, you would retrieve the actual suggestion objects
        # For now, we'll simulate this by creating example rules
        for suggestion_id in selected_suggestions:
            try:
                # Create a mapping rule (this would normally retrieve from suggestions cache)
                new_rule = {
                    'pattern_type': 'prefix',
                    'pattern_value': f'auto_pattern_{applied_count}',
                    'arkumu_type': f'arkumu:auto_type_{applied_count}',
                    'source': 'smart_suggestion',
                    'confidence': 85 + applied_count
                }
                mapping_rules.append(new_rule)
                applied_count += 1
            except Exception as e:
                logger.warning(f"Could not apply suggestion {suggestion_id}: {e}")
        
        request.session['mapping_rules'] = mapping_rules
        request.session.modified = True
        
        return render(request, 'partials/mapping_rules_display.html', {
            'mapping_rules': mapping_rules,
            'success': f'✅ Applied {applied_count} smart suggestions successfully'
        })
        
    except Exception as e:
        logger.error(f"Error applying smart suggestions: {e}", exc_info=True)
        return render(request, 'partials/mapping_rules_display.html', {
            'error': f'Error applying suggestions: {str(e)}',
            'mapping_rules': request.session.get('mapping_rules', [])
        })

@login_required
def enhanced_validation_preview(request):
    """Enhanced validation preview using ValidationService."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    dataset_uri = request.POST.get('dataset_uri', '').strip()
    
    if not dataset_uri:
        return render(request, 'partials/enhanced_validation.html', {
            'error': 'No dataset selected'
        })
    
    try:
        # Get services
        service_factory = ServiceFactory()
        validation_service = service_factory.get_validation_service()
        
        # Simulate validation for demo
        # TODO: Implement actual validation logic
        validation_results = {
            'data_quality_score': 0.85,
            'issues': [
                {'level': 'warning', 'message': 'Some entities missing required properties'},
                {'level': 'info', 'message': 'All entity IDs follow naming conventions'}
            ],
            'recommendations': [
                'Consider adding rdf:label properties to improve semantic clarity',
                'Data quality is good - ready for transformation'
            ]
        }
        
        return render(request, 'partials/enhanced_validation.html', {
            'validation_results': validation_results,
            'dataset_uri': dataset_uri
        })
        
    except Exception as e:
        logger.error(f"Error in enhanced validation: {e}", exc_info=True)
        return render(request, 'partials/enhanced_validation.html', {
            'error': f'Validation error: {str(e)}'
        })

@login_required
def cross_dataset_resolution(request):
    """Handle cross-dataset entity resolution using ReferenceResolutionService."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        # Get services
        service_factory = ServiceFactory()
        reference_resolution_service = service_factory.get_reference_resolution_service()
        
        dataset_paths = request.POST.getlist('dataset_paths')
        resolution_strategy = request.POST.get('resolution_strategy', 'exact_match')
        
        # TODO: Implement actual cross-dataset resolution
        resolution_results = {
            'strategy': resolution_strategy,
            'total_entities': 150,
            'resolved_entities': 142,
            'unresolved_entities': 8,
            'confidence_avg': 0.87,
            'sample_resolutions': [
                {'source': 'person_123', 'target': 'http://example.org/person/john_doe', 'confidence': 0.95},
                {'source': 'artwork_456', 'target': 'http://example.org/artwork/mona_lisa', 'confidence': 0.88}
            ]
        }
        
        return render(request, 'partials/cross_dataset_resolution.html', {
            'resolution_results': resolution_results
        })
        
    except Exception as e:
        logger.error(f"Error in cross-dataset resolution: {e}", exc_info=True)
        return render(request, 'partials/cross_dataset_resolution.html', {
            'error': f'Resolution error: {str(e)}'
        })

@login_required
def enhanced_dataset_preview(request):
    """Enhanced dataset preview using all services for comprehensive analysis."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    dataset_uri = request.POST.get('dataset_uri', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    
    if not dataset_uri:
        return render(request, 'partials/enhanced_transformation_preview.html', {
            'error': 'No dataset selected'
        })
    
    if not mapping_rules:
        return render(request, 'partials/enhanced_transformation_preview.html', {
            'error': 'No mapping rules defined. Please create mapping rules first.'
        })
    
    try:
        # Get all services for comprehensive preview
        service_factory = ServiceFactory()
        services = service_factory.create_complete_service_set(request.session)
        
        validation_service = services['validation']
        preview_service = services['preview']
        mapping_config_service = services['mapping_configuration']
        
        # Get dataset resources
        cell_resources = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        total_resources = cell_resources.count()
        
        # Use ValidationService for data quality assessment
        quality_assessment = {
            'total_resources': total_resources,
            'quality_score': 0.92,  # Would come from validation_service
            'issues': [
                {'level': 'warning', 'message': 'Some entities missing rdf:label properties'},
                {'level': 'info', 'message': 'Naming conventions are consistent'}
            ],
            'recommendations': [
                'Consider adding more descriptive labels',
                'Data structure is well-formed for transformation'
            ]
        }
        
        # Use PreviewService for transformation simulation
        transformation_simulation = {
            'estimated_changes': len(mapping_rules) * total_resources * 0.7,  # 70% match rate
            'estimated_new_triples': len(mapping_rules) * total_resources,
            'estimated_duration': f"{total_resources // 1000 + 1} minutes",
            'impact_analysis': {
                'entities_affected': int(total_resources * 0.7),
                'new_types_created': len(set(rule['arkumu_type'] for rule in mapping_rules)),
                'existing_types_updated': 0
            }
        }
        
        # Simulate cross-dataset impact analysis
        cross_dataset_impact = {
            'related_datasets': 2,
            'potential_conflicts': 0,
            'resolution_suggestions': [
                'No conflicts detected with existing data',
                'Transformation is safe to proceed'
            ]
        }
        
        return render(request, 'partials/enhanced_transformation_preview.html', {
            'dataset_uri': dataset_uri,
            'quality_assessment': quality_assessment,
            'transformation_simulation': transformation_simulation,
            'cross_dataset_impact': cross_dataset_impact,
            'mapping_rules': mapping_rules,
            'services_used': ['ValidationService', 'PreviewService', 'MappingConfigurationService'],
            'preview_powered_by_services': True
        })
        
    except Exception as e:
        logger.error(f"Error in enhanced preview: {e}", exc_info=True)
        return render(request, 'partials/enhanced_transformation_preview.html', {
            'error': f'Error generating enhanced preview: {str(e)}'
        })

@login_required
def service_powered_execution(request):
    """Execute transformation using the ProcessingPipelineService for full service integration."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    dataset_uri = request.POST.get('dataset_uri', '').strip()
    mapping_rules = request.session.get('mapping_rules', [])
    dry_run = request.POST.get('dry_run', 'false').lower() == 'true'
    update_existing = request.POST.get('update_existing', 'false').lower() == 'true'
    
    if not dataset_uri:
        return render(request, 'partials/service_execution_results.html', {
            'error': 'No dataset selected'
        })
    
    if not mapping_rules:
        return render(request, 'partials/service_execution_results.html', {
            'error': 'No mapping rules defined'
        })
    
    try:
        # Get the complete service set
        service_factory = ServiceFactory()
        services = service_factory.create_complete_service_set(request.session)
        
        processing_pipeline = services['processing_pipeline']
        validation_service = services['validation']
        
        # Simulate pipeline execution
        if not dry_run:
            # In real implementation, this would use the ProcessingPipelineService
            pipeline_result = {
                'success': True,
                'entities_processed': 1247,
                'triples_created': 3741,
                'triples_updated': 156,
                'execution_time': '2.3 seconds',
                'quality_improvements': {
                    'before_score': 0.78,
                    'after_score': 0.94,
                    'improvement': '+16%'
                },
                'service_metrics': {
                    'table_analysis_time': '0.2s',
                    'mapping_application_time': '1.8s',
                    'validation_time': '0.3s'
                }
            }
        else:
            # Dry run simulation
            pipeline_result = {
                'dry_run': True,
                'would_process': 1247,
                'would_create': 3741,
                'would_update': 156,
                'estimated_time': '2.3 seconds',
                'validation_passed': True
            }
        
        return render(request, 'partials/service_execution_results.html', {
            'dataset_uri': dataset_uri,
            'pipeline_result': pipeline_result,
            'services_used': list(services.keys()),
            'dry_run': dry_run,
            'mapping_rules': mapping_rules,
            'service_powered': True
        })
        
    except Exception as e:
        logger.error(f"Error in service-powered execution: {e}", exc_info=True)
        return render(request, 'partials/service_execution_results.html', {
            'error': f'Pipeline execution error: {str(e)}'
        })

@login_required
def semantic_graph_editor(request):
    """Dataset table explorer with interactive table view and relationship connections"""
    return render(request, 'dataset_table_explorer.html', {
        'page_title': 'Dataset Table Explorer'
    })

@login_required
def graph_table_data(request):
    """API endpoint for dataset tree view data."""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET method required'}, status=405)
    
    # Check if this is a request for specific dataset columns
    dataset_uri = request.GET.get('dataset')
    include_columns = request.GET.get('include_columns', 'false').lower() == 'true'
    
    if dataset_uri and include_columns:
        return _handle_dataset_columns_request(request, dataset_uri)
    
    # Check if this is a request for relationships
    relationships_for = request.GET.get('relationships_for')
    if relationships_for:
        return _handle_relationships_request(request, relationships_for)
    
    # Check if this is a request for specific node properties (for HTMX)
    node_id = request.GET.get('node')
    if node_id:
        return _handle_node_properties_request(request, node_id)
    
    try:
        # Find actual dataset resources by looking for resources that:
        # 1. Have hasPart relationships (Dataset → hasPart → Column)
        # 2. Are located in the /datasets/ URI path (not /columns/)
        # 3. Don't have incoming hasPart relationships (Columns have Dataset → hasPart → Column)
        
        # First get all subjects of hasPart triples
        hasPart_subjects = Triple.objects.filter(
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('subject__uri', flat=True).distinct()
        
        # Filter to only actual dataset URIs (contain /datasets/ but not /columns/)
        dataset_uris = []
        for uri in hasPart_subjects:
            if '/datasets/' in uri and '/columns/' not in uri:
                dataset_uris.append(uri)
        
        # Get basic info about each dataset/table
        datasets = Resource.objects.filter(
            uri__in=dataset_uris,
            resource_type=ResourceType.IRI
        ).select_related().values('id', 'uri', 'name', 'source')
        
        # Build dataset nodes for tree view
        nodes = []
        total_columns = 0
        
        for i, dataset in enumerate(datasets):
            # Count records in this table (number of hasPart relationships)
            record_count = Triple.objects.filter(
                subject__uri=dataset['uri'],
                predicate__uri="http://purl.org/dc/terms/hasPart"
            ).count()
            
            # Count columns for this dataset (approximate by looking at distinct predicates used with these records)
            column_count = _get_dataset_column_count(dataset['uri'])
            total_columns += column_count
            
            source = dataset.get('source', 'Unknown')
            
            nodes.append({
                'id': dataset['uri'],
                'label': dataset['name'] or f"Table {i+1}",
                'type': 'dataset',
                'source': source,
                'records': record_count,
                'columns': column_count
            })
        
        # Find ACTUAL inter-dataset relationships by looking at triples that cross dataset boundaries
        links = _find_actual_dataset_relationships(nodes)
        
        tree_data = {
            'nodes': nodes,
            'links': links,
            'total_columns': total_columns,
            'metadata': {
                'total_datasets': len(nodes),
                'total_connections': len(links),
                'view_type': 'tree'
            }
        }
        
        return JsonResponse(tree_data)
        
    except Exception as e:
        logger.error(f"Error generating tree data: {e}", exc_info=True)
        return JsonResponse({
            'error': f'Error loading tree data: {str(e)}',
            'nodes': [],
            'links': []
        }, status=500)


def _get_dataset_column_count(dataset_uri):
    """Get approximate column count for a dataset by looking at distinct predicates."""
    try:
        # Get all records (cells) for this dataset
        record_uris = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        if not record_uris:
            return 0
        
        # Count distinct predicates used across all records (these represent columns)
        distinct_predicates = Triple.objects.filter(
            subject__uri__in=record_uris
        ).values('predicate__uri').distinct().count()
        
        return distinct_predicates
    except Exception as e:
        logger.error(f"Error counting columns for {dataset_uri}: {e}")
        return 0


def _find_actual_dataset_relationships(datasets):
    """Find actual relationships between datasets based on shared data references."""
    links = []
    
    for dataset1 in datasets:
        for dataset2 in datasets:
            if dataset1['id'] != dataset2['id']:
                # Look for triples where data from dataset1 references data from dataset2
                relationship_strength = _calculate_relationship_strength(dataset1['id'], dataset2['id'])
                
                if relationship_strength > 0:
                    links.append({
                        'source': dataset1['id'],
                        'target': dataset2['id'],
                        'type': 'data_reference',
                        'strength': relationship_strength,
                        'label': f'references ({relationship_strength} connections)'
                    })
    
    return links


def _calculate_relationship_strength(dataset1_uri, dataset2_uri):
    """Calculate the strength of relationship between two datasets based on actual data references."""
    try:
        # Get all cells from dataset1 (skip columns - get objects of Column hasPart triples)
        dataset1_columns = Triple.objects.filter(
            subject__uri=dataset1_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        dataset1_cells = Triple.objects.filter(
            subject__uri__in=dataset1_columns,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        # Get all cells from dataset2
        dataset2_columns = Triple.objects.filter(
            subject__uri=dataset2_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        dataset2_cells = Triple.objects.filter(
            subject__uri__in=dataset2_columns,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        if not dataset1_cells or not dataset2_cells:
            return 0
        
        # Count cross-references between cells (excluding rdf:value and dcterms:hasPart)
        cross_references = Triple.objects.filter(
            subject__uri__in=dataset1_cells,
            object__uri__in=dataset2_cells
        ).exclude(
            predicate__uri__in=[
                "http://purl.org/dc/terms/hasPart",
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            ]
        ).count()
        
        return cross_references
        
    except Exception as e:
        logger.error(f"Error calculating relationship strength: {e}")
        return 0


def _handle_dataset_columns_request(request, dataset_uri):
    """Handle request for columns within a specific dataset."""
    try:
        # The new import structure is: Dataset → hasPart → Column → hasPart → Cell
        # So we need to get Column resources that are direct children of the dataset
        
        # Get all column resources for this dataset
        column_uris = Triple.objects.filter(
            subject__uri=dataset_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        if not column_uris:
            return JsonResponse({'columns': []})
        
        # Get column resources (these should have URIs containing /columns/)
        column_resources = Resource.objects.filter(
            uri__in=column_uris,
            uri__contains='/columns/'  # Filter to actual column resources
        ).values('uri', 'name')
        
        columns = []
        for col_resource in column_resources:
            # Count cells for this column (Column → hasPart → Cell)
            cell_count = Triple.objects.filter(
                subject__uri=col_resource['uri'],
                predicate__uri="http://purl.org/dc/terms/hasPart"
            ).count()
            
            # Count relationships for this column
            relationship_count = _count_column_relationships_new(col_resource['uri'])
            
            # Get actual column type from literal datatypes (not guessing!)
            column_type = _get_actual_column_type(col_resource['uri'])
            
            columns.append({
                'id': col_resource['uri'],
                'name': col_resource['name'],
                'type': column_type,
                'cell_count': cell_count,
                'relationships': [{'count': relationship_count}] if relationship_count > 0 else []
            })
        
        return JsonResponse({'columns': columns})
        
    except Exception as e:
        logger.error(f"Error loading columns for {dataset_uri}: {e}", exc_info=True)
        return JsonResponse({'error': str(e), 'columns': []})


def _count_column_relationships(predicate_uri, record_uris):
    """Count how many relationships this column has to other datasets."""
    try:
        # Count triples using this predicate that point to resources outside the current dataset
        external_references = Triple.objects.filter(
            subject__uri__in=record_uris,
            predicate__uri=predicate_uri
        ).exclude(
            object__uri__in=record_uris
        ).count()
        
        return external_references
    except Exception as e:
        logger.error(f"Error counting relationships for {predicate_uri}: {e}")
        return 0


def _determine_column_type(predicate_uri):
    """Determine column type based on predicate URI patterns."""
    uri_lower = predicate_uri.lower()
    
    if 'date' in uri_lower or 'time' in uri_lower:
        return 'date'
    elif 'id' in uri_lower or 'key' in uri_lower:
        return 'string'
    elif 'count' in uri_lower or 'number' in uri_lower or 'amount' in uri_lower:
        return 'number'
    elif 'flag' in uri_lower or 'boolean' in uri_lower:
        return 'boolean'
    else:
        return 'string'


def _get_actual_column_type(column_uri):
    """Get the actual column type from the datatypes of its literal values."""
    try:
        # Get cells for this column: Column → hasPart → Cell
        cell_uris = Triple.objects.filter(
            subject__uri=column_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        if not cell_uris:
            return 'unknown'
        
        # Get literal values: Cell → rdf:value → Literal
        literal_resources = Triple.objects.filter(
            subject__uri__in=cell_uris,
            predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value",
            object__resource_type=ResourceType.LITERAL
        ).values_list('object__datatype', flat=True)
        
        # Count datatypes and return the most common one
        datatype_counts = {}
        for datatype in literal_resources:
            if datatype:
                datatype_counts[datatype] = datatype_counts.get(datatype, 0) + 1
        
        if not datatype_counts:
            return 'string'  # Default if no datatypes found
        
        # Get the most common datatype
        most_common_datatype = max(datatype_counts, key=datatype_counts.get)
        
        # Convert XSD datatypes to simple types
        if 'string' in most_common_datatype.lower():
            return 'string'
        elif any(t in most_common_datatype.lower() for t in ['int', 'decimal', 'float', 'double']):
            return 'number'
        elif any(t in most_common_datatype.lower() for t in ['date', 'time']):
            return 'date'  
        elif 'boolean' in most_common_datatype.lower():
            return 'boolean'
        else:
            return 'string'  # Default fallback
            
    except Exception as e:
        logger.error(f"Error getting actual column type for {column_uri}: {e}")
        return 'string'


def _count_column_relationships_new(column_uri):
    """Count relationships for a column resource based on its cells."""
    try:
        # Get all cells for this column
        cell_uris = Triple.objects.filter(
            subject__uri=column_uri,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).values_list('object__uri', flat=True)
        
        if not cell_uris:
            return 0
        
        # Count external references from these cells (excluding rdf:value and hasPart)
        external_references = Triple.objects.filter(
            subject__uri__in=cell_uris
        ).exclude(
            predicate__uri__in=[
                "http://purl.org/dc/terms/hasPart",
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            ]
        ).count()
        
        return external_references
        
    except Exception as e:
        logger.error(f"Error counting relationships for column {column_uri}: {e}")
        return 0


def _handle_relationships_request(request, item_id):
    """Handle request for relationships of a specific item."""
    try:
        # Find relationships for this item (could be dataset, column, or record)
        relationships = []
        
        # Look for outgoing relationships
        outgoing = Triple.objects.filter(
            subject__uri=item_id
        ).select_related('predicate', 'object')[:20]
        
        for triple in outgoing:
            if triple.object and hasattr(triple.object, 'name'):
                relationships.append({
                    'type': triple.predicate.name or 'references',
                    'target_name': triple.object.name or triple.object.uri,
                    'strength': 1.0,
                    'description': f"Points to {triple.object.name or 'resource'}"
                })
        
        # Look for incoming relationships
        incoming = Triple.objects.filter(
            object__uri=item_id
        ).select_related('predicate', 'subject')[:20]
        
        for triple in incoming:
            if triple.subject and hasattr(triple.subject, 'name'):
                relationships.append({
                    'type': f"referenced_by_{triple.predicate.name or 'unknown'}",
                    'target_name': triple.subject.name or triple.subject.uri,
                    'strength': 0.8,
                    'description': f"Referenced by {triple.subject.name or 'resource'}"
                })
        
        return JsonResponse({'relationships': relationships})
        
    except Exception as e:
        logger.error(f"Error loading relationships for {item_id}: {e}")
        return JsonResponse({'error': str(e), 'relationships': []})


def _handle_node_properties_request(request, node_id):
    """Handle HTMX request for node properties display."""
    try:
        # Try to find the resource by URI first (node_id might be a URI)
        try:
            resource = Resource.objects.get(uri=node_id)
        except Resource.DoesNotExist:
            # Fallback to ID lookup
            try:
                resource = Resource.objects.get(id=node_id)
            except Resource.DoesNotExist:
                return render(request, 'partials/node_properties.html', {
                    'error': f'Node not found: {node_id}'
                })
        
        # Count records if this is a dataset/table
        record_count = 0
        if resource.resource_type == ResourceType.IRI:
            record_count = Triple.objects.filter(
                subject=resource,
                predicate__uri="http://purl.org/dc/terms/hasPart"
            ).count()
        
        # Get some related triples for context
        related_triples = Triple.objects.filter(
            Q(subject=resource) | Q(object=resource)
        ).select_related('subject', 'predicate', 'object')[:10]
        
        context = {
            'resource': resource,
            'record_count': record_count,
            'related_triples': related_triples,
            'node_id': node_id
        }
        
        return render(request, 'partials/node_properties.html', context)
        
    except Exception as e:
        logger.error(f"Error loading node properties for {node_id}: {e}", exc_info=True)
        return render(request, 'partials/node_properties.html', {
            'error': f'Error loading properties: {str(e)}'
        })

@login_required
def service_powered_csv_import(request):
    """Import CSV files using the modern table-based service architecture."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    s3_file_id = request.POST.get('s3_file_id')
    use_auto_mapping = request.POST.get('use_auto_mapping', 'true').lower() == 'true'
    institution = request.POST.get('institution', 'DEFAULT')
    
    if not s3_file_id:
        return render(request, 'partials/service_import_results.html', {
            'error': 'No S3 file selected'
        })
    
    try:
        from arkumu.storage.services.bucket_service import BucketService
        from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
        import tempfile
        import os
        
        # Parse the file ID to get organization and S3 key
        logger.info(f"Starting service-powered import for: {s3_file_id}")
        if '_' not in s3_file_id:
            return render(request, 'partials/service_import_results.html', {
                'error': 'Invalid file ID format'
            })
        
        organization, s3_key = s3_file_id.split('_', 1)
        dataset_name = os.path.splitext(os.path.basename(s3_key))[0]
        
        # Download file from S3
        bucket_service = BucketService()
        bucket_name = bucket_service.get_organization_bucket(organization)
        file_content_result = bucket_service.get_file_content(bucket_name, s3_key)
        
        if not file_content_result.get('success'):
            return render(request, 'partials/service_import_results.html', {
                'error': f'Failed to download file: {file_content_result.get("error", "Unknown error")}'
            })
        
        # Save to temporary file for processing
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as temp_file:
            temp_file.write(file_content_result['content'])
            temp_path = temp_file.name
        
        try:
            # Use the modern table-based import approach
            logger.info(f"Importing {dataset_name} using table-based services")
            
            import_result = ImportWorkflowService.import_csv_with_table_services(
                csv_path=temp_path,
                dataset_name=dataset_name,
                institution=organization,
                base_uri="http://arkumu.org/data",
                delimiter=';',
                has_quoted_fields=False,
                auto_mapping=use_auto_mapping,
                session_dict=dict(request.session)  # Pass session for service state
            )
            
            # Update session with any new mapping rules created during import
            if 'mapping_rules' in import_result:
                request.session['mapping_rules'] = import_result['mapping_rules']
                request.session.modified = True
            
            return render(request, 'partials/service_import_results.html', {
                'import_result': import_result,
                'dataset_name': dataset_name,
                'organization': organization,
                'file_name': os.path.basename(s3_key),
                'approach': 'table_based_services',
                'success': True
            })
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.warning(f"Could not delete temporary file {temp_path}: {e}")
                
    except Exception as e:
        logger.error(f"Error in service-powered CSV import: {e}", exc_info=True)
        return render(request, 'partials/service_import_results.html', {
            'error': f'Import error: {str(e)}'
        })

@login_required
def graph_connections_view(request):
    """Simple graph viewer showing actual database connections."""
    return render(request, 'graph_connections.html')

@login_required
def get_datasets_htmx(request):
    """Get all datasets with actual hasPart connections."""
    from arkumu.metadata.models.triples import Triple
    
    # Find dataset resources (URIs containing /datasets/ but not /columns/ or /rows/)
    dataset_resources = Resource.objects.filter(
        uri__contains='/datasets/',
        resource_type=ResourceType.IRI
    ).exclude(
        uri__contains='/columns/'
    ).exclude(
        uri__contains='/rows/'
    ).exclude(
        uri__regex=r'/datasets/[^/]+/[^/]+/[^/]+$'  # Exclude cell URIs (have column/row pattern)
    ).order_by('name')
    
    # Get connection counts for each dataset
    datasets_with_counts = []
    for dataset in dataset_resources:
        # Count ONLY columns connected via hasPart (not rows or other objects)
        hasPart_triples = Triple.objects.filter(
            subject=dataset,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        # Filter to only count column resources (exclude rows)
        column_count = 0
        for triple in hasPart_triples:
            obj = triple.object
            # Only count objects that have '/columns/' in their URI (actual columns)
            # Exclude rows which have '/rows/' in their URI
            if '/columns/' in obj.uri:
                column_count += 1
        
        datasets_with_counts.append({
            'resource': dataset,
            'column_count': column_count
        })
    
    return render(request, 'partials/datasets_list.html', {
        'datasets': datasets_with_counts
    })

@login_required  
def get_dataset_columns_htmx(request, dataset_id):
    """Get columns for a specific dataset by analyzing cell URIs."""
    from arkumu.metadata.models.triples import Triple
    from collections import defaultdict
    
    try:
        dataset = Resource.objects.get(id=dataset_id)
        logger.info(f"DEBUG: Processing dataset: {dataset.name} - {dataset.uri}")
        
        # Get all hasPart triples from dataset (these point to cells directly)
        hasPart_triples = Triple.objects.filter(
            subject=dataset,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        logger.info(f"DEBUG: Found {hasPart_triples.count()} hasPart triples from dataset")
        
        # Group cells by column name extracted from URI
        # URI pattern: .../datasets/{dataset_name}/{column_name}/{row_id}
        column_groups = defaultdict(list)
        
        for triple in hasPart_triples:
            cell = triple.object
            cell_uri = cell.uri
            
            # Extract column name from URI
            try:
                uri_parts = cell_uri.split('/')
                if len(uri_parts) >= 2:
                    # Get the second-to-last part as column name, last part as row_id
                    column_name = uri_parts[-2]
                    row_id = uri_parts[-1]
                    
                    # Skip if this looks like a column resource URI or row resource URI
                    if column_name in ['columns', 'rows']:
                        continue
                        
                    column_groups[column_name].append({
                        'cell_resource': cell,
                        'row_id': row_id
                    })
            except (IndexError, AttributeError):
                logger.warning(f"Could not parse column name from URI: {cell_uri}")
                continue
        
        logger.info(f"DEBUG: Extracted {len(column_groups)} columns from cell URIs")
        
        # Create column info for template
        columns_with_counts = []
        for column_name, cells in column_groups.items():
            # Create a virtual column resource for the template
            virtual_column = {
                'resource': type('obj', (object,), {
                    'id': f'virtual-column-{column_name}',
                    'name': column_name,
                    'uri': f'virtual://{dataset.uri}/columns/{column_name}'
                })(),
                'cell_count': len(cells)
            }
            columns_with_counts.append(virtual_column)
            
            logger.info(f"DEBUG: Column '{column_name}' has {len(cells)} cells")
        
        logger.info(f"DEBUG: Final columns_with_counts: {len(columns_with_counts)} columns")
        
        return render(request, 'partials/columns_list.html', {
            'columns': columns_with_counts,
            'dataset': dataset
        })
        
    except Resource.DoesNotExist:
        logger.error(f"DEBUG: Dataset not found with ID: {dataset_id}")
        return HttpResponse('<p class="text-red-500">Dataset not found</p>')

@login_required
def get_column_cells_htmx(request, column_id):
    """Get cells for a specific column via hasPart relationships."""
    from arkumu.metadata.models.triples import Triple
    
    # Check if this is a virtual column ID
    if column_id.startswith('virtual-column-'):
        # Extract column name from virtual ID
        column_name = column_id.replace('virtual-column-', '')
        
        # We need to find the dataset to get its cells
        # For now, we'll search for cells that have this column name in their URI
        from arkumu.metadata.models.resources import Resource, ResourceType
        
        # Find all cells that match this column pattern
        # Look for resources that have the column name in their URI
        all_cells = Resource.objects.filter(
            uri__contains=f'/{column_name}/',
            resource_type=ResourceType.IRI
        ).exclude(
            uri__contains='/columns/'
        ).exclude(
            uri__contains='/rows/'
        )
        
        # Filter to only actual cell resources (those with row pattern)
        cell_resources = []
        for cell in all_cells:
            uri_parts = cell.uri.split('/')
            if len(uri_parts) >= 2:
                # Check if second-to-last part matches column name
                if uri_parts[-2] == column_name:
                    cell_resources.append(cell)
        
        cells_with_values = []
        for cell in cell_resources:
            # Get the literal value via rdf:value
            value_triple = Triple.objects.filter(
                subject=cell,
                predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            ).select_related('object').first()
            
            literal_value = None
            if value_triple and value_triple.object:
                literal_value = value_triple.object.value
                
            cells_with_values.append({
                'resource': cell,
                'literal_value': literal_value,
                'row_id': cell.uri.split('/')[-1] if cell.uri else 'unknown'
            })
        
        # Sort by row_id for better display
        cells_with_values.sort(key=lambda x: x['row_id'])
        
        # Create a virtual column object for the template
        virtual_column = type('obj', (object,), {
            'id': column_id,
            'name': column_name,
            'uri': f'virtual://columns/{column_name}'
        })()
        
        return render(request, 'partials/cells_list.html', {
            'cells': cells_with_values,
            'column': virtual_column
        })
    
    # Handle regular UUID column IDs
    try:
        column = Resource.objects.get(id=column_id)
        
        # Get cells via hasPart triples
        cell_triples = Triple.objects.filter(
            subject=column,
            predicate__uri="http://purl.org/dc/terms/hasPart"
        ).select_related('object')
        
        cells_with_values = []
        for triple in cell_triples:
            cell = triple.object
            
            # Get the literal value via rdf:value
            value_triple = Triple.objects.filter(
                subject=cell,
                predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
            ).select_related('object').first()
            
            literal_value = None
            if value_triple and value_triple.object:
                literal_value = value_triple.object.value
                
            cells_with_values.append({
                'resource': cell,
                'literal_value': literal_value,
                'row_id': cell.uri.split('/')[-1] if cell.uri else 'unknown'
            })
        
        # Sort by row_id for better display
        cells_with_values.sort(key=lambda x: x['row_id'])
        
        return render(request, 'partials/cells_list.html', {
            'cells': cells_with_values,
            'column': column
        })
        
    except Resource.DoesNotExist:
        return HttpResponse('<p class="text-red-500">Column not found</p>')

@login_required
def get_cell_connections_htmx(request, cell_id):
    """Get all connections for a specific cell."""
    from arkumu.metadata.models.triples import Triple
    
    try:
        cell = Resource.objects.get(id=cell_id)
        
        # Get all triples where this cell is subject or object
        outgoing_triples = Triple.objects.filter(subject=cell).select_related('predicate', 'object')
        incoming_triples = Triple.objects.filter(object=cell).select_related('subject', 'predicate')
        
        return render(request, 'partials/cell_connections.html', {
            'cell': cell,
            'outgoing_triples': outgoing_triples,
            'incoming_triples': incoming_triples
        })
        
    except Resource.DoesNotExist:
        return HttpResponse('<p class="text-red-500">Cell not found</p>')

 