"""
Patient ID Validator for granular validation system.

This validator extracts patient IDs from uploaded files and validates them
against the submission's master patient ID list. It replaces the monolithic
patient ID extraction logic with a job-based approach.

Key features:
- Extracts patient IDs from DuckDB using efficient SQL
- Validates against SubmissionPatientIDs (master list)
- Stores results in ValidationJob for queryability
- Reports invalid IDs as ValidationIssue records
- Tracks progress for large files

See: docs/technical/granular-validation-system.md
"""
import logging
from typing import Dict, Any
from depot.validation.base import BaseValidator
from depot.models import SubmissionPatientIDs

logger = logging.getLogger(__name__)


class PatientIDValidator(BaseValidator):
    """
    Validates patient IDs against submission master list.

    For patient files: Extracts and stores patient IDs as master list
    For non-patient files: Validates IDs against master list
    """

    PATIENT_ID_COLUMN = 'cohortPatientId'

    def validate(self, validation_job) -> Dict[str, Any]:
        """
        Execute patient ID validation.

        Returns:
            dict: Validation results with summary and issues
        """
        try:
            self.update_progress(validation_job, 10)

            # Determine if this is a patient file or not
            is_patient_file = self._is_patient_file()

            if is_patient_file:
                return self._extract_patient_ids(validation_job)
            else:
                return self._validate_patient_ids(validation_job)

        except Exception as e:
            logger.error(f"Patient ID validation failed: {e}", exc_info=True)
            return {
                'passed': False,
                'summary': {
                    'error': str(e)
                },
                'issues': [{
                    'severity': 'critical',
                    'row_number': None,
                    'column_name': self.PATIENT_ID_COLUMN,
                    'issue_type': 'validation_error',
                    'message': f'Patient ID validation failed: {str(e)}',
                    'invalid_value': None,
                    'expected_value': None,
                }]
            }

    def _is_patient_file(self) -> bool:
        """
        Determine if this is a patient file.

        Returns:
            bool: True if patient file type
        """
        return self.data_file_type.name.lower() == 'patient'

    def _extract_patient_ids(self, validation_job) -> Dict[str, Any]:
        """
        Extract patient IDs from patient file and store as master list.

        Args:
            validation_job: ValidationJob instance

        Returns:
            dict: Validation results
        """
        self.update_progress(validation_job, 20)

        # Find patient ID column (case-insensitive)
        patient_id_col = self._find_patient_id_column()
        if not patient_id_col:
            return {
                'passed': False,
                'summary': {
                    'error': f'Column "{self.PATIENT_ID_COLUMN}" not found'
                },
                'issues': [{
                    'severity': 'critical',
                    'row_number': None,
                    'column_name': self.PATIENT_ID_COLUMN,
                    'issue_type': 'missing_column',
                    'message': f'Required column "{self.PATIENT_ID_COLUMN}" not found in patient file',
                    'invalid_value': None,
                    'expected_value': self.PATIENT_ID_COLUMN,
                }]
            }

        self.update_progress(validation_job, 40)

        # Extract unique patient IDs
        query = f"""
            SELECT DISTINCT "{patient_id_col}"
            FROM data
            WHERE "{patient_id_col}" IS NOT NULL
        """
        result = self.conn.execute(query).fetchall()

        # Filter out None and empty strings
        patient_ids = [
            str(row[0]).strip()
            for row in result
            if row[0] is not None and str(row[0]).strip() != ''
        ]

        self.update_progress(validation_job, 60)

        # Check for duplicates
        total_ids = len(patient_ids)
        unique_ids = list(set(patient_ids))
        duplicate_count = total_ids - len(unique_ids)
        has_duplicates = duplicate_count > 0

        self.update_progress(validation_job, 80)

        # Store patient IDs in result_summary for later storage
        # The actual SubmissionPatientIDs record will be created/updated
        # by the orchestration layer after validation completes

        issues = []
        if has_duplicates:
            issues.append({
                'severity': 'warning',
                'row_number': None,
                'column_name': patient_id_col,
                'issue_type': 'duplicate_patient_ids',
                'message': f'Found {duplicate_count} duplicate patient IDs (removed for validation)',
                'invalid_value': str(duplicate_count),
                'expected_value': 'Unique patient IDs only',
            })

        self.update_progress(validation_job, 100)

        return {
            'passed': True,
            'summary': {
                'patient_count': len(unique_ids),
                'total_ids_found': total_ids,
                'duplicate_count': duplicate_count,
                'has_duplicates': has_duplicates,
                'column_name': patient_id_col,
            },
            'details': {
                # Store patient IDs for SubmissionPatientIDs creation
                'patient_ids': unique_ids,
                'extraction_type': 'duckdb',
            },
            'issues': issues
        }

    def _validate_patient_ids(self, validation_job) -> Dict[str, Any]:
        """
        Validate patient IDs against master list from patient file.

        Args:
            validation_job: ValidationJob instance

        Returns:
            dict: Validation results with invalid IDs as issues
        """
        self.update_progress(validation_job, 20)

        # Get submission from validation run
        validation_run = validation_job.validation_run
        content_object = validation_run.content_object

        # Get submission - handle different object types (Audit, PrecheckRun, etc.)
        submission = None
        if hasattr(content_object, 'submission'):
            submission = content_object.submission
        elif hasattr(content_object, 'cohort_submission'):
            submission = content_object.cohort_submission

        if not submission:
            return {
                'passed': False,
                'summary': {
                    'error': 'Cannot determine submission for validation'
                },
                'issues': [{
                    'severity': 'critical',
                    'row_number': None,
                    'column_name': self.PATIENT_ID_COLUMN,
                    'issue_type': 'configuration_error',
                    'message': 'Cannot determine submission for patient ID validation',
                    'invalid_value': None,
                    'expected_value': None,
                }]
            }

        self.update_progress(validation_job, 40)

        # Get master patient IDs
        try:
            patient_ids_record = SubmissionPatientIDs.objects.get(submission=submission)
            master_ids = set(patient_ids_record.patient_ids)
        except SubmissionPatientIDs.DoesNotExist:
            return {
                'passed': False,
                'summary': {
                    'error': 'No patient file uploaded yet'
                },
                'issues': [{
                    'severity': 'critical',
                    'row_number': None,
                    'column_name': self.PATIENT_ID_COLUMN,
                    'issue_type': 'missing_patient_file',
                    'message': 'Patient file must be uploaded before other files can be validated',
                    'invalid_value': None,
                    'expected_value': 'Upload patient file first',
                }]
            }

        self.update_progress(validation_job, 50)

        # Find patient ID column
        patient_id_col = self._find_patient_id_column()
        if not patient_id_col:
            return {
                'passed': False,
                'summary': {
                    'error': f'Column "{self.PATIENT_ID_COLUMN}" not found'
                },
                'issues': [{
                    'severity': 'critical',
                    'row_number': None,
                    'column_name': self.PATIENT_ID_COLUMN,
                    'issue_type': 'missing_column',
                    'message': f'Required column "{self.PATIENT_ID_COLUMN}" not found',
                    'invalid_value': None,
                    'expected_value': self.PATIENT_ID_COLUMN,
                }]
            }

        self.update_progress(validation_job, 60)

        # Extract patient IDs from this file
        query = f"""
            SELECT DISTINCT "{patient_id_col}"
            FROM data
            WHERE "{patient_id_col}" IS NOT NULL
        """
        result = self.conn.execute(query).fetchall()

        file_patient_ids = [
            str(row[0]).strip()
            for row in result
            if row[0] is not None and str(row[0]).strip() != ''
        ]
        file_ids_set = set(file_patient_ids)

        self.update_progress(validation_job, 75)

        # Find invalid IDs
        invalid_ids = list(file_ids_set - master_ids)

        # Create issues for invalid IDs (limit to 1000 for performance)
        issues = []
        for invalid_id in invalid_ids[:1000]:
            issues.append({
                'severity': 'error',
                'row_number': None,  # Row number not tracked for performance
                'column_name': patient_id_col,
                'issue_type': 'invalid_patient_id',
                'message': f'Patient ID "{invalid_id}" not found in patient file',
                'invalid_value': invalid_id,
                'expected_value': 'Patient ID from patient file',
            })

        self.update_progress(validation_job, 100)

        passed = len(invalid_ids) == 0

        return {
            'passed': passed,
            'summary': {
                'total_patient_ids': len(file_ids_set),
                'valid_patient_ids': len(file_ids_set & master_ids),
                'invalid_patient_ids': len(invalid_ids),
                'master_patient_count': len(master_ids),
                'has_more_issues': len(invalid_ids) > 1000,
                'column_name': patient_id_col,
            },
            'details': {
                'file_patient_ids': list(file_ids_set),
                'valid_ids': list(file_ids_set & master_ids),
                'invalid_ids': invalid_ids,
            },
            'issues': issues
        }

    def _find_patient_id_column(self) -> str:
        """
        Find patient ID column name (case-insensitive match).

        Returns:
            str: Column name if found, None otherwise
        """
        try:
            columns = self.conn.execute("PRAGMA table_info('data')").fetchall()
            column_names = [col[1] for col in columns]

            # Try case-insensitive match
            for col in column_names:
                if col.lower() == self.PATIENT_ID_COLUMN.lower():
                    return col

            return None
        except Exception as e:
            logger.error(f"Failed to find patient ID column: {e}")
            return None
