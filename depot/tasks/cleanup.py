"""
Celery tasks for file cleanup operations.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def cleanup_workflow_files_task(self, task_data):
    """
    Clean up temporary files created during the workflow.

    Args:
        task_data: Data bundle dict containing workflow information

    Returns:
        dict: Cleanup results
    """
    try:
        from depot.models import DataTableFile, PrecheckRun
        from depot.storage.phi_manager import PHIStorageManager
        from depot.storage.scratch_manager import ScratchManager

        logger.info(f"CLEANUP_TASK: Starting cleanup for workflow")
        logger.info(f"CLEANUP_TASK: Task data keys: {list(task_data.keys()) if task_data else 'None'}")

        cleanup_results = {
            'duckdb_cleanup': False,
            'scratch_cleanup': False,
            'phi_cleanup': False
        }

        # Clean up DuckDB file if it exists
        if task_data.get('duckdb_path'):
            # Preserve DuckDB artifacts so validation can be re-run without rebuilding.
            cleanup_results['duckdb_cleanup'] = False

        # Clean up scratch directories if upload precheck exists
        if task_data.get('precheck_run_id'):
            try:
                scratch = ScratchManager()
                success = scratch.cleanup_precheck_run(task_data['precheck_run_id'])
                cleanup_results['scratch_cleanup'] = success
                if success:
                    logger.info(f"Cleaned up scratch files for upload precheck {task_data['precheck_run_id']}")
                else:
                    logger.warning(f"Failed to clean up scratch files for upload precheck {task_data['precheck_run_id']}")

            except Exception as e:
                logger.error(f"Error cleaning up scratch files: {e}")

        # Clean up any PHI tracking records if needed
        try:
            from depot.models import PHIFileTracking

            # Mark cleanup operations in PHI tracking
            if task_data.get('data_file_id'):
                data_file = DataTableFile.objects.get(id=task_data['data_file_id'])
                submission = data_file.data_table.submission

                PHIFileTracking.log_operation(
                    cohort=submission.cohort,
                    user_id=task_data.get('user_id'),
                    action='workflow_cleanup_completed',
                    file_path=task_data.get('duckdb_path', 'unknown'),
                    file_type='cleanup_operation',
                    content_object=data_file
                )
                cleanup_results['phi_cleanup'] = True

        except Exception as e:
            logger.error(f"Error updating PHI tracking for cleanup: {e}")

        logger.info(f"CLEANUP_TASK: Cleanup completed for workflow. Results: {cleanup_results}")

        return {
            'success': True,
            'task_data': task_data,
            'cleanup_results': cleanup_results
        }

    except Exception as e:
        logger.error(f"CLEANUP_TASK: Failed to clean up workflow files: {e}")
        # Don't retry cleanup failures - log and move on
        return {
            'success': False,
            'task_data': task_data,
            'error': str(e)
        }
