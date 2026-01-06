"""
Asynchronous file processing tasks for handling large file uploads.
"""
import hashlib
import logging
import os
from pathlib import Path
from celery import shared_task
from depot.models import DataTableFile, UploadedFile
from depot.storage.phi_manager import PHIStorageManager
from depot.models import PHIFileTracking
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def process_uploaded_file_async(data_file_id, temp_file_path, nas_path, filename_with_version, user_id):
    """
    Process uploaded file asynchronously:
    1. Move file from temp to NAS
    2. Calculate file hash (optional)
    3. Update database records
    4. Clean up temp file

    Args:
        data_file_id: ID of DataTableFile
        temp_file_path: Path to temporary file
        nas_path: Target NAS path
        filename_with_version: Filename with version prefix
        user_id: ID of user who uploaded

    Returns:
        dict with data_file_id and next task parameters
    """
    try:
        logger.info(f"Starting async file processing for DataTableFile {data_file_id}")

        # Get objects
        data_file = DataTableFile.objects.get(id=data_file_id)
        uploaded_file_record = data_file.current_version
        submission = data_file.submission_data_table.submission
        file_type = data_file.submission_data_table.data_file_type.name

        # Import user model properly
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(id=user_id)

        # Step 1: Move file to NAS
        logger.info(f"Moving file from {temp_file_path} to NAS: {nas_path}")
        phi_manager = PHIStorageManager()

        # Move file to NAS
        with open(temp_file_path, 'rb') as f:
            from django.core.files.base import File
            saved_path = phi_manager.storage.save(nas_path, File(f))

        logger.info(f"File moved to NAS: {saved_path}")

        # Get absolute path for PHI tracking
        absolute_path = phi_manager.storage.get_absolute_path(saved_path)

        # Step 2: Calculate file hash (optional - do it streaming to be efficient)
        logger.info(f"Calculating hash for {temp_file_path}")
        file_hash = hashlib.sha256()
        with open(temp_file_path, 'rb') as f:
            while chunk := f.read(65536):  # Read in 64KB chunks
                file_hash.update(chunk)
        file_hash_str = file_hash.hexdigest()
        logger.info(f"Calculated hash: {file_hash_str[:16]}...")

        # Step 3: Update database records
        # Update UploadedFile record
        uploaded_file_record.file_hash = file_hash_str
        uploaded_file_record.storage_path = saved_path
        uploaded_file_record.save(update_fields=['file_hash', 'storage_path'])

        # Update DataTableFile record
        data_file.raw_file_path = saved_path
        data_file.save(update_fields=['raw_file_path'])

        # Create PHI tracking record
        PHIFileTracking.objects.create(
            cohort=submission.cohort,
            user=user,
            action='submission_file_uploaded',
            file_path=absolute_path,  # Use absolute path
            file_type='raw_csv' if filename_with_version.endswith('.csv') else 'raw_tsv',
            server_role=os.environ.get('SERVER_ROLE', 'unknown'),
            cleanup_required=False,  # Submission files should be kept
            bytes_transferred=Path(temp_file_path).stat().st_size,
            content_type=ContentType.objects.get_for_model(submission),
            object_id=submission.id,
            metadata={'relative_path': saved_path}  # Keep relative for reference
        )

        # Step 4: Clean up temp file and mark PHI tracking as cleaned
        logger.info(f"Cleaning up temp file {temp_file_path}")
        try:
            os.unlink(temp_file_path)
            # Also remove temp directory if empty
            temp_dir = Path(temp_file_path).parent
            if temp_dir.is_dir() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()

            # Mark PHI tracking as cleaned
            PHIFileTracking.objects.filter(
                file_path=str(temp_file_path),
                cleanup_required=True
            ).update(
                cleanup_completed=True,
                cleanup_completed_at=timezone.now()
            )
            logger.info(f"Marked PHI tracking as cleaned for {temp_file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file: {e}")

        logger.info(f"Async file processing complete for DataTableFile {data_file_id}")

        # Return data for next task in chain
        return {
            'data_file_id': data_file_id,
            'user_id': user_id,
            'nas_path': saved_path
        }

    except Exception as e:
        logger.error(f"Async file processing failed for DataTableFile {data_file_id}: {e}")

        # Try to clean up temp file on error
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        except:
            pass

        raise