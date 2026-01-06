from django.db import models
from django.utils import timezone
from depot.models import BaseModel


class DataTableFile(BaseModel):
    """Individual file within a data table, supporting versioning."""
    
    # Core relationships
    data_table = models.ForeignKey(
        'CohortSubmissionDataTable',
        on_delete=models.CASCADE,
        related_name='files'
    )
    
    # File identity
    name = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Custom name for this file (shown when multiple files exist)"
    )
    comments = models.TextField(blank=True)
    
    # Version tracking
    version = models.IntegerField(default=1)
    is_current = models.BooleanField(default=True, db_index=True)
    
    # File reference (latest version)
    uploaded_file = models.ForeignKey(
        'UploadedFile',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='data_table_files',
        help_text='Reference to the latest uploaded file version'
    )

    # File metadata (cached from uploaded_file for quick access)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, blank=True)
    
    # NAS storage paths
    raw_file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="NAS path for raw CSV/TSV file (as submitted by cohort)"
    )
    processed_file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="NAS path for processed CSV/TSV file (with mapping applied, for analyst use)"
    )
    duckdb_file_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="NAS path for DuckDB file (derived from processed file)"
    )
    duckdb_created_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When DuckDB file was created"
    )
    duckdb_conversion_error = models.TextField(
        blank=True,
        help_text="Error message if DuckDB conversion failed"
    )

    # Link to latest validation run (granular pipeline)
    latest_validation_run = models.ForeignKey(
        'ValidationRun',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='latest_files',
        help_text="Most recent granular validation run for this file"
    )
    
    # Upload tracking
    uploaded_by = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='uploaded_data_table_files'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Debug mode (skip processing/validation)
    debug_submission = models.BooleanField(
        default=False,
        help_text="If true, file is stored for debugging/chain of custody only - no processing or validation"
    )
    
    # Validation results (per file)
    validation_warnings = models.JSONField(default=dict, blank=True)
    patient_id_mismatches = models.JSONField(default=list, blank=True)
    warning_count = models.IntegerField(default=0)
    
    # Error explanation
    error_explanation = models.TextField(
        blank=True,
        help_text="Explanation of audit errors/warnings that couldn't be fixed"
    )

    # Patient ID validation rejection (privacy protection)
    rejection_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Reason why file was rejected (e.g., invalid patient IDs)"
    )
    rejection_details = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured rejection data including invalid IDs and metadata"
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When file was rejected"
    )

    # File cleanup verification
    files_cleaned_up = models.BooleanField(
        default=False,
        help_text="Whether all PHI files have been deleted after rejection"
    )
    cleanup_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When file cleanup was verified"
    )

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['data_table', 'is_current']),
            models.Index(fields=['data_table', 'version']),
        ]
        
    def __str__(self):
        if self.name:
            return f"{self.data_table} - {self.name} v{self.version}"
        return f"{self.data_table} - File {self.id} v{self.version}"
    
    def get_display_name(self):
        """Get display name for this file."""
        if self.name:
            return self.name
        return self.original_filename or f"File {self.id}"
    
    def create_new_version(self, user, uploaded_file):
        """Create a new version of this file."""
        # Mark current version as not current
        DataTableFile.objects.filter(
            data_table=self.data_table,
            id=self.id,
            is_current=True
        ).update(is_current=False)
        
        # Update this file with new version
        self.version += 1
        self.is_current = True
        self.uploaded_file = uploaded_file
        self.uploaded_by = user
        self.uploaded_at = timezone.now()
        
        # Update metadata from uploaded file
        if uploaded_file:
            self.original_filename = uploaded_file.filename
            # file_size is not stored in UploadedFile, keep from previous version
            # self.file_size is already set when creating the file
            self.file_hash = uploaded_file.file_hash
        
        # Clear validation from previous version
        self.validation_warnings = {}
        self.patient_id_mismatches = []
        self.warning_count = 0
        self.error_explanation = ''
        
        self.save()
        self.save_revision(user, 'new_version')
        
        # Clear parent table sign-off when file changes
        if self.data_table.signed_off:
            self.data_table.clear_sign_off()
        
        return self
    
    def get_all_versions(self):
        """Get all versions of this file."""
        # Since we're tracking versions on the same record, we need version history
        # This would require a separate model or using the revision system
        # For now, return just this file
        return DataTableFile.objects.filter(id=self.id).order_by('-version')
    
    def delete(self, using=None, keep_parents=False):
        """Override delete to also set is_current = False for file removal."""
        # Set is_current to False before soft deletion
        self.is_current = False
        # Call parent's soft delete method
        super().delete(using=using, keep_parents=keep_parents)

    def save(self, *args, **kwargs):
        """Override save to update parent data table status."""
        is_new = not self.pk
        super().save(*args, **kwargs)
        
        # Update parent data table status if this is the first file
        if is_new and self.data_table.status == 'not_started':
            self.data_table.update_status('in_progress')
    
