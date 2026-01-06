import duckdb
import tempfile
import os
import subprocess
import shutil
from pathlib import Path
from depot.data.definition_loader import get_definition_for_type
from depot.storage.temp_files import TemporaryStorage
from depot.storage.phi_manager import PHIStorageManager
from django.conf import settings
import time
from django.utils import timezone
from depot.models import Notebook, PrecheckRun, DataTableFile, PHIFileTracking
from celery import shared_task
from depot.services.notebook import NotebookService
from depot.data.notebook_templates import notebook_templates
import logging

logger = logging.getLogger(__name__)

class Auditor:
    """
    Auditor for processing upload prechecks.

    OPTIMIZED: Supports file_path parameter to avoid loading large files into memory.
    For backward compatibility, still accepts data_content parameter.
    """

    # DuckDB memory limits for large file processing
    DUCKDB_MEMORY_LIMIT = '2GB'
    DUCKDB_TEMP_DIR = '/tmp/duckdb_temp'

    def __init__(self, data_file_type, precheck_run, data_content=None, file_path=None):
        """
        Initialize Auditor.

        Args:
            data_file_type: DataFileType instance
            precheck_run: PrecheckRun instance
            data_content: File content as string (legacy - loads into memory)
            file_path: Absolute file path (preferred - streams from disk)

        Note: Either data_content or file_path must be provided.
        file_path is preferred for large files as it avoids memory overhead.
        """
        if not precheck_run:
            raise ValueError("Upload precheck record is required")

        if data_content is None and file_path is None:
            raise ValueError("Either data_content or file_path must be provided")

        self.data_file_type = data_file_type
        self.data_content = data_content
        self.file_path = file_path  # NEW: Support direct file path
        self.precheck_run = precheck_run
        self.conn = None
        self.db_path = None
        self.column_mapping = {}
        self.submitted_columns = []
        self.temp_file_path = None
        # Load the JSON definition directly
        definition_obj = get_definition_for_type(data_file_type.name)
        self.definition = definition_obj.definition
        self.definition_file_path = definition_obj.definition_path
        self.temp_dir = None
        self.notebook_path = None
        self.notebook = None

    def _configure_duckdb_connection(self, conn):
        """Configure DuckDB connection with memory limits for large files."""
        os.makedirs(self.DUCKDB_TEMP_DIR, exist_ok=True)
        conn.execute(f"SET memory_limit='{self.DUCKDB_MEMORY_LIMIT}'")
        conn.execute(f"SET temp_directory='{self.DUCKDB_TEMP_DIR}'")
        logger.info(f'DuckDB configured: memory_limit={self.DUCKDB_MEMORY_LIMIT}')

    def process(self):
        """Process the complete audit, including notebook creation and compilation"""
        try:
            # Step 1: Load data into DuckDB
            self.precheck_run.mark_processing_duckdb(None)
            self.load_duckdb()
            
            # Step 2: Get statistics
            stats = self.get_statistics()
            
            # Step 3: Set initial audit result with DuckDB path
            initial_result = self._create_initial_result(stats)
            self.precheck_run.result = initial_result
            self.precheck_run.save()
            
            # Step 4: Create and compile notebook
            self.precheck_run.mark_processing_notebook()
            try:
                notebook = self._create_notebook()
                notebook_info = self._compile_notebook(notebook)
            except Exception as e:
                logger.error(f"Error creating/compiling notebook: {e}", exc_info=True)
                self.precheck_run.mark_failed(str(e))
                return {"status": "failed", "error": str(e), "result": None}
            
            # Step 5: Format and return final response
            response = self._format_response(stats, notebook_info)
            self.precheck_run.mark_completed(response)
            return response

        except Exception as e:
            logger.error(f"Error in audit process: {e}", exc_info=True)
            self.precheck_run.mark_failed(str(e))
            return {"status": "failed", "error": str(e), "result": None}
        finally:
            self.cleanup()

    def process_with_existing_duckdb(self):
        """
        Process audit using an already-created DuckDB file.
        This method is used in Celery workflows where DuckDB is created separately.
        """
        try:
            # Connect to existing DuckDB file
            import duckdb
            from pathlib import Path

            if not self.db_path:
                raise ValueError("No DuckDB path provided for existing DuckDB processing")

            self.conn = duckdb.connect(str(self.db_path))

            # Get column information from existing DuckDB
            columns = self.conn.execute("PRAGMA table_info('data')").fetchall()
            column_names = [col[1] for col in columns]
            self.submitted_columns = [col for col in column_names if col != 'row_no']

            # Build column mapping for case normalization
            self.column_mapping = {}
            definition_names = [col["name"] for col in self.definition]
            for def_col in definition_names:
                for sub_col in self.submitted_columns:
                    if def_col.lower() == sub_col.lower() and def_col != sub_col:
                        self.column_mapping[sub_col] = def_col

            # Step 1: Get statistics from existing DuckDB
            stats = self.get_statistics()

            # Step 2: Set initial audit result
            initial_result = self._create_initial_result(stats)
            self.precheck_run.result = initial_result
            self.precheck_run.save()

            # Step 3: Create and compile notebook
            self.precheck_run.mark_processing_notebook()
            try:
                notebook = self._create_notebook()
                notebook_info = self._compile_notebook(notebook)
            except Exception as e:
                logger.error(f"Error creating/compiling notebook: {e}", exc_info=True)
                self.precheck_run.mark_failed(str(e))
                return {"status": "failed", "error": str(e), "result": None}

            # Step 4: Format and return final response
            response = self._format_response(stats, notebook_info)
            self.precheck_run.mark_completed(response)
            return response

        except Exception as e:
            logger.error(f"Error in audit process with existing DuckDB: {e}", exc_info=True)
            self.precheck_run.mark_failed(str(e))
            return {"status": "failed", "error": str(e), "result": None}

    def _create_initial_result(self, stats):
        """Create the initial audit result with DuckDB path and statistics."""
        return {
            "status": "processing",
            "error": None,
            "result": {
                "temp_file": str(self.db_path),
                "message": "Processing audit...",
                "data_file_type": self.data_file_type.name,
                "data_file_type_label": self.data_file_type.label,
                "file_size": stats["file_size"],
                "stats": {
                    "row_count": stats["row_count"],
                    "unique_rows": stats["unique_rows"],
                    "null_count": stats["null_count"],
                    "column_stats": stats["column_stats"],
                    "columns": stats["columns"],
                }
            }
        }

    def _create_notebook(self):
        """Create a new notebook record for the audit."""
        template_name = notebook_templates.get_template(self.precheck_run.data_file_type.name)
        notebook = Notebook.objects.create(
            name=f"Audit Report - {self.precheck_run.data_file_type.name}",
            template_path=f"audit/{template_name}",
            data_file_type=self.precheck_run.data_file_type,
            content_object=self.precheck_run,
            created_by=self.precheck_run.created_by,
            cohort=self.precheck_run.cohort
        )
        logger.info(f"Created notebook {notebook.id}")
        return notebook

    def _compile_notebook(self, notebook):
        """Compile the notebook and update the audit record."""
        # Close DuckDB connection before compilation
        if self.conn:
            self.conn.close()
            self.conn = None
            
        # Compile notebook
        service = NotebookService(notebook)
        if not service.compile():
            raise Exception(f"Failed to compile notebook: {notebook.error}")
        
        # Update audit with notebook reference
        self.precheck_run.notebook = notebook
        self.precheck_run.save()
        
        return {
            "id": notebook.id,
            "status": notebook.status,
            "error": notebook.error,
            "compiled_at": notebook.compiled_at.isoformat() if notebook.compiled_at else None,
        }

    def _format_response(self, stats, notebook_info):
        """Format the audit response"""
        return {
            "status": "completed",
            "error": None,
            "result": {
                "temp_file": str(self.db_path),
                "message": "Audit completed successfully.",
                "data_file_type": self.data_file_type.name,
                "data_file_type_label": self.data_file_type.label,
                "file_size": stats["file_size"],
                "stats": {
                    "row_count": stats["row_count"],
                    "unique_rows": stats["unique_rows"],
                    "null_count": stats["null_count"],
                    "column_stats": stats["column_stats"],
                    "columns": stats["columns"],
                },
                "notebook": notebook_info
            }
        }

    def _get_input_csv_path(self):
        """
        Get CSV file path for processing.

        OPTIMIZED: Uses file_path directly if available, avoiding memory load.
        Falls back to creating temp file from data_content for backward compatibility.

        Returns:
            Tuple of (csv_path, is_temp_file)
        """
        if self.file_path:
            # OPTIMIZATION: Use file path directly - no memory load
            logger.info(f'Using file path directly: {self.file_path} (no memory load)')
            return self.file_path, False
        elif self.data_content:
            # Legacy path: write content to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False
            ) as temp_csv:
                temp_csv.write(self.data_content)
                self.temp_file_path = temp_csv.name
            logger.info(f'Created temp CSV from data_content: {self.temp_file_path}')
            return self.temp_file_path, True
        else:
            raise ValueError("No file path or data content available")

    def load_duckdb(self):
        """
        Load data into DuckDB for analysis using PHI management.

        OPTIMIZED: Uses file paths directly when possible to avoid memory overhead.
        Configures DuckDB with memory limits to prevent OOM on large files.
        """
        # Initialize PHI storage manager
        phi_manager = PHIStorageManager()

        # Check if this audit is associated with a DataTableFile
        data_table_file = None
        submission = None

        # Try to find the associated DataTableFile through the audit
        try:
            data_table_file = DataTableFile.objects.filter(precheck_run=self.precheck_run).first()
            if data_table_file:
                # Refresh from DB to ensure we have the latest data (including comments)
                data_table_file.refresh_from_db()
                submission = data_table_file.data_table.submission

                # Check if we already have a DuckDB file on NAS
                if data_table_file.duckdb_file_path:
                    # OPTIMIZATION: Get absolute path instead of loading content
                    from depot.storage.scratch_manager import ScratchManager
                    scratch = ScratchManager()
                    work_dir_prefix = scratch.get_precheck_run_dir(self.precheck_run.id)
                    self.temp_dir = work_dir_prefix  # Store for cleanup

                    # Get absolute path to DuckDB file on NAS
                    duckdb_absolute_path = phi_manager.storage.get_absolute_path(data_table_file.duckdb_file_path)

                    if os.path.exists(duckdb_absolute_path):
                        # Copy file using streaming (not loading into memory)
                        fd, local_db_path = tempfile.mkstemp(suffix='.duckdb')
                        os.close(fd)
                        os.remove(local_db_path)

                        from depot.services.large_file_utils import copy_file_streaming
                        copy_file_streaming(duckdb_absolute_path, local_db_path)
                        logger.info(f'Copied DuckDB file via streaming: {duckdb_absolute_path} -> {local_db_path}')

                        self.db_path = Path(local_db_path)
                        self.conn = duckdb.connect(str(self.db_path))
                        self._configure_duckdb_connection(self.conn)
                    else:
                        # Fallback: load via storage API
                        file_content = phi_manager.storage.get_file(data_table_file.duckdb_file_path)
                        if file_content is None:
                            raise ValueError(f"Failed to retrieve DuckDB file from NAS: {data_table_file.duckdb_file_path}")

                        fd, local_db_path = tempfile.mkstemp(suffix='.duckdb')
                        os.close(fd)
                        os.remove(local_db_path)

                        with open(local_db_path, 'wb') as f:
                            f.write(file_content)

                        self.db_path = Path(local_db_path)
                        self.conn = duckdb.connect(str(self.db_path))
                        self._configure_duckdb_connection(self.conn)

                    # Check if row_no column exists, add it if not
                    columns = self.conn.execute("PRAGMA table_info('data')").fetchall()
                    column_names = [col[1] for col in columns]

                    if 'row_no' not in column_names:
                        try:
                            self.conn.execute("ALTER TABLE data ADD COLUMN row_no INTEGER")
                            self.conn.execute("UPDATE data SET row_no = CAST(rowid AS INTEGER)")
                        except Exception as e:
                            logger.warning(f"Could not add row_no column: {e}")

                    self.submitted_columns = [col for col in column_names if col != 'row_no']

                    # Build column mapping for case normalization
                    self.column_mapping = {}
                    definition_names = [col["name"] for col in self.definition]
                    for def_col in definition_names:
                        for sub_col in self.submitted_columns:
                            if def_col.lower() == sub_col.lower() and def_col != sub_col:
                                self.column_mapping[sub_col] = def_col

                    return self.db_path
        except Exception as e:
            logger.warning(f"Could not check for existing DuckDB: {e}")

        # No existing DuckDB, create a new one
        # OPTIMIZATION: Get CSV path (uses file_path if available)
        csv_path, is_temp_csv = self._get_input_csv_path()
        
        # If we have a submission, convert to DuckDB and store on NAS
        if submission and data_table_file:
            try:
                # Store the raw file on NAS if not already stored
                if not data_table_file.raw_file_path:
                    # OPTIMIZATION: Read from file path if available, avoid memory
                    if self.file_path:
                        with open(self.file_path, 'rb') as f:
                            file_content_bytes = f.read()
                        raw_nas_path, file_hash = phi_manager.store_raw_file(
                            file_content=file_content_bytes.decode('utf-8'),
                            submission=submission,
                            file_type=self.data_file_type.name,
                            filename=f"audit_{self.precheck_run.id}.csv",
                            user=self.precheck_run.uploaded_by or self.precheck_run.created_by
                        )
                    else:
                        raw_nas_path, file_hash = phi_manager.store_raw_file(
                            file_content=self.data_content,
                            submission=submission,
                            file_type=self.data_file_type.name,
                            filename=f"audit_{self.precheck_run.id}.csv",
                            user=self.precheck_run.uploaded_by or self.precheck_run.created_by
                        )
                    data_table_file.raw_file_path = raw_nas_path
                    data_table_file.save(update_fields=['raw_file_path'])
                else:
                    raw_nas_path = data_table_file.raw_file_path

                # For upload prechecks, create temporary DuckDB directly (no permanent storage)
                from depot.storage.scratch_manager import ScratchManager
                scratch = ScratchManager()
                work_dir_prefix = scratch.get_precheck_run_dir(self.precheck_run.id)
                self.temp_dir = work_dir_prefix  # Store for cleanup

                # Create temporary DuckDB file directly
                fd, local_db_path = tempfile.mkstemp(suffix='.duckdb')
                os.close(fd)
                os.remove(local_db_path)  # Remove empty file so DuckDB can create it fresh

                self.db_path = Path(local_db_path)
                self.conn = duckdb.connect(str(self.db_path))
                self._configure_duckdb_connection(self.conn)

                # OPTIMIZATION: Get absolute path to raw file instead of loading content
                raw_file_absolute_path = phi_manager.storage.get_absolute_path(raw_nas_path)

                if os.path.exists(raw_file_absolute_path):
                    # Use file path directly - DuckDB reads from disk
                    csv_for_duckdb = raw_file_absolute_path
                    logger.info(f'Loading CSV directly from NAS path: {csv_for_duckdb}')
                else:
                    # Fallback: load via storage API and write to temp file
                    raw_file_content = phi_manager.storage.get_file(raw_nas_path)
                    if not raw_file_content:
                        raise ValueError(f"Failed to retrieve raw file from NAS: {raw_nas_path}")

                    if isinstance(raw_file_content, bytes):
                        raw_file_content = raw_file_content.decode('utf-8')

                    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
                        temp_csv.write(raw_file_content)
                        csv_for_duckdb = temp_csv.name

                try:
                    # Load CSV into DuckDB - reads directly from file, no Python memory
                    self.conn.execute("""
                        CREATE TABLE data AS
                        SELECT *, row_number() OVER () as row_no
                        FROM read_csv_auto(?, header=true)
                    """, [csv_for_duckdb])

                    # Get column names (row_no already added in CREATE TABLE)
                    columns = self.conn.execute("PRAGMA table_info('data')").fetchall()
                    column_names = [col[1] for col in columns]

                    # Get column names from the DuckDB (excluding row_no)
                    self.submitted_columns = [col for col in column_names if col != 'row_no']

                    # Build column mapping for case normalization
                    self.column_mapping = {}
                    definition_names = [col["name"] for col in self.definition]
                    for def_col in definition_names:
                        for sub_col in self.submitted_columns:
                            if def_col.lower() == sub_col.lower() and def_col != sub_col:
                                self.column_mapping[sub_col] = def_col

                    return self.db_path

                finally:
                    # Clean up temporary CSV only if we created one
                    if csv_for_duckdb != raw_file_absolute_path and os.path.exists(csv_for_duckdb):
                        os.unlink(csv_for_duckdb)
            except Exception as e:
                logger.error(f"Failed to use PHI storage for DuckDB: {e}")
                # Fall back to temporary storage

        # Fallback: Create DuckDB in controlled workspace (for audits without submissions)
        from depot.storage.scratch_manager import ScratchManager
        from depot.storage.temp_file_manager import TempFileManager

        scratch = ScratchManager()
        work_dir_prefix = scratch.get_precheck_run_dir(self.precheck_run.id)
        self.temp_dir = work_dir_prefix  # Store for cleanup

        # OPTIMIZATION: Use file path directly if available, avoid memory copies
        if self.file_path:
            # Copy file to scratch using streaming
            csv_key = f"{work_dir_prefix}input.csv"
            from depot.services.large_file_utils import copy_file_streaming
            scratch_absolute_path = scratch.storage.get_absolute_path(csv_key)
            os.makedirs(os.path.dirname(scratch_absolute_path), exist_ok=True)
            copy_file_streaming(self.file_path, scratch_absolute_path)
            self.temp_file_path = self.file_path  # Original file path
            logger.info(f'Copied CSV to scratch via streaming: {self.file_path} -> {scratch_absolute_path}')
        else:
            # Legacy path: save content to scratch
            csv_key = f"{work_dir_prefix}input.csv"
            scratch.storage.save(csv_key, self.data_content.encode('utf-8'), 'text/csv')
            # Also create a temporary file for DuckDB processing
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
                temp_csv.write(self.data_content)
                self.temp_file_path = temp_csv.name

        # Track the CSV file for cleanup (use absolute path)
        csv_absolute_path = scratch.storage.get_absolute_path(csv_key)
        logger.critical(f"DEBUG PHI TRACKING CSV: csv_key={csv_key}, absolute={csv_absolute_path}")
        PHIFileTracking.objects.create(
            cohort=self.precheck_run.cohort,
            user=self.precheck_run.uploaded_by or self.precheck_run.created_by,
            action='work_copy_created',
            file_path=csv_absolute_path,
            file_type='raw_csv',
            cleanup_required=True,
            content_object=self.precheck_run,
            metadata={'relative_path': csv_key}
        )
        logger.critical(f"DEBUG PHI TRACKING CSV CREATED: file_path should be absolute")

        # For DuckDB, we need a local file path, so create a temporary filename
        fd, self.db_path = tempfile.mkstemp(suffix='.duckdb')
        os.close(fd)  # Close the file descriptor but keep the path
        os.remove(self.db_path)  # Remove the empty file so DuckDB can create it fresh
        self.conn = duckdb.connect(str(self.db_path))
        self._configure_duckdb_connection(self.conn)  # OPTIMIZATION: Add memory limits

        # Track the scratch directory for cleanup (remove trailing slash for directory tracking)
        directory_path = work_dir_prefix.rstrip('/')
        directory_absolute_path = scratch.storage.get_absolute_path(directory_path)
        PHIFileTracking.objects.create(
            cohort=self.precheck_run.cohort,
            user=self.precheck_run.uploaded_by or self.precheck_run.created_by,
            action='work_copy_created',
            file_path=directory_absolute_path,
            file_type='scratch_directory',
            cleanup_required=True,
            content_object=self.precheck_run,
            metadata={'relative_path': directory_path}
        )

        # CRITICAL: Track the DuckDB file specifically for PHI cleanup
        # Use a logical path in the scratch directory for consistency
        logical_duckdb_path = f"{directory_path}/audit_{self.precheck_run.id}.duckdb"
        duckdb_absolute_path = scratch.storage.get_absolute_path(logical_duckdb_path)
        PHIFileTracking.objects.create(
            cohort=self.precheck_run.cohort,
            user=self.precheck_run.uploaded_by or self.precheck_run.created_by,
            action='work_copy_created',
            file_path=duckdb_absolute_path,
            file_type='duckdb',
            cleanup_required=True,
            content_object=self.precheck_run,
            metadata={'relative_path': logical_duckdb_path}
        )
        
        # Read and normalize column names
        self._normalize_columns()
        
        # Create the table with normalized columns
        self._create_table()
        
        return self.db_path

    def get_statistics(self):
        """Get statistics about the data"""
        # Get row count
        row_count = self.conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]

        # Get unique rows count - using COLUMNS(*) instead of *
        unique_rows = self.conn.execute(
            "SELECT COUNT(DISTINCT COLUMNS(*)) FROM data"
        ).fetchone()[0]

        # Get null count - check for required columns based on file type
        null_count_sql = "SELECT SUM(CASE WHEN row_no IS NULL THEN 1 ELSE 0 END"
        
        # Only check cohortPatientId for patient files
        if self.data_file_type.name == 'patient' and 'cohortPatientId' in self.submitted_columns:
            null_count_sql += " + CASE WHEN cohortPatientId IS NULL THEN 1 ELSE 0 END"
        
        null_count_sql += ") FROM data"
        
        null_count = (
            self.conn.execute(null_count_sql).fetchone()[0] or 0
        )

        # Get column statistics
        column_stats = {}
        for col in self.submitted_columns:
            stats = self.conn.execute(
                f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT {col}) as unique_values,
                    SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) as nulls
                FROM data
            """
            ).fetchone()
            column_stats[col] = {
                "nulls": stats[2] or 0,
                "unique_values": stats[1] or 0,
            }

        # Get file size
        file_size = 0
        if self.temp_file_path and os.path.exists(self.temp_file_path):
            file_size = os.path.getsize(self.temp_file_path)
        elif self.db_path and os.path.exists(self.db_path):
            file_size = os.path.getsize(self.db_path)

        return {
            "row_count": row_count,
            "unique_rows": unique_rows,
            "null_count": null_count,
            "column_stats": column_stats,
            "columns": [
                {"name": col, "type": "string"}
                for col in self.submitted_columns
            ],
            "file_size": file_size,
        }

    def get_notebook_info(self):
        """Get notebook creation information"""
        if not self.precheck_run:
            return None
            
        template_name = notebook_templates.get_template(self.precheck_run.data_file_type.name)
        return {
            "name": f"Audit Report - {self.precheck_run.data_file_type.name}",
            "template_path": f"audit/{template_name}",
            "data_file_type": self.precheck_run.data_file_type,
            "created_by": self.precheck_run.created_by,
            "cohort": self.precheck_run.cohort
        }

    def cleanup(self):
        """Clean up resources with workspace management and PHI tracking"""
        # Close database connection
        if self.conn:
            self.conn.close()
            self.conn = None
        
        # Clean up temporary files
        if hasattr(self, "temp_file_path") and self.temp_file_path and os.path.exists(self.temp_file_path):
            os.remove(self.temp_file_path)
        
        # Clean up workspace directory using ScratchManager
        # Always try to clean up precheck_run workspace since we know we have precheck_run
        try:
            from depot.storage.scratch_manager import ScratchManager
            scratch = ScratchManager()

            # Clean up precheck_run workspace
            success = scratch.cleanup_precheck_run(self.precheck_run.id)
            if success:
                logger.info(f"Successfully cleaned up workspace for precheck_run {self.precheck_run.id}")
                # Mark ALL files in this workspace as cleaned in PHI tracking
                user = self.precheck_run.uploaded_by or self.precheck_run.created_by

                # Use relative paths to match metadata (file_path is now absolute)
                scratch_relative = f"scratch/precheck_runs/{self.precheck_run.id}"
                csv_relative = f"scratch/precheck_runs/{self.precheck_run.id}/input.csv"
                duckdb_relative = f"scratch/precheck_runs/{self.precheck_run.id}/audit_{self.precheck_run.id}.duckdb"

                # Mark workspace directory as cleaned
                tracking = PHIFileTracking.objects.filter(
                    metadata__relative_path=scratch_relative,
                    cleanup_required=True,
                    cleaned_up=False
                ).first()
                if tracking:
                    tracking.mark_cleaned_up(user)
                    logger.info(f"Marked workspace directory as cleaned: {scratch_relative}")

                # Mark DuckDB file as cleaned
                tracking = PHIFileTracking.objects.filter(
                    metadata__relative_path=duckdb_relative,
                    cleanup_required=True,
                    cleaned_up=False
                ).first()
                if tracking:
                    tracking.mark_cleaned_up(user)
                    logger.info(f"Marked DuckDB file as cleaned: {duckdb_relative}")

                # Mark CSV file as cleaned
                tracking = PHIFileTracking.objects.filter(
                    metadata__relative_path=csv_relative,
                    cleanup_required=True,
                    cleaned_up=False
                ).first()
                if tracking:
                    tracking.mark_cleaned_up(user)
                    logger.info(f"Marked CSV file as cleaned: {csv_relative}")
            else:
                logger.error(f"Failed to cleanup workspace for precheck_run {self.precheck_run.id}")

        except Exception as e:
            logger.error(f"Failed to cleanup workspace: {e}")
            # Try direct cleanup as fallback
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as cleanup_error:
                    logger.error(f"Direct cleanup also failed: {cleanup_error}")

    def _create_table(self):
        """Create DuckDB table with normalized columns and row numbers"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as temp_csv:
            # Add row_no to the header
            header = "row_no," + ",".join(
                [self.column_mapping.get(col, col) for col in self.submitted_columns]
            )
            temp_csv.write(header + "\n")

            # Write the rest of the file
            with open(self.temp_file_path, "r") as f:
                next(f)  # Skip original header
                for idx, line in enumerate(f, start=1):
                    temp_csv.write(f"{idx},{line}")

            temp_csv_path = temp_csv.name

        try:
            # Create the table with explicit type for row_no as INTEGER
            self.conn.execute(
                f"""
                CREATE TABLE data AS 
                SELECT 
                    CAST(row_no AS INTEGER) as row_no,
                    * EXCLUDE (row_no)
                FROM read_csv(
                    '{temp_csv_path}',
                    header=true,
                    sep=',',
                    quote='"',
                    escape='"',
                    nullstr=''
                )
            """
            )
        finally:
            # Clean up temp CSV
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)

    def _normalize_columns(self):
        """Create mapping between submitted columns and definition columns"""
        # Read first line of CSV
        with open(self.temp_file_path, "r") as f:
            header = f.readline().strip()

        self.submitted_columns = [col.strip() for col in header.split(",")]
        definition_names = [col["name"] for col in self.definition]

        # Build case-insensitive mapping
        for def_col in definition_names:
            for sub_col in self.submitted_columns:
                if def_col.lower() == sub_col.lower() and def_col != sub_col:
                    self.column_mapping[sub_col] = def_col
