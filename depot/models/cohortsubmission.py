from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from depot.models import BaseModel


class CohortSubmission(BaseModel):
    """Tracks a complete submission for a cohort in a specific wave."""
    
    # Core relationships
    protocol_year = models.ForeignKey(
        'ProtocolYear', 
        on_delete=models.CASCADE,
        related_name='cohort_submissions'
    )
    cohort = models.ForeignKey(
        'Cohort',
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    started_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='started_submissions'
    )
    
    # Status tracking
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('signed_off', 'Signed Off'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True
    )
    
    # Patient ID tracking
    patient_ids = models.JSONField(default=list, blank=True)
    patient_file_processed = models.BooleanField(default=False)

    # Patient ID validation settings
    VALIDATION_MODE_CHOICES = [
        ('permissive', 'Allow with warnings'),
        ('strict', 'Block if invalid IDs found'),
    ]
    validation_mode = models.CharField(
        max_length=20,
        choices=VALIDATION_MODE_CHOICES,
        default='permissive',
        help_text="How to handle invalid patient IDs"
    )
    validation_threshold = models.IntegerField(
        default=0,
        help_text="Max invalid IDs allowed before blocking (0 = no tolerance in strict mode)"
    )
    
    # Submission notes and tracking
    notes = models.TextField(blank=True, help_text="General notes about this submission")
    
    # Final sign-off
    final_comments = models.TextField(blank=True)
    final_acknowledged = models.BooleanField(default=False)
    final_acknowledged_by = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='acknowledged_submissions'
    )
    final_acknowledged_at = models.DateTimeField(null=True, blank=True)
    
    # New sign-off and closure tracking
    signed_off = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp when user confirmed all data reviewed and errors corrected"
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when submission was finalized"
    )
    
    # Reopening tracking
    reopened_reason = models.TextField(
        blank=True,
        help_text="Reason provided by admin for reopening submission"
    )
    reopened_by = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reopened_submissions'
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    
    # Generic relation for attachments
    attachments = GenericRelation('FileAttachment')
    
    class Meta:
        unique_together = ['protocol_year', 'cohort']
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.cohort.name} - {self.protocol_year.name} ({self.status})"
    
    def can_upload_non_patient_files(self):
        """Check if non-patient files can be uploaded."""
        return self.patient_file_processed
    
    def get_patient_data_table(self):
        """Get the patient data table for this submission."""
        from depot.models import DataFileType, CohortSubmissionDataTable
        patient_type = DataFileType.objects.filter(name__iexact='patient').first()
        if not patient_type:
            return None
        return self.data_tables.filter(data_file_type=patient_type).first()
    
    def has_patient_file(self):
        """Check if this submission has a patient file uploaded."""
        patient_table = self.get_patient_data_table()
        return patient_table and patient_table.has_files()
    
    def get_patient_stats(self):
        """
        Get patient statistics for display.

        Returns:
            dict with 'count', 'example_ids', and 'latest_file' or None if no patient data
        """
        # Check if we have patient_ids_record
        if hasattr(self, 'patient_ids_record'):
            patient_record = self.patient_ids_record
            if patient_record and patient_record.patient_ids:
                # Get the patient table to find the latest file
                patient_table = self.get_patient_data_table()
                latest_file = None
                if patient_table:
                    latest_file = patient_table.files.filter(is_current=True).order_by('-created_at').first()

                # Get first 3-4 example IDs
                example_ids = patient_record.patient_ids[:4]
                return {
                    'count': patient_record.patient_count,
                    'example_ids': example_ids,
                    'has_duplicates': patient_record.has_duplicates,
                    'duplicate_count': patient_record.duplicate_count if patient_record.has_duplicates else 0,
                    'latest_file': latest_file
                }
        return None
    
    def can_accept_files(self, user):
        """Check if this submission can accept new file uploads from the given user."""
        # Cannot upload to signed-off or closed submissions
        if self.status in ['signed_off', 'closed']:
            return False
        
        # Check user permissions
        from depot.permissions import SubmissionPermissions
        return SubmissionPermissions.can_edit(user, self)
    
    def check_patient_file_requirement(self, file_type):
        """
        Check if this is a patient file and if patient file exists.
        
        Args:
            file_type: DataFileType instance
            
        Returns:
            tuple: (is_patient_table, patient_file_exists)
        """
        is_patient_table = file_type.name.lower() == 'patient'
        
        if is_patient_table:
            return True, False  # Patient table doesn't need patient file
        
        # For non-patient tables, check if patient file exists
        return False, self.has_patient_file()
    
    def mark_signed_off(self, user):
        """Mark submission as signed off and move files to permanent storage."""
        self.status = 'signed_off'
        self.final_acknowledged = True
        self.final_acknowledged_by = user
        self.final_acknowledged_at = timezone.now()
        self.signed_off = timezone.now()  # Set the new signed_off timestamp
        self.closed_at = timezone.now()   # Also close the submission
        self.save()
        # Revision will be tracked automatically via RevisionMixin
        self.save_revision(user, 'updated')

        # Move files from uploads to permanent storage
        self._move_files_to_permanent_storage(user)

    def _move_files_to_permanent_storage(self, user):
        """Move all uploaded files from uploads disk to permanent data storage."""
        import logging
        from depot.storage.manager import StorageManager
        from depot.models import PHIFileTracking

        logger = logging.getLogger(__name__)
        uploads_storage = StorageManager.get_storage('uploads')
        data_storage = StorageManager.get_storage('data')

        # Get all uploaded files for this submission
        from depot.models import UploadedFile
        uploaded_files = UploadedFile.objects.filter(
            data_table_files__data_table__submission=self,
            deleted_at__isnull=True
        ).distinct()

        for uploaded_file in uploaded_files:
            try:
                old_path = uploaded_file.storage_path
                # Keep the same relative path, just move to different disk
                new_path = old_path

                logger.info(f"Moving file from uploads:{old_path} to data:{new_path}")

                # Read from uploads storage
                content = uploads_storage.read(old_path)

                # Write to data storage
                data_storage.save(new_path, content)

                # Track old file deletion in uploads
                PHIFileTracking.log_operation(
                    cohort=self.cohort,
                    user=user,
                    action='file_moved_from_uploads',
                    file_path=old_path,
                    file_type='raw_csv',
                    content_object=uploaded_file
                )

                # Track new file creation in data
                PHIFileTracking.log_operation(
                    cohort=self.cohort,
                    user=user,
                    action='file_moved_to_data',
                    file_path=new_path,
                    file_type='raw_csv',
                    content_object=uploaded_file
                )

                # Delete from uploads storage
                uploads_storage.delete(old_path)

                # Update the database record to point to data storage
                uploaded_file.storage_disk = 'data'
                uploaded_file.save(update_fields=['storage_disk'])

                logger.info(f"Successfully moved file: {old_path}")

            except Exception as e:
                logger.error(f"Error moving file {uploaded_file.storage_path}: {str(e)}")
                # Continue with other files even if one fails
                continue

    def reopen(self, user, reason):
        """Reopen a closed submission."""
        if not user.is_superuser:
            raise ValueError("Only administrators can reopen submissions")
        
        self.status = 'in_progress'
        self.closed_at = None
        self.reopened_reason = reason
        self.reopened_by = user
        self.reopened_at = timezone.now()
        self.save()
        self.save_revision(user, 'updated')
    
    def update_status(self, new_status, user):
        """Update status with revision tracking."""
        old_status = self.status
        self.status = new_status
        self.save()
        if user:
            self.save_revision(user, 'updated')