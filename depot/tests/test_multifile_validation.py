"""
Tests for multi-file validation with file and row number tracking.

This module tests:
1. DuckDBCombinerService - combining multiple DuckDB files
2. VariableValidator - detecting combined files and tracking affected rows
3. ValidationCheck - storing file/row information in database
4. End-to-end validation workflow with multiple files
"""
import os
import shutil
import tempfile
from pathlib import Path

import duckdb
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType

from depot.models import (
    Cohort, User, DataFileType, ProtocolYear, CohortSubmission,
    CohortSubmissionDataTable, DataTableFile, ValidationRun, ValidationVariable, ValidationCheck
)
from depot.services.duckdb_combiner import DuckDBCombinerService
from depot.validators.variable_validator import VariableValidator


class DuckDBCombinerServiceTests(TestCase):
    """Test DuckDBCombinerService functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.workspace = Path(tempfile.mkdtemp(prefix="combiner-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.workspace, ignore_errors=True))

        # Create test cohort and user
        self.cohort = Cohort.objects.create(name="Test Cohort")
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def _create_test_duckdb(self, filename: str, data: list) -> str:
        """
        Create a test DuckDB file with patient data.

        Args:
            filename: Name for the DuckDB file (will be converted to Parquet)
            data: List of tuples (cohortPatientId, visitDate)

        Returns:
            Absolute path to created Parquet file (DuckDB reads Parquet directly)
        """
        # DuckDBCombinerService reads from Parquet files, not DuckDB database files
        # Create a Parquet file instead
        parquet_path = self.workspace / filename.replace('.duckdb', '.parquet')
        temp_db_path = self.workspace / f"temp_{filename}"

        conn = duckdb.connect(str(temp_db_path))

        # Create table with data
        if data:
            values_str = ", ".join([f"('{patient_id}', '{visit_date}')" for patient_id, visit_date in data])
            conn.execute(f"""
                CREATE TABLE data AS
                SELECT * FROM (VALUES
                    {values_str}
                ) AS t(cohortPatientId, visitDate)
            """)

            # Export to Parquet
            conn.execute(f"COPY data TO '{parquet_path}' (FORMAT PARQUET)")

        conn.close()

        # Clean up temp database
        import os
        if temp_db_path.exists():
            os.remove(temp_db_path)

        return str(parquet_path)

    def _create_data_table_file(self, duckdb_path: str, order: int) -> DataTableFile:
        """Create a DataTableFile instance with DuckDB path."""
        # Create necessary related objects
        protocol_year = ProtocolYear.objects.create(year=2024)
        file_type = DataFileType.objects.create(name="patient", description="Patient data")

        submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=protocol_year,
            status='in_progress',
            started_by=self.user
        )

        data_table = CohortSubmissionDataTable.objects.create(
            submission=submission,
            data_file_type=file_type
        )

        return DataTableFile.objects.create(
            data_table=data_table,
            version=order,
            uploaded_by=self.user,
            duckdb_file_path=duckdb_path
        )

    def test_combine_two_files(self):
        """Test combining two DuckDB files adds source metadata."""
        # Create two test DuckDB files
        db1_path = self._create_test_duckdb("file1.duckdb", [
            ("P001", "2024-01-15"),
            ("P002", "2024-01-16"),
        ])
        db2_path = self._create_test_duckdb("file2.duckdb", [
            ("P003", "2024-02-10"),
            ("P004", "2024-02-11"),
        ])

        # Create DataTableFile instances
        file1 = self._create_data_table_file(db1_path, 1)
        file2 = self._create_data_table_file(db2_path, 2)

        # Combine files
        service = DuckDBCombinerService(self.workspace)
        combined_path = service.combine_files([file1, file2], self.cohort, self.user)

        # Verify combined file was created
        self.assertIsNotNone(combined_path)
        self.assertTrue(os.path.exists(combined_path))

        # Verify combined file has metadata columns
        conn = duckdb.connect(combined_path, read_only=True)

        # Check for metadata columns
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'data'"
        ).fetchall()
        column_names = [col[0] for col in columns]

        self.assertIn('__source_file_id', column_names)
        self.assertIn('__source_row_number', column_names)

        # Verify row count
        total_rows = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
        self.assertEqual(total_rows, 4)  # 2 from each file

        # Verify source file IDs are correct
        file1_rows = conn.execute(
            "SELECT COUNT(*) FROM data WHERE __source_file_id = ?",
            [file1.id]
        ).fetchone()[0]
        self.assertEqual(file1_rows, 2)

        file2_rows = conn.execute(
            "SELECT COUNT(*) FROM data WHERE __source_file_id = ?",
            [file2.id]
        ).fetchone()[0]
        self.assertEqual(file2_rows, 2)

        # Verify row numbers are sequential per file
        file1_row_numbers = conn.execute(
            "SELECT __source_row_number FROM data WHERE __source_file_id = ? ORDER BY __source_row_number",
            [file1.id]
        ).fetchall()
        self.assertEqual([r[0] for r in file1_row_numbers], [1, 2])

        conn.close()

    def test_single_file_returns_original(self):
        """Test that single file doesn't trigger combining."""
        db_path = self._create_test_duckdb("single.duckdb", [
            ("P001", "2024-01-15"),
        ])

        file1 = self._create_data_table_file(db_path, 1)

        service = DuckDBCombinerService(self.workspace)
        result_path = service.combine_files([file1], self.cohort, self.user)

        # Should return the original path, not create a new file
        self.assertEqual(result_path, db_path)

    def test_empty_file_list_returns_none(self):
        """Test that empty file list returns None."""
        service = DuckDBCombinerService(self.workspace)
        result = service.combine_files([], self.cohort, self.user)

        self.assertIsNone(result)


class VariableValidatorFileTrackingTests(TestCase):
    """Test VariableValidator file and row tracking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.workspace = Path(tempfile.mkdtemp(prefix="validator-tracking-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.workspace, ignore_errors=True))

    def _create_combined_duckdb(self, data_by_file: dict) -> str:
        """
        Create a combined DuckDB with source metadata.

        Args:
            data_by_file: Dict mapping file_id to list of (cohortPatientId, age) tuples

        Returns:
            Path to created DuckDB file
        """
        db_path = self.workspace / "combined.duckdb"
        conn = duckdb.connect(str(db_path))

        # Create table with metadata columns
        conn.execute("""
            CREATE TABLE data (
                cohortPatientId VARCHAR,
                age INTEGER,
                __source_file_id INTEGER,
                __source_row_number INTEGER,
                row_no INTEGER
            )
        """)

        # Insert data from each file
        row_no = 1
        for file_id, rows in data_by_file.items():
            for idx, (patient_id, age) in enumerate(rows, start=1):
                conn.execute(
                    "INSERT INTO data VALUES (?, ?, ?, ?, ?)",
                    [patient_id, age, file_id, idx, row_no]
                )
                row_no += 1

        conn.close()
        return str(db_path)

    def test_detects_combined_duckdb(self):
        """Test that validator detects combined DuckDB files."""
        db_path = self._create_combined_duckdb({
            1: [("P001", 25)],
            2: [("P002", 30)],
        })

        variable_def = {
            'name': 'age',
            'type': 'int',
            'validators': []
        }

        with VariableValidator(db_path, variable_def, None) as validator:
            # Should detect combined file
            self.assertTrue(validator.is_combined_duckdb)

    def test_no_duplicates_tracks_affected_rows(self):
        """Test that no_duplicates validator tracks file and row for duplicates."""
        # Create data with duplicates across files
        db_path = self._create_combined_duckdb({
            5: [("P001", 25), ("P002", 30)],
            7: [("P001", 28), ("P003", 35)],  # P001 is duplicate
        })

        variable_def = {
            'name': 'cohortPatientId',
            'type': 'id',
            'validators': ['no_duplicates']
        }

        with VariableValidator(db_path, variable_def, None) as validator:
            results = validator.validate()

        # Should fail due to duplicates
        self.assertFalse(results['passed'])
        self.assertEqual(results['error_count'], 1)

        # Check the validation check result
        check = results['checks'][0]
        self.assertEqual(check['check_type'], 'no_duplicates')
        self.assertFalse(check['passed'])

        # Should have affected_rows with file tracking
        self.assertIn('affected_rows', check)
        affected = check['affected_rows']

        # Should have 2 rows (both instances of P001)
        self.assertEqual(len(affected), 2)

        # Verify file IDs are correct
        file_ids = {row['file_id'] for row in affected}
        self.assertEqual(file_ids, {5, 7})

        # Verify source row numbers
        for row in affected:
            self.assertIn('source_row', row)
            self.assertIn('duckdb_row', row)

    def test_range_validator_tracks_affected_rows(self):
        """Test that range validator tracks file and row for out-of-range values."""
        db_path = self._create_combined_duckdb({
            10: [("P001", 25), ("P002", 150)],  # 150 is out of range
            11: [("P003", 30), ("P004", 200)],  # 200 is out of range
        })

        variable_def = {
            'name': 'age',
            'type': 'int',
            'validators': [
                {'name': 'range', 'params': [0, 120]}
            ]
        }

        with VariableValidator(db_path, variable_def, None) as validator:
            results = validator.validate()

        # Should fail due to out-of-range values
        self.assertFalse(results['passed'])

        # Check the range validation result
        check = results['checks'][0]
        self.assertEqual(check['check_type'], 'range')
        self.assertFalse(check['passed'])

        # Should have affected_rows
        self.assertIn('affected_rows', check)
        affected = check['affected_rows']

        # Should have 2 rows
        self.assertEqual(len(affected), 2)

        # Verify invalid values are included
        values = {row['value'] for row in affected}
        self.assertEqual(values, {150, 200})

        # Verify file tracking
        file_ids = {row['file_id'] for row in affected}
        self.assertEqual(file_ids, {10, 11})


class ValidationCheckFileTrackingTests(TestCase):
    """Test that ValidationCheck model stores file/row information correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.cohort = Cohort.objects.create(name="Test Cohort")
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.protocol_year = ProtocolYear.objects.create(year=2024)
        self.file_type = DataFileType.objects.create(name="patient", description="Patient data")

        # Create submission and validation run
        submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status='in_progress',
            started_by=self.user
        )

        content_type = ContentType.objects.get_for_model(submission)
        self.validation_run = ValidationRun.objects.create(
            content_type=content_type,
            object_id=submission.id,
            data_file_type=self.file_type,
            status='running'
        )

        self.validation_variable = ValidationVariable.objects.create(
            validation_run=self.validation_run,
            column_name='cohortPatientId',
            column_type='id',
            display_name='Patient ID'
        )

    def test_stores_affected_rows_in_meta(self):
        """Test that affected rows are stored in ValidationCheck.meta field."""
        affected_rows = [
            {'file_id': 5, 'source_row': 10, 'duckdb_row': 15},
            {'file_id': 5, 'source_row': 25, 'duckdb_row': 30},
            {'file_id': 7, 'source_row': 8, 'duckdb_row': 45},
        ]

        check = ValidationCheck.objects.create(
            validation_variable=self.validation_variable,
            rule_key='no_duplicates',
            passed=False,
            severity='error',
            message='Found 3 duplicate values',
            affected_row_count=3,
            row_numbers='file_5:row_10, file_5:row_25, file_7:row_8',
            meta={
                'affected_rows': affected_rows,
                'has_file_tracking': True,
                'duplicate_count': 3
            }
        )

        # Retrieve and verify
        saved_check = ValidationCheck.objects.get(id=check.id)

        self.assertEqual(saved_check.affected_row_count, 3)
        self.assertTrue(saved_check.meta['has_file_tracking'])
        self.assertEqual(len(saved_check.meta['affected_rows']), 3)

        # Verify row_numbers format
        self.assertIn('file_5:row_10', saved_check.row_numbers)
        self.assertIn('file_7:row_8', saved_check.row_numbers)

    def test_row_numbers_display_method(self):
        """Test that get_row_numbers_display works with file:row format."""
        check = ValidationCheck.objects.create(
            validation_variable=self.validation_variable,
            rule_key='range',
            passed=False,
            severity='error',
            message='Out of range',
            row_numbers='file_5:row_10, file_5:row_25, file_7:row_8'
        )

        display = check.get_row_numbers_display(max_display=10)
        self.assertEqual(display, 'file_5:row_10, file_5:row_25, file_7:row_8')

    def test_handles_many_affected_rows(self):
        """Test handling of large number of affected rows."""
        # Create 500 affected rows
        affected_rows = [
            {'file_id': i % 10, 'source_row': i, 'duckdb_row': i * 2}
            for i in range(500)
        ]

        # Create row_numbers string (first 100)
        row_numbers_list = [
            f"file_{row['file_id']}:row_{row['source_row']}"
            for row in affected_rows[:100]
        ]
        row_numbers_str = ", ".join(row_numbers_list)

        check = ValidationCheck.objects.create(
            validation_variable=self.validation_variable,
            rule_key='no_duplicates',
            passed=False,
            severity='error',
            message='Found 500 duplicate values',
            affected_row_count=500,
            row_numbers=row_numbers_str,
            meta={
                'affected_rows': affected_rows,
                'has_file_tracking': True
            }
        )

        # Verify storage
        saved_check = ValidationCheck.objects.get(id=check.id)
        self.assertEqual(saved_check.affected_row_count, 500)
        self.assertEqual(len(saved_check.meta['affected_rows']), 500)

        # Verify display method limits output
        display = saved_check.get_row_numbers_display(max_display=10)
        self.assertIn('...', display)
        self.assertIn('(90 more)', display)  # 100 in row_numbers minus 10 displayed = 90 more


class MultiFileValidationIntegrationTests(TestCase):
    """Integration tests for end-to-end multi-file validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.workspace = Path(tempfile.mkdtemp(prefix="integration-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.workspace, ignore_errors=True))

        self.cohort = Cohort.objects.create(name="Test Cohort")
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.protocol_year = ProtocolYear.objects.create(year=2024)
        self.file_type = DataFileType.objects.create(name="patient", description="Patient data")

    def test_complete_workflow_with_duplicate_detection(self):
        """
        Test complete workflow:
        1. Create two DuckDB files with duplicate patient IDs
        2. Combine them
        3. Run validation
        4. Verify ValidationCheck has file/row tracking
        """
        # 1. Create two Parquet files (DuckDB combiner reads from Parquet)
        parquet1_path = self.workspace / "file1.parquet"
        temp_db1 = self.workspace / "temp1.duckdb"
        conn1 = duckdb.connect(str(temp_db1))
        conn1.execute("""
            CREATE TABLE data AS
            SELECT * FROM (VALUES
                ('P001', 25, 1, 1),
                ('P002', 30, 1, 2)
            ) AS t(cohortPatientId, age, __source_row_number, row_no)
        """)
        conn1.execute(f"COPY data TO '{parquet1_path}' (FORMAT PARQUET)")
        conn1.close()
        temp_db1.unlink()

        parquet2_path = self.workspace / "file2.parquet"
        temp_db2 = self.workspace / "temp2.duckdb"
        conn2 = duckdb.connect(str(temp_db2))
        conn2.execute("""
            CREATE TABLE data AS
            SELECT * FROM (VALUES
                ('P001', 28, 1, 3),  -- Duplicate!
                ('P003', 35, 2, 4)
            ) AS t(cohortPatientId, age, __source_row_number, row_no)
        """)
        conn2.execute(f"COPY data TO '{parquet2_path}' (FORMAT PARQUET)")
        conn2.close()
        temp_db2.unlink()

        # 2. Combine files
        submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status='in_progress',
            started_by=self.user
        )

        data_table = CohortSubmissionDataTable.objects.create(
            submission=submission,
            data_file_type=self.file_type
        )

        file1 = DataTableFile.objects.create(
            data_table=data_table,
            version=1,
            uploaded_by=self.user,
            duckdb_file_path=str(parquet1_path)
        )

        file2 = DataTableFile.objects.create(
            data_table=data_table,
            version=2,
            uploaded_by=self.user,
            duckdb_file_path=str(parquet2_path)
        )

        combiner = DuckDBCombinerService(self.workspace)
        combined_path = combiner.combine_files([file1, file2], self.cohort, self.user)

        # 3. Run validation
        content_type = ContentType.objects.get_for_model(submission)
        validation_run = ValidationRun.objects.create(
            content_type=content_type,
            object_id=submission.id,
            data_file_type=self.file_type,
            duckdb_path=combined_path,
            status='running'
        )

        validation_variable = ValidationVariable.objects.create(
            validation_run=validation_run,
            column_name='cohortPatientId',
            column_type='id',
            display_name='Patient ID'
        )

        variable_def = {
            'name': 'cohortPatientId',
            'type': 'id',
            'validators': ['no_duplicates']
        }

        # Run validation
        with VariableValidator(combined_path, variable_def, validation_variable) as validator:
            results = validator.validate()

        # 4. Create ValidationCheck (simulating what orchestration does)
        check_result = results['checks'][0]
        affected_rows = check_result.get('affected_rows', [])

        ValidationCheck.objects.create(
            validation_variable=validation_variable,
            rule_key=check_result['check_type'],
            passed=check_result['passed'],
            severity=check_result['severity'],
            message=check_result['message'],
            affected_row_count=len(affected_rows),
            meta={
                'affected_rows': affected_rows,
                'has_file_tracking': True
            }
        )

        # 5. Verify results
        check = ValidationCheck.objects.get(validation_variable=validation_variable)

        self.assertFalse(check.passed)
        self.assertEqual(check.severity, 'error')
        self.assertTrue(check.meta['has_file_tracking'])

        # Should have tracked 2 instances of P001
        affected = check.meta['affected_rows']
        self.assertEqual(len(affected), 2)

        # Verify file IDs
        file_ids = {row['file_id'] for row in affected}
        self.assertIn(file1.id, file_ids)
        self.assertIn(file2.id, file_ids)
