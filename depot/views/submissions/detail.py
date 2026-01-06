from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Prefetch
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
import logging

from depot.models import (
    CohortSubmission,
    DataFileType,
    CohortSubmissionDataTable,
    FileAttachment,
    DataTableReview,
    PrecheckRun,
    Notebook,
    DataTableFilePatientIDs,
    SubmissionValidation,
)
from depot.permissions import SubmissionPermissions
from depot.data.table_config import (
    TABLE_ORDER, 
    get_table_display_name, 
    requires_patient_file,
    is_patient_table
)
from depot.utils.activity_logging import log_access_denied

logger = logging.getLogger(__name__)


@login_required
def submission_detail_page(request, submission_id):
    """
    Display detailed view of a submission with all files and their status.
    """
    submission = get_object_or_404(
        CohortSubmission.objects.select_related(
            'cohort', 'protocol_year', 'started_by', 'final_acknowledged_by'
        ),
        pk=submission_id
    )
    
    # Check permissions
    if not SubmissionPermissions.can_view(request.user, submission):
        logger.warning(
            f"Access denied: User {request.user.email} attempted to view submission {submission_id} "
            f"from cohort {submission.cohort.name} from IP {request.META.get('REMOTE_ADDR', 'unknown')}"
        )
        log_access_denied(
            request,
            'submission',
            submission_id,
            f"Submission {submission.id} for {submission.cohort.name}"
        )
        raise PermissionDenied("You don't have permission to view this submission.")
    
    # Get permission flags for template
    can_manage = SubmissionPermissions.can_manage(request.user, submission)
    can_edit = SubmissionPermissions.can_edit(request.user, submission)
    
    # Get all file types in configured order
    all_file_types = DataFileType.objects.filter(name__in=TABLE_ORDER)
    file_type_dict = {ft.name: ft for ft in all_file_types}
    
    # Order file types according to TABLE_ORDER
    ordered_file_types = []
    for name in TABLE_ORDER:
        if name in file_type_dict:
            ordered_file_types.append(file_type_dict[name])
    
    # Get existing data tables with review data
    data_tables = submission.data_tables.select_related(
        'data_file_type', 'signed_off_by', 'review'
    ).prefetch_related(
        'files'
    ).order_by('data_file_type__order', 'data_file_type__name')
    
    # Create a map of file type to data table
    table_map = {dt.data_file_type_id: dt for dt in data_tables}
    
    # Check if patient file exists
    patient_file_exists = submission.has_patient_file()
    patient_stats = submission.get_patient_stats() if patient_file_exists else None
    
    # Build the data tables list with all types and review info
    tables_display = []
    tables_with_issues = 0
    tables_reviewed = 0
    
    for file_type in ordered_file_types:
        data_table = table_map.get(file_type.id)
        if data_table:
            file_count = data_table.files.filter(is_current=True).count()
            status = data_table.get_status_display_text()
            
            # Get review info
            review = None
            has_audit = False
            notebook_id = None

            if data_table.has_review:
                review = data_table.review
                if review.has_validation_errors or review.has_validation_warnings:
                    tables_with_issues += 1
                if review.is_reviewed:
                    tables_reviewed += 1
            
            # Note: Submissions use ValidationRun for validation/notebook tracking
            # Not PrecheckRun (which is for standalone precheck validation)

            # Get patient ID validation info for non-patient tables
            patient_validation_info = None
            if not is_patient_table(file_type.name) and data_table:
                # Get validation info for all current files in this table
                validation_records = DataTableFilePatientIDs.objects.filter(
                    data_file__data_table=data_table,
                    data_file__is_current=True
                ).select_related('data_file')

                if validation_records.exists():
                    total_files = validation_records.count()
                    validated_files = validation_records.filter(validated=True).count()
                    valid_files = validation_records.filter(validation_status='valid').count()
                    invalid_files = validation_records.filter(validation_status='invalid').count()
                    error_files = validation_records.filter(validation_status='error').count()
                    pending_files = validation_records.filter(validation_status__in=['pending', 'extracting', 'validating']).count()

                    # Calculate overall validation status
                    if pending_files > 0:
                        overall_status = 'pending'
                    elif error_files > 0:
                        overall_status = 'error'
                    elif invalid_files > 0:
                        overall_status = 'invalid'
                    elif valid_files == total_files:
                        overall_status = 'valid'
                    else:
                        overall_status = 'partial'

                    patient_validation_info = {
                        'total_files': total_files,
                        'validated_files': validated_files,
                        'valid_files': valid_files,
                        'invalid_files': invalid_files,
                        'error_files': error_files,
                        'pending_files': pending_files,
                        'overall_status': overall_status,
                        'records': list(validation_records)
                    }
        else:
            file_count = 0
            status = 'Not Started'
            review = None
            has_audit = False
            notebook_id = None
            patient_validation_info = None

        # Determine if table is enabled (patient always enabled, others need patient file)
        is_patient = is_patient_table(file_type.name)
        enabled = is_patient or patient_file_exists

        tables_display.append({
            'file_type': file_type,
            'data_table': data_table,
            'is_patient': is_patient,
            'status': status,
            'file_count': file_count,
            'has_files': file_count > 0,
            'enabled': enabled,
            'display_name': get_table_display_name(file_type.name),
            'review': review,
            'has_audit': has_audit,
            'notebook_id': notebook_id,
            'patient_validation': patient_validation_info,
        })
    
    # Get recent activities
    recent_activities = submission.activities.select_related('user', 'file__data_table__data_file_type').order_by('-created_at')[:20]

    # Get submission attachments
    submission_attachments = FileAttachment.get_for_entity(submission)
    validation_summary, _ = SubmissionValidation.objects.get_or_create(submission=submission)
    
    # Calculate completion stats
    total_tables = len(all_file_types)
    tables_started = len([t for t in tables_display if t['has_files']])
    # Count only completed or signed off tables, not just tables with files
    tables_completed = len([t for t in tables_display 
                          if t['data_table'] and (
                              t['data_table'].status == 'completed' or 
                              t['data_table'].signed_off
                          )])
    tables_signed_off = submission.data_tables.filter(signed_off=True).count()
    
    # Handle POST requests for final sign-off
    if request.method == 'POST' and can_edit:
        if 'final_sign_off' in request.POST:
            # Check if all tables are ready
            if submission.status != 'signed_off':
                submission.final_comments = request.POST.get('final_comments', '')
                submission.mark_signed_off(request.user)
                messages.success(request, 'Submission has been signed off successfully.')
                return redirect('submission_detail', submission_id=submission.id)
    
    context = {
        'submission': submission,
        'tables_display': tables_display,
        'submission_attachments': submission_attachments,
        'recent_activities': recent_activities,
        'can_manage': can_manage,
        'can_edit': can_edit,
        'total_tables': total_tables,
        'tables_started': tables_started,
        'tables_completed': tables_completed,
        'tables_signed_off': tables_signed_off,
        'tables_reviewed': tables_reviewed,
        'tables_with_issues': tables_with_issues,
        'completion_percentage': (tables_reviewed / total_tables * 100) if total_tables > 0 else 0,
        'patient_file_exists': patient_file_exists,
        'patient_stats': patient_stats,
        'validation_summary': validation_summary,
    }
    
    return render(request, 'pages/submissions/detail.html', context)
