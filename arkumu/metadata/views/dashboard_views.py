from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import UploadSession
from arkumu.importer.models import IngestSession


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


def all_upload_sessions(request):
    """Displays a list of all upload sessions."""
    all_uploads = UploadSession.objects.all().order_by('-created_at')
    # TODO: Add pagination if the list can become very long
    return render(request, 'all_upload_sessions.html', {
        'upload_sessions': all_uploads
    })


def all_ingest_sessions(request):
    """Displays a list of all ingest sessions."""
    all_ingests = IngestSession.objects.all().order_by('-created_at')
    # TODO: Add pagination if the list can become very long
    return render(request, 'all_ingest_sessions.html', {
        'ingest_sessions': all_ingests
    })


