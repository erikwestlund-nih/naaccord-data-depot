"""
Cross-File Validator - Validates foreign key relationships across files in a submission.

This validator handles the `in_file:<table>:<column>` validator syntax, allowing
data definitions to declare cross-file foreign key constraints.

Example:
    In diagnosis_definition.json:
    {
        "name": "cohortPatientId",
        "validators": ["in_file:patient:cohortPatientId"]
    }

    This checks that every cohortPatientId in the diagnosis file exists
    in the patient file's cohortPatientId column.
"""
import logging
import duckdb
from typing import Dict, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class CrossFileValidator:
    """
    Validates foreign key relationships across multiple files in a submission.

    Supports declarative syntax: in_file:<table>:<column>
    Examples:
        - in_file:patient:cohortPatientId
        - in_file:medication:varName
        - in_file:visit:visitId
    """

    def __init__(self, duckdb_path: str, column_name: str, validator_def: str):
        """
        Initialize cross-file validator.

        Args:
            duckdb_path: Path to current file's DuckDB
            column_name: Column being validated in current file
            validator_def: Validator string like "in_file:patient:cohortPatientId"
        """
        self.duckdb_path = duckdb_path
        self.column_name = column_name
        self.validator_def = validator_def

        # Parse validator definition
        self.reference_table, self.reference_column = self._parse_validator(validator_def)

    def _parse_validator(self, validator_def: str) -> Tuple[str, str]:
        """
        Parse validator definition into table and column.

        Args:
            validator_def: String like "in_file:patient:cohortPatientId"

        Returns:
            Tuple of (table_name, column_name)

        Raises:
            ValueError: If validator format is invalid
        """
        if not validator_def.startswith('in_file:'):
            raise ValueError(f"Cross-file validator must start with 'in_file:': {validator_def}")

        # Remove 'in_file:' prefix
        spec = validator_def[8:]

        # Split on colon - should have exactly 2 parts (table:column)
        parts = spec.split(':', 1)

        if len(parts) != 2:
            raise ValueError(f"Cross-file validator must use format 'in_file:<table>:<column>': {validator_def}")

        table, column = parts

        if not table or not column:
            raise ValueError(f"Both table and column must be specified: {validator_def}")

        return table, column

    def validate(self, submission, data_file) -> Dict:
        """
        Validate that all IDs in current file exist in reference file.

        Args:
            submission: Submission model instance (to find reference files)
            data_file: Current DataTableFile being validated

        Returns:
            dict: {
                'check_type': 'cross_file_reference',
                'passed': bool,
                'severity': 'error',
                'message': str,
                'details': dict,
                'affected_rows': list (optional, if combined DuckDB)
            }
        """
        try:
            # Find reference file in submission
            reference_file_path = self._find_reference_file(submission, self.reference_table)

            if not reference_file_path:
                return {
                    'check_type': 'cross_file_reference',
                    'passed': False,
                    'severity': 'error',
                    'message': f"Reference file '{self.reference_table}' not found in submission",
                    'details': {
                        'reference_table': self.reference_table,
                        'reference_column': self.reference_column,
                        'validator': self.validator_def
                    }
                }

            # Extract IDs from reference file
            reference_ids = self._extract_ids_from_reference(reference_file_path)

            if not reference_ids:
                return {
                    'check_type': 'cross_file_reference',
                    'passed': False,
                    'severity': 'error',
                    'message': f"No IDs found in reference file '{self.reference_table}.{self.reference_column}'",
                    'details': {
                        'reference_table': self.reference_table,
                        'reference_column': self.reference_column,
                        'reference_file': str(reference_file_path)
                    }
                }

            # Check current file's IDs against reference
            missing_ids, affected_rows = self._check_ids_against_reference(reference_ids)

            passed = len(missing_ids) == 0

            result = {
                'check_type': 'cross_file_reference',
                'passed': passed,
                'severity': 'error',
                'message': self._build_message(passed, missing_ids, reference_ids),
                'details': {
                    'reference_table': self.reference_table,
                    'reference_column': self.reference_column,
                    'reference_id_count': len(reference_ids),
                    'missing_id_count': len(missing_ids),
                    'missing_ids_sample': missing_ids[:10] if missing_ids else []
                }
            }

            # Add affected rows if we have them
            if affected_rows:
                result['affected_rows'] = affected_rows
                result['affected_row_count'] = len(affected_rows)

            return result

        except Exception as e:
            logger.error(f"Cross-file validation failed: {e}", exc_info=True)
            return {
                'check_type': 'cross_file_reference',
                'passed': False,
                'severity': 'error',
                'message': f"Validation error: {str(e)}",
                'details': {
                    'error': str(e),
                    'validator': self.validator_def
                }
            }

    def _find_reference_file(self, submission, table_name: str) -> Optional[str]:
        """
        Find reference file's DuckDB path in submission.

        Args:
            submission: Submission model instance
            table_name: Name of reference table (e.g., 'patient', 'medication')

        Returns:
            Path to reference file's DuckDB, or None if not found
        """
        try:
            from depot.models import CohortSubmissionDataTable

            # Find data table for this file type
            data_table = CohortSubmissionDataTable.objects.filter(
                submission=submission,
                data_file_type__name=table_name
            ).first()

            if not data_table:
                logger.warning(f"Reference table '{table_name}' not found in submission {submission.id}")
                return None

            # Get current files for this table
            current_files = data_table.files.filter(is_current=True)

            if not current_files.exists():
                logger.warning(f"No current files for reference table '{table_name}'")
                return None

            # Use first file's DuckDB (for reference files, we don't need combined DuckDB)
            # The combined DuckDB is only for the file being validated, not for reference files
            first_file = current_files.first()
            if first_file.duckdb_file_path:
                # Convert relative path to absolute using storage manager
                from depot.storage.manager import StorageManager
                storage = StorageManager.get_submission_storage()
                absolute_path = storage.get_absolute_path(first_file.duckdb_file_path)

                if Path(absolute_path).exists():
                    logger.info(f"Using DuckDB for reference: {absolute_path}")
                    return absolute_path
                else:
                    logger.warning(f"DuckDB file not found at: {absolute_path}")

            logger.warning(f"No DuckDB file found for reference table '{table_name}'")
            return None

        except Exception as e:
            logger.error(f"Error finding reference file: {e}", exc_info=True)
            return None

    def _extract_ids_from_reference(self, reference_path: str) -> set:
        """
        Extract all IDs from reference file.

        Args:
            reference_path: Path to reference file's DuckDB

        Returns:
            Set of ID values
        """
        try:
            conn = duckdb.connect(reference_path, read_only=True)

            # Check if column exists
            column_check = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'data' AND column_name = ?",
                [self.reference_column]
            ).fetchone()

            if not column_check:
                logger.error(f"Column '{self.reference_column}' not found in reference file")
                conn.close()
                return set()

            # Extract distinct IDs
            query = f"""
                SELECT DISTINCT "{self.reference_column}"
                FROM data
                WHERE "{self.reference_column}" IS NOT NULL
                  AND TRIM(CAST("{self.reference_column}" AS VARCHAR)) != ''
            """

            results = conn.execute(query).fetchall()
            conn.close()

            # Convert to set of strings for comparison
            ids = {str(row[0]).strip() for row in results if row[0] is not None}

            logger.info(f"Extracted {len(ids)} unique IDs from reference file")
            return ids

        except Exception as e:
            logger.error(f"Error extracting IDs from reference: {e}", exc_info=True)
            return set()

    def _check_ids_against_reference(self, reference_ids: set) -> Tuple[List[str], List[Dict]]:
        """
        Check current file's IDs against reference IDs.

        Args:
            reference_ids: Set of valid IDs from reference file

        Returns:
            Tuple of (missing_ids, affected_rows)
            - missing_ids: List of IDs that are missing from reference
            - affected_rows: List of dicts with file_id/source_row info (if combined DuckDB)
        """
        try:
            conn = duckdb.connect(self.duckdb_path, read_only=True)

            # Check if this is a combined DuckDB (has __source_file_id)
            has_metadata = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'data' AND column_name = '__source_file_id'"
            ).fetchone()
            is_combined = has_metadata is not None

            # Get all IDs from current file
            query = f"""
                SELECT DISTINCT
                    TRIM(CAST("{self.column_name}" AS VARCHAR)) as id_value
                    {', __source_file_id, __source_row_number' if is_combined else ''}
                FROM data
                WHERE "{self.column_name}" IS NOT NULL
                  AND TRIM(CAST("{self.column_name}" AS VARCHAR)) != ''
            """

            results = conn.execute(query).fetchall()

            # Find missing IDs
            missing_ids = []
            affected_rows = []

            for row in results:
                id_value = str(row[0]).strip()

                if id_value not in reference_ids:
                    if id_value not in missing_ids:
                        missing_ids.append(id_value)

                    # Track affected rows if combined DuckDB
                    if is_combined and len(row) >= 3:
                        affected_rows.append({
                            'file_id': row[1],
                            'source_row': row[2],
                            'id_value': id_value
                        })

            conn.close()

            logger.info(f"Found {len(missing_ids)} missing IDs out of {len(results)} total")

            return missing_ids, affected_rows

        except Exception as e:
            logger.error(f"Error checking IDs: {e}", exc_info=True)
            return [], []

    def _build_message(self, passed: bool, missing_ids: List[str], reference_ids: set) -> str:
        """Build human-readable validation message."""
        if passed:
            return f"All {self.column_name} values exist in {self.reference_table}.{self.reference_column}"

        missing_count = len(missing_ids)
        sample = missing_ids[:5]
        sample_str = ', '.join(f"'{id}'" for id in sample)

        if missing_count <= 5:
            return f"Found {missing_count} {self.column_name} value(s) not in {self.reference_table}.{self.reference_column}: {sample_str}"
        else:
            return f"Found {missing_count} {self.column_name} values not in {self.reference_table}.{self.reference_column} (showing first 5: {sample_str})"
