from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from arkumu.importer.models import IngestSession
from arkumu.metadata.models import Resource, Triple, ResourceType


@login_required
def database_structure_visualizer(request, session_id):
    """Display the database structures created from an import session."""
    ingest_session = get_object_or_404(IngestSession, pk=session_id)
    
    # Get resources created during this import (based on source)
    source_filter = f"import_{ingest_session.id}"
    resources = Resource.objects.filter(source__icontains=source_filter)
    
    # Count resources and triples
    resource_count = resources.count()
    triple_count = Triple.objects.filter(
        Q(subject__source__icontains=source_filter) |
        Q(object__source__icontains=source_filter)
    ).distinct().count()
    
    # Get resource type breakdown
    resource_types = resources.values('resource_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Add example URIs for each type
    for type_info in resource_types:
        examples = resources.filter(
            resource_type=type_info['resource_type']
        ).values_list('uri', flat=True)[:5]
        type_info['examples'] = list(examples)
    
    # Get triple patterns
    triple_patterns = []
    pattern_query = Triple.objects.filter(
        Q(subject__source__icontains=source_filter) |
        Q(object__source__icontains=source_filter)
    ).select_related('subject', 'predicate', 'object')
    
    # Group by pattern
    pattern_counts = {}
    for triple in pattern_query[:1000]:  # Limit for performance
        pattern = (
            triple.subject.resource_type,
            triple.predicate.uri.split('/')[-1],  # Simplify predicate display
            triple.object.resource_type
        )
        if pattern not in pattern_counts:
            pattern_counts[pattern] = {
                'count': 0,
                'example': None
            }
        pattern_counts[pattern]['count'] += 1
        if not pattern_counts[pattern]['example']:
            pattern_counts[pattern]['example'] = {
                'subject': triple.subject.uri,
                'predicate': triple.predicate.uri,
                'object': triple.object.value or triple.object.uri
            }
    
    # Convert to list for template
    for pattern, data in pattern_counts.items():
        triple_patterns.append({
            'subject_type': pattern[0],
            'predicate': pattern[1],
            'object_type': pattern[2],
            'count': data['count'],
            'example': data['example']
        })
    
    # Sort by count
    triple_patterns.sort(key=lambda x: x['count'], reverse=True)
    
    # Get entity classes (resources that are classes)
    entity_classes = []
    class_resources = resources.filter(resource_type=ResourceType.CLASS)
    for class_res in class_resources:
        # Count instances of this class
        instance_count = Triple.objects.filter(
            predicate__uri='http://www.w3.org/1999/02/22-rdf-syntax-ns#type',
            object=class_res
        ).count()
        
        entity_classes.append({
            'uri': class_res.uri,
            'label': class_res.value,
            'instance_count': instance_count
        })
    
    # Get sample resources with property counts
    sample_resources = []
    for resource in resources.filter(resource_type=ResourceType.IRI)[:20]:
        property_count = Triple.objects.filter(subject=resource).count()
        sample_resources.append({
            'id': resource.id,
            'uri': resource.uri,
            'resource_type': resource.resource_type,
            'value': resource.value,
            'property_count': property_count
        })
    
    context = {
        'ingest_session': ingest_session,
        'resource_count': resource_count,
        'triple_count': triple_count,
        'resource_types': resource_types,
        'triple_patterns': triple_patterns[:20],  # Limit display
        'entity_classes': entity_classes,
        'sample_resources': sample_resources
    }
    
    return render(request, 'metadata/database_structure_visualizer.html', context)