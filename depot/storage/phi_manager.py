import os
import shutil
import tempfile
import hashlib
import time
import csv
from pathlib import Path
from typing import Optional, Tuple
from django.conf import settings
from django.utils import timezone
import duckdb
import logging

from depot.models import PHIFileTracking
from depot.storage.manager import StorageManager
from depot.services.data_mapping import DataMappingService

logger = logging.getLogger(__name__)


class PHIStorageManager:
    """
    Handles all PHI file operations with complete tracking and cleanup.
    Ensures PHI data only exists on NAS except when actively being processed.
    """
    
    def __init__(self):
        # Use uploads storage for submission files
        self.storage = StorageManager.get_storage('uploads')
        
        # Check for NAS mount point for workspace
        nas_workspace = os.environ.get('NAS_WORKSPACE_PATH')
        
        if nas_workspace:
            # Production: Use NAS mount point for PHI workspace
            self.temp_workspace = Path(nas_workspace) / 'phi_workspace'
            logger.info(f"Using NAS PHI workspace at: {self.temp_workspace}")
        else:
            # Development: Use temp directory
            self.temp_workspace = Path(tempfile.gettempdir()) / 'naaccord_workspace'
            logger.info(f"Using local PHI workspace at: {self.temp_workspace}")

        self.temp_workspace.mkdir(parents=True, exist_ok=True)
    
    def store_raw_file(self, file_content, submission, file_type, filename, user) -> Tuple[str, str]:
        """
        Store raw CSV/TSV file on NAS with tracking.
        Returns: (nas_path, file_hash)
        """
        try:
            # Calculate file hash
            if hasattr(file_content, 'read'):
                file_content.seek(0)
                content = file_content.read()
                file_content.seek(0)
            else:
                content = file_content
            
            file_hash = hashlib.sha256(content if isinstance(content, bytes) else content.encode()).hexdigest()
            
            # Build NAS path
            cohort_name = submission.cohort.name.replace(' ', '_').replace('/', '-')
            nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{file_type}/raw/{filename}"
            
            # Store on NAS
            saved_path = self.storage.save(nas_path, file_content)

            # Get absolute path for PHI tracking
            absolute_path = self.storage.get_absolute_path(saved_path)

            # Get file size
            file_size = len(content) if isinstance(content, (str, bytes)) else file_content.size

            # Log the operation
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_raw_created',
                file_path=absolute_path,  # Use absolute path
                file_type='raw_csv' if filename.endswith('.csv') else 'raw_tsv',
                file_size=file_size,
                content_object=submission,
                metadata={'relative_path': saved_path}  # Keep relative for reference
            )
            
            logger.info(f"Stored raw file on NAS: {saved_path}")
            return saved_path, file_hash
            
        except Exception as e:
            logger.error(f"Failed to store raw file: {e}")
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_raw_created',
                file_path=nas_path,
                file_type='raw_csv',
                error_message=str(e),
                content_object=submission
            )
            raise

    def convert_multiple_files_to_duckdb(self, files_with_raw, submission, file_type, user) -> Optional[Tuple[str, str, dict]]:
        """
        Convert multiple raw CSV/TSV files to a single DuckDB format after applying cohort mapping.
        Used for multi-file tables (non-patient) where all files should be combined.

        Args:
            files_with_raw: List of (file_id, raw_nas_path) tuples
            submission: CohortSubmission instance
            file_type: Data file type name
            user: User performing the operation

        Returns:
            Tuple[str, str, dict]: (DuckDB NAS path, processed file NAS path, processing metadata) or None on failure.
        """
        workspace_raws = []
        workspace_db = None
        tracking_records = []

        processing_metadata = {
            'mapping': None,
            'summary': {},
            'row_count_in': 0,
            'row_count_out': None,
            'files_combined': len(files_with_raw)
        }

        try:
            # Copy all raw files from NAS to workspace and process each through mapping
            processed_files = []
            for idx, (upload_id, raw_nas_path) in enumerate(files_with_raw):
                logger.info(f"Processing file {idx + 1}/{len(files_with_raw)} (Upload ID {upload_id}): {raw_nas_path}")

                # Copy raw file to workspace
                workspace_raw = self.copy_to_workspace(raw_nas_path, submission.cohort, user)
                workspace_raws.append(workspace_raw)
                tracking_records.append(workspace_raw)

                # Apply cohort-specific mapping to this file
                temp_processed = self.temp_workspace / f"processed_{submission.id}_{file_type}_{idx}_{int(time.time() * 1000)}.csv"
                tracking_records.append(str(temp_processed))

                try:
                    mapping_service = DataMappingService(
                        cohort_name=submission.cohort.name,
                        data_file_type=file_type
                    )
                    if idx == 0:
                        processing_metadata['mapping'] = mapping_service.get_mapping_info()

                    changes_summary = mapping_service.process_file(workspace_raw, str(temp_processed))

                    rows_processed = changes_summary.get('summary', {}).get('rows_processed', 0)
                    processing_metadata['row_count_in'] += rows_processed
                    logger.info(f"File {idx + 1} processed: {rows_processed} rows")

                    # Store changes summary from first file, aggregate for subsequent files
                    if idx == 0:
                        # First file: store full changes summary
                        processing_metadata['summary'] = changes_summary
                    else:
                        # Subsequent files: aggregate renamed columns (avoid duplicates)
                        existing_renames = {(r['source'], r['target']) for r in processing_metadata['summary'].get('renamed_columns', [])}
                        for rename in changes_summary.get('renamed_columns', []):
                            rename_tuple = (rename['source'], rename['target'])
                            if rename_tuple not in existing_renames:
                                processing_metadata['summary']['renamed_columns'].append(rename)
                                existing_renames.add(rename_tuple)

                        # Update summary statistics
                        if 'summary' in changes_summary and 'summary' in processing_metadata['summary']:
                            # Aggregate columns_normalized count
                            processing_metadata['summary']['summary']['columns_normalized'] = \
                                processing_metadata['summary']['summary'].get('columns_normalized', 0) + \
                                changes_summary['summary'].get('columns_normalized', 0)

                    if changes_summary.get('errors'):
                        raise ValueError(
                            f"Data mapping failed for file {idx + 1}: {changes_summary['errors']}"
                        )

                    processed_files.append(temp_processed)
                    # Note: We no longer save individual processed files
                    # Only the combined processed file is saved

                except Exception as mapping_error:
                    logger.error(f"Data mapping failed for file {idx + 1}: {mapping_error}", exc_info=True)
                    # Cleanup any created files
                    for pf in processed_files:
                        if pf.exists():
                            pf.unlink(missing_ok=True)
                    raise

            # Combine all processed files into one CSV
            logger.info(f"Combining {len(processed_files)} processed files into one")
            combined_processed = self.temp_workspace / f"combined_processed_{submission.id}_{file_type}_{int(time.time() * 1000)}.csv"
            tracking_records.append(str(combined_processed))

            if len(processed_files) == 1:
                # Single file - just rename it (instant, no CSV parsing!)
                import shutil
                shutil.move(str(processed_files[0]), str(combined_processed))
                logger.info(f"Combined file created (single file rename): {combined_processed}")
            else:
                # Multiple files - need to actually combine them
                # Read header from first file and write to combined file
                with open(processed_files[0], 'r', newline='', encoding='utf-8') as first_file:
                    reader = csv.reader(first_file)
                    header = next(reader)

                    with open(combined_processed, 'w', newline='', encoding='utf-8') as combined:
                        writer = csv.writer(combined)
                        writer.writerow(header)

                        # Write data rows from first file
                        for row in reader:
                            writer.writerow(row)

                        # Append data rows from remaining files (skip headers)
                        for processed_file in processed_files[1:]:
                            with open(processed_file, 'r', newline='', encoding='utf-8') as pf:
                                pf_reader = csv.reader(pf)
                                next(pf_reader)  # Skip header
                                for row in pf_reader:
                                    writer.writerow(row)

                logger.info(f"Combined file created (merged {len(processed_files)} files): {combined_processed}")

            # Store processed file on NAS (simple naming - always overwrites)
            cohort_name = submission.cohort.name.replace(' ', '_').replace('/', '-')
            processed_nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{file_type}/processed/{file_type}_processed.csv"

            # Calculate file hash for integrity tracking
            import hashlib
            processed_hash = hashlib.sha256()
            with open(combined_processed, 'rb') as f:
                while chunk := f.read(65536):
                    processed_hash.update(chunk)
            processed_file_hash = processed_hash.hexdigest()
            logger.info(f"Calculated combined processed file hash: {processed_file_hash[:16]}...")

            # Prepare metadata with hash
            processed_metadata = {
                'relative_path': processed_nas_path,
                'file_hash': processed_file_hash,
                'cohort_id': submission.cohort.id,
                'user_id': user.id,
                'file_type': file_type,
                'files_combined': len(files_with_raw)
            }

            with open(combined_processed, 'rb') as f:
                processed_saved_path = self.storage.save(processed_nas_path, f, metadata=processed_metadata)

            # Get absolute path for PHI tracking
            processed_absolute_path = self.storage.get_absolute_path(processed_saved_path)

            # Log processed file storage with hash
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_processed_created',
                file_path=processed_absolute_path,
                file_type='processed_csv',
                file_size=combined_processed.stat().st_size,
                file_hash=processed_file_hash,
                content_object=submission,
                metadata={'relative_path': processed_saved_path, 'file_hash': processed_file_hash, 'files_combined': len(files_with_raw)}
            )

            logger.info(f"Stored combined processed file on NAS: {processed_saved_path}")

            # Create temporary DuckDB file
            workspace_db = self.temp_workspace / f"temp_{submission.id}_{file_type}_combined.duckdb"
            logger.info(f"Starting DuckDB creation: {workspace_db}")

            # Log DuckDB creation start
            logger.info(f"Logging DuckDB creation start to PHIFileTracking")
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_started',
                file_path=str(workspace_db),
                file_type='duckdb',
                content_object=submission
            )
            logger.info("PHIFileTracking log operation completed successfully")

            # Convert combined CSV to DuckDB
            # Delete existing DuckDB file AND WAL files if they exist to avoid locks
            logger.info(f"Checking for existing DuckDB file: {workspace_db}")
            if workspace_db.exists():
                workspace_db.unlink()
                logger.info(f"Deleted existing workspace DuckDB: {workspace_db}")

            # Also delete WAL files that can cause locks
            logger.info("Checking for WAL files")
            wal_file = Path(str(workspace_db) + '.wal')
            if wal_file.exists():
                wal_file.unlink()
                logger.info(f"Deleted WAL file: {wal_file}")

            wal_shm_file = Path(str(workspace_db) + '.wal-shm')
            if wal_shm_file.exists():
                wal_shm_file.unlink()
                logger.info(f"Deleted WAL-SHM file: {wal_shm_file}")

            logger.info(f"Opening DuckDB connection to {workspace_db}")
            conn = duckdb.connect(str(workspace_db))
            logger.info("DuckDB connection opened successfully")
            try:
                # Detect delimiter (use first raw file to determine)
                delimiter = '\t' if files_with_raw[0][1].endswith('.tsv') else ','

                # Create table from combined CSV - force all columns to be varchar to avoid type issues
                logger.info(f"Starting CREATE TABLE from {combined_processed} with delimiter '{delimiter}'")

                # Use environment-based parallel setting (Linux production: true, macOS dev: false)
                parallel_mode = "true" if settings.DUCKDB_PARALLEL_CSV else "false"
                logger.info(f"Using parallel={parallel_mode} for CSV reading")
                conn.execute(f"""
                    CREATE TABLE data AS
                    SELECT * FROM read_csv_auto(
                        '{combined_processed}',
                        delim='{delimiter}',
                        header=true,
                        all_varchar=true,
                        sample_size=100000,
                        parallel={parallel_mode},
                        ignore_errors=true
                    )
                """)
                logger.info("CREATE TABLE completed successfully")

                # Get row count for verification
                row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
                logger.info(f"Converted {row_count} rows to DuckDB from {len(files_with_raw)} combined files")
                processing_metadata['row_count_out'] = row_count

            finally:
                conn.close()

            # Store DuckDB on NAS (simple naming - always overwrites)
            duckdb_nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{file_type}/duckdb/{file_type}_combined.duckdb"

            # Calculate file hash for integrity tracking
            duckdb_hash = hashlib.sha256()
            with open(workspace_db, 'rb') as f:
                while chunk := f.read(65536):
                    duckdb_hash.update(chunk)
            duckdb_file_hash = duckdb_hash.hexdigest()
            logger.info(f"Calculated combined DuckDB file hash: {duckdb_file_hash[:16]}...")

            # Prepare metadata with hash
            duckdb_metadata = {
                'relative_path': duckdb_nas_path,
                'file_hash': duckdb_file_hash,
                'cohort_id': submission.cohort.id,
                'user_id': user.id,
                'file_type': file_type,
                'files_combined': len(files_with_raw)
            }

            with open(workspace_db, 'rb') as f:
                saved_path = self.storage.save(duckdb_nas_path, f, metadata=duckdb_metadata)

            # Get absolute path for PHI tracking
            absolute_path = self.storage.get_absolute_path(saved_path)

            # Log successful storage with hash
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_duckdb_created',
                file_path=absolute_path,
                file_type='duckdb',
                file_size=workspace_db.stat().st_size,
                file_hash=duckdb_file_hash,
                content_object=submission,
                metadata={'relative_path': saved_path, 'file_hash': duckdb_file_hash, 'files_combined': len(files_with_raw)}
            )

            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_completed',
                file_path=absolute_path,
                file_type='duckdb',
                content_object=submission,
                metadata={'relative_path': saved_path, 'files_combined': len(files_with_raw)}
            )

            logger.info(f"Stored combined DuckDB on NAS: {saved_path}")
            return saved_path, processed_saved_path, processing_metadata

        except Exception as e:
            logger.error(f"Failed to convert multiple files to DuckDB: {e}")
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_failed',
                file_path=str(workspace_db) if workspace_db else 'unknown',
                file_type='duckdb',
                error_message=str(e),
                content_object=submission
            )
            raise
        finally:
            # Cleanup workspace files
            for temp_file in tracking_records:
                if isinstance(temp_file, str):
                    temp_path = Path(temp_file)
                else:
                    temp_path = Path(temp_file)

                if temp_path.exists():
                    try:
                        temp_path.unlink()
                        logger.debug(f"Cleaned up workspace file: {temp_path}")

                        # Log cleanup
                        PHIFileTracking.log_operation(
                            cohort=submission.cohort,
                            user=user,
                            action='work_copy_deleted',
                            file_path=str(temp_path),
                            file_type='work_copy',
                            content_object=submission
                        )
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to cleanup workspace file {temp_path}: {cleanup_error}")

    def convert_to_duckdb(self, raw_nas_path, submission, file_type, user, upload_id=None) -> Optional[Tuple[str, str, dict]]:
        """
        Convert single raw CSV/TSV to DuckDB format after applying cohort mapping.
        For single-file tables (patient tables) or single file in multi-file tables.

        Args:
            upload_id: UploadedFile ID for naming (if None, uses submission.id for backwards compat)

        Returns:
            Tuple[str, str, dict]: (DuckDB NAS path, processed file NAS path, processing metadata) or None on failure.
        """
        workspace_raw = None
        workspace_db = None
        tracking_records = []
        
        processing_metadata = {
            'mapping': None,
            'summary': {},
            'row_count_in': None,
            'row_count_out': None,
        }

        try:
            # Copy raw file from NAS to workspace
            workspace_raw = self.copy_to_workspace(raw_nas_path, submission.cohort, user)
            tracking_records.append(workspace_raw)

            # Prepare processed workspace path
            processed_workspace = self.temp_workspace / f"processed_{submission.id}_{file_type}_{int(time.time() * 1000)}.csv"
            tracking_records.append(str(processed_workspace))

            # Apply cohort-specific mapping before DuckDB conversion
            try:
                mapping_service = DataMappingService(
                    cohort_name=submission.cohort.name,
                    data_file_type=file_type
                )
                processing_metadata['mapping'] = mapping_service.get_mapping_info()
                changes_summary = mapping_service.process_file(workspace_raw, str(processed_workspace))
                processing_metadata['summary'] = changes_summary
                rows_processed = changes_summary.get('summary', {}).get('rows_processed')
                if rows_processed is not None:
                    processing_metadata['row_count_in'] = rows_processed

                if changes_summary.get('errors'):
                    raise ValueError(
                        f"Data mapping failed for {submission.cohort.name} {file_type}: {changes_summary['errors']}"
                    )

                mapping_source_path = processed_workspace
            except Exception as mapping_error:
                logger.error("Data mapping failed for %s/%s: %s", submission.cohort.name, file_type, mapping_error, exc_info=True)
                # Cleanup processed temp file if it was created
                if processed_workspace.exists():
                    processed_workspace.unlink(missing_ok=True)
                raise

            # Store processed file on NAS for analyst use
            cohort_name = submission.cohort.name.replace(' ', '_').replace('/', '-')
            # Use upload_id prefix for chronological sorting (e.g., "2_diagnosis.csv")
            file_identifier = f"{upload_id}_{file_type}" if upload_id else f"{file_type}_{submission.id}"
            processed_nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{file_type}/processed/{file_identifier}.csv"

            # Calculate file hash for integrity tracking
            import hashlib
            processed_hash = hashlib.sha256()
            with open(processed_workspace, 'rb') as f:
                while chunk := f.read(65536):
                    processed_hash.update(chunk)
            processed_file_hash = processed_hash.hexdigest()
            logger.info(f"Calculated processed file hash: {processed_file_hash[:16]}...")

            # Prepare metadata with hash
            processed_metadata = {
                'relative_path': processed_nas_path,
                'file_hash': processed_file_hash,
                'cohort_id': submission.cohort.id,
                'user_id': user.id,
                'file_type': file_type
            }

            with open(processed_workspace, 'rb') as f:
                processed_saved_path = self.storage.save(processed_nas_path, f, metadata=processed_metadata)

            # Get absolute path for PHI tracking
            processed_absolute_path = self.storage.get_absolute_path(processed_saved_path)

            # Log processed file storage with hash
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_processed_created',
                file_path=processed_absolute_path,
                file_type='processed_csv' if processed_nas_path.endswith('.csv') else 'processed_tsv',
                file_size=processed_workspace.stat().st_size,
                file_hash=processed_file_hash,
                content_object=submission,
                metadata={'relative_path': processed_saved_path, 'file_hash': processed_file_hash}
            )

            logger.info(f"Stored processed file on NAS: {processed_saved_path}")

            # Create temporary DuckDB file
            workspace_db = self.temp_workspace / f"temp_{submission.id}_{file_type}.duckdb"
            logger.info(f"Starting DuckDB creation: {workspace_db}")

            # Log DuckDB creation start
            logger.info(f"Logging DuckDB creation start to PHIFileTracking")
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_started',
                file_path=str(workspace_db),
                file_type='duckdb',
                content_object=submission
            )
            logger.info("PHIFileTracking log operation completed successfully")

            # Delete existing DuckDB file AND WAL files if they exist to avoid locks
            logger.info(f"Checking for existing DuckDB file: {workspace_db}")
            if workspace_db.exists():
                workspace_db.unlink()
                logger.info(f"Deleted existing workspace DuckDB: {workspace_db}")

            # Also delete WAL files that can cause locks
            logger.info("Checking for WAL files")
            wal_file = Path(str(workspace_db) + '.wal')
            if wal_file.exists():
                wal_file.unlink()
                logger.info(f"Deleted WAL file: {wal_file}")

            wal_shm_file = Path(str(workspace_db) + '.wal-shm')
            if wal_shm_file.exists():
                wal_shm_file.unlink()
                logger.info(f"Deleted WAL-SHM file: {wal_shm_file}")

            # Convert to DuckDB
            logger.info(f"Opening DuckDB connection to {workspace_db}")
            conn = duckdb.connect(str(workspace_db))
            logger.info("DuckDB connection opened successfully")
            try:
                # Detect delimiter
                delimiter = '\t' if raw_nas_path.endswith('.tsv') else ','

                # Create table from CSV/TSV - force all columns to be varchar to avoid type issues
                logger.info(f"Starting CREATE TABLE from {mapping_source_path} with delimiter '{delimiter}'")

                # Use environment-based parallel setting (Linux production: true, macOS dev: false)
                parallel_mode = "true" if settings.DUCKDB_PARALLEL_CSV else "false"
                logger.info(f"Using parallel={parallel_mode} for CSV reading")
                conn.execute(f"""
                    CREATE TABLE data AS
                    SELECT * FROM read_csv_auto(
                        '{mapping_source_path}',
                        delim='{delimiter}',
                        header=true,
                        all_varchar=true,
                        sample_size=100000,
                        parallel={parallel_mode},
                        ignore_errors=true
                    )
                """)
                logger.info("CREATE TABLE completed successfully")

                # Get row count for verification
                row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
                logger.info(f"Converted {row_count} rows to DuckDB")
                processing_metadata['row_count_out'] = row_count

            finally:
                conn.close()

            # Now that DuckDB is created successfully, clean up the processed workspace file
            if processed_workspace.exists():
                try:
                    processed_workspace.unlink()
                    logger.info(f"Cleaned up processed workspace file after DuckDB creation: {processed_workspace}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup processed workspace file: {e}")

            # Store DuckDB on NAS
            cohort_name = submission.cohort.name.replace(' ', '_').replace('/', '-')
            # Use upload_id prefix for chronological sorting (e.g., "2_diagnosis.duckdb")
            file_identifier = f"{upload_id}_{file_type}" if upload_id else f"{file_type}_{submission.id}"
            duckdb_nas_path = f"{submission.cohort.id}_{cohort_name}/{submission.protocol_year.year}/{file_type}/duckdb/{file_identifier}.duckdb"

            # Calculate file hash for integrity tracking
            duckdb_hash = hashlib.sha256()
            with open(workspace_db, 'rb') as f:
                while chunk := f.read(65536):
                    duckdb_hash.update(chunk)
            duckdb_file_hash = duckdb_hash.hexdigest()
            logger.info(f"Calculated DuckDB file hash: {duckdb_file_hash[:16]}...")

            # Prepare metadata with hash
            duckdb_metadata = {
                'relative_path': duckdb_nas_path,
                'file_hash': duckdb_file_hash,
                'cohort_id': submission.cohort.id,
                'user_id': user.id,
                'file_type': file_type
            }

            with open(workspace_db, 'rb') as f:
                saved_path = self.storage.save(duckdb_nas_path, f, metadata=duckdb_metadata)

            # Get absolute path for PHI tracking
            absolute_path = self.storage.get_absolute_path(saved_path)

            # Log successful storage with hash
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='nas_duckdb_created',
                file_path=absolute_path,  # Use absolute path
                file_type='duckdb',
                file_size=workspace_db.stat().st_size,
                file_hash=duckdb_file_hash,
                content_object=submission,
                metadata={'relative_path': saved_path, 'file_hash': duckdb_file_hash}  # Include hash in metadata
            )

            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_completed',
                file_path=absolute_path,  # Use absolute path
                file_type='duckdb',
                content_object=submission,
                metadata={'relative_path': saved_path}  # Keep relative for reference
            )

            logger.info(f"Stored DuckDB on NAS: {saved_path}")
            if processing_metadata['row_count_in'] is None:
                processing_metadata['row_count_in'] = processing_metadata['row_count_out']
            return saved_path, processed_saved_path, processing_metadata
            
        except Exception as e:
            logger.error(f"Failed to convert to DuckDB: {e}")
            PHIFileTracking.log_operation(
                cohort=submission.cohort,
                user=user,
                action='conversion_failed',
                file_path=str(workspace_db) if workspace_db else 'unknown',
                file_type='duckdb',
                error_message=str(e),
                content_object=submission
            )
            return None
            
        finally:
            # Always cleanup workspace files
            if workspace_raw and Path(workspace_raw).exists():
                self.cleanup_workspace_file(workspace_raw, submission.cohort, user)
            # Processed workspace file is cleaned up after successful DuckDB creation (line 542-547)
            # Only clean it here if DuckDB conversion failed
            if 'processed_workspace' in locals() and processed_workspace.exists():
                # Check if we're in the error path (DuckDB not created)
                if not workspace_db or not workspace_db.exists():
                    try:
                        processed_workspace.unlink()
                        logger.info(f"Cleaned up processed workspace file after error: {processed_workspace}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup processed workspace file: {e}")
            if workspace_db and workspace_db.exists():
                self.cleanup_workspace_file(str(workspace_db), submission.cohort, user)
    
    def copy_to_workspace(self, nas_path, cohort, user, purpose='processing', retention_hours=1) -> str:
        """
        Copy file from NAS to temporary workspace for processing.
        Returns: workspace path
        """
        try:
            from datetime import timedelta
            
            # Create purpose-based subdirectory
            purpose_dir = self.temp_workspace / purpose
            purpose_dir.mkdir(exist_ok=True)
            
            # Generate unique workspace path
            filename = Path(nas_path).name
            workspace_path = purpose_dir / f"{timezone.now().timestamp()}_{filename}"
            
            # Get file from NAS
            file_content = self.storage.get_file(nas_path)
            
            # Check if content was retrieved
            if file_content is None:
                raise ValueError(f"Failed to retrieve file from NAS: {nas_path}")
            
            # Write to workspace
            if isinstance(file_content, bytes):
                with open(workspace_path, 'wb') as f:
                    f.write(file_content)
            else:
                # Ensure it's a string
                file_content_str = str(file_content) if file_content is not None else ""
                with open(workspace_path, 'w') as f:
                    f.write(file_content_str)
            
            # Calculate expected cleanup time
            expected_cleanup = timezone.now() + timedelta(hours=retention_hours)
            
            # Log the operation with enhanced tracking
            tracking = PHIFileTracking.objects.create(
                cohort=cohort,
                user=user,
                action='work_copy_created',
                file_path=str(workspace_path),
                file_type='temp_working',
                file_size=workspace_path.stat().st_size,
                purpose_subdirectory=purpose,
                expected_cleanup_by=expected_cleanup
            )
            
            logger.info(f"Copied to workspace: {workspace_path} (cleanup by {expected_cleanup})")
            return str(workspace_path)
            
        except Exception as e:
            logger.error(f"Failed to copy to workspace: {e}")
            raise
    
    def cleanup_workspace_file(self, workspace_path, cohort, user):
        """
        Delete file from workspace and log the cleanup.
        """
        try:
            path = Path(workspace_path)
            if path.exists():
                # Securely delete the file
                if path.is_file():
                    # Overwrite with random data before deletion (optional, for extra security)
                    # with open(path, 'ba+', buffering=0) as f:
                    #     length = f.tell()
                    #     f.seek(0)
                    #     f.write(os.urandom(length))
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path)
                
                # Log the cleanup
                PHIFileTracking.log_operation(
                    cohort=cohort,
                    user=user,
                    action='work_copy_deleted',
                    file_path=workspace_path,
                    file_type='temp_working'
                )
                
                # Mark the creation record as cleaned up
                creation_record = PHIFileTracking.objects.filter(
                    file_path=workspace_path,
                    action='work_copy_created'
                ).first()
                if creation_record:
                    creation_record.mark_cleaned_up(user)
                
                logger.info(f"Cleaned up workspace file: {workspace_path}")
            else:
                logger.warning(f"Workspace file not found for cleanup: {workspace_path}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup workspace file: {e}")
            # Still log the attempt
            PHIFileTracking.log_operation(
                cohort=cohort,
                user=user,
                action='work_copy_deleted',
                file_path=workspace_path,
                file_type='temp_working',
                error_message=str(e)
            )
    
    def delete_from_nas(self, nas_path, cohort, user, file_type='raw_csv'):
        """
        Delete file from NAS storage with logging.
        """
        try:
            # Delete from storage
            if self.storage.exists(nas_path):
                # Get absolute path for PHI tracking
                absolute_path = self.storage.get_absolute_path(nas_path)

                self.storage.delete(nas_path)

                # Log the deletion
                action = 'nas_raw_deleted' if 'raw' in nas_path else 'nas_duckdb_deleted'
                PHIFileTracking.log_operation(
                    cohort=cohort,
                    user=user,
                    action=action,
                    file_path=absolute_path,
                    file_type=file_type,
                    metadata={'relative_path': nas_path}
                )

                logger.info(f"Deleted from NAS: {nas_path}")
            else:
                logger.warning(f"File not found on NAS for deletion: {nas_path}")
                
        except Exception as e:
            logger.error(f"Failed to delete from NAS: {e}")
            raise
    
    def cleanup_all_workspace_files(self):
        """
        Clean up any orphaned workspace files.
        Called by management command.
        """
        cleaned = 0
        errors = 0
        
        # Get all uncleaned workspace files from tracking
        uncleaned = PHIFileTracking.get_uncleaned_workspace_files()
        
        for record in uncleaned:
            try:
                path = Path(record.file_path)
                if path.exists():
                    path.unlink()
                    record.mark_cleaned_up()
                    cleaned += 1
                else:
                    # File already gone, just mark as cleaned
                    record.mark_cleaned_up()
            except Exception as e:
                logger.error(f"Failed to cleanup {record.file_path}: {e}")
                errors += 1
        
        # Also check for any files in workspace not in tracking
        if self.temp_workspace.exists():
            for file_path in self.temp_workspace.iterdir():
                if file_path.is_file():
                    # Check if this file is tracked
                    if not PHIFileTracking.objects.filter(file_path=str(file_path)).exists():
                        logger.warning(f"Found untracked workspace file: {file_path}")
                        try:
                            file_path.unlink()
                            cleaned += 1
                        except Exception as e:
                            logger.error(f"Failed to cleanup untracked file {file_path}: {e}")
                            errors += 1
        
        return cleaned, errors
