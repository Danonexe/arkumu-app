import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ImportTask(models.Model):
    """
    Tracks individual dataset import tasks within an IngestSession.
    Each dataset being imported gets its own ImportTask with unique task_id.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Link to parent session
    ingest_session = models.ForeignKey(
        'IngestSession',
        on_delete=models.CASCADE,
        related_name='import_tasks',
        help_text="Parent ingest session this task belongs to"
    )
    
    # Dataset information
    dataset_name = models.CharField(
        max_length=255,
        help_text="Name of the dataset being imported"
    )
    file_path = models.CharField(
        max_length=512,
        help_text="S3 file path for this dataset"
    )
    
    # Task tracking
    task_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique task ID for progress tracking"
    )
    huey_task_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Huey task instance ID"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    rows_processed = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'importer_import_task'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['task_id']),
            models.Index(fields=['ingest_session', 'status']),
        ]
    
    def __str__(self):
        return f"ImportTask {self.dataset_name} ({self.status})"