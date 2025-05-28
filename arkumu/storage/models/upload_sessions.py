from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone

class UploadSession(models.Model):
    """Represents a batch upload session"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Use this instead of User directly
        on_delete=models.CASCADE
    )
    folder_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('initialized', 'Initialized'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='initialized'
    )
    total_files = models.IntegerField(default=0)
    total_size_bytes = models.BigIntegerField(default=0)
    
    # New fields for import tracking
    import_type = models.CharField(
        max_length=20,
        choices=[
            ('csv_import', 'CSV Import'),
            ('file_upload', 'File Upload'),
            ('zip_import', 'ZIP Import'),
        ],
        default='csv_import'
    )
    institution = models.CharField(max_length=255, blank=True)
    base_uri = models.CharField(max_length=512, blank=True)
    s3_bucket = models.CharField(max_length=255, blank=True)
    s3_base_path = models.CharField(max_length=512, blank=True)
    import_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Upload Session"
        verbose_name_plural = "Upload Sessions"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['import_type']),
        ]

    def __str__(self):
        return f"Upload {self.id} by {self.user.username} ({self.status})"
    
    def mark_completed(self, stats=None):
        """Mark the session as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if stats:
            self.import_stats = stats
        self.save()
    
    def mark_failed(self, error_message=None):
        """Mark the session as failed"""
        self.status = 'failed'
        if error_message:
            self.import_stats = {'error': error_message}
        self.save()
    
    def get_progress(self):
        """Calculate upload progress percentage"""
        completed = self.files.filter(status='completed').count()
        if self.total_files == 0:
            return 0
        return (completed / self.total_files) * 100
    
    @classmethod
    def create_from_import(cls, user, folder_name, import_type='csv_import', 
                          institution='DEFAULT', base_uri='http://arkumu.org/data',
                          s3_bucket=None, s3_base_path=None):
        """Create an upload session for an import operation"""
        session = cls.objects.create(
            user=user,
            folder_name=folder_name,
            import_type=import_type,
            institution=institution,
            base_uri=base_uri,
            s3_bucket=s3_bucket or '',
            s3_base_path=s3_base_path or '',
            status='in_progress'
        )
        return session 