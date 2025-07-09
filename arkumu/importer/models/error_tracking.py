"""
Comprehensive error tracking and persistence models for the import pipeline.
Provides structured error handling, validation issue persistence, and communication.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
import json


class ImportPipelineError(models.Model):
    """
    Tracks all errors that occur during the import pipeline.
    Provides structured error information for debugging and analysis.
    """
    
    ERROR_CATEGORIES = [
        ('validation', 'Validation Error'),
        ('file_processing', 'File Processing Error'),
        ('data_transformation', 'Data Transformation Error'),
        ('execution', 'Execution Error'),
        ('storage', 'Storage Error'),
        ('mapping', 'Mapping Error'),
        ('system', 'System Error'),
    ]
    
    ERROR_SEVERITY = [
        ('critical', 'Critical'),
        ('error', 'Error'),
        ('warning', 'Warning'),
        ('info', 'Information'),
    ]
    
    ERROR_STATUS = [
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Error identification
    error_code = models.CharField(max_length=50, help_text="Unique error code for categorization")
    error_type = models.CharField(max_length=100, help_text="Python exception type or error class")
    error_message = models.TextField(help_text="Human-readable error message")
    error_category = models.CharField(max_length=20, choices=ERROR_CATEGORIES, default='system')
    severity = models.CharField(max_length=10, choices=ERROR_SEVERITY, default='error')
    
    # Context information
    ingest_session = models.ForeignKey(
        'IngestSession',
        on_delete=models.CASCADE,
        related_name='pipeline_errors',
        null=True,
        blank=True
    )
    mapping_id = models.UUIDField(null=True, blank=True, help_text="Associated mapping ID")
    dataset_name = models.CharField(max_length=255, blank=True, help_text="Dataset being processed")
    file_path = models.CharField(max_length=512, blank=True, help_text="File path causing the error")
    row_number = models.IntegerField(null=True, blank=True, help_text="Row number in CSV file")
    column_name = models.CharField(max_length=100, blank=True, help_text="Column name causing error")
    
    # Technical details
    stack_trace = models.TextField(blank=True, help_text="Full stack trace")
    context_data = models.JSONField(default=dict, blank=True, help_text="Additional context data")
    
    # Timing and tracking
    occurred_at = models.DateTimeField(auto_now_add=True)
    first_occurrence = models.DateTimeField(auto_now_add=True)
    last_occurrence = models.DateTimeField(auto_now=True)
    occurrence_count = models.IntegerField(default=1)
    
    # Status tracking
    status = models.CharField(max_length=15, choices=ERROR_STATUS, default='new')
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_errors'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, help_text="Notes about error resolution")
    
    class Meta:
        verbose_name = "Import Pipeline Error"
        verbose_name_plural = "Import Pipeline Errors"
        indexes = [
            models.Index(fields=['error_category', 'severity']),
            models.Index(fields=['ingest_session', 'occurred_at']),
            models.Index(fields=['error_code', 'status']),
            models.Index(fields=['mapping_id', 'dataset_name']),
            models.Index(fields=['occurred_at']),
        ]
        ordering = ['-occurred_at']
    
    def __str__(self):
        return f"{self.error_code}: {self.error_message[:50]}..."
    
    def acknowledge(self, user, notes=None):
        """Mark error as acknowledged by a user"""
        self.status = 'acknowledged'
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        if notes:
            self.resolution_notes = notes
        self.save()
    
    def resolve(self, notes=None):
        """Mark error as resolved"""
        self.status = 'resolved'
        if notes:
            self.resolution_notes = notes
        self.save()
    
    def increment_occurrence(self):
        """Increment occurrence count for duplicate errors"""
        self.occurrence_count += 1
        self.last_occurrence = timezone.now()
        self.save()
    
    @classmethod
    def create_or_increment(cls, error_code, error_type, error_message, **kwargs):
        """Create new error or increment existing one"""
        try:
            existing = cls.objects.get(
                error_code=error_code,
                error_type=error_type,
                status__in=['new', 'acknowledged', 'investigating']
            )
            existing.increment_occurrence()
            return existing
        except cls.DoesNotExist:
            return cls.objects.create(
                error_code=error_code,
                error_type=error_type,
                error_message=error_message,
                **kwargs
            )


class MappingValidationIssue(models.Model):
    """
    Tracks validation issues found in mapping configurations.
    Provides structured validation feedback and remediation guidance.
    """
    
    ISSUE_TYPES = [
        ('missing_field', 'Missing Required Field'),
        ('invalid_type', 'Invalid Data Type'),
        ('invalid_reference', 'Invalid Reference'),
        ('circular_dependency', 'Circular Dependency'),
        ('inconsistent_config', 'Inconsistent Configuration'),
        ('performance_warning', 'Performance Warning'),
        ('best_practice', 'Best Practice Violation'),
    ]
    
    ISSUE_SEVERITY = [
        ('blocker', 'Blocker'),
        ('critical', 'Critical'),
        ('major', 'Major'),
        ('minor', 'Minor'),
        ('info', 'Information'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Issue identification
    mapping_id = models.UUIDField(help_text="Associated mapping ID")
    mapping_name = models.CharField(max_length=255, help_text="Mapping name for reference")
    organization = models.CharField(max_length=100, help_text="Organization code")
    
    # Issue details
    issue_type = models.CharField(max_length=30, choices=ISSUE_TYPES)
    severity = models.CharField(max_length=10, choices=ISSUE_SEVERITY)
    issue_code = models.CharField(max_length=50, help_text="Unique issue code")
    issue_message = models.TextField(help_text="Human-readable issue description")
    
    # Location information
    dataset_name = models.CharField(max_length=255, blank=True, help_text="Dataset with issue")
    column_name = models.CharField(max_length=100, blank=True, help_text="Column with issue")
    field_path = models.CharField(max_length=255, blank=True, help_text="JSON path to problematic field")
    
    # Technical details
    expected_value = models.TextField(blank=True, help_text="What was expected")
    actual_value = models.TextField(blank=True, help_text="What was found")
    context_data = models.JSONField(default=dict, blank=True, help_text="Additional context")
    
    # Remediation guidance
    remediation_suggestion = models.TextField(blank=True, help_text="Suggested fix")
    documentation_link = models.URLField(blank=True, help_text="Link to relevant documentation")
    
    # Timing
    detected_at = models.DateTimeField(auto_now_add=True)
    validation_run_id = models.UUIDField(null=True, blank=True, help_text="ID of validation run")
    
    class Meta:
        verbose_name = "Mapping Validation Issue"
        verbose_name_plural = "Mapping Validation Issues"
        indexes = [
            models.Index(fields=['mapping_id', 'severity']),
            models.Index(fields=['organization', 'detected_at']),
            models.Index(fields=['issue_type', 'severity']),
            models.Index(fields=['validation_run_id']),
        ]
        ordering = ['-detected_at', 'severity']
    
    def __str__(self):
        return f"{self.mapping_name}: {self.issue_message[:50]}..."
    
    @property
    def is_blocking(self):
        """Check if this issue blocks execution"""
        return self.severity in ['blocker', 'critical']
    
    @property
    def location_display(self):
        """Human-readable location of the issue"""
        parts = []
        if self.dataset_name:
            parts.append(f"Dataset: {self.dataset_name}")
        if self.column_name:
            parts.append(f"Column: {self.column_name}")
        if self.field_path:
            parts.append(f"Path: {self.field_path}")
        return " | ".join(parts) if parts else "General"


class FileProcessingIssue(models.Model):
    """
    Tracks issues encountered during file processing.
    Provides detailed information about file-level problems.
    """
    
    ISSUE_TYPES = [
        ('file_not_found', 'File Not Found'),
        ('file_corrupted', 'File Corrupted'),
        ('encoding_error', 'Encoding Error'),
        ('format_error', 'Format Error'),
        ('size_limit', 'Size Limit Exceeded'),
        ('permission_denied', 'Permission Denied'),
        ('network_error', 'Network Error'),
        ('parsing_error', 'Parsing Error'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # File identification
    ingest_session = models.ForeignKey(
        'IngestSession',
        on_delete=models.CASCADE,
        related_name='file_issues'
    )
    file_path = models.CharField(max_length=512, help_text="Full path to problematic file")
    file_name = models.CharField(max_length=255, help_text="File name")
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    
    # Issue details
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPES)
    issue_message = models.TextField(help_text="Detailed issue description")
    
    # Technical details
    error_details = models.JSONField(default=dict, blank=True, help_text="Technical error details")
    detected_encoding = models.CharField(max_length=50, blank=True, help_text="Detected file encoding")
    expected_format = models.CharField(max_length=50, blank=True, help_text="Expected file format")
    
    # Recovery information
    recovery_attempted = models.BooleanField(default=False)
    recovery_successful = models.BooleanField(default=False)
    recovery_notes = models.TextField(blank=True, help_text="Recovery attempt details")
    
    # Timing
    detected_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "File Processing Issue"
        verbose_name_plural = "File Processing Issues"
        indexes = [
            models.Index(fields=['ingest_session', 'issue_type']),
            models.Index(fields=['file_path']),
            models.Index(fields=['detected_at']),
        ]
        ordering = ['-detected_at']
    
    def __str__(self):
        return f"{self.file_name}: {self.issue_message[:50]}..."


class ExecutionPhaseError(models.Model):
    """
    Tracks errors that occur during specific execution phases.
    Provides phase-specific error analysis and recovery guidance.
    """
    
    EXECUTION_PHASES = [
        ('validation', 'Validation Phase'),
        ('file_download', 'File Download Phase'),
        ('data_processing', 'Data Processing Phase'),
        ('entity_creation', 'Entity Creation Phase'),
        ('literal_processing', 'Literal Processing Phase'),
        ('relationship_processing', 'Relationship Processing Phase'),
        ('context_processing', 'Context Processing Phase'),
        ('finalization', 'Finalization Phase'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Phase identification
    ingest_session = models.ForeignKey(
        'IngestSession',
        on_delete=models.CASCADE,
        related_name='phase_errors'
    )
    phase = models.CharField(max_length=25, choices=EXECUTION_PHASES)
    phase_step = models.CharField(max_length=100, blank=True, help_text="Specific step within phase")
    
    # Error details
    error_type = models.CharField(max_length=100, help_text="Python exception type")
    error_message = models.TextField(help_text="Error message")
    stack_trace = models.TextField(blank=True, help_text="Stack trace")
    
    # Context
    dataset_name = models.CharField(max_length=255, blank=True)
    batch_info = models.JSONField(default=dict, blank=True, help_text="Batch processing context")
    
    # Impact assessment
    rows_affected = models.IntegerField(default=0, help_text="Number of rows affected")
    can_continue = models.BooleanField(default=False, help_text="Can execution continue?")
    
    # Recovery
    recovery_strategy = models.CharField(max_length=100, blank=True, help_text="Suggested recovery strategy")
    retry_count = models.IntegerField(default=0, help_text="Number of retry attempts")
    
    # Timing
    occurred_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Execution Phase Error"
        verbose_name_plural = "Execution Phase Errors"
        indexes = [
            models.Index(fields=['ingest_session', 'phase']),
            models.Index(fields=['phase', 'error_type']),
            models.Index(fields=['occurred_at']),
        ]
        ordering = ['-occurred_at']
    
    def __str__(self):
        return f"{self.phase}: {self.error_message[:50]}..."


class ErrorCommunication(models.Model):
    """
    Tracks how errors are communicated to users and administrators.
    Ensures proper notification and follow-up on critical issues.
    """
    
    COMMUNICATION_TYPES = [
        ('email', 'Email Notification'),
        ('ui_alert', 'UI Alert'),
        ('slack', 'Slack Notification'),
        ('log_entry', 'Log Entry'),
        ('dashboard', 'Dashboard Update'),
    ]
    
    COMMUNICATION_STATUS = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('acknowledged', 'Acknowledged'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Error reference
    pipeline_error = models.ForeignKey(
        'ImportPipelineError',
        on_delete=models.CASCADE,
        related_name='communications'
    )
    
    # Communication details
    communication_type = models.CharField(max_length=15, choices=COMMUNICATION_TYPES)
    recipient = models.EmailField(help_text="Email address of recipient")
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='error_communications'
    )
    
    # Message content
    subject = models.CharField(max_length=255, help_text="Communication subject")
    message = models.TextField(help_text="Communication message")
    
    # Status tracking
    status = models.CharField(max_length=15, choices=COMMUNICATION_STATUS, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    # Technical details
    external_id = models.CharField(max_length=255, blank=True, help_text="External service message ID")
    error_details = models.JSONField(default=dict, blank=True, help_text="Communication error details")
    
    class Meta:
        verbose_name = "Error Communication"
        verbose_name_plural = "Error Communications"
        indexes = [
            models.Index(fields=['pipeline_error', 'status']),
            models.Index(fields=['recipient', 'sent_at']),
            models.Index(fields=['communication_type', 'status']),
        ]
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.communication_type} to {self.recipient}: {self.subject}"
    
    def mark_sent(self, external_id=None):
        """Mark communication as sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        if external_id:
            self.external_id = external_id
        self.save()
    
    def mark_acknowledged(self):
        """Mark communication as acknowledged"""
        self.status = 'acknowledged'
        self.acknowledged_at = timezone.now()
        self.save()