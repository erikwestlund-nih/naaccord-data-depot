import os
import json
import shutil
import tempfile

import duckdb
from django.test import SimpleTestCase

from depot.validators.variable_validator import VariableValidator


class VariableValidatorCategoricalSummaryTests(SimpleTestCase):
    databases = {}

    def _create_duckdb_with_column(self, column_name: str, values):
        """Create a temporary DuckDB file with a single column and values."""
        temp_dir = tempfile.mkdtemp(prefix="validator-categorical-")
        db_path = os.path.join(temp_dir, "data.duckdb")

        conn = duckdb.connect(db_path)
        conn.execute(f'CREATE TABLE data ({column_name} VARCHAR)')
        conn.executemany(
            f'INSERT INTO data VALUES (?)',
            [(value,) for value in values]
        )
        conn.close()

        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return db_path

    def test_enum_summary_exposes_raw_counts_and_chart_data(self):
        db_path = self._create_duckdb_with_column(
            "presentSex",
            [
                "Female",
                "Male",
                "Male",
                "Unknown",
                "",
                None,
            ],
        )

        variable_def = {
            'name': 'presentSex',
            'type': 'enum',
            'allowed_values': ["Female", "Male", "Intersexed"],
            'summarizers': ['bar_chart'],
        }

        with VariableValidator(db_path, variable_def, None) as validator:
            results = validator.validate()

        summary = results['summary']

        # Raw counts maintain literal submissions (excluding NULL) and include blanks.
        raw_counts = {row['value']: row['count'] for row in summary['raw_counts']}
        self.assertEqual(raw_counts['Male'], 2)
        self.assertEqual(raw_counts['Female'], 1)
        self.assertEqual(raw_counts['Unknown'], 1)
        self.assertEqual(raw_counts['(blank)'], 1)

        # Chart data should exist and align with raw counts for allowed values.
        chart_data = summary['chart_data']
        chart_map = dict(zip(chart_data['labels'], chart_data['values']))
        self.assertEqual(chart_map['Male'], 2)
        self.assertEqual(chart_map['Female'], 1)
        self.assertEqual(chart_map['Unknown'], 1)
        self.assertEqual(chart_data['labels_json'], json.dumps(chart_data['labels']))
        self.assertEqual(chart_data['values_json'], json.dumps(chart_data['values']))

        # Summary metadata exposes totals for templates.
        self.assertEqual(summary['unique_raw_values'], 4)
        self.assertEqual(summary['raw_total'], 5)

    def test_boolean_summary_normalizes_synonyms_and_preserves_raw_values(self):
        db_path = self._create_duckdb_with_column(
            "hispanic",
            [
                "Yes",
                "No",
                "Unknown",
                "yes",
                "NO",
                "",
                None,
                "1",
                "Maybe",
            ],
        )

        variable_def = {
            'name': 'hispanic',
            'type': 'boolean',
            'allowed_values': {'true': ['Yes'], 'false': ['No'], 'Unknown': ['Unknown']},
        }

        with VariableValidator(db_path, variable_def, None) as validator:
            results = validator.validate()

        summary = results['summary']

        # Normalized counts collapse synonyms (e.g., Yes/yes/1) and remain accessible for templates.
        normalized_counts = {
            entry['label']: entry['count']
            for entry in summary['definition_counts']
        }
        self.assertEqual(normalized_counts['Yes'], 3)
        self.assertEqual(normalized_counts['No'], 2)
        self.assertEqual(normalized_counts['Unknown'], 1)

        # Explicit helper counts still align with normalized values.
        self.assertEqual(summary['true_count'], 3)
        self.assertEqual(summary['false_count'], 2)
        self.assertEqual(summary['unknown_count'], 1)

        # Raw counts list every literal submission so the UI can surface unexpected labels.
        raw_counts = {row['raw']: row['count'] for row in summary['raw_counts']}
        self.assertEqual(raw_counts['Yes'], 1)
        self.assertEqual(raw_counts['yes'], 1)
        self.assertEqual(raw_counts['NO'], 1)
        self.assertEqual(raw_counts['Maybe'], 1)
        self.assertEqual(raw_counts['1'], 1)

        # Unexpected values capture entries that do not map to the definition or defaults.
        unexpected = dict(summary['unexpected_values'])
        self.assertEqual(unexpected['Maybe'], 1)
        self.assertEqual(unexpected['(blank)'], 1)

        # Chart data remains available for Plotly visualisations.
        chart_data = summary['chart_data']
        chart_map = dict(zip(chart_data['labels'], chart_data['values']))
        self.assertEqual(chart_map['Yes'], 3)
        self.assertEqual(chart_map['No'], 2)
        self.assertEqual(chart_map['Unknown'], 1)
        self.assertEqual(chart_data['labels_json'], json.dumps(chart_data['labels']))
        self.assertEqual(chart_data['values_json'], json.dumps(chart_data['values']))

        # Meta counts support template guards.
        self.assertEqual(summary['unique_raw_values'], len(raw_counts))
        self.assertEqual(summary['raw_total'], sum(raw_counts.values()))
