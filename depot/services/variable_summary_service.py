"""
Variable summary generation service.

This service bridges the validation system with the existing summarizer
framework by loading data from DuckDB, executing summarizers, and storing
the results in the new VariableSummary model.
"""
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from depot.data.definition_loader import get_definition_for_type
from depot.data.summarizer import Summarizer as SummarizerOrchestrator
from depot.models import VariableSummary

logger = logging.getLogger(__name__)


class VariableSummaryService:
    """
    Generate VariableSummary records from validation output.

    Workflow:
        1. Retrieve series for the variable from DuckDB
        2. Load JSON definition to determine summarizers
        3. Execute summarizers via existing orchestrator
        4. Persist results on VariableSummary
    """

    NUMERIC_SUMMARIZER_FIELDS = {
        'mean': 'mean_value',
        'median': 'median_value',
        'min': 'min_value',
        'max': 'max_value',
        'sd': 'std_dev',
    }

    CHART_SUMMARIZERS = {'histogram', 'bar_chart', 'date_histogram', 'box_plot'}

    def __init__(self):
        self.summarizer = SummarizerOrchestrator()

    def generate_summary(self, validation_variable):
        """
        Create or update the VariableSummary for a ValidationVariable.

        Returns:
            VariableSummary instance (saved)
        """
        summary, _ = VariableSummary.objects.get_or_create(
            validation_variable=validation_variable
        )

        # Mirror baseline counts from validation results
        summary.total_count = validation_variable.total_rows
        summary.null_count = validation_variable.null_count
        summary.empty_count = validation_variable.empty_count
        summary.valid_count = validation_variable.valid_count
        summary.invalid_count = validation_variable.invalid_count
        summary.warning_count = validation_variable.warning_count
        summary.error_count = validation_variable.error_count

        column_name = validation_variable.column_name

        try:
            series = self._load_series_from_duckdb(validation_variable, column_name)
            if series is None:
                summary.save(update_fields=self._base_update_fields())
                return summary

            variable_definition = self._get_variable_definition(validation_variable, column_name)
            if not variable_definition:
                logger.warning(
                    "No definition found for %s on run %s; skipping summarizers",
                    column_name,
                    validation_variable.validation_run_id,
                )
                summary.save(update_fields=self._base_update_fields())
                return summary

            df = pd.DataFrame({column_name: series})

            summarizer_payload = self._run_summarizers(variable_definition, df)
            self._apply_summarizer_results(summary, summarizer_payload, series)

            summary.save()
            return summary

        except Exception as exc:
            logger.exception(
                "Failed to generate summary for ValidationVariable %s: %s",
                validation_variable.id,
                exc,
            )
            summary.save(update_fields=self._base_update_fields())
            return summary

    def _run_summarizers(self, variable_definition: Dict, df: pd.DataFrame) -> List[Dict]:
        """Execute summarizers for a single variable."""

        class _SingleVariableDefinition:
            def __init__(self, definition):
                self.definition = [definition]

        orchestrator_input = _SingleVariableDefinition(variable_definition)
        summaries = self.summarizer.handle(orchestrator_input, df)
        column_name = variable_definition['name']
        column_summary = summaries.get(column_name, {})
        return column_summary.get('results', [])

    def _apply_summarizer_results(self, summary: VariableSummary, results: List[Dict], series: pd.Series) -> None:
        """Persist summarizer output onto the model."""
        chart_payload: Dict[str, Dict] = {}

        # Compute values that do not rely on summarizers
        summary.unique_count = int(series.nunique(dropna=True))

        non_null_series = series.dropna()
        non_empty_series = non_null_series[non_null_series.astype(str) != '']
        if not non_empty_series.empty:
            mode_series = non_empty_series.mode()
            if not mode_series.empty:
                summary.mode_value = mode_series.iloc[0]
                summary.mode_count = int((non_empty_series == summary.mode_value).sum())

        # For string variables, also capture random samples
        # Get variable type from validation_variable
        variable_type = summary.validation_variable.column_type
        if variable_type == 'string' and not non_empty_series.empty:
            # Get top 20 values to exclude from random samples
            top_values = set(non_empty_series.value_counts().head(20).index.tolist())

            # Filter out top values for random sampling
            non_top_series = non_empty_series[~non_empty_series.isin(top_values)]

            # Get up to 30 random samples from non-top values
            if not non_top_series.empty:
                n_samples = min(30, len(non_top_series))
                random_samples = non_top_series.sample(n=n_samples, random_state=42).tolist()
            else:
                # If all values are in top 20, sample from all values
                n_samples = min(30, len(non_empty_series))
                random_samples = non_empty_series.sample(n=n_samples, random_state=42).tolist()

            # Store random samples in chart_data under a 'random_samples' key
            # We'll use chart_data since it's a JSONField that can hold arbitrary data
            if not hasattr(summary, '_temp_random_samples'):
                summary._temp_random_samples = random_samples

        for result in results:
            name = result.get('name')
            report = result.get('report') or {}
            if not isinstance(report, dict):
                continue

            if report.get('status') != 'success':
                continue

            value = report.get('value')

            if name in self.NUMERIC_SUMMARIZER_FIELDS and value is not None:
                field = self.NUMERIC_SUMMARIZER_FIELDS[name]
                summary.__setattr__(field, self._safe_float(value))
            elif name == 'examples' and isinstance(value, dict):
                summary.example_values = [
                    {'value': key, 'count': count} for key, count in value.items()
                ]
            elif name == 'unique' and value is not None and value > 0:
                # Only override pandas calculation if summarizer returns a positive value
                # This prevents 0 or invalid results from overwriting correct pandas nunique()
                summary.unique_count = int(value)
            elif name == 'mode' and value is not None:
                summary.mode_value = value
            elif name in self.CHART_SUMMARIZERS and report.get('value_rendered'):
                chart_payload[name] = {
                    'display_name': result.get('display_name'),
                    'render': report.get('value_rendered'),
                }

        # Add random samples to chart_data if we have them
        if hasattr(summary, '_temp_random_samples'):
            chart_payload['random_samples'] = summary._temp_random_samples
            delattr(summary, '_temp_random_samples')

        if chart_payload:
            existing = summary.chart_data or {}
            existing.update(chart_payload)
            summary.chart_data = existing

    def _load_series_from_duckdb(self, validation_variable, column_name: str) -> Optional[pd.Series]:
        """Fetch the column data from DuckDB as a pandas Series."""
        run = validation_variable.validation_run
        duckdb_path = run.duckdb_path

        if not duckdb_path:
            logger.warning(
                "ValidationRun %s has no duckdb_path; cannot generate summaries",
                run.id,
            )
            return None

        with self._duckdb_connection(duckdb_path) as conn:
            try:
                # Check if column exists first to avoid noisy DuckDB errors
                columns = conn.execute("PRAGMA table_info(data)").fetchall()
                column_names = {col[1].lower() for col in columns}

                if column_name.lower() not in column_names:
                    logger.debug(
                        "Column %s not found in uploaded file for run %s (skipping summary)",
                        column_name,
                        run.id,
                    )
                    return None

                # Column exists, fetch the data
                query = f'SELECT "{column_name}" FROM data'
                df = conn.execute(query).fetch_df()

            except duckdb.Error as exc:
                logger.warning(
                    "DuckDB error while loading column %s for run %s: %s",
                    column_name,
                    run.id,
                    exc,
                )
                return None

        if column_name not in df.columns:
            logger.warning(
                "Column %s missing from DuckDB data for run %s",
                column_name,
                run.id,
            )
            return None

        return df[column_name]

    def _get_variable_definition(self, validation_variable, column_name: str) -> Optional[Dict]:
        """Return the JSON definition entry for the variable."""
        run = validation_variable.validation_run
        data_file_type = run.data_file_type
        if not data_file_type:
            return None

        try:
            definition = get_definition_for_type(data_file_type.name)
        except ValueError:
            logger.warning("Definition not found for data file type %s", data_file_type.name)
            return None

        for variable_def in definition.get_definition():
            if variable_def.get('name') == column_name:
                return variable_def

        return None

    @contextmanager
    def _duckdb_connection(self, duckdb_path: str):
        """Context manager wrapper for DuckDB connections."""
        conn = duckdb.connect(duckdb_path, read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _safe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _base_update_fields():
        return [
            'total_count',
            'null_count',
            'empty_count',
            'valid_count',
            'invalid_count',
            'warning_count',
            'error_count',
            'updated_at',
        ]
