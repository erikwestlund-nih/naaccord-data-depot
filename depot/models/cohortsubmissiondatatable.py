import os
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from depot.models import BaseModel


class CohortSubmissionDataTable(BaseModel):
    """Represents a data table (patient, laboratory, etc.) within a submission."""
    
    # Status choices
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),  # File rejected due to privacy violation (invalid patient IDs)
        ('not_available', 'Not Available'),
    ]
    
    # Core relationships
    submission = models.ForeignKey(
        'CohortSubmission',
        on_delete=models.CASCADE,
        related_name='data_tables'
    )
    data_file_type = models.ForeignKey(
        'DataFileType',
        on_delete=models.CASCADE,
        related_name='submission_data_tables'
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='not_started',
        help_text="Current status of this data table in the submission"
    )
    
    # Skip functionality
    is_skipped = models.BooleanField(default=False)
    skip_reason = models.TextField(blank=True)
    skipped_by = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='skipped_data_tables'
    )
    skipped_at = models.DateTimeField(null=True, blank=True)
    
    # Availability flags
    not_available = models.BooleanField(
        default=False,
        help_text="Indicates cohort doesn't have this data"
    )
    not_required = models.BooleanField(
        default=False,
        help_text="Indicates this data table is not required for this cohort"
    )
    
    # Sign-off tracking (at table level, not individual files)
    signed_off = models.BooleanField(default=False)
    signed_off_by = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='signed_off_data_tables'
    )
    signed_off_at = models.DateTimeField(null=True, blank=True)
    sign_off_comments = models.TextField(blank=True)
    
    # Validation results (aggregated from all files)
    validation_warnings = models.JSONField(default=dict, blank=True)
    patient_id_mismatches = models.JSONField(default=list, blank=True)
    warning_count = models.IntegerField(default=0)
    
    # Generic relation for attachments
    attachments = GenericRelation('FileAttachment')
    
    class Meta:
        ordering = ['data_file_type__order']
        unique_together = [['submission', 'data_file_type']]
        indexes = [
            models.Index(fields=['submission', 'data_file_type']),
            models.Index(fields=['submission', 'status']),
        ]
        
    def __str__(self):
        return f"{self.submission} - {self.data_file_type.label}"
    
    def get_status_display_text(self):
        """Get human-readable status of the data table."""
        if self.is_skipped:
            return "Skipped"
        elif self.not_available:
            return "Not Available"
        elif self.signed_off:
            return "Signed Off"
        else:
            return self.get_status_display()
    
    def mark_signed_off(self, user, comments=''):
        """Mark data table as signed off with revision tracking."""
        self.signed_off = True
        self.signed_off_by = user
        self.signed_off_at = timezone.now()
        if comments:
            self.sign_off_comments = comments
        self.save()
        self.save_revision(user, 'signed_off')
    
    def clear_sign_off(self):
        """Clear sign-off when files change."""
        self.signed_off = False
        self.signed_off_at = None
        self.signed_off_by = None
        self.save()
    
    def mark_skipped(self, user, reason):
        """Mark data table as skipped with revision tracking."""
        self.is_skipped = True
        self.skip_reason = reason
        self.skipped_by = user
        self.skipped_at = timezone.now()
        self.status = 'not_available'
        self.save()
        self.save_revision(user, 'skipped')
    
    def mark_not_available(self, user, reason=''):
        """Mark data table as not available (site doesn't collect this data)."""
        self.not_available = True
        self.status = 'not_available'
        if reason:
            self.skip_reason = reason
            self.skipped_by = user
            self.skipped_at = timezone.now()
        self.save()
        self.save_revision(user, 'marked_not_available')
    
    def clear_not_available(self, user):
        """Clear the not available status."""
        self.not_available = False
        if self.status == 'not_available' and not self.is_skipped:
            self.status = 'not_started'
        self.save()
        self.save_revision(user, 'cleared_not_available')
    
    def update_status(self, new_status, user=None):
        """Update data table status."""
        old_status = self.status
        self.status = new_status
        
        # Clear sign-off if status changes after sign-off
        if old_status == 'completed' and new_status != 'completed' and self.signed_off:
            self.clear_sign_off()
        
        self.save()
        if user:
            self.save_revision(user, 'status_updated')
    
    def has_files(self):
        """Check if this data table has any files uploaded."""
        return self.files.filter(uploaded_file__isnull=False).exists()
    
    def can_upload_file(self, user):
        """Check if user can upload a file to this data table."""
        # Check if submission accepts files
        if not self.submission.can_accept_files(user):
            return False, "Submission is closed or user lacks permission"
        
        # Check if this is a patient table
        is_patient_table = self.data_file_type.name.lower() == 'patient'
        
        # For non-patient tables, check if patient file exists
        if not is_patient_table and not self.submission.has_patient_file():
            return False, "Patient file must be uploaded first"
        
        # Check for duplicate patient files
        if is_patient_table:
            existing_patient_table = self.submission.data_tables.filter(
                data_file_type__name__iexact='patient'
            ).exclude(id=self.id).first()
            
            if existing_patient_table and existing_patient_table.has_files():
                return False, "A patient file already exists for this submission"
        
        return True, None
    
    def requires_patient_file(self):
        """Check if this data table requires a patient file to be uploaded first."""
        return self.data_file_type.name.lower() != 'patient'
    
    def validate_file_upload(self, uploaded_file, user):
        """
        Comprehensive validation for file upload.
        Returns (is_valid, error_message)
        """
        # Check basic upload permission
        can_upload, error = self.can_upload_file(user)
        if not can_upload:
            return False, error
        
        # Check for empty files
        if uploaded_file.size == 0:
            return False, "Empty files are not allowed"

        # File size limit
        max_size = 3 * 1024 * 1024 * 1024  # 3GB in bytes
        if uploaded_file.size > max_size:
            return False, f"File size exceeds maximum of {max_size // (1024*1024)}MB"
        
        # Check file extension matches expected types
        allowed_extensions = ['.csv', '.tsv', '.txt']
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in allowed_extensions:
            return False, f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
        
        return True, None
    
    def get_current_files(self):
        """Get all current version files for this data table."""
        import logging
        logger = logging.getLogger(__name__)

        files = self.files.filter(is_current=True).order_by('created_at')
        logger.info(f"get_current_files for table {self.id} ({self.data_file_type.name}): found {files.count()} files")
        for f in files:
            logger.info(f"  - File {f.id}: version={f.version}, is_current={f.is_current}, created={f.created_at}")

        return files
    
    def aggregate_validation_warnings(self):
        """Aggregate validation warnings from all files."""
        all_warnings = {}
        all_mismatches = []
        total_count = 0
        
        for file in self.get_current_files():
            if file.validation_warnings:
                all_warnings[file.name or f"File {file.id}"] = file.validation_warnings
                total_count += file.warning_count
            if file.patient_id_mismatches:
                all_mismatches.extend(file.patient_id_mismatches)
        
        self.validation_warnings = all_warnings
        self.patient_id_mismatches = list(set(all_mismatches))  # Unique mismatches
        self.warning_count = total_count
        self.save()
    
    @property
    def has_review(self):
        """Check if this table has a review record."""
        return hasattr(self, 'review')
    
    @property
    def is_reviewed(self):
        """Check if this table has been reviewed."""
        return self.has_review and self.review.is_reviewed
    
    @property
    def review_status(self):
        """Get the review status display."""
        if not self.has_review:
            return "No Review"
        return self.review.review_status_display
    
    @property
    def has_validation_issues(self):
        """Check if this table has any validation issues."""
        if self.has_review:
            return self.review.has_validation_errors or self.review.has_validation_warnings
        return self.warning_count > 0
    
    @property
    def validation_report_viewed(self):
        """Check if the validation report has been viewed."""
        if self.has_review:
            return self.review.validation_report_viewed
        return False
    
    def get_or_create_review(self):
        """Get or create the review record for this table."""
        from depot.models.datatablereview import DataTableReview
        review, created = DataTableReview.objects.get_or_create(
            data_table=self,
            defaults={
                'has_validation_warnings': self.warning_count > 0,
                'issue_count': self.warning_count
            }
        )
        return review

    def get_patient_validation_metrics(self):
        """
        Calculate patient ID validation metrics for this data table.
        Returns a dictionary with validation statistics including per-file breakdowns.
        """
        from depot.models import DataTableFilePatientIDs

        # Get patient IDs from the submission's patient file
        submission = self.submission

        # Check if submission has patient_ids_record (related model) or patient_ids (JSON field)
        if hasattr(submission, 'patient_ids_record') and submission.patient_ids_record:
            # Use the related CohortSubmissionPatientIDs model
            patient_file_ids = set(submission.patient_ids_record.patient_ids) if submission.patient_ids_record.patient_ids else set()
        else:
            # Use the JSONField directly
            patient_file_ids = set(submission.patient_ids) if submission.patient_ids else set()

        total_patient_file = len(patient_file_ids)

        # Get patient ID records for current files with their file info
        patient_records = DataTableFilePatientIDs.objects.filter(
            data_file__data_table=self,
            data_file__is_current=True
        ).select_related('data_file')

        # Calculate per-file metrics
        file_metrics = []
        all_uploaded_ids = []

        for record in patient_records:
            file_patient_ids = set(record.patient_ids) if record.patient_ids else set()
            file_total = len(file_patient_ids)

            if file_total > 0:
                all_uploaded_ids.extend(file_patient_ids)

                # Calculate matches for this file
                file_matching = patient_file_ids & file_patient_ids if patient_file_ids else set()
                file_out_of_bounds = file_patient_ids - patient_file_ids if patient_file_ids else file_patient_ids

                file_matching_count = len(file_matching)
                file_out_of_bounds_count = len(file_out_of_bounds)

                # Calculate percentages for this file
                file_matching_percent = round((file_matching_count / file_total * 100), 1) if file_total > 0 else 0
                file_out_of_bounds_percent = round((file_out_of_bounds_count / file_total * 100), 1) if file_total > 0 else 0

                file_metrics.append({
                    'file_id': record.data_file.id,
                    'file_name': record.data_file.name or record.data_file.original_filename or f"File {record.data_file.id}",
                    'total': file_total,
                    'matching_count': file_matching_count,
                    'matching_percent': file_matching_percent,
                    'out_of_bounds_count': file_out_of_bounds_count,
                    'out_of_bounds_percent': file_out_of_bounds_percent,
                    'validation_status': record.validation_status
                })

        # Calculate aggregate metrics
        uploaded_set = set(all_uploaded_ids)
        total_uploaded = len(uploaded_set)

        # Calculate matches and out of bounds for aggregate
        matching = patient_file_ids & uploaded_set if patient_file_ids else set()
        out_of_bounds = uploaded_set - patient_file_ids if patient_file_ids else uploaded_set

        matching_count = len(matching)
        out_of_bounds_count = len(out_of_bounds)

        # Sample IDs for preview
        sample_ids = sorted(uploaded_set)[:5] if uploaded_set else []

        # Calculate percentages
        # Coverage: how much of the patient file is covered by uploads
        coverage_percent = round((matching_count / total_patient_file * 100), 1) if total_patient_file > 0 else 0
        # Validation: what percentage of uploaded IDs are valid
        validation_percent = round((matching_count / total_uploaded * 100), 1) if total_uploaded > 0 else 0
        # Invalid: what percentage of uploaded IDs are invalid
        out_of_bounds_percent = round((out_of_bounds_count / total_uploaded * 100), 1) if total_uploaded > 0 else 0

        return {
            'total_patient_file': total_patient_file,
            'total_uploaded': total_uploaded,
            'matching_count': matching_count,
            'matching_percent': validation_percent,  # Keep for backwards compatibility but this is validation %
            'coverage_percent': coverage_percent,  # New: how much of patient file is covered
            'validation_percent': validation_percent,  # New: what % of uploads are valid
            'out_of_bounds_count': out_of_bounds_count,
            'out_of_bounds_percent': out_of_bounds_percent,
            'has_validation': total_uploaded > 0,
            'file_metrics': file_metrics,  # Per-file breakdown
            'sample_ids': sample_ids,
        }
