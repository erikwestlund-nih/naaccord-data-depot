"""
Granular per-variable validation system models.

This module provides a variable-based validation architecture that validates
each column independently with parallel execution and detailed tracking.

Key models:
- ValidationRun: Top-level validation run for a file
- ValidationVariable: Per-column validation with status tracking
- ValidationCheck: Individual validation rule outcomes

Architecture:
ValidationRun (file-level)
  → ValidationVariable (column-level)
    → ValidationCheck (rule-level)

See: docs/features/validation-pipeline/architecture.md
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from depot.models.basemodel import BaseModel
import logging

logger = logging.getLogger(__name__)


class SubmissionValidation(BaseModel):
    """Aggregated validation state for an entire submission."""

    submission = models.OneToOneField(
        'CohortSubmission',
        on_delete=models.CASCADE,
        related_name='validation_summary'
    )

    latest_run = models.ForeignKey(
        'ValidationRun',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='submission_summaries'
    )

    total_runs = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_completed_at = models.DateTimeField(null=True, blank=True)
    total_files = models.IntegerField(default=0)
    files_with_errors = models.IntegerField(default=0)
    files_with_warnings = models.IntegerField(default=0)
    patient_validation_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'depot_submission_validations'
        ordering = ['-created_at']

    def __str__(self):
        return f"SubmissionValidation {self.submission_id} ({self.status})"

    def mark_running(self, run=None):
        self.status = 'running'
        self.last_started_at = timezone.now()
        if run:
            self.latest_run = run
        self.save(update_fields=['status', 'last_started_at', 'latest_run', 'updated_at'])

    def mark_completed(self, run=None):
        self.status = 'completed'
        self.last_completed_at = timezone.now()
        if run:
            self.latest_run = run
        self.save(update_fields=['status', 'last_completed_at', 'latest_run', 'updated_at'])

    def mark_failed(self, error_run=None):
        self.status = 'failed'
        self.last_completed_at = timezone.now()
        if error_run:
            self.latest_run = error_run
        self.save(update_fields=['status', 'last_completed_at', 'latest_run', 'updated_at'])


class ValidationRun(BaseModel):
    """
    Top-level validation run for a single file.
    Polymorphic: can be linked to either PrecheckValidationRun or DataTableFile.
    """
    # Polymorphic relationship
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)  # Support both integer and UUID primary keys
    content_object = GenericForeignKey('content_type', 'object_id')

    # File information
    data_file_type = models.ForeignKey('DataFileType', on_delete=models.CASCADE)
    duckdb_path = models.CharField(max_length=500, null=True, blank=True, help_text="Temporary DuckDB file path")
    raw_file_path = models.CharField(max_length=500, null=True, blank=True)
    processed_file_path = models.CharField(max_length=500, null=True, blank=True)

    # Data processing metadata
    processing_metadata = models.JSONField(
        null=True,
        blank=True,
        help_text="Metadata about data processing transformations applied (column renames, value remaps, data cleaning, etc.)"
    )

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Summary counts
    total_variables = models.IntegerField(default=0)
    completed_variables = models.IntegerField(default=0)
    variables_with_warnings = models.IntegerField(default=0)
    variables_with_errors = models.IntegerField(default=0)

    class Meta:
        db_table = 'depot_validation_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
            models.Index(fields=['data_file_type']),
        ]

    def __str__(self):
        return f"ValidationRun {self.id} - {self.data_file_type.name} ({self.status})"

    def mark_started(self):
        """Mark validation run as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
        logger.info(f"ValidationRun {self.id} started")

    def mark_completed(self):
        """Mark validation run as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
        logger.info(f"ValidationRun {self.id} completed")
        # Note: DuckDB cleanup now happens after summary generation completes
        # See generate_data_table_summary_task for cleanup timing
        self._cleanup_precheck_workspace()

        try:
            from depot.tasks.summary_generation import generate_data_table_summary_task
            generate_data_table_summary_task.delay(self.id)
        except Exception as exc:
            logger.warning("Failed to enqueue DataTableSummary generation for run %s: %s", self.id, exc)

        # Update CohortSubmissionDataTable status if this is for a submission file
        try:
            from depot.models import DataTableFile
            if self.content_type and self.content_type.model_class() is DataTableFile:
                data_file = self.content_object
                if data_file and hasattr(data_file, 'data_table'):
                    data_table = data_file.data_table
                    if data_table.status == 'in_progress':
                        data_table.update_status('completed')
                        logger.info(f"Updated CohortSubmissionDataTable {data_table.id} status to completed")
        except Exception as e:
            logger.warning(f"Failed to update data table status: {e}")

        # Update PrecheckValidation status if this is for a precheck
        try:
            from depot.models import PrecheckValidation
            if self.content_type and self.content_type.model_class() is PrecheckValidation:
                precheck = self.content_object
                if precheck and precheck.status == 'validating':
                    precheck.update_status('completed', 'Validation complete', 100)
                    logger.info(f"Updated PrecheckValidation {precheck.id} status to completed")
        except Exception as e:
            logger.warning(f"Failed to update precheck validation status: {e}")

    def mark_failed(self, error_message: str):
        """Mark validation run as failed."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])
        logger.error(f"ValidationRun {self.id} failed: {error_message}")
        # Note: DuckDB cleanup happens after summary generation (even for failed runs)
        # See generate_data_table_summary_task for cleanup timing
        self._cleanup_precheck_workspace()

        try:
            from depot.tasks.summary_generation import generate_data_table_summary_task
            generate_data_table_summary_task.delay(self.id)
        except Exception as exc:
            logger.warning("Failed to enqueue DataTableSummary generation for failed run %s: %s", self.id, exc)

        # Update CohortSubmissionDataTable status even if validation failed
        # (so UI doesn't get stuck on "Processing...")
        try:
            from depot.models import DataTableFile
            if self.content_type and self.content_type.model_class() is DataTableFile:
                data_file = self.content_object
                if data_file and hasattr(data_file, 'data_table'):
                    data_table = data_file.data_table
                    if data_table.status == 'in_progress':
                        data_table.update_status('completed')  # Still mark as completed, errors will be visible
                        logger.info(f"Updated CohortSubmissionDataTable {data_table.id} status to completed (with errors)")
        except Exception as e:
            logger.warning(f"Failed to update data table status: {e}")

        # Update PrecheckValidation status if this is for a precheck
        try:
            from depot.models import PrecheckValidation
            if self.content_type and self.content_type.model_class() is PrecheckValidation:
                precheck = self.content_object
                if precheck and precheck.status == 'validating':
                    error_summary = error_message[:90] + '...' if len(error_message) > 90 else error_message
                    precheck.update_status('failed', f'Validation error: {error_summary}', 0)
                    logger.info(f"Updated PrecheckValidation {precheck.id} status to failed")
        except Exception as e:
            logger.warning(f"Failed to update precheck validation status: {e}")

    def update_summary(self):
        """Recalculate summary counts from variables and check completion."""
        variables = self.variables.all()
        self.total_variables = variables.count()
        self.completed_variables = variables.filter(status='completed').count()
        self.variables_with_warnings = variables.filter(warning_count__gt=0).count()
        self.variables_with_errors = variables.filter(error_count__gt=0).count()

        # Check if all variables are completed and mark run as completed
        if self.status == 'running' and self.total_variables > 0:
            failed_count = variables.filter(status='failed').count()
            finished_count = self.completed_variables + failed_count

            if finished_count == self.total_variables:
                # All variables are done (either completed or failed)
                self.mark_completed()
                logger.info(f"ValidationRun {self.id} auto-completed: {self.completed_variables} completed, {failed_count} failed")
                return  # mark_completed() already saves

        self.save(update_fields=[
            'total_variables', 'completed_variables',
            'variables_with_warnings', 'variables_with_errors', 'updated_at'
        ])

    def get_duration(self):
        """Get validation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_duration_display(self):
        """Get human-readable duration."""
        duration = self.get_duration()
        if duration is None:
            return "N/A"

        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            minutes = duration / 60
            return f"{minutes:.1f}m"
        else:
            hours = duration / 3600
            return f"{hours:.1f}h"

    def _cleanup_duckdb_file(self):
        """
        Delete the temporary DuckDB file after validation completes.

        DuckDB files are only needed during validation. Once validation is complete,
        we have the validation results stored and don't need the DuckDB file anymore.

        Keep:
        - raw_file_path (original upload)
        - processed_file_path (keep for now, delete later when we have recovery)

        Delete:
        - duckdb_path (temporary, no longer needed after validation)
        """
        if not self.duckdb_path:
            return

        import os
        try:
            if os.path.exists(self.duckdb_path):
                os.unlink(self.duckdb_path)
                logger.info(f"Deleted DuckDB file for ValidationRun {self.id}: {self.duckdb_path}")

                # Also delete .wal file if it exists (DuckDB write-ahead log)
                wal_path = f"{self.duckdb_path}.wal"
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
                    logger.info(f"Deleted DuckDB WAL file: {wal_path}")

                # Also delete .meta file if it exists
                meta_path = f"{self.duckdb_path}.meta"
                if os.path.exists(meta_path):
                    os.unlink(meta_path)
                    logger.info(f"Deleted DuckDB .meta file: {meta_path}")
            else:
                logger.debug(f"DuckDB file already deleted: {self.duckdb_path}")
        except Exception as e:
            logger.warning(f"Failed to delete DuckDB file for ValidationRun {self.id}: {e}")

    def _cleanup_precheck_workspace(self):
        """Cleanup scratch workspace files for precheck validations."""
        try:
            model_class = self.content_type.model_class() if self.content_type else None
            if model_class is None or model_class.__name__ != 'PrecheckRun':
                return

            precheck_run = self.content_object
            if not precheck_run:
                return

            # Delete scratch directory for this precheck
            from depot.storage.scratch_manager import ScratchManager
            from depot.models.phifiletracking import PHIFileTracking

            scratch = ScratchManager()
            prefix = f"{scratch.precheck_runs_prefix}{precheck_run.id}/"
            scratch.storage.delete_prefix(prefix)

            user = precheck_run.uploaded_by or precheck_run.created_by

            pending_records = PHIFileTracking.objects.filter(
                content_type=self.content_type,
                object_id=precheck_run.id,
                cleanup_required=True,
                cleaned_up=False
            )

            for record in pending_records:
                record.mark_cleaned_up(user)
                PHIFileTracking.objects.create(
                    cohort=record.cohort,
                    user=user,
                    action='work_copy_deleted',
                    file_path=record.file_path,
                    file_type=record.file_type,
                    content_object=precheck_run,
                    metadata=record.metadata
                )

        except Exception as exc:
            logger.warning(
                "Failed to cleanup workspace for ValidationRun %s: %s",
                self.id,
                exc,
                exc_info=True
            )


class ValidationVariable(BaseModel):
    """
    Per-column validation results.
    One record per variable in the data file.
    """
    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name='variables'
    )

    # Column information
    column_name = models.CharField(max_length=100, help_text="Column name from definition")
    column_type = models.CharField(max_length=50, help_text="Data type from definition")
    display_name = models.CharField(max_length=200, help_text="Human-readable name")

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Summary statistics
    total_rows = models.IntegerField(default=0)
    null_count = models.IntegerField(default=0)
    empty_count = models.IntegerField(default=0)
    valid_count = models.IntegerField(default=0)
    invalid_count = models.IntegerField(default=0)
    warning_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)

    # Variable-specific summary (flexible)
    summary = models.JSONField(
        default=dict,
        help_text="Variable-specific statistics (e.g., duplicate_count, out_of_range_count)"
    )

    class Meta:
        db_table = 'depot_validation_variables'
        ordering = ['validation_run', 'column_name']
        unique_together = [['validation_run', 'column_name']]
        indexes = [
            models.Index(fields=['validation_run', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.validation_run.data_file_type.name}.{self.column_name} ({self.status})"

    def get_display_name(self):
        """Get display name with fallback to column name."""
        return self.display_name or self.column_name

    def mark_started(self):
        """Mark variable validation as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
        logger.info(f"ValidationVariable {self.id} ({self.column_name}) started")

    def mark_completed(self):
        """Mark variable validation as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()
        logger.info(f"ValidationVariable {self.id} ({self.column_name}) completed")

    def mark_failed(self, error_message: str):
        """Mark variable validation as failed."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()
        logger.error(f"ValidationVariable {self.id} ({self.column_name}) failed: {error_message}")

    def update_counts(self):
        """Recalculate counts from checks."""
        checks = self.checks.all()
        self.warning_count = checks.filter(severity='warning', passed=False).count()
        self.error_count = checks.filter(severity='error', passed=False).count()
        self.save(update_fields=['warning_count', 'error_count', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()

    def get_duration(self):
        """Get validation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def get_duration_display(self):
        """Get human-readable duration."""
        duration = self.get_duration()
        if duration is None:
            return "N/A"

        if duration < 60:
            return f"{duration:.1f}s"
        else:
            minutes = duration / 60
            return f"{minutes:.1f}m"


class ValidationCheck(BaseModel):
    """
    Individual validation rule outcome.
    Multiple checks per variable (one per validation rule).
    """
    validation_variable = models.ForeignKey(
        ValidationVariable,
        on_delete=models.CASCADE,
        related_name='checks'
    )

    # Rule information
    rule_key = models.CharField(
        max_length=100,
        help_text="Validator identifier (e.g., 'type_is_boolean', 'range', 'no_duplicates')"
    )
    rule_params = models.JSONField(
        default=dict,
        help_text="Rule parameters (e.g., {'min': 1900, 'max': 2025})"
    )

    # Result
    passed = models.BooleanField(default=False, help_text="Whether validation passed")
    SEVERITY_CHOICES = [
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    message = models.TextField(help_text="Human-readable validation message")

    # Issue details (PHI-safe)
    affected_row_count = models.IntegerField(
        default=0,
        help_text="Number of rows affected by this issue"
    )
    row_numbers = models.TextField(
        null=True,
        blank=True,
        help_text="Comma-separated row numbers (never with patient IDs)"
    )
    invalid_value = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Example invalid value (only if not PHI-sensitive)"
    )

    # Additional metadata
    meta = models.JSONField(
        default=dict,
        help_text="Additional rule-specific information"
    )

    class Meta:
        db_table = 'depot_validation_checks'
        ordering = ['validation_variable', 'rule_key']
        indexes = [
            models.Index(fields=['validation_variable', 'passed']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        status = "✓" if self.passed else "✗"
        return f"{status} {self.validation_variable.column_name}.{self.rule_key}"

    def get_row_numbers_list(self):
        """
        Parse row_numbers into list.

        Handles two formats:
        - Legacy: comma-separated integers (e.g., "1, 2, 3")
        - New: file:row format (e.g., "file_5:row_10, file_7:row_8")

        Returns list of integers for legacy format, list of strings for new format.
        """
        if not self.row_numbers:
            return []
        try:
            # Try to parse as integers (legacy format)
            return [int(x.strip()) for x in self.row_numbers.split(',')]
        except (ValueError, AttributeError):
            # Fall back to string format (new file:row format)
            return [x.strip() for x in self.row_numbers.split(',')]

    def get_row_numbers_display(self, max_display=10):
        """Get formatted row numbers for display with limit."""
        row_list = self.get_row_numbers_list()
        if not row_list:
            return "N/A"

        if len(row_list) <= max_display:
            return ", ".join(map(str, row_list))
        else:
            displayed = ", ".join(map(str, row_list[:max_display]))
            return f"{displayed}, ... ({len(row_list) - max_display} more)"


class DataProcessingLog(BaseModel):
    """
    Log of data processing/mapping operations performed on raw files.
    Tracks schema mappings, column renames, value remaps, and transformations.
    """
    # Link to validation run
    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name='processing_logs',
        null=True,
        blank=True
    )

    # Cohort and file type context
    cohort = models.ForeignKey(
        'Cohort',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    data_file_type = models.ForeignKey(
        'DataFileType',
        on_delete=models.CASCADE
    )

    # Mapping information
    mapping_key = models.CharField(
        max_length=100,
        default='passthrough',
        help_text="Mapping identifier (e.g., 'cnics', 'standard', 'passthrough')"
    )
    mapping_version = models.CharField(
        max_length=20,
        default='1.0',
        help_text="Mapping version (e.g., '1.0', '1.1')"
    )

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # File paths
    raw_file_path = models.CharField(max_length=500, null=True, blank=True)
    processed_file_path = models.CharField(max_length=500, null=True, blank=True)

    # Changes summary (JSON)
    changes_summary = models.JSONField(
        default=dict,
        help_text="Summary of transformations: renamed columns, value remaps, defaults, warnings, errors"
    )

    # Row counts for verification
    row_count_in = models.IntegerField(default=0)
    row_count_out = models.IntegerField(default=0)

    class Meta:
        db_table = 'depot_data_processing_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['validation_run']),
            models.Index(fields=['cohort', 'data_file_type']),
            models.Index(fields=['status']),
            models.Index(fields=['mapping_key']),
        ]

    def __str__(self):
        return f"DataProcessingLog {self.id} - {self.mapping_key} ({self.status})"

    def mark_started(self):
        """Mark processing as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])
        logger.info(f"DataProcessingLog {self.id} started")

    def mark_completed(self, processed_path, changes_summary, row_count_in, row_count_out):
        """Mark processing as completed with results."""
        self.status = 'completed'
        self.finished_at = timezone.now()
        self.processed_file_path = processed_path
        self.changes_summary = changes_summary
        self.row_count_in = row_count_in
        self.row_count_out = row_count_out
        self.save(update_fields=[
            'status', 'finished_at', 'processed_file_path',
            'changes_summary', 'row_count_in', 'row_count_out', 'updated_at'
        ])
        logger.info(f"DataProcessingLog {self.id} completed")

    def mark_failed(self, error_message: str):
        """Mark processing as failed."""
        self.status = 'failed'
        self.finished_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
        logger.error(f"DataProcessingLog {self.id} failed: {error_message}")

    def get_duration(self):
        """Get processing duration in seconds."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def get_summary_display(self):
        """Get human-readable summary of changes."""
        if not self.changes_summary:
            return "No changes"

        parts = []
        renamed = len(self.changes_summary.get('renamed_columns', []))
        if renamed:
            parts.append(f"{renamed} column{'s' if renamed != 1 else ''} renamed")

        remapped = len(self.changes_summary.get('value_remaps', {}))
        if remapped:
            parts.append(f"{remapped} value remap{'s' if remapped != 1 else ''}")

        defaults = len(self.changes_summary.get('defaults_applied', {}))
        if defaults:
            parts.append(f"{defaults} default{'s' if defaults != 1 else ''} applied")

        unmapped = len(self.changes_summary.get('unmapped_columns', []))
        if unmapped:
            parts.append(f"{unmapped} unmapped column{'s' if unmapped != 1 else ''} kept")

        return "; ".join(parts) if parts else "No changes"
