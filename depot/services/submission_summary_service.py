"""
Aggregate validation metrics across an entire submission.

The submission summary collects table-level summaries (DataTableSummary)
to provide a quick snapshot of completeness and data quality for the whole
submission.
"""
import logging
from statistics import mean
from typing import Iterable

from depot.models import (
    CohortSubmission,
    SubmissionSummary,
    DataTableSummary,
)

logger = logging.getLogger(__name__)


class SubmissionSummaryService:
    """Create or update SubmissionSummary for a cohort submission."""

    def generate_summary(self, submission: CohortSubmission) -> SubmissionSummary:
        if submission is None:
            raise ValueError("submission is required")

        summary, _created = SubmissionSummary.objects.get_or_create(
            submission=submission,
            defaults={'validation_state': getattr(submission, 'validation_summary', None)},
        )

        if summary.validation_state_id is None and hasattr(submission, 'validation_summary'):
            summary.validation_state = submission.validation_summary

        data_tables = submission.data_tables.select_related(
            'data_file_type'
        ).all()

        summary.total_tables = data_tables.count()

        summaries = self._collect_data_table_summaries(data_tables)
        summary.tables_validated = len(summaries)
        summary.tables_with_errors = sum(
            1 for item in summaries if item.variables_with_issues > 0
        )
        summary.tables_with_warnings = sum(
            1 for item in summaries if item.variables_with_warnings > 0 and item.variables_with_issues == 0
        )

        completeness = [item.overall_completeness_pct for item in summaries if item.overall_completeness_pct]
        validity = [item.overall_validity_pct for item in summaries if item.overall_validity_pct]

        summary.overall_completeness_pct = round(mean(completeness), 2) if completeness else 0.0
        summary.overall_validity_pct = round(mean(validity), 2) if validity else 0.0

        summary.total_rows = sum(item.total_rows for item in summaries if item.total_rows)
        summary.total_variables = sum(item.total_columns for item in summaries)

        summary.save()
        return summary

    def _collect_data_table_summaries(self, data_tables) -> Iterable[DataTableSummary]:
        """Fetch DataTableSummary for each table's latest validation run."""
        summaries = []
        seen_run_ids = set()

        for table in data_tables:
            current_files = table.files.filter(is_current=True).select_related('latest_validation_run')
            for data_file in current_files:
                run = data_file.latest_validation_run
                if not run or run.id in seen_run_ids:
                    continue

                summary = getattr(run, 'summary_stats', None)
                if summary:
                    summaries.append(summary)
                    seen_run_ids.add(run.id)

        return summaries
