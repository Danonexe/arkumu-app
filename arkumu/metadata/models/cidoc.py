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

class CIDOCClass(UUIDModel):
    """
    Represents a CIDOC-CRM class (E1, E2, etc.).
    """
    class_id = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField()
    parent_classes = models.ManyToManyField('self', symmetrical=False, related_name='child_classes', blank=True)
    is_primitive = models.BooleanField(
        default=False,
        help_text="If True, this class represents a primitive value type (E59, E60, etc.)"
    )
    
    class Meta:
        verbose_name = "CIDOC Class"
        verbose_name_plural = "CIDOC Classes"
    
    def __str__(self):
        return f"{self.class_id}: {self.label}"

class CIDOCProperty(UUIDModel):
    """
    Represents a CIDOC-CRM property definition (P1, P2, etc.).
    """
    property_id = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    description = models.TextField()
    domain_class = models.ForeignKey(CIDOCClass, on_delete=models.SET_NULL, null=True, related_name='domain_properties')
    range_class = models.ForeignKey(CIDOCClass, on_delete=models.SET_NULL, null=True, related_name='range_properties')
    
    # Property characteristics from RDF
    is_functional = models.BooleanField(default=False, help_text="Property can have at most one value")
    is_symmetric = models.BooleanField(default=False, help_text="If A relates to B, then B relates to A")
    is_transitive = models.BooleanField(default=False, help_text="If A relates to B and B to C, then A relates to C")
    
    # Property hierarchy
    parent_properties = models.ManyToManyField('self', symmetrical=False, related_name='child_properties', blank=True)
    inverse_property = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='inverse_of',
        help_text="The inverse property (e.g., P1i for P1)"
    )
    
    class Meta:
        verbose_name = "CIDOC Property"
        verbose_name_plural = "CIDOC Properties"
    
    def __str__(self):
        return f"{self.property_id}: {self.label}" 
