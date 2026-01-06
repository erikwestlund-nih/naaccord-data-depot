"""
Patient ID validation and file cleanup tasks.

Critical privacy requirement: Files with patient IDs not in the patient file
must be rejected and ALL files must be deleted, preserving only metadata.
"""
import logging
from typing import List, Dict, Any, Optional
from celery import shared_task
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import duckdb

from depot.storage.manager import StorageManager
from depot.models import PHIFileTracking, DataTableFile, CohortSubmissionDataTable

logger = logging.getLogger(__name__)

# MODULE-LEVEL LOGGING TO SEE IF FILE IS LOADED
logger.info("="*80)
logger.info("PATIENT_ID_VALIDATION MODULE LOADED!")
logger.info("="*80)


def find_invalid_patient_ids(submitted_file: str, patient_file: str) -> List[str]:
    """
    Use DuckDB to efficiently find patient IDs in submitted file
    that don't exist in patient file.

    Args:
        submitted_file: Path to DuckDB file being validated
        patient_file: Path to patient DuckDB file

    Returns:
        List of invalid patient IDs (sorted, distinct)
    """
    try:
        conn = duckdb.connect(':memory:')

        # Load both files - handle both DuckDB and Parquet formats
        if submitted_file.endswith('.duckdb'):
            # Attach DuckDB file and query it
            conn.execute(f"ATTACH '{submitted_file}' AS submitted_db")
            conn.execute("""
                CREATE TABLE submitted AS
                SELECT DISTINCT cohortPatientId
                FROM submitted_db.data
            """)
        else:
            # Read from Parquet
            conn.execute(f"""
                CREATE TABLE submitted AS
                SELECT DISTINCT cohortPatientId
                FROM read_parquet('{submitted_file}')
            """)

        if patient_file.endswith('.duckdb'):
            # Attach DuckDB file and query it
            conn.execute(f"ATTACH '{patient_file}' AS patient_db")
            conn.execute("""
                CREATE TABLE valid_patients AS
                SELECT DISTINCT cohortPatientId
                FROM patient_db.data
            """)
        else:
            # Read from Parquet
            conn.execute(f"""
                CREATE TABLE valid_patients AS
                SELECT DISTINCT cohortPatientId
                FROM read_parquet('{patient_file}')
            """)

        # Find IDs in submitted but NOT in patient file
        result = conn.execute("""
            SELECT s.cohortPatientId
            FROM submitted s
            LEFT JOIN valid_patients p ON s.cohortPatientId = p.cohortPatientId
            WHERE p.cohortPatientId IS NULL
            ORDER BY s.cohortPatientId
        """).fetchall()

        conn.close()

        return [row[0] for row in result]

    except Exception as e:
        logger.error(f"Error finding invalid patient IDs: {e}")
        raise


def build_rejection_message(invalid_ids: List[str]) -> str:
    """
    Build clear, actionable error message for rejected file.

    Args:
        invalid_ids: List of invalid patient IDs

    Returns:
        Formatted rejection message for user display
    """
    count = len(invalid_ids)
    sample_ids = invalid_ids[:10]  # Show first 10

    message = f"""
FILE REJECTED: Invalid Patient IDs Found

This file contains {count} patient ID(s) that do not exist in your patient file.

Privacy Policy: We cannot accept data for patients not enrolled in your cohort.

Invalid Patient IDs (showing first {min(10, count)}):
{', '.join(map(str, sample_ids))}

Action Required:
1. Verify these patient IDs against your patient file
2. Remove rows with invalid patient IDs OR
3. Add missing patients to your patient file first

Total invalid IDs: {count}
"""
    return message


def build_rejection_metadata(
    reason: str,
    message: str,
    invalid_ids: Optional[List[str]],
    filename: str,
    file_size: int,
    cohort_name: str,
    data_type: str
) -> Dict[str, Any]:
    """
    Build structured rejection metadata for database storage.

    Args:
        reason: Rejection reason code
        message: Human-readable rejection message
        invalid_ids: List of invalid patient IDs (if applicable)
        filename: Original filename
        file_size: File size in bytes
        cohort_name: Cohort name
        data_type: Data file type name

    Returns:
        Structured metadata dictionary
    """
    metadata = {
        'reason': reason,
        'message': message,
        'rejected_at': timezone.now().isoformat(),
        'file_metadata': {
            'filename': filename,
            'size': file_size,
            'cohort': cohort_name,
            'data_type': data_type
        }
    }

    if invalid_ids:
        metadata['invalid_ids'] = {
            'count': len(invalid_ids),
            'sample': invalid_ids[:20],  # First 20 IDs
            'total': len(invalid_ids)
        }

    return metadata


def cleanup_rejected_files(file_obj) -> List[str]:
    """
    Delete ALL files associated with a rejected upload.

    Args:
        file_obj: DataTableFile instance

    Returns:
        List of deleted file paths for audit trail
    """
    deleted_files = []

    # Find all PHI files associated with this file
    content_type = ContentType.objects.get_for_model(file_obj.__class__)
    phi_records = PHIFileTracking.objects.filter(
        content_type=content_type,
        object_id=file_obj.id
    )

    storage_manager = StorageManager()

    for record in phi_records:
        try:
            # Delete from storage
            if record.file_path and storage_manager.exists(record.file_path):
                storage_manager.delete(record.file_path)
                deleted_files.append(record.file_path)

                # Update PHI tracking
                record.cleanup_status = 'completed'
                record.cleaned_up_at = timezone.now()
                record.save()

        except Exception as e:
            # Log but don't fail - we want to try to delete everything
            logger.error(f"Failed to delete {record.file_path}: {e}")
            record.cleanup_status = 'failed'
            record.cleanup_error = str(e)
            record.save()

    # Mark file as cleaned up
    file_obj.files_cleaned_up = True
    file_obj.cleanup_verified_at = timezone.now()
    file_obj.save()

    # Log cleanup completion
    PHIFileTracking.log_operation(
        cohort=file_obj.data_table.submission.cohort,
        user=file_obj.uploaded_by,
        action='rejected_file_cleanup_completed',
        file_path=f"file_{file_obj.id}_cleanup",
        metadata={
            'deleted_file_count': len(deleted_files),
            'deleted_files': deleted_files
        }
    )

    return deleted_files


def get_patient_file_duckdb_path(data_file: DataTableFile) -> Optional[str]:
    """
    Get the patient file DuckDB path for validation.

    Args:
        data_file: DataTableFile being validated (non-patient file)

    Returns:
        Path to patient DuckDB file, or None if not found
    """
    from depot.models import DataFileType

    # Get the submission
    submission = data_file.data_table.submission

    # Find patient file type
    patient_type = DataFileType.objects.filter(name='patient').first()
    if not patient_type:
        logger.error("Patient file type not found in database")
        return None

    # Get patient data table
    patient_table = CohortSubmissionDataTable.objects.filter(
        submission=submission,
        data_file_type=patient_type
    ).first()

    if not patient_table:
        logger.warning(f"No patient table found for submission {submission.id}")
        return None

    # Get current patient file
    patient_file = DataTableFile.objects.filter(
        data_table=patient_table,
        is_current=True
    ).first()

    if not patient_file or not patient_file.duckdb_file_path:
        logger.warning(f"No patient DuckDB file found for submission {submission.id}")
        return None

    return patient_file.duckdb_file_path


@shared_task(bind=True, max_retries=0)  # No retries for validation failures
def validate_patient_ids_in_workflow(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate patient IDs in submitted file against patient file.
    Part of the upload workflow chain.

    This task runs AFTER DuckDB creation and patient ID extraction.
    If invalid patient IDs are found, the file is REJECTED and ALL files are DELETED.

    Args:
        task_data: Data bundle from previous workflow step

    Returns:
        Updated task_data for next workflow step (or rejection info)
    """
    logger.info("========================================")
    logger.info("PATIENT_ID_VALIDATION: TASK CALLED!")
    logger.info(f"PATIENT_ID_VALIDATION: task_data type: {type(task_data)}")
    logger.info(f"PATIENT_ID_VALIDATION: task_data: {task_data}")
    logger.info("========================================")
    try:
        logger.info("PATIENT_ID_VALIDATION: Starting patient ID validation in workflow")

        # Extract required data
        data_file_id = task_data.get('data_file_id')
        if not data_file_id:
            raise ValueError("data_file_id missing from task_data")

        # Get the data file
        data_file = DataTableFile.objects.get(id=data_file_id)
        file_type = data_file.data_table.data_file_type.name

        # Skip validation for patient files (they define the patient universe)
        if file_type == 'patient':
            logger.info("PATIENT_ID_VALIDATION: Skipping validation for patient file")
            task_data['patient_id_validation_status'] = 'skipped_patient_file'
            return task_data

        # Get DuckDB path for the submitted file
        submitted_duckdb_path = task_data.get('duckdb_path')
        if not submitted_duckdb_path:
            raise ValueError("duckdb_path missing from task_data")

        # Get patient file DuckDB path
        patient_duckdb_path = get_patient_file_duckdb_path(data_file)
        if not patient_duckdb_path:
            # No patient file exists - reject
            error_msg = "Cannot validate: No patient file found for this submission"
            logger.error(f"PATIENT_ID_VALIDATION: {error_msg}")

            # Handle rejection
            handle_rejection(
                data_file=data_file,
                reason='no_patient_file',
                message=error_msg,
                invalid_ids=None
            )

            # Return task_data with rejection flag
            task_data['patient_id_validation_status'] = 'rejected'
            task_data['rejection_reason'] = 'no_patient_file'
            task_data['rejection_message'] = error_msg
            task_data['workflow_should_stop'] = True
            return task_data

        logger.info(f"PATIENT_ID_VALIDATION: Comparing {submitted_duckdb_path} against {patient_duckdb_path}")

        # Find invalid patient IDs
        invalid_ids = find_invalid_patient_ids(
            submitted_file=submitted_duckdb_path,
            patient_file=patient_duckdb_path
        )

        if invalid_ids:
            # REJECT - Invalid patient IDs found
            count = len(invalid_ids)
            error_msg = f"Found {count} invalid patient ID(s) not in patient file"
            logger.warning(f"PATIENT_ID_VALIDATION: {error_msg}")

            # Handle rejection
            handle_rejection(
                data_file=data_file,
                reason='invalid_patient_ids',
                message=error_msg,
                invalid_ids=invalid_ids
            )

            # Return task_data with rejection flag
            task_data['patient_id_validation_status'] = 'rejected'
            task_data['rejection_reason'] = 'invalid_patient_ids'
            task_data['rejection_message'] = error_msg
            task_data['invalid_id_count'] = count
            task_data['workflow_should_stop'] = True
            return task_data

        # VALID - All patient IDs exist in patient file
        logger.info("PATIENT_ID_VALIDATION: All patient IDs are valid")
        task_data['patient_id_validation_status'] = 'passed'
        return task_data

    except Exception as e:
        logger.error(f"PATIENT_ID_VALIDATION: Validation error: {e}", exc_info=True)

        # On error, mark as failed but don't reject
        task_data['patient_id_validation_status'] = 'error'
        task_data['patient_id_validation_error'] = str(e)
        task_data['workflow_should_stop'] = True
        raise


def handle_rejection(
    data_file: DataTableFile,
    reason: str,
    message: str,
    invalid_ids: Optional[List[str]]
):
    """
    Handle file rejection: save metadata, cleanup files, update status.

    Args:
        data_file: DataTableFile being rejected
        reason: Rejection reason code
        message: Human-readable rejection message
        invalid_ids: List of invalid patient IDs (if applicable)
    """
    try:
        # Build rejection metadata
        metadata = build_rejection_metadata(
            reason=reason,
            message=message,
            invalid_ids=invalid_ids,
            filename=data_file.original_filename or 'unknown',
            file_size=data_file.file_size or 0,
            cohort_name=data_file.data_table.submission.cohort.name,
            data_type=data_file.data_table.data_file_type.name
        )

        # Save rejection details to database
        data_file.rejection_reason = message
        data_file.rejection_details = metadata
        data_file.rejected_at = timezone.now()
        data_file.save(update_fields=['rejection_reason', 'rejection_details', 'rejected_at'])

        # Update data table status to rejected
        data_table = data_file.data_table
        data_table.status = 'rejected'
        data_table.save(update_fields=['status'])

        # Delete all files
        deleted_files = cleanup_rejected_files(data_file)

        logger.info(f"REJECTION: File {data_file.id} rejected - {reason}. Deleted {len(deleted_files)} files.")

        # Build user-friendly rejection message
        rejection_message = build_rejection_message(invalid_ids) if invalid_ids else message

        # Log rejection in PHI tracking
        PHIFileTracking.log_operation(
            cohort=data_file.data_table.submission.cohort,
            user=data_file.uploaded_by,
            action='file_rejected_and_cleaned',
            file_path=f"file_{data_file.id}_rejected",
            metadata={
                'reason': reason,
                'message': rejection_message,
                'deleted_files_count': len(deleted_files),
                'invalid_id_count': len(invalid_ids) if invalid_ids else 0
            }
        )

    except Exception as e:
        logger.error(f"REJECTION: Error handling rejection for file {data_file.id}: {e}", exc_info=True)
        raise
