"""
Variable Validator - Executes validation for a single variable/column.

This module validates one column at a time using the definition and DuckDB.
"""
import json
import logging
import duckdb
from datetime import date
from collections import OrderedDict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class VariableValidator:
    """
    Validates a single variable (column) from the data.

    Uses DuckDB for efficient querying and validation.
    """

    def __init__(self, duckdb_path: str, variable_def: Dict, validation_variable, submission=None, data_file=None):
        """
        Initialize validator for a single variable.

        Args:
            duckdb_path: Path to DuckDB file with data
            variable_def: Variable definition from JSON
            validation_variable: ValidationVariable model instance
            submission: Submission instance (optional, needed for cross-file validation)
            data_file: DataTableFile instance (optional, needed for cross-file validation)
        """
        self.duckdb_path = duckdb_path
        self.variable_def = variable_def
        self.validation_variable = validation_variable
        self.column_name = variable_def['name']
        self.column_type = variable_def.get('type', 'string')
        self.conn = None
        self.is_combined_duckdb = False  # Will be set when connection opens
        self.submission = submission
        self.data_file = data_file

    def __enter__(self):
        """Context manager entry - open DuckDB connection."""
        self.conn = duckdb.connect(self.duckdb_path, read_only=True)
        # Check if this is a combined DuckDB (has __source_file_id column)
        self.is_combined_duckdb = self._has_source_metadata()
        if self.is_combined_duckdb:
            logger.info(f"Detected combined DuckDB file for validation of {self.column_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        if self.conn:
            self.conn.close()
        return False

    def validate(self) -> Dict:
        """
        Run all validations for this variable.

        Returns:
            dict: {
                'passed': bool,
                'total_rows': int,
                'null_count': int,
                'empty_count': int,
                'valid_count': int,
                'invalid_count': int,
                'warning_count': int,
                'error_count': int,
                'checks': [...],
                'summary': dict  # Type-specific summary statistics
            }
        """
        results = {
            'passed': True,
            'total_rows': 0,
            'null_count': 0,
            'empty_count': 0,
            'valid_count': 0,
            'invalid_count': 0,
            'warning_count': 0,
            'error_count': 0,
            'checks': [],
            'summary': {}
        }

        try:
            # Check if column exists
            column_exists = self._column_exists()

            if not column_exists:
                # Check if this column has conditional validators
                validators = self.variable_def.get('validators', [])
                has_conditional = any(
                    (isinstance(v, dict) and v.get('name') in ['required_when', 'forbidden_when']) or
                    (isinstance(v, str) and v in ['required_when', 'forbidden_when'])
                    for v in validators
                )

                if has_conditional:
                    # Column doesn't exist, but might be valid due to conditional logic
                    # Run conditional validators with empty stats
                    stats = {'total_rows': 0, 'null_count': 0, 'empty_count': 0}
                    results.update(stats)

                    for validator_def in validators:
                        check_result = self._run_validator(validator_def, stats, column_exists=False)
                        results['checks'].append(check_result)

                        if not check_result['passed']:
                            if check_result['severity'] == 'error':
                                results['error_count'] += 1
                                results['passed'] = False
                            else:
                                results['warning_count'] += 1

                    return results
                else:
                    # No conditional validators, missing column is an error
                    results['passed'] = False
                    results['error_count'] = 1
                    results['checks'].append({
                        'check_type': 'column_exists',
                        'passed': False,
                        'severity': 'error',
                        'message': f"Column '{self.column_name}' not found in data",
                        'details': {}
                    })
                    return results

            # Get basic stats
            stats = self._get_basic_stats()
            results.update(stats)

            # Run validators from definition
            validators = self.variable_def.get('validators', [])
            for validator_def in validators:
                check_result = self._run_validator(validator_def, stats, column_exists=True)
                results['checks'].append(check_result)

                if not check_result['passed']:
                    if check_result['severity'] == 'error':
                        results['error_count'] += 1
                        results['passed'] = False
                    else:
                        results['warning_count'] += 1

            # Calculate valid/invalid counts
            results['invalid_count'] = results['error_count']
            results['valid_count'] = results['total_rows'] - results['null_count'] - results['invalid_count']

            # Generate type-specific summary statistics
            results['summary'] = self._generate_summary(stats)

            return results

        except Exception as e:
            logger.error(f"Validation failed for {self.column_name}: {e}", exc_info=True)
            results['passed'] = False
            results['error_count'] = 1
            results['checks'].append({
                'check_type': 'validation_error',
                'passed': False,
                'severity': 'error',
                'message': f"Validation error: {str(e)}",
                'details': {}
            })
            return results

    def _column_exists(self) -> bool:
        """Check if column exists in data."""
        try:
            result = self.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'data' AND column_name = ?",
                [self.column_name]
            ).fetchone()
            return result is not None
        except Exception:
            return False

    def _has_source_metadata(self) -> bool:
        """Check if DuckDB has source file metadata columns (indicating combined file)."""
        try:
            result = self.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'data' AND column_name = '__source_file_id'"
            ).fetchone()
            return result is not None
        except Exception:
            return False

    def _get_basic_stats(self) -> Dict:
        """Get basic statistics for the column."""
        query = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(CASE WHEN "{self.column_name}" IS NULL THEN 1 END) as null_count,
                COUNT(CASE WHEN CAST("{self.column_name}" AS VARCHAR) = '' THEN 1 END) as empty_count
            FROM data
        """

        result = self.conn.execute(query).fetchone()
        return {
            'total_rows': result[0],
            'null_count': result[1],
            'empty_count': result[2]
        }

    @staticmethod
    def _normalize_token(value: str, case_sensitive: bool) -> str:
        if value is None:
            return ""
        value = value.strip()
        return value if case_sensitive else value.lower()

    def _fetch_raw_value_counts(self) -> List[Dict[str, object]]:
        """Return trimmed raw value counts for the column."""
        query = f"""
            SELECT trim(CAST("{self.column_name}" AS TEXT)) AS raw_value,
                   COUNT(*) AS count
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
            GROUP BY trim(CAST("{self.column_name}" AS TEXT))
        """

        rows = self.conn.execute(query).fetchall()
        counts: List[Dict[str, object]] = []
        for raw_value, count in rows:
            value = (raw_value or "").strip()
            display = value if value else "(blank)"
            counts.append({
                "raw": value,
                "display": display,
                "count": count or 0
            })

        counts.sort(key=lambda item: (-item["count"], item["display"]))
        return counts

    def _build_categorical_summary(
        self,
        raw_counts: List[Dict[str, object]],
        allowed_values,
        case_sensitive: bool = False,
        default_synonyms: Optional[Dict[str, List[str]]] = None,
    ) -> Dict:
        """Normalize raw value counts against allowed categories."""

        entries: List[Dict[str, object]] = []

        def normalize_iterable(values) -> List[str]:
            if values is None:
                return []
            if not isinstance(values, (list, tuple, set)):
                values = [values]
            normalized: List[str] = []
            for value in values:
                value_str = "" if value is None else str(value)
                normalized.append(value_str)
            return normalized

        def add_entry(label, synonyms=None, display: Optional[str] = None):
            label_str = "" if label is None else str(label)
            normalized = self._normalize_token(label_str, case_sensitive)

            synonym_values = normalize_iterable(synonyms)
            normalized_synonyms = {
                self._normalize_token(str(value), case_sensitive)
                for value in synonym_values
            }
            normalized_synonyms.add(normalized)

            display_candidate: Optional[str] = display
            if display_candidate is None:
                for raw_value in synonym_values:
                    if raw_value and raw_value.strip():
                        display_candidate = raw_value
                        break
            if display_candidate is None:
                display_candidate = label_str

            display_value = "" if display_candidate is None else str(display_candidate)
            if not display_value.strip():
                display_value = "(blank)"

            for entry in entries:
                if entry["normalized"] == normalized:
                    entry["synonyms"].update(normalized_synonyms)
                    if (
                        (not entry["display"] or entry["display"] == "(blank)")
                        and display_value
                    ):
                        entry["display"] = display_value
                    return

            entries.append({
                "original": label_str,
                "normalized": normalized,
                "display": display_value,
                "synonyms": normalized_synonyms,
            })

        if isinstance(allowed_values, dict):
            for key, spec in allowed_values.items():
                if isinstance(spec, dict):
                    synonyms = (
                        spec.get("synonyms")
                        or spec.get("values")
                        or spec.get("aliases")
                        or spec.get("options")
                    )
                    display = spec.get("label") or spec.get("description")
                else:
                    synonyms = spec
                    display = None
                add_entry(key, synonyms or [key], display)
        elif isinstance(allowed_values, list):
            for value in allowed_values:
                display = None
                synonyms = None
                label = value
                if isinstance(value, dict):
                    label = (
                        value.get("value")
                        or value.get("key")
                        or value.get("label")
                        or value.get("name")
                    )
                    synonyms = (
                        value.get("synonyms")
                        or value.get("values")
                        or value.get("aliases")
                    )
                    display = value.get("label") or value.get("description")
                    if label is None and display is not None:
                        label = display
                add_entry(label, synonyms or [label], display)

        default_synonyms = default_synonyms or {}
        for key, synonyms in default_synonyms.items():
            normalized_key = str(key)
            display = None if case_sensitive else normalized_key.title()
            add_entry(normalized_key, synonyms, display)

        if not entries:
            for item in raw_counts:
                add_entry(item["raw"], [item["raw"]], item["display"])

        synonyms_lookup = {}
        counts_by_key = {}
        for entry in entries:
            normalized = entry["normalized"]
            counts_by_key[normalized] = 0
            for synonym in entry["synonyms"]:
                synonyms_lookup[synonym] = normalized

        unexpected: Dict[str, int] = {}
        for item in raw_counts:
            normalized_value = self._normalize_token(item["raw"], case_sensitive)
            key = synonyms_lookup.get(normalized_value)
            count = item["count"]
            if key is not None:
                counts_by_key[key] += count
            else:
                display = item["display"]
                unexpected[display] = unexpected.get(display, 0) + count

        normalized_entries = []
        for entry in entries:
            normalized = entry["normalized"]
            normalized_entries.append({
                "key": normalized,
                "original_key": entry["original"],
                "label": entry["display"],
                "count": counts_by_key.get(normalized, 0),
            })

        unexpected_list = sorted(unexpected.items(), key=lambda item: (-item[1], item[0]))
        raw_counts_display = [
            {
                "value": item["display"],
                "raw": item["raw"],
                "count": item["count"],
            }
            for item in raw_counts
        ]

        labels = [entry["label"] for entry in normalized_entries if entry["count"] > 0]
        values = [entry["count"] for entry in normalized_entries if entry["count"] > 0]
        chart_data = None
        if labels:
            chart_data = {
                "labels": labels,
                "values": values,
                "labels_json": json.dumps(labels),
                "values_json": json.dumps(values),
            }

        return {
            "normalized_entries": normalized_entries,
            "counts_by_key": counts_by_key,
            "unexpected_values": unexpected_list,
            "raw_counts": raw_counts_display,
            "chart_data": chart_data,
        }

    def _run_validator(self, validator_def, stats: Dict, column_exists: bool = True) -> Dict:
        """
        Run a single validator.

        Args:
            validator_def: Either a string like "no_duplicates" or dict like {"name": "range", "params": [1900, 2025]}
            stats: Basic stats from _get_basic_stats()
            column_exists: Whether the column exists in the data

        Returns:
            dict: Check result
        """
        # Handle string validators
        if isinstance(validator_def, str):
            validator_name = validator_def
            validator_params = {}
        else:
            validator_name = validator_def.get('name')
            validator_params = validator_def.get('params', {})

        # Check for cross-file validators (format: in_file:<table>:<column>)
        if validator_name and validator_name.startswith('in_file:'):
            return self._validate_cross_file(validator_name, stats)

        # Dispatch to specific validator
        if validator_name == 'no_duplicates':
            return self._validate_no_duplicates(stats)
        elif validator_name == 'range':
            return self._validate_range(validator_params, stats)
        elif validator_name == 'required_when':
            return self._validate_required_when(validator_params, stats, column_exists)
        elif validator_name == 'forbidden_when':
            return self._validate_forbidden_when(validator_params, stats, column_exists)
        else:
            # Unknown validator - just mark as skipped
            return {
                'check_type': validator_name,
                'passed': True,
                'severity': 'warning',
                'message': f"Validator '{validator_name}' not implemented yet",
                'details': {}
            }

    def _validate_cross_file(self, validator_name: str, stats: Dict) -> Dict:
        """
        Validate cross-file foreign key relationships.

        Args:
            validator_name: Validator string like "in_file:patient:cohortPatientId"
            stats: Basic stats from _get_basic_stats()

        Returns:
            dict: Check result with affected rows if available
        """
        # Check that we have submission context
        if not self.submission:
            logger.warning(f"Cross-file validation '{validator_name}' requires submission context")
            return {
                'check_type': 'cross_file_reference',
                'passed': False,
                'severity': 'error',
                'message': f"Cross-file validation '{validator_name}' requires a submission to be selected. Re-run the precheck validation with a submission selected to validate patient IDs against the submission's patient file.",
                'details': {
                    'validator': validator_name,
                    'suggestion': 'Select a submission when running precheck validation to enable cross-file validation'
                }
            }

        # Use CrossFileValidator
        from depot.validators.cross_file_validator import CrossFileValidator

        try:
            validator = CrossFileValidator(
                duckdb_path=self.duckdb_path,
                column_name=self.column_name,
                validator_def=validator_name
            )

            return validator.validate(self.submission, self.data_file)

        except Exception as e:
            logger.error(f"Cross-file validation failed: {e}", exc_info=True)
            return {
                'check_type': 'cross_file_reference',
                'passed': False,
                'severity': 'error',
                'message': f"Cross-file validation error: {str(e)}",
                'details': {
                    'validator': validator_name,
                    'error': str(e)
                }
            }

    def _validate_no_duplicates(self, stats: Dict) -> Dict:
        """Check for duplicate values."""
        query = f"""
            SELECT
                COUNT(*) as dup_count,
                COUNT(DISTINCT "{self.column_name}") as unique_count
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
        """

        result = self.conn.execute(query).fetchone()
        total_non_null = result[0]
        unique_count = result[1]
        duplicate_count = total_non_null - unique_count

        passed = duplicate_count == 0

        check_result = {
            'check_type': 'no_duplicates',
            'passed': passed,
            'severity': 'error',
            'message': f"Found {duplicate_count} duplicate value{'s' if duplicate_count != 1 else ''}" if not passed else "No duplicates found",
            'affected_row_count': duplicate_count,  # Number of rows with duplicate values
            'details': {
                'total_values': total_non_null,
                'unique_values': unique_count,
                'duplicate_count': duplicate_count
            }
        }

        # If validation failed and we have source metadata, query for affected rows
        if not passed and self.is_combined_duckdb:
            row_info_query = f"""
                WITH duplicates AS (
                    SELECT "{self.column_name}", COUNT(*) as cnt
                    FROM data
                    WHERE "{self.column_name}" IS NOT NULL
                    GROUP BY "{self.column_name}"
                    HAVING COUNT(*) > 1
                )
                SELECT DISTINCT
                    d.__source_file_id,
                    d.__source_row_number,
                    d.row_no
                FROM data d
                INNER JOIN duplicates dup ON d."{self.column_name}" = dup."{self.column_name}"
                WHERE d."{self.column_name}" IS NOT NULL
                ORDER BY d.__source_file_id, d.__source_row_number
                LIMIT 500
            """
            try:
                affected_rows = self.conn.execute(row_info_query).fetchall()
                check_result['affected_rows'] = [
                    {
                        'file_id': row[0],
                        'source_row': row[1],
                        'duckdb_row': row[2]
                    }
                    for row in affected_rows
                ]
                check_result['affected_row_count'] = len(affected_rows)
            except Exception as e:
                logger.warning(f"Failed to query affected rows for duplicates: {e}")

        return check_result

    def _validate_range(self, params, stats: Dict) -> Dict:
        """Check values are within range."""
        if isinstance(params, list):
            min_val, max_val = params[0], params[1]
        else:
            min_val = params.get('min')
            max_val = params.get('max')

        query = f"""
            SELECT COUNT(*)
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
              AND (CAST("{self.column_name}" AS INTEGER) < ? OR CAST("{self.column_name}" AS INTEGER) > ?)
        """

        result = self.conn.execute(query, [min_val, max_val]).fetchone()
        out_of_range_count = result[0]

        passed = out_of_range_count == 0

        check_result = {
            'check_type': 'range',
            'passed': passed,
            'severity': 'error',
            'message': f"Found {out_of_range_count} value{'s' if out_of_range_count != 1 else ''} outside range [{min_val}, {max_val}]" if not passed else f"All values within range [{min_val}, {max_val}]",
            'details': {
                'min': min_val,
                'max': max_val,
                'out_of_range_count': out_of_range_count
            }
        }

        # If validation failed and we have source metadata, query for affected rows
        if not passed and self.is_combined_duckdb:
            row_info_query = f"""
                SELECT
                    __source_file_id,
                    __source_row_number,
                    row_no,
                    CAST("{self.column_name}" AS INTEGER) as value
                FROM data
                WHERE "{self.column_name}" IS NOT NULL
                  AND (CAST("{self.column_name}" AS INTEGER) < ? OR CAST("{self.column_name}" AS INTEGER) > ?)
                ORDER BY __source_file_id, __source_row_number
                LIMIT 500
            """
            try:
                affected_rows = self.conn.execute(row_info_query, [min_val, max_val]).fetchall()
                check_result['affected_rows'] = [
                    {
                        'file_id': row[0],
                        'source_row': row[1],
                        'duckdb_row': row[2],
                        'value': row[3]
                    }
                    for row in affected_rows
                ]
                check_result['affected_row_count'] = len(affected_rows)
            except Exception as e:
                logger.warning(f"Failed to query affected rows for range validation: {e}")

        return check_result

    def _validate_required_when(self, params: Dict, stats: Dict, column_exists: bool) -> Dict:
        """
        Check that field is required when condition is met.

        Params can be:
        - {"absent": "other_column"} - this field required when other_column is absent
        - {"present": "other_column"} - this field required when other_column is present
        """
        # Check for 'absent' condition
        if 'absent' in params:
            other_column = params['absent']
            other_exists = self._other_column_exists(other_column)

            if not other_exists:
                # Other column is absent, so this field IS required
                if column_exists and stats['total_rows'] > 0:
                    return {
                        'check_type': 'required_when',
                        'passed': True,
                        'severity': 'error',
                        'message': f"Field correctly present ({other_column} is absent)",
                        'details': params
                    }
                else:
                    return {
                        'check_type': 'required_when',
                        'passed': False,
                        'severity': 'error',
                        'message': f"Field required but missing ({other_column} is absent)",
                        'details': params
                    }
            else:
                # Other column is present, so this field is NOT required
                return {
                    'check_type': 'required_when',
                    'passed': True,
                    'severity': 'error',
                    'message': f"Field not required ({other_column} is present)",
                    'details': params
                }

        # Check for 'present' condition
        elif 'present' in params:
            other_column = params['present']
            other_exists = self._other_column_exists(other_column)

            if other_exists:
                # Other column is present, so this field IS required
                if column_exists and stats['total_rows'] > 0:
                    return {
                        'check_type': 'required_when',
                        'passed': True,
                        'severity': 'error',
                        'message': f"Field correctly present ({other_column} is present)",
                        'details': params
                    }
                else:
                    return {
                        'check_type': 'required_when',
                        'passed': False,
                        'severity': 'error',
                        'message': f"Field required but missing ({other_column} is present)",
                        'details': params
                    }
            else:
                # Other column is absent, so this field is NOT required
                return {
                    'check_type': 'required_when',
                    'passed': True,
                    'severity': 'error',
                    'message': f"Field not required ({other_column} is absent)",
                    'details': params
                }

        return {
            'check_type': 'required_when',
            'passed': True,
            'severity': 'warning',
            'message': "Invalid required_when parameters",
            'details': params
        }

    def _validate_forbidden_when(self, params: Dict, stats: Dict, column_exists: bool) -> Dict:
        """
        Check that field is forbidden when condition is met.

        Params can be:
        - {"present": "other_column"} - this field forbidden when other_column is present
        - {"absent": "other_column"} - this field forbidden when other_column is absent
        - {"severity": "warning"|"error"} - severity level (defaults to "error")
        """
        # Get severity from params, default to 'error'
        severity = params.get('severity', 'error')

        # Check for 'present' condition
        if 'present' in params:
            other_column = params['present']
            other_exists = self._other_column_exists(other_column)

            if other_exists:
                # Other column is present, so this field SHOULD be forbidden (absent)
                if not column_exists or stats['total_rows'] == 0:
                    return {
                        'check_type': 'forbidden_when',
                        'passed': True,
                        'severity': severity,
                        'message': f"Field correctly absent ({other_column} is present)",
                        'details': params
                    }
                else:
                    return {
                        'check_type': 'forbidden_when',
                        'passed': False,
                        'severity': severity,
                        'message': f"Field should be absent but is present ({other_column} is present)",
                        'details': params
                    }
            else:
                # Other column is absent, so this field is allowed
                return {
                    'check_type': 'forbidden_when',
                    'passed': True,
                    'severity': severity,
                    'message': f"Field allowed ({other_column} is absent)",
                    'details': params
                }

        # Check for 'absent' condition
        elif 'absent' in params:
            other_column = params['absent']
            other_exists = self._other_column_exists(other_column)

            if not other_exists:
                # Other column is absent, so this field SHOULD be forbidden (absent)
                if not column_exists or stats['total_rows'] == 0:
                    return {
                        'check_type': 'forbidden_when',
                        'passed': True,
                        'severity': severity,
                        'message': f"Field correctly absent ({other_column} is absent)",
                        'details': params
                    }
                else:
                    return {
                        'check_type': 'forbidden_when',
                        'passed': False,
                        'severity': severity,
                        'message': f"Field should be absent but is present ({other_column} is absent)",
                        'details': params
                    }
            else:
                # Other column is present, so this field is allowed
                return {
                    'check_type': 'forbidden_when',
                    'passed': True,
                    'severity': severity,
                    'message': f"Field allowed ({other_column} is present)",
                    'details': params
                }

        return {
            'check_type': 'forbidden_when',
            'passed': True,
            'severity': 'warning',
            'message': "Invalid forbidden_when parameters",
            'details': params
        }

    def _other_column_exists(self, column_name: str) -> bool:
        """Check if another column exists in the data."""
        try:
            result = self.conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'data' AND column_name = ?",
                [column_name]
            ).fetchone()
            return result is not None
        except Exception:
            return False

    def _generate_summary(self, stats: Dict) -> Dict:
        """
        Generate type-specific summary statistics for visualization and display.

        Reads 'summarizers' and 'visualize' from variable definition to determine
        what data to generate.

        Args:
            stats: Basic stats from _get_basic_stats()

        Returns:
            dict: Type-specific summary data including charts/visualizations
        """
        summary = {}

        # Get summarizers and visualizers from definition
        summarizers = self.variable_def.get('summarizers', [])
        visualizers = self.variable_def.get('visualize', [])

        # Generate type-specific base summary
        if self.column_type == 'id':
            summary = self._generate_id_summary(stats)
        elif self.column_type == 'enum':
            summary = self._generate_enum_summary(stats, summarizers)
        elif self.column_type in ['int', 'float', 'year']:
            summary = self._generate_numeric_summary(stats, visualizers)
        elif self.column_type == 'date':
            summary = self._generate_date_summary(stats, visualizers)
        elif self.column_type == 'boolean':
            summary = self._generate_boolean_summary(stats)
        elif self.column_type == 'string':
            summary = self._generate_string_summary(stats)

        return summary

    def _generate_id_summary(self, stats: Dict) -> Dict:
        """Generate summary for ID columns."""
        # Get unique and duplicate counts
        query = f"""
            SELECT
                COUNT(*) as total_non_null,
                COUNT(DISTINCT "{self.column_name}") as unique_count
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
        """
        result = self.conn.execute(query).fetchone()
        total_non_null = result[0]
        unique_count = result[1]
        duplicate_count = total_non_null - unique_count

        # Get sample values (first 20)
        sample_query = f"""
            SELECT DISTINCT "{self.column_name}"
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
            ORDER BY "{self.column_name}"
            LIMIT 20
        """
        sample_results = self.conn.execute(sample_query).fetchall()
        sample_values = [str(row[0]) for row in sample_results]

        return {
            'unique_count': unique_count,
            'duplicate_count': duplicate_count,
            'sample_values': sample_values,
            'total_non_null': total_non_null
        }

    def _generate_date_summary(self, stats: Dict, visualizers: list) -> Dict:
        """Generate summary for date columns."""
        summary: Dict[str, object] = {}

        total_rows = stats.get('total_rows', 0)
        null_count = stats.get('null_count', 0)
        empty_count = stats.get('empty_count', 0)
        non_empty_count = max(total_rows - null_count - empty_count, 0)

        valid_dates_sql = f"""
            SELECT
                TRY_CAST("{self.column_name}" AS DATE) AS valid_date,
                TRIM(CAST("{self.column_name}" AS VARCHAR)) AS raw_value
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
              AND TRIM(CAST("{self.column_name}" AS VARCHAR)) <> ''
        """

        invalid_query = f"""
            SELECT COUNT(*)
            FROM ({valid_dates_sql})
            WHERE valid_date IS NULL
        """
        invalid_result = self.conn.execute(invalid_query).fetchone()
        invalid_count = int(invalid_result[0]) if invalid_result and invalid_result[0] is not None else 0

        valid_count = max(non_empty_count - invalid_count, 0)

        range_query = f"""
            SELECT
                MIN(valid_date) AS min_date,
                MAX(valid_date) AS max_date
            FROM ({valid_dates_sql})
            WHERE valid_date IS NOT NULL
        """
        range_result = self.conn.execute(range_query).fetchone()
        min_date_value = range_result[0] if range_result else None
        max_date_value = range_result[1] if range_result else None

        if min_date_value is not None and not isinstance(min_date_value, date):
            min_date_value = date.fromisoformat(str(min_date_value))
        if max_date_value is not None and not isinstance(max_date_value, date):
            max_date_value = date.fromisoformat(str(max_date_value))

        summary['non_empty_count'] = non_empty_count
        summary['valid_count'] = valid_count
        summary['invalid_count'] = invalid_count
        summary['min_date'] = min_date_value.isoformat() if min_date_value else None
        summary['max_date'] = max_date_value.isoformat() if max_date_value else None

        if min_date_value and max_date_value:
            summary['range_days'] = (max_date_value - min_date_value).days
            summary['span_years'] = max_date_value.year - min_date_value.year + 1
        else:
            summary['range_days'] = None
            summary['span_years'] = None

        timeline_query = f"""
            SELECT
                STRFTIME(valid_date, '%Y-%m') AS period,
                COUNT(*) AS count
            FROM ({valid_dates_sql})
            WHERE valid_date IS NOT NULL
            GROUP BY period
            ORDER BY period
        """
        timeline_rows = self.conn.execute(timeline_query).fetchall()
        timeline = []
        labels: List[str] = []
        values: List[int] = []
        for period, count in timeline_rows:
            if period is None:
                continue
            period_str = str(period)
            timeline.append({'period': period_str, 'count': count})
            labels.append(period_str)
            values.append(count)

        chart_data = None
        if timeline:
            chart_data = {
                'labels': labels,
                'values': values,
                'labels_json': json.dumps(labels),
                'values_json': json.dumps(values),
            }

        summary['timeline'] = timeline
        summary['chart_data'] = chart_data if timeline else None
        summary['chart_type'] = 'line' if timeline else None

        year_query = f"""
            SELECT
                CAST(EXTRACT(YEAR FROM valid_date) AS INTEGER) AS year,
                COUNT(*) AS count
            FROM ({valid_dates_sql})
            WHERE valid_date IS NOT NULL
            GROUP BY year
            ORDER BY year
        """
        year_rows = self.conn.execute(year_query).fetchall()
        summary['year_breakdown'] = [
            {
                'year': int(row[0]),
                'count': row[1],
            }
            for row in year_rows
            if row[0] is not None
        ]

        invalid_examples_query = f"""
            SELECT raw_value, COUNT(*) AS count
            FROM ({valid_dates_sql})
            WHERE valid_date IS NULL
            GROUP BY raw_value
            ORDER BY count DESC, raw_value
            LIMIT 10
        """
        invalid_example_rows = self.conn.execute(invalid_examples_query).fetchall()
        summary['invalid_examples'] = [
            {
                'value': row[0],
                'count': row[1],
            }
            for row in invalid_example_rows
            if row[0] is not None
        ]

        return summary

    def _generate_enum_summary(self, stats: Dict, summarizers: list) -> Dict:
        """
        Generate summary for enum columns.

        If 'bar_chart' in summarizers, generates value distribution for visualization.
        """
        summary: Dict[str, object] = {}
        raw_counts = self._fetch_raw_value_counts()

        raw_distribution = [
            {
                "value": item["display"],
                "raw": item["raw"],
                "count": item["count"],
            }
            for item in raw_counts
        ]

        summary['raw_counts'] = raw_distribution
        summary['raw_total'] = sum(item['count'] for item in raw_distribution)
        summary['unique_raw_values'] = len(raw_distribution)
        summary['value_distribution'] = {
            item['value']: item['count'] for item in raw_distribution
        }
        summary['unique_values'] = summary['unique_raw_values']

        allowed_values = self.variable_def.get('allowed_values', [])
        case_sensitive = self.variable_def.get('case_sensitive', False)

        categorical = self._build_categorical_summary(
            raw_counts,
            allowed_values,
            case_sensitive=case_sensitive,
        )

        summary['definition_counts'] = [
            {
                "label": entry['label'],
                "count": entry['count'],
                "original_key": entry['original_key'],
                "normalized_key": entry['key'],
            }
            for entry in categorical['normalized_entries']
        ]
        summary['unexpected_values'] = categorical['unexpected_values']

        chart_data = None
        if 'bar_chart' in summarizers and raw_distribution:
            labels = [item['value'] for item in raw_distribution]
            values = [item['count'] for item in raw_distribution]
            chart_data = {
                'labels': labels,
                'values': values,
                'labels_json': json.dumps(labels),
                'values_json': json.dumps(values),
            }

        summary['chart_data'] = chart_data
        summary['chart_type'] = 'bar' if chart_data else None

        return summary

    def _generate_numeric_summary(self, stats: Dict, visualizers: list) -> Dict:
        """
        Generate summary for numeric columns (int, float, year).

        If 'histogram' in visualizers, generates bin data for visualization.
        """
        summary = {}

        # Get basic numeric statistics
        query = f"""
            SELECT
                MIN(CAST("{self.column_name}" AS DOUBLE)) as min_val,
                MAX(CAST("{self.column_name}" AS DOUBLE)) as max_val,
                AVG(CAST("{self.column_name}" AS DOUBLE)) as mean_val,
                MEDIAN(CAST("{self.column_name}" AS DOUBLE)) as median_val
            FROM data
            WHERE "{self.column_name}" IS NOT NULL
        """

        result = self.conn.execute(query).fetchone()
        summary['min'] = result[0]
        summary['max'] = result[1]
        summary['mean'] = result[2]
        summary['median'] = result[3]

        # If histogram requested, get all values for client-side binning
        if 'histogram' in visualizers:
            value_query = f"""
                SELECT CAST("{self.column_name}" AS DOUBLE) as value
                FROM data
                WHERE "{self.column_name}" IS NOT NULL
                ORDER BY value
            """
            value_results = self.conn.execute(value_query).fetchall()
            summary['chart_type'] = 'histogram'
            summary['chart_data'] = {
                'values': [row[0] for row in value_results]
            }

        return summary

    def _generate_string_summary(self, stats: Dict) -> Dict:
        """Generate summary for string columns."""
        # TODO: Implement string-specific summaries
        return {}

    def _generate_boolean_summary(self, stats: Dict) -> Dict:
        """Generate summary for boolean columns."""
        summary = {}

        raw_counts = self._fetch_raw_value_counts()
        case_sensitive = self.variable_def.get('case_sensitive', False)
        allowed_values = self.variable_def.get('allowed_values', {})

        default_synonyms = {
            "true": ["true", "1", "t", "y", "yes"],
            "false": ["false", "0", "f", "n", "no"],
            "unknown": ["unknown", "unk", "na", "n/a"],
        }

        categorical = self._build_categorical_summary(
            raw_counts,
            allowed_values,
            case_sensitive=case_sensitive,
            default_synonyms=default_synonyms,
        )

        summary['normalized_entries'] = categorical['normalized_entries']
        summary['unexpected_values'] = categorical['unexpected_values']
        summary['raw_counts'] = categorical['raw_counts']
        summary['raw_total'] = sum(item['count'] for item in summary['raw_counts'])
        summary['unique_raw_values'] = len(summary['raw_counts'])
        summary['value_distribution'] = {
            entry['label']: entry['count'] for entry in categorical['normalized_entries']
        }

        counts_map = categorical['counts_by_key']
        summary['true_count'] = counts_map.get(self._normalize_token('true', case_sensitive), 0)
        summary['false_count'] = counts_map.get(self._normalize_token('false', case_sensitive), 0)
        summary['unknown_count'] = counts_map.get(self._normalize_token('unknown', case_sensitive), 0)

        summary['definition_counts'] = [
            {
                "label": entry['label'],
                "count": entry['count'],
                "original_key": entry['original_key'],
                "normalized_key": entry['key'],
            }
            for entry in categorical['normalized_entries']
        ]

        summary['chart_data'] = categorical['chart_data']
        summary['chart_type'] = 'bar' if summary['chart_data'] else None

        return summary
