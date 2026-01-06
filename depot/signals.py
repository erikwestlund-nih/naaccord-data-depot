"""
Django signals for NA-ACCORD depot application.
Handles patient file deletion cascade, validation triggers, and login activity logging.
"""
import logging
from django.db.models.signals import post_delete, post_save
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from depot.models import DataTableFile, SubmissionPatientIDs, DataTableFilePatientIDs

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Log all user login events for the activity feed.
    This catches any login regardless of authentication method (SAML, mock, etc).
    """
    try:
        from depot.models import Activity, ActivityType

        # Determine login method from request or session
        login_method = 'unknown'
        if hasattr(request, 'session'):
            if 'saml' in request.session.get('_auth_user_backend', '').lower():
                login_method = 'saml'
            elif 'mock' in request.session.get('_auth_user_backend', '').lower():
                login_method = 'mock_saml'
            else:
                login_method = 'django'

        # Clean up the path for display - don't show technical SAML URLs
        display_path = None
        if request and hasattr(request, 'path'):
            path = request.path
            if path == '/saml2/acs/':
                display_path = '/login'  # User-friendly display
            elif path.startswith('/saml2/'):
                display_path = '/login'  # Any SAML-related path
            else:
                display_path = path

        Activity.log_activity(
            user=user,
            activity_type=ActivityType.LOGIN,
            success=True,
            request=request,
            path=display_path,  # Override the technical path
            details={
                'login_method': login_method,
                'backend': request.session.get('_auth_user_backend', 'unknown'),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200] if request else None,
                'actual_path': request.path if request else None,  # Keep original for debugging
            }
        )
        logger.info(f"Logged login activity for user ID: {user.id}")

    except Exception as e:
        logger.error(f"Failed to log login activity: {e}")


@receiver(post_delete, sender=DataTableFile)
def handle_patient_file_deletion(sender, instance, **kwargs):
    """
    Handle deletion of patient files - clean up associated patient ID records.

    When a patient file is deleted, we need to:
    1. Clear the SubmissionPatientIDs record for the submission
    2. Mark all other DataTableFilePatientIDs in the submission as needing revalidation
    3. Clear patient_ids from the submission itself
    """
    # Check if this was a patient file
    if instance.data_table.data_file_type.name.lower() != 'patient':
        return

    submission = instance.data_table.submission
    logger.info(f"Patient file deleted for submission {submission.id}, cleaning up patient ID records")

    try:
        # Clear the master patient ID record
        if hasattr(submission, 'patient_ids_record'):
            submission.patient_ids_record.delete()
            logger.info(f"Deleted SubmissionPatientIDs record for submission {submission.id}")

        # Clear patient_ids from submission itself
        submission.patient_ids = []
        submission.patient_file_processed = False
        submission.save()

        # Mark all other file validation records as needing revalidation
        other_file_records = DataTableFilePatientIDs.objects.filter(
            data_file__data_table__submission=submission
        ).exclude(
            data_file__data_table__data_file_type__name__iexact='patient'
        )

        updated_count = other_file_records.update(
            validated=False,
            validation_status='pending',
            validation_date=None,
            validation_error='Patient file changed - revalidation required',
            invalid_count=0,
            progress=0,
            validation_report_url=''
        )

        logger.info(f"Marked {updated_count} file validation records for revalidation")

    except Exception as e:
        logger.error(f"Error cleaning up after patient file deletion: {e}")


@receiver(post_save, sender=DataTableFile)
def handle_file_upload(sender, instance, created, **kwargs):
    """
    Trigger validation when a new file is uploaded.
    """
    if not created:
        return

    # Skip validation for patient files - they become the source of truth
    if instance.data_table.data_file_type.name.lower() == 'patient':
        return

    # Check if submission has a patient file before validating
    if not instance.data_table.submission.has_patient_file():
        logger.warning(f"File {instance.id} uploaded but no patient file exists for submission")
        return

    # Import here to avoid circular imports
    from depot.tasks.patient_extraction import extract_and_validate_patient_ids

    # Trigger async validation
    logger.info(f"Triggering patient ID validation for file {instance.id}")
    extract_and_validate_patient_ids.delay(instance.id)