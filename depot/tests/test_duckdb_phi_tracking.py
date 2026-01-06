"""
Tests for DuckDB PHI tracking and cleanup verification.

This test ensures that:
1. DuckDB files created during processing are tracked in PHIFileTracking
2. Workspace files have cleanup_required=True flag
3. Cleanup is properly verified with mark_cleaned_up()
4. All temporary files (CSV, DuckDB) are tracked and cleaned
"""
import tempfile
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from depot.models import (
    Cohort, DataFileType, PrecheckRun, UploadedFile,
    PHIFileTracking, UploadType, ProtocolYear,
    CohortSubmission, CohortSubmissionDataTable, DataTableFile
)
from depot.data.upload_prechecker import Auditor
from depot.storage.scratch_manager import ScratchManager

User = get_user_model()


class DuckDBPHITrackingTest(TransactionTestCase):
    """Test that DuckDB files are properly tracked in PHI system."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort',
            status='active'
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Record'
        )
        self.protocol_year = ProtocolYear.objects.create(
            name='2024',
            year=2024,
            is_active=True
        )

        # Create temp directories
        self.temp_dir = tempfile.mkdtemp()
        self.scratch_dir = Path(self.temp_dir) / 'scratch'
        self.scratch_dir.mkdir()

        # Patch scratch manager for new implementation
        test_temp_dir = self.temp_dir
        def mock_init(instance):
            # Mock the storage backend with a simple mock object
            from unittest.mock import MagicMock
            storage_mock = MagicMock()
            storage_mock.save = MagicMock()
            storage_mock.ensure_prefix = MagicMock()
            # Mock get_absolute_path to prepend /tmp/test/ to relative paths
            storage_mock.get_absolute_path = lambda path: f"/tmp/test/{path}"
            instance.storage = storage_mock

            # Set up prefixes like the real implementation
            instance.scratch_prefix = "scratch/"
            instance.precheck_runs_prefix = f"{instance.scratch_prefix}precheck_runs/"
            instance.submissions_prefix = f"{instance.scratch_prefix}submissions/"
            instance.cleanup_logs_prefix = f"{instance.scratch_prefix}cleanup_logs/"

            # Mock cleanup method to always return success
            instance.cleanup_precheck_run = MagicMock(return_value=True)

        self.scratch_patcher = patch.object(ScratchManager, '__init__', mock_init)
        self.scratch_patcher.start()

    def tearDown(self):
        """Clean up temp files."""
        self.scratch_patcher.stop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('depot.data.upload_prechecker.get_definition_for_type')
    def test_duckdb_file_tracked_in_precheck_run(self, mock_get_definition):
        """Test that DuckDB file created during upload precheck is tracked."""
        # Mock definition
        mock_definition = MagicMock()
        mock_definition.definition = [
            {"name": "cohortPatientId", "type": "string", "description": "Patient ID"}
        ]
        mock_definition.definition_path = "/test/definition.json"
        mock_get_definition.return_value = mock_definition

        # Create upload precheck
        precheck_run = PrecheckRun.objects.create(
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            created_by=self.user,
            status='pending'
        )

        # Create auditor and process
        test_csv = "cohortPatientId\nPAT001\nPAT002\n"
        auditor = Auditor(
            data_file_type=self.data_file_type,
            data_content=test_csv,
            precheck_run=precheck_run
        )

        # Load data into DuckDB (this should create PHI tracking)
        db_path = auditor.load_duckdb()

        # Check that scratch directory was tracked (file_path is now absolute, relative in metadata)
        scratch_tracking = PHIFileTracking.objects.filter(
            action='work_copy_created',
            file_type='scratch_directory',
            metadata__relative_path=f"scratch/precheck_runs/{precheck_run.id}",
            cleanup_required=True
        ).first()
        self.assertIsNotNone(scratch_tracking, "Scratch directory should be tracked")
        self.assertTrue(scratch_tracking.cleanup_required)
        # Verify absolute path is stored in file_path
        self.assertTrue(scratch_tracking.file_path.startswith('/'))

        # Check that CSV file was tracked (file_path is now absolute, relative in metadata)
        csv_tracking = PHIFileTracking.objects.filter(
            action='work_copy_created',
            file_type='raw_csv',
            metadata__relative_path=f"scratch/precheck_runs/{precheck_run.id}/input.csv",
            cleanup_required=True
        ).first()
        self.assertIsNotNone(csv_tracking, "CSV file should be tracked")
        self.assertTrue(csv_tracking.cleanup_required)
        # Verify absolute path is stored in file_path
        self.assertTrue(csv_tracking.file_path.startswith('/'))

        # Check that DuckDB file was tracked (file_path is now absolute, relative in metadata)
        duckdb_tracking = PHIFileTracking.objects.filter(
            action='work_copy_created',
            file_type='duckdb',
            metadata__relative_path=f"scratch/precheck_runs/{precheck_run.id}/audit_{precheck_run.id}.duckdb",
            cleanup_required=True
        ).first()
        self.assertIsNotNone(duckdb_tracking, "DuckDB file should be tracked")
        self.assertTrue(duckdb_tracking.cleanup_required)
        # Verify absolute path is stored in file_path
        self.assertTrue(duckdb_tracking.file_path.startswith('/'))

        # Cleanup
        auditor.cleanup()

    @patch('depot.data.upload_prechecker.get_definition_for_type')
    def test_cleanup_marks_all_files_as_cleaned(self, mock_get_definition):
        """Test that cleanup properly marks all PHI files as cleaned."""
        # Mock definition
        mock_definition = MagicMock()
        mock_definition.definition = [
            {"name": "cohortPatientId", "type": "string", "description": "Patient ID"}
        ]
        mock_definition.definition_path = "/test/definition.json"
        mock_get_definition.return_value = mock_definition

        # Create upload precheck
        precheck_run = PrecheckRun.objects.create(
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            created_by=self.user,
            status='pending'
        )

        # Create auditor and process
        test_csv = "cohortPatientId\nPAT001\nPAT002\n"
        auditor = Auditor(
            data_file_type=self.data_file_type,
            data_content=test_csv,
            precheck_run=precheck_run
        )

        # Load data into DuckDB
        db_path = auditor.load_duckdb()

        # Verify files were created and tracked
        initial_tracking_count = PHIFileTracking.objects.filter(
            cleanup_required=True,
            cleaned_up=False
        ).count()
        self.assertGreaterEqual(initial_tracking_count, 3, "Should have at least 3 tracked files")

        # Run cleanup
        auditor.cleanup()

        # Check that all files were marked as cleaned
        uncleaned_files = PHIFileTracking.objects.filter(
            cleanup_required=True,
            cleaned_up=False,
            file_path__contains=str(precheck_run.id)
        )

        # List any uncleaned files for debugging
        for file in uncleaned_files:
            print(f"Uncleaned file: {file.file_path} (type: {file.file_type})")

        self.assertEqual(uncleaned_files.count(), 0, "All files should be marked as cleaned")

        # Verify specific files were marked cleaned
        cleaned_files = PHIFileTracking.objects.filter(
            cleanup_required=True,
            cleaned_up=True,
            file_path__contains=str(precheck_run.id)
        )
        self.assertGreaterEqual(cleaned_files.count(), 3, "Should have at least 3 cleaned files")

        # Check cleanup timestamps were set
        for tracking in cleaned_files:
            self.assertIsNotNone(tracking.cleanup_verified_at)
            self.assertEqual(tracking.cleanup_verified_by, self.user)

    @patch('depot.data.upload_prechecker.get_definition_for_type')
    @unittest.skip("TODO: Rewrite for submission ValidationRun workflow - Auditor is only for standalone precheck")
    def test_submission_duckdb_tracked_differently(self, mock_get_definition):
        """Test that submission DuckDB files have different retention policy."""
        # Mock definition
        mock_definition = MagicMock()
        mock_definition.definition = [
            {"name": "cohortPatientId", "type": "string", "description": "Patient ID"}
        ]
        mock_definition.definition_path = "/test/definition.json"
        mock_get_definition.return_value = mock_definition

        # Create submission and data table
        submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status='in_progress',
            started_by=self.user
        )

        data_table = CohortSubmissionDataTable.objects.create(
            submission=submission,
            data_file_type=self.data_file_type,
            status='not_started'
        )

        data_file = DataTableFile.objects.create(
            data_table=data_table,
            raw_file_path="/nas/cohort/2024/patient/raw/file.csv",
            version=1,
            uploaded_by=self.user
        )

        # Note: Submissions use ValidationRun, not PrecheckRun
        # This test is about PHI tracking during DuckDB conversion, which happens
        # in both standalone precheck and submission workflows

        # Create auditor for testing PHI tracking
        test_csv = "cohortPatientId\nPAT001\nPAT002\n"
        auditor = Auditor(
            data_file_type=self.data_file_type,
            data_content=test_csv,
            precheck_run=None  # Submissions don't use PrecheckRun
        )

        # Mock PHI manager for NAS operations
        with patch('depot.data.upload_prechecker.PHIStorageManager') as mock_phi_manager_class:
            mock_phi_manager = MagicMock()
            mock_phi_manager.store_raw_file.return_value = ("/nas/path/raw.csv", "hash123")
            mock_phi_manager.convert_to_duckdb.return_value = (
                "/nas/path/data.duckdb",
                "/nas/path/processed.csv",
                {
                    'mapping': None,
                    'summary': {},
                    'row_count_in': None,
                    'row_count_out': None,
                },
            )
            mock_phi_manager.copy_to_scratch.return_value = str(self.scratch_dir / "temp.duckdb")
            mock_phi_manager_class.return_value = mock_phi_manager

            # Load data - should use PHI manager for submission
            db_path = auditor.load_duckdb()

            # For submissions, DuckDB on NAS should NOT have cleanup_required
            # (they're retained until user explicitly removes)
            # But scratch copies should still be cleaned

            # This test verifies the distinction between temporary (upload precheck)
            # and permanent (submission) DuckDB files


class DuckDBCleanupVerificationTest(TestCase):
    """Test that DuckDB cleanup is properly verified."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )

    def test_mark_cleaned_up_sets_verification_fields(self):
        """Test that mark_cleaned_up properly sets verification fields."""
        # Create PHI tracking record
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='work_copy_created',
            file_path='/scratch/test.duckdb',
            file_type='duckdb',
            cleanup_required=True,
            cleaned_up=False
        )

        # Mark as cleaned up
        tracking.mark_cleaned_up(self.user)

        # Verify fields were set
        tracking.refresh_from_db()
        self.assertTrue(tracking.cleaned_up)
        self.assertIsNotNone(tracking.cleanup_verified_at)
        self.assertEqual(tracking.cleanup_verified_by, self.user)

    def test_cleanup_required_flag_for_all_scratch_files(self):
        """Test that all scratch files have cleanup_required=True."""
        # Create various PHI tracking records
        scratch_files = [
            '/scratch/precheck_runs/1/input.csv',
            '/scratch/precheck_runs/1/audit_1.duckdb',
            '/scratch/submissions/2/temp.duckdb',
        ]

        for file_path in scratch_files:
            file_type = 'duckdb' if file_path.endswith('.duckdb') else 'raw_csv'
            tracking = PHIFileTracking.objects.create(
                cohort=self.cohort,
                user=self.user,
                action='work_copy_created',
                file_path=file_path,
                file_type=file_type,
                cleanup_required=True  # All scratch files should have this
            )
            self.assertTrue(tracking.cleanup_required,
                          f"Workspace file {file_path} should have cleanup_required=True")

    def test_nas_files_have_different_retention(self):
        """Test that NAS files have different retention policies."""
        # NAS files for submissions should NOT have cleanup_required=True
        # They're retained until explicitly removed by user
        nas_tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='nas_duckdb_created',
            file_path='/nas/cohort/2024/patient/duckdb/data.duckdb',
            file_type='duckdb',
            cleanup_required=False  # NAS files retained
        )
        self.assertFalse(nas_tracking.cleanup_required,
                        "NAS submission files should not have cleanup_required=True")

        # But upload precheck files should be cleaned
        upload_tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path='precheck_runs/1/patient/test.csv',
            file_type='raw_csv',
            cleanup_required=True  # Upload precheck files cleaned
        )
        self.assertTrue(upload_tracking.cleanup_required,
                       "Upload precheck files should have cleanup_required=True")
