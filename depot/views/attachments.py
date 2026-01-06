import logging
import json
import os
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie

from depot.models import (
    FileAttachment,
    CohortSubmissionDataTable,
    CohortSubmission,
    UploadedFile,
    UploadType,
    PHIFileTracking,
)
from depot.permissions import SubmissionPermissions
from depot.storage.manager import StorageManager
from depot.services.file_upload_service import FileUploadService
from depot.validators.file_security import validate_attachment_upload
import mimetypes

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
@ensure_csrf_cookie
def upload_attachment_secure(request, submission_id, table_name):
    """
    Secure attachment upload that streams through internal storage API.
    Creates PHI tracking records for audit trail compliance.
    """
    logger.info(f"=== SECURE UPLOAD CALLED: submission_id={submission_id}, table_name={table_name} ===")
    logger.info(f"SECURE POST data keys: {list(request.POST.keys())}")
    # Get the data table
    try:
        data_table = CohortSubmissionDataTable.objects.select_related(
            'submission__cohort',
            'submission__protocol_year',
            'data_file_type'
        ).get(
            submission_id=submission_id,
            data_file_type__name=table_name
        )
    except CohortSubmissionDataTable.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Data table not found'
        }, status=404)

    # Security check - can user edit this submission?
    if not SubmissionPermissions.can_edit(request.user, data_table.submission):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to upload attachments to this submission'
        }, status=403)

    # Check if submission is signed off
    if data_table.submission.signed_off:
        return JsonResponse({
            'success': False,
            'error': 'Cannot add attachments to a signed-off submission'
        }, status=400)

    # Get the uploaded file
    attachment_file = request.FILES.get('attachment')
    if not attachment_file:
        return JsonResponse({
            'success': False,
            'error': 'No file provided'
        }, status=400)

    # Get metadata
    attachment_name = request.POST.get('attachment_name', '')
    attachment_comments = request.POST.get('attachment_comments', '')

    # No file size limit
    # max_size = 100 * 1024 * 1024
    # if attachment_file.size > max_size:
    #     return JsonResponse({
    #         'success': False,
    #         'error': f'File size exceeds maximum of {max_size // (1024*1024)}MB'
    #     }, status=400)

    # Validate file type for attachments (PDF, Office docs, text, markdown, zips)
    try:
        validate_attachment_upload(attachment_file)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'File validation failed: {str(e)}'
        }, status=400)

    # Log the upload attempt
    logger.info(
        f"User {request.user.username} uploading attachment '{attachment_file.name}' "
        f"({attachment_file.size} bytes) to {data_table} via secure endpoint"
    )

    # Debug logging for metadata
    logger.info(f"SECURE metadata - name: '{attachment_name}', comments: '{attachment_comments}'")

    try:
        # Initialize services
        file_service = FileUploadService()

        # Calculate file hash before streaming
        file_hash = file_service.calculate_file_hash(attachment_file)

        # Create a placeholder UploadedFile record to get an attachment ID
        # We'll update it with the real storage path after upload succeeds
        placeholder_uploaded_file = file_service.create_uploaded_file_record(
            file=attachment_file,
            user=request.user,
            storage_path="placeholder",  # Will be updated
            file_hash=file_hash,
            upload_type=UploadType.OTHER
        )

        # Create FileAttachment record to get attachment ID for storage path
        temp_attachment = FileAttachment.objects.create(
            content_object=data_table,
            name=attachment_name or attachment_file.name,
            comments=attachment_comments,
            uploaded_by=request.user,
            uploaded_file=placeholder_uploaded_file
        )

        # Build storage path using attachment ID for directory-per-attachment approach
        storage_path = file_service.build_storage_path(
            cohort_id=data_table.submission.cohort.id,
            cohort_name=data_table.submission.cohort.name,
            protocol_year=str(data_table.submission.protocol_year.year),
            file_type=data_table.data_file_type.name,
            filename=attachment_file.name,
            is_attachment=True,
            attachment_id=temp_attachment.id
        )

        # Check if we're in web server mode (need to use internal API)
        server_role = os.environ.get('SERVER_ROLE', 'web')

        if server_role == 'web':
            # Stream to internal storage API on services server
            api_key = os.environ.get('INTERNAL_API_KEY')
            if not api_key:
                logger.error("INTERNAL_API_KEY not configured for secure upload")
                return JsonResponse({
                    'success': False,
                    'error': 'Server configuration error'
                }, status=500)

            # Prepare metadata for PHI tracking
            metadata = {
                'cohort_id': data_table.submission.cohort.id,
                'user_id': request.user.id,
                'file_type': 'attachment',
                'submission_id': submission_id,
                'table_name': table_name,
                'cleanup_required': False,  # Attachments are permanent
                'file_hash': file_hash
            }

            # Stream to internal storage
            services_url = os.environ.get('SERVICES_URL', 'http://localhost:8001')

            # Reset file pointer for streaming
            attachment_file.seek(0)

            response = requests.post(
                f"{services_url}/internal/storage/upload",
                files={'file': (attachment_file.name, attachment_file, attachment_file.content_type or 'application/octet-stream')},
                data={
                    'path': storage_path,
                    'disk': 'attachments',  # Explicitly use attachments storage
                    'content_type': attachment_file.content_type or 'application/octet-stream',
                    'metadata': json.dumps(metadata)
                },
                headers={'X-API-Key': api_key}
            )

            if response.status_code != 200:
                logger.error(f"Internal storage API error: {response.status_code} - {response.text}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to upload file to storage'
                }, status=500)

            storage_result = response.json()
            saved_path = storage_result.get('path', storage_path)

        else:
            # Services server - save directly to attachments storage
            storage = StorageManager.get_storage('attachments')
            saved_path = storage.save(
                path=storage_path,
                content=attachment_file,
                content_type=attachment_file.content_type or 'application/octet-stream',
            )

        # Create PHI tracking record
        PHIFileTracking.objects.create(
            cohort=data_table.submission.cohort,
            user=request.user,
            action='attachment_uploaded',
            file_path=saved_path,
            file_type='attachment',
            file_size=attachment_file.size,
            server_role=server_role,
            cleanup_required=False,  # Attachments are permanent
            purpose_subdirectory=f"submissions/{submission_id}/attachments"
        )

        # Update the placeholder UploadedFile record with the real storage path
        placeholder_uploaded_file.storage_path = saved_path
        placeholder_uploaded_file.save()
        attachment = temp_attachment

        # Log successful upload
        logger.info(
            f"Successfully uploaded attachment {attachment.id} for {data_table} with PHI tracking"
        )

        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Attachment uploaded successfully',
            'attachment': {
                'id': attachment.id,
                'name': attachment.name,
                'size': placeholder_uploaded_file.file_size,
                'uploaded_by': request.user.get_full_name() or request.user.username,
                'uploaded_at': attachment.created_at.isoformat(),
            }
        })

    except Exception as e:
        # Clean up placeholder records if upload failed
        try:
            if 'temp_attachment' in locals():
                temp_attachment.delete()
            if 'placeholder_uploaded_file' in locals():
                placeholder_uploaded_file.delete()
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup placeholder records: {cleanup_error}")

        error_msg = f"Failed to upload attachment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=500)


@login_required
@require_http_methods(["POST"])
@ensure_csrf_cookie
def upload_attachment(request, submission_id, table_name):
    print(f"*** UPLOAD_ATTACHMENT CALLED WITH POST KEYS: {list(request.POST.keys())} ***")
    print(f"*** POST VALUES: name='{request.POST.get('attachment_name', '')}', comments='{request.POST.get('attachment_comments', '')}' ***")
    """
    Dedicated endpoint for attachment uploads.
    Accepts all file types and handles security through permissions.
    """
    # Get the data table
    try:
        data_table = CohortSubmissionDataTable.objects.select_related(
            'submission__cohort', 
            'submission__protocol_year',
            'data_file_type'
        ).get(
            submission_id=submission_id,
            data_file_type__name=table_name
        )
    except CohortSubmissionDataTable.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'error': 'Data table not found'
        }, status=404)
    
    # Security check - can user edit this submission?
    if not SubmissionPermissions.can_edit(request.user, data_table.submission):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to upload attachments to this submission'
        }, status=403)
    
    # Check if submission is signed off
    if data_table.submission.signed_off:
        return JsonResponse({
            'success': False,
            'error': 'Cannot add attachments to a signed-off submission'
        }, status=400)
    
    # Get the uploaded file
    attachment_file = request.FILES.get('attachment')
    if not attachment_file:
        return JsonResponse({
            'success': False,
            'error': 'No file provided'
        }, status=400)
    
    # Get metadata
    attachment_name = request.POST.get('attachment_name', '')
    attachment_comments = request.POST.get('attachment_comments', '')

    # Debug logging
    logger.info(f"Attachment upload debug - name: '{attachment_name}', comments: '{attachment_comments}'")
    logger.info(f"POST data keys: {list(request.POST.keys())}")

    # Validate file type for attachments (PDF, Office docs, text, markdown, zips)
    try:
        validate_attachment_upload(attachment_file)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'File validation failed: {str(e)}'
        }, status=400)

    # No file size limit for attachments - accept all sizes

    # Log the upload attempt
    logger.info(
        f"User {request.user.username} uploading attachment '{attachment_file.name}' "
        f"({attachment_file.size} bytes) to {data_table}"
    )
    
    try:
        # Initialize services
        file_service = FileUploadService()
        storage = StorageManager.get_storage('attachments')
        
        from django.db import transaction

        with transaction.atomic():
            # Calculate file hash
            file_hash = file_service.calculate_file_hash(attachment_file)

            # First, create a temporary UploadedFile record to get the FileAttachment ID
            # We'll update the path after we know the attachment ID
            temp_uploaded_file = file_service.create_uploaded_file_record(
                file=attachment_file,
                user=request.user,
                storage_path="temp_path",  # Temporary placeholder
                file_hash=file_hash,
                upload_type=UploadType.OTHER
            )

            # Create FileAttachment record to get the ID
            attachment = FileAttachment.create_for_entity(
                entity=data_table,
                uploaded_file=temp_uploaded_file,
                user=request.user,
                name=attachment_name or attachment_file.name,
                comments=attachment_comments
            )

            # Now build the proper storage path with attachment ID
            storage_path = file_service.build_storage_path(
                cohort_id=data_table.submission.cohort.id,
                cohort_name=data_table.submission.cohort.name,
                protocol_year=str(data_table.submission.protocol_year.year),
                file_type=data_table.data_file_type.name,
                filename=attachment_file.name,
                is_attachment=True,
                attachment_id=attachment.id
            )

            # Save to storage with the proper path
            saved_path = storage.save(
                path=storage_path,
                content=attachment_file,
                content_type=attachment_file.content_type or 'application/octet-stream',
            )

            # Update the UploadedFile record with the correct path
            temp_uploaded_file.storage_path = saved_path
            temp_uploaded_file.save()
        
        # Log successful upload
        logger.info(
            f"Successfully uploaded attachment {attachment.id} for {data_table}"
        )

        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Attachment uploaded successfully',
            'attachment': {
                'id': attachment.id,
                'name': attachment.name,
                'size': temp_uploaded_file.file_size,
                'uploaded_by': request.user.get_full_name() or request.user.username,
                'uploaded_at': attachment.created_at.isoformat(),
            }
        })
        
    except Exception as e:
        error_msg = f"Failed to upload attachment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=500)


@login_required
def download_attachment(request, attachment_id):
    """Download a file attachment."""
    attachment = get_object_or_404(FileAttachment, pk=attachment_id)
    
    # Check permission - attachment is linked to a CohortSubmissionDataTable
    if attachment.content_object and hasattr(attachment.content_object, 'submission'):
        submission = attachment.content_object.submission
        if not SubmissionPermissions.can_view(request.user, submission):
            return HttpResponseForbidden("You don't have permission to download this attachment.")
    
    # Get the file from attachments storage
    storage = StorageManager.get_storage('attachments')
    
    if not attachment.uploaded_file or not attachment.uploaded_file.storage_path:
        raise Http404("Attachment file not found")
    
    try:
        file_content = storage.open(attachment.uploaded_file.storage_path)
    except Exception as e:
        raise Http404(f"Failed to retrieve attachment: {str(e)}")
    
    # Determine content type
    content_type = attachment.file_type or 'application/octet-stream'
    if not content_type or content_type == 'application/octet-stream':
        content_type, _ = mimetypes.guess_type(attachment.uploaded_file.original_filename)
        content_type = content_type or 'application/octet-stream'
    
    # Create response
    response = HttpResponse(file_content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{attachment.get_display_name()}"'
    
    if attachment.file_size:
        response['Content-Length'] = attachment.file_size
    
    return response


@login_required
@require_http_methods(["POST"])
@ensure_csrf_cookie
def upload_submission_attachment_secure(request, submission_id):
    """
    Secure attachment upload for submission-level attachments.
    Streams through internal storage API and creates PHI tracking records for audit trail compliance.
    """
    # Get the submission
    try:
        submission = CohortSubmission.objects.select_related(
            'cohort', 'protocol_year'
        ).get(pk=submission_id)
    except CohortSubmission.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Submission not found'
        }, status=404)

    # Security check - can user edit this submission?
    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({
            'success': False,
            'error': 'You do not have permission to upload attachments to this submission'
        }, status=403)

    # Check if submission is signed off
    if submission.signed_off:
        return JsonResponse({
            'success': False,
            'error': 'Cannot add attachments to a signed-off submission'
        }, status=400)

    # Get the uploaded file
    attachment_file = request.FILES.get('attachment')
    if not attachment_file:
        return JsonResponse({
            'success': False,
            'error': 'No file provided'
        }, status=400)

    # Get metadata
    attachment_name = request.POST.get('attachment_name', '')
    attachment_comments = request.POST.get('attachment_comments', '')

    # No file size limit
    # max_size = 100 * 1024 * 1024
    # if attachment_file.size > max_size:
    #     return JsonResponse({
    #         'success': False,
    #         'error': f'File size exceeds maximum of {max_size // (1024*1024)}MB'
    #     }, status=400)

    # Validate file type for attachments (PDF, Office docs, text, markdown, zips)
    try:
        validate_attachment_upload(attachment_file)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'File validation failed: {str(e)}'
        }, status=400)

    # Log the upload attempt
    logger.info(
        f"User {request.user.username} uploading submission attachment '{attachment_file.name}' "
        f"({attachment_file.size} bytes) to submission {submission.id} via secure endpoint"
    )

    try:
        # Initialize services
        file_service = FileUploadService()

        # Calculate file hash before streaming
        file_hash = file_service.calculate_file_hash(attachment_file)

        # Build storage path for submission attachment
        # Note: Pass empty file_type since is_attachment=True will add 'attachments' subdirectory
        storage_path = file_service.build_storage_path(
            cohort_id=submission.cohort.id,
            cohort_name=submission.cohort.name,
            protocol_year=str(submission.protocol_year.year),
            file_type='',  # Empty - 'attachments' will be added by is_attachment=True
            filename=attachment_file.name,
            is_attachment=True
        )

        # Check if we're in web server mode (need to use internal API)
        server_role = os.environ.get('SERVER_ROLE', 'web')

        if server_role == 'web':
            # Stream to internal storage API on services server
            api_key = os.environ.get('INTERNAL_API_KEY')
            if not api_key:
                logger.error("INTERNAL_API_KEY not configured for secure upload")
                return JsonResponse({
                    'success': False,
                    'error': 'Server configuration error'
                }, status=500)

            # Prepare metadata for PHI tracking
            metadata = {
                'cohort_id': submission.cohort.id,
                'user_id': request.user.id,
                'file_type': 'submission_attachment',
                'submission_id': submission_id,
                'cleanup_required': False,  # Attachments are permanent
                'file_hash': file_hash
            }

            # Stream to internal storage
            services_url = os.environ.get('SERVICES_URL', 'http://localhost:8001')

            # Reset file pointer for streaming
            attachment_file.seek(0)

            response = requests.post(
                f"{services_url}/internal/storage/upload",
                files={'file': (attachment_file.name, attachment_file, attachment_file.content_type or 'application/octet-stream')},
                data={
                    'path': storage_path,
                    'disk': 'attachments',  # Explicitly use attachments storage
                    'content_type': attachment_file.content_type or 'application/octet-stream',
                    'metadata': json.dumps(metadata)
                },
                headers={'X-API-Key': api_key}
            )

            if response.status_code != 200:
                logger.error(f"Internal storage API error: {response.status_code} - {response.text}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to upload file to storage'
                }, status=500)

            storage_result = response.json()
            saved_path = storage_result.get('path', storage_path)

        else:
            # Services server - save directly to attachments storage
            storage = StorageManager.get_storage('attachments')
            saved_path = storage.save(
                path=storage_path,
                content=attachment_file,
                content_type=attachment_file.content_type or 'application/octet-stream',
            )

        # Create PHI tracking record
        PHIFileTracking.objects.create(
            cohort=submission.cohort,
            user=request.user,
            action='submission_attachment_uploaded',
            file_path=saved_path,
            file_type='submission_attachment',
            file_size=attachment_file.size,
            server_role=server_role,
            cleanup_required=False,  # Attachments are permanent
            purpose_subdirectory=f"submissions/{submission_id}/attachments"
        )

        # Create UploadedFile record
        uploaded_file_record = file_service.create_uploaded_file_record(
            file=attachment_file,
            user=request.user,
            storage_path=saved_path,
            file_hash=file_hash,
            upload_type=UploadType.OTHER
        )

        # Create FileAttachment for submission
        attachment = FileAttachment.create_for_entity(
            entity=submission,
            uploaded_file=uploaded_file_record,
            user=request.user,
            name=attachment_name or attachment_file.name,
            comments=attachment_comments
        )

        # Log successful upload
        logger.info(
            f"Successfully uploaded submission attachment {attachment.id} for submission {submission.id} with PHI tracking"
        )

        # Return success response
        return JsonResponse({
            'success': True,
            'message': 'Attachment uploaded successfully',
            'attachment': {
                'id': attachment.id,
                'name': attachment.name,
                'size': uploaded_file_record.file_size,
                'uploaded_by': request.user.get_full_name() or request.user.username,
                'uploaded_at': attachment.created_at.isoformat(),
            }
        })

    except Exception as e:
        error_msg = f"Failed to upload submission attachment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=500)


@login_required
@require_http_methods(["POST"])
def remove_attachment(request, attachment_id):
    """Remove an attachment (mark as deleted, don't actually delete file)."""
    logger.info(f"=== REMOVE ATTACHMENT CALLED: attachment_id={attachment_id} ===")
    attachment = get_object_or_404(FileAttachment, pk=attachment_id)
    logger.info(f"Found attachment: {attachment.id}, name: {attachment.name}")

    # Check permission
    if attachment.content_object and hasattr(attachment.content_object, 'submission'):
        submission = attachment.content_object.submission
        if not SubmissionPermissions.can_edit(request.user, submission):
            return JsonResponse({
                'success': False,
                'error': "You don't have permission to remove this attachment."
            }, status=403)

    try:
        attachment_name = attachment.name
        uploaded_file = attachment.uploaded_file

        # Delete the actual file from storage using PHIStorageManager
        from depot.storage.phi_manager import PHIStorageManager
        phi_manager = PHIStorageManager()

        try:
            logger.info(f"Attempting to delete file from storage: {uploaded_file.storage_path}")
            phi_manager.delete_from_nas(
                nas_path=uploaded_file.storage_path,
                cohort=attachment.content_object.submission.cohort if hasattr(attachment.content_object, 'submission') else None,
                user=request.user,
                file_type='attachment'
            )
            logger.info(f"Successfully deleted file from storage: {uploaded_file.storage_path}")

            # Also remove the containing directory (attachments are stored in individual directories)
            import os
            directory_path = os.path.dirname(uploaded_file.storage_path)
            try:
                logger.info(f"Attempting to delete containing directory: {directory_path}")
                phi_manager.delete_directory_from_nas(
                    nas_path=directory_path,
                    cohort=attachment.content_object.submission.cohort if hasattr(attachment.content_object, 'submission') else None,
                    user=request.user,
                    file_type='attachment'
                )
                logger.info(f"Successfully deleted directory from storage: {directory_path}")
            except Exception as dir_error:
                logger.error(f"Failed to delete directory from storage {directory_path}: {dir_error}", exc_info=True)

        except Exception as storage_error:
            logger.error(f"Failed to delete file from storage {uploaded_file.storage_path}: {storage_error}", exc_info=True)

        # Soft delete the UploadedFile record (marks with deleted_at timestamp)
        uploaded_file.delete()
        logger.info(f"Soft deleted UploadedFile record {uploaded_file.id} with deleted_at timestamp")

        # Soft delete the attachment record
        attachment.delete()
        logger.info(f"Soft deleted FileAttachment record {attachment.id} with deleted_at timestamp")

        logger.info(f"User_id {request.user.id} removed attachment {attachment_id}")

        return JsonResponse({
            'success': True,
            'message': f'Attachment "{attachment_name}" removed successfully'
        })
    except Exception as e:
        logger.error(f"Failed to remove attachment {attachment_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)