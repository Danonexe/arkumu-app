from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import UploadSession
from arkumu.importer.models import IngestSession
from arkumu.users.mixins import general_login_required


@general_login_required
def metadata_dashboard(request):
    """Main dashboard view for metadata visualization and analysis."""
    # Get basic statistics
    stats = {
        'total_resources': Resource.objects.count(),
        'total_triples': Triple.objects.count(),
        'iri_resources': Resource.objects.filter(resource_type=ResourceType.IRI).count(),
        'literal_resources': Resource.objects.filter(resource_type=ResourceType.LITERAL).count(),
        'class_resources': Resource.objects.filter(resource_type=ResourceType.CLASS).count(),
        'property_resources': Resource.objects.filter(resource_type=ResourceType.PROPERTY).count(),
        'uploads': UploadSession.objects.count(),
        'ingests': IngestSession.objects.count(),
    }
    
    # Get recent uploads
    recent_uploads = UploadSession.objects.all().order_by('-created_at')[:5]
    
    # Get recent ingests
    recent_ingests = IngestSession.objects.all().order_by('-created_at')[:5]
    
    # Get institutions with resource counts
    institutions = Resource.objects.values('source').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    return render(request, 'dashboard.html', {
        'stats': stats,
        'recent_uploads': recent_uploads,
        'recent_ingests': recent_ingests,
        'institutions': institutions,
    })


@general_login_required
def all_upload_sessions(request):
    """Displays a list of all upload sessions."""
    all_uploads = UploadSession.objects.all().order_by('-created_at')
    # TODO: Add pagination if the list can become very long
    return render(request, 'all_upload_sessions.html', {
        'upload_sessions': all_uploads
    })


@general_login_required
def all_ingest_sessions(request):
    """Displays a list of all ingest sessions with their datasets."""
    all_ingests = IngestSession.objects.prefetch_related('import_tasks').all().order_by('-created_at')
    
    # Prepare enhanced session data
    enhanced_sessions = []
    for session in all_ingests:
        # Get associated import tasks (individual datasets)
        import_tasks = list(session.import_tasks.all())
        
        # Determine datasets for this session
        datasets = []
        if import_tasks:
            # Multi-dataset session - each ImportTask is a dataset
            for task in import_tasks:
                datasets.append({
                    'name': task.dataset_name,
                    'file_path': task.file_path,
                    'status': task.status,
                    'rows_processed': task.rows_processed,
                    'task_id': task.task_id,
                })
        elif session.file_paths:
            # Multi-file session from file_paths
            for file_path in session.file_paths:
                filename = file_path.split('/')[-1] if '/' in file_path else file_path
                datasets.append({
                    'name': filename,
                    'file_path': file_path,
                    'status': session.status,
                    'rows_processed': session.processed_rows if len(session.file_paths) == 1 else None,
                })
        else:
            # Single dataset session
            datasets.append({
                'name': session.dataset_name or session.file_name or 'Unknown Dataset',
                'file_path': session.s3_object_key,
                'status': session.status,
                'rows_processed': session.processed_rows,
            })
        
        enhanced_sessions.append({
            'session': session,
            'datasets': datasets,
            'dataset_count': len(datasets),
            'is_multi_dataset': len(datasets) > 1
        })
    
    # Calculate aggregate statistics
    total_stats = {
        'total_sessions': len(enhanced_sessions),
        'total_datasets': sum(item['dataset_count'] for item in enhanced_sessions),
        'completed_sessions': sum(1 for item in enhanced_sessions if item['session'].status == 'completed'),
        'failed_sessions': sum(1 for item in enhanced_sessions if item['session'].status == 'failed'),
        'processing_sessions': sum(1 for item in enhanced_sessions if item['session'].status == 'processing'),
        'total_rows_processed': 0,
        'total_resources_created': 0,
        'total_triples_created': 0,
        'sessions_with_stats': 0,
    }
    
    # Sum up ingestion stats
    for item in enhanced_sessions:
        session = item['session']
        if session.ingestion_stats:
            total_stats['sessions_with_stats'] += 1
            total_stats['total_rows_processed'] += session.ingestion_stats.get('rows_processed', 0)
            total_stats['total_resources_created'] += session.ingestion_stats.get('resources_created', 0)
            total_stats['total_triples_created'] += session.ingestion_stats.get('triples_created', 0)
    
    return render(request, 'all_ingest_sessions.html', {
        'enhanced_sessions': enhanced_sessions,
        'total_stats': total_stats
    })


@general_login_required
def ingest_session_stats(request, session_id):
    """HTMX endpoint to show detailed stats for a specific ingest session."""
    try:
        session = IngestSession.objects.get(pk=session_id)
        return render(request, 'importer/partials/stats_modal_content.html', {
            'session': session,
            'show_expanded': True
        })
    except IngestSession.DoesNotExist:
        return render(request, 'partials/error_message.html', {
            'error': 'Ingest session not found'
        })


