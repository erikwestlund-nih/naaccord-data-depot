import json
import os
import logging
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from depot.models import CohortSubmissionDataTable, DataTableReview, NotebookAccess, DataTableFile, FileAttachment, CohortSubmission
from depot.permissions import SubmissionPermissions

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def toggle_table_review(request, table_id):
    """
    Toggle the review status of a data table.
    """
    data_table = get_object_or_404(
        CohortSubmissionDataTable.objects.select_related('submission'),
        pk=table_id
    )
    
    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Parse request body
    try:
        body = json.loads(request.body)
        reviewed = body.get('reviewed', False)
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
    
    # Get or create review record
    review = data_table.get_or_create_review()
    
    # Update review status
    if reviewed:
        review.mark_reviewed(request.user)
    else:
        review.unmark_reviewed()
    
    return JsonResponse({
        'success': True,
        'reviewed': review.is_reviewed,
        'reviewed_by': review.reviewed_by.get_full_name() if review.reviewed_by else None,
        'reviewed_at': review.reviewed_at.isoformat() if review.reviewed_at else None
    })


@login_required
@require_http_methods(["POST"])
def save_table_comments(request, table_id):
    """
    Save comments for a data table review.
    """
    data_table = get_object_or_404(
        CohortSubmissionDataTable.objects.select_related('submission'),
        pk=table_id
    )
    
    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Parse request body
    try:
        body = json.loads(request.body)
        comments = body.get('comments', '')
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
    
    # Get or create review record
    review = data_table.get_or_create_review()
    
    # Update comments
    review.update_comments(comments, request.user)
    
    return JsonResponse({
        'success': True,
        'comments': review.comments,
        'updated_by': request.user.get_full_name(),
        'updated_at': review.comments_updated_at.isoformat() if review.comments_updated_at else None
    })


@login_required
@require_http_methods(["POST"])
def track_report_view(request, table_id):
    """
    Track that a user viewed a validation report.
    """
    data_table = get_object_or_404(
        CohortSubmissionDataTable.objects.select_related('submission'),
        pk=table_id
    )
    
    # Check permissions
    if not SubmissionPermissions.can_view(request.user, data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Get or create review record
    review = data_table.get_or_create_review()
    
    # Record the view
    review.record_report_view(request.user)
    
    # Also create NotebookAccess record if we have upload precheck/notebook info
    precheck_run_id = request.POST.get('precheck_run_id')
    if precheck_run_id:
        from depot.models import PrecheckRun, Notebook
        try:
            precheck_run = PrecheckRun.objects.get(pk=precheck_run_id)
            if hasattr(precheck_run, 'notebook'):
                NotebookAccess.objects.create(
                    user=request.user,
                    notebook=precheck_run.notebook,
                    data_table=data_table,
                    access_method='direct_view',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
        except PrecheckRun.DoesNotExist:
            pass
    
    return JsonResponse({
        'success': True,
        'view_count': review.validation_report_view_count,
        'first_viewed': review.validation_report_first_viewed_at.isoformat() if review.validation_report_first_viewed_at else None,
        'last_viewed': review.validation_report_last_viewed_at.isoformat() if review.validation_report_last_viewed_at else None
    })


@login_required
@require_http_methods(["GET"])
def get_table_review_status(request, table_id):
    """
    Get the current review status of a data table.
    """
    data_table = get_object_or_404(
        CohortSubmissionDataTable.objects.select_related('submission'),
        pk=table_id
    )
    
    # Check permissions
    if not SubmissionPermissions.can_view(request.user, data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Get review info if it exists
    if data_table.has_review:
        review = data_table.review
        return JsonResponse({
            'success': True,
            'has_review': True,
            'is_reviewed': review.is_reviewed,
            'reviewed_by': review.reviewed_by.get_full_name() if review.reviewed_by else None,
            'reviewed_at': review.reviewed_at.isoformat() if review.reviewed_at else None,
            'comments': review.comments,
            'report_viewed': review.validation_report_viewed,
            'view_count': review.validation_report_view_count,
            'has_errors': review.has_validation_errors,
            'has_warnings': review.has_validation_warnings
        })
    else:
        return JsonResponse({
            'success': True,
            'has_review': False,
            'is_reviewed': False,
            'comments': '',
            'report_viewed': False,
            'view_count': 0
        })


@login_required
@require_http_methods(["POST"])
def save_file_comments(request, file_id):
    """
    Save comments for an individual data table file.
    """
    file_obj = get_object_or_404(
        DataTableFile.objects.select_related('data_table__submission'),
        pk=file_id
    )

    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, file_obj.data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Parse request body
    try:
        body = json.loads(request.body)
        comments = body.get('comments', '')
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    # Update file comments
    file_obj.comments = comments
    file_obj.save()

    return JsonResponse({
        'success': True,
        'comments': file_obj.comments,
        'updated_by': request.user.get_full_name(),
        'file_id': file_obj.id
    })


@login_required
@require_http_methods(["POST"])
def save_file_name(request, file_id):
    """
    Save custom name for an individual data table file.
    """
    file_obj = get_object_or_404(
        DataTableFile.objects.select_related('data_table__submission'),
        pk=file_id
    )

    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, file_obj.data_table.submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Parse request body
    try:
        body = json.loads(request.body)
        name = body.get('name', '').strip()
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    # Update file name
    file_obj.name = name
    file_obj.save()

    return JsonResponse({
        'success': True,
        'name': file_obj.name,
        'updated_by': request.user.get_full_name(),
        'file_id': file_obj.id
    })


@login_required
@require_http_methods(["POST"])
def save_attachment_name(request, attachment_id):
    """
    Save custom name for a file attachment.
    """
    attachment = get_object_or_404(FileAttachment, pk=attachment_id)

    # Check permissions - need to check based on content_object type
    content_obj = attachment.content_object
    if hasattr(content_obj, 'submission'):
        submission = content_obj.submission
    elif hasattr(content_obj, 'data_table') and hasattr(content_obj.data_table, 'submission'):
        submission = content_obj.data_table.submission
    elif hasattr(content_obj, 'id') and content_obj.__class__.__name__ == 'CohortSubmission':
        submission = content_obj
    else:
        return JsonResponse({'success': False, 'error': 'Invalid attachment entity'}, status=400)

    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Parse request body
    try:
        body = json.loads(request.body)
        name = body.get('name', '').strip()
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    # Update attachment name
    attachment.name = name
    attachment.save()

    return JsonResponse({
        'success': True,
        'name': attachment.name,
        'updated_by': request.user.get_full_name(),
        'attachment_id': attachment.id
    })


@login_required
@require_http_methods(["POST"])
def save_attachment_comments(request, attachment_id):
    """
    Save comments for a file attachment.
    """
    attachment = get_object_or_404(FileAttachment, pk=attachment_id)

    # Check permissions - need to check based on content_object type
    content_obj = attachment.content_object
    if hasattr(content_obj, 'submission'):
        submission = content_obj.submission
    elif hasattr(content_obj, 'data_table') and hasattr(content_obj.data_table, 'submission'):
        submission = content_obj.data_table.submission
    elif hasattr(content_obj, 'id') and content_obj.__class__.__name__ == 'CohortSubmission':
        submission = content_obj
    else:
        return JsonResponse({'success': False, 'error': 'Invalid attachment entity'}, status=400)

    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Parse request body
    try:
        body = json.loads(request.body)
        comments = body.get('comments', '')
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    # Update attachment comments
    attachment.comments = comments
    attachment.save()

    return JsonResponse({
        'success': True,
        'comments': attachment.comments,
        'updated_by': request.user.get_full_name(),
        'attachment_id': attachment.id
    })


@login_required
@require_http_methods(["POST"])
def save_submission_final_comments(request, submission_id):
    """
    Save final sign-off comments for a submission.
    Auto-saves as user types before final sign-off.
    """
    submission = get_object_or_404(CohortSubmission, pk=submission_id)

    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Can't edit comments on signed-off submissions
    if submission.signed_off:
        return JsonResponse({'success': False, 'error': 'Cannot edit comments on signed-off submission'}, status=400)

    # Parse request body
    try:
        body = json.loads(request.body)
        comments = body.get('comments', '')
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    # Update final comments
    submission.final_comments = comments
    submission.save(update_fields=['final_comments'])

    return JsonResponse({
        'success': True,
        'comments': submission.final_comments,
        'updated_by': request.user.get_full_name()
    })


@login_required
@require_http_methods(["POST"])
def delete_attachment(request, attachment_id):
    """
    Delete a file attachment (soft delete).
    Works for attachments on both data tables and submissions.
    """
    attachment = get_object_or_404(FileAttachment, pk=attachment_id)

    # Check permissions - need to check based on content_object type
    content_obj = attachment.content_object
    if hasattr(content_obj, 'submission'):
        submission = content_obj.submission
    elif hasattr(content_obj, 'data_table') and hasattr(content_obj.data_table, 'submission'):
        submission = content_obj.data_table.submission
    elif hasattr(content_obj, 'id') and content_obj.__class__.__name__ == 'CohortSubmission':
        submission = content_obj
    else:
        return JsonResponse({'success': False, 'error': 'Invalid attachment entity'}, status=400)

    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # Soft delete the attachment
    try:
        # Mark the attachment as deleted
        attachment.deleted_at = timezone.now()
        attachment.save()

        # Also mark the associated uploaded file as deleted if it exists
        if attachment.uploaded_file:
            attachment.uploaded_file.deleted_at = timezone.now()
            attachment.uploaded_file.save()

        # Log PHI tracking for the deletion
        from depot.models import PHIFileTracking
        if attachment.uploaded_file and attachment.uploaded_file.storage_path:
            PHIFileTracking.objects.create(
                action='attachment_deleted',
                file_path=attachment.uploaded_file.storage_path,
                file_type='attachment',
                cohort=submission.cohort,
                user=request.user,
                file_size=attachment.uploaded_file.file_size or 0,
                server_role=os.environ.get('SERVER_ROLE', 'unknown'),
                cleanup_required=True
            )

        return JsonResponse({
            'success': True,
            'message': 'Attachment deleted successfully',
            'deleted_by': request.user.get_full_name(),
            'attachment_id': attachment.id
        })

    except Exception as e:
        logger.error(f"Error deleting attachment {attachment_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to delete attachment: {str(e)}'
        }, status=500)