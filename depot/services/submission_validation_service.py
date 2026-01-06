"""
Service for comprehensive patient ID validation across all files in a submission.
Aggregates patient IDs from all uploaded files and provides detailed validation reporting.
"""
import logging
from typing import Dict, List, Set, Any
from collections import defaultdict
from django.db import models
from depot.models import CohortSubmission, DataTableFile, DataTableFilePatientIDs, SubmissionPatientIDs

logger = logging.getLogger(__name__)


class SubmissionValidationService:
    """
    Service to provide comprehensive patient ID validation reporting for a submission.
    Combines all uploaded files and compares against the main patient file.
    """

    def __init__(self, submission: CohortSubmission):
        self.submission = submission

    def get_comprehensive_validation_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive validation report for the entire submission.
        Returns detailed statistics about patient ID coverage across all files.
        """
        try:
            # Get the main patient record for this submission
            main_patient_record = SubmissionPatientIDs.objects.filter(
                submission=self.submission
            ).first()

            if not main_patient_record:
                return {
                    'status': 'no_patient_file',
                    'message': 'No patient file has been uploaded yet',
                    'main_patient_count': 0,
                    'files': [],
                    'summary': {}
                }

            main_patient_ids = set(main_patient_record.patient_ids)

            # Get all uploaded files with patient ID data
            file_reports = self._get_file_validation_reports(main_patient_ids)

            # Generate summary statistics
            summary = self._generate_summary_statistics(main_patient_ids, file_reports)

            return {
                'status': 'success',
                'submission_id': self.submission.id,
                'main_patient_count': len(main_patient_ids),
                'files': file_reports,
                'summary': summary,
                'main_patient_record': {
                    'id': main_patient_record.id,
                    'patient_count': main_patient_record.patient_count,
                    'extracted_at': main_patient_record.extracted_at,
                    'source_file': main_patient_record.source_file.original_filename if main_patient_record.source_file else None
                }
            }

        except Exception as e:
            logger.error(f"Failed to generate validation report for submission {self.submission.id}: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'submission_id': self.submission.id
            }

    def _get_file_validation_reports(self, main_patient_ids: Set[str]) -> List[Dict[str, Any]]:
        """Get validation reports for all files in the submission."""
        file_reports = []

        # Get all current data files for this submission
        data_files = DataTableFile.objects.filter(
            data_table__submission=self.submission,
            is_current=True
        ).select_related('data_table__data_file_type').order_by('data_table__data_file_type__name')

        for data_file in data_files:
            # Get the patient IDs record for this file
            patient_ids_record = DataTableFilePatientIDs.objects.filter(
                data_file=data_file
            ).first()

            if patient_ids_record:
                file_report = self._generate_file_report(data_file, patient_ids_record, main_patient_ids)
            else:
                # File has no patient ID extraction yet
                file_report = {
                    'file_id': data_file.id,
                    'file_name': data_file.original_filename,
                    'file_type': data_file.data_table.data_file_type.name,
                    'file_type_label': data_file.data_table.data_file_type.label,
                    'status': 'not_processed',
                    'patient_count': 0,
                    'valid_count': 0,
                    'invalid_count': 0,
                    'coverage_percentage': 0.0,
                    'validation_status': 'pending'
                }

            file_reports.append(file_report)

        return file_reports

    def _generate_file_report(self, data_file: DataTableFile, patient_ids_record: DataTableFilePatientIDs, main_patient_ids: Set[str]) -> Dict[str, Any]:
        """Generate validation report for a single file."""
        file_patient_ids = set(patient_ids_record.patient_ids) if patient_ids_record.patient_ids else set()

        # Calculate validation statistics
        valid_ids = file_patient_ids & main_patient_ids  # Intersection
        invalid_ids = file_patient_ids - main_patient_ids  # Difference

        # Calculate coverage percentage (what % of main patient IDs are represented in this file)
        coverage_percentage = (len(valid_ids) / len(main_patient_ids) * 100) if main_patient_ids else 0.0

        return {
            'file_id': data_file.id,
            'file_name': data_file.original_filename,
            'file_type': data_file.data_table.data_file_type.name,
            'file_type_label': data_file.data_table.data_file_type.label,
            'status': 'processed',
            'patient_count': len(file_patient_ids),
            'valid_count': len(valid_ids),
            'invalid_count': len(invalid_ids),
            'coverage_percentage': round(coverage_percentage, 2),
            'validation_status': patient_ids_record.validation_status,
            'validation_date': patient_ids_record.validation_date,
            'validation_error': patient_ids_record.validation_error,
            'extraction_date': patient_ids_record.extraction_date,
            'sample_invalid_ids': list(invalid_ids)[:10] if invalid_ids else [],  # First 10 invalid IDs
            'is_patient_file': data_file.data_table.data_file_type.name.lower() == 'patient'
        }

    def _generate_summary_statistics(self, main_patient_ids: Set[str], file_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics across all files."""
        all_file_patient_ids = set()
        total_files = len(file_reports)
        processed_files = 0
        files_with_invalid_ids = 0
        total_invalid_ids = 0

        # Aggregate data from all files
        for file_report in file_reports:
            if file_report['status'] == 'processed':
                processed_files += 1

                # Get this file's patient IDs (we need to fetch them again since we only stored samples)
                data_file = DataTableFile.objects.get(id=file_report['file_id'])
                patient_ids_record = DataTableFilePatientIDs.objects.filter(data_file=data_file).first()

                if patient_ids_record and patient_ids_record.patient_ids:
                    file_patient_ids = set(patient_ids_record.patient_ids)
                    all_file_patient_ids.update(file_patient_ids)

                if file_report['invalid_count'] > 0:
                    files_with_invalid_ids += 1
                    total_invalid_ids += file_report['invalid_count']

        # Calculate cross-file statistics
        patients_represented_in_files = all_file_patient_ids & main_patient_ids
        patients_missing_from_all_files = main_patient_ids - all_file_patient_ids
        patients_in_files_not_in_main = all_file_patient_ids - main_patient_ids

        # Overall coverage percentage
        overall_coverage = (len(patients_represented_in_files) / len(main_patient_ids) * 100) if main_patient_ids else 0.0

        return {
            'total_files': total_files,
            'processed_files': processed_files,
            'files_with_invalid_ids': files_with_invalid_ids,
            'total_invalid_ids': total_invalid_ids,
            'main_patient_count': len(main_patient_ids),
            'unique_patients_in_files': len(all_file_patient_ids),
            'patients_represented_in_files': len(patients_represented_in_files),
            'patients_missing_from_all_files': len(patients_missing_from_all_files),
            'patients_in_files_not_in_main': len(patients_in_files_not_in_main),
            'overall_coverage_percentage': round(overall_coverage, 2),
            'validation_complete': processed_files == total_files,
            'has_validation_issues': files_with_invalid_ids > 0 or len(patients_in_files_not_in_main) > 0
        }

    def get_missing_patients_report(self, limit: int = 100) -> List[str]:
        """
        Get a list of patient IDs that are in the main patient file
        but missing from all uploaded files.
        """
        try:
            main_patient_record = SubmissionPatientIDs.objects.filter(
                submission=self.submission
            ).first()

            if not main_patient_record:
                return []

            main_patient_ids = set(main_patient_record.patient_ids)
            all_file_patient_ids = set()

            # Collect patient IDs from all files
            patient_id_records = DataTableFilePatientIDs.objects.filter(
                data_file__data_table__submission=self.submission,
                data_file__is_current=True
            ).select_related('data_file')

            for record in patient_id_records:
                if record.patient_ids:
                    all_file_patient_ids.update(record.patient_ids)

            # Find missing patients
            missing_patients = main_patient_ids - all_file_patient_ids
            return sorted(list(missing_patients))[:limit]

        except Exception as e:
            logger.error(f"Failed to generate missing patients report: {e}")
            return []

    def get_invalid_patients_report(self, limit: int = 100) -> Dict[str, List[str]]:
        """
        Get a breakdown of invalid patient IDs by file type.
        Returns a dict mapping file types to lists of invalid patient IDs.
        """
        try:
            main_patient_record = SubmissionPatientIDs.objects.filter(
                submission=self.submission
            ).first()

            if not main_patient_record:
                return {}

            main_patient_ids = set(main_patient_record.patient_ids)
            invalid_by_file_type = defaultdict(list)

            # Get all files with patient ID records
            patient_id_records = DataTableFilePatientIDs.objects.filter(
                data_file__data_table__submission=self.submission,
                data_file__is_current=True
            ).select_related('data_file__data_table__data_file_type')

            for record in patient_id_records:
                if record.patient_ids:
                    file_patient_ids = set(record.patient_ids)
                    invalid_ids = file_patient_ids - main_patient_ids

                    if invalid_ids:
                        file_type = record.data_file.data_table.data_file_type.name
                        invalid_by_file_type[file_type].extend(list(invalid_ids)[:limit])

            # Remove duplicates and limit
            for file_type in invalid_by_file_type:
                invalid_by_file_type[file_type] = sorted(list(set(invalid_by_file_type[file_type])))[:limit]

            return dict(invalid_by_file_type)

        except Exception as e:
            logger.error(f"Failed to generate invalid patients report: {e}")
            return {}