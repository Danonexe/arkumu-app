from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.conf import settings
from arkumu.metadata.models.base import UUIDModel


class HarmonizationRule(UUIDModel):
    """Stores mapping rules between archive properties and catalog properties"""
    
    # Source specification
    source_organization = models.ForeignKey('users.Organization', on_delete=models.CASCADE, related_name='harmonization_rules')
    source_property_pattern = models.CharField(
        max_length=512,
        help_text="Regex or exact match pattern for source properties"
    )
    
    # Target catalog property
    catalog_property_uri = models.URLField(max_length=512, help_text="URI of the catalog-level property")
    catalog_property_label = models.CharField(max_length=255, help_text="Human-readable label for the catalog property")
    
    # Mapping metadata
    MAPPING_TYPE_CHOICES = [
        ('exact', 'Exact Match'),
        ('close', 'Close Match'),
        ('broad', 'Broader Match'),
        ('narrow', 'Narrower Match')
    ]
    mapping_type = models.CharField(
        max_length=20,
        choices=MAPPING_TYPE_CHOICES,
        default='exact',
        help_text="Type of semantic mapping"
    )
    
    # Conflict resolution
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority wins in conflicts"
    )
    
    # Validation and status
    is_active = models.BooleanField(default=True, help_text="Whether this rule is currently active")
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='validated_harmonization_rules'
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Additional notes about this rule")
    
    class Meta:
        db_table = 'metadata_harmonization_rule'
        ordering = ['-priority', 'catalog_property_label']
        unique_together = [
            ['source_organization', 'source_property_pattern', 'catalog_property_uri']
        ]
        indexes = [
            models.Index(fields=['source_organization', 'is_active']),
            models.Index(fields=['catalog_property_uri']),
        ]
    
    def __str__(self):
        return f"{self.source_organization.name}: {self.source_property_pattern} -> {self.catalog_property_label}"


class HarmonizationExecution(UUIDModel):
    """Tracks harmonization runs for auditing and rollback"""
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Scope
    organizations = models.ManyToManyField('users.Organization', related_name='harmonization_executions')
    rules_applied = models.ManyToManyField('HarmonizationRule', related_name='executions')
    
    # Statistics
    resources_processed = models.IntegerField(default=0)
    triples_created = models.IntegerField(default=0)
    conflicts_resolved = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    
    # Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Execution context
    execution_mode = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manual'),
            ('scheduled', 'Scheduled'),
            ('triggered', 'Triggered by Import')
        ],
        default='manual'
    )
    
    # Performance tracking
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'metadata_harmonization_execution'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['completed_at']),
        ]
    
    def __str__(self):
        return f"Harmonization {self.id} - {self.status} ({self.started_at})"
    
    def calculate_duration(self):
        """Calculate and store execution duration"""
        if self.completed_at and self.started_at:
            self.duration_seconds = int((self.completed_at - self.started_at).total_seconds())
            self.save(update_fields=['duration_seconds'])


class HarmonizationConflict(UUIDModel):
    """Records conflicts encountered during harmonization for review"""
    
    execution = models.ForeignKey(
        HarmonizationExecution,
        on_delete=models.CASCADE,
        related_name='conflicts'
    )
    
    # Conflict details
    source_resource_uri = models.URLField(max_length=512)
    conflicting_rules = models.ManyToManyField(HarmonizationRule, related_name='conflicts')
    
    # Resolution
    RESOLUTION_CHOICES = [
        ('priority', 'Resolved by Priority'),
        ('manual', 'Manual Override'),
        ('skipped', 'Skipped'),
        ('pending', 'Pending Review')
    ]
    resolution = models.CharField(
        max_length=20,
        choices=RESOLUTION_CHOICES,
        default='pending'
    )
    
    selected_rule = models.ForeignKey(
        HarmonizationRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='selected_for_conflicts'
    )
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'metadata_harmonization_conflict'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['execution', 'resolution']),
            models.Index(fields=['source_resource_uri']),
        ]
    
    def __str__(self):
        return f"Conflict for {self.source_resource_uri} in execution {self.execution_id}"