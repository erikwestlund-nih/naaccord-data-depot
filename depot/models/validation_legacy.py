"""
Granular validation system models.

This module provides a job-based validation architecture that replaces
the monolithic Quarto notebook approach. Each validation type runs as
an independent job with progress tracking and result storage.

Key features:
- Real-time progress updates for each validation type
- Parallel execution of independent validations
- Database-queryable validation results
- Granular error handling and retry capability
- Extensible validator registry

See: docs/technical/granular-validation-system.md
"""
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from depot.models.basemodel import BaseModel


class ValidationRun(BaseModel):
    """
    Represents a complete validation run for a file upload.

    A ValidationRun orchestrates multiple ValidationJob instances,
    tracking overall progress and completion status. It can be linked
    to any uploadable model (Audit, PrecheckRun, etc.) via GenericForeignKey.

    Example:
        run = ValidationRun.objects.create(
            content_object=precheck_run,
            data_file_type=file_type,
            duckdb_path='/tmp/data.duckdb',
            initiated_by=user
        )
    """

    # Polymorphic relationship to any uploadable model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of object being validated (Audit, PrecheckRun, etc.)"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the object being validated"
    )
    content_object = GenericForeignKey('content_type', 'object_id')

    # File context
    data_file_type = models.ForeignKey(
        'DataFileType',
        on_delete=models.CASCADE,
        help_text="Type of data file being validated"
    )
    duckdb_path = models.CharField(
        max_length=500,
        help_text="Path to DuckDB file for validation queries"
    )

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('partial', 'Partially Completed'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )

    # Progress tracking
    total_jobs = models.IntegerField(
        default=0,
        help_text="Total number of validation jobs in this run"
    )
    completed_jobs = models.IntegerField(
        default=0,
        help_text="Number of jobs that have completed (passed or failed)"
    )
    failed_jobs = models.IntegerField(
        default=0,
        help_text="Number of jobs that failed with errors"
    )

    # Timestamps
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When validation processing started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When all validation jobs completed"
    )

    # User context
    initiated_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='initiated_validation_runs'
    )

    class Meta:
        db_table = 'depot_validation_run'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['data_file_type', 'status']),
        ]
        verbose_name = 'Validation Run'
        verbose_name_plural = 'Validation Runs'

    def __str__(self):
        return f"ValidationRun {self.id} - {self.status} ({self.completed_jobs}/{self.total_jobs})"

    @property
    def progress_percentage(self):
        """Calculate progress as percentage (0-100)"""
        if self.total_jobs == 0:
            return 0
        return int((self.completed_jobs / self.total_jobs) * 100)

    def get_validation_summary(self):
        """
        Get summary of validation results.

        Returns:
            dict: Summary with counts by status and completion percentage
        """
        jobs = self.validation_jobs.all()
        total = jobs.count()
        passed = jobs.filter(status='passed').count()
        failed = jobs.filter(status='failed').count()
        running = jobs.filter(status='running').count()
        pending = jobs.filter(status='pending').count()
        skipped = jobs.filter(status='skipped').count()

        # Completed = passed + failed + skipped (any non-running/pending state)
        completed = passed + failed + skipped

        # Calculate completion percentage
        completion_percentage = 0
        if total > 0:
            completion_percentage = (completed / total) * 100

        return {
            'total': total,
            'completed': completed,
            'running': running,
            'pending': pending,
            'completion_percentage': completion_percentage,
            # Keep legacy fields for backward compatibility if needed
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
        }

    def mark_started(self):
        """Mark validation run as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def mark_completed(self):
        """Mark validation run as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self):
        """Mark validation run as failed"""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def increment_completed(self):
        """Increment completed job counter"""
        self.completed_jobs += 1
        self.save(update_fields=['completed_jobs', 'updated_at'])

    def increment_failed(self):
        """Increment failed job counter"""
        self.failed_jobs += 1
        self.save(update_fields=['failed_jobs', 'updated_at'])


class ValidationJob(BaseModel):
    """
    Individual validation job within a ValidationRun.

    Each job represents a specific validation type (required fields, date ranges,
    patient IDs, etc.) and stores its results independently. Jobs can run in
    parallel or have dependencies on other jobs.

    Example:
        job = ValidationJob.objects.create(
            validation_run=run,
            validation_type='required_fields',
            status='pending'
        )
    """

    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name='validation_jobs',
        help_text="Parent validation run"
    )

    # Validation type (key from VALIDATION_REGISTRY)
    validation_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of validation (key from VALIDATION_REGISTRY)"
    )

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )

    # Progress for long-running validations (0-100)
    progress = models.IntegerField(
        default=0,
        help_text="Percentage complete (0-100)"
    )

    # Results storage (JSON)
    result_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Summary statistics (counts, percentages, metadata)"
    )
    result_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed results (configuration, thresholds, etc.)"
    )

    # Error handling
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if job failed"
    )
    error_traceback = models.TextField(
        null=True,
        blank=True,
        help_text="Full traceback if job failed"
    )

    # Celery task tracking
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Celery task ID for this job"
    )

    # Timestamps
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this job started processing"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this job completed"
    )

    class Meta:
        db_table = 'depot_validation_job'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['validation_run', 'status']),
            models.Index(fields=['validation_type', 'status']),
            models.Index(fields=['celery_task_id']),
        ]
        verbose_name = 'Validation Job'
        verbose_name_plural = 'Validation Jobs'

    def __str__(self):
        return f"ValidationJob {self.id} - {self.validation_type} ({self.status})"

    def get_display_name(self):
        """Get human-readable display name from registry"""
        from depot.validation.registry import VALIDATION_REGISTRY
        config = VALIDATION_REGISTRY.get(self.validation_type, {})
        return config.get('display_name', self.validation_type.replace('_', ' ').title())

    def get_duration_display(self):
        """Get human-readable duration"""
        if not self.started_at or not self.completed_at:
            return None

        duration = self.completed_at - self.started_at
        total_seconds = int(duration.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"

    def mark_running(self):
        """Mark job as running"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def mark_passed(self, result_summary, result_details=None):
        """
        Mark job as passed with results.

        Args:
            result_summary: dict with summary statistics
            result_details: optional dict with detailed results
        """
        self.status = 'passed'
        self.result_summary = result_summary
        if result_details:
            self.result_details = result_details
        self.completed_at = timezone.now()
        self.progress = 100
        self.save(update_fields=[
            'status', 'result_summary', 'result_details',
            'completed_at', 'progress', 'updated_at'
        ])

    def mark_failed(self, error_message, traceback=None):
        """
        Mark job as failed with error information.

        Args:
            error_message: str error message
            traceback: optional str full traceback
        """
        self.status = 'failed'
        self.error_message = error_message
        if traceback:
            self.error_traceback = traceback
        self.completed_at = timezone.now()
        self.save(update_fields=[
            'status', 'error_message', 'error_traceback',
            'completed_at', 'updated_at'
        ])

    def mark_skipped(self, reason):
        """
        Mark job as skipped with reason.

        Args:
            reason: str reason for skipping
        """
        self.status = 'skipped'
        self.error_message = reason
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])

    def update_progress(self, progress):
        """
        Update job progress.

        Args:
            progress: int between 0 and 100
        """
        self.progress = max(0, min(100, progress))
        self.save(update_fields=['progress', 'updated_at'])


class ValidationIssue(BaseModel):
    """
    Individual validation issues/warnings discovered during validation.

    This model stores specific problems found in the data, allowing for
    detailed filtering, querying, and reporting. Issues are linked to
    their parent ValidationJob.

    Example:
        ValidationIssue.objects.create(
            validation_job=job,
            severity='error',
            row_number=42,
            column_name='birthDate',
            issue_type='required_field_missing',
            message='Required field "birthDate" is missing or empty',
            invalid_value=None,
            expected_value='Non-empty date value'
        )
    """

    validation_job = models.ForeignKey(
        ValidationJob,
        on_delete=models.CASCADE,
        related_name='issues',
        help_text="Parent validation job"
    )

    # Severity levels
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),  # Blocks submission
        ('error', 'Error'),        # Significant issue
        ('warning', 'Warning'),    # Should be reviewed
        ('info', 'Info'),          # Informational only
    ]
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        db_index=True,
        help_text="Severity level of this issue"
    )

    # Location in data
    row_number = models.IntegerField(
        null=True,
        blank=True,
        help_text="Row number where issue was found (1-indexed)"
    )
    column_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Column name where issue was found"
    )

    # Issue description
    issue_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of validation failure (e.g., 'required_field_missing')"
    )
    message = models.TextField(
        help_text="Human-readable error message"
    )

    # Context data
    invalid_value = models.TextField(
        null=True,
        blank=True,
        help_text="The invalid value that was found"
    )
    expected_value = models.TextField(
        null=True,
        blank=True,
        help_text="What the value should be or look like"
    )

    # Additional context (JSON for flexibility)
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional context data (e.g., related values, constraints)"
    )

    class Meta:
        db_table = 'depot_validation_issue'
        ordering = ['severity', 'row_number']
        indexes = [
            models.Index(fields=['validation_job', 'severity']),
            models.Index(fields=['issue_type', 'severity']),
            models.Index(fields=['column_name', 'severity']),
        ]
        verbose_name = 'Validation Issue'
        verbose_name_plural = 'Validation Issues'

    def __str__(self):
        location = f"Row {self.row_number}" if self.row_number else "General"
        return f"{self.severity.upper()}: {self.message} ({location})"
