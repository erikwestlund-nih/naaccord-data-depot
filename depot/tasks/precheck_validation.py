"""
Precheck Validation Celery Tasks

Runs progressive validation with database status tracking.
"""
from celery import shared_task
import logging
from depot.models import PrecheckValidation
from depot.services.precheck_validation_service import PrecheckValidationService

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_precheck_validation(self, validation_id):
    """
    Run complete precheck validation workflow.

    Args:
        validation_id: UUID of PrecheckValidation record

    This task runs three validation stages:
    1. Metadata analysis (encoding, BOM, hash, size)
    2. CSV integrity checking (row-by-row column counts)
    3. Full validation (against data definition)

    Progress is stored in the database and can be polled via API.
    """
    try:
        logger.info(f"Starting precheck validation for validation_id: {validation_id}")

        # Verify validation record exists
        validation = PrecheckValidation.objects.get(id=validation_id)
        logger.info(
            f"Found precheck validation: {validation.id}, "
            f"file: {validation.original_filename}, "
            f"data_file_type: {validation.data_file_type.name}"
        )

        # Run complete validation workflow
        service = PrecheckValidationService(validation_id)
        service.run_complete_validation()

        logger.info(f"Precheck validation completed successfully: {validation_id}")

    except PrecheckValidation.DoesNotExist:
        logger.error(f"PrecheckValidation not found: {validation_id}")
        raise

    except Exception as e:
        logger.error(f"Precheck validation failed: {e}", exc_info=True)
        # Service handles error tracking in database
        raise
