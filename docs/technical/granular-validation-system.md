# Granular Validation System - Design Document
## Moving from Monolithic Quarto to Async Job-Based Validation

### Document Information
- **Date Created**: 2025-01-22
- **Status**: Design Proposal
- **Author**: Erik Westlund
- **Version**: 1.0

---

## Executive Summary

This document outlines the redesign of NA-ACCORD's data validation system from monolithic Quarto notebook processing to a granular, job-based validation pipeline. The new system provides real-time feedback, better error handling, improved UX, and database-queryable results while maintaining the existing DuckDB data processing foundation.

**Key Benefits**:
- ✅ **Real-time feedback**: Users see validation results progressively, not all-at-once
- ✅ **Better UX**: Modern UI with Alpine.js components and progress indicators
- ✅ **Failure isolation**: One validation step failing doesn't block others
- ✅ **Retry capability**: Individual validations can be retried without re-running everything
- ✅ **Performance visibility**: Users see which validations are slow/fast
- ✅ **Database queryability**: Results stored in DB enable filtering, searching, history tracking
- ✅ **Parallel execution**: Independent validations run concurrently
- ✅ **Better error handling**: Granular error messages tied to specific validation steps

---

## Current System Architecture

### Existing Quarto-Based Workflow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│File Upload   │ --> │DuckDB        │ --> │Quarto        │
│(CSV/TSV)     │     │Conversion    │     │Notebook      │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  v
                                          ┌──────────────┐
                                          │HTML Report   │
                                          │(All-at-Once) │
                                          └──────────────┘
```

**Current Flow** (from `depot/tasks/upload_precheck.py`):
1. User uploads CSV/TSV file
2. File stored via StorageManager (RemoteStorageDriver on web server)
3. Celery task converts to DuckDB format
4. R/Quarto notebook executes all validations
5. Single HTML report generated with all results
6. Report stored in NAS via StorageManager

**Problems with Current Approach**:
- ⚠️ **No progressive feedback**: Users wait for entire notebook to complete
- ⚠️ **All-or-nothing**: One validation failure means no results at all
- ⚠️ **Black box**: No visibility into which validations are running/slow
- ⚠️ **Not queryable**: Results trapped in HTML, not searchable in database
- ⚠️ **Poor error handling**: Generic failure messages, hard to debug
- ⚠️ **No retry**: Failures require re-uploading entire file
- ⚠️ **Inflexible**: Adding new validations requires R notebook changes

---

## Proposed Architecture

### High-Level Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐
│File Upload   │ --> │DuckDB        │ --> │Validation Job Queue      │
│(CSV/TSV)     │     │Conversion    │     │(Parallel Execution)      │
└──────────────┘     └──────────────┘     └──────────────────────────┘
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    v                             v                             v
            ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
            │Required Field │           │Date Range     │           │Enum Value     │
            │Validation Job │           │Validation Job │           │Validation Job │
            └───────────────┘           └───────────────┘           └───────────────┘
                    │                             │                             │
                    v                             v                             v
            ┌──────────────────────────────────────────────────────────────────────┐
            │                     Validation Results Database                       │
            │              (Queryable, Filterable, Versioned)                      │
            └──────────────────────────────────────────────────────────────────────┘
                    │
                    v
            ┌──────────────┐
            │Live UI Update│
            │(Alpine.js)   │
            └──────────────┘
```

### Component Architecture

#### 1. Validation Registry
Central registry defining all available validation types:

```python
# depot/validation/registry.py
from depot.validation.validators import (
    RequiredFieldValidator,
    DateRangeValidator,
    EnumValueValidator,
    PatientIDValidator,
    CrossFileValidator,
)

VALIDATION_REGISTRY = {
    'required_fields': {
        'validator': RequiredFieldValidator,
        'display_name': 'Required Fields Check',
        'description': 'Validates that all required fields have values',
        'dependencies': [],  # No dependencies
        'parallel_safe': True,  # Can run in parallel
    },
    'date_ranges': {
        'validator': DateRangeValidator,
        'display_name': 'Date Range Validation',
        'description': 'Validates date fields are within acceptable ranges',
        'dependencies': [],
        'parallel_safe': True,
    },
    'enum_values': {
        'validator': EnumValueValidator,
        'display_name': 'Categorical Value Check',
        'description': 'Validates enum/categorical field values',
        'dependencies': [],
        'parallel_safe': True,
    },
    'patient_ids': {
        'validator': PatientIDValidator,
        'display_name': 'Patient ID Validation',
        'description': 'Validates patient IDs against submission master list',
        'dependencies': [],  # Uses existing SubmissionPatientIDs
        'parallel_safe': True,
    },
    'cross_file_consistency': {
        'validator': CrossFileValidator,
        'display_name': 'Cross-File Consistency',
        'description': 'Validates consistency across multiple files',
        'dependencies': ['patient_ids'],  # Depends on patient validation
        'parallel_safe': False,  # Requires other files
    },
}
```

#### 2. Data Models

```python
# depot/models/validation_job.py
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class ValidationRun(models.Model):
    """
    Represents a complete validation run for a file upload.
    Tracks overall progress and completion status.
    """
    # Polymorphic relationship to any uploadable model (Audit, UploadPrecheck, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # File context
    data_file_type = models.ForeignKey('DataFileType', on_delete=models.CASCADE)
    duckdb_path = models.CharField(max_length=500, help_text="Path to DuckDB file for validation")

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('partial', 'Partially Completed'),
        ],
        default='pending'
    )

    # Progress tracking
    total_jobs = models.IntegerField(default=0)
    completed_jobs = models.IntegerField(default=0)
    failed_jobs = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # User context
    initiated_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'depot_validation_run'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    @property
    def progress_percentage(self):
        """Calculate progress as percentage"""
        if self.total_jobs == 0:
            return 0
        return int((self.completed_jobs / self.total_jobs) * 100)

    def get_validation_summary(self):
        """Get summary of validation results"""
        jobs = self.validation_jobs.all()
        return {
            'total': jobs.count(),
            'passed': jobs.filter(status='passed').count(),
            'failed': jobs.filter(status='failed').count(),
            'running': jobs.filter(status='running').count(),
            'pending': jobs.filter(status='pending').count(),
        }


class ValidationJob(models.Model):
    """
    Individual validation job within a ValidationRun.
    Stores results and progress for a specific validation type.
    """
    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name='validation_jobs'
    )

    # Validation type
    validation_type = models.CharField(
        max_length=50,
        help_text="Key from VALIDATION_REGISTRY"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('passed', 'Passed'),
            ('failed', 'Failed'),
            ('skipped', 'Skipped'),
        ],
        default='pending'
    )

    # Progress for long-running validations
    progress = models.IntegerField(default=0, help_text="Percentage complete (0-100)")

    # Results storage (JSON)
    result_summary = models.JSONField(
        default=dict,
        help_text="Summary statistics (counts, percentages)"
    )
    result_details = models.JSONField(
        default=dict,
        help_text="Detailed results (failures, warnings)"
    )

    # Error handling
    error_message = models.TextField(null=True, blank=True)
    error_traceback = models.TextField(null=True, blank=True)

    # Celery task tracking
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'depot_validation_job'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['validation_run', 'status']),
            models.Index(fields=['validation_type', 'status']),
            models.Index(fields=['celery_task_id']),
        ]

    def mark_running(self):
        """Mark job as running"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def mark_passed(self, result_summary, result_details=None):
        """Mark job as passed with results"""
        self.status = 'passed'
        self.result_summary = result_summary
        if result_details:
            self.result_details = result_details
        self.completed_at = timezone.now()
        self.progress = 100
        self.save()

    def mark_failed(self, error_message, traceback=None):
        """Mark job as failed with error"""
        self.status = 'failed'
        self.error_message = error_message
        if traceback:
            self.error_traceback = traceback
        self.completed_at = timezone.now()
        self.save()


class ValidationIssue(models.Model):
    """
    Individual validation issues/warnings discovered during validation.
    Allows for detailed filtering and querying of specific problems.
    """
    validation_job = models.ForeignKey(
        ValidationJob,
        on_delete=models.CASCADE,
        related_name='issues'
    )

    # Issue details
    severity = models.CharField(
        max_length=20,
        choices=[
            ('critical', 'Critical'),  # Blocks submission
            ('error', 'Error'),        # Significant issue
            ('warning', 'Warning'),    # Should be reviewed
            ('info', 'Info'),          # Informational only
        ]
    )

    # Location in data
    row_number = models.IntegerField(null=True, blank=True)
    column_name = models.CharField(max_length=100, null=True, blank=True)

    # Issue description
    issue_type = models.CharField(max_length=100, help_text="Type of validation failure")
    message = models.TextField()

    # Context data
    invalid_value = models.TextField(null=True, blank=True)
    expected_value = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'depot_validation_issue'
        ordering = ['severity', 'row_number']
        indexes = [
            models.Index(fields=['validation_job', 'severity']),
            models.Index(fields=['issue_type']),
        ]
```

#### 3. Base Validator Class

```python
# depot/validation/base.py
from abc import ABC, abstractmethod
import duckdb
from typing import Dict, List, Any

class BaseValidator(ABC):
    """
    Base class for all validators.
    Each validator operates on a DuckDB connection.
    """

    def __init__(self, duckdb_path: str, data_file_type, definition: Dict):
        """
        Initialize validator

        Args:
            duckdb_path: Path to DuckDB file
            data_file_type: DataFileType instance
            definition: JSON definition for this file type
        """
        self.duckdb_path = duckdb_path
        self.data_file_type = data_file_type
        self.definition = definition
        self.conn = None

    def connect(self):
        """Establish DuckDB connection"""
        self.conn = duckdb.connect(self.duckdb_path, read_only=True)

    def disconnect(self):
        """Close DuckDB connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    @abstractmethod
    def validate(self, validation_job) -> Dict[str, Any]:
        """
        Execute validation logic.

        Args:
            validation_job: ValidationJob instance to update with progress

        Returns:
            Dict with:
                - passed: bool
                - summary: Dict with counts/statistics
                - issues: List of issue dicts
        """
        pass

    def update_progress(self, validation_job, progress: int):
        """Update job progress"""
        validation_job.progress = progress
        validation_job.save(update_fields=['progress'])

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
```

#### 4. Example Validator Implementation

```python
# depot/validation/validators/required_fields.py
from depot.validation.base import BaseValidator
from typing import Dict, Any

class RequiredFieldValidator(BaseValidator):
    """
    Validates that required fields have non-null values
    """

    def validate(self, validation_job) -> Dict[str, Any]:
        """Execute required field validation"""
        self.update_progress(validation_job, 10)

        # Get required fields from definition
        required_fields = [
            field['name']
            for field in self.definition['fields']
            if field.get('value_required', False)
        ]

        if not required_fields:
            return {
                'passed': True,
                'summary': {'required_field_count': 0},
                'issues': []
            }

        self.update_progress(validation_job, 30)

        issues = []
        total_rows = self.conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]

        # Check each required field
        for i, field in enumerate(required_fields):
            progress = 30 + int((i / len(required_fields)) * 60)
            self.update_progress(validation_job, progress)

            # Find null/empty values
            query = f"""
                SELECT
                    ROW_NUMBER() OVER () as row_num,
                    '{field}' as column_name
                FROM data
                WHERE "{field}" IS NULL
                   OR TRIM(CAST("{field}" AS VARCHAR)) = ''
                LIMIT 1000  -- Limit issues to prevent memory issues
            """

            results = self.conn.execute(query).fetchall()

            for row_num, col_name in results:
                issues.append({
                    'row_number': row_num,
                    'column_name': col_name,
                    'severity': 'error',
                    'issue_type': 'required_field_missing',
                    'message': f'Required field "{col_name}" is missing or empty',
                    'invalid_value': None,
                    'expected_value': 'Non-empty value'
                })

        self.update_progress(validation_job, 100)

        return {
            'passed': len(issues) == 0,
            'summary': {
                'required_field_count': len(required_fields),
                'total_rows': total_rows,
                'missing_count': len(issues),
                'has_more_issues': len(issues) == 1000
            },
            'issues': issues
        }
```

#### 5. Celery Task Orchestration

```python
# depot/tasks/validation.py
from celery import shared_task, group, chord
import logging
from django.utils import timezone
from depot.models import ValidationRun, ValidationJob, ValidationIssue
from depot.validation.registry import VALIDATION_REGISTRY
from depot.data.definition_loader import load_definition

logger = logging.getLogger(__name__)


@shared_task
def start_validation_run(validation_run_id):
    """
    Start a validation run by creating jobs and dispatching tasks.
    Uses Celery chords for dependency management.
    """
    try:
        validation_run = ValidationRun.objects.get(id=validation_run_id)

        # Mark as running
        validation_run.status = 'running'
        validation_run.started_at = timezone.now()
        validation_run.save()

        # Load data definition
        definition = load_definition(validation_run.data_file_type)

        # Create validation jobs based on registry
        jobs = []
        dependency_map = {}

        for validation_type, config in VALIDATION_REGISTRY.items():
            job = ValidationJob.objects.create(
                validation_run=validation_run,
                validation_type=validation_type,
                status='pending'
            )
            jobs.append(job)
            dependency_map[validation_type] = {
                'job': job,
                'dependencies': config['dependencies'],
                'parallel_safe': config['parallel_safe']
            }

        # Update total job count
        validation_run.total_jobs = len(jobs)
        validation_run.save(update_fields=['total_jobs'])

        # Organize jobs by dependency levels
        level_0_jobs = []  # No dependencies
        dependent_jobs = []  # Have dependencies

        for val_type, info in dependency_map.items():
            if not info['dependencies'] and info['parallel_safe']:
                level_0_jobs.append(info['job'])
            else:
                dependent_jobs.append(info['job'])

        # Execute level 0 jobs in parallel using group
        if level_0_jobs:
            parallel_tasks = group([
                execute_validation_job.s(job.id)
                for job in level_0_jobs
            ])

            # If we have dependent jobs, use chord to execute them after
            if dependent_jobs:
                callback = process_dependent_jobs.s(
                    validation_run_id,
                    [job.id for job in dependent_jobs]
                )
                chord(parallel_tasks)(callback)
            else:
                # No dependent jobs, just run parallel and finalize
                chord(parallel_tasks)(finalize_validation_run.s(validation_run_id))
        else:
            # No parallel jobs, just run dependent ones
            process_dependent_jobs.delay(validation_run_id, [job.id for job in dependent_jobs])

        return {
            'validation_run_id': validation_run_id,
            'total_jobs': len(jobs),
            'parallel_jobs': len(level_0_jobs),
            'dependent_jobs': len(dependent_jobs)
        }

    except Exception as e:
        logger.error(f"Failed to start validation run {validation_run_id}: {e}", exc_info=True)
        validation_run.status = 'failed'
        validation_run.save()
        raise


@shared_task
def execute_validation_job(validation_job_id):
    """
    Execute a single validation job.
    """
    try:
        job = ValidationJob.objects.select_related('validation_run').get(id=validation_job_id)

        # Mark as running
        job.mark_running()

        # Get validator config
        config = VALIDATION_REGISTRY[job.validation_type]

        # Load data definition
        definition = load_definition(job.validation_run.data_file_type)

        # Instantiate validator
        validator_class = config['validator']
        validator = validator_class(
            job.validation_run.duckdb_path,
            job.validation_run.data_file_type,
            definition
        )

        # Execute validation
        with validator:
            result = validator.validate(job)

        # Store results
        if result['passed']:
            job.mark_passed(result['summary'], result.get('details'))
        else:
            # Create ValidationIssue records
            for issue_data in result.get('issues', []):
                ValidationIssue.objects.create(
                    validation_job=job,
                    **issue_data
                )

            job.mark_passed(result['summary'], {'issue_count': len(result['issues'])})

        # Update validation run counters
        validation_run = job.validation_run
        validation_run.completed_jobs += 1
        validation_run.save(update_fields=['completed_jobs'])

        return {
            'validation_job_id': validation_job_id,
            'passed': result['passed'],
            'summary': result['summary']
        }

    except Exception as e:
        logger.error(f"Validation job {validation_job_id} failed: {e}", exc_info=True)
        job.mark_failed(str(e), traceback.format_exc())

        # Update validation run
        validation_run = job.validation_run
        validation_run.failed_jobs += 1
        validation_run.save(update_fields=['failed_jobs'])

        raise


@shared_task
def process_dependent_jobs(parallel_results, validation_run_id, dependent_job_ids):
    """
    Process jobs that depend on other jobs completing first.
    """
    # Execute dependent jobs sequentially (or in groups if no inter-dependencies)
    for job_id in dependent_job_ids:
        execute_validation_job.delay(job_id)

    # Finalize after all dependent jobs complete
    finalize_validation_run.delay(validation_run_id)


@shared_task
def finalize_validation_run(parallel_results, validation_run_id):
    """
    Finalize validation run after all jobs complete.
    """
    try:
        validation_run = ValidationRun.objects.get(id=validation_run_id)

        # Check if all jobs are complete
        summary = validation_run.get_validation_summary()

        if summary['running'] > 0 or summary['pending'] > 0:
            # Not done yet, don't finalize
            logger.info(f"Validation run {validation_run_id} not ready for finalization")
            return

        # Determine final status
        if summary['failed'] > 0:
            if summary['passed'] > 0:
                validation_run.status = 'partial'
            else:
                validation_run.status = 'failed'
        else:
            validation_run.status = 'completed'

        validation_run.completed_at = timezone.now()
        validation_run.save()

        logger.info(f"Validation run {validation_run_id} finalized: {validation_run.status}")

        return {
            'validation_run_id': validation_run_id,
            'status': validation_run.status,
            'summary': summary
        }

    except Exception as e:
        logger.error(f"Failed to finalize validation run {validation_run_id}: {e}", exc_info=True)
        raise
```

#### 6. UI Components

```python
# depot/views/validation_status.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from depot.models import ValidationRun, ValidationJob, ValidationIssue

@login_required
def validation_status(request, validation_run_id):
    """
    Return validation status for HTMX polling
    """
    validation_run = get_object_or_404(ValidationRun, id=validation_run_id)

    # Check user has access to this cohort
    # ... access control logic ...

    jobs = validation_run.validation_jobs.all().order_by('created_at')

    job_statuses = []
    for job in jobs:
        config = VALIDATION_REGISTRY.get(job.validation_type, {})
        job_statuses.append({
            'id': job.id,
            'type': job.validation_type,
            'display_name': config.get('display_name', job.validation_type),
            'status': job.status,
            'progress': job.progress,
            'result_summary': job.result_summary,
            'issue_count': job.issues.count() if job.status == 'passed' else 0,
        })

    return render(request, 'partials/validation_status.html', {
        'validation_run': validation_run,
        'jobs': job_statuses,
        'progress': validation_run.progress_percentage,
    })


@login_required
def validation_issues(request, validation_job_id):
    """
    Return detailed issues for a specific validation job
    """
    validation_job = get_object_or_404(ValidationJob, id=validation_job_id)

    # Check access
    # ... access control logic ...

    # Get paginated issues
    issues = validation_job.issues.all().order_by('severity', 'row_number')

    # Filter by severity if requested
    severity_filter = request.GET.get('severity')
    if severity_filter:
        issues = issues.filter(severity=severity_filter)

    # Paginate (100 per page)
    from django.core.paginator import Paginator
    paginator = Paginator(issues, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'partials/validation_issues.html', {
        'validation_job': validation_job,
        'page_obj': page_obj,
        'total_issues': issues.count(),
    })
```

```html
<!-- depot/templates/partials/validation_status.html -->
<div
    x-data="{
        expandedJobs: {},
        toggleJob(jobId) {
            this.expandedJobs[jobId] = !this.expandedJobs[jobId];
        }
    }"
    hx-get="{% url 'validation_status' validation_run.id %}"
    hx-trigger="every 2s [validation_run.status == 'running']"
    hx-swap="outerHTML"
>
    <!-- Overall Progress -->
    <div class="mb-6">
        <div class="flex justify-between items-center mb-2">
            <h3 class="text-lg font-semibold">Validation Progress</h3>
            <span class="text-sm text-gray-600">{{ validation_run.completed_jobs }}/{{ validation_run.total_jobs }} complete</span>
        </div>

        <div class="w-full bg-gray-200 rounded-full h-4">
            <div class="bg-blue-600 h-4 rounded-full transition-all duration-300"
                 style="width: {{ progress }}%">
                <span class="text-xs text-white px-2">{{ progress }}%</span>
            </div>
        </div>
    </div>

    <!-- Individual Job Status -->
    <div class="space-y-2">
        {% for job in jobs %}
        <div class="border rounded-lg p-4
                    {% if job.status == 'passed' %}bg-green-50 border-green-200
                    {% elif job.status == 'failed' %}bg-red-50 border-red-200
                    {% elif job.status == 'running' %}bg-blue-50 border-blue-200
                    {% else %}bg-gray-50 border-gray-200{% endif %}">

            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <!-- Status Icon -->
                    {% if job.status == 'passed' %}
                        <svg class="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                        </svg>
                    {% elif job.status == 'failed' %}
                        <svg class="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                        </svg>
                    {% elif job.status == 'running' %}
                        <svg class="animate-spin w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    {% else %}
                        <svg class="w-5 h-5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>
                        </svg>
                    {% endif %}

                    <!-- Job Name -->
                    <span class="font-medium">{{ job.display_name }}</span>
                </div>

                <div class="flex items-center space-x-3">
                    <!-- Progress or Result -->
                    {% if job.status == 'running' %}
                        <span class="text-sm text-gray-600">{{ job.progress }}%</span>
                    {% elif job.status == 'passed' %}
                        {% if job.issue_count > 0 %}
                            <button
                                @click="toggleJob({{ job.id }})"
                                class="text-sm text-orange-600 hover:text-orange-700"
                            >
                                {{ job.issue_count }} issue{{ job.issue_count|pluralize }}
                            </button>
                        {% else %}
                            <span class="text-sm text-green-600">✓ Valid</span>
                        {% endif %}
                    {% elif job.status == 'failed' %}
                        <span class="text-sm text-red-600">Error</span>
                    {% endif %}
                </div>
            </div>

            <!-- Progress bar for running jobs -->
            {% if job.status == 'running' %}
            <div class="mt-2 w-full bg-gray-200 rounded-full h-2">
                <div class="bg-blue-600 h-2 rounded-full transition-all duration-300"
                     style="width: {{ job.progress }}%"></div>
            </div>
            {% endif %}

            <!-- Expandable issue details -->
            {% if job.issue_count > 0 %}
            <div x-show="expandedJobs[{{ job.id }}]"
                 x-collapse
                 class="mt-3 border-t pt-3"
                 hx-get="{% url 'validation_issues' job.id %}"
                 hx-trigger="revealed"
                 hx-swap="innerHTML">
                <div class="text-center text-gray-500 py-4">
                    <svg class="animate-spin h-5 w-5 mx-auto" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                </div>
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</div>
```

---

## Migration Strategy

### Phase 1: Parallel Implementation (2-3 weeks)
- ✅ Create new models (ValidationRun, ValidationJob, ValidationIssue)
- ✅ Build validator registry and base classes
- ✅ Implement 2-3 example validators (required fields, date ranges, enums)
- ✅ Create Celery task orchestration
- ✅ Build UI components
- ⚠️ **Keep existing Quarto workflow intact**

### Phase 2: Soft Launch (1-2 weeks)
- ✅ Add feature flag to enable new validation system
- ✅ Run both systems in parallel for comparison
- ✅ Allow users to opt-in to new UI
- ✅ Collect feedback on performance and usability

### Phase 3: Migration (1-2 weeks)
- ✅ Migrate remaining validators from R to Python
- ✅ Make new system default
- ✅ Keep Quarto as fallback option

### Phase 4: Deprecation (1-2 weeks)
- ✅ Remove Quarto dependency
- ✅ Clean up old code paths
- ✅ Archive old validation notebooks

---

## Performance Considerations

### DuckDB Optimization
```python
# Reuse existing DuckDB connection across validators
# Use read-only connections for safety
# Leverage DuckDB's query optimization

# Example: Efficient validation query
query = """
    SELECT
        ROW_NUMBER() OVER () as row_num,
        column_name,
        value
    FROM data
    WHERE value NOT IN (SELECT allowed FROM enum_values)
    LIMIT 1000
"""
```

### Celery Optimization
- Use `group` for truly parallel validations
- Use `chord` for dependency management
- Limit concurrent validation jobs to prevent resource exhaustion
- Store large result sets in database, not Celery result backend

### Database Optimization
```sql
-- Index for fast validation status lookups
CREATE INDEX idx_validation_status
ON depot_validation_job(validation_run_id, status);

-- Index for issue filtering
CREATE INDEX idx_issue_severity
ON depot_validation_issue(validation_job_id, severity);

-- Index for issue searching
CREATE INDEX idx_issue_type
ON depot_validation_issue(issue_type, severity);
```

---

## Comparison to Existing Patient ID Validation

The patient ID validation system (`depot/tasks/patient_id_extraction.py`) already demonstrates this pattern effectively:

**Similarities**:
- ✅ Async Celery tasks for extraction/validation
- ✅ Database storage of results (SubmissionPatientIDs, DataTableFilePatientIDs)
- ✅ Progress tracking and status updates
- ✅ Issue recording (invalid patient IDs)
- ✅ Reusable DuckDB connections

**What We're Adding**:
- 📈 **Registry system**: Extensible validation types beyond just patient IDs
- 📈 **Parallel execution**: Multiple independent validations run concurrently
- 📈 **Dependency management**: Some validations depend on others (chord pattern)
- 📈 **Better UI**: Live progress for ALL validation types, not just patient IDs
- 📈 **Queryable results**: Filter/search validation issues across all types
- 📈 **Retry capability**: Re-run individual validations without re-upload

---

## Success Metrics

| Metric | Current (Quarto) | Target (New System) |
|--------|------------------|---------------------|
| Time to first feedback | 5-10 minutes (full notebook) | <30 seconds (first validation) |
| User visibility | Black box | Real-time progress per validation |
| Error recovery | Re-upload file | Retry individual validation |
| Result queryability | None (HTML only) | Full database queries |
| Parallel execution | Sequential | Concurrent independent validations |
| Extension difficulty | Modify R notebook | Add validator class + registry entry |

---

## Security Considerations

### PHI Handling
- All validations use read-only DuckDB connections
- Validation results stored in database with cohort access control
- Issue details limited to prevent PHI exposure in UI
- Full audit trail via existing PHIFileTracking system

### Access Control
```python
# depot/views/validation_status.py
def validation_status(request, validation_run_id):
    validation_run = get_object_or_404(ValidationRun, id=validation_run_id)

    # Ensure user has access to this cohort
    content_object = validation_run.content_object
    if hasattr(content_object, 'cohort'):
        if not request.user.can_access_cohort(content_object.cohort):
            raise PermissionDenied("You do not have access to this cohort's data")
```

---

## Future Enhancements

### 1. Custom Validation Rules
Allow cohorts to define custom validation rules via admin UI

### 2. Machine Learning Validations
- Anomaly detection
- Pattern recognition
- Predictive validation

### 3. Cross-Submission Analysis
- Compare current submission to historical data
- Identify trends and outliers
- Quality control metrics

### 4. API Access
- REST API for validation status
- Webhook notifications for completion
- Integration with external systems

---

## Related Documentation

- `upload-submission-workflow.md` - Multi-file submission system
- `patient-id-validation-system.md` - Existing patient ID validation (inspiration)
- `storage-manager-abstraction.md` - File storage patterns
- `PHIFileTracking-system.md` - HIPAA audit trail
- `../CLAUDE.md` - Main development guide

---

## Approval and Next Steps

**Stakeholder Review Required**:
- [ ] Development team approval
- [ ] UX review of proposed interface
- [ ] Performance testing plan approval
- [ ] Security review of PHI handling

**Implementation Phases**:
1. Phase 1: Parallel implementation (2-3 weeks)
2. Phase 2: Soft launch with opt-in (1-2 weeks)
3. Phase 3: Full migration (1-2 weeks)
4. Phase 4: Deprecation of Quarto (1-2 weeks)

**Estimated Total Timeline**: 6-9 weeks

---

## Questions for Stakeholders

1. **Validator Priority**: Which validation types should be implemented first?
2. **UI Preferences**: Any specific UX requirements or preferences?
3. **Performance Targets**: Any specific performance benchmarks beyond those listed?
4. **R Integration**: Should we keep any R-based validations or migrate all to Python?
5. **Reporting**: Do we still need HTML reports, or is the live UI sufficient?

