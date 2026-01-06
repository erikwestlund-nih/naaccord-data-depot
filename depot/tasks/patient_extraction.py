"""
Celery tasks for patient ID extraction and validation.
"""
import logging
from celery import shared_task
from django.db import transaction, connection
from depot.models import DataTableFile, CohortSubmission
from depot.services.patient_id_extractor import PatientIDExtractor

logger = logging.getLogger(__name__)


def ensure_db_connection():
    """Ensure database connection is active, reconnect if needed."""
    if connection.connection is not None:
        if connection.is_usable():
            return
        connection.close()
    # Force a new connection
    connection.ensure_connection()


@shared_task(bind=True, max_retries=3)
def extract_patient_ids_task(self, task_data):
    """
    Extract patient IDs from a data file asynchronously.

    Args:
        task_data: Data bundle dict from previous task

    """
    try:
        # Ensure fresh database connection at start of task
        ensure_db_connection()

        from depot.models import User

        # Extract data from bundle
        data_file_id = task_data['data_file_id']
        user_id = task_data['user_id']

        logger.info(f"PATIENT_EXTRACT_TASK: Starting patient ID extraction for file {data_file_id}")
        logger.info(f"PATIENT_EXTRACT_TASK: Task data keys: {list(task_data.keys())}")

        # Get the data file and user
        data_file = DataTableFile.objects.get(id=data_file_id)
        user = User.objects.get(id=user_id)

        # Check if this is a patient file
        is_patient_file = data_file.data_table.data_file_type.name.lower() == 'patient'

        extractor = PatientIDExtractor()
        submission = data_file.data_table.submission

        # Always extract patient IDs for every file
        from depot.models import DataTableFilePatientIDs

        # Extract patient IDs from the file (regardless of type)
        extracted_ids = extractor.extract_ids_from_data_file(data_file)

        # Store the extracted IDs in our new model with fresh connection
        # Ensure connection is fresh after potentially long DuckDB operations
        ensure_db_connection()
        with transaction.atomic():
            # Double-check connection health before database operations
            if not connection.is_usable():
                connection.close()
                connection.ensure_connection()

            file_patient_ids, created = DataTableFilePatientIDs.objects.get_or_create(
                data_file=data_file,
                defaults={
                    'patient_ids': [],
                    'patient_count': 0,
                    'invalid_count': 0,
                    'validation_status': 'pending',
                    'progress': 0
                }
            )

            if extracted_ids:
                file_patient_ids.extract_and_store_ids(extracted_ids)
                logger.info(f"Stored {len(extracted_ids)} patient IDs for {data_file.data_table.data_file_type.name} file {data_file_id}")

        patient_record = None

        if is_patient_file:
            # For patient files: Also create/update the submission-level patient record
            patient_record = extractor.extract_from_data_table_file(data_file, user)

            if patient_record:
                logger.info(f"Successfully extracted {patient_record.patient_count} patient IDs from patient file {data_file_id}")

                # Trigger validation of other files in the submission
                validate_submission_files_task.delay(submission.id, user.id)
            else:
                logger.warning(f"Patient ID extraction returned None for patient file {data_file_id}")
        else:
            # For non-patient files: Validate against existing patient IDs
            logger.info(f"Validating non-patient file {data_file_id} against patient IDs")

            from depot.models import SubmissionPatientIDs

            patient_record = SubmissionPatientIDs.objects.filter(
                submission=submission
            ).first()

            if patient_record and file_patient_ids.patient_ids:
                # Validate this file's patient IDs against the submission's patient IDs
                validation_result = file_patient_ids.validate_against_main(patient_record.patient_ids)
                logger.info(f"Validation result for {data_file.data_table.data_file_type.name}: {validation_result}")
            elif not patient_record:
                logger.warning(f"No patient record found for submission {submission.id} - cannot validate")

        # Return enhanced task_data for next step
        result = task_data.copy()
        result.update({
            'patient_count': patient_record.patient_count if patient_record else 0,
            'patient_extraction_completed': True,
            'extracted_ids_count': len(extracted_ids) if extracted_ids else 0
        })

        logger.info(f"PATIENT_EXTRACT_TASK: Successfully completed patient extraction for file {data_file_id}")
        logger.info(f"PATIENT_EXTRACT_TASK: Extracted {len(extracted_ids) if extracted_ids else 0} patient IDs")
        logger.info(f"PATIENT_EXTRACT_TASK: Returning result with keys: {list(result.keys())}")

        return result

    except DataTableFile.DoesNotExist:
        logger.error(f"PATIENT_EXTRACT_TASK: DataTableFile {data_file_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to extract patient IDs from file {data_file_id}: {e}")
        # Ensure fresh connection before retry
        try:
            ensure_db_connection()
        except:
            pass  # If connection fails, let the retry handle it
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def validate_submission_files_task(self, submission_id, user_id):
    """
    Validate all files in a submission against extracted patient IDs.
    
    Args:
        submission_id: ID of the CohortSubmission
        user_id: ID of the user who triggered validation
    """
    try:
        # Ensure fresh database connection at start of task
        ensure_db_connection()

        from depot.models import User, DataTableFile

        submission = CohortSubmission.objects.get(id=submission_id)
        user = User.objects.get(id=user_id)
        
        # Get all non-patient files in the submission
        data_files = DataTableFile.objects.filter(
            data_table__submission=submission,
            is_current=True
        ).exclude(
            data_table__data_file_type__name__iexact='patient'
        )
        
        extractor = PatientIDExtractor()
        
        for data_file in data_files:
            try:
                # Validate each file against patient IDs
                # This would need to be implemented to actually check the file's patient IDs
                logger.info(f"Validating file {data_file.id} against patient IDs")
                
                # For now, just log that we would validate
                # In production, this would extract IDs from the file and validate
                
            except Exception as e:
                logger.error(f"Failed to validate file {data_file.id}: {e}")
                
        return {
            'success': True,
            'submission_id': submission_id,
            'files_validated': data_files.count()
        }
        
    except CohortSubmission.DoesNotExist:
        logger.error(f"CohortSubmission {submission_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to validate submission {submission_id}: {e}")
        raise self.retry(exc=e, countdown=120)


@shared_task(bind=True, max_retries=3)
def extract_and_validate_patient_ids(self, task_data):
    """
    Enhanced task for extracting and validating patient IDs with progress tracking.
    Uses the new validation_status fields for comprehensive tracking.

    Args:
        task_data: Data bundle dict from previous task
    """
    logger.info(f"extract_and_validate_patient_ids called with task_data keys: {list(task_data.keys())}")

    # Extract data from bundle
    data_file_id = task_data['data_file_id']
    try:
        ensure_db_connection()

        from depot.models import DataTableFilePatientIDs, SubmissionPatientIDs

        data_file = DataTableFile.objects.get(id=data_file_id)
        submission = data_file.data_table.submission

        # Get or create the patient IDs record
        file_patient_ids, created = DataTableFilePatientIDs.objects.get_or_create(
            data_file=data_file,
            defaults={
                'patient_ids': [],
                'patient_count': 0,
                'invalid_count': 0,
                'validation_status': 'pending',
                'progress': 0
            }
        )

        # Update status to extracting
        file_patient_ids.validation_status = 'extracting'
        file_patient_ids.progress = 10
        file_patient_ids.save()

        logger.info(f"Starting enhanced extraction for file {data_file_id}")

        # Extract patient IDs using DuckDB
        extractor = PatientIDExtractor()
        extracted_ids = extractor.extract_ids_from_data_file(data_file)

        # Update progress
        file_patient_ids.progress = 50
        file_patient_ids.save()

        if not extracted_ids:
            file_patient_ids.validation_status = 'error'
            file_patient_ids.validation_error = 'No patient IDs found in file'
            file_patient_ids.progress = 100
            file_patient_ids.save()

            # Return error in task_data format
            result = task_data.copy()
            result.update({
                'patient_validation_completed': False,
                'validation_status': 'error',
                'validation_error': 'No patient IDs found'
            })
            return result

        # Store extracted IDs
        ensure_db_connection()
        with transaction.atomic():
            file_patient_ids.extract_and_store_ids(extracted_ids)

        # Update progress
        file_patient_ids.progress = 70
        file_patient_ids.validation_status = 'validating'
        file_patient_ids.save()

        # Get master patient list for validation
        patient_record = SubmissionPatientIDs.objects.filter(
            submission=submission
        ).first()

        if not patient_record:
            file_patient_ids.validation_status = 'error'
            file_patient_ids.validation_error = 'No master patient list found'
            file_patient_ids.progress = 100
            file_patient_ids.save()
            logger.warning(f"No patient record found for submission {submission.id}")

            # Return error in task_data format
            result = task_data.copy()
            result.update({
                'patient_validation_completed': False,
                'validation_status': 'error',
                'validation_error': 'No master patient list found'
            })
            return result

        # Validate against master list
        validation_result = file_patient_ids.validate_against_main(patient_record.patient_ids)

        # Update final status
        if validation_result['invalid'] > 0:
            file_patient_ids.validation_status = 'invalid'
            file_patient_ids.invalid_count = validation_result['invalid']

            # Generate validation report (don't block the chain)
            generate_validation_report.delay(data_file_id, validation_result)
        else:
            file_patient_ids.validation_status = 'valid'
            file_patient_ids.invalid_count = 0

        file_patient_ids.progress = 100
        file_patient_ids.validated = True
        file_patient_ids.save()

        logger.info(f"Validation complete for file {data_file_id}: {validation_result}")

        # Return enhanced task_data for next task in chain
        result = task_data.copy()
        result.update({
            'patient_validation_completed': True,
            'validation_status': file_patient_ids.validation_status
        })
        logger.info(f"extract_and_validate_patient_ids returning task_data with keys: {list(result.keys())}")
        return result

    except DataTableFile.DoesNotExist:
        logger.error(f"DataTableFile {data_file_id} not found")
        raise
    except Exception as e:
        logger.error(f"Failed to extract/validate file {data_file_id}: {e}")

        # Update status to error
        try:
            file_patient_ids = DataTableFilePatientIDs.objects.get(data_file_id=data_file_id)
            file_patient_ids.validation_status = 'error'
            file_patient_ids.validation_error = str(e)
            file_patient_ids.save()
        except:
            pass

        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=2)
def generate_validation_report(self, data_file_id, validation_result):
    """
    Generate a detailed validation report and upload to S3.

    Args:
        data_file_id: ID of the DataTableFile
        validation_result: Dict with validation results
    """
    try:
        ensure_db_connection()

        from depot.models import DataTableFilePatientIDs
        import csv
        import tempfile

        data_file = DataTableFile.objects.get(id=data_file_id)
        file_patient_ids = DataTableFilePatientIDs.objects.get(data_file=data_file)

        # Create CSV report
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['Patient ID', 'Status', 'Found In Master List'])

            # Write valid IDs
            for patient_id in file_patient_ids.valid_ids:
                writer.writerow([patient_id, 'Valid', 'Yes'])

            # Write invalid IDs
            for patient_id in file_patient_ids.invalid_ids:
                writer.writerow([patient_id, 'Invalid', 'No'])

            report_file = f.name

        # Note: S3/MinIO upload removed - validation reports are no longer uploaded to external storage
        logger.info(f"Validation report generated locally for file {data_file_id}")

        # Clean up temp file
        import os
        os.unlink(report_file)

        return {
            'success': True,
            'report_generated': True
        }

    except Exception as e:
        logger.error(f"Failed to generate validation report for file {data_file_id}: {e}")
        raise