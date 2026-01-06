"""
File integrity tasks for HIPAA compliance.
Handles SHA256 hash calculation for uploaded files to satisfy integrity requirements.
"""
import hashlib
import logging
from pathlib import Path
from typing import Union

from celery import shared_task
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


@shared_task
def calculate_hashes_in_workflow(task_data):
    """
    Simple wrapper to calculate hashes as part of the workflow chain.
    Accepts task_data from previous task and passes it through.
    """
    logger.info(f"HASH_TASK: Starting hash calculation in workflow")
    logger.info(f"HASH_TASK: Task data keys: {list(task_data.keys()) if task_data else 'None'}")

    # Check if workflow should stop (file was rejected)
    if task_data and task_data.get('workflow_should_stop'):
        logger.info(f"HASH_TASK: Workflow stopped (file rejected), skipping hash calculation")
        return task_data

    # Extract file IDs from workflow info
    if task_data and isinstance(task_data, dict):
        data_file_id = task_data.get('data_file_id')

        logger.info(f"HASH_TASK: Processing file {data_file_id}")

        if data_file_id:
            # Get the uploaded file ID from the data table file
            from depot.models import DataTableFile
            try:
                data_file = DataTableFile.objects.get(id=data_file_id)
                uploaded_file_id = data_file.uploaded_file_id

                # Calculate both hashes synchronously within this task
                logger.info(f"Calculating hash for DataTableFile {data_file_id}")
                result1 = calculate_file_hash_task.apply(args=('DataTableFile', data_file_id))
                logger.info(f"Calculated hash for DataTableFile ID {data_file_id}: {result1.result.get('file_hash', 'N/A')[:16]}...")

                if uploaded_file_id:
                    logger.info(f"Calculating hash for UploadedFile {uploaded_file_id}")
                    result2 = calculate_file_hash_task.apply(args=('UploadedFile', uploaded_file_id))
                    logger.info(f"Updated hash for UploadedFile ID {uploaded_file_id}")

            except Exception as e:
                logger.error(f"HASH_TASK: Error in hash calculation wrapper: {e}")
        else:
            logger.warning(f"HASH_TASK: No data_file_id found in task_data")
    else:
        logger.warning(f"HASH_TASK: Invalid or None task_data received")

    logger.info(f"HASH_TASK: Successfully completed hash calculation")
    logger.info(f"HASH_TASK: Returning task_data with keys: {list(task_data.keys()) if task_data else 'None'}")

    # Pass through the task_data for next task
    return task_data


@shared_task(bind=True, max_retries=3)
def calculate_file_hash_task(self, model_type: str, file_id: int) -> dict:
    """
    Calculate SHA256 hash for an uploaded file and update the database record.

    Args:
        model_type: Either 'UploadedFile' or 'DataTableFile'
        file_id: Primary key of the file record

    Returns:
        dict: Result containing success status, hash value, and metadata

    Raises:
        ObjectDoesNotExist: If the file record doesn't exist
        FileNotFoundError: If the file doesn't exist in storage
        Exception: For other calculation errors (will retry)
    """
    try:
        # Get the appropriate model class
        if model_type == 'UploadedFile':
            model_class = apps.get_model('depot', 'UploadedFile')
        elif model_type == 'DataTableFile':
            model_class = apps.get_model('depot', 'DataTableFile')
        else:
            raise ValueError(f"Invalid model_type: {model_type}")

        # Get the file record
        try:
            file_record = model_class.objects.get(id=file_id)
        except ObjectDoesNotExist:
            logger.error(f"File record not found: {model_type} ID {file_id}")
            return {
                'success': False,
                'error': f'{model_type} with ID {file_id} not found',
                'file_id': file_id,
                'model_type': model_type
            }

        # Get storage path based on model type
        if model_type == 'UploadedFile':
            storage_path = file_record.storage_path
        elif model_type == 'DataTableFile':
            # DataTableFile uses raw_file_path for the actual CSV file
            storage_path = file_record.raw_file_path
        else:
            storage_path = None

        if not storage_path:
            logger.error(f"No storage path for {model_type} ID {file_id}")
            return {
                'success': False,
                'error': 'No storage path available',
                'file_id': file_id,
                'model_type': model_type
            }

        # Calculate hash
        try:
            file_hash = _calculate_sha256_hash(storage_path)
            logger.info(f"Calculated hash for {model_type} ID {file_id}: {file_hash[:16]}...")
        except FileNotFoundError:
            logger.error(f"File not found in storage: {storage_path}")
            return {
                'success': False,
                'error': f'File not found in storage: {storage_path}',
                'file_id': file_id,
                'model_type': model_type
            }
        except Exception as e:
            logger.error(f"Hash calculation failed for {model_type} ID {file_id}: {e}")
            # Retry on calculation errors
            raise self.retry(countdown=60, exc=e)

        # Update the database record
        try:
            file_record.file_hash = file_hash
            file_record.save(update_fields=['file_hash'])

            logger.info(f"Updated hash for {model_type} ID {file_id}")

            return {
                'success': True,
                'file_hash': file_hash,
                'file_id': file_id,
                'model_type': model_type,
                'storage_path': storage_path
            }

        except Exception as e:
            logger.error(f"Database update failed for {model_type} ID {file_id}: {e}")
            # Retry on database errors
            raise self.retry(countdown=60, exc=e)

    except Exception as e:
        if self.request.retries >= self.max_retries:
            logger.error(f"Max retries exceeded for hash calculation: {model_type} ID {file_id}, error: {e}")
            return {
                'success': False,
                'error': f'Max retries exceeded: {str(e)}',
                'file_id': file_id,
                'model_type': model_type
            }
        else:
            # Let Celery handle the retry
            raise


def _calculate_sha256_hash(storage_path: str) -> str:
    """
    Calculate SHA256 hash for a file in storage.

    Args:
        storage_path: Path to file in storage system

    Returns:
        str: SHA256 hash as hexadecimal string

    Raises:
        FileNotFoundError: If file doesn't exist in storage
        Exception: For other I/O or calculation errors
    """
    # Get appropriate storage system
    if storage_path.startswith('uploads/'):
        storage = StorageManager.get_storage('uploads')
        # Remove 'uploads/' prefix for storage operations
        storage_file_path = storage_path[8:]  # Remove 'uploads/' prefix
    elif storage_path.startswith('submissions/'):
        storage = StorageManager.get_submission_storage()
        storage_file_path = storage_path
    else:
        # Default to uploads storage for paths without prefix
        storage = StorageManager.get_storage('uploads')
        storage_file_path = storage_path

    # Check if file exists
    if not storage.exists(storage_file_path):
        raise FileNotFoundError(f"File not found in storage: {storage_path}")

    # Calculate hash by reading file in chunks
    sha256_hash = hashlib.sha256()

    try:
        # For different storage drivers, handle file reading appropriately
        if hasattr(storage, 'open'):
            # Local storage - use file handle
            with storage.open(storage_file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256_hash.update(chunk)
        elif hasattr(storage, 'get_file'):
            # Remote storage - get full content
            file_content = storage.get_file(storage_file_path)
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')
            sha256_hash.update(file_content)
        else:
            raise Exception(f"Unsupported storage driver for hash calculation: {type(storage)}")

        return sha256_hash.hexdigest()

    except Exception as e:
        logger.error(f"Error reading file for hash calculation: {storage_path}, error: {e}")
        raise


@shared_task
def migrate_pending_hashes(batch_size: int = 50) -> dict:
    """
    Migration task to calculate hashes for existing files with "pending_calculation" status.

    Args:
        batch_size: Number of files to process in each batch

    Returns:
        dict: Summary of migration results
    """
    from depot.models import UploadedFile, DataTableFile

    results = {
        'uploaded_files_processed': 0,
        'data_table_files_processed': 0,
        'successful_calculations': 0,
        'failed_calculations': 0,
        'errors': []
    }

    # Process UploadedFile records
    pending_uploaded_files = UploadedFile.objects.filter(
        file_hash__in=['pending_calculation', 'pending_async_calculation']
    )[:batch_size]

    for file_record in pending_uploaded_files:
        try:
            task_result = calculate_file_hash_task.delay('UploadedFile', file_record.id)
            results['uploaded_files_processed'] += 1
            logger.info(f"Queued hash calculation for UploadedFile {file_record.id}")
        except Exception as e:
            results['failed_calculations'] += 1
            results['errors'].append(f"UploadedFile {file_record.id}: {str(e)}")

    # Process DataTableFile records
    pending_data_files = DataTableFile.objects.filter(
        file_hash__in=['pending_calculation', 'pending_async_calculation']
    )[:batch_size]

    for file_record in pending_data_files:
        try:
            task_result = calculate_file_hash_task.delay('DataTableFile', file_record.id)
            results['data_table_files_processed'] += 1
            logger.info(f"Queued hash calculation for DataTableFile {file_record.id}")
        except Exception as e:
            results['failed_calculations'] += 1
            results['errors'].append(f"DataTableFile {file_record.id}: {str(e)}")

    logger.info(f"Migration batch complete: {results}")
    return results


@shared_task
def verify_file_integrity(model_type: str, file_id: int) -> dict:
    """
    Verify file integrity by recalculating hash and comparing with stored value.

    Args:
        model_type: Either 'UploadedFile' or 'DataTableFile'
        file_id: Primary key of the file record

    Returns:
        dict: Verification results including integrity status
    """
    try:
        # Get the appropriate model class
        if model_type == 'UploadedFile':
            model_class = apps.get_model('depot', 'UploadedFile')
        elif model_type == 'DataTableFile':
            model_class = apps.get_model('depot', 'DataTableFile')
        else:
            raise ValueError(f"Invalid model_type: {model_type}")

        # Get the file record
        file_record = model_class.objects.get(id=file_id)
        stored_hash = file_record.file_hash

        if not stored_hash or stored_hash in ['pending_calculation', 'pending_async_calculation']:
            return {
                'success': False,
                'error': 'No valid hash stored for verification',
                'file_id': file_id,
                'model_type': model_type
            }

        # Calculate current hash
        current_hash = _calculate_sha256_hash(file_record.storage_path)

        # Compare hashes
        integrity_valid = stored_hash == current_hash

        result = {
            'success': True,
            'integrity_valid': integrity_valid,
            'stored_hash': stored_hash,
            'calculated_hash': current_hash,
            'file_id': file_id,
            'model_type': model_type,
            'storage_path': file_record.storage_path
        }

        if not integrity_valid:
            logger.warning(f"Integrity verification failed for {model_type} ID {file_id}")
            # TODO: Could trigger security alert here
        else:
            logger.info(f"Integrity verified for {model_type} ID {file_id}")

        return result

    except Exception as e:
        logger.error(f"Integrity verification error for {model_type} ID {file_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'file_id': file_id,
            'model_type': model_type
        }