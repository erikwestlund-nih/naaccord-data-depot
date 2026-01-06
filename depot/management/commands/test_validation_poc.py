"""
Test Validation POC Command

Quick end-to-end test of the new validation pipeline.

Creates a test CSV, processes it through:
1. Data mapping (if CNICS cohort)
2. DuckDB conversion
3. Statistics computation
4. Definition processing
5. Validator execution
6. Database record creation

Usage:
    python manage.py test_validation_poc
    python manage.py test_validation_poc --cohort UNC  # Test CNICS mapping
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import tempfile
from pathlib import Path
import csv

from depot.models import (
    ValidationRun,
    ValidationVariable,
    ValidationCheck,
    DataFileType,
    Cohort,
    DataProcessingLog
)
from depot.services import (
    DataMappingService,
    DuckDBConversionService,
    DataFileStatisticsService,
    DefinitionProcessingService
)
from depot.validators import get_validator


class Command(BaseCommand):
    help = 'Test end-to-end validation pipeline POC'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cohort',
            type=str,
            default='TestCohort',
            help='Cohort name to test (use UNC to test CNICS mapping)'
        )

    def handle(self, *args, **options):
        cohort_name = options['cohort']

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"Validation Pipeline POC Test - Cohort: {cohort_name}\n"
            f"{'='*60}\n"
        ))

        try:
            # Step 1: Create test CSV file
            self.stdout.write("\n1. Creating test CSV file...")
            csv_path = self._create_test_csv(cohort_name)
            self.stdout.write(self.style.SUCCESS(f"   ✓ Created: {csv_path}"))

            # Step 2: Test data mapping
            self.stdout.write("\n2. Testing data mapping service...")
            processed_path = self._test_data_mapping(cohort_name, csv_path)
            self.stdout.write(self.style.SUCCESS(f"   ✓ Processed: {processed_path}"))

            # Step 3: Convert to DuckDB
            self.stdout.write("\n3. Converting to DuckDB...")
            duckdb_service = self._test_duckdb_conversion(processed_path)
            self.stdout.write(self.style.SUCCESS(
                f"   ✓ Created DuckDB with {duckdb_service.get_row_count()} rows"
            ))

            # Step 4: Compute statistics
            self.stdout.write("\n4. Computing statistics...")
            stats = self._test_statistics(duckdb_service)
            self.stdout.write(self.style.SUCCESS(
                f"   ✓ Computed stats for {len(stats)} columns"
            ))

            # Step 5: Load definition
            self.stdout.write("\n5. Loading data definition...")
            definition_service = DefinitionProcessingService("patient")
            variables = definition_service.get_variables_for_validation()
            self.stdout.write(self.style.SUCCESS(
                f"   ✓ Loaded {len(variables)} variable definitions"
            ))

            # Step 6: Run validator
            self.stdout.write("\n6. Running no_duplicates validator...")
            validator_result = self._test_validator(duckdb_service)
            self.stdout.write(self.style.SUCCESS(
                f"   ✓ Validator result: {'PASS' if validator_result.passed else 'FAIL'}"
            ))

            # Step 7: Create database records
            self.stdout.write("\n7. Creating database records...")
            validation_run = self._create_database_records(
                cohort_name,
                csv_path,
                processed_path,
                duckdb_service,
                stats,
                validator_result
            )
            self.stdout.write(self.style.SUCCESS(
                f"   ✓ Created ValidationRun {validation_run.id}"
            ))

            # Cleanup
            duckdb_service.cleanup()

            # Summary
            self.stdout.write(self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"✓ POC Test Complete!\n"
                f"{'='*60}\n"
                f"ValidationRun ID: {validation_run.id}\n"
                f"Status: {validation_run.status}\n"
                f"Total Variables: {validation_run.total_variables}\n"
                f"Variables with Errors: {validation_run.variables_with_errors}\n"
                f"{'='*60}\n"
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n✗ Error: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())

    def _create_test_csv(self, cohort_name):
        """Create a test patient CSV file."""
        temp_dir = Path(tempfile.mkdtemp(prefix="validation_poc_"))
        csv_path = temp_dir / "patient.csv"

        # Use CNICS schema if UNC cohort
        if cohort_name == "UNC":
            headers = ["sitePatientId", "site", "birthSex", "birthDate"]
            rows = [
                ["PAT001", "UNC", "M", "1985-01-15"],
                ["PAT002", "UNC", "F", "1990-05-20"],
                ["PAT003", "UNC", "Male", "1978-11-30"],
                ["PAT001", "UNC", "M", "1985-01-15"],  # Duplicate!
            ]
        else:
            headers = ["cohortPatientId", "birthSex", "birthDate"]
            rows = [
                ["PAT001", "1", "1985-01-15"],
                ["PAT002", "2", "1990-05-20"],
                ["PAT003", "1", "1978-11-30"],
                ["PAT001", "1", "1985-01-15"],  # Duplicate!
            ]

        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return str(csv_path)

    def _test_data_mapping(self, cohort_name, csv_path):
        """Test data mapping service."""
        service = DataMappingService(cohort_name, "patient")

        temp_dir = Path(csv_path).parent
        processed_path = temp_dir / "patient_processed.csv"

        changes = service.process_file(str(csv_path), str(processed_path))

        if service.is_passthrough():
            self.stdout.write("   → Passthrough mode (no mapping)")
        else:
            self.stdout.write(f"   → Renamed columns: {len(changes['renamed_columns'])}")
            self.stdout.write(f"   → Value remaps: {len(changes['value_remaps'])}")

        return str(processed_path)

    def _test_duckdb_conversion(self, csv_path):
        """Test DuckDB conversion."""
        service = DuckDBConversionService(csv_path)
        service.create_database()
        return service

    def _test_statistics(self, duckdb_service):
        """Test statistics computation."""
        with duckdb_service.get_connection() as conn:
            stats_service = DataFileStatisticsService(conn)
            stats = stats_service.compute_all_columns_statistics()

            for col_name, col_stats in stats.items():
                self.stdout.write(
                    f"   → {col_name}: "
                    f"{col_stats['total_rows']} rows, "
                    f"{col_stats['null_count']} nulls"
                )

            return stats

    def _test_validator(self, duckdb_service):
        """Test no_duplicates validator."""
        validator = get_validator("no_duplicates")

        with duckdb_service.get_connection() as conn:
            result = validator.execute(conn, "data", "cohortPatientId", {})

            self.stdout.write(f"   → Passed: {result.passed}")
            self.stdout.write(f"   → Message: {result.message}")
            self.stdout.write(f"   → Affected rows: {result.affected_row_count}")

            return result

    def _create_database_records(
        self,
        cohort_name,
        raw_path,
        processed_path,
        duckdb_service,
        stats,
        validator_result
    ):
        """Create database records for validation run."""
        # Get or create data file type
        data_file_type, _ = DataFileType.objects.get_or_create(
            name="patient",
            defaults={'description': 'Patient demographics file'}
        )

        # Create ValidationRun (polymorphic - link to PrecheckValidationRun in real use)
        content_type = ContentType.objects.get_for_model(DataFileType)
        validation_run = ValidationRun.objects.create(
            content_type=content_type,
            object_id=data_file_type.id,
            data_file_type=data_file_type,
            raw_file_path=raw_path,
            processed_file_path=processed_path,
            duckdb_path=str(duckdb_service.db_path),
            status='running'
        )

        validation_run.mark_started()

        # Create ValidationVariable for cohortPatientId
        col_stats = stats.get('cohortPatientId', {})
        validation_var = ValidationVariable.objects.create(
            validation_run=validation_run,
            column_name='cohortPatientId',
            column_type='id',
            display_name='Cohort Patient ID',
            total_rows=col_stats.get('total_rows', 0),
            null_count=col_stats.get('null_count', 0),
            empty_count=col_stats.get('empty_count', 0),
            valid_count=col_stats.get('valid_count', 0),
            summary={'distinct_count': col_stats.get('distinct_count', 0)}
        )

        validation_var.mark_started()

        # Create ValidationCheck from validator result
        ValidationCheck.objects.create(
            validation_variable=validation_var,
            rule_key=validator_result.rule_key,
            rule_params=validator_result.rule_params,
            passed=validator_result.passed,
            severity=validator_result.severity,
            message=validator_result.message,
            affected_row_count=validator_result.affected_row_count,
            row_numbers=','.join(map(str, validator_result.row_numbers[:100])),
            meta=validator_result.meta
        )

        # Update counts
        validation_var.update_counts()
        validation_var.mark_completed()

        # Mark ValidationRun complete
        validation_run.update_summary()
        validation_run.mark_completed()

        return validation_run
