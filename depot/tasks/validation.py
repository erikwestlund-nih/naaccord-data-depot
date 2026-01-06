"""
Celery tasks for granular validation system.

This module provides tasks for converting uploaded files to DuckDB
and initiating validation runs.
"""
import logging
import os
import tempfile
from datetime import timedelta

import duckdb
from celery import shared_task
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from depot.models import PHIFileTracking, PrecheckRun, ValidationRun
from depot.services.data_mapping import DataMappingService
from depot.storage.scratch_manager import ScratchManager
from depot.tasks.validation_orchestration import start_validation_run

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def convert_precheck_to_duckdb(self, precheck_run_id, validation_run_id=None):
    """
    Convert uploaded CSV to DuckDB for a precheck run.

    Args:
        precheck_run_id: ID of the PrecheckRun instance
        validation_run_id: Optional existing ValidationRun ID (created if omitted)

    Returns:
        int: ValidationRun ID ready for validation
    """
    try:
        logger.info(f"Starting DuckDB conversion for PrecheckRun {precheck_run_id}")

        # Get the upload precheck
        precheck_run = PrecheckRun.objects.get(id=precheck_run_id)
        user = precheck_run.uploaded_by or precheck_run.created_by

        # Stage 1: Processing Data File
        precheck_run.mark_processing_duckdb(None)
        logger.info(f"Stage 1: Processing data file for PrecheckRun {precheck_run_id}")

        # Get the file content
        from depot.storage.manager import StorageManager
        storage = StorageManager.get_storage('uploads')

        # Remove /media/submissions/ prefix if present
        storage_path = precheck_run.uploaded_file.storage_path
        logger.info(f"Original storage_path from DB: {storage_path}")

        # Strip disk prefixes used for storage bookkeeping
        if storage_path.startswith('uploads/'):
            storage_path = storage_path[len('uploads/'):]
            logger.info(f"Stripped 'uploads/' prefix, now: {storage_path}")
        if storage_path.startswith('/media/submissions/'):
            storage_path = storage_path.replace('/media/submissions/', '')
            logger.info(f"Stripped '/media/submissions/' prefix, now: {storage_path}")
        elif storage_path.startswith('media/submissions/'):
            storage_path = storage_path.replace('media/submissions/', '')
            logger.info(f"Stripped 'media/submissions/' prefix, now: {storage_path}")

        logger.info(f"Loading file from storage path: {storage_path}")
        logger.info(f"Storage base_path: {storage.base_path}")
        logger.info(f"Storage class: {storage.__class__.__name__}")

        try:
            data_content = storage.get_file(storage_path)
            logger.info(f"Successfully read file, content type: {type(data_content)}, length: {len(data_content) if data_content else 'None'}")
        except Exception as e:
            logger.error(f"Exception reading file: {e}", exc_info=True)
            raise ValueError(f"Could not read file from storage: {storage_path}") from e

        if data_content is None:
            raise ValueError(f"Could not read file from storage: {storage_path}")

        if isinstance(data_content, bytes):
            data_content = data_content.decode('utf-8')

        # Stage files in scratch workspace so PHI tracking/cleanup remain consistent
        scratch = ScratchManager()
        workspace_prefix = scratch.get_precheck_run_dir(precheck_run.id)
        workspace_relative = workspace_prefix.rstrip('/')
        workspace_absolute = scratch.storage.get_absolute_path(workspace_relative)

        # Track workspace directory (one record per upload precheck workspace)
        PHIFileTracking.objects.create(
            cohort=precheck_run.cohort,
            user=user,
            action='work_copy_created',
            file_path=workspace_absolute,
            file_type='workspace_directory',
            cleanup_required=True,
            content_object=precheck_run,
            metadata={'relative_path': workspace_relative},
            expected_cleanup_by=timezone.now() + timedelta(hours=6)
        )

        # Save raw CSV into scratch for audit trail
        raw_relative = f"{workspace_prefix}input.csv"
        scratch.storage.save(raw_relative, data_content, 'text/csv')
        raw_absolute = scratch.storage.get_absolute_path(raw_relative)
        raw_tracking = PHIFileTracking.objects.create(
            cohort=precheck_run.cohort,
            user=user,
            action='work_copy_created',
            file_path=raw_absolute,
            file_type='raw_csv',
            cleanup_required=True,
            content_object=precheck_run,
            metadata={'relative_path': raw_relative},
            expected_cleanup_by=timezone.now() + timedelta(hours=6)
        )

        # Create temporary raw CSV file for mapping pipeline
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as temp_csv:
            temp_csv.write(data_content)
            raw_file_path = temp_csv.name

        # Apply data processing (cohort-specific transformations: column renames, value remaps, etc.)
        # If no cohort is associated, use a generic cohort name for passthrough processing
        cohort_name = precheck_run.cohort.name if precheck_run.cohort else 'Unknown'

        processing_service = DataMappingService(
            cohort_name=cohort_name,
            data_file_type=precheck_run.data_file_type.name
        )

        # Create temporary processed CSV file
        processed_file_path = tempfile.mktemp(suffix=".csv")

        logger.info(f"Stage 1: Applying data processing for cohort: {cohort_name}")
        processing_results = processing_service.process_file(raw_file_path, processed_file_path)

        if processing_results.get('errors'):
            error_msg = f"Data processing failed: {processing_results['errors']}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Stage 1 complete: Data processing finished - {processing_results.get('summary', {})}")

        # Stage 2: Creating Analytic Data File (DuckDB)
        duckdb_relative = f"{workspace_prefix}validation_{precheck_run_id}.duckdb"
        duckdb_absolute = scratch.storage.get_absolute_path(duckdb_relative)

        logger.info(f"Stage 2: Creating analytic data file (DuckDB) at {duckdb_absolute}")
        PHIFileTracking.log_operation(
            cohort=precheck_run.cohort,
            user=user,
            action='conversion_started',
            file_path=duckdb_absolute,
            file_type='duckdb',
            content_object=precheck_run,
            metadata={'relative_path': duckdb_relative}
        )

        # Convert processed CSV to DuckDB (DuckDB creates the file if missing)
        conn = duckdb.connect(duckdb_absolute)

        # Create table from processed CSV with automatic type detection
        # Use CREATE OR REPLACE to handle cases where table already exists
        conn.execute(f"""
            CREATE OR REPLACE TABLE data AS
            SELECT *, ROW_NUMBER() OVER () AS row_no
            FROM read_csv_auto('{processed_file_path}', header=true, all_varchar=false)
        """)

        # Get row count
        row_count = conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
        logger.info(f"Stage 2 complete: Loaded {row_count} rows into DuckDB")

        conn.close()

        # Log DuckDB workspace artefact
        PHIFileTracking.objects.create(
            cohort=precheck_run.cohort,
            user=user,
            action='work_copy_created',
            file_path=duckdb_absolute,
            file_type='duckdb',
            cleanup_required=True,
            content_object=precheck_run,
            metadata={'relative_path': duckdb_relative},
            expected_cleanup_by=timezone.now() + timedelta(hours=6)
        )

        PHIFileTracking.log_operation(
            cohort=precheck_run.cohort,
            user=user,
            action='conversion_completed',
            file_path=duckdb_absolute,
            file_type='duckdb',
            content_object=precheck_run,
            metadata={'relative_path': duckdb_relative}
        )

        # Clean up temp files
        os.remove(raw_file_path)
        os.remove(processed_file_path)

        # Raw CSV staged in scratch is no longer needed once DuckDB is created
        if scratch.storage.delete(raw_relative):
            raw_tracking.mark_cleaned_up(user)
            PHIFileTracking.objects.create(
                cohort=precheck_run.cohort,
                user=user,
                action='work_copy_deleted',
                file_path=raw_absolute,
                file_type='raw_csv',
                content_object=precheck_run,
                metadata={'relative_path': raw_relative}
            )

        # Delete original uploaded file (stored on uploads disk) now that processing is complete
        try:
            if precheck_run.uploaded_file:
                original_path = precheck_run.uploaded_file.storage_path
                delete_path = original_path[len('uploads/'):] if original_path.startswith('uploads/') else original_path.lstrip('/')

                if storage.delete(delete_path):
                    tracking = PHIFileTracking.objects.filter(
                        action='file_uploaded_via_stream',
                        metadata__relative_path=original_path,
                        cleanup_required=True,
                        cleaned_up=False
                    ).first()

                    if tracking:
                        tracking.mark_cleaned_up(user)
                        PHIFileTracking.objects.create(
                            cohort=tracking.cohort,
                            user=user,
                            action='work_copy_deleted',
                            file_path=tracking.file_path,
                            file_type=tracking.file_type,
                            content_object=precheck_run,
                            metadata=tracking.metadata,
                            server_role=tracking.server_role
                        )
                    logger.info("Deleted original precheck upload %s", original_path)
                else:
                    logger.warning("Failed to delete original precheck upload %s", original_path)
        except Exception as original_cleanup_error:
            logger.warning("Failed to cleanup original precheck upload: %s", original_cleanup_error, exc_info=True)

        logger.info(f"Stage 3: Preparing validation run")

        # Get or create ValidationRun
        if validation_run_id:
            # Update existing ValidationRun with DuckDB path and processing metadata
            validation_run = ValidationRun.objects.get(id=validation_run_id)
            validation_run.duckdb_path = duckdb_absolute
            validation_run.processing_metadata = processing_results
            validation_run.save(update_fields=['duckdb_path', 'processing_metadata', 'updated_at'])
            logger.info(f"Updated ValidationRun {validation_run.id} with DuckDB path and processing metadata")
        else:
            # Create new ValidationRun (backward compatibility)
            content_type = ContentType.objects.get_for_model(precheck_run)
            validation_run = ValidationRun.objects.create(
                content_type=content_type,
                object_id=precheck_run.id,
                data_file_type=precheck_run.data_file_type,
                duckdb_path=duckdb_absolute,
                processing_metadata=processing_results
            )
            logger.info(f"Created ValidationRun {validation_run.id} for PrecheckRun {precheck_run_id}")

        # Kick off validation run now that conversion is complete
        start_validation_run.delay(validation_run.id)
        return validation_run.id

    except Exception as e:
        logger.error(f"Failed to convert to DuckDB: {e}", exc_info=True)
        try:
            precheck_run = PrecheckRun.objects.get(id=precheck_run_id)
            precheck_run.mark_failed(str(e))
        except Exception as save_error:
            logger.error(f"Failed to mark precheck run as failed: {save_error}")
        raise
