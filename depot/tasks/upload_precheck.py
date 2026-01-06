from celery import shared_task
import logging
from depot.models import PrecheckRun

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def process_precheck_run(self, precheck_run_id):
    """
    Process upload precheck.

    OPTIMIZED: Uses file paths instead of loading content into memory.
    For a 1.9GB file, this reduces peak memory from ~6GB to ~500MB.
    """
    try:
        import os
        logger.info(f"Starting upload precheck process for precheck_run_id: {precheck_run_id}")
        precheck_run = PrecheckRun.objects.get(id=precheck_run_id)
        logger.info(f"Found upload precheck: {precheck_run.id}, data_file_type: {precheck_run.data_file_type.name}")

        # OPTIMIZATION: Get file path instead of loading content into memory
        file_path = None
        data_content = None  # Only used as fallback

        if precheck_run.uploaded_file:
            from depot.storage.manager import StorageManager
            storage = StorageManager.get_storage('uploads')

            # Remove /media/submissions/ prefix if present
            storage_path = precheck_run.uploaded_file.storage_path
            if storage_path.startswith('uploads/'):
                storage_path = storage_path[len('uploads/'):]
            if storage_path.startswith('/media/submissions/'):
                storage_path = storage_path.replace('/media/submissions/', '')
            elif storage_path.startswith('media/submissions/'):
                storage_path = storage_path.replace('media/submissions/', '')

            # OPTIMIZATION: Get absolute file path instead of loading content
            try:
                file_path = storage.get_absolute_path(storage_path)
                if os.path.exists(file_path):
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    logger.info(f"Using file path directly: {file_path} ({file_size_mb:.1f} MB) - no memory load")
                else:
                    logger.warning(f"File path doesn't exist: {file_path}, falling back to content load")
                    file_path = None
            except Exception as e:
                logger.warning(f"Could not get absolute path: {e}, falling back to content load")
                file_path = None

            # Fallback: load content if file path not available
            if file_path is None:
                logger.info(f"Attempting to read file content from path: {storage_path}")
                data_content = storage.get_file(storage_path)
                logger.info(f"Retrieved content type: {type(data_content)}, is None: {data_content is None}")

                if data_content is None:
                    raise ValueError(f"Could not read file from storage at path: {precheck_run.uploaded_file.storage_path}")

                if isinstance(data_content, bytes):
                    data_content = data_content.decode('utf-8')

                logger.info(f"Read data content, length: {len(data_content)}")

        elif precheck_run.temp_file:
            # Fallback to temp_file for backward compatibility
            data_content = precheck_run.temp_file.read_contents()
            if data_content is None:
                raise ValueError("File content is None")
            logger.info(f"Read data content from temp_file, length: {len(data_content)}")
        else:
            raise ValueError("No file found for upload precheck")

        # Process the complete upload precheck
        from depot.data.upload_prechecker import Auditor
        auditor = Auditor(
            data_file_type=precheck_run.data_file_type,
            precheck_run=precheck_run,
            data_content=data_content,  # May be None if using file_path
            file_path=file_path  # Preferred - avoids memory overhead
        )
        logger.info(f"Created auditor instance (file_path={file_path is not None})")

        # Process the upload precheck (including notebook creation and compilation)
        result = auditor.process()
        logger.info(f"Got upload precheck result: {result}")

        # Cleanup the uploaded file after successful processing
        if result.get('status') in ['success', 'completed'] and precheck_run.uploaded_file:
            try:
                from depot.models import PHIFileTracking

                # Find the PHI tracking record for this file
                # Use GenericForeignKey relationship instead of path query (avoids MySQL JSONField bugs)
                from django.contrib.contenttypes.models import ContentType
                tracking = PHIFileTracking.objects.filter(
                    content_type=ContentType.objects.get_for_model(precheck_run.uploaded_file),
                    object_id=precheck_run.uploaded_file.id,
                    action='file_uploaded_via_stream',
                    cleanup_required=True,
                    cleaned_up=False
                ).first()

                if tracking:
                    # Delete the file from storage
                    path_for_delete = precheck_run.uploaded_file.storage_path
                    if path_for_delete.startswith('uploads/'):
                        path_for_delete = path_for_delete[len('uploads/'):]

                    if storage.delete(path_for_delete):
                        # Mark as cleaned up
                        tracking.mark_cleaned_up(precheck_run.uploaded_by)
                        logger.info(f"Successfully cleaned up upload precheck file: {precheck_run.uploaded_file.storage_path}")

                        # Create deletion tracking record
                        PHIFileTracking.objects.create(
                            cohort=tracking.cohort,
                            user=precheck_run.uploaded_by,
                            action='work_copy_deleted',
                            file_path=precheck_run.uploaded_file.storage_path,
                            file_type=tracking.file_type,
                            server_role='services',
                            purpose_subdirectory='auto_cleanup_after_processing'
                        )
                    else:
                        logger.warning(f"Failed to delete upload precheck file: {precheck_run.uploaded_file.storage_path}")
                else:
                    logger.warning(f"No PHI tracking record found for: {precheck_run.uploaded_file.storage_path}")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up upload precheck file: {cleanup_error}", exc_info=True)
                # Don't fail the task if cleanup fails

        return result

    except Exception as e:
        logger.error(f"Error processing upload precheck: {e}", exc_info=True)
        if "precheck_run" in locals():
            precheck_run.mark_failed(str(e))

            # Cleanup uploaded file on failure to prevent disk space accumulation
            if precheck_run.uploaded_file and 'storage' in locals():
                try:
                    from depot.models import PHIFileTracking
                    from django.contrib.contenttypes.models import ContentType
                    tracking = PHIFileTracking.objects.filter(
                        content_type=ContentType.objects.get_for_model(precheck_run.uploaded_file),
                        object_id=precheck_run.uploaded_file.id,
                        action='file_uploaded_via_stream',
                        cleanup_required=True,
                        cleaned_up=False
                    ).first()

                    if tracking:
                        path_for_delete = precheck_run.uploaded_file.storage_path
                        if path_for_delete.startswith('uploads/'):
                            path_for_delete = path_for_delete[len('uploads/'):]

                        if storage.delete(path_for_delete):
                            tracking.mark_cleaned_up(precheck_run.uploaded_by)
                            logger.info(f"Cleaned up failed upload file: {precheck_run.uploaded_file.storage_path}")
                            PHIFileTracking.objects.create(
                                cohort=tracking.cohort,
                                user=precheck_run.uploaded_by,
                                action='work_copy_deleted',
                                file_path=precheck_run.uploaded_file.storage_path,
                                file_type=tracking.file_type,
                                server_role='services',
                                purpose_subdirectory='auto_cleanup_after_failure'
                            )
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up failed upload: {cleanup_error}")

        return {"status": "error", "precheck_run_id": precheck_run_id, "error": str(e)}
    finally:
        if "auditor" in locals():
            auditor.cleanup()


@shared_task(bind=True)
def process_precheck_run_with_duckdb(self, task_data):
    """
    Process upload precheck using pre-created DuckDB file.
    This task is designed to work in a sequential Celery workflow.

    Args:
        task_data: Data bundle dict from previous workflow step

    Returns:
        Dict with processing results for next workflow step
    """
    try:
        from depot.models import DataTableFile, PrecheckRun
        from depot.data.upload_prechecker import Auditor

        logger.info(f"UPLOAD_PRECHECK_TASK: Starting upload precheck with DuckDB")

        # Validate task_data
        if task_data is None:
            logger.error("UPLOAD_PRECHECK_TASK: Received None task_data")
            raise ValueError("task_data cannot be None")

        if not isinstance(task_data, dict):
            logger.error(f"UPLOAD_PRECHECK_TASK: Received non-dict: {type(task_data)}")
            raise TypeError(f"Expected dict, got {type(task_data)}")

        # Log what we received
        logger.info(f"UPLOAD_PRECHECK_TASK: Task data keys: {list(task_data.keys()) if task_data else 'None'}")
        logger.info(f"UPLOAD_PRECHECK_TASK: data_file_id: {task_data.get('data_file_id')}, patient_extraction_completed: {task_data.get('patient_extraction_completed')}")

        # Ensure required fields
        data_file_id = task_data.get('data_file_id')
        if not data_file_id:
            logger.error(f"Missing data_file_id in task_data: {task_data}")
            raise ValueError("data_file_id is required in task_data")

        logger.info(f"Starting upload precheck with DuckDB for file {data_file_id}")

        # Get the DataTableFile to find associated PrecheckRun
        data_file = DataTableFile.objects.get(id=task_data['data_file_id'])

        # Find the PrecheckRun associated with this DataTableFile
        precheck_run = None

        # First try direct relationship
        if hasattr(data_file, 'precheck_run') and data_file.precheck_run:
            precheck_run = data_file.precheck_run
            logger.info(f"Found upload precheck via direct relationship: {precheck_run.id}")

        # Fallback to submission file relationship (for patient files)
        elif hasattr(data_file, 'submission_file') and data_file.submission_file and hasattr(data_file.submission_file, 'precheck_run'):
            precheck_run = data_file.submission_file.precheck_run
            logger.info(f"Found upload precheck via submission_file relationship: {precheck_run.id}")

        if not precheck_run:
            # Last resort: look for upload precheck by file type and recent creation (no status restriction)
            precheck_runs = PrecheckRun.objects.filter(
                data_file_type=data_file.data_table.data_file_type,
            ).order_by('-created_at')

            if precheck_runs.exists():
                precheck_run = precheck_runs.first()
                logger.info(f"Found upload precheck via fallback query: {precheck_run.id}")
            else:
                raise ValueError(f"No PrecheckRun found for DataTableFile {task_data['data_file_id']}")

        logger.info(f"Using upload precheck: {precheck_run.id} with status: {precheck_run.status}")

        # Update status to processing_notebook
        precheck_run.status = 'processing_notebook'
        precheck_run.save(update_fields=['status'])
        logger.info(f"Updated PrecheckRun {precheck_run.id} status to processing_notebook")

        # Create Auditor with DuckDB already available
        # We need to get the data content from the uploaded file
        from depot.storage.manager import StorageManager
        storage = StorageManager.get_storage('uploads')

        # Get the original file content
        original_file_path = data_file.raw_file_path
        data_content = storage.get_file(original_file_path)
        if isinstance(data_content, bytes):
            data_content = data_content.decode('utf-8')

        # Create Auditor with all required parameters
        auditor = Auditor(
            data_file_type=data_file.data_table.data_file_type,
            data_content=data_content,
            precheck_run=precheck_run
        )

        # Set the DuckDB path from the task data
        auditor.db_path = task_data['duckdb_path']

        # Process the audit using the pre-created DuckDB
        result = auditor.process()

        # Update upload precheck status
        precheck_run.status = result.get('status', 'completed')
        precheck_run.result = result
        precheck_run.save()

        logger.info(f"UPLOAD_PRECHECK_TASK: Upload precheck completed successfully for {precheck_run.id}")

        # Return enhanced task_data for cleanup step
        result_data = task_data.copy()
        result_data.update({
            'precheck_run_id': precheck_run.id,
            'notebook_processing_completed': True,
            'precheck_run_result': result
        })

        logger.info(f"UPLOAD_PRECHECK_TASK: Successfully completed upload precheck processing")
        logger.info(f"UPLOAD_PRECHECK_TASK: Returning result with keys: {list(result_data.keys())}")

        return result_data

    except Exception as e:
        logger.error(f"UPLOAD_PRECHECK_TASK: Error processing upload precheck with DuckDB: {e}", exc_info=True)
        if "precheck_run" in locals():
            precheck_run.mark_failed(str(e))

        # Still return task_data for cleanup even on failure
        error_result = task_data.copy()
        error_result.update({
            'status': 'error',
            'error': str(e),
            'precheck_run_failed': True
        })
        return error_result
