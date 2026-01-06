"""
Summary models for the validation system.

These models capture aggregated statistics for the three levels of the
validation hierarchy:

Submission -> Data table (ValidationRun) -> Variable

They replace the ad-hoc JSON storage that previously lived on validation
models and provide queryable structures we can evolve over time.
"""
from django.db import models

from depot.models.basemodel import BaseModel


class VariableSummary(BaseModel):
    """
    Summary statistics for a single ValidationVariable.

    We keep the relationship as OneToOne so the validation flow can
    create/update summaries without impacting the existing validation
    objects. The majority of numeric fields are nullable because they
    only apply to certain data types.
    """

    validation_variable = models.OneToOneField(
        'ValidationVariable',
        on_delete=models.CASCADE,
        related_name='summary_stats',
    )

    # Universal counts
    total_count = models.IntegerField(default=0)
    unique_count = models.IntegerField(default=0)
    null_count = models.IntegerField(default=0)
    empty_count = models.IntegerField(default=0)

    # Validation quality metrics
    valid_count = models.IntegerField(default=0)
    invalid_count = models.IntegerField(default=0)
    warning_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)

    # Numeric statistics
    mean_value = models.FloatField(null=True, blank=True)
    median_value = models.FloatField(null=True, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    std_dev = models.FloatField(null=True, blank=True)

    # Categorical statistics
    mode_value = models.CharField(max_length=255, null=True, blank=True)
    mode_count = models.IntegerField(null=True, blank=True)

    # Chart data / visualizations (histograms, bar charts, etc.)
    chart_data = models.JSONField(default=dict, blank=True)

    # Example values to display in the UI
    example_values = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'depot_variable_summaries'
        ordering = ['-created_at']

    def __str__(self):
        return f"VariableSummary for variable {self.validation_variable_id}"


class DataTableSummary(BaseModel):
    """
    Aggregated statistics for a single ValidationRun (data table).
    """

    validation_run = models.OneToOneField(
        'ValidationRun',
        on_delete=models.CASCADE,
        related_name='summary_stats',
    )

    # Aggregate counts
    total_variables = models.IntegerField(default=0)
    variables_validated = models.IntegerField(default=0)
    variables_with_issues = models.IntegerField(default=0)
    variables_with_warnings = models.IntegerField(default=0)

    # Quality metrics
    overall_completeness_pct = models.FloatField(default=0.0)
    overall_validity_pct = models.FloatField(default=0.0)

    # Data characteristics
    total_rows = models.IntegerField(default=0)
    total_columns = models.IntegerField(default=0)

    # Timestamps of the validations used in aggregation
    last_variable_validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'depot_datatable_summaries'
        ordering = ['-created_at']

    def __str__(self):
        return f"DataTableSummary for run {self.validation_run_id}"


class SubmissionSummary(BaseModel):
    """
    Aggregated statistics for an entire submission.
    """

    submission = models.OneToOneField(
        'CohortSubmission',
        on_delete=models.CASCADE,
        related_name='summary_stats',
    )

    validation_state = models.OneToOneField(
        'SubmissionValidation',
        on_delete=models.CASCADE,
        related_name='statistics',
        null=True,
        blank=True,
        help_text="Optional link back to validation status tracking",
    )

    # Aggregate counts
    total_tables = models.IntegerField(default=0)
    tables_validated = models.IntegerField(default=0)
    tables_with_errors = models.IntegerField(default=0)
    tables_with_warnings = models.IntegerField(default=0)

    # Quality metrics
    overall_completeness_pct = models.FloatField(default=0.0)
    overall_validity_pct = models.FloatField(default=0.0)

    # Data characteristics
    total_rows = models.IntegerField(default=0)
    total_variables = models.IntegerField(default=0)

    class Meta:
        db_table = 'depot_submission_summaries'
        ordering = ['-created_at']

    def __str__(self):
        return f"SubmissionSummary for submission {self.submission_id}"
