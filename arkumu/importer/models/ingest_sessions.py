from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone

class IngestSession(models.Model):
    """Represents a CSV ingestion session from S3 into the database"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    dataset_name = models.CharField(max_length=255, help_text="Name of the dataset being ingested", null=True, blank=True)
    organization = models.ForeignKey(
        'users.Organization',
        on_delete=models.CASCADE,
        help_text="Organization this ingestion belongs to"
    )
    s3_bucket = models.CharField(max_length=255, help_text="S3 bucket containing the CSV file", null=True, blank=True)
    s3_object_key = models.CharField(max_length=512, help_text="S3 object key/path to the CSV file", null=True, blank=True)
    
    # Multi-file mapping-aware import fields
    file_paths = models.JSONField(default=list, blank=True, help_text="List of file paths for multi-file imports")
    mapping = models.ForeignKey(
        'metadata.Mapping',
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Mapping configuration used for this import"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    
    # Ingestion configuration
    delimiter = models.CharField(max_length=5, default=';', help_text="CSV delimiter")
    has_quoted_fields = models.BooleanField(default=True)
    base_uri = models.CharField(max_length=512, default="http://arkumu.org/data")
    
    # Progress tracking
    total_rows = models.IntegerField(default=0, help_text="Total rows in CSV file")
    processed_rows = models.IntegerField(default=0, help_text="Number of rows processed")
    successful_rows = models.IntegerField(default=0, help_text="Number of rows successfully ingested")
    failed_rows = models.IntegerField(default=0, help_text="Number of rows that failed to ingest")
    skipped_datasets = models.IntegerField(default=0, help_text="Number of datasets skipped (empty or missing)")
    
    # SSE Progress fields
    progress_percentage = models.IntegerField(default=0)
    progress_message = models.CharField(max_length=255, blank=True)
    progress_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('complete', 'Complete'),
            ('error', 'Error'),
        ],
        default='pending'
    )
    
    # Results and error tracking
    ingestion_stats = models.JSONField(default=dict, blank=True, help_text="Detailed ingestion statistics")
    error_message = models.TextField(blank=True, help_text="Error message if ingestion failed")
    
    # Task tracking
    task_id = models.CharField(max_length=255, blank=True, help_text="Background task ID for polling")
    huey_task_id = models.CharField(max_length=255, blank=True, help_text="Huey task instance ID")

    class Meta:
        verbose_name = "Ingest Session"
        verbose_name_plural = "Ingest Sessions"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['organization', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['task_id']),
        ]

    def __str__(self):
        return f"Ingest {self.dataset_name} by {self.user.username} ({self.status})"
    
    def mark_started(self):
        """Mark the ingestion as started"""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.save()
    
    def mark_completed(self, stats=None):
        """Mark the ingestion as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if stats:
            self.ingestion_stats = stats
            # Update row counts from stats if available
            if 'total_rows' in stats:
                self.total_rows = stats['total_rows']
            if 'processed_rows' in stats:
                self.processed_rows = stats['processed_rows']
            if 'successful_rows' in stats:
                self.successful_rows = stats['successful_rows']
            if 'failed_rows' in stats:
                self.failed_rows = stats['failed_rows']
            if 'skipped_datasets' in stats:
                self.skipped_datasets = stats['skipped_datasets']
        self.save()
    
    def mark_failed(self, error_message=None):
        """Mark the ingestion as failed"""
        self.status = 'failed'
        if error_message:
            self.error_message = error_message
        self.save()
    
    def get_progress_percentage(self):
        """Calculate ingestion progress percentage"""
        if self.total_rows == 0:
            return 0
        return (self.processed_rows / self.total_rows) * 100
    
    def get_success_rate(self):
        """Calculate success rate of processed rows"""
        if self.processed_rows == 0:
            return 0
        return (self.successful_rows / self.processed_rows) * 100
    
    @property
    def progress_channel_id(self) -> str:
        """Get SSE channel ID for this session."""
        return f"import-{self.pk}"
    
    @property
    def file_name(self):
        """Extract filename from S3 object key"""
        return self.s3_object_key.split('/')[-1] if self.s3_object_key else ''
    
    @property
    def duration(self):
        """Calculate duration of the ingestion"""
        if not self.started_at:
            return None
        end_time = self.completed_at or timezone.now()
        return end_time - self.started_at 