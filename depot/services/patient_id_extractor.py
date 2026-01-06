import csv
import logging
import duckdb
from pathlib import Path
from typing import List, Tuple, Optional
from django.utils import timezone

from depot.models import SubmissionPatientIDs, PHIFileTracking, DataTableFile
from depot.storage.phi_manager import PHIStorageManager
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class PatientIDExtractor:
    """
    Service to extract patient IDs from patient files.
    Handles both CSV/TSV raw files and DuckDB files.
    """
    
    PATIENT_ID_COLUMN = 'cohortPatientId'
    
    def __init__(self):
        self.phi_manager = PHIStorageManager()

    def extract_ids_from_data_file(self, data_file: DataTableFile) -> List[str]:
        """
        Extract patient IDs from any data file (patient or non-patient).
        Returns a list of patient IDs found in the file.
        """
        try:
            # Use DuckDB if available, otherwise use raw file
            if data_file.duckdb_file_path:
                patient_ids, _ = self._extract_from_duckdb(
                    data_file.duckdb_file_path,
                    data_file.data_table.submission.cohort,
                    None  # No user needed for simple extraction
                )
            elif data_file.raw_file_path:
                patient_ids, _ = self._extract_from_raw(
                    data_file.raw_file_path,
                    data_file.data_table.submission.cohort,
                    None  # No user needed for simple extraction
                )
            else:
                logger.warning(f"No file path available for DataTableFile {data_file.id}")
                return []

            return patient_ids

        except Exception as e:
            logger.error(f"Failed to extract patient IDs from file {data_file.id}: {e}")
            return []

    def extract_from_data_table_file(self, data_file: DataTableFile, user) -> Optional[SubmissionPatientIDs]:
        """
        Extract patient IDs from a DataTableFile record.
        Uses DuckDB file if available, otherwise falls back to raw file.
        """
        submission = data_file.data_table.submission

        try:
            # Get storage instance and convert relative path to absolute
            storage = StorageManager.get_storage('uploads')
            relative_path = data_file.duckdb_file_path or data_file.raw_file_path
            absolute_path = storage.get_absolute_path(relative_path)

            # Log extraction start
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='patient_id_extraction_started',
                file_path=absolute_path,
                file_type='duckdb' if data_file.duckdb_file_path else 'raw_csv',
                content_object=data_file,
                metadata={'relative_path': relative_path}
            )
            
            # Extract IDs based on available file type
            if data_file.duckdb_file_path:
                patient_ids, warnings = self._extract_from_duckdb(
                    data_file.duckdb_file_path, 
                    submission.cohort, 
                    user
                )
            elif data_file.raw_file_path:
                patient_ids, warnings = self._extract_from_raw(
                    data_file.raw_file_path,
                    submission.cohort,
                    user
                )
            else:
                raise ValueError("No file path available for extraction")
            
            # Create or update the patient IDs record
            record = SubmissionPatientIDs.create_or_update_for_submission(
                submission=submission,
                patient_ids=patient_ids,
                user=user,
                source_file=data_file
            )
            
            # Store any warnings
            if warnings:
                record.extraction_error = '\n'.join(warnings)
                record.save()
            
            # Log successful extraction
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='patient_id_extraction_completed',
                file_path=absolute_path,
                file_type='duckdb' if data_file.duckdb_file_path else 'raw_csv',
                content_object=record,
                metadata={'relative_path': relative_path}
            )
            
            logger.info(f"Extracted {record.patient_count} patient IDs for submission {submission.id}")
            return record
            
        except Exception as e:
            logger.error(f"Failed to extract patient IDs: {e}")

            # Log the failure (reuse absolute_path from try block if available)
            try:
                # Try to use the absolute_path from the try block
                file_path = absolute_path
            except NameError:
                # If absolute_path wasn't set (early exception), compute it here
                storage = StorageManager.get_storage('uploads')
                relative_path = data_file.duckdb_file_path or data_file.raw_file_path
                file_path = storage.get_absolute_path(relative_path)

            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='patient_id_extraction_failed',
                file_path=file_path,
                file_type='duckdb' if data_file.duckdb_file_path else 'raw_csv',
                error_message=str(e),
                content_object=data_file,
                metadata={'relative_path': data_file.duckdb_file_path or data_file.raw_file_path}
            )
            
            # Create a failed record
            record = SubmissionPatientIDs.create_or_update_for_submission(
                submission=submission,
                patient_ids=[],
                user=user,
                source_file=data_file
            )
            record.extraction_error = f"Extraction failed: {str(e)}"
            record.save()
            
            return record
    
    def _extract_from_duckdb(self, nas_path: str, cohort, user) -> Tuple[List[str], List[str]]:
        """
        Extract patient IDs from a DuckDB file.
        Returns: (patient_ids, warnings)
        """
        workspace_path = None
        warnings = []
        
        try:
            # Copy DuckDB to workspace
            workspace_path = self.phi_manager.copy_to_workspace(nas_path, cohort, user)
            logger.info(f"Successfully copied DuckDB to workspace: {workspace_path}")

            # Connect to DuckDB
            conn = duckdb.connect(workspace_path, read_only=True)
            logger.info(f"Successfully connected to DuckDB at: {workspace_path}")
            
            try:
                # Check if column exists
                columns = conn.execute("PRAGMA table_info('data')").fetchall()
                column_names = [col[1] for col in columns]
                
                # Try case-insensitive match
                patient_id_col = None
                for col in column_names:
                    if col.lower() == self.PATIENT_ID_COLUMN.lower():
                        patient_id_col = col
                        break
                
                if not patient_id_col:
                    raise ValueError(f"Column '{self.PATIENT_ID_COLUMN}' not found. Available columns: {column_names}")
                
                # Extract unique patient IDs - simpler query without type comparisons
                result = conn.execute(f"""
                    SELECT DISTINCT "{patient_id_col}"
                    FROM data
                    WHERE "{patient_id_col}" IS NOT NULL
                """).fetchall()
                
                # Filter out None and empty strings in Python to avoid SQL type issues
                patient_ids = [str(row[0]).strip() for row in result 
                             if row[0] is not None and str(row[0]).strip() != '']
                
                # Get total non-null count for duplicate checking
                # We filtered empty strings in Python, so need to count properly
                all_non_null = conn.execute(f"""
                    SELECT "{patient_id_col}"
                    FROM data
                    WHERE "{patient_id_col}" IS NOT NULL
                """).fetchall()
                
                # Count non-empty values for accurate duplicate count
                non_empty_values = [str(row[0]).strip() for row in all_non_null 
                                  if row[0] is not None and str(row[0]).strip() != '']
                
                if len(non_empty_values) > len(patient_ids):
                    duplicate_count = len(non_empty_values) - len(patient_ids)
                    warnings.append(f"Found {duplicate_count} duplicate patient IDs that were removed")
                
                # Check for nulls or empty values
                null_count = conn.execute(f"""
                    SELECT COUNT(*)
                    FROM data
                    WHERE "{patient_id_col}" IS NULL
                """).fetchone()[0]
                
                # Count empty strings separately (in total rows minus non-empty)
                total_rows = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
                empty_count = total_rows - len(non_empty_values) - null_count
                
                if null_count > 0 or empty_count > 0:
                    missing_total = null_count + empty_count
                    warnings.append(f"Found {missing_total} rows with missing or empty patient IDs")
                
            finally:
                conn.close()

            # Ensure Django connection is fresh after DuckDB operations
            from django.db import connection as django_connection
            if django_connection.connection is not None and not django_connection.is_usable():
                django_connection.close()

            logger.info(f"Successfully extracted {len(patient_ids)} patient IDs from DuckDB")
            return patient_ids, warnings

        except Exception as e:
            logger.error(f"Exception during DuckDB extraction: {e}")
            raise
        finally:
            # Always cleanup workspace
            if workspace_path:
                logger.info(f"Cleaning up DuckDB workspace file: {workspace_path}")
                self.phi_manager.cleanup_workspace_file(workspace_path, cohort, user)
    
    def _extract_from_raw(self, nas_path: str, cohort, user) -> Tuple[List[str], List[str]]:
        """
        Extract patient IDs from a raw CSV/TSV file.
        Returns: (patient_ids, warnings)
        """
        workspace_path = None
        warnings = []
        
        try:
            # Copy raw file to workspace
            workspace_path = self.phi_manager.copy_to_workspace(nas_path, cohort, user)
            
            # Detect delimiter
            delimiter = '\t' if nas_path.endswith('.tsv') else ','
            
            # Read the file
            patient_ids_raw = []
            header_index = None
            
            with open(workspace_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f, delimiter=delimiter)
                
                # Find the patient ID column
                header = next(reader)
                for i, col in enumerate(header):
                    if col.strip().lower() == self.PATIENT_ID_COLUMN.lower():
                        header_index = i
                        break
                
                if header_index is None:
                    # Try case-insensitive match
                    for i, col in enumerate(header):
                        if self.PATIENT_ID_COLUMN.lower() in col.strip().lower():
                            header_index = i
                            warnings.append(f"Using fuzzy match for column: {col}")
                            break
                
                if header_index is None:
                    raise ValueError(f"Column '{self.PATIENT_ID_COLUMN}' not found. Available columns: {header}")
                
                # Extract patient IDs
                for row in reader:
                    if len(row) > header_index:
                        patient_id = row[header_index]
                        if patient_id is not None:
                            patient_id = str(patient_id).strip()
                            if patient_id:
                                patient_ids_raw.append(patient_id)
            
            # Get unique IDs
            patient_ids = list(set(patient_ids_raw))
            
            # Check for duplicates
            if len(patient_ids_raw) > len(patient_ids):
                duplicate_count = len(patient_ids_raw) - len(patient_ids)
                warnings.append(f"Found {duplicate_count} duplicate patient IDs that were removed")
            
            # Sort for consistency
            patient_ids.sort()

            # Ensure Django connection is fresh after file operations
            from django.db import connection as django_connection
            if django_connection.connection is not None and not django_connection.is_usable():
                django_connection.close()

            return patient_ids, warnings
            
        finally:
            # Always cleanup workspace
            if workspace_path:
                self.phi_manager.cleanup_workspace_file(workspace_path, cohort, user)
    
    def validate_patient_ids(self, submission, ids_to_check: List[str]) -> Tuple[List[str], List[str]]:
        """
        Validate a list of patient IDs against the submission's valid IDs.
        Returns: (valid_ids, invalid_ids)
        """
        try:
            # Get the patient IDs record
            patient_record = SubmissionPatientIDs.objects.filter(submission=submission).first()
            
            if not patient_record:
                # No patient file uploaded yet
                logger.warning(f"No patient IDs found for submission {submission.id}")
                return [], ids_to_check
            
            valid_ids = []
            invalid_ids = []
            
            valid_set = patient_record.get_patient_ids_set()
            
            for patient_id in ids_to_check:
                if patient_id in valid_set:
                    valid_ids.append(patient_id)
                else:
                    invalid_ids.append(patient_id)
            
            return valid_ids, invalid_ids
            
        except Exception as e:
            logger.error(f"Failed to validate patient IDs: {e}")
            return [], ids_to_check