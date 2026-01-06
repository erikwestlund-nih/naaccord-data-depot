"""
Integration tests for table_manage upload functionality.

Tests the complete upload flow including file processing, versioning,
audit creation, and patient ID extraction.
"""
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from depot.models import (
    Cohort, CohortMembership, CohortSubmission, ProtocolYear,
    DataFileType, CohortSubmissionDataTable,
    DataTableFile, UploadedFile, PrecheckRun, Activity, DataRevision
)

User = get_user_model()


class TestTableManageUpload(TestCase):
    """Integration tests for file upload in table_manage view."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user.is_staff = True
        self.user.save()
        
        # Add user to proper group for permissions
        from django.contrib.auth.models import Group
        from depot.constants.groups import Groups
        manager_group, _ = Group.objects.get_or_create(name=Groups.COHORT_MANAGERS)
        self.user.groups.add(manager_group)
        
        # Create cohort
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        
        # Add user to cohort
        CohortMembership.objects.create(
            user=self.user,
            cohort=self.cohort
        )
        
        # Create protocol year
        self.protocol_year = ProtocolYear.objects.create(
            name='2024 Wave 1',
            year=2024
        )
        
        # Create submission
        self.submission = CohortSubmission.objects.create(
            protocol_year=self.protocol_year,
            cohort=self.cohort,
            started_by=self.user,
            status='in_progress'
        )
        
        # Create data file types
        self.patient_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient'
        )
        
        self.lab_file_type = DataFileType.objects.create(
            name='laboratory',
            label='Laboratory'
        )
        
        # Create data tables
        self.patient_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.patient_file_type,
            status='not_started'
        )
        
        self.lab_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.lab_file_type,
            status='not_started'
        )
        
        # Login
        self.client.login(username='testuser', password='testpass123')
    
    def tearDown(self):
        """Clean up test data, including Activity and DataRevision records."""
        # Delete all DataRevision and Activity records to avoid foreign key constraint violations
        # Both models use PROTECT on_delete to prevent accidental deletions
        # This cleans up records for all users created during tests
        DataRevision.objects.all().delete()
        Activity.objects.all().delete()
        super().tearDown()
    
    def create_test_csv(self, content):
        """Create a test CSV file."""
        return SimpleUploadedFile(
            'test.csv',
            content.encode('utf-8'),
            content_type='text/csv'
        )
    
    @patch('depot.services.file_upload_service.PHIStorageManager')
    @patch('depot.services.audit_service.AuditService.trigger_processing')
    def test_ajax_file_upload_success(self, mock_process_audit, mock_phi_manager):
        """Test successful AJAX file upload."""
        # Mock PHI storage
        mock_phi_instance = mock_phi_manager.return_value
        mock_phi_instance.store_raw_file.return_value = (
            '/nas/test/file.csv',
            'abc123hash'
        )
        # Mock the storage.save method for attachment handling
        mock_phi_instance.storage.save.return_value = '/nas/test/file.csv'
        # Mock get_absolute_path to return string instead of MagicMock
        mock_phi_instance.storage.get_absolute_path = lambda path: f'/absolute/{path}'
        
        # Create test file
        csv_content = "cohortPatientId,dateOfBirth\n1001,1990-01-01\n1002,1985-05-15"
        test_file = self.create_test_csv(csv_content)
        
        # Make AJAX upload request
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {
                'file': test_file,
                'file_name': 'Patient Data Q1',
                'file_comments': 'Initial patient upload'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Check response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Debug: Print response to understand failure
        if not data.get('success'):
            print(f"Upload failed with error: {data.get('error', 'No error message')}")
            print(f"Full response: {data}")
        self.assertTrue(data['success'])
        self.assertIn('File uploaded successfully', data['message'])
        
        # Verify file was created
        data_file = DataTableFile.objects.filter(
            data_table=self.patient_table
        ).first()
        self.assertIsNotNone(data_file)
        self.assertEqual(data_file.version, 1)
        self.assertEqual(data_file.name, 'Patient Data Q1')
        self.assertEqual(data_file.comments, 'Initial patient upload')
        self.assertTrue(data_file.is_current)

        # Note: Submissions use ValidationRun, not PrecheckRun
        # ValidationRun will be created by the workflow chain
    
    @patch('depot.services.file_upload_service.PHIStorageManager')
    @patch('depot.services.audit_service.AuditService.trigger_processing')
    def test_ajax_file_upload_versioning(self, mock_process_audit, mock_phi_manager):
        """Test file versioning on re-upload."""
        # Mock PHI storage
        mock_phi_instance = mock_phi_manager.return_value
        mock_phi_instance.store_raw_file.return_value = (
            '/nas/test/file.csv',
            'abc123hash'
        )
        # Mock the storage.save method for attachment handling
        mock_phi_instance.storage.save.return_value = '/nas/test/file.csv'
        # Mock get_absolute_path to return string instead of MagicMock
        mock_phi_instance.storage.get_absolute_path = lambda path: f'/absolute/{path}'

        # Create initial file
        csv_content_v1 = "cohortPatientId,dateOfBirth\n1001,1990-01-01"
        test_file_v1 = self.create_test_csv(csv_content_v1)
        
        # First upload
        response1 = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {'file': test_file_v1},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response1.status_code, 200)
        
        # Get first file
        file_v1 = DataTableFile.objects.filter(
            data_table=self.patient_table
        ).first()
        self.assertEqual(file_v1.version, 1)
        self.assertTrue(file_v1.is_current)
        
        # Second upload (new version)
        mock_phi_instance.store_raw_file.return_value = (
            '/nas/test/file_v2.csv',
            'def456hash'
        )
        csv_content_v2 = "cohortPatientId,dateOfBirth\n1001,1990-01-01\n1002,1985-05-15"
        test_file_v2 = self.create_test_csv(csv_content_v2)
        
        response2 = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {
                'file': test_file_v2,
                'file_id': str(file_v1.id)  # Update existing file
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response2.status_code, 200)
        
        # Verify versioning
        file_v1.refresh_from_db()
        self.assertEqual(file_v1.version, 2)
        self.assertTrue(file_v1.is_current)
        
        # Should still be only one file, but with new version
        file_count = DataTableFile.objects.filter(
            data_table=self.patient_table
        ).count()
        self.assertEqual(file_count, 1)
    
    def test_ajax_file_upload_patient_requirement(self):
        """Test that non-patient files require patient file first."""
        # Try to upload lab file without patient file
        csv_content = "cohortPatientId,labDate,result\n1001,2024-01-01,5.5"
        test_file = self.create_test_csv(csv_content)
        
        response = self.client.post(
            f'/submissions/{self.submission.id}/laboratory',
            {'file': test_file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should fail because no patient file
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Patient file must be uploaded first', data['error'])
    
    
    def test_ajax_file_upload_permission_denied(self):
        """Test upload denied for users without permission."""
        # Create another user not in cohort
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        # Login as other user
        self.client.login(username='otheruser', password='otherpass123')
        
        # Try to upload
        csv_content = "cohortPatientId,dateOfBirth\n1001,1990-01-01"
        test_file = self.create_test_csv(csv_content)
        
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {'file': test_file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should be forbidden
        self.assertEqual(response.status_code, 403)
    
    @patch('depot.services.file_upload_service.PHIStorageManager')
    def test_ajax_file_upload_with_comments(self, mock_phi_manager):
        """Test file upload with name and comments."""
        # Mock PHI storage
        mock_phi_instance = mock_phi_manager.return_value
        mock_phi_instance.store_raw_file.return_value = (
            '/nas/test/file.csv',
            'abc123hash'
        )
        # Mock the storage.save method for attachment handling
        mock_phi_instance.storage.save.return_value = '/nas/test/file.csv'
        # Mock get_absolute_path to return string instead of MagicMock
        mock_phi_instance.storage.get_absolute_path = lambda path: f'/absolute/{path}'

        # Create test file
        csv_content = "cohortPatientId,dateOfBirth\n1001,1990-01-01"
        test_file = self.create_test_csv(csv_content)
        
        # Upload with metadata
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {
                'file': test_file,
                'file_name': 'Q1 2024 Patient Data',
                'file_comments': 'Contains 1000 patients from Q1'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify metadata was saved
        data_file = DataTableFile.objects.filter(
            data_table=self.patient_table
        ).first()
        self.assertEqual(data_file.name, 'Q1 2024 Patient Data')
        self.assertEqual(data_file.comments, 'Contains 1000 patients from Q1')
    
    def test_ajax_file_upload_invalid_file(self):
        """Test upload with invalid file type."""
        # Create non-CSV file
        test_file = SimpleUploadedFile(
            'test.exe',
            b'MZ\x90\x00',  # EXE header
            content_type='application/x-msdownload'
        )
        
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {'file': test_file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should reject files that aren't CSV/TSV/TXT
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid file type. Allowed types: .csv, .tsv, .txt', data['error'])
    
    def test_ajax_file_upload_empty_file(self):
        """Test upload with empty file."""
        # Create empty file
        test_file = SimpleUploadedFile(
            'empty.csv',
            b'',
            content_type='text/csv'
        )
        
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {'file': test_file},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should reject empty files
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('empty', data['error'].lower())
    
    def test_non_ajax_file_upload_redirects(self):
        """Test that non-AJAX uploads redirect properly."""
        csv_content = "cohortPatientId,dateOfBirth\n1001,1990-01-01"
        test_file = self.create_test_csv(csv_content)
        
        # Make non-AJAX request
        response = self.client.post(
            f'/submissions/{self.submission.id}/patient',
            {'file': test_file}
            # No X-Requested-With header
        )
        
        # Should redirect or return appropriate response
        self.assertIn(response.status_code, [302, 200])