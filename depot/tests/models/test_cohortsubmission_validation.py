"""
Tests for CohortSubmission validation methods
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from depot.models import (
    Cohort, CohortSubmission, ProtocolYear,
    DataFileType, CohortSubmissionDataTable, DataTableFile,
    UploadedFile, UploadType
)

User = get_user_model()


class TestCohortSubmissionValidation(TestCase):
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.cohort = Cohort.objects.create(name='Test Cohort')
        self.protocol_year = ProtocolYear.objects.create(
            name='Test Wave',
            year=2024
        )
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            started_by=self.user
        )
        self.patient_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )
        self.lab_type = DataFileType.objects.create(
            name='laboratory',
            label='Laboratory Data'
        )
        
        # Add user to cohort so they have permission to upload files
        from depot.models import CohortMembership
        from django.contrib.auth.models import Group
        from depot.constants.groups import Groups
        
        # Create and assign the user to the COHORT_MANAGERS group
        manager_group, _ = Group.objects.get_or_create(name=Groups.COHORT_MANAGERS)
        self.user.groups.add(manager_group)
        
        CohortMembership.objects.create(
            user=self.user,
            cohort=self.cohort
        )
    
    def test_get_patient_data_table(self):
        """Test getting patient data table."""
        # No patient table initially
        self.assertIsNone(self.submission.get_patient_data_table())
        
        # Create patient table
        patient_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.patient_type
        )
        
        result = self.submission.get_patient_data_table()
        self.assertEqual(result, patient_table)
    
    def test_has_patient_file(self):
        """Test checking for patient file."""
        # No patient file initially
        self.assertFalse(self.submission.has_patient_file())
        
        # Create patient table without file
        patient_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.patient_type
        )
        self.assertFalse(self.submission.has_patient_file())
        
        # Add file to patient table
        uploaded_file = UploadedFile.objects.create(
            filename='patient.csv',
            storage_path='/test/patient.csv',
            file_hash='abc123',
            uploader=self.user,
            type=UploadType.RAW
        )
        DataTableFile.objects.create(
            data_table=patient_table,
            uploaded_file=uploaded_file,
            uploaded_by=self.user,
            version=1
        )
        
        self.assertTrue(self.submission.has_patient_file())
    
    def test_can_accept_files(self):
        """Test checking if submission can accept files."""
        # Draft submission can accept files
        self.assertTrue(self.submission.can_accept_files(self.user))
        
        # In progress can accept files
        self.submission.status = 'in_progress'
        self.submission.save()
        self.assertTrue(self.submission.can_accept_files(self.user))
        
        # Signed off cannot accept files
        self.submission.status = 'signed_off'
        self.submission.save()
        self.assertFalse(self.submission.can_accept_files(self.user))
        
        # Closed cannot accept files
        self.submission.status = 'closed'
        self.submission.save()
        self.assertFalse(self.submission.can_accept_files(self.user))


class TestCohortSubmissionDataTableValidation(TestCase):
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.cohort = Cohort.objects.create(name='Test Cohort')
        self.protocol_year = ProtocolYear.objects.create(
            name='Test Wave',
            year=2024
        )
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            started_by=self.user
        )
        self.patient_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )
        self.lab_type = DataFileType.objects.create(
            name='laboratory',
            label='Laboratory Data'
        )
        
        # Add user to cohort so they have permission to upload files
        from depot.models import CohortMembership
        from django.contrib.auth.models import Group
        from depot.constants.groups import Groups
        
        # Create and assign the user to the COHORT_MANAGERS group
        manager_group, _ = Group.objects.get_or_create(name=Groups.COHORT_MANAGERS)
        self.user.groups.add(manager_group)
        
        CohortMembership.objects.create(
            user=self.user,
            cohort=self.cohort
        )
        self.patient_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.patient_type
        )
        self.lab_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.lab_type
        )
    
    def test_requires_patient_file(self):
        """Test checking if table requires patient file."""
        # Patient table doesn't require patient file
        self.assertFalse(self.patient_table.requires_patient_file())
        
        # Lab table requires patient file
        self.assertTrue(self.lab_table.requires_patient_file())
    
    def test_can_upload_file_no_patient(self):
        """Test upload validation when no patient file exists."""
        # Patient table can upload
        can_upload, error = self.patient_table.can_upload_file(self.user)
        self.assertTrue(can_upload)
        self.assertIsNone(error)
        
        # Lab table cannot upload without patient file
        can_upload, error = self.lab_table.can_upload_file(self.user)
        self.assertFalse(can_upload)
        self.assertEqual(error, "Patient file must be uploaded first")
    
    def test_can_upload_file_with_patient(self):
        """Test upload validation when patient file exists."""
        # Add patient file
        uploaded_file = UploadedFile.objects.create(
            filename='patient.csv',
            storage_path='/test/patient.csv',
            file_hash='abc123',
            uploader=self.user,
            type=UploadType.RAW
        )
        DataTableFile.objects.create(
            data_table=self.patient_table,
            uploaded_file=uploaded_file,
            uploaded_by=self.user,
            version=1
        )
        
        # Now lab table can upload
        can_upload, error = self.lab_table.can_upload_file(self.user)
        self.assertTrue(can_upload)
        self.assertIsNone(error)
    
    def test_can_upload_file_duplicate_patient(self):
        """Test preventing duplicate patient files."""
        # Add first patient file
        uploaded_file = UploadedFile.objects.create(
            filename='patient.csv',
            storage_path='/test/patient.csv',
            file_hash='abc123',
            uploader=self.user,
            type=UploadType.RAW
        )
        DataTableFile.objects.create(
            data_table=self.patient_table,
            uploaded_file=uploaded_file,
            uploaded_by=self.user,
            version=1
        )
        
        # Create another patient table (shouldn't happen in practice)
        patient_table2 = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=DataFileType.objects.create(name='Patient', label='Patient 2')
        )
        
        # Second patient table cannot upload
        can_upload, error = patient_table2.can_upload_file(self.user)
        self.assertFalse(can_upload)
        self.assertEqual(error, "A patient file already exists for this submission")
    
    def test_validate_file_upload(self):
        """Test comprehensive file validation."""
        from unittest.mock import Mock
        
        # Create mock file
        mock_file = Mock()
        mock_file.name = 'test.csv'
        mock_file.size = 1000  # 1KB
        
        # Valid file
        is_valid, error = self.patient_table.validate_file_upload(mock_file, self.user)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        # File too large (>3GB limit)
        mock_file.size = 4 * 1024 * 1024 * 1024  # 4GB
        is_valid, error = self.patient_table.validate_file_upload(mock_file, self.user)
        self.assertFalse(is_valid)
        self.assertIn("exceeds maximum", error)
        
        # Invalid extension
        mock_file.name = 'test.pdf'
        mock_file.size = 1000
        is_valid, error = self.patient_table.validate_file_upload(mock_file, self.user)
        self.assertFalse(is_valid)
        self.assertIn("Invalid file type", error)