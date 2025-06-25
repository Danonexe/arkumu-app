from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class UUIDModel(models.Model):
    """Abstract base class for tracking"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_created', null=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name='%(class)s_updated', null=True)

    class Meta:
        abstract = True
