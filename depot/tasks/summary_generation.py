"""
Celery tasks to generate validation summaries.

These tasks ensure summaries are generated asynchronously as validation
completes, keeping the workflow event-driven.
"""

import logging

from celery import shared_task

from depot.models import (
    ValidationVariable,
    ValidationRun,
    CohortSubmission,
    DataTableFile,
)
from depot.services.variable_summary_service import VariableSummaryService
from depot.services.data_table_summary_service import DataTableSummaryService
from depot.services.submission_summary_service import SubmissionSummaryService

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_variable_summary_task(self, validation_variable_id: int) -> int:
    """Generate a VariableSummary for a single validation variable."""
    try:
        variable = ValidationVariable.objects.select_related('validation_run').get(id=validation_variable_id)
    except ValidationVariable.DoesNotExist:
        logger.warning("VariableSummary task skipped: ValidationVariable %s not found", validation_variable_id)
        return validation_variable_id

    service = VariableSummaryService()
    service.generate_summary(variable)
    return validation_variable_id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_data_table_summary_task(self, validation_run_id: int) -> int:
    """Generate DataTableSummary for the provided validation run."""
    try:
        run = ValidationRun.objects.select_related('content_type').get(id=validation_run_id)
    except ValidationRun.DoesNotExist:
        logger.warning("DataTableSummary task skipped: ValidationRun %s not found", validation_run_id)
        return validation_run_id

    # Ensure all completed variables have summary stats before aggregation
    pending_summaries = run.variables.filter(status='completed', summary_stats__isnull=True)
    if pending_summaries.exists():
        logger.debug(
            "Deferring DataTableSummary for run %s; %s variable summaries still pending",
            validation_run_id,
            pending_summaries.count(),
        )
        raise self.retry(countdown=5)

    service = DataTableSummaryService()
    summary = service.generate_summary(run)

    # TODO: DuckDB cleanup disabled for now
    # Need to review protocol to understand all cross-file dependencies
    # Potential optimization: Use stored patient IDs instead of requiring DuckDB
    # for cross-file validation
    logger.debug(f"DuckDB cleanup disabled - keeping file for run {validation_run_id}")

    # Kick off submission summary if this run is tied to a submission
    submission = None
    try:
        model_class = run.content_type.model_class() if run.content_type else None
        if model_class is DataTableFile:
            data_file = run.content_object
            if data_file and getattr(data_file, 'data_table', None):
                submission = getattr(data_file.data_table, 'submission', None)
    except Exception as exc:
        logger.debug("Unable to resolve submission for ValidationRun %s: %s", validation_run_id, exc)

    if submission is not None:
        generate_submission_summary_task.delay(submission.id)

    return summary.id


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def generate_submission_summary_task(self, submission_id: int) -> int:
    """Generate SubmissionSummary for a submission."""
    try:
        submission = CohortSubmission.objects.get(id=submission_id)
    except CohortSubmission.DoesNotExist:
        logger.warning("SubmissionSummary task skipped: CohortSubmission %s not found", submission_id)
        return submission_id

    service = SubmissionSummaryService()
    summary = service.generate_summary(submission)
    return summary.id
