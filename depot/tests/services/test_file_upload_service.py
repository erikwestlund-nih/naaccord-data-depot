"""
Tests for FileUploadService

Tests the centralized file upload service functionality including:
- File hash calculation
- Storage path generation
- File versioning
- Upload record management
"""
import hashlib
import io
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from depot.services.file_upload_service import FileUploadService
from depot.models import (
    UploadedFile, 
    UploadType, 
    DataTableFile,
    CohortSubmissionDataTable,
    CohortSubmission,
    DataFileType,
    Cohort,
    ProtocolYear
)

User = get_user_model()


class TestFileUploadService(TestCase):
    """Test cases for FileUploadService."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = FileUploadService()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create test cohort
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        
        # Create protocol year
        self.protocol_year = ProtocolYear.objects.create(
            year='2024'
        )
        
        # Create data file type
        self.file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data',
            order=1
        )
        
        # Create submission
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status='in_progress',
            started_by=self.user
        )
        
        # Create data table
        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.file_type,
            status='not_started'
        )
    
    def test_calculate_file_hash(self):
        """Test SHA256 hash calculation for uploaded file."""
        # Create a test file
        content = b"Test file content for hashing"
        test_file = SimpleUploadedFile(
            "test.csv",
            content,
            content_type="text/csv"
        )
        
        # Calculate hash
        result_hash = self.service.calculate_file_hash(test_file)
        
        # Verify hash
        expected_hash = hashlib.sha256(content).hexdigest()
        self.assertEqual(result_hash, expected_hash)
        
        # Verify file position is reset
        self.assertEqual(test_file.tell(), 0)
    
    def test_calculate_file_hash_empty_file(self):
        """Test hash calculation for empty file."""
        # Create empty file
        test_file = SimpleUploadedFile(
            "empty.csv",
            b"",
            content_type="text/csv"
        )
        
        # Calculate hash
        result_hash = self.service.calculate_file_hash(test_file)
        
        # Empty file should still have a hash
        expected_hash = hashlib.sha256(b"").hexdigest()
        self.assertEqual(result_hash, expected_hash)
    
    def test_build_versioned_filename(self):
        """Test versioned filename generation."""
        # Test basic versioning
        filename = self.service.build_versioned_filename("patient_data.csv", 1)
        self.assertEqual(filename, "v1_patient_data.csv")
        
        filename = self.service.build_versioned_filename("patient_data.csv", 5)
        self.assertEqual(filename, "v5_patient_data.csv")
    
    def test_build_versioned_filename_special_chars(self):
        """Test versioned filename with special characters."""
        # Test with spaces and special chars
        filename = self.service.build_versioned_filename(
            "patient data (2024).csv", 
            2
        )
        self.assertEqual(filename, "v2_patient data (2024).csv")
        
        # Test with unicode
        filename = self.service.build_versioned_filename(
            "données_patient.csv",
            1
        )
        self.assertEqual(filename, "v1_données_patient.csv")
    
    def test_build_storage_path(self):
        """Test storage path construction."""
        # Test regular data file path
        path = self.service.build_storage_path(
            cohort_id=1,
            cohort_name="Test Cohort",
            protocol_year="2024",
            file_type="patient",
            filename="patient_data.csv",
            is_attachment=False
        )
        
        expected = "1_Test_Cohort/2024/patient/patient_data.csv"
        self.assertEqual(path, expected)
    
    def test_build_storage_path_with_special_chars(self):
        """Test storage path with special characters in cohort name."""
        # Test with slashes and spaces
        path = self.service.build_storage_path(
            cohort_id=2,
            cohort_name="Test/Cohort Name",
            protocol_year="2024",
            file_type="laboratory",
            filename="lab_data.csv",
            is_attachment=False
        )
        
        expected = "2_Test-Cohort_Name/2024/laboratory/lab_data.csv"
        self.assertEqual(path, expected)
    
    def test_build_storage_path_attachment(self):
        """Test storage path for attachments."""
        path = self.service.build_storage_path(
            cohort_id=1,
            cohort_name="Test Cohort",
            protocol_year="2024",
            file_type="patient",
            filename="notes.pdf",
            is_attachment=True,
            attachment_id=123  # Provide attachment_id to avoid timestamp
        )

        # is_attachment=True adds 'attachments' subdirectory, then attachment_id, then filename
        expected = "1_Test_Cohort/2024/patient/attachments/123/notes.pdf"
        self.assertEqual(path, expected)
    
    def test_create_uploaded_file_record(self):
        """Test creation of UploadedFile database record."""
        # Create test file
        test_file = SimpleUploadedFile(
            "test.csv",
            b"test content",
            content_type="text/csv"
        )
        
        # Create record
        record = self.service.create_uploaded_file_record(
            file=test_file,
            user=self.user,
            storage_path="test/path/test.csv",
            file_hash="abc123def456",
            upload_type=UploadType.RAW
        )
        
        # Verify record
        self.assertIsInstance(record, UploadedFile)
        self.assertEqual(record.filename, "test.csv")
        self.assertEqual(record.storage_path, "test/path/test.csv")
        self.assertEqual(record.uploader, self.user)
        self.assertEqual(record.type, UploadType.RAW)
        self.assertEqual(record.file_hash, "abc123def456")
    
    def test_determine_file_version_new_file(self):
        """Test version determination for new file."""
        version, existing = self.service.determine_file_version(
            self.data_table,
            file_id=None
        )
        
        self.assertEqual(version, 1)
        self.assertIsNone(existing)
    
    def test_determine_file_version_with_existing(self):
        """Test version determination with existing file."""
        # Create existing file
        uploaded_file = UploadedFile.objects.create(
            filename="existing.csv",
            storage_path="test/existing.csv",
            uploader=self.user,
            type=UploadType.RAW,
            file_hash="existing_hash"
        )
        
        existing_file = DataTableFile.objects.create(
            data_table=self.data_table,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            version=1,
            is_current=True,
            original_filename="existing.csv",
            file_size=1000,
            file_hash="existing_hash"
        )
        
        # Test version determination
        version, existing = self.service.determine_file_version(
            self.data_table,
            file_id=None
        )
        
        self.assertEqual(version, 2)
        self.assertEqual(existing.id, existing_file.id)
    
    def test_determine_file_version_update_specific(self):
        """Test version determination when updating specific file."""
        # Create existing file
        uploaded_file = UploadedFile.objects.create(
            filename="specific.csv",
            storage_path="test/specific.csv",
            uploader=self.user,
            type=UploadType.RAW,
            file_hash="specific_hash"
        )
        
        existing_file = DataTableFile.objects.create(
            data_table=self.data_table,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            version=3,
            is_current=True,
            original_filename="specific.csv",
            file_size=2000,
            file_hash="specific_hash"
        )
        
        # Test version determination with specific file ID
        version, existing = self.service.determine_file_version(
            self.data_table,
            file_id=str(existing_file.id)
        )
        
        self.assertEqual(version, 4)
        self.assertEqual(existing.id, existing_file.id)
    
    def test_prepare_file_metadata(self):
        """Test metadata preparation for file storage."""
        test_file = SimpleUploadedFile(
            "metadata_test.csv",
            b"test content",
            content_type="text/csv"
        )
        test_file.size = 1234
        
        metadata = self.service.prepare_file_metadata(
            uploaded_file=test_file,
            version=2,
            file_name="Custom Name",
            file_comments="Test comments"
        )
        
        expected = {
            'original_filename': 'metadata_test.csv',
            'file_size': 1234,
            'version': 2,
            'name': 'Custom Name',
            'comments': 'Test comments',
            'versioned_filename': 'v2_metadata_test.csv'
        }
        
        self.assertEqual(metadata, expected)
    
    def test_prepare_file_metadata_minimal(self):
        """Test metadata preparation with minimal inputs."""
        test_file = SimpleUploadedFile(
            "minimal.csv",
            b"content",
            content_type="text/csv"
        )
        test_file.size = 500
        
        metadata = self.service.prepare_file_metadata(
            uploaded_file=test_file,
            version=1
        )
        
        expected = {
            'original_filename': 'minimal.csv',
            'file_size': 500,
            'version': 1,
            'name': '',
            'comments': '',
            'versioned_filename': 'v1_minimal.csv'
        }
        
        self.assertEqual(metadata, expected)
    
    def test_create_new_data_table_file(self):
        """Test creation of new DataTableFile."""
        # Create uploaded file record
        uploaded_file = UploadedFile.objects.create(
            filename="new_file.csv",
            storage_path="test/new_file.csv",
            uploader=self.user,
            type=UploadType.RAW,
            file_hash="new_hash"
        )
        
        metadata = {
            'name': 'New File',
            'comments': 'This is a new file',
            'version': 1,
            'original_filename': 'new_file.csv',
            'file_size': 5000
        }
        
        # Create new data table file
        data_file = self.service.create_new_data_table_file(
            data_table=self.data_table,
            uploaded_file_record=uploaded_file,
            user=self.user,
            metadata=metadata,
            file_hash="new_hash",
            raw_file_path="/nas/raw/new_file.csv"
        )
        
        # Verify creation
        self.assertIsInstance(data_file, DataTableFile)
        self.assertEqual(data_file.data_table, self.data_table)
        self.assertEqual(data_file.uploaded_by, self.user)
        self.assertEqual(data_file.name, "New File")
        self.assertEqual(data_file.comments, "This is a new file")
        self.assertEqual(data_file.version, 1)
        self.assertTrue(data_file.is_current)
        self.assertEqual(data_file.file_hash, "new_hash")
        self.assertEqual(data_file.raw_file_path, "/nas/raw/new_file.csv")
    
    @patch.object(DataTableFile, 'create_new_version')
    def test_handle_file_versioning(self, mock_create_version):
        """Test file versioning handling."""
        # Create existing file
        uploaded_file = UploadedFile.objects.create(
            filename="versioned.csv",
            storage_path="test/versioned.csv",
            uploader=self.user,
            type=UploadType.RAW,
            file_hash="version_hash"
        )
        
        data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            version=1,
            is_current=True,
            original_filename="versioned.csv",
            file_size=3000,
            file_hash="version_hash"
        )
        
        # Create new uploaded file for new version
        new_uploaded_file = UploadedFile.objects.create(
            filename="versioned_v2.csv",
            storage_path="test/versioned_v2.csv",
            uploader=self.user,
            type=UploadType.RAW,
            file_hash="version2_hash"
        )
        
        metadata = {
            'name': 'Updated File',
            'comments': 'Version 2 comments',
            'file_size': 4000,
            'original_filename': 'versioned_v2.csv'
        }
        
        # Handle versioning
        result = self.service.handle_file_versioning(
            data_table_file=data_file,
            new_uploaded_file=new_uploaded_file,
            user=self.user,
            metadata=metadata
        )
        
        # Verify versioning
        mock_create_version.assert_called_once_with(self.user, new_uploaded_file)
        self.assertEqual(result.name, "Updated File")
        self.assertEqual(result.comments, "Version 2 comments")
        self.assertEqual(result.file_size, 4000)