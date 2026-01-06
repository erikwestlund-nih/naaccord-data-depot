"""
Tests for Patient ID Extraction with Transaction Boundary Fix

This test verifies that:
1. Patient ID extraction works with transaction.on_commit()
2. Extraction errors are cleared on successful re-extraction
3. Retry logic handles transient failures
"""
import time
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import transaction

from depot.models import (
    Cohort,
    CohortSubmission,
    DataFileType,
    DataTableFile,
    SubmissionPatientIDs,
    CohortSubmissionDataTable,
    ProtocolYear
)
from depot.services.patient_id_service import PatientIDService

User = get_user_model()


class PatientIDExtractionTestCase(TransactionTestCase):
    """
    Test patient ID extraction with proper transaction handling.

    Uses TransactionTestCase to properly test transaction.on_commit() behavior.
    """

    def setUp(self):
        """Set up test data."""
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create cohort
        self.cohort = Cohort.objects.create(
            name='Test Cohort',
            status='active',
            type='clinical'
        )

        # Create protocol year
        self.protocol_year = ProtocolYear.objects.create(
            name='2024',
            year=2024,
            is_active=True
        )

        # Create submission
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status='in_progress',
            started_by=self.user
        )

        # Create data file type
        self.file_type = DataFileType.objects.create(
            name='patient',
            label='Patient'
        )

        # Create data table
        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.file_type,
            status='not_started'
        )

    def test_extraction_clears_previous_error(self):
        """Test that successful extraction clears previous errors."""
        # First, create a record with an error
        record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=[],
            user=self.user
        )
        record.extraction_error = "Previous extraction failed"
        record.save()

        # Verify error is set
        self.assertEqual(record.extraction_error, "Previous extraction failed")

        # Now do a successful extraction
        patient_ids = ["PAT001", "PAT002", "PAT003"]
        updated_record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=patient_ids,
            user=self.user
        )

        # Error should be cleared
        self.assertEqual(updated_record.extraction_error, '')
        self.assertEqual(updated_record.patient_count, 3)
        self.assertEqual(set(updated_record.patient_ids), set(patient_ids))

    def test_extraction_with_duplicates(self):
        """Test that duplicate patient IDs are handled correctly."""
        patient_ids_with_dupes = ["PAT001", "PAT002", "PAT001", "PAT003", "PAT002"]

        record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=patient_ids_with_dupes,
            user=self.user
        )

        # Should have unique IDs only
        self.assertEqual(record.patient_count, 3)
        self.assertEqual(set(record.patient_ids), {"PAT001", "PAT002", "PAT003"})
        self.assertTrue(record.has_duplicates)
        self.assertEqual(record.duplicate_count, 2)

    @patch('depot.services.patient_id_service.PatientIDExtractor')
    def test_retry_logic_on_failure(self, mock_extractor_class):
        """Test that retry logic works for transient failures."""
        # Create a mock that fails twice then succeeds
        mock_extractor = MagicMock()
        mock_extractor_class.return_value = mock_extractor

        # First two calls fail, third succeeds
        mock_record = MagicMock()
        mock_record.patient_count = 5
        mock_extractor.extract_from_data_table_file.side_effect = [
            Exception("Transient error 1"),
            Exception("Transient error 2"),
            mock_record
        ]

        # Create a data file
        data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path="/test/path.csv",
            version=1,
            uploaded_by=self.user
        )

        # Run extraction with retry logic
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = PatientIDService._extract_sync(data_file.id, self.user.id)

        # Should have succeeded after retries
        self.assertIsNotNone(result)
        self.assertEqual(mock_extractor.extract_from_data_table_file.call_count, 3)

    @patch('depot.services.patient_id_service.PatientIDExtractor')
    def test_all_retries_fail(self, mock_extractor_class):
        """Test behavior when all retry attempts fail."""
        # Create a mock that always fails
        mock_extractor = MagicMock()
        mock_extractor_class.return_value = mock_extractor
        mock_extractor.extract_from_data_table_file.side_effect = Exception("Persistent error")

        # Create a data file
        data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            raw_file_path="/test/path.csv",
            version=1,
            uploaded_by=self.user
        )

        # Run extraction with retry logic
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = PatientIDService._extract_sync(data_file.id, self.user.id)

        # Should return None after all retries fail
        self.assertIsNone(result)
        self.assertEqual(mock_extractor.extract_from_data_table_file.call_count, 3)


class PatientIDModelTestCase(TestCase):
    """Test the SubmissionPatientIDs model methods."""

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

        self.protocol_year = ProtocolYear.objects.create(
            name='2024',
            year=2024
        )

        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            started_by=self.user
        )

    def test_get_patient_ids_set(self):
        """Test converting patient IDs to a set."""
        patient_ids = ["PAT001", "PAT002", "PAT003"]
        record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=patient_ids,
            user=self.user
        )

        id_set = record.get_patient_ids_set()
        self.assertIsInstance(id_set, set)
        self.assertEqual(id_set, {"PAT001", "PAT002", "PAT003"})

    def test_validate_patient_id(self):
        """Test validating individual patient IDs."""
        patient_ids = ["PAT001", "PAT002", "PAT003"]
        record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=patient_ids,
            user=self.user
        )

        # Valid IDs
        self.assertTrue(record.validate_patient_id("PAT001"))
        self.assertTrue(record.validate_patient_id("PAT002"))

        # Invalid IDs
        self.assertFalse(record.validate_patient_id("PAT999"))
        self.assertFalse(record.validate_patient_id(""))

    def test_get_invalid_patient_ids(self):
        """Test finding invalid patient IDs from a list."""
        patient_ids = ["PAT001", "PAT002", "PAT003"]
        record = SubmissionPatientIDs.create_or_update_for_submission(
            submission=self.submission,
            patient_ids=patient_ids,
            user=self.user
        )

        # Mix of valid and invalid IDs
        ids_to_check = ["PAT001", "PAT999", "PAT002", "PAT888"]
        invalid_ids = record.get_invalid_patient_ids(ids_to_check)

        self.assertEqual(invalid_ids, ["PAT999", "PAT888"])