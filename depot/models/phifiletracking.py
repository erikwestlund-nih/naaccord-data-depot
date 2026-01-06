from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from depot.models.basemodel import BaseModel
import socket


class PHIFileTracking(BaseModel):
    """
    Audit log for all PHI file operations.
    Tracks every movement of PHI data to ensure complete accountability
    and enable cleanup verification.
    """
    
    # Action types for file operations
    ACTION_CHOICES = [
        # NAS operations
        ('nas_raw_created', 'Raw file created on NAS'),
        ('nas_raw_deleted', 'Raw file deleted from NAS'),
        ('nas_duckdb_created', 'DuckDB file created on NAS'),
        ('nas_duckdb_deleted', 'DuckDB file deleted from NAS'),
        ('nas_report_created', 'Report created on NAS'),
        ('nas_report_deleted', 'Report deleted from NAS'),
        
        # Workspace operations
        ('work_copy_created', 'File copied to workspace'),
        ('work_copy_deleted', 'File deleted from workspace'),
        
        # Conversion operations
        ('conversion_started', 'File conversion started'),
        ('conversion_completed', 'File conversion completed'),
        ('conversion_failed', 'File conversion failed'),
        
        # Extraction operations
        ('patient_id_extraction_started', 'Patient ID extraction started'),
        ('patient_id_extraction_completed', 'Patient ID extraction completed'),
        ('patient_id_extraction_failed', 'Patient ID extraction failed'),
        
        # Streaming operations
        ('file_uploaded_via_stream', 'File uploaded via streaming'),
        ('file_uploaded_chunked', 'File uploaded in chunks'),
        ('file_downloaded_via_stream', 'File downloaded via streaming'),
        ('file_deleted_via_api', 'File deleted via internal API'),
        ('prefix_deleted_via_api', 'Prefix deleted via internal API'),
        ('scratch_cleanup', 'Scratch directory cleanup'),
        ('stream_started', 'Streaming operation started'),
        ('stream_completed', 'Streaming operation completed'),
        ('stream_failed', 'Streaming operation failed'),
        ('precheck_upload_staged', 'Precheck validation upload staged'),
    ]
    
    FILE_TYPE_CHOICES = [
        ('raw_csv', 'Raw CSV file'),
        ('raw_tsv', 'Raw TSV file'),
        ('duckdb', 'DuckDB database'),
        ('report_html', 'HTML report'),
        ('temp_working', 'Temporary working file'),
        ('patient_data', 'Patient data file'),
        ('workspace_directory', 'Workspace directory'),
        ('attachment', 'File attachment'),
        ('submission_attachment', 'Submission attachment'),
        ('unknown', 'Unknown file type'),
    ]
    
    # Core tracking fields
    cohort = models.ForeignKey(
        'Cohort',
        on_delete=models.CASCADE,
        related_name='phi_file_operations',
        null=True,
        blank=True,
        help_text="Cohort this file belongs to (null for system operations)"
    )
    user = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='phi_file_operations'
    )
    
    # Operation details
    action = models.CharField(
        max_length=50,
        choices=ACTION_CHOICES,
        db_index=True
    )
    file_path = models.CharField(
        max_length=500,
        help_text="Full path to the file"
    )
    file_type = models.CharField(
        max_length=30,
        choices=FILE_TYPE_CHOICES
    )
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA256 hash of file contents"
    )
    
    # Polymorphic reference to related object (Audit, DataTableFile, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if operation failed"
    )
    
    # Server tracking
    server_hostname = models.CharField(
        max_length=255,
        default='',
        help_text="Hostname of server where operation occurred"
    )
    
    # Cleanup verification
    cleaned_up = models.BooleanField(
        default=False,
        help_text="Whether temporary file has been cleaned up"
    )
    cleanup_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When cleanup was verified"
    )
    cleanup_verified_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_cleanups'
    )
    
    # Enhanced tracking for cleanup management
    cleanup_required = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this file needs to be cleaned up"
    )
    cleanup_attempted_count = models.IntegerField(
        default=0,
        help_text="Number of cleanup attempts made"
    )
    parent_process_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Process ID that created this file (for orphan detection)"
    )
    expected_cleanup_by = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this file should be cleaned up"
    )
    purpose_subdirectory = models.CharField(
        max_length=50,
        blank=True,
        help_text="Subdirectory for organization (e.g., 'audit', 'upload')"
    )
    
    # Streaming-specific fields
    server_role = models.CharField(
        max_length=20,
        blank=True,
        help_text="Role of server (web/services/testing)"
    )
    stream_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When streaming operation started"
    )
    stream_complete = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When streaming operation completed"
    )
    bytes_transferred = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Number of bytes transferred in streaming operation"
    )
    cleanup_scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this file is scheduled for cleanup"
    )
    metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional metadata for tracking"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cohort', 'action']),
            models.Index(fields=['file_path']),
            models.Index(fields=['cleaned_up', 'action']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['cleanup_required', 'created_at'], name='idx_cleanup_pending'),
        ]
        verbose_name = 'PHI File Tracking'
        verbose_name_plural = 'PHI File Tracking Records'
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.file_path}"
    
    def save(self, *args, **kwargs):
        # Auto-populate hostname if not set
        if not self.server_hostname:
            self.server_hostname = socket.gethostname()
        super().save(*args, **kwargs)
    
    @classmethod
    def log_operation(cls, cohort, user, action, file_path,
                      file_type='raw_csv', file_size=None, file_hash='',
                      content_object=None, error_message='', metadata=None):
        """
        Convenience method to log a file operation.
        """
        return cls.objects.create(
            cohort=cohort,
            user=user,
            action=action,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            file_hash=file_hash,
            content_object=content_object,
            error_message=error_message,
            metadata=metadata,
        )
    
    @classmethod
    def get_uncleaned_workspace_files(cls):
        """
        Get all workspace files that haven't been cleaned up.
        """
        return cls.objects.filter(
            action='work_copy_created',
            cleaned_up=False
        ).exclude(
            file_path__in=cls.objects.filter(
                action='work_copy_deleted'
            ).values_list('file_path', flat=True)
        )
    
    def mark_cleaned_up(self, user=None):
        """
        Mark this file as cleaned up and verified.
        """
        from django.utils import timezone
        self.cleaned_up = True
        self.cleanup_verified_at = timezone.now()
        self.cleanup_verified_by = user
        self.save()
    
    @property
    def is_cleanup_overdue(self):
        """Check if cleanup is overdue."""
        from django.utils import timezone
        if not self.expected_cleanup_by:
            return False
        if self.cleaned_up:
            return False
        return timezone.now() > self.expected_cleanup_by
    
    @classmethod
    def get_overdue_cleanups(cls):
        """Get all files that should have been cleaned up."""
        from django.utils import timezone
        return cls.objects.filter(
            cleaned_up=False,
            expected_cleanup_by__lt=timezone.now()
        ).exclude(
            action__in=['nas_raw_created', 'nas_duckdb_created', 'nas_report_created']
        )
