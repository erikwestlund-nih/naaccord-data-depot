"""
Patient ID Service

Centralized service for handling patient ID extraction and validation.
"""
import logging
from typing import Optional
from depot.models import DataTableFile
from depot.services.patient_id_extractor import PatientIDExtractor
from depot.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class PatientIDService:
    """Service for managing patient ID operations."""
    
    @staticmethod
    def process_patient_file(data_file: DataTableFile, user) -> Optional[object]:
        """
        Process a patient file for ID extraction.
        
        Handles both async (via Celery) and sync execution with automatic fallback.
        
        Args:
            data_file: The DataTableFile containing patient data
            user: User who uploaded the file
            
        Returns:
            PatientIDRecord if sync execution, None if async queued
        """
        try:
            from depot.tasks.patient_extraction import extract_patient_ids_task
            
            # Use AuditService's async/sync handler
            result = AuditService.handle_async_sync_task(
                async_func=extract_patient_ids_task.delay,
                sync_func=lambda file_id, user_id: PatientIDService._extract_sync(file_id, user_id),
                task_args=(data_file.id, user.id),
                task_name="patient ID extraction",
                object_id=data_file.id
            )
            
            if result:
                logger.info(f"Patient ID extraction completed for file {data_file.id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process patient file {data_file.id}: {e}")
            raise
    
    @staticmethod
    def _extract_sync(file_id: int, user_id: int):
        """
        Synchronous patient ID extraction with retry logic.

        Args:
            file_id: ID of the DataTableFile
            user_id: ID of the user

        Returns:
            PatientIDRecord or None
        """
        import time
        from django.contrib.auth import get_user_model

        User = get_user_model()
        max_retries = 3
        base_delay = 0.5  # Start with 500ms

        for attempt in range(max_retries):
            try:
                # Get fresh copies from database on each attempt
                data_file = DataTableFile.objects.get(id=file_id)
                user = User.objects.get(id=user_id)

                extractor = PatientIDExtractor()
                patient_record = extractor.extract_from_data_table_file(data_file, user)

                if patient_record:
                    logger.info(f"Extracted {patient_record.patient_count} patient IDs from file {file_id} on attempt {attempt + 1}")

                return patient_record

            except Exception as e:
                if attempt < max_retries - 1:
                    # Calculate exponential backoff delay
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Extraction attempt {attempt + 1} failed for file {file_id}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"All extraction attempts failed for file {file_id}: {e}")
                    return None
    
    @staticmethod
    def validate_patient_ids(submission, file_type: str, uploaded_ids: list) -> dict:
        """
        Validate uploaded IDs against the submission's patient list.
        
        Args:
            submission: CohortSubmission instance
            file_type: Type of file being validated
            uploaded_ids: List of IDs from the uploaded file
            
        Returns:
            Dictionary with validation results
        """
        if not submission.patient_ids:
            return {
                'valid': True,
                'missing_ids': [],
                'extra_ids': [],
                'message': 'No patient IDs to validate against'
            }
        
        patient_set = set(submission.patient_ids)
        uploaded_set = set(uploaded_ids)
        
        missing_ids = list(patient_set - uploaded_set)
        extra_ids = list(uploaded_set - patient_set)
        
        is_valid = len(missing_ids) == 0 and len(extra_ids) == 0
        
        message = 'All patient IDs match' if is_valid else f"{len(missing_ids)} missing, {len(extra_ids)} extra IDs"
        
        logger.info(f"Validated {file_type} file: {message}")
        
        return {
            'valid': is_valid,
            'missing_ids': missing_ids[:100],  # Limit to first 100
            'extra_ids': extra_ids[:100],
            'message': message,
            'total_missing': len(missing_ids),
            'total_extra': len(extra_ids)
        }