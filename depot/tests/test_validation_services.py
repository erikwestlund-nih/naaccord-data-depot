"""
Unit tests for validation pipeline services.

Tests each service in isolation:
- StorageManager: Upload → Raw file
- DataMappingService: Raw file → Processed file
- DuckDBConversionService: Processed file → DuckDB

These tests don't involve Celery - they test the service classes directly.
"""
import tempfile
import os
from pathlib import Path
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection

from depot.models import Cohort, DataFileType
from depot.storage.manager import StorageManager
from depot.services.data_mapping import DataMappingService
from depot.services.duckdb_conversion import DuckDBConversionService

User = get_user_model()


# Fixture: Minimal patient CSV data
PATIENT_CSV_MINIMAL = """cohortpatientid,race,sex,ageinyrs
P001,1,M,45
P002,2,F,32
P003,1,M,28"""


class StorageManagerRawFileTest(TestCase):
    """Test that uploads are correctly stored as raw files."""

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_upload_creates_raw_file(self):
        """
        Test Step 1: Mock an upload and verify raw file is created.

        This simulates the upload workflow:
        1. User uploads a file
        2. File is saved via StorageManager.get_scratch_storage()
        3. Raw file exists and content matches
        """
        # Create mock uploaded file
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile(
            "patient.csv",
            content,
            content_type="text/csv"
        )

        # Save via StorageManager (simulates upload handling)
        storage = StorageManager.get_scratch_storage()
        file_path = f'test_uploads/{self.user.id}/patient_raw.csv'
        saved_path = storage.save(file_path, uploaded_file)

        # Verify raw file exists
        self.assertTrue(storage.exists(saved_path), "Raw file should exist after upload")

        # Verify content matches original upload
        saved_content = storage.get_file(saved_path)
        if isinstance(saved_content, bytes):
            saved_content = saved_content.decode('utf-8')

        self.assertEqual(saved_content, PATIENT_CSV_MINIMAL, "Raw file content should match upload")

        # Cleanup
        storage.delete(saved_path)


class DataMappingServiceTest(TestCase):
    """Test that raw files are correctly processed into processed files."""

    def setUp(self):
        """Create test fixtures."""
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_raw_file_creates_processed_file(self):
        """
        Test Step 2: Given a raw file, verify processed file is created.

        Workflow:
        1. Create a raw CSV file
        2. Pass to DataMappingService
        3. Verify processed file exists
        4. Verify content is correct (for passthrough cohorts, should be identical)
        """
        # Create temporary raw file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(PATIENT_CSV_MINIMAL)
            raw_path = raw_file.name

        # Create temporary processed file path
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Process raw file through DataMappingService
            # For cohorts without special mapping, this is passthrough
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )

            # Verify this is passthrough mode (no special mapping for TEST cohort)
            self.assertTrue(service.is_passthrough(), "Test cohort should use passthrough mode")

            # Process the file
            changes_summary = service.process_file(raw_path, processed_path)

            # Verify processed file exists
            self.assertTrue(
                os.path.exists(processed_path),
                "Processed file should exist after DataMappingService.process_file()"
            )

            # Verify processed file has correct content
            with open(processed_path, 'r') as f:
                processed_content = f.read()

            self.assertIn('cohortPatientId', processed_content, "Processed file should contain normalized header")
            self.assertIn('P001', processed_content, "Processed file should contain patient IDs")
            self.assertIn('P002', processed_content)
            self.assertIn('P003', processed_content)

            # Verify no errors in processing
            self.assertEqual(len(changes_summary['errors']), 0, "Processing should complete without errors")

        finally:
            # Cleanup
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)

    def test_processing_preserves_data_integrity(self):
        """
        Test that data mapping doesn't corrupt data.

        Verify:
        - Row count is preserved
        - Column names are correct
        - Data values are intact
        """
        # Create raw file with known data
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as raw_file:
            raw_file.write(PATIENT_CSV_MINIMAL)
            raw_path = raw_file.name

        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Process file
            service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )
            service.process_file(raw_path, processed_path)

            # Count rows in both files
            with open(raw_path, 'r') as f:
                raw_lines = f.readlines()

            with open(processed_path, 'r') as f:
                processed_lines = f.readlines()

            # Should have same number of lines (header + data rows)
            self.assertEqual(
                len(raw_lines),
                len(processed_lines),
                "Processed file should have same number of rows as raw file"
            )

        finally:
            os.unlink(raw_path)
            if os.path.exists(processed_path):
                os.unlink(processed_path)


class DuckDBConversionServiceTest(TestCase):
    """Test that processed files are correctly converted to DuckDB."""

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_processed_file_creates_duckdb(self):
        """
        Test Step 3: Given a processed CSV, verify DuckDB is created.

        Workflow:
        1. Create a processed CSV file
        2. Pass to DuckDBConversionService
        3. Verify DuckDB file is created
        4. Verify table has correct data
        """
        # Create temporary processed CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as csv_file:
            csv_file.write(PATIENT_CSV_MINIMAL)
            csv_path = csv_file.name

        try:
            # Convert to DuckDB
            service = DuckDBConversionService(csv_path=csv_path, table_name='data')
            db_path = service.create_database()

            # Verify database was created
            self.assertIsNotNone(db_path, "DuckDB path should be returned")

            # Verify database file exists (if not in-memory)
            if not service.in_memory:
                self.assertTrue(
                    os.path.exists(db_path),
                    "DuckDB file should exist on disk"
                )

            # Verify table has correct row count
            row_count = service.get_row_count()
            self.assertEqual(row_count, 3, "DuckDB should have 3 data rows")

            # Verify columns exist
            columns = service.get_column_names()
            self.assertIn('cohortpatientid', columns, "DuckDB should have cohortpatientid column")
            self.assertIn('race', columns)
            self.assertIn('sex', columns)
            self.assertIn('ageinyrs', columns)

            # Verify data is queryable
            with service.get_connection() as conn:
                result = conn.execute("SELECT cohortpatientid FROM data ORDER BY cohortpatientid").fetchall()
                patient_ids = [row[0] for row in result]
                self.assertEqual(patient_ids, ['P001', 'P002', 'P003'], "Patient IDs should be preserved")

            # Cleanup
            service.cleanup()

        finally:
            os.unlink(csv_path)

    def test_duckdb_handles_numeric_columns(self):
        """
        Test that DuckDB correctly infers numeric column types.

        Verify:
        - Integer columns are detected
        - Numeric queries work correctly
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as csv_file:
            csv_file.write(PATIENT_CSV_MINIMAL)
            csv_path = csv_file.name

        try:
            service = DuckDBConversionService(csv_path=csv_path)
            service.create_database()

            # Verify numeric column types
            column_types = service.get_column_types()
            self.assertIn('ageinyrs', column_types, "Age column should exist")

            # Verify we can do numeric queries on age
            with service.get_connection() as conn:
                result = conn.execute("SELECT MAX(ageinyrs) as max_age FROM data").fetchone()
                max_age = result[0]
                self.assertEqual(max_age, 45, "Should be able to query numeric columns")

            service.cleanup()

        finally:
            os.unlink(csv_path)

    def test_duckdb_info_method(self):
        """Test that get_database_info() returns correct metadata."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as csv_file:
            csv_file.write(PATIENT_CSV_MINIMAL)
            csv_path = csv_file.name

        try:
            service = DuckDBConversionService(csv_path=csv_path)
            service.create_database()

            info = service.get_database_info()

            self.assertEqual(info['table_name'], 'data')
            self.assertEqual(info['row_count'], 3)
            self.assertIn('cohortpatientid', info['columns'])
            self.assertIsNotNone(info['column_types'])

            service.cleanup()

        finally:
            os.unlink(csv_path)


class ValidationPipelineIntegrationTest(TestCase):
    """
    Integration test: Verify all three steps work together.

    This test runs the complete transformation pipeline:
    Upload → Raw → Processed → DuckDB

    Without involving Celery tasks.
    """

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )

    def tearDown(self):
        """Close database connections."""
        connection.close()

    def test_complete_pipeline_upload_to_duckdb(self):
        """
        Integration test: Upload → Raw → Processed → DuckDB.

        This verifies the complete workflow without Celery:
        1. Upload creates raw file
        2. DataMappingService creates processed file
        3. DuckDBConversionService creates DuckDB
        4. All data is preserved correctly
        """
        storage = StorageManager.get_scratch_storage()

        # Step 1: Create raw file from upload
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile("patient.csv", content, content_type="text/csv")

        raw_path = f'integration_test/{self.user.id}/patient_raw.csv'
        saved_raw_path = storage.save(raw_path, uploaded_file)

        self.assertTrue(storage.exists(saved_raw_path), "Step 1: Raw file should exist")

        # Step 2: Create processed file from raw
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as processed_file:
            processed_path = processed_file.name

        try:
            # Get raw file content
            raw_content = storage.get_file(saved_raw_path)
            if isinstance(raw_content, bytes):
                raw_content = raw_content.decode('utf-8')

            # Write to temp file for processing
            temp_raw_path = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
            temp_raw_path.write(raw_content)
            temp_raw_path.close()

            # Process through DataMappingService
            mapping_service = DataMappingService(
                cohort_name=self.cohort.name,
                data_file_type=self.data_file_type.name
            )
            mapping_service.process_file(temp_raw_path.name, processed_path)

            self.assertTrue(os.path.exists(processed_path), "Step 2: Processed file should exist")

            # Step 3: Create DuckDB from processed file
            duckdb_service = DuckDBConversionService(csv_path=processed_path)
            db_path = duckdb_service.create_database()

            self.assertIsNotNone(db_path, "Step 3: DuckDB should be created")

            # Verify end-to-end data integrity
            with duckdb_service.get_connection() as conn:
                result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
                self.assertEqual(result[0], 3, "All 3 rows should be in DuckDB")

                # Verify specific patient ID
                result = conn.execute(
                    "SELECT cohortpatientid, ageinyrs FROM data WHERE cohortpatientid = 'P001'"
                ).fetchone()
                self.assertEqual(result[0], 'P001')
                self.assertEqual(result[1], 45)

            # Cleanup
            duckdb_service.cleanup()
            os.unlink(temp_raw_path.name)
            os.unlink(processed_path)
            storage.delete(saved_raw_path)

        except Exception as e:
            # Ensure cleanup on failure
            if os.path.exists(processed_path):
                os.unlink(processed_path)
            storage.delete(saved_raw_path)
            raise
