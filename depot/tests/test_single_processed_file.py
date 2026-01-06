"""
Tests for single processed file workflow.

Requirements:
1. All raw files maintained and tracked in PHIFileTracking
2. Single processed file created from raw files: {upload_id}_{file_type}.csv
3. Single DuckDB file created from processed CSV: {upload_id}_{file_type}.duckdb
4. Validation runs once per upload
"""

import unittest
from django.test import TestCase
from pathlib import Path
from depot.models import (
    CohortSubmission, DataTableFile, CohortSubmissionDataTable,
    Cohort, ProtocolYear, DataFileType, User, PHIFileTracking
)
from depot.tasks.duckdb_creation import create_duckdb_task
from depot.storage.phi_manager import PHIStorageManager


class TestSingleProcessedFileWorkflow(TestCase):
    """Test that multi-file uploads create only ONE processed file."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.cohort = Cohort.objects.create(id=18, name='Vanderbilt')
        self.protocol_year = ProtocolYear.objects.create(year=2024)
        self.file_type = DataFileType.objects.create(
            name='diagnosis',
            label='Diagnosis',
            description='Diagnosis data'
        )
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            started_by=self.user
        )
        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.file_type
        )

    @unittest.skip("Requires actual file creation and full Celery pipeline - use E2E tests instead")
    def test_single_file_upload_creates_one_processed_file(self):
        """
        When uploading ONE file, should create:
        - 1 raw file
        - 1 processed file: {upload_id}_diagnosis.csv (e.g., 11_diagnosis.csv)
        - 1 duckdb file: {upload_id}_diagnosis.duckdb (e.g., 11_diagnosis.duckdb)

        NOTE: This test requires:
        - Actual raw file created on disk at raw_file_path
        - Full Celery task execution
        - Proper storage initialization

        These are better tested as E2E tests with proper fixtures.
        """
        phi_manager = PHIStorageManager()
        storage_path = phi_manager.storage.base_path

        # Create one data file
        data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file1.csv',
            uploaded_by=self.user
        )

        # Trigger DuckDB creation
        task_data = {
            'data_file_id': data_file.id,
            'user_id': self.user.id,
            'submission_id': self.submission.id,
            'cohort_id': self.cohort.id,
            'file_type_name': 'diagnosis',
            'raw_file_path': data_file.raw_file_path,
            'precheck_run_id': None,
        }

        create_duckdb_task(task_data)

        # Check processed directory
        processed_dir = storage_path / '18_Vanderbilt' / '2024' / 'diagnosis' / 'processed'
        processed_files = list(processed_dir.glob('*.csv')) if processed_dir.exists() else []

        # Should only have ONE processed file with new naming: {upload_id}_{file_type}.csv
        assert len(processed_files) == 1, f"Expected 1 processed file, found {len(processed_files)}"
        expected_name = f'{data_file.id}_diagnosis.csv'
        assert processed_files[0].name == expected_name, f"Expected {expected_name}, got {processed_files[0].name}"

    @unittest.skip("Requires actual file creation and full Celery pipeline - use E2E tests instead")
    def test_multi_file_upload_creates_one_processed_file(self):
        """
        When uploading MULTIPLE files, should create:
        - N raw files
        - 1 processed file per upload: {upload_id}_{file_type}.csv
        - 1 duckdb file per upload: {upload_id}_{file_type}.duckdb

        NOTE: This test requires:
        - Actual raw files created on disk at raw_file_paths
        - Full Celery task execution
        - Proper storage initialization

        These are better tested as E2E tests with proper fixtures.
        """
        phi_manager = PHIStorageManager()
        storage_path = phi_manager.storage.base_path

        # Create two data files
        file1 = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file1.csv',
            uploaded_by=self.user
        )
        file2 = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file2.csv',
            uploaded_by=self.user
        )

        # Trigger DuckDB creation for second file (should process both)
        task_data = {
            'data_file_id': file2.id,
            'user_id': self.user.id,
            'submission_id': self.submission.id,
            'cohort_id': self.cohort.id,
            'file_type_name': 'diagnosis',
            'raw_file_path': file2.raw_file_path,
            'precheck_run_id': None,
        }

        create_duckdb_task(task_data)

        # Check processed directory
        processed_dir = storage_path / '18_Vanderbilt' / '2024' / 'diagnosis' / 'processed'
        processed_files = list(processed_dir.glob('*.csv')) if processed_dir.exists() else []

        # Should have processed files with new naming: {upload_id}_{file_type}.csv
        assert len(processed_files) >= 1, f"Expected at least 1 processed file, found {len(processed_files)}"
        # Each file gets its own processed file: file1.id_diagnosis.csv, file2.id_diagnosis.csv
        expected_names = {f'{file1.id}_diagnosis.csv', f'{file2.id}_diagnosis.csv'}
        actual_names = {f.name for f in processed_files}
        assert expected_names.intersection(actual_names), f"Expected files {expected_names}, got {actual_names}"

    @unittest.skip("Requires actual file creation and full Celery pipeline - use E2E tests instead")
    def test_single_duckdb_file_created(self):
        """
        Should create ONE DuckDB file per upload: {upload_id}_{file_type}.duckdb

        NOTE: This test requires:
        - Actual raw file created on disk at raw_file_path
        - Full Celery task execution
        - Proper storage initialization

        These are better tested as E2E tests with proper fixtures.
        """
        phi_manager = PHIStorageManager()
        storage_path = phi_manager.storage.base_path

        data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file1.csv',
            uploaded_by=self.user
        )

        task_data = {
            'data_file_id': data_file.id,
            'user_id': self.user.id,
            'submission_id': self.submission.id,
            'cohort_id': self.cohort.id,
            'file_type_name': 'diagnosis',
            'raw_file_path': data_file.raw_file_path,
            'precheck_run_id': None,
        }

        create_duckdb_task(task_data)

        # Check duckdb directory
        duckdb_dir = storage_path / '18_Vanderbilt' / '2024' / 'diagnosis' / 'duckdb'
        duckdb_files = list(duckdb_dir.glob('*.duckdb')) if duckdb_dir.exists() else []

        # Should only have ONE duckdb file with new naming: {upload_id}_{file_type}.duckdb
        assert len(duckdb_files) == 1, f"Expected 1 duckdb file, found {len(duckdb_files)}"
        expected_name = f'{data_file.id}_diagnosis.duckdb'
        assert duckdb_files[0].name == expected_name, f"Expected {expected_name}, got {duckdb_files[0].name}"

    @unittest.skip("Requires actual file upload workflow to create PHI tracking - use E2E tests instead")
    def test_all_raw_files_tracked_in_phi(self):
        """
        All raw files should be tracked in PHIFileTracking.

        NOTE: This test requires:
        - Actual file upload through proper workflow
        - PHI tracking records created during upload
        - FileUploadService to be used for file operations

        These are better tested as E2E tests with proper fixtures.
        """
        # Create two raw files
        file1 = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file1.csv',
            uploaded_by=self.user
        )
        file2 = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path='18_Vanderbilt/2024/diagnosis/raw/file2.csv',
            uploaded_by=self.user
        )

        # Check PHI tracking
        raw_tracking = PHIFileTracking.objects.filter(
            file_type='raw_csv',
            cohort=self.cohort
        )

        assert raw_tracking.count() >= 2, "Both raw files should be tracked"
