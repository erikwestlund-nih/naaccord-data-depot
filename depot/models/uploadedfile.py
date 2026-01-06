from django.contrib.auth import get_user_model
from django.db import models

from depot.models import BaseModel, UploadType
from depot.mixins.timestamp import TimestampMixin

User = get_user_model()


class UploadedFile(BaseModel, TimestampMixin):
    uploader = models.ForeignKey(User, on_delete=models.CASCADE)
    storage_path = models.CharField(
        max_length=1024
    )  # e.g., 'uploads/2024/04/filename.csv'
    storage_disk = models.CharField(
        max_length=50,
        default='uploads',
        help_text='Which storage disk this file is stored on (uploads, data, attachments, etc.)'
    )
    filename = models.CharField(max_length=255)
    type = models.CharField(max_length=50, choices=UploadType.choices)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(max_length=64, null=True, blank=True)  # SHA-256 or MD5
    keep_until = models.DateTimeField(null=True, blank=True)

    # Additional metadata for file attachments
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=255, blank=True)

    # Pre-upload validation metadata (added for data quality)
    detected_encoding = models.CharField(max_length=50, blank=True, help_text='Detected file encoding (e.g., utf-8, latin-1)')
    has_bom = models.BooleanField(default=False, help_text='Whether file has UTF-8 BOM marker')
    has_crlf = models.BooleanField(default=False, help_text='Whether file has Windows line endings')
    line_count = models.IntegerField(null=True, blank=True, help_text='Number of lines in file')
    header_column_count = models.IntegerField(null=True, blank=True, help_text='Number of columns in header row')
    validation_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('passed', 'Passed'),
            ('failed', 'Failed')
        ],
        default='pending',
        help_text='Pre-upload validation status'
    )
    validation_errors = models.JSONField(
        default=list,
        blank=True,
        help_text='List of validation errors found during pre-upload check'
    )
    validation_performed_at = models.DateTimeField(null=True, blank=True, help_text='When validation was performed')

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.filename

    def get_storage(self):
        """Get the StorageManager instance for this file's storage disk."""
        from depot.storage.manager import StorageManager
        return StorageManager.get_storage(self.storage_disk)

    def get_absolute_path(self):
        """Get the absolute filesystem path for this file."""
        storage = self.get_storage()
        return storage.get_absolute_path(self.storage_path)

    @property
    def uploaded_ago(self):
        """Return human-readable time since upload."""
        from django.utils.timesince import timesince
        return f"{timesince(self.uploaded_at)} ago"
