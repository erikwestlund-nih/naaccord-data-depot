"""
Async storage tasks for handling large file operations on the services server.
"""
import os
import logging
from pathlib import Path
from celery import shared_task
from depot.storage.manager import StorageManager
from depot.models import PHIFileTracking
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_large_file_async(self, temp_path, storage_path, content_type, metadata):
    """
    Process large file upload asynchronously on services server.
    This runs ONLY on the services server, never on the web server.

    Args:
        temp_path: Path to temporary file containing upload
        storage_path: Target storage path
        content_type: MIME type
        metadata: File metadata dict

    Returns:
        Dict with final storage path and size
    """
    try:
        logger.info(f"Starting async storage processing for {storage_path}")

        # Get storage backend
        if storage_path.startswith('precheck_runs/'):
            storage = StorageManager.get_storage('uploads')
        elif storage_path.startswith('data/'):
            storage = StorageManager.get_storage('data')
        elif storage_path.startswith('downloads/'):
            storage = StorageManager.get_storage('downloads')
        else:
            storage = StorageManager.get_storage('uploads')

        # Get file size
        file_size = os.path.getsize(temp_path)
        logger.info(f"Processing {file_size / 1024 / 1024:.1f}MB file from {temp_path}")

        # Stream from temp file to final storage
        with open(temp_path, 'rb') as f:
            saved_path = storage.save(storage_path, f, content_type=content_type, metadata=metadata)

        logger.info(f"Successfully saved file to storage: {saved_path}")

        # Track in PHIFileTracking if it's PHI data
        if metadata and 'cohort_id' in metadata:
            try:
                PHIFileTracking.objects.create(
                    cohort_id=metadata['cohort_id'],
                    user_id=metadata.get('user_id'),
                    action='file_uploaded_async',
                    file_path=saved_path,
                    file_type=metadata.get('file_type', 'unknown'),
                    server_role='services',
                    bytes_transferred=file_size
                )
            except Exception as e:
                logger.error(f"Failed to track async file upload: {e}")

        # Clean up temp file
        try:
            os.unlink(temp_path)
            # Also remove temp directory if empty
            temp_dir = Path(temp_path).parent
            if temp_dir.is_dir() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
            logger.info(f"Cleaned up temp file: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_path}: {e}")

        return {
            'success': True,
            'path': saved_path,
            'size': file_size
        }

    except Exception as e:
        logger.error(f"Async storage processing failed: {e}")

        # Clean up temp file on error
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)