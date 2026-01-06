"""
Celery tasks for DuckDB file creation.
"""
import logging
from celery import shared_task
from depot.models import DataTableFile
from depot.storage.phi_manager import PHIStorageManager

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def create_duckdb_task(self, task_data):
    """
    Create DuckDB file from raw CSV/TSV data.
    For multi-file tables (non-patient), combines all current files into one DuckDB.
    For single-file tables (patient), processes just that file.

    Args:
        task_data: Data bundle dict with pre-fetched information

    Returns:
        dict: DuckDB file information
    """
    try:
        from depot.models import User, DataFileType

        # Extract data from bundle
        data_file_id = task_data['data_file_id']
        user_id = task_data['user_id']

        logger.info(f"DUCKDB_TASK: Starting DuckDB creation for file {data_file_id}, user {user_id}")
        logger.info(f"DUCKDB_TASK: Task data keys: {list(task_data.keys())}")

        # Still need to fetch these for some operations
        data_file = DataTableFile.objects.get(id=data_file_id)
        user = User.objects.get(id=user_id)

        logger.info(f"DUCKDB_TASK: Loaded DataTableFile {data_file_id}, raw_file_path: {data_file.raw_file_path}")

        # Update upload precheck status to processing_duckdb
        from depot.models import PrecheckRun
        if hasattr(data_file, 'precheck_run') and data_file.precheck_run:
            precheck_run = data_file.precheck_run
            precheck_run.status = 'processing_duckdb'
            precheck_run.save(update_fields=['status'])
            logger.info(f"Updated PrecheckRun {precheck_run.id} status to processing_duckdb")

        # Get PHI manager
        phi_manager = PHIStorageManager()

        # Ensure raw file exists
        if not data_file.raw_file_path:
            raise ValueError(f"No raw file path for DataTableFile {data_file_id}")

        submission = data_file.data_table.submission
        data_table = data_file.data_table
        file_type = data_table.data_file_type.name

        # Determine if this is a multi-file table
        # Patient tables are single-file only, all others support multiple files
        is_patient_table = file_type == 'patient'

        if is_patient_table:
            # Single file processing for patient tables
            logger.info(f"DUCKDB_TASK: Processing single patient file")
            upload_id = data_file.uploaded_file.id if data_file.uploaded_file else data_file.id
            conversion_result = phi_manager.convert_to_duckdb(
                raw_nas_path=data_file.raw_file_path,
                submission=submission,
                file_type=file_type,
                user=user,
                upload_id=upload_id
            )
        else:
            # Multi-file processing: get ALL current files for this table
            current_files = DataTableFile.objects.filter(
                data_table=data_table,
                is_current=True
            ).order_by('id')

            files_with_raw = [(f.uploaded_file.id if f.uploaded_file else f.id, f.raw_file_path) for f in current_files if f.raw_file_path]

            logger.info(f"DUCKDB_TASK: Processing {len(files_with_raw)} files for multi-file table {file_type}")
            for idx, (upload_id, path) in enumerate(files_with_raw):
                logger.info(f"  File {idx + 1} (Upload ID {upload_id}): {path}")

            # For multi-file tables, ALWAYS use multi-file method (creates only combined files)
            # This ensures we never create individual DuckDB files for multi-file tables
            conversion_result = phi_manager.convert_multiple_files_to_duckdb(
                files_with_raw=files_with_raw,
                submission=submission,
                file_type=file_type,
                user=user
            )

        if not conversion_result:
            raise ValueError("DuckDB conversion failed")

        # Unpack result - both return 3 items now
        duckdb_nas_path, processed_nas_path, processing_metadata = conversion_result

        # Update ALL current DataTableFiles with the same DuckDB and processed file paths
        # This ensures all files point to the combined DuckDB
        # Store relative paths (like raw_file_path) so they work across environments
        from django.utils import timezone

        if is_patient_table:
            # Single file update
            data_file.duckdb_file_path = duckdb_nas_path
            data_file.processed_file_path = processed_nas_path
            data_file.duckdb_created_at = timezone.now()
            data_file.save(update_fields=['duckdb_file_path', 'processed_file_path', 'duckdb_created_at'])
            logger.info(f"Updated DataTableFile {data_file.id} with DuckDB path")
        else:
            # Multi-file: update ALL current files with the SAME combined DuckDB and processed paths
            # All files point to the single diagnosis_processed.csv and diagnosis_combined.duckdb
            current_files_to_update = DataTableFile.objects.filter(
                data_table=data_table,
                is_current=True
            )

            for file_record in current_files_to_update:
                upload_id = file_record.uploaded_file.id if file_record.uploaded_file else file_record.id

                file_record.duckdb_file_path = duckdb_nas_path
                file_record.processed_file_path = processed_nas_path
                file_record.duckdb_created_at = timezone.now()
                file_record.save(update_fields=['duckdb_file_path', 'processed_file_path', 'duckdb_created_at'])

                logger.info(f"Updated File {file_record.id} (Upload {upload_id}): duckdb={duckdb_nas_path}, processed={processed_nas_path}")

            logger.info(f"Updated {current_files_to_update.count()} DataTableFile records with combined paths")

        logger.info(f"Successfully created DuckDB file: {duckdb_nas_path}")

        # Return enhanced task_data for next step
        # Convert to absolute path for next task (but don't store in DB)
        absolute_duckdb_path = phi_manager.storage.get_absolute_path(duckdb_nas_path)

        result = task_data.copy()
        result.update({
            'duckdb_path': absolute_duckdb_path,
            'duckdb_creation_completed': True,
            'processing_metadata': processing_metadata,
        })

        logger.info(f"DUCKDB_TASK: Successfully completed DuckDB creation for file {data_file_id}")
        logger.info(f"DUCKDB_TASK: Returning result with keys: {list(result.keys())}")

        return result

    except Exception as e:
        logger.error(f"DUCKDB_TASK: Failed to create DuckDB for DataTableFile {data_file_id}: {e}")

        # Check if we've exhausted retries
        if self.request.retries >= self.max_retries:
            # Final failure - update database status
            try:
                data_file = DataTableFile.objects.get(id=data_file_id)
                data_file.duckdb_conversion_error = str(e)
                data_file.save(update_fields=['duckdb_conversion_error'])

                # Update data table status to failed
                data_table = data_file.data_table
                data_table.update_status('failed')

                logger.error(f"DUCKDB_TASK: Max retries exhausted for file {data_file_id}, marked as failed")
            except Exception as update_error:
                logger.error(f"DUCKDB_TASK: Failed to update status after max retries: {update_error}")

            # Re-raise to mark task as failed
            raise
        else:
            # Retry the task
            raise self.retry(countdown=60, exc=e)
