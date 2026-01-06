"""
Tests for patient ID validation and file cleanup on validation failure.

Critical privacy requirement: Files with patient IDs not in the patient file
must be rejected and ALL files must be deleted, preserving only metadata.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import duckdb
from django.test import TestCase
from django.utils import timezone

from depot.tasks.patient_id_validation import (
    find_invalid_patient_ids,
    build_rejection_message,
)


class FindInvalidPatientIDsTest(TestCase):
    """Test the DuckDB query function that finds invalid patient IDs."""

    def setUp(self):
        """Set up test DuckDB files."""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: self._cleanup_temp_dir())

    def _cleanup_temp_dir(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_duckdb(self, patient_ids, filename="test.duckdb"):
        """Helper to create a DuckDB file with patient IDs."""
        db_path = Path(self.temp_dir) / filename
        conn = duckdb.connect(str(db_path))

        # Create table with patient IDs
        conn.execute("""
            CREATE TABLE data (
                cohortPatientId VARCHAR,
                testName VARCHAR,
                testResult VARCHAR
            )
        """)

        # Insert test data
        for patient_id in patient_ids:
            conn.execute("""
                INSERT INTO data VALUES (?, 'CD4', '500')
            """, [patient_id])

        conn.close()
        return str(db_path)

    def test_all_valid_patient_ids(self):
        """Test when all patient IDs in file exist in patient file."""
        # Create patient file with IDs: P001, P002, P003
        patient_db = self.create_test_duckdb(['P001', 'P002', 'P003'], 'patient.duckdb')

        # Create lab file with same IDs
        lab_db = self.create_test_duckdb(['P001', 'P002', 'P003'], 'lab.duckdb')

        # Find invalid IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=lab_db,
            patient_file=patient_db
        )

        # Should find no invalid IDs
        self.assertEqual(invalid_ids, [])

    def test_some_invalid_patient_ids(self):
        """Test when some patient IDs don't exist in patient file."""
        # Create patient file with IDs: P001, P002, P003
        patient_db = self.create_test_duckdb(['P001', 'P002', 'P003'], 'patient.duckdb')

        # Create lab file with IDs including invalid ones
        lab_db = self.create_test_duckdb(['P001', 'P999', 'P888', 'P002'], 'lab.duckdb')

        # Find invalid IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=lab_db,
            patient_file=patient_db
        )

        # Should find P888 and P999
        self.assertEqual(sorted(invalid_ids), ['P888', 'P999'])

    def test_all_invalid_patient_ids(self):
        """Test when all patient IDs are invalid."""
        # Create patient file with IDs: P001, P002, P003
        patient_db = self.create_test_duckdb(['P001', 'P002', 'P003'], 'patient.duckdb')

        # Create lab file with completely different IDs
        lab_db = self.create_test_duckdb(['P999', 'P888', 'P777'], 'lab.duckdb')

        # Find invalid IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=lab_db,
            patient_file=patient_db
        )

        # Should find all three
        self.assertEqual(sorted(invalid_ids), ['P777', 'P888', 'P999'])

    def test_duplicate_patient_ids_in_submission(self):
        """Test that duplicate IDs in submission are handled correctly."""
        # Create patient file with IDs: P001, P002
        patient_db = self.create_test_duckdb(['P001', 'P002'], 'patient.duckdb')

        # Create lab file with duplicate invalid ID
        lab_db = self.create_test_duckdb(['P001', 'P999', 'P999', 'P999'], 'lab.duckdb')

        # Find invalid IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=lab_db,
            patient_file=patient_db
        )

        # Should find P999 only once (DISTINCT query)
        self.assertEqual(invalid_ids, ['P999'])

    def test_empty_patient_file(self):
        """Test handling of empty patient file."""
        # Create empty patient file
        patient_db = self.create_test_duckdb([], 'patient.duckdb')

        # Create lab file with IDs
        lab_db = self.create_test_duckdb(['P001', 'P002'], 'lab.duckdb')

        # Find invalid IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=lab_db,
            patient_file=patient_db
        )

        # All IDs should be invalid
        self.assertEqual(sorted(invalid_ids), ['P001', 'P002'])


class RejectionMessageTest(TestCase):
    """Test rejection message building."""

    def test_rejection_message_with_few_invalid_ids(self):
        """Test message building with small number of invalid IDs."""
        invalid_ids = ['P999', 'P888', 'P777']

        message = build_rejection_message(invalid_ids)

        # Check message contains key information
        self.assertIn('FILE REJECTED', message)
        self.assertIn('3 patient ID(s)', message)
        self.assertIn('P999', message)
        self.assertIn('P888', message)
        self.assertIn('P777', message)
        self.assertIn('Privacy Policy', message)

    def test_rejection_message_limits_display(self):
        """Test that message only shows first 10 IDs."""
        invalid_ids = [f'P{i:03d}' for i in range(100, 130)]  # 30 IDs

        message = build_rejection_message(invalid_ids)

        # Check count is correct
        self.assertIn('30 patient ID(s)', message)

        # Check only first 10 are shown
        self.assertIn('showing first 10', message)
        self.assertIn('P100', message)  # First ID
        self.assertIn('P109', message)  # 10th ID
        self.assertNotIn('P110', message)  # 11th ID should not be shown

    def test_rejection_message_with_single_invalid_id(self):
        """Test message with just one invalid ID."""
        invalid_ids = ['P999']

        message = build_rejection_message(invalid_ids)

        # Check singular grammar
        self.assertIn('1 patient ID(s)', message)
        self.assertIn('P999', message)


class CleanupFunctionTest(TestCase):
    """Test file cleanup orchestration."""

    @patch('depot.tasks.patient_id_validation.ContentType')
    @patch('depot.tasks.patient_id_validation.StorageManager')
    @patch('depot.tasks.patient_id_validation.PHIFileTracking')
    def test_cleanup_deletes_all_tracked_files(self, mock_phi_tracking, mock_storage_manager, mock_content_type):
        """Test that cleanup function deletes all tracked files."""
        # Mock PHI tracking records
        mock_records = [
            MagicMock(file_path='/scratch/file1.csv', id=1),
            MagicMock(file_path='/scratch/file2.duckdb', id=2),
            MagicMock(file_path='/scratch/file3.csv', id=3),
        ]
        mock_phi_tracking.objects.filter.return_value = mock_records

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage_manager.return_value = mock_storage

        # Mock file object with proper attributes
        mock_file = MagicMock()
        mock_file.id = 123
        mock_file.data_table.submission.cohort = MagicMock()
        mock_file.uploaded_by = MagicMock()

        # Mock ContentType
        mock_content_type.objects.get_for_model.return_value = MagicMock(id=1)

        # Import and run cleanup
        from depot.tasks.patient_id_validation import cleanup_rejected_files
        deleted_files = cleanup_rejected_files(mock_file)

        # Should delete all three files
        self.assertEqual(len(deleted_files), 3)
        self.assertEqual(mock_storage.delete.call_count, 3)

        # Verify calls were made with correct paths
        expected_calls = [
            call('/scratch/file1.csv'),
            call('/scratch/file2.duckdb'),
            call('/scratch/file3.csv'),
        ]
        mock_storage.delete.assert_has_calls(expected_calls, any_order=True)

    @patch('depot.tasks.patient_id_validation.ContentType')
    @patch('depot.tasks.patient_id_validation.StorageManager')
    @patch('depot.tasks.patient_id_validation.PHIFileTracking')
    def test_cleanup_continues_on_individual_failure(self, mock_phi_tracking, mock_storage_manager, mock_content_type):
        """Test that cleanup continues even if one file delete fails."""
        # Mock PHI tracking records
        mock_records = [
            MagicMock(file_path='/scratch/file1.csv', id=1),
            MagicMock(file_path='/scratch/file2.duckdb', id=2),
            MagicMock(file_path='/scratch/file3.csv', id=3),
        ]
        mock_phi_tracking.objects.filter.return_value = mock_records

        # Mock storage manager with failure on second delete
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.delete.side_effect = [None, Exception("Delete failed"), None]
        mock_storage_manager.return_value = mock_storage

        # Mock file object with proper attributes
        mock_file = MagicMock()
        mock_file.id = 123
        mock_file.data_table.submission.cohort = MagicMock()
        mock_file.uploaded_by = MagicMock()

        # Mock ContentType
        mock_content_type.objects.get_for_model.return_value = MagicMock(id=1)

        # Import and run cleanup
        from depot.tasks.patient_id_validation import cleanup_rejected_files
        deleted_files = cleanup_rejected_files(mock_file)

        # Should successfully delete 2 files (not counting the failed one)
        self.assertEqual(len(deleted_files), 2)
        self.assertEqual(mock_storage.delete.call_count, 3)  # Attempted all 3

        # Verify failed record has error logged
        mock_records[1].save.assert_called()
        self.assertEqual(mock_records[1].cleanup_status, 'failed')

    @patch('depot.tasks.patient_id_validation.ContentType')
    @patch('depot.tasks.patient_id_validation.StorageManager')
    @patch('depot.tasks.patient_id_validation.PHIFileTracking')
    def test_cleanup_skips_nonexistent_files(self, mock_phi_tracking, mock_storage_manager, mock_content_type):
        """Test that cleanup handles already-deleted files gracefully."""
        # Mock PHI tracking records
        mock_records = [
            MagicMock(file_path='/scratch/file1.csv', id=1),
            MagicMock(file_path='/scratch/file2.duckdb', id=2),
        ]
        mock_phi_tracking.objects.filter.return_value = mock_records

        # Mock storage manager - first file exists, second doesn't
        mock_storage = MagicMock()
        mock_storage.exists.side_effect = [True, False]
        mock_storage_manager.return_value = mock_storage

        # Mock file object with proper attributes
        mock_file = MagicMock()
        mock_file.id = 123
        mock_file.data_table.submission.cohort = MagicMock()
        mock_file.uploaded_by = MagicMock()

        # Mock ContentType
        mock_content_type.objects.get_for_model.return_value = MagicMock(id=1)

        # Import and run cleanup
        from depot.tasks.patient_id_validation import cleanup_rejected_files
        deleted_files = cleanup_rejected_files(mock_file)

        # Should only delete the one that exists
        self.assertEqual(len(deleted_files), 1)
        self.assertEqual(mock_storage.delete.call_count, 1)


class RejectionMetadataTest(TestCase):
    """Test rejection metadata structure."""

    def test_metadata_structure_with_invalid_ids(self):
        """Test that rejection metadata has correct structure."""
        from depot.tasks.patient_id_validation import build_rejection_metadata

        invalid_ids = ['P888', 'P999', 'P777']

        metadata = build_rejection_metadata(
            reason='invalid_patient_ids',
            message='Found 3 invalid patient IDs',
            invalid_ids=invalid_ids,
            filename='laboratory.csv',
            file_size=2048,
            cohort_name='Test Cohort',
            data_type='laboratory'
        )

        # Check structure
        self.assertEqual(metadata['reason'], 'invalid_patient_ids')
        self.assertEqual(metadata['message'], 'Found 3 invalid patient IDs')
        self.assertEqual(metadata['invalid_ids']['count'], 3)
        self.assertEqual(sorted(metadata['invalid_ids']['sample']), ['P777', 'P888', 'P999'])
        self.assertEqual(metadata['file_metadata']['filename'], 'laboratory.csv')
        self.assertEqual(metadata['file_metadata']['size'], 2048)
        self.assertEqual(metadata['file_metadata']['cohort'], 'Test Cohort')
        self.assertEqual(metadata['file_metadata']['data_type'], 'laboratory')

    def test_metadata_limits_invalid_id_sample(self):
        """Test that metadata only stores first 20 invalid IDs."""
        from depot.tasks.patient_id_validation import build_rejection_metadata

        invalid_ids = [f'P{i:03d}' for i in range(100, 150)]  # 50 IDs

        metadata = build_rejection_metadata(
            reason='invalid_patient_ids',
            message='Found 50 invalid patient IDs',
            invalid_ids=invalid_ids,
            filename='laboratory.csv',
            file_size=2048,
            cohort_name='Test Cohort',
            data_type='laboratory'
        )

        # Check total count is correct
        self.assertEqual(metadata['invalid_ids']['count'], 50)

        # Check only first 20 are stored
        self.assertEqual(len(metadata['invalid_ids']['sample']), 20)
        self.assertEqual(metadata['invalid_ids']['sample'][0], 'P100')
        self.assertEqual(metadata['invalid_ids']['sample'][19], 'P119')
