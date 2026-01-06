# Validation Pipeline Implementation Guide

## Overview

This guide provides step-by-step implementation instructions for the validation pipeline, organized by phase with specific code locations, dependencies, and testing requirements.

## Phase 1: Foundation (Models + Services)

### 1.1 Create Database Models

**File**: `depot/models/validation.py` (new file)

```python
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


class ValidationRun(models.Model):
    """
    Top-level validation run for a single file.
    Can be linked to either PrecheckValidationRun or CohortSubmissionFile.
    """
    # Polymorphic relationship
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # File information
    data_file_type = models.ForeignKey('DataFileType', on_delete=models.CASCADE)
    duckdb_path = models.CharField(max_length=500, help_text="Temporary DuckDB file path")
    raw_file_path = models.CharField(max_length=500)
    processed_file_path = models.CharField(max_length=500, null=True, blank=True)

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Summary counts
    total_variables = models.IntegerField(default=0)
    completed_variables = models.IntegerField(default=0)
    variables_with_warnings = models.IntegerField(default=0)
    variables_with_errors = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'validation_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
            models.Index(fields=['data_file_type']),
        ]

    def __str__(self):
        return f"ValidationRun {self.id} - {self.data_file_type.name} ({self.status})"

    def mark_started(self):
        """Mark validation run as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def mark_completed(self):
        """Mark validation run as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message: str):
        """Mark validation run as failed."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])

    def update_summary(self):
        """Recalculate summary counts from variables."""
        variables = self.variables.all()
        self.total_variables = variables.count()
        self.completed_variables = variables.filter(status='completed').count()
        self.variables_with_warnings = variables.filter(warning_count__gt=0).count()
        self.variables_with_errors = variables.filter(error_count__gt=0).count()
        self.save(update_fields=[
            'total_variables', 'completed_variables',
            'variables_with_warnings', 'variables_with_errors', 'updated_at'
        ])

    def get_duration(self):
        """Get validation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class ValidationVariable(models.Model):
    """
    Per-column validation results.
    One record per variable in the data file.
    """
    validation_run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name='variables'
    )

    # Column information
    column_name = models.CharField(max_length=100, help_text="Column name from definition")
    column_type = models.CharField(max_length=50, help_text="Data type from definition")
    display_name = models.CharField(max_length=200, help_text="Human-readable name")

    # Status tracking
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    # Summary statistics
    total_rows = models.IntegerField(default=0)
    null_count = models.IntegerField(default=0)
    empty_count = models.IntegerField(default=0)
    valid_count = models.IntegerField(default=0)
    invalid_count = models.IntegerField(default=0)
    warning_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)

    # Variable-specific summary (flexible)
    summary = models.JSONField(
        default=dict,
        help_text="Variable-specific statistics (e.g., duplicate_count, out_of_range_count)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'validation_variables'
        ordering = ['validation_run', 'column_name']
        unique_together = [['validation_run', 'column_name']]
        indexes = [
            models.Index(fields=['validation_run', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.validation_run.data_file_type.name}.{self.column_name} ({self.status})"

    def mark_started(self):
        """Mark variable validation as started."""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at', 'updated_at'])

    def mark_completed(self):
        """Mark variable validation as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()

    def mark_failed(self, error_message: str):
        """Mark variable validation as failed."""
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()

    def update_counts(self):
        """Recalculate counts from checks."""
        checks = self.checks.all()
        self.warning_count = checks.filter(severity='warning', passed=False).count()
        self.error_count = checks.filter(severity='error', passed=False).count()
        self.save(update_fields=['warning_count', 'error_count', 'updated_at'])

        # Update parent ValidationRun summary
        self.validation_run.update_summary()

    def get_duration(self):
        """Get validation duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class ValidationCheck(models.Model):
    """
    Individual validation rule outcome.
    Multiple checks per variable (one per validation rule).
    """
    validation_variable = models.ForeignKey(
        ValidationVariable,
        on_delete=models.CASCADE,
        related_name='checks'
    )

    # Rule information
    rule_key = models.CharField(
        max_length=100,
        help_text="Validator identifier (e.g., 'type_is_boolean', 'range', 'no_duplicates')"
    )
    rule_params = models.JSONField(
        default=dict,
        help_text="Rule parameters (e.g., {'min': 1900, 'max': 2025})"
    )

    # Result
    passed = models.BooleanField(default=False, help_text="Whether validation passed")
    SEVERITY_CHOICES = [
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    message = models.TextField(help_text="Human-readable validation message")

    # Issue details (PHI-safe)
    affected_row_count = models.IntegerField(
        default=0,
        help_text="Number of rows affected by this issue"
    )
    row_numbers = models.TextField(
        null=True,
        blank=True,
        help_text="Comma-separated row numbers (never with patient IDs)"
    )
    invalid_value = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Example invalid value (only if not PHI-sensitive)"
    )

    # Additional metadata
    meta = models.JSONField(
        default=dict,
        help_text="Additional rule-specific information"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'validation_checks'
        ordering = ['validation_variable', 'rule_key']
        indexes = [
            models.Index(fields=['validation_variable', 'passed']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        status = "✓" if self.passed else "✗"
        return f"{status} {self.validation_variable.column_name}.{self.rule_key}"

    def get_row_numbers_list(self):
        """Parse row_numbers into list of integers."""
        if not self.row_numbers:
            return []
        try:
            return [int(x.strip()) for x in self.row_numbers.split(',')]
        except:
            return []
```

**Migration**:
```bash
# Create migration
python manage.py makemigrations depot --name create_validation_models

# Apply migration
python manage.py migrate
```

**Update `depot/models/__init__.py`**:
```python
from .validation import ValidationRun, ValidationVariable, ValidationCheck
```

### 1.2 Implement DuckDBConversionService

**File**: `depot/services/duckdb_conversion.py` (new file)

```python
import duckdb
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
from django.conf import settings
from depot.models import PHIFileTracking
from depot.storage.manager import StorageManager
import logging

logger = logging.getLogger(__name__)


class DuckDBConversionService:
    """
    Convert CSV/TSV/Parquet files to DuckDB with PHI tracking.
    """

    @staticmethod
    def convert(
        source_path: str,
        cohort=None,
        user=None,
        content_object=None
    ) -> Dict[str, Any]:
        """
        Convert source file to DuckDB with PHI tracking.

        Args:
            source_path: Path to raw or processed file
            cohort: Cohort for PHI tracking (optional)
            user: User for PHI tracking (optional)
            content_object: Related model instance for PHI tracking

        Returns:
            {
                'duckdb_path': str,
                'row_count': int,
                'column_count': int,
                'column_names': list,
                'file_size_bytes': int,
                'phi_tracking_id': int
            }
        """
        try:
            # Get scratch storage for DuckDB
            scratch_storage = StorageManager.get_scratch_storage()

            # Create temp directory for DuckDB file
            temp_dir = tempfile.mkdtemp(prefix='duckdb_')
            duckdb_filename = f"data_{os.getpid()}_{os.urandom(4).hex()}.duckdb"
            local_duckdb_path = Path(temp_dir) / duckdb_filename

            logger.info(f"Converting {source_path} to DuckDB at {local_duckdb_path}")

            # Connect to DuckDB
            conn = duckdb.connect(str(local_duckdb_path))

            # Detect file type and load
            source_storage = StorageManager.get_storage('uploads')
            file_content = source_storage.get_file(source_path)

            if isinstance(file_content, bytes):
                file_content = file_content.decode('utf-8')

            # Write to temp file for DuckDB to read
            temp_csv = Path(temp_dir) / "temp_data.csv"
            with open(temp_csv, 'w') as f:
                f.write(file_content)

            # Load into DuckDB with row_no column
            conn.execute("""
                CREATE TABLE data AS
                SELECT
                    ROW_NUMBER() OVER () as row_no,
                    *
                FROM read_csv_auto(?, header=true, ignore_errors=true)
            """, [str(temp_csv)])

            # Get statistics
            row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
            columns = conn.execute("PRAGMA table_info('data')").fetchall()
            column_names = [col[1] for col in columns if col[1] != 'row_no']
            column_count = len(column_names)

            # Close connection before moving file
            conn.close()

            # Get file size
            file_size = local_duckdb_path.stat().st_size

            # Move DuckDB to scratch storage
            with open(local_duckdb_path, 'rb') as f:
                duckdb_storage_path = scratch_storage.save(
                    f"duckdb/{duckdb_filename}",
                    f.read()
                )

            logger.info(f"DuckDB saved to scratch storage: {duckdb_storage_path}")

            # Track PHI
            phi_tracking = None
            if cohort and user:
                phi_tracking = PHIFileTracking.objects.create(
                    cohort=cohort,
                    user=user,
                    action='duckdb_created',
                    file_path=duckdb_storage_path,
                    file_type='duckdb',
                    file_size=file_size,
                    cleanup_required=True,
                    server_role=os.environ.get('SERVER_ROLE', 'services'),
                    content_object=content_object,
                    metadata={
                        'source_path': source_path,
                        'row_count': row_count,
                        'column_count': column_count,
                        'column_names': column_names
                    }
                )
                logger.info(f"PHI tracking created: {phi_tracking.id}")

            # Cleanup temp files
            temp_csv.unlink()
            local_duckdb_path.unlink()
            os.rmdir(temp_dir)

            return {
                'duckdb_path': duckdb_storage_path,
                'row_count': row_count,
                'column_count': column_count,
                'column_names': column_names,
                'file_size_bytes': file_size,
                'phi_tracking_id': phi_tracking.id if phi_tracking else None
            }

        except Exception as e:
            logger.error(f"Error converting to DuckDB: {e}", exc_info=True)
            raise

    @staticmethod
    def cleanup_duckdb(duckdb_path: str, cohort=None, user=None):
        """
        Delete DuckDB file and update PHI tracking.

        Args:
            duckdb_path: Path to DuckDB file
            cohort: Cohort for PHI tracking
            user: User for PHI tracking
        """
        try:
            scratch_storage = StorageManager.get_scratch_storage()

            # Delete file
            if scratch_storage.delete(duckdb_path):
                logger.info(f"Deleted DuckDB file: {duckdb_path}")

                # Update PHI tracking
                if cohort and user:
                    # Find and mark as cleaned up
                    tracking = PHIFileTracking.objects.filter(
                        file_path=duckdb_path,
                        action='duckdb_created',
                        cleanup_required=True,
                        cleaned_up=False
                    ).first()

                    if tracking:
                        tracking.mark_cleaned_up(user)
                        logger.info(f"Marked PHI tracking as cleaned up: {tracking.id}")

                    # Create deletion tracking
                    PHIFileTracking.objects.create(
                        cohort=cohort,
                        user=user,
                        action='duckdb_deleted',
                        file_path=duckdb_path,
                        file_type='duckdb',
                        server_role=os.environ.get('SERVER_ROLE', 'services')
                    )
            else:
                logger.warning(f"Failed to delete DuckDB file: {duckdb_path}")

        except Exception as e:
            logger.error(f"Error cleaning up DuckDB: {e}", exc_info=True)
```

### 1.3 Implement DataFileStatisticsService

**File**: `depot/services/data_statistics.py` (new file)

```python
import duckdb
from typing import Dict, Any
from depot.storage.manager import StorageManager
import logging

logger = logging.getLogger(__name__)


class DataFileStatisticsService:
    """
    Generate summary statistics from DuckDB files.
    """

    @staticmethod
    def generate_statistics(duckdb_path: str) -> Dict[str, Any]:
        """
        Generate summary statistics from DuckDB file.

        Args:
            duckdb_path: Path to DuckDB file in storage

        Returns:
            {
                'row_count': int,
                'unique_rows': int,
                'null_count': int,
                'column_stats': {
                    'column_name': {
                        'null_count': int,
                        'empty_count': int,
                        'distinct_count': int,
                        'most_common_value': str,
                        'most_common_count': int
                    }
                }
            }
        """
        try:
            # Get DuckDB file from storage
            scratch_storage = StorageManager.get_scratch_storage()

            # For local storage, get direct path
            # For remote storage, download to temp location
            if hasattr(scratch_storage, 'get_absolute_path'):
                local_path = scratch_storage.get_absolute_path(duckdb_path)
            else:
                # Download to temp location
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.duckdb')
                content = scratch_storage.get_file(duckdb_path)
                temp_file.write(content)
                temp_file.close()
                local_path = temp_file.name

            # Connect to DuckDB
            conn = duckdb.connect(local_path, read_only=True)

            # Get row count
            row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]

            # Get unique row count (excluding row_no)
            columns = conn.execute("PRAGMA table_info('data')").fetchall()
            data_columns = [col[1] for col in columns if col[1] != 'row_no']

            if data_columns:
                col_list = ', '.join(data_columns)
                unique_rows = conn.execute(f"SELECT COUNT(DISTINCT ({col_list})) FROM data").fetchone()[0]
            else:
                unique_rows = row_count

            # Get total null count across all columns
            null_count = 0
            for col in data_columns:
                col_nulls = conn.execute(f"SELECT COUNT(*) FROM data WHERE {col} IS NULL").fetchone()[0]
                null_count += col_nulls

            # Get per-column statistics
            column_stats = {}
            for col in data_columns:
                # Null count
                col_null_count = conn.execute(
                    f"SELECT COUNT(*) FROM data WHERE {col} IS NULL"
                ).fetchone()[0]

                # Empty string count
                col_empty_count = conn.execute(
                    f"SELECT COUNT(*) FROM data WHERE CAST({col} AS VARCHAR) = ''"
                ).fetchone()[0]

                # Distinct count
                col_distinct_count = conn.execute(
                    f"SELECT COUNT(DISTINCT {col}) FROM data WHERE {col} IS NOT NULL"
                ).fetchone()[0]

                # Most common value (non-PHI columns only - skip 'id' type columns)
                most_common_value = None
                most_common_count = 0

                # Skip for potential PHI columns
                if not any(sensitive in col.lower() for sensitive in ['id', 'patient', 'subject']):
                    try:
                        result = conn.execute(f"""
                            SELECT CAST({col} AS VARCHAR) as value, COUNT(*) as cnt
                            FROM data
                            WHERE {col} IS NOT NULL AND CAST({col} AS VARCHAR) != ''
                            GROUP BY {col}
                            ORDER BY cnt DESC
                            LIMIT 1
                        """).fetchone()

                        if result:
                            most_common_value = result[0]
                            most_common_count = result[1]
                    except:
                        pass  # Skip if error (e.g., incompatible type)

                column_stats[col] = {
                    'null_count': col_null_count,
                    'empty_count': col_empty_count,
                    'distinct_count': col_distinct_count,
                    'most_common_value': most_common_value,
                    'most_common_count': most_common_count
                }

            conn.close()

            # Cleanup temp file if we created one
            if not hasattr(scratch_storage, 'get_absolute_path'):
                import os
                os.unlink(local_path)

            return {
                'row_count': row_count,
                'unique_rows': unique_rows,
                'null_count': null_count,
                'column_stats': column_stats
            }

        except Exception as e:
            logger.error(f"Error generating statistics: {e}", exc_info=True)
            raise
```

### 1.4 Implement DefinitionProcessingService

**File**: `depot/services/definition_processing.py` (new file)

```python
from typing import Dict, List, Any
from depot.data.definition_loader import get_definition_for_type
import logging

logger = logging.getLogger(__name__)


class DefinitionProcessingService:
    """
    Parse JSON definitions and create structured validation execution plans.
    """

    @staticmethod
    def parse_definition(data_file_type) -> Dict[str, Any]:
        """
        Read JSON definition and create structured execution plan.

        Args:
            data_file_type: DataFileType instance

        Returns:
            {
                'variables': [
                    {
                        'name': 'cohortPatientId',
                        'type': 'id',
                        'description': 'De-identified patient identification code',
                        'phi_sensitive': True,
                        'validators': [
                            {'rule': 'type_is_id', 'params': {}},
                            {'rule': 'no_duplicates', 'params': {}}
                        ]
                    },
                    ...
                ]
            }
        """
        try:
            # Load definition
            definition_obj = get_definition_for_type(data_file_type.name)
            definition = definition_obj.definition

            variables = []

            for field in definition:
                variable = {
                    'name': field['name'],
                    'type': field['type'],
                    'description': field.get('description', ''),
                    'phi_sensitive': field.get('phi_sensitive', False),
                    'validators': []
                }

                # Add type-based validator
                type_validator = DefinitionProcessingService._get_type_validator(field)
                if type_validator:
                    variable['validators'].append(type_validator)

                # Add explicit validators from definition
                if 'validators' in field:
                    for validator in field['validators']:
                        if isinstance(validator, str):
                            # Simple string validator (e.g., "no_duplicates")
                            variable['validators'].append({
                                'rule': validator,
                                'params': {}
                            })
                        elif isinstance(validator, dict):
                            # Dictionary with name and params
                            variable['validators'].append({
                                'rule': validator['name'],
                                'params': validator.get('params', {})
                            })

                variables.append(variable)

            return {'variables': variables}

        except Exception as e:
            logger.error(f"Error parsing definition: {e}", exc_info=True)
            raise

    @staticmethod
    def _get_type_validator(field: Dict) -> Dict[str, Any]:
        """
        Get type-based validator for a field.

        Args:
            field: Field definition from JSON

        Returns:
            Validator dict or None
        """
        field_type = field['type']

        # Map types to validators
        type_validators = {
            'id': 'type_is_id',
            'string': 'type_is_string',
            'enum': 'type_is_enum',
            'boolean': 'type_is_boolean',
            'date': 'type_is_date',
            'year': 'type_is_year',
            'int': 'type_is_integer',
            'float': 'type_is_numeric'
        }

        validator_name = type_validators.get(field_type)
        if not validator_name:
            return None

        # Build params based on type
        params = {}

        if field_type == 'enum':
            params['allowed_values'] = field.get('allowed_values', [])
        elif field_type == 'boolean':
            params['allowed_values'] = field.get('allowed_values', {})
        elif field_type == 'date':
            params['date_format'] = field.get('date_format', 'YYYY-MM-DD')

        return {
            'rule': validator_name,
            'params': params
        }
```

## Continue to Next Phase

This completes Phase 1. Would you like me to continue with:
- Phase 2: Validator Library implementation?
- Review and adjust Phase 1 before proceeding?
- Start with a specific validator as a proof of concept?
