import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.urls import reverse

# Import views from their respective modules

from arkumu.storage.views.streaming_upload_views import streaming_upload_form

logger = logging.getLogger(__name__)


@login_required
def upload_form(request):
    """
    Use the streaming upload form directly.
    
    The old upload form using presigned URLs is now deprecated.
    This view directly calls the streaming upload form view.
    """
    logger.info(f"User {request.user.username} accessing upload form, using streaming upload")
    return streaming_upload_form(request)


@login_required
def upload_success(request):
    """
    Render the upload success page.
    
    This is a simple view that renders the success confirmation template.
    No business logic is performed here.
    """
    return render(request, "upload/upload_success.html")
