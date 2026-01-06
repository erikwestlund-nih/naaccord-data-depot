"""
Precheck Validation Service

Performs progressive validation with database status tracking.
Provides detailed file diagnostics for problematic uploads.
"""

import logging
import hashlib
import io
import csv
import codecs
import traceback
from typing import Optional
from django.utils import timezone

# Try to import chardet, fall back to charset-normalizer if not available
try:
    import chardet
except ImportError:
    try:
        from charset_normalizer import from_bytes as chardet_detect
        # Create a chardet-compatible wrapper
        class ChardetWrapper:
            @staticmethod
            def detect(byte_str):
                results = chardet_detect(byte_str)
                if results and len(results) > 0:
                    result = results.best()
                    if result:
                        return {'encoding': result.encoding or 'utf-8', 'confidence': 0.9}
                return {'encoding': 'utf-8', 'confidence': 0.5}
        chardet = ChardetWrapper()
    except ImportError:
        # Final fallback - assume UTF-8
        class ChardetFallback:
            @staticmethod
            def detect(byte_str):
                return {'encoding': 'utf-8', 'confidence': 1.0}
        chardet = ChardetFallback()

from depot.models import PrecheckValidation
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class PrecheckValidationService:
    """
    Handles progressive validation with database status updates.

    This service performs validation in stages:
    1. Metadata analysis (size, encoding, BOM, hash)
    2. CSV integrity checking (row-by-row column counts)
    3. Full validation (against data definition)

    Progress is stored in the database and can be polled via API.
    """

    def __init__(self, validation_id):
        """
        Initialize service with validation ID.

        Args:
            validation_id: UUID of PrecheckValidation record
        """
        self.validation = PrecheckValidation.objects.get(id=validation_id)
        self.storage = StorageManager.get_scratch_storage()

    def run_complete_validation(self):
        """
        Run complete validation workflow.

        Executes all stages sequentially and handles errors.
        """
        try:
            # Stage 1: Metadata analysis
            self.analyze_metadata()

            # Stage 2: CSV integrity checking
            self.check_csv_integrity()

            # Reload validation to get updated malformed_rows
            self.validation.refresh_from_db()

            # Stage 3: Convert to DuckDB (skip if malformed rows detected)
            if self.validation.malformed_rows and len(self.validation.malformed_rows) > 0:
                logger.info(f'Skipping DuckDB conversion - {len(self.validation.malformed_rows)} malformed rows detected')
                self.validation.update_status('converting_duckdb', 'Skipped due to malformed rows', 70)
            else:
                self.convert_to_duckdb()

            # Stage 4: Patient ID validation (if submission selected)
            if self.validation.cohort_submission and self.validation.data_file_type.name != 'patient':
                self.validate_patient_ids()

            # Stage 5: Queue async validation run (if no integrity errors)
            if self.validation.malformed_rows and len(self.validation.malformed_rows) > 0:
                logger.info('Skipping validation - malformed rows detected')
                self.finalize()
            else:
                # File is valid, queue async validation run
                self.queue_validation_run()

        except Exception as e:
            logger.error(f'Precheck validation failed: {e}', exc_info=True)
            self._handle_error('complete_validation', e)

    def queue_validation_run(self):
        """Queue async validation run after precheck passes."""
        from depot.tasks.validation_orchestration import run_validation_for_precheck

        logger.info(f'Queuing async validation run for {self.validation.original_filename}')
        self.validation.update_status('validating', 'Queuing full validation...', 85)

        # Queue Celery task for async validation
        run_validation_for_precheck.delay(self.validation.id)

        logger.info(f'Validation task queued for precheck {self.validation.id}')

    def analyze_metadata(self):
        """
        Stage 1: Analyze file metadata (OPTIMIZED for large files).

        Extracts:
        - File size
        - SHA256 hash (streamed)
        - Encoding (using chardet on first 10KB)
        - BOM detection
        - Line count (efficient counting of newlines)
        - Column names (from first line only)

        OPTIMIZED: Streams file from disk instead of loading into memory.
        """
        self.validation.update_status('analyzing_metadata', 'Analyzing file metadata', 10)

        try:
            import os
            logger.info(f'Analyzing metadata for {self.validation.original_filename}')

            # OPTIMIZATION: Get absolute file path instead of loading content
            file_path = self.storage.get_absolute_path(self.validation.file_path)
            logger.info(f'Using file path directly: {file_path}')

            if not os.path.exists(file_path):
                raise FileNotFoundError(f'File not found: {file_path}')

            # Stream file for hash and line counting (memory-efficient)
            hasher = hashlib.sha256()
            file_size = 0
            line_count = 0
            first_10kb = b''
            first_line_bytes = b''
            found_first_line = False

            # Stream file in chunks from disk - never loads entire file
            CHUNK_SIZE = 65536  # 64KB chunks for better I/O performance

            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    hasher.update(chunk)
                    file_size += len(chunk)
                    line_count += chunk.count(b'\n')

                    # Collect first 10KB for encoding detection
                    if len(first_10kb) < 10000:
                        first_10kb += chunk[:10000 - len(first_10kb)]

                    # Extract first line for column names
                    if not found_first_line:
                        newline_pos = chunk.find(b'\n')
                        if newline_pos != -1:
                            first_line_bytes += chunk[:newline_pos]
                            found_first_line = True
                        else:
                            first_line_bytes += chunk

            file_hash = hasher.hexdigest()

            # Detect BOM
            has_bom = first_10kb.startswith(codecs.BOM_UTF8)

            # Detect encoding using chardet (only on first 10KB)
            encoding_result = chardet.detect(first_10kb)
            encoding = encoding_result['encoding'] or 'utf-8'

            # Detect line endings (CRLF vs LF)
            has_crlf = b'\r\n' in first_10kb

            # Extract column names from first line
            columns = []
            if first_line_bytes:
                try:
                    if has_bom:
                        header_text = first_line_bytes.decode('utf-8-sig')
                    else:
                        header_text = first_line_bytes.decode(encoding or 'utf-8', errors='replace')

                    # Simple CSV parsing for header
                    columns = [col.strip() for col in header_text.split(',')]
                except Exception as e:
                    logger.warning(f'Failed to decode header line: {e}')
                    columns = []

            # Save metadata to database
            self.validation.file_size = file_size
            self.validation.file_hash = file_hash
            self.validation.encoding = encoding
            self.validation.has_bom = has_bom
            self.validation.has_crlf = has_crlf
            self.validation.line_count = line_count
            self.validation.header_column_count = len(columns)
            self.validation.columns = columns
            self.validation.delimiter = ','  # CSV files use comma delimiter
            self.validation.save(update_fields=[
                'file_size', 'file_hash', 'encoding', 'has_bom', 'has_crlf',
                'line_count', 'header_column_count', 'columns', 'delimiter', 'updated_at'
            ])

            file_size_mb = file_size / (1024 * 1024)
            logger.info(
                f'Metadata analysis complete: size={file_size_mb:.1f}MB, '
                f'encoding={encoding}, has_bom={has_bom}, has_crlf={has_crlf}, '
                f'line_count={line_count:,}, columns={len(columns)}, delimiter=",", '
                f'hash={file_hash[:16]}...'
            )

            self.validation.update_status('analyzing_metadata', 'Metadata analysis complete', 20)

        except Exception as e:
            self._handle_error('analyze_metadata', e)
            raise

    def check_csv_integrity(self):
        """
        Stage 2: Check CSV file integrity.

        Validates:
        - CSV can be parsed
        - All rows have consistent column count
        - Records malformed rows

        This is the key diagnostic step for problematic files.

        OPTIMIZED: Reads file directly from disk instead of loading into memory.
        """
        self.validation.update_status('checking_integrity', 'Checking CSV integrity', 30)

        try:
            import os
            logger.info(f'Checking CSV integrity for {self.validation.original_filename}')

            # OPTIMIZATION: Get absolute file path instead of loading content
            file_path = self.storage.get_absolute_path(self.validation.file_path)
            logger.info(f'Using file path directly: {file_path}')

            if not os.path.exists(file_path):
                raise FileNotFoundError(f'File not found: {file_path}')

            # Determine encoding to use
            encoding = 'utf-8-sig' if self.validation.has_bom else (self.validation.encoding or 'utf-8')

            # Open file directly from disk - streams line by line
            with open(file_path, 'r', encoding=encoding, newline='') as f:
                csv_reader = csv.reader(f)

                # Read header to get expected column count
                try:
                    header = next(csv_reader)
                    expected_columns = len(header)
                    logger.info(f'CSV header has {expected_columns} columns')
                except StopIteration:
                    raise ValueError('File is empty or has no header row')

                malformed_rows = []
                total_rows = 1  # Header counts as row 1

                # Check each row for column count - streams from disk
                for row_num, row in enumerate(csv_reader, start=2):
                    total_rows = row_num

                    if len(row) != expected_columns:
                        malformed_rows.append({
                            'row': row_num,
                            'expected_columns': expected_columns,
                            'actual_columns': len(row),
                        })

                    # Update progress periodically (every 100000 rows for large files)
                    if row_num % 100000 == 0:
                        # Progress from 30% to 60% based on row count
                        progress = min(30 + int((row_num / 1000000) * 30), 60)
                        self.validation.update_status(
                            'checking_integrity',
                            f'Checked {row_num:,} rows',
                            progress
                        )

            # Save integrity results
            self.validation.total_rows = total_rows
            self.validation.malformed_rows = malformed_rows
            self.validation.save(update_fields=['total_rows', 'malformed_rows', 'updated_at'])

            if malformed_rows:
                logger.warning(
                    f'Found {len(malformed_rows)} malformed rows in '
                    f'{self.validation.original_filename}'
                )
            else:
                logger.info(
                    f'CSV integrity check passed: {total_rows:,} rows, '
                    f'{expected_columns} columns'
                )

            self.validation.update_status(
                'checking_integrity',
                f'Integrity check complete: {len(malformed_rows)} issues found',
                60
            )

        except Exception as e:
            self._handle_error('check_csv_integrity', e)
            raise

    def convert_to_duckdb(self):
        """
        Stage 3: Verify CSV can be loaded into DuckDB format.

        This is a non-blocking verification step. If it fails, we log a warning
        but continue with validation. The actual DuckDB conversion happens during
        the main upload process.

        OPTIMIZED: Uses file path directly instead of loading content into memory.
        """
        self.validation.update_status('converting_duckdb', 'Verifying data format compatibility', 60)

        try:
            import duckdb
            import os

            logger.info(f'Verifying DuckDB compatibility for {self.validation.original_filename}')
            logger.info(f'Storage file path: {self.validation.file_path}')

            # OPTIMIZATION: Get absolute file path instead of loading content
            file_path = self.storage.get_absolute_path(self.validation.file_path)
            logger.info(f'Using file path directly: {file_path} (no memory load)')

            # Verify file exists and get size
            if not os.path.exists(file_path):
                raise FileNotFoundError(f'File not found: {file_path}')

            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            logger.info(f'File size: {file_size_mb:.1f} MB')

            try:
                # OPTIMIZATION: Use file-based DuckDB with memory limits
                conn = duckdb.connect(':memory:')

                # Set memory limit for large files - DuckDB will spill to disk
                conn.execute("SET memory_limit='2GB'")
                conn.execute("SET temp_directory='/tmp/duckdb_temp'")
                os.makedirs('/tmp/duckdb_temp', exist_ok=True)

                logger.info('DuckDB configured with memory_limit=2GB')

                # Load CSV directly from file path (no Python memory involved)
                logger.info(f'Loading CSV from: {file_path}')
                conn.execute("""
                    CREATE TABLE data AS
                    SELECT * FROM read_csv_auto(?,
                        header=true,
                        ignore_errors=false
                    )
                """, [file_path])

                logger.info('Successfully created DuckDB table')

                # Get row count
                result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
                row_count = result[0] if result else 0

                # Close connection
                conn.close()

                logger.info(f'DuckDB verification successful: {row_count:,} rows')
                self.validation.update_status('converting_duckdb', 'Format verification complete', 70)

            except Exception as duckdb_error:
                logger.warning(f'DuckDB verification failed: {duckdb_error}')
                raise

        except Exception as e:
            # Log warning but don't fail validation
            logger.warning(f'DuckDB verification failed (non-blocking): {str(e)}', exc_info=True)
            self.validation.update_status('converting_duckdb', 'Format verification skipped', 70)

    def validate_patient_ids(self):
        """
        Stage 4: Validate patient IDs against submission's patient universe.

        For non-patient files, validates that all patient IDs exist in the
        submission's patient file. Stores results in patient_id_results field.

        NOTE: Skips validation if no submission is selected, as cohorts with
        patient ID mapping (like CNICS) need the mapping applied during upload.
        """
        self.validation.update_status('validating_patient_ids', 'Validating patient IDs', 75)

        try:
            logger.info(f'Validating patient IDs for {self.validation.original_filename}')

            # Skip validation if no submission selected
            if not self.validation.cohort_submission:
                logger.info('No submission selected - skipping patient ID validation')
                self.validation.patient_id_results = {
                    'skipped': True,
                    'reason': 'No submission selected for validation',
                    'note': 'Patient ID validation will occur during file upload if a submission is selected'
                }
                self.validation.save(update_fields=['patient_id_results', 'updated_at'])
                self.validation.update_status('validating_patient_ids', 'Patient ID validation skipped', 80)
                return

            # Get submission's patient ID universe
            from depot.models import SubmissionPatientIDs

            try:
                submission_patient_ids = SubmissionPatientIDs.objects.get(
                    submission=self.validation.cohort_submission
                )
                valid_patient_ids = set(submission_patient_ids.patient_ids)
                logger.info(f'Submission has {len(valid_patient_ids)} patient IDs')
            except SubmissionPatientIDs.DoesNotExist:
                # No patient IDs exist for this submission yet
                logger.warning(f'No patient IDs found for submission {self.validation.cohort_submission.id}')
                self.validation.patient_id_results = {
                    'error': 'No patient file uploaded for this submission yet',
                    'total': 0,
                    'valid': 0,
                    'invalid': 0,
                    'invalid_ids': []
                }
                self.validation.save(update_fields=['patient_id_results', 'updated_at'])
                self.validation.update_status('validating_patient_ids', 'Patient ID validation complete', 80)
                return

            # Extract patient IDs from uploaded file using DuckDB
            from depot.services.duckdb_utils import InMemoryDuckDBExtractor

            file_bytes = self.storage.get_file(self.validation.file_path)

            extractor = InMemoryDuckDBExtractor(
                io.BytesIO(file_bytes),
                encoding=self.validation.encoding or 'utf-8',
                has_bom=self.validation.has_bom or False
            )

            # Get list of possible patient ID column names to try
            # This handles both pre-mapped files (already have cohortPatientId) and
            # unmapped files (have cohort-specific column like sitePatientId)
            patient_id_columns = self._get_patient_id_column_names()
            logger.info(f'Will try patient ID columns in order: {", ".join(patient_id_columns)}')

            # Extract patient IDs using fast DuckDB extraction with flexible column matching
            extracted_patient_ids = extractor.extract_patient_ids_flexible(patient_id_columns)
            logger.info(f'Extracted {len(extracted_patient_ids)} patient IDs from file')

            # Compare against submission's patient IDs
            invalid_ids = sorted(extracted_patient_ids - valid_patient_ids)
            valid_count = len(extracted_patient_ids - set(invalid_ids))

            # Store results
            self.validation.patient_id_results = {
                'total': len(extracted_patient_ids),
                'valid': valid_count,
                'invalid': len(invalid_ids),
                'invalid_ids': invalid_ids  # Store ALL invalid IDs for complete reporting
            }
            self.validation.save(update_fields=['patient_id_results', 'updated_at'])

            if invalid_ids:
                logger.warning(
                    f'Found {len(invalid_ids)} invalid patient IDs not in submission universe'
                )
            else:
                logger.info('All patient IDs are valid')

            self.validation.update_status('validating_patient_ids', 'Patient ID validation complete', 80)

        except Exception as e:
            logger.error(f'Patient ID validation failed: {e}', exc_info=True)
            self.validation.patient_id_results = {
                'error': f'Validation failed: {str(e)}',
                'total': 0,
                'valid': 0,
                'invalid': 0,
                'invalid_ids': []
            }
            self.validation.save(update_fields=['patient_id_results', 'updated_at'])
            # Don't fail the whole validation - just log the error
            self.validation.update_status('validating_patient_ids', 'Patient ID validation error', 80)

    def run_validation(self):
        """
        Stage 5: Run full validation against data definition.

        Runs validation synchronously (no Celery workers needed) by calling
        validation tasks directly instead of queuing them.

        OPTIMIZED: Uses file paths instead of loading content into memory.
        For a 1.9GB file, this reduces peak memory from ~6GB to ~500MB.
        """
        logger.info(f"===== run_validation() called for {self.validation.original_filename} =====")

        # Skip validation if there are integrity errors
        if self.validation.malformed_rows and len(self.validation.malformed_rows) > 0:
            logger.info(f'Skipping validation - {len(self.validation.malformed_rows)} malformed rows detected')
            self.validation.update_status('validating', 'Skipped due to integrity errors', 95)
            return

        logger.info("Starting data definition validation")
        self.validation.update_status('validating', 'Running data definition validation', 90)

        import tempfile
        import duckdb
        import os

        # Track temp files for cleanup
        temp_files_to_cleanup = []
        processed_csv_path = None
        temp_db_path = None

        try:
            from depot.models import ValidationRun, ValidationVariable
            from django.contrib.contenttypes.models import ContentType
            from depot.tasks.validation_orchestration import execute_variable_validation
            from depot.data.definition_loader import get_definition_for_type

            logger.info(f'Starting validation for {self.validation.original_filename}')

            # Load data definition
            definition_obj = get_definition_for_type(self.validation.data_file_type.name)
            definition_list = definition_obj.get_definition()

            # Definition is a list of variable definitions
            if not isinstance(definition_list, list):
                raise ValueError(f'Expected definition to be a list, got {type(definition_list)}')

            logger.info(f'Loaded definition with {len(definition_list)} variables')

            # Create ValidationRun
            content_type = ContentType.objects.get_for_model(self.validation)

            validation_run = ValidationRun.objects.create(
                content_type=content_type,
                object_id=self.validation.id,
                data_file_type=self.validation.data_file_type,
                duckdb_path=None,  # We'll create temp DuckDB for validation
                raw_file_path=self.validation.file_path,
                status='pending'
            )

            logger.info(f'Created ValidationRun {validation_run.id} for PrecheckValidation {self.validation.id}')

            # OPTIMIZATION: Get absolute file path instead of loading content into memory
            # This avoids loading the entire file (e.g., 1.9GB) into Python memory
            input_csv_path = self.storage.get_absolute_path(self.validation.file_path)
            logger.info(f'Using file path directly: {input_csv_path} (no memory load)')

            # Verify the file exists
            if not os.path.exists(input_csv_path):
                raise FileNotFoundError(f'Input file not found: {input_csv_path}')

            file_size_mb = os.path.getsize(input_csv_path) / (1024 * 1024)
            logger.info(f'Input file size: {file_size_mb:.1f} MB')

            # Apply data processing (cohort-specific transformations: column renames, value remaps, etc.)
            from depot.services.data_mapping import DataMappingService

            cohort_name = self.validation.cohort.name if self.validation.cohort else 'Unknown'
            processing_service = DataMappingService(
                cohort_name=cohort_name,
                data_file_type=self.validation.data_file_type.name
            )

            # Create temporary processed CSV file
            processed_csv_fd, processed_csv_path = tempfile.mkstemp(suffix='.csv', prefix='processed_')
            os.close(processed_csv_fd)
            temp_files_to_cleanup.append(processed_csv_path)

            logger.info(f'Applying data processing for cohort: {cohort_name}')
            # OPTIMIZATION: process_file already streams row-by-row for transforms
            processing_results = processing_service.process_file(input_csv_path, processed_csv_path)

            if processing_results.get('errors'):
                error_msg = f"Data processing failed: {processing_results['errors']}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info(f'Data processing complete - {processing_results.get("summary", {})}')

            # Use processed CSV for DuckDB creation
            csv_for_duckdb = processed_csv_path

            # Create temporary DuckDB file
            temp_db_fd, temp_db_path = tempfile.mkstemp(suffix='.duckdb', prefix='validation_')
            os.close(temp_db_fd)
            temp_files_to_cleanup.append(temp_db_path)

            # Delete the empty file so DuckDB can create it fresh
            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)

            # OPTIMIZATION: Configure DuckDB with memory limits for large files
            conn = duckdb.connect(temp_db_path)
            try:
                # Set memory limit to prevent OOM - DuckDB will spill to disk
                conn.execute("SET memory_limit='2GB'")
                # Use temp directory for spilling large operations
                conn.execute("SET temp_directory='/tmp/duckdb_temp'")
                # Ensure temp directory exists
                os.makedirs('/tmp/duckdb_temp', exist_ok=True)

                logger.info('DuckDB configured with memory_limit=2GB, temp spill enabled')

                # Load CSV - DuckDB reads directly from file (no Python memory)
                conn.execute("""
                    CREATE TABLE data AS
                    SELECT * FROM read_csv_auto(?, header=true, ignore_errors=false)
                """, [csv_for_duckdb])

                row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
                logger.info(f'DuckDB loaded {row_count:,} rows from {csv_for_duckdb}')
            finally:
                conn.close()

            validation_run.duckdb_path = temp_db_path
            validation_run.status = 'running'
            validation_run.save()

            # Create ValidationVariable records
            variables = []
            for var_def in definition_list:
                variable = ValidationVariable.objects.create(
                    validation_run=validation_run,
                    column_name=var_def['name'],
                    column_type=var_def.get('type', 'string'),
                    display_name=var_def.get('label', var_def['name']),
                    status='pending'
                )
                variables.append(variable)

            logger.info(f'Created {len(variables)} validation variables')

            # Execute validation for each variable SYNCHRONOUSLY
            for variable in variables:
                try:
                    logger.info(f'Validating {variable.column_name}...')
                    # Call directly instead of .delay()
                    execute_variable_validation(variable.id, definition_list)
                except Exception as e:
                    logger.error(f'Failed to validate variable {variable.id}: {e}')

            # Mark validation run as completed
            validation_run.mark_completed()

            # Store reference to validation run
            self.validation.validation_run = validation_run
            self.validation.save(update_fields=['validation_run', 'updated_at'])

            logger.info(f'Validation complete for {self.validation.original_filename}')
            logger.info(f'ValidationRun {validation_run.id} saved to PrecheckValidation {self.validation.id}')
            self.validation.update_status('validating', 'Validation complete', 95)

        except Exception as e:
            logger.error(f'Validation failed: {e}', exc_info=True)
            # Store full error in error_message field, truncate for current_stage
            self.validation.error_message = str(e)
            error_summary = str(e)[:90] + '...' if len(str(e)) > 90 else str(e)
            self.validation.update_status('validating', f'Error: {error_summary}', 95)

        finally:
            # Clean up temp files
            for temp_file in temp_files_to_cleanup:
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.unlink(temp_file)
                        logger.info(f'Cleaned up temp file: {temp_file}')
                except Exception as cleanup_error:
                    logger.warning(f'Failed to cleanup {temp_file}: {cleanup_error}')

    def finalize(self):
        """Mark validation as complete and cleanup scratch files."""
        self.validation.mark_completed()
        self.validation.cleanup_scratch_file()
        logger.info(f'Precheck validation complete for {self.validation.original_filename}')

    def _get_patient_id_column_names(self):
        """
        Determine possible patient ID column names for this cohort.

        Returns a list of column names to try, in order of preference:
        1. Standard column name (cohortPatientId) - for pre-mapped files
        2. Source column name from mapping (e.g., sitePatientId) - for unmapped files

        This allows files to be uploaded either already in standard format
        or in cohort-specific format that will be mapped during processing.

        Returns:
            List of column names to try, e.g., ['cohortPatientId', 'sitePatientId']
        """
        # Always try standard column name first
        candidate_columns = ['cohortPatientId']

        try:
            from depot.services.data_mapping import DataMappingService

            # Check if cohort has a mapping for this file type
            mapping_service = DataMappingService(
                cohort_name=self.validation.cohort.name,
                data_file_type=self.validation.data_file_type.name
            )

            mapping_definition = mapping_service.mapping_definition

            if mapping_definition:
                # Look for a column mapping that targets cohortPatientId
                column_mappings = mapping_definition.get('column_mappings', [])
                for mapping in column_mappings:
                    if mapping.get('target_column') == 'cohortPatientId':
                        source_column = mapping.get('source_column')
                        # Add source column as second option (if different from standard)
                        if source_column and source_column.lower() != 'cohortpatientid':
                            candidate_columns.append(source_column)
                            logger.info(
                                f"Cohort {self.validation.cohort.name} has mapping: "
                                f"{source_column} → cohortPatientId. "
                                f"Will try both column names."
                            )
                        break
        except Exception as e:
            logger.warning(f'Could not load column mapping: {e}')

        return candidate_columns

    def _handle_error(self, stage: str, exception: Exception):
        """
        Handle errors during validation.

        Args:
            stage: Name of the stage where error occurred
            exception: The exception that was raised
        """
        error_message = f'Error in {stage}: {str(exception)}'
        error_traceback = traceback.format_exc()

        logger.error(error_message)
        logger.error(error_traceback)

        self.validation.mark_failed(error_message, error_traceback)
        self.validation.cleanup_scratch_file()
