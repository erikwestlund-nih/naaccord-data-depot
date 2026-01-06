from django.db import models
from django.core.validators import MinValueValidator
from depot.models.basemodel import BaseModel


class SubmissionPatientIDs(BaseModel):
    """
    Stores the list of patient IDs extracted from the patient file
    for a protocol year submission. This is used for cross-file validation
    to ensure all files in a submission only contain valid patient IDs.
    """
    
    submission = models.OneToOneField(
        'CohortSubmission',
        on_delete=models.CASCADE,
        related_name='patient_ids_record'
    )
    
    # Store patient IDs as JSON list for flexibility
    # Example: ["PAT001", "PAT002", "PAT003"]
    patient_ids = models.JSONField(
        default=list,
        help_text="List of unique patient IDs from the patient file"
    )
    
    # Denormalized count for quick access
    patient_count = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Total number of unique patient IDs"
    )
    
    # Tracking fields
    extracted_at = models.DateTimeField(
        help_text="When the patient IDs were extracted"
    )
    extracted_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='patient_id_extractions'
    )
    
    # Error handling
    extraction_error = models.TextField(
        blank=True,
        help_text="Any errors encountered during extraction"
    )
    has_duplicates = models.BooleanField(
        default=False,
        help_text="Whether duplicate IDs were found and removed"
    )
    duplicate_count = models.IntegerField(
        default=0,
        help_text="Number of duplicate IDs that were removed"
    )
    
    # Source file reference
    source_file = models.ForeignKey(
        'DataTableFile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patient_id_extraction',
        help_text="The patient file these IDs were extracted from"
    )
    
    class Meta:
        ordering = ['-extracted_at']
        indexes = [
            models.Index(fields=['submission']),
            models.Index(fields=['extracted_at']),
        ]
        verbose_name = 'Submission Patient IDs'
        verbose_name_plural = 'Submission Patient IDs'
    
    def __str__(self):
        return f"{self.submission} - {self.patient_count} patients"
    
    def get_patient_ids_set(self):
        """Return patient IDs as a Python set for efficient lookups."""
        return set(self.patient_ids)
    
    def validate_patient_id(self, patient_id):
        """Check if a patient ID is valid for this submission."""
        return patient_id in self.patient_ids
    
    def get_invalid_patient_ids(self, ids_to_check):
        """
        Given a list of patient IDs, return which ones are NOT in our valid list.
        """
        valid_ids = self.get_patient_ids_set()
        return [pid for pid in ids_to_check if pid not in valid_ids]
    
    def update_from_file(self, file_path, user):
        """
        Update patient IDs from a new file upload.
        This will be called by the extraction service.
        """
        from django.utils import timezone
        # This will be implemented by the extraction service
        # Just updating metadata here
        self.extracted_at = timezone.now()
        self.extracted_by = user
        self.save()
    
    @classmethod
    def create_or_update_for_submission(cls, submission, patient_ids, user, source_file=None):
        """
        Create or update patient IDs for a submission.
        Handles deduplication and counting.
        """
        from django.utils import timezone
        
        # Deduplicate patient IDs
        unique_ids = list(set(patient_ids))
        duplicate_count = len(patient_ids) - len(unique_ids)
        
        # Get or create the record
        record, created = cls.objects.get_or_create(
            submission=submission,
            defaults={
                'patient_ids': unique_ids,
                'patient_count': len(unique_ids),
                'extracted_at': timezone.now(),
                'extracted_by': user,
                'has_duplicates': duplicate_count > 0,
                'duplicate_count': duplicate_count,
                'source_file': source_file,
            }
        )
        
        if not created:
            # Update existing record
            record.patient_ids = unique_ids
            record.patient_count = len(unique_ids)
            record.extracted_at = timezone.now()
            record.extracted_by = user
            record.has_duplicates = duplicate_count > 0
            record.duplicate_count = duplicate_count
            record.source_file = source_file
            # Clear any previous extraction error on successful update
            record.extraction_error = ''
            record.save()
        
        return record