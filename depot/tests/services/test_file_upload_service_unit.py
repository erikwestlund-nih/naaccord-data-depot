"""
Unit tests for FileUploadService (no database required)

Tests the pure functions in FileUploadService that don't require database access.
"""
import hashlib
import unittest
from unittest.mock import Mock, MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile

from depot.services.file_upload_service import FileUploadService


class TestFileUploadServiceUnit(unittest.TestCase):
    """Unit tests for FileUploadService that don't require database."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = FileUploadService()
    
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
    
    def test_calculate_file_hash_large_file(self):
        """Test hash calculation for larger file."""
        # Create a larger test file (1MB)
        content = b"x" * (1024 * 1024)
        test_file = SimpleUploadedFile(
            "large.csv",
            content,
            content_type="text/csv"
        )
        
        # Calculate hash
        result_hash = self.service.calculate_file_hash(test_file)
        
        # Verify hash
        expected_hash = hashlib.sha256(content).hexdigest()
        self.assertEqual(result_hash, expected_hash)
    
    def test_build_versioned_filename(self):
        """Test versioned filename generation."""
        # Test basic versioning
        filename = self.service.build_versioned_filename("patient_data.csv", 1)
        self.assertEqual(filename, "v1_patient_data.csv")
        
        filename = self.service.build_versioned_filename("patient_data.csv", 5)
        self.assertEqual(filename, "v5_patient_data.csv")
        
        # Test with different extensions
        filename = self.service.build_versioned_filename("data.txt", 3)
        self.assertEqual(filename, "v3_data.txt")
        
        filename = self.service.build_versioned_filename("report.pdf", 2)
        self.assertEqual(filename, "v2_report.pdf")
    
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
        
        # Test with dots in filename
        filename = self.service.build_versioned_filename(
            "patient.data.2024.csv",
            4
        )
        self.assertEqual(filename, "v4_patient.data.2024.csv")
    
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
        
        # Test with different parameters
        path = self.service.build_storage_path(
            cohort_id=42,
            cohort_name="Another Cohort",
            protocol_year="2025",
            file_type="laboratory",
            filename="lab_results.csv",
            is_attachment=False
        )
        
        expected = "42_Another_Cohort/2025/laboratory/lab_results.csv"
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
        
        # Test with multiple special characters
        path = self.service.build_storage_path(
            cohort_id=3,
            cohort_name="Test / Cohort & Name",
            protocol_year="2024",
            file_type="medication",
            filename="meds.csv",
            is_attachment=False
        )
        
        expected = "3_Test_-_Cohort_&_Name/2024/medication/meds.csv"
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

        # Test attachment with different file type
        path = self.service.build_storage_path(
            cohort_id=5,
            cohort_name="Research Cohort",
            protocol_year="2023",
            file_type="laboratory",
            filename="lab_protocol.docx",
            is_attachment=True,
            attachment_id=456  # Provide attachment_id to avoid timestamp
        )

        expected = "5_Research_Cohort/2023/laboratory/attachments/456/lab_protocol.docx"
        self.assertEqual(path, expected)
    
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
    
    def test_prepare_file_metadata_none_values(self):
        """Test metadata preparation with None values."""
        test_file = SimpleUploadedFile(
            "test.csv",
            b"data",
            content_type="text/csv"
        )
        test_file.size = 100
        
        metadata = self.service.prepare_file_metadata(
            uploaded_file=test_file,
            version=3,
            file_name=None,
            file_comments=None
        )
        
        expected = {
            'original_filename': 'test.csv',
            'file_size': 100,
            'version': 3,
            'name': '',
            'comments': '',
            'versioned_filename': 'v3_test.csv'
        }
        
        self.assertEqual(metadata, expected)


if __name__ == '__main__':
    unittest.main()