"""
Precheck Validation Model

Tracks precheck validation runs with progressive status updates.
Used for the precheck validation tool that provides detailed file analysis.
"""

from django.db import models
from django.contrib.auth import get_user_model
from depot.models.cohort import Cohort
from depot.models.datafiletype import DataFileType

User = get_user_model()


class PrecheckValidation(models.Model):
    """
    Tracks precheck validation runs with progressive status updates.

    Precheck validation is a diagnostic tool for problematic files. It provides:
    - File metadata analysis (size, encoding, BOM, hash)
    - CSV integrity checking (row-by-row column count validation)
    - Full validation against data definitions

    Status progression:
    pending → analyzing_metadata → checking_integrity → validating → completed/failed
    """

    # Identification (uses Django default AutoField for id)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='precheck_validations')
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name='precheck_validations')
    data_file_type = models.ForeignKey(
        DataFileType,
        on_delete=models.CASCADE,
        related_name='precheck_validations'
    )
    cohort_submission = models.ForeignKey(
        'CohortSubmission',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='precheck_validations',
        help_text='Optional submission to validate patient IDs against'
    )

    # File tracking
    original_filename = models.CharField(max_length=500)
    file_path = models.CharField(max_length=1000, help_text='Path in scratch storage')
    file_size = models.BigIntegerField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, null=True, blank=True, help_text='SHA256 hash')

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('analyzing_metadata', 'Analyzing Metadata'),
        ('checking_integrity', 'Checking CSV Integrity'),
        ('validating', 'Running Validation'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending', db_index=True)
    current_stage = models.CharField(max_length=100, null=True, blank=True)
    progress_percent = models.IntegerField(default=0)

    # Metadata results
    encoding = models.CharField(max_length=50, null=True, blank=True)
    has_bom = models.BooleanField(null=True, blank=True)
    delimiter = models.CharField(max_length=10, null=True, blank=True)
    has_crlf = models.BooleanField(null=True, blank=True, help_text='Windows (CRLF) vs Unix (LF) line endings')
    line_count = models.IntegerField(null=True, blank=True, help_text='Total number of lines in file')
    header_column_count = models.IntegerField(null=True, blank=True, help_text='Number of columns in header')
    columns = models.JSONField(
        default=list,
        blank=True,
        help_text='List of column names from header row'
    )

    # Integrity results
    total_rows = models.IntegerField(null=True, blank=True)
    malformed_rows = models.JSONField(
        default=list,
        help_text='List of dicts with row number and column count info'
    )

    # Patient ID validation results
    patient_id_results = models.JSONField(
        default=dict,
        blank=True,
        help_text='Patient ID validation results: {total, valid, invalid, invalid_ids: []}'
    )

    # Validation results
    validation_run = models.ForeignKey(
        'ValidationRun',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='precheck_validations',
        help_text='Link to ValidationRun for detailed per-variable validation results'
    )
    validation_errors = models.JSONField(default=list, help_text='List of error messages')
    validation_warnings = models.JSONField(default=list, help_text='List of warning messages')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    error_traceback = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'depot_precheck_validation'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['cohort', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'PrecheckValidation {self.id} - {self.original_filename} ({self.status})'

    def update_status(self, status: str, stage: str = None, progress: int = None):
        """
        Update validation status and optionally stage/progress.

        Args:
            status: New status value
            stage: Optional current stage description
            progress: Optional progress percentage (0-100)
        """
        self.status = status
        if stage is not None:
            self.current_stage = stage
        if progress is not None:
            self.progress_percent = min(max(progress, 0), 100)  # Clamp to 0-100
        self.save(update_fields=['status', 'current_stage', 'progress_percent', 'updated_at'])

    def mark_completed(self):
        """Mark validation as completed."""
        from django.utils import timezone
        self.status = 'completed'
        self.progress_percent = 100
        self.current_stage = 'Complete'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'progress_percent', 'current_stage', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message: str, traceback: str = None):
        """
        Mark validation as failed with error details.

        Args:
            error_message: Error message to display
            traceback: Optional error traceback for debugging
        """
        self.status = 'failed'
        self.error_message = error_message
        if traceback:
            self.error_traceback = traceback
        self.save(update_fields=['status', 'error_message', 'error_traceback', 'updated_at'])

    def cleanup_scratch_file(self):
        """
        Clean up the uploaded file from scratch storage.

        This should be called after validation completes (success or failure)
        to free up disk space.
        """
        import logging
        from depot.storage.manager import StorageManager

        logger = logging.getLogger(__name__)

        if not self.file_path:
            logger.warning(f'No file_path set for PrecheckValidation {self.id}')
            return

        try:
            storage = StorageManager.get_scratch_storage()

            # Remove the file and its .meta file if they exist
            if storage.exists(self.file_path):
                storage.delete(self.file_path)
                logger.info(f'Cleaned up precheck validation file: {self.file_path}')

            # Also clean up .meta file
            meta_path = f'{self.file_path}.meta'
            if storage.exists(meta_path):
                storage.delete(meta_path)
                logger.info(f'Cleaned up precheck validation meta file: {meta_path}')

        except Exception as e:
            logger.error(f'Failed to cleanup scratch file for PrecheckValidation {self.id}: {e}', exc_info=True)

    def get_metadata_dict(self):
        """Get file metadata as dictionary."""
        if self.status == 'pending':
            return None
        return {
            'size': self.file_size,
            'hash': self.file_hash,
            'encoding': self.encoding,
            'has_bom': self.has_bom,
            'delimiter': self.delimiter,
            'line_count': self.line_count,
            'has_crlf': self.has_crlf,
            'header_column_count': self.header_column_count,
            'columns': self.columns,
        }

    def get_integrity_dict(self):
        """Get integrity results as dictionary."""
        if self.status not in ['validating', 'completed', 'failed']:
            return None
        return {
            'total_rows': self.total_rows,
            'malformed_row_count': len(self.malformed_rows),
            'malformed_rows': self.malformed_rows[:10],  # First 10 only for display
        }

    def get_validation_dict(self):
        """Get validation results as dictionary with per-variable details."""
        if self.status != 'completed':
            return None

        result = {
            'errors': self.validation_errors,
            'warnings': self.validation_warnings,
        }

        # Include ValidationRun data if available
        if self.validation_run:
            variables = self.validation_run.variables.prefetch_related('checks').all()

            result['variables'] = []
            for variable in variables:
                variable_data = {
                    'name': variable.column_name,
                    'status': variable.status,
                    'total_rows': variable.total_rows,
                    'null_count': variable.null_count,
                    'empty_count': variable.empty_count,
                    'valid_count': variable.valid_count,
                    'invalid_count': variable.invalid_count,
                    'warning_count': variable.warning_count,
                    'error_count': variable.error_count,
                    'summary': variable.summary,
                    'checks': []
                }

                # Add validation checks
                for check in variable.checks.all():
                    check_data = {
                        'rule_key': check.rule_key,
                        'passed': check.passed,
                        'message': check.message,
                        'severity': check.severity,
                        'affected_row_count': check.affected_row_count,
                        'row_numbers': check.row_numbers,
                    }
                    variable_data['checks'].append(check_data)

                result['variables'].append(variable_data)

        return result
