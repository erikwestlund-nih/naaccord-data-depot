"""
Upload Precheck Service

Centralized service for handling upload precheck creation and processing.
Provides consistent upload precheck management across the application.
"""
import logging
from django.conf import settings
from depot.models import PrecheckRun
from depot.tasks import process_precheck_run

logger = logging.getLogger(__name__)


class PrecheckRunService:
    """Service for managing upload precheck operations."""
    
    @staticmethod
    def create_precheck_run(submission, data_table_file, uploaded_file_record, user):
        """
        Create an upload precheck record for a file upload.
        
        Args:
            submission: CohortSubmission instance
            data_table_file: DataTableFile instance
            uploaded_file_record: UploadedFile instance
            user: User who uploaded the file
            
        Returns:
            PrecheckRun instance
        """
        precheck_run = PrecheckRun.objects.create(
            cohort=submission.cohort,
            uploaded_file=uploaded_file_record,
            data_file_type=data_table_file.data_table.data_file_type,
            uploaded_by=user,
            created_by=user,
            original_filename=data_table_file.original_filename,
            file_size=data_table_file.file_size,
        )
        
        # Note: PrecheckRun is standalone - not linked to submission data table files
        
        logger.info(f"Created upload precheck {precheck_run.id} for file {data_table_file.id}")
        return precheck_run
    
    @staticmethod
    def trigger_processing(precheck_run_id):
        """
        Trigger upload precheck processing, with fallback to synchronous if Celery fails.
        
        Args:
            precheck_run_id: ID of the upload precheck to process
            
        Returns:
            bool: True if successfully queued/processed, False otherwise
        """
        return PrecheckRunService.handle_async_sync_task(
            async_func=process_precheck_run.delay,
            sync_func=process_precheck_run,
            task_args=(precheck_run_id,),
            task_name="upload precheck processing",
            object_id=precheck_run_id
        )
    
    @staticmethod
    def handle_async_sync_task(async_func, sync_func, task_args, task_name, object_id):
        """
        Generic handler for tasks that should run async but can fallback to sync.
        
        Args:
            async_func: Celery task delay function
            sync_func: Synchronous function fallback
            task_args: Arguments tuple for the task
            task_name: Human-readable task name for logging
            object_id: ID of the object being processed
            
        Returns:
            bool: True if task was handled (async or sync), False if failed
        """
        try:
            # Try to queue task asynchronously
            logger.info(f"Queueing {task_name} for ID {object_id}")
            async_func(*task_args)
            logger.info(f"Successfully queued {task_name} for ID {object_id}")
            return True
            
        except Exception as celery_error:
            # If Celery isn't running, try synchronously as fallback
            logger.error(f"Failed to queue {task_name}: {celery_error}")
            
            if settings.DEBUG:
                # In development, fall back to synchronous execution
                logger.info(f"DEBUG mode: Falling back to synchronous {task_name}")
                try:
                    sync_func(*task_args)
                    logger.info(f"Synchronous {task_name} completed for ID {object_id}")
                    return True
                except Exception as sync_error:
                    logger.error(f"Synchronous {task_name} also failed: {sync_error}", exc_info=True)
                    return False
            else:
                # In production, re-raise the Celery error
                raise celery_error
    
    @staticmethod
    def check_status(precheck_run_id):
        """
        Check the current status of an upload precheck.
        
        Args:
            precheck_run_id: ID of the upload precheck
            
        Returns:
            str: Current status or None if not found
        """
        try:
            precheck_run = PrecheckRun.objects.get(id=precheck_run_id)
            return precheck_run.status
        except PrecheckRun.DoesNotExist:
            return None
    
    @staticmethod
    def get_report_url(precheck_run):
        """
        Get the S3 signed URL for an upload precheck report.
        
        Args:
            precheck_run: PrecheckRun instance
            
        Returns:
            str: Signed URL or None if report not available
        """
        if precheck_run.status == 'completed' and precheck_run.report_url:
            # TODO: Implement S3 signed URL generation
            # For now, return the stored URL
            return precheck_run.report_url
        return None
    
    @staticmethod
    def mark_failed(precheck_run_id, error_message):
        """
        Mark an upload precheck as failed with error details.
        
        Args:
            precheck_run_id: ID of the upload precheck
            error_message: Error description
        """
        try:
            precheck_run = PrecheckRun.objects.get(id=precheck_run_id)
            precheck_run.mark_failed(error_message)
            logger.error(f"Upload precheck {precheck_run_id} marked as failed: {error_message}")
        except PrecheckRun.DoesNotExist:
            logger.error(f"Cannot mark upload precheck {precheck_run_id} as failed - not found")
    
    # NOTE: Removed get_precheck_run_report_urls() method
    # Submissions use ValidationRun, not PrecheckRun
    # PrecheckRun is only for standalone precheck validation workflow