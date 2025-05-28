from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.storage.models import UploadSession

@login_required
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
    }
    
    # Get recent uploads
    recent_uploads = UploadSession.objects.all().order_by('-created_at')[:5]
    
    # Get institutions with resource counts
    institutions = Resource.objects.values('source').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    return render(request, 'dashboard.html', {
        'stats': stats,
        'recent_uploads': recent_uploads,
        'institutions': institutions,
    })


