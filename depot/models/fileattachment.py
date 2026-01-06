from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from depot.models import BaseModel


class FileAttachment(BaseModel):
    """
    Polymorphic model for arbitrary file attachments.
    Can be attached to CohortSubmission or CohortSubmissionDataTable.
    These files don't go through audit processing.
    """
    
    # Polymorphic relationship
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of entity this attachment belongs to"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the entity this attachment belongs to"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # File details
    name = models.CharField(
        max_length=255,
        help_text="Display name for this attachment"
    )
    comments = models.TextField(
        blank=True,
        help_text="Optional comments about this attachment"
    )
    
    # File reference
    uploaded_file = models.ForeignKey(
        'UploadedFile',
        on_delete=models.CASCADE,
        related_name='attachments',
        help_text='Reference to the uploaded file in storage'
    )
    
    # Upload tracking
    uploaded_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='uploaded_attachments'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    # File metadata (cached for quick access)
    original_filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_type = models.CharField(
        max_length=255,
        blank=True,
        help_text="MIME type of the file"
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['uploaded_at']),
        ]
        
    def __str__(self):
        return f"Attachment: {self.name}"
    
    def get_display_name(self):
        """Get display name for this attachment."""
        return self.name or self.original_filename
    
    def save(self, *args, **kwargs):
        """Override save to cache file metadata."""
        if self.uploaded_file and not self.original_filename:
            self.original_filename = self.uploaded_file.original_filename
            self.file_size = self.uploaded_file.file_size
            # Truncate file_type if it's too long (max 100 chars)
            file_type = self.uploaded_file.content_type or ''
            if len(file_type) > 100:
                file_type = file_type[:100]
            self.file_type = file_type
        super().save(*args, **kwargs)
        
    @classmethod
    def get_for_entity(cls, entity):
        """Get all attachments for a given entity (submission or data table)."""
        content_type = ContentType.objects.get_for_model(entity)
        # No need to filter deleted_at - the SoftDeletableManager handles it automatically
        return cls.objects.filter(
            content_type=content_type,
            object_id=entity.id
        )
    
    @classmethod
    def create_for_entity(cls, entity, uploaded_file, user, name='', comments=''):
        """Create an attachment for a given entity."""
        content_type = ContentType.objects.get_for_model(entity)

        # Truncate file_type if it's too long (max 100 chars)
        file_type = uploaded_file.content_type or ''
        if len(file_type) > 100:
            file_type = file_type[:100]

        attachment = cls.objects.create(
            content_type=content_type,
            object_id=entity.id,
            uploaded_file=uploaded_file,
            uploaded_by=user,
            name=name or uploaded_file.original_filename,
            comments=comments,
            original_filename=uploaded_file.original_filename,
            file_size=uploaded_file.file_size,
            file_type=file_type
        )
        attachment.save_revision(user, 'created')
        return attachment