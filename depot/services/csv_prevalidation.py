"""
CSV Pre-validation Service

Performs synchronous validation checks on uploaded CSV files BEFORE
any expensive processing (DuckDB creation, full validation).

This is the FIRST line of defense for data quality and privacy compliance.
"""
import csv
import logging
from io import TextIOWrapper
from typing import Dict, List, Set, Any, Optional
from django.core.files.uploadedfile import UploadedFile

from depot.data.definition_loader import get_definition_for_type

logger = logging.getLogger(__name__)


class CSVPrevalidationResult:
    """Result of CSV pre-validation check"""

    def __init__(self):
        self.valid = True
        self.errors = []
        self.warnings = []

        # Column validation
        self.missing_required_columns = []
        self.extra_columns = []
        self.expected_columns = []

        # Patient ID validation
        self.patient_ids_extracted = []
        self.invalid_patient_ids = []
        self.patient_id_count = 0
        self.invalid_patient_id_count = 0

        # CSV structure
        self.malformed_rows = []
        self.total_rows = 0
        self.has_bom = False

    def add_error(self, message: str):
        """Add validation error"""
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str):
        """Add validation warning"""
        self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response"""
        return {
            'valid': self.valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'missing_required_columns': self.missing_required_columns,
            'extra_columns': self.extra_columns,
            'expected_columns': self.expected_columns,
            'patient_ids_extracted': len(self.patient_ids_extracted),
            'invalid_patient_ids': self.invalid_patient_ids,
            'invalid_patient_id_count': self.invalid_patient_id_count,
            'total_rows': self.total_rows,
            'malformed_rows': len(self.malformed_rows),
        }


class CSVPrevalidationService:
    """
    Synchronous CSV pre-validation service.

    Validates CSV structure, columns, and patient IDs BEFORE
    launching expensive async processing.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate_csv_file(
        self,
        csv_file: UploadedFile,
        file_type_name: str,
        patient_ids_from_patient_file: Optional[Set[str]] = None
    ) -> CSVPrevalidationResult:
        """
        Validate uploaded CSV file synchronously.

        Checks performed in ONE streaming pass:
        - CSV structure (malformed rows)
        - Column validation (missing required, extra columns)
        - Patient ID extraction
        - Patient ID validation (against patient file if provided)

        Args:
            csv_file: Uploaded CSV file
            file_type_name: Data file type (e.g., 'diagnosis', 'patient')
            patient_ids_from_patient_file: Set of valid patient IDs (if not patient file)

        Returns:
            CSVPrevalidationResult with validation results
        """
        result = CSVPrevalidationResult()

        try:
            # Get expected columns from definition
            definition_obj = get_definition_for_type(file_type_name)
            definition = definition_obj.get_definition()
            expected_columns = {var['name'] for var in definition}
            result.expected_columns = sorted(expected_columns)

            # Reset file pointer to beginning
            csv_file.seek(0)

            # Detect BOM and open stream
            # utf-8-sig automatically strips BOM if present
            first_bytes = csv_file.read(3)
            if first_bytes == b'\xef\xbb\xbf':
                result.has_bom = True
            csv_file.seek(0)

            # Create text stream with BOM handling
            # IMPORTANT: Don't let TextIOWrapper close the underlying file
            text_stream = TextIOWrapper(csv_file, encoding='utf-8-sig', newline='')

            # Stream CSV - memory efficient!
            reader = csv.DictReader(text_stream)

            # Get actual columns from header
            if reader.fieldnames is None:
                result.add_error("CSV file has no header row")
                return result

            actual_columns = set(reader.fieldnames)

            # Track column differences for metadata but don't warn
            missing = expected_columns - actual_columns
            if missing:
                result.missing_required_columns = sorted(missing)

            extra = actual_columns - expected_columns
            if extra:
                result.extra_columns = sorted(extra)

            # Stream through rows - extract patient IDs and check structure
            patient_ids = set()
            row_num = 1  # Header is row 0

            for row in reader:
                row_num += 1
                result.total_rows += 1

                # Check for malformed rows (different column count)
                if None in row.keys():
                    result.malformed_rows.append(row_num)
                    if len(result.malformed_rows) <= 5:  # Only log first 5
                        result.add_error(f"Malformed row {row_num}: Column count mismatch")
                    continue

                # Extract patient ID if present
                if 'cohortPatientId' in row:
                    patient_id = row['cohortPatientId']
                    if patient_id:  # Skip empty/null values
                        patient_ids.add(str(patient_id).strip())

            # Store extracted patient IDs
            result.patient_ids_extracted = sorted(patient_ids)
            result.patient_id_count = len(patient_ids)

            # Validate patient IDs against patient file (if provided)
            if patient_ids_from_patient_file is not None:
                invalid_ids = patient_ids - patient_ids_from_patient_file
                if invalid_ids:
                    result.invalid_patient_ids = sorted(invalid_ids)[:20]  # First 20
                    result.invalid_patient_id_count = len(invalid_ids)
                    # Mark as invalid - error message will be formatted by caller
                    result.valid = False

            # Check for too many malformed rows
            if len(result.malformed_rows) > 10:
                result.add_error(
                    f"Too many malformed rows ({len(result.malformed_rows)}). "
                    "Please check CSV formatting."
                )

            self.logger.info(
                f"Pre-validation completed for {file_type_name}: "
                f"{result.total_rows} rows, {result.patient_id_count} patient IDs, "
                f"valid={result.valid}"
            )

            # Detach the text wrapper to prevent it from closing the underlying file
            text_stream.detach()

            # Reset file pointer for next read
            csv_file.seek(0)

            return result

        except Exception as e:
            self.logger.error(f"Pre-validation error for {file_type_name}: {e}", exc_info=True)
            result.add_error(f"Pre-validation failed: {str(e)}")
            return result

    def get_patient_ids_from_duckdb(self, duckdb_path: str) -> Set[str]:
        """
        Get patient IDs from patient file's DuckDB.

        Used to get the valid patient ID universe for validation.

        Args:
            duckdb_path: Path to patient file DuckDB

        Returns:
            Set of patient IDs from patient file
        """
        import duckdb

        try:
            conn = duckdb.connect(':memory:')

            # Read from DuckDB file
            if duckdb_path.endswith('.duckdb'):
                conn.execute(f"ATTACH '{duckdb_path}' AS patient_db")
                result = conn.execute("""
                    SELECT DISTINCT cohortPatientId
                    FROM patient_db.data
                    WHERE cohortPatientId IS NOT NULL
                """).fetchall()
            else:
                # Parquet format
                result = conn.execute(f"""
                    SELECT DISTINCT cohortPatientId
                    FROM read_parquet('{duckdb_path}')
                    WHERE cohortPatientId IS NOT NULL
                """).fetchall()

            conn.close()

            return {str(row[0]).strip() for row in result}

        except Exception as e:
            self.logger.error(f"Failed to extract patient IDs from {duckdb_path}: {e}")
            return set()
