from django.db import models
from django.conf import settings
from django.utils.timezone import now
from django.utils import timezone

class UserTrackedModel(models.Model):
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        blank=True,
        null=True,
        related_name='%(class)s_created_set'
    )
    last_updated_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        blank=True,
        null=True,
        related_name='%(class)s_updated_set'
    )
    audit_created = models.DateTimeField(null=True, blank=True)
    audit_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        from arkumu.metadata.middleware import get_current_user
        
        user = get_current_user()
        
        if not self.pk:  # New instance
            self.created_by_user = user
            self.audit_created = now()
            
        self.last_updated_by_user = user
        self.audit_updated = now()
        super().save(*args, **kwargs)
