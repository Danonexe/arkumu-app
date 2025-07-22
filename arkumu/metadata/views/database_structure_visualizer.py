from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from arkumu.importer.models import IngestSession
from arkumu.metadata.models import Resource, Triple, ResourceType


@login_required
def database_structure_visualizer(request, session_id):
    """Display the database structures created from an import session."""
    ingest_session = get_object_or_404(IngestSession, pk=session_id)
    
    # Get resources created during this import session
    # Resources are associated by organization code, not session ID
    # We need to filter by organization and approximate time range
    import datetime
    from django.utils import timezone
    
    # Get resources from this organization created around the same time as the session
    organization_code = ingest_session.organization.code
    
    # Define a time window around the session (more flexible approach)
    session_start = ingest_session.created_at
    session_end = ingest_session.completed_at or timezone.now()
    
    # Expand time window by 1 hour on each side to catch related resources
    time_buffer = datetime.timedelta(hours=1)
    start_time = session_start - time_buffer
    end_time = session_end + time_buffer
    
    resources = Resource.objects.filter(
        source=organization_code,
        created_at__range=(start_time, end_time)
    ).order_by('-created_at')
    
    # Count resources and triples
    resource_count = resources.count()
    triple_count = Triple.objects.filter(
        Q(subject__source=organization_code, subject__created_at__range=(start_time, end_time)) |
        Q(object__source=organization_code, object__created_at__range=(start_time, end_time))
    ).distinct().count()
    
    # Get resource type breakdown
    resource_types = resources.values('resource_type').annotate(
        count=Count('id')
    ).order_by('-count')
    
    
    
    # Get import tasks for detailed dataset status
    import_tasks = ingest_session.import_tasks.all().order_by('created_at')
    
    context = {
        'ingest_session': ingest_session,
        'resource_count': resource_count,
        'triple_count': triple_count,
        'resource_types': resource_types,
        'import_tasks': import_tasks
    }
    
    return render(request, 'metadata/database_structure_visualizer.html', context)