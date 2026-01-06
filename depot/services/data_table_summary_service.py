"""
Aggregate validation metrics at the data-table (ValidationRun) level.

This service rolls up per-variable validation results into a single
`DataTableSummary` record that captures table-level quality metrics.
"""
import logging
from statistics import mean

from django.db.models import Max

from depot.models import (
    DataTableSummary,
    ValidationRun,
)

logger = logging.getLogger(__name__)


class DataTableSummaryService:
    """Create or update `DataTableSummary` instances for a validation run."""

    def generate_summary(self, validation_run: ValidationRun) -> DataTableSummary:
        """
        Aggregate metrics for a validation run.

        Args:
            validation_run: The run we are summarizing.

        Returns:
            Persisted `DataTableSummary`.
        """
        if validation_run is None:
            raise ValueError("validation_run is required")

        summary, _created = DataTableSummary.objects.get_or_create(
            validation_run=validation_run,
        )

        variables = (
            validation_run.variables
            .select_related('summary_stats')
            .all()
        )

        total_variables = variables.count()
        summary.total_variables = total_variables

        if total_variables == 0:
            summary.variables_validated = 0
            summary.variables_with_issues = 0
            summary.variables_with_warnings = 0
            summary.overall_completeness_pct = 0.0
            summary.overall_validity_pct = 0.0
            summary.total_rows = 0
            summary.total_columns = 0
            summary.last_variable_validated_at = None
            summary.save()
            return summary

        summary.variables_validated = variables.exclude(status='pending').count()
        summary.variables_with_issues = variables.filter(error_count__gt=0).count()
        summary.variables_with_warnings = variables.filter(warning_count__gt=0).count()

        completeness_ratios = []
        validity_ratios = []
        total_rows = 0

        for variable in variables:
            total = variable.total_rows or 0
            nulls = variable.null_count or 0
            empty = variable.empty_count or 0
            valid = variable.valid_count or 0

            if total > 0:
                completeness = (total - nulls - empty) / total
                completeness_ratios.append(completeness)
                validity = valid / total
                validity_ratios.append(validity)
                total_rows = max(total_rows, total)

        summary.overall_completeness_pct = round(
            mean(completeness_ratios) * 100, 2
        ) if completeness_ratios else 0.0
        summary.overall_validity_pct = round(
            mean(validity_ratios) * 100, 2
        ) if validity_ratios else 0.0

        summary.total_rows = total_rows
        summary.total_columns = total_variables

        summary.last_variable_validated_at = (
            variables.aggregate(Max('completed_at'))['completed_at__max']
        )

        summary.save()
        return summary
