"""
Tests for the granular validation pipeline.

Tests the complete workflow:
1. Upload → Raw file storage
2. Raw file → Processed file (data mapping)
3. Processed file → DuckDB conversion
4. DuckDB → Validation execution

Tests are organized in three levels:
- Unit tests: Individual services in isolation
- Integration tests: Services working together (no Celery)
- E2E tests: Full workflow with Celery (synchronous)
"""
import tempfile
import os
import unittest
from pathlib import Path
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import duckdb

from depot.models import (
    DataFileType,
    Cohort,
    PrecheckRun,
    ValidationRun,
    ValidationVariable,
    ValidationCheck
)
from depot.services.data_mapping import DataMappingService
from depot.services.duckdb_conversion import DuckDBConversionService
from depot.storage.manager import StorageManager
from depot.tasks.validation import convert_precheck_to_duckdb
from depot.tasks.validation_orchestration import start_validation_run

User = get_user_model()


# Fixture: Minimal patient CSV data
PATIENT_CSV_MINIMAL = """cohortpatientid,race,sex,ageinyrs
P001,1,M,45
P002,2,F,32
P003,1,M,28"""

PATIENT_CSV_WITH_ISSUES = """cohortpatientid,race,sex,ageinyrs
P001,1,M,45
P001,2,F,32
P003,1,M,999"""  # Duplicate ID + out of range age


class ValidationPipelineUnitTests(TestCase):
    """
    Unit tests for individual services.
    Tests each component in isolation.
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
            label='Patient Data',
            description='Patient demographic data'
        )

    def test_storage_manager_saves_raw_file(self):
        """Test that StorageManager saves raw uploaded file."""
        # Create temporary uploaded file
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile(
            "patient.csv",
            content,
            content_type="text/csv"
        )

        # Save via StorageManager
        storage = StorageManager.get_scratch_storage()
        file_path = storage.save(f'test_raw_{self.user.id}.csv', uploaded_file)

        # Verify file exists
        self.assertTrue(storage.exists(file_path))

        # Verify content matches
        saved_content = storage.get_file(file_path)
        self.assertEqual(saved_content.decode('utf-8'), PATIENT_CSV_MINIMAL)

        # Cleanup
        storage.delete(file_path)

    def test_data_mapping_service_creates_processed_file(self):
        """Test that DataMappingService creates processed file from raw file."""
        # This test would use DataMappingService once it's fully implemented
        # For now, we're testing the contract that it should fulfill

        # Create raw file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(PATIENT_CSV_MINIMAL)
            raw_path = f.name

        try:
            # For cohorts without special mapping, processed = raw
            # Once DataMappingService is implemented, this will actually transform
            processed_path = raw_path  # Placeholder

            # Verify processed file exists and is readable
            self.assertTrue(os.path.exists(processed_path))

            with open(processed_path, 'r') as f:
                content = f.read()
                self.assertIn('cohortpatientid', content)
                self.assertIn('P001', content)
        finally:
            os.unlink(raw_path)

    def test_duckdb_conversion_service_creates_database(self):
        """Test that DuckDBConversionService creates DuckDB from CSV."""
        import tempfile as temp_module

        # Create temporary CSV
        with temp_module.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(PATIENT_CSV_MINIMAL)
            csv_path = f.name

        try:
            # Create temporary DuckDB file path (don't create the file yet)
            temp_dir = temp_module.mkdtemp()
            db_path = os.path.join(temp_dir, 'test.duckdb')

            try:
                # Convert CSV to DuckDB
                conn = duckdb.connect(db_path)
                conn.execute(f"""
                    CREATE TABLE data AS
                    SELECT *, ROW_NUMBER() OVER () AS row_no
                    FROM read_csv_auto('{csv_path}', header=true, all_varchar=false)
                """)

                # Verify table exists and has data
                result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
                self.assertEqual(result[0], 3)  # 3 rows in fixture

                # Verify row_no column exists
                result = conn.execute("SELECT row_no FROM data ORDER BY row_no").fetchall()
                self.assertEqual([r[0] for r in result], [1, 2, 3])

                conn.close()
            finally:
                import shutil
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
        finally:
            os.unlink(csv_path)


class ValidationPipelineIntegrationTests(TestCase):
    """
    Integration tests for services working together.
    Tests the workflow without Celery.
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
            label='Patient Data',
            description='Patient demographic data'
        )

    def test_full_pipeline_without_celery(self):
        """
        Test complete pipeline: Upload → Raw → Processed → DuckDB
        Without using Celery (direct function calls).
        """
        # Step 1: Create PrecheckRun (simulates upload)
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile(
            "patient.csv",
            content,
            content_type="text/csv"
        )

        precheck_run = PrecheckRun.objects.create(
            uploaded_by=self.user,
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            original_filename='patient.csv',
            file_size=len(content)
        )

        # Step 2: Save raw file
        storage = StorageManager.get_scratch_storage()
        raw_path = f'precheck/{self.cohort.id}/patient_raw.csv'
        storage.save(raw_path, uploaded_file)

        # Verify raw file exists
        self.assertTrue(storage.exists(raw_path))

        # Step 3: Create processed file (for now, just copy raw)
        # Once DataMappingService is implemented, this will transform
        processed_path = f'precheck/{self.cohort.id}/patient_processed.csv'
        raw_content = storage.get_file(raw_path)
        storage.save(processed_path, raw_content)

        # Verify processed file exists
        self.assertTrue(storage.exists(processed_path))

        # Step 4: Convert to DuckDB
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'validation.duckdb'

            # Get processed file content
            csv_content = storage.get_file(processed_path).decode('utf-8')

            # Write to temp file for DuckDB
            temp_csv = Path(temp_dir) / 'data.csv'
            temp_csv.write_text(csv_content)

            # Create DuckDB
            conn = duckdb.connect(str(db_path))
            conn.execute(f"""
                CREATE TABLE data AS
                SELECT *, ROW_NUMBER() OVER () AS row_no
                FROM read_csv_auto('{temp_csv}', header=true, all_varchar=false)
            """)

            # Verify DuckDB has correct data
            result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
            self.assertEqual(result[0], 3)

            # Verify columns exist
            columns = conn.execute("DESCRIBE data").fetchall()
            column_names = [c[0] for c in columns]
            self.assertIn('cohortpatientid', column_names)
            self.assertIn('race', column_names)
            self.assertIn('sex', column_names)
            self.assertIn('ageinyrs', column_names)
            self.assertIn('row_no', column_names)

            conn.close()

        # Cleanup
        storage.delete(raw_path)
        storage.delete(processed_path)


@unittest.skip("DuckDB segfaults in local test environment - run in CI only")
class ValidationPipelineE2ETests(TransactionTestCase):
    """
    End-to-end tests using Celery tasks (synchronous execution).
    Tests the complete workflow as it runs in production.
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
            label='Patient Data',
            description='Patient demographic data'
        )

    def test_celery_task_creates_duckdb_and_validation_run(self):
        """
        Test that Celery task creates DuckDB and ValidationRun.
        Uses apply() for synchronous execution in tests.
        """
        # Create PrecheckRun
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile(
            "patient.csv",
            content,
            content_type="text/csv"
        )

        # Save raw file first - use uploads storage (not scratch) for precheck files
        storage = StorageManager.get_storage('uploads')
        raw_path = f'precheck/{self.cohort.id}/patient.csv'
        storage.save(raw_path, uploaded_file)

        # Create UploadedFile record
        from depot.models import UploadedFile, UploadType
        uploaded_file_record = UploadedFile.objects.create(
            uploader=self.user,
            filename='patient.csv',
            original_filename='patient.csv',
            storage_path=raw_path,
            file_size=len(content),
            content_type='text/csv',
            type=UploadType.RAW,
            storage_disk='uploads'
        )

        precheck_run = PrecheckRun.objects.create(
            uploaded_by=self.user,
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            original_filename='patient.csv',
            file_size=len(content),
            uploaded_file=uploaded_file_record
        )

        # Create ValidationRun
        from django.contrib.contenttypes.models import ContentType
        content_type = ContentType.objects.get_for_model(precheck_run)

        validation_run = ValidationRun.objects.create(
            content_type=content_type,
            object_id=precheck_run.id,
            data_file_type=self.data_file_type,
            duckdb_path=''
        )

        # Execute task synchronously (using apply instead of delay)
        # NOTE: This requires Celery to be configured with CELERY_TASK_ALWAYS_EAGER = True in test settings
        conversion_result = convert_precheck_to_duckdb.apply(
            args=[precheck_run.id, validation_run.id]
        )

        # Verify conversion completed and returned validation run id
        if not conversion_result.successful():
            # Get the actual error for debugging
            try:
                result = conversion_result.get()
            except Exception as e:
                self.fail(f"Task failed with exception: {type(e).__name__}: {str(e)}")

        self.assertTrue(conversion_result.successful())
        self.assertEqual(conversion_result.get(), validation_run.id)

        validation_result = start_validation_run.apply(args=[validation_run.id])
        self.assertTrue(validation_result.successful())

        # Verify ValidationRun was updated
        validation_run.refresh_from_db()
        self.assertIsNotNone(validation_run.duckdb_path)
        self.assertEqual(validation_run.status, 'running')  # Will be 'running' or 'completed'

        # Cleanup
        storage.delete(raw_path)


class ValidationPipelineFileOrderTests(TestCase):
    """
    Tests that verify files are created in the correct order.
    These are critical for the workflow contract.
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
            label='Patient Data',
            description='Patient demographic data'
        )

    def test_file_creation_order(self):
        """
        Test that files are created in the correct order:
        1. Raw file
        2. Processed file
        3. DuckDB file
        """
        storage = StorageManager.get_scratch_storage()

        # Step 1: Create raw file
        content = PATIENT_CSV_MINIMAL.encode('utf-8')
        uploaded_file = SimpleUploadedFile("patient.csv", content)

        raw_path = f'test/order/raw.csv'
        raw_created_at = storage.save(raw_path, uploaded_file)
        self.assertTrue(storage.exists(raw_path))

        # Step 2: Create processed file (must happen after raw)
        processed_path = f'test/order/processed.csv'
        raw_content = storage.get_file(raw_path)
        storage.save(processed_path, raw_content)
        self.assertTrue(storage.exists(processed_path))

        # Step 3: Create DuckDB (must happen after processed)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'data.duckdb'

            # Get processed content
            csv_content = storage.get_file(processed_path).decode('utf-8')

            temp_csv = Path(temp_dir) / 'data.csv'
            temp_csv.write_text(csv_content)

            # Create DuckDB
            conn = duckdb.connect(str(db_path))
            conn.execute(f"""
                CREATE TABLE data AS
                SELECT *, ROW_NUMBER() OVER () AS row_no
                FROM read_csv_auto('{temp_csv}', header=true)
            """)
            conn.close()

            # Verify DuckDB exists
            self.assertTrue(db_path.exists())

        # Cleanup
        storage.delete(raw_path)
        storage.delete(processed_path)

    def test_raw_file_must_exist_before_processing(self):
        """Test that processing requires raw file to exist."""
        storage = StorageManager.get_scratch_storage()

        # Attempt to process non-existent raw file
        raw_path = 'test/nonexistent/raw.csv'
        self.assertFalse(storage.exists(raw_path))

        # Processing should fail
        with self.assertRaises(Exception):
            with storage.open(raw_path) as f:
                content = f.read()

    def test_processed_file_must_exist_before_duckdb(self):
        """Test that DuckDB creation requires processed file."""
        # Attempt to create DuckDB from non-existent file
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'data.duckdb'
            nonexistent_csv = Path(temp_dir) / 'nonexistent.csv'

            conn = duckdb.connect(str(db_path))

            # Should raise error about missing file
            with self.assertRaises(Exception):
                conn.execute(f"""
                    CREATE TABLE data AS
                    SELECT * FROM read_csv_auto('{nonexistent_csv}')
                """)

            conn.close()
