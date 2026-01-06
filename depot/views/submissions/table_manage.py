from django.contrib.auth.decorators import login_required
from depot.decorators import submission_view_required, ajax_login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse, Http404
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.db.models import Prefetch
from django.utils import timezone

from depot.models import (
    CohortSubmission,
    CohortSubmissionDataTable,
    DataTableFile,
    DataFileType,
    SubmissionActivity,
    UploadedFile,
    UploadType,
    FileAttachment,
    SubmissionPatientIDs,
    ValidationRun,
    ValidationVariable,
)
from depot.permissions import SubmissionPermissions
from depot.data.table_config import get_table_display_name
from depot.storage.manager import StorageManager
from depot.services.file_upload_service import FileUploadService
from depot.services.activity_logger import SubmissionActivityLogger
from depot.services.submission_validation_service import SubmissionValidationService
from depot.tasks.validation_orchestration import (
    revalidate_single_variable,
    ensure_validation_run_for_data_file,
)


def schedule_submission_file_workflow(submission, data_table, data_file, user):
    """Schedule the async workflow (duckdb → extraction → validation) for a data file."""
    from celery import chain
    from depot.tasks import (
        create_duckdb_task,
        extract_patient_ids_task,
        cleanup_workflow_files_task,
        start_validation_for_data_file,
    )
    from depot.tasks.file_integrity import calculate_hashes_in_workflow
    from depot.tasks.upload_precheck import process_precheck_run_with_duckdb

    task_data = {
        'data_file_id': data_file.id,
        'user_id': user.id,
        'submission_id': submission.id,
        'cohort_id': submission.cohort.id,
        'file_type_name': data_table.data_file_type.name,
        'raw_file_path': data_file.raw_file_path,
    }

    # Build workflow steps for granular validation system
    # Note: No longer using legacy Quarto notebook compilation (process_precheck_run_with_duckdb)
    workflow_steps = [
        create_duckdb_task.si(task_data),
        extract_patient_ids_task.s(),
        calculate_hashes_in_workflow.s(),
        start_validation_for_data_file.s(),
        cleanup_workflow_files_task.s(),
    ]

    chain(*workflow_steps).apply_async(countdown=2)

import hashlib
import os
import json
import logging
import csv
import io
from django.conf import settings

logger = logging.getLogger(__name__)


def handle_post_request(request, submission, data_table, is_patient_table, patient_file_exists, can_edit):
    """Route POST requests to appropriate handlers."""
    
    # Debug logging to see what's in the request
    logger.info(f"POST request - FILES keys: {list(request.FILES.keys())}, POST keys: {list(request.POST.keys())[:10]}")
    logger.info(f"X-Requested-With header: {request.headers.get('X-Requested-With')}")
    
    # PRIORITIZE attachment uploads - check this FIRST
    if 'attachment' in request.FILES and can_edit:
        logger.info(f"Routing to attachment upload handler for file: {request.FILES.get('attachment').name}")
        return handle_attachment_upload(request, data_table)
    
    # Also check for attachment by form field names (in case FILES check fails)
    if can_edit and ('attachment_name' in request.POST or 'attachment_comments' in request.POST):
        logger.info("Detected attachment upload by POST fields")
        return handle_attachment_upload(request, data_table)
    
    # Handle AJAX requests  
    # Check both X-Requested-With header AND that it's NOT an attachment
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Make sure it's not an attachment that somehow got here
        if 'attachment' not in request.FILES:
            # Check if this is a file action (update/remove)
            if 'action' in request.POST and can_edit:
                return handle_file_actions(request, data_table)
            # Otherwise it's a file upload
            return handle_ajax_file_upload(request, submission, data_table, is_patient_table, patient_file_exists)
    
    # Handle marking as not collected/not available
    if ('save_not_available' in request.POST or 'mark_not_collected' in request.POST) and can_edit:
        return handle_mark_not_available(request, data_table)
    
    # Sign-off is now handled at the submission level, not individual tables
    # if 'sign_off' in request.POST and can_edit:
    #     return handle_table_sign_off(request, data_table)
    
    # Handle file management actions (add/remove files)
    if 'action' in request.POST and can_edit:
        return handle_file_actions(request, data_table)
    
    # If nothing matched, redirect back
    return redirect('submission_table_manage', 
                   submission_id=submission.id,
                   table_name=data_table.data_file_type.name)


def build_table_context(submission, data_table, file_type, current_files, attachments,
                        can_edit, is_patient_table, patient_file_exists, can_toggle_review=None):
    """Build context dictionary for template rendering."""
    # Default can_toggle_review to can_edit if not provided
    if can_toggle_review is None:
        can_toggle_review = can_edit
    logger.info(f"==== BUILD_TABLE_CONTEXT CALLED for {file_type.name} ====")

    # Import models needed for patient stats
    from depot.models import Notebook, DataTableFilePatientIDs

    # Get patient stats and validation metrics
    patient_stats = None
    validation_metrics = None

    if is_patient_table:
        # For patient table, get stats from the patient IDs extracted from files
        if current_files.exists():
            # Get patient count from DataTableFilePatientIDs records
            patient_records = DataTableFilePatientIDs.objects.filter(
                data_file__in=current_files,
                data_file__is_current=True
            )
            total_patient_count = 0
            for record in patient_records:
                if record.patient_ids:
                    total_patient_count += len(record.patient_ids)

            if total_patient_count > 0:
                patient_stats = {
                    'total_count': total_patient_count,
                    'has_data': True
                }
    elif patient_file_exists:
        # For non-patient tables, get patient stats and validation metrics
        patient_stats = submission.get_patient_stats()
        validation_metrics = data_table.get_patient_validation_metrics()

    # Update file_type with display name for template
    if file_type:
        file_type.display_name = get_table_display_name(file_type.name)

    # Pre-fetch notebook objects for upload prechecks
    notebook_map = {}

    # Get patient IDs from submission for validation
    if hasattr(submission, 'patient_ids_record') and submission.patient_ids_record:
        patient_file_ids = set(submission.patient_ids_record.patient_ids) if submission.patient_ids_record.patient_ids else set()
    else:
        patient_file_ids = set(submission.patient_ids) if submission.patient_ids else set()

    for file in current_files:
        if getattr(file, 'latest_validation_run', None):
            run = file.latest_validation_run
            variables = getattr(run, 'prefetched_variables', None)
            if variables is None:
                variables = list(run.variables.order_by('column_name'))
            run.variable_list = variables
            run.summary = {
                'total': run.total_variables,
                'completed': run.completed_variables,
                'with_warnings': run.variables_with_warnings,
                'with_errors': run.variables_with_errors,
                'status': run.status,
            }

            # Surface ID summary data for patient validation card directly from
            # the granular validation results so the UI reflects the new system.
            run.id_summary = None
            for variable in variables:
                if variable.column_type == 'id' and isinstance(variable.summary, dict):
                    summary_data = variable.summary or {}
                    run.id_summary = {
                        'column_name': variable.column_name,
                        'display_name': variable.get_display_name(),
                        'total_ids': summary_data.get('total_non_null', variable.total_rows or 0),
                        'unique_ids': summary_data.get('unique_count', 0),
                        'duplicate_count': summary_data.get('duplicate_count', 0),
                        'null_count': variable.null_count,
                        'sample_values': summary_data.get('sample_values') or [],
                    }
                    break

        # Note: Submissions use ValidationRun, not PrecheckRun
        # Notebook access is through ValidationRun relationship

        # Add validation metrics for non-patient tables
        if not is_patient_table and patient_file_exists:
            # Get patient ID record for this file
            patient_record = DataTableFilePatientIDs.objects.filter(data_file=file).first()
            if patient_record and patient_record.patient_ids:
                file_patient_ids = set(patient_record.patient_ids)
                file_total = len(file_patient_ids)

                if file_total > 0:
                    # Calculate matches for this file
                    file_matching = patient_file_ids & file_patient_ids if patient_file_ids else set()
                    file_out_of_bounds = file_patient_ids - patient_file_ids if patient_file_ids else file_patient_ids

                    file_matching_count = len(file_matching)
                    file_out_of_bounds_count = len(file_out_of_bounds)

                    # Calculate percentages for this file
                    file_matching_percent = round((file_matching_count / file_total * 100), 1) if file_total > 0 else 0
                    file_out_of_bounds_percent = round((file_out_of_bounds_count / file_total * 100), 1) if file_total > 0 else 0

                    # Add validation metrics to the file object
                    file.validation_metrics = {
                        'total': file_total,
                        'matching_count': file_matching_count,
                        'matching_percent': file_matching_percent,
                        'out_of_bounds_count': file_out_of_bounds_count,
                        'out_of_bounds_percent': file_out_of_bounds_percent,
                        'validation_status': patient_record.validation_status
                    }

    print(f"DEBUG: Final notebook_map has {len(notebook_map)} entries: {notebook_map}")

    file_count = current_files.count()

    # Load definition JSON to get labels for variables
    from depot.services.definition_processing import DefinitionProcessingService
    definition_service = DefinitionProcessingService(file_type.name)
    try:
        definition = definition_service.load_definition()
        # Create label mapping from definition
        definition_labels = {}
        for var_def in definition.get('variables', []):
            column_name = var_def.get('name')
            label = var_def.get('label', column_name)
            if column_name:
                definition_labels[column_name] = label
    except Exception as e:
        # If definition loading fails, use empty dict
        definition_labels = {}

    # Order variables for each file's validation run
    try:
        from depot.services.variable_ordering import VariableOrderingService
        ordering_service = VariableOrderingService(file_type.name)
        logger.info(f"==== ORDERING SERVICE INITIALIZED for {file_type.name} ====")
        logger.info(f"==== Processing {len(list(current_files))} files ====")

        # Process each file's validation run to add ordered variables
        for file in current_files:
            logger.info(f"==== Checking file {file.id}: has_validation_run={file.latest_validation_run is not None} ====")
            if file.latest_validation_run:
                logger.info(f"==== File {file.id} validation_run exists, has_variable_list={hasattr(file.latest_validation_run, 'variable_list')} ====")
                if hasattr(file.latest_validation_run, 'variable_list'):
                    variables = file.latest_validation_run.variable_list
                    logger.info(f"==== ORDERING {len(variables)} variables for file {file.id} ====")

                    # Order the variables for this file
                    core_vars, additional_vars = ordering_service.order_variables(variables)
                    ordered_vars = ordering_service.order_all_variables(variables)

                    logger.info(f"==== ORDERED: {len(ordered_vars)} variables (core: {len(core_vars)}, additional: {len(additional_vars)}) ====")
                    logger.info(f"==== First 5 ordered: {[v.column_name if hasattr(v, 'column_name') else str(v) for v in ordered_vars[:5]]} ====")

                    # Add ordering to the validation run (these are dynamic attributes, not model fields)
                    file.latest_validation_run.core_variables = core_vars
                    file.latest_validation_run.additional_variables = additional_vars
                    file.latest_validation_run.ordered_variables = ordered_vars
    except Exception as e:
        logger.error(f"==== ERROR IN VARIABLE ORDERING: {e} ====", exc_info=True)

    # Build table navigation (previous/next)
    all_tables = DataFileType.objects.filter(is_active=True).order_by('order', 'name')
    table_list = list(all_tables)

    # Add status information to each table based on submission data tables
    for table in table_list:
        # Get the data table for this submission + file type
        data_table_obj = CohortSubmissionDataTable.objects.filter(
            submission=submission,
            data_file_type=table
        ).first()

        if data_table_obj:
            # Check if table has files
            has_files = data_table_obj.get_current_files().exists()

            # Determine status display
            if data_table_obj.is_reviewed:
                table.status_display = 'Complete'
            elif has_files:
                table.status_display = 'Uploaded'
            elif data_table_obj.not_available:
                table.status_display = 'Not available'
            else:
                table.status_display = 'Not started'
        else:
            table.status_display = 'Not started'

    current_index = None
    for idx, table in enumerate(table_list):
        if table.id == file_type.id:
            current_index = idx
            break

    previous_table = None
    next_table = None
    if current_index is not None:
        if current_index > 0:
            previous_table = table_list[current_index - 1]
        if current_index < len(table_list) - 1:
            next_table = table_list[current_index + 1]

    logger.info(f"==== BUILD_TABLE_CONTEXT RETURNING ====")
    return {
        'submission': submission,
        'data_table': data_table,
        'file_type': file_type,
        'current_files': current_files,
        'attachments': attachments,
        'file_notebooks': notebook_map,  # Map of file IDs to Notebook objects
        'can_edit': can_edit,
        'can_toggle_review': can_toggle_review,  # Can toggle review status even when table is reviewed
        'can_upload': can_edit and (is_patient_table or patient_file_exists),
        'is_patient_table': is_patient_table,
        'patient_file_exists': patient_file_exists,
        'patient_stats': patient_stats,
        'validation_metrics': validation_metrics,  # Patient ID validation metrics
        'show_names': file_count > 1,  # Show name fields when multiple files
        'single_file_mode': is_patient_table or file_count <= 1,
        'definition_labels': definition_labels,
        # Table navigation
        'all_tables': table_list,
        'previous_table': previous_table,
        'next_table': next_table,
    }


@login_required
def submission_table_manage(request, submission_id, table_name):
    """
    Manage a specific data table within a submission.
    Supports multiple file uploads per table.
    """
    logger.info(f"🔥 SUBMISSION_TABLE_MANAGE: {request.method} request for submission {submission_id}, table {table_name}")
    if request.method == 'POST':
        logger.info(f"🔥 POST REQUEST: Files: {list(request.FILES.keys())}, POST data keys: {list(request.POST.keys())}")
    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )
    
    # Get data file type by name (not ID anymore)
    file_type = get_object_or_404(DataFileType, name=table_name)
    
    # Check basic view permission
    if not SubmissionPermissions.can_view(request.user, submission):
        return HttpResponseForbidden("You don't have permission to manage this submission.")
    
    # Check if submission is editable
    can_edit_submission = SubmissionPermissions.can_edit(request.user, submission)
    if not can_edit_submission and request.method == 'POST':
        # Provide specific error message based on reason
        if submission.status in ['signed_off', 'closed']:
            messages.warning(request, "This submission has been signed off and cannot be modified.")
        else:
            messages.warning(request, "You don't have permission to upload files. You must be a member of the Cohort Managers group.")
        return redirect('submission_detail', submission_id=submission.id)

    # Get or create the data table
    data_table, created = CohortSubmissionDataTable.objects.get_or_create(
        submission=submission,
        data_file_type=file_type,
        defaults={'status': 'not_started'}
    )

    # Separate permissions: can_edit (files/content) vs can_toggle_review (review status)
    can_toggle_review = can_edit_submission  # Can always toggle review if can edit submission
    can_edit = can_edit_submission

    # Check if table is marked as reviewed - if so, disable file/content editing
    if can_edit and hasattr(data_table, 'review') and data_table.review.is_reviewed:
        can_edit = False
        if request.method == 'POST' and 'reviewed' not in request.POST:
            # Allow only the review status toggle itself to be changed
            messages.warning(request, "This table has been marked as completed and cannot be modified. Unmark it as completed to make changes.")
            return redirect('submission_table_manage', submission_id=submission.id, table_name=table_name)
    
    # Check patient file requirement using model method
    is_patient_table, patient_file_exists = submission.check_patient_file_requirement(file_type)
    
    # Handle POST requests
    if request.method == 'POST':
        return handle_post_request(
            request, submission, data_table, 
            is_patient_table, patient_file_exists, can_edit
        )
    
    # Get current files with uploaded file data and attachments
    current_files = data_table.get_current_files().select_related(
        'uploaded_file',
        'latest_validation_run'
    ).prefetch_related(
        Prefetch(
            'latest_validation_run__variables',
            queryset=ValidationVariable.objects.order_by('column_name'),
            to_attr='prefetched_variables'
        )
    )
    logger.info(f"=== TABLE MANAGE VIEW === table={data_table.data_file_type.name}, current_files count={current_files.count()}, IDs={list(current_files.values_list('id', flat=True))}")
    attachments = FileAttachment.get_for_entity(data_table)

    # Note: Submissions use ValidationRun, not PrecheckRun
    # Validation reports accessed through ValidationRun relationship

    # Build context for template
    context = build_table_context(
        submission, data_table, file_type, current_files, attachments,
        can_edit, is_patient_table, patient_file_exists, can_toggle_review
    )

    # Handle AJAX requests for status polling
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse

        # Check if any files are still processing (using granular validation system)
        has_processing = any(
            file.latest_validation_run and
            file.latest_validation_run.status in ['pending', 'running']
            for file in current_files
        )

        # Check if any files just completed
        has_completed = any(
            file.latest_validation_run and
            file.latest_validation_run.status == 'completed'
            for file in current_files
        )

        # Check if data table is still in progress
        table_is_processing = data_table.status == 'in_progress'

        # Check if any variables are still generating summaries
        # This prevents reload before users can see validation errors/warnings
        summaries_pending = False
        if has_completed and not has_processing:
            # Only check if files have completed validation
            for file in current_files:
                if file.latest_validation_run and file.latest_validation_run.status == 'completed':
                    # Check if any variables in this run are missing summaries
                    pending_count = file.latest_validation_run.variables.filter(
                        summary_stats__isnull=True
                    ).count()
                    if pending_count > 0:
                        summaries_pending = True
                        break

        # Reload is needed when ALL processing AND summary generation has stopped
        # This ensures users can see all validation messages before page reloads
        reload_needed = not has_processing and not table_is_processing and not summaries_pending

        return JsonResponse({
            'reload_needed': reload_needed,
            'has_processing': has_processing,
            'has_completed': has_completed,
            'table_status': data_table.status,
            'file_count': current_files.count()
        })

    return render(request, 'pages/submissions/table_manage.html', context)


@login_required
def revalidate_submission_file(request, submission_id, table_name, file_id):
    """Trigger re-validation workflow for an existing uploaded file."""
    if request.method != 'POST':
        return HttpResponseForbidden("Revalidation must be triggered via POST")

    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )

    if not SubmissionPermissions.can_view(request.user, submission):
        return HttpResponseForbidden("You don't have permission to view this submission.")

    file_type = get_object_or_404(DataFileType, name=table_name)
    data_table = get_object_or_404(
        CohortSubmissionDataTable,
        submission=submission,
        data_file_type=file_type
    )

    if not SubmissionPermissions.can_edit(request.user, submission):
        return HttpResponseForbidden("You don't have permission to modify this submission.")

    data_file = get_object_or_404(
        DataTableFile,
        id=file_id,
        data_table=data_table,
        is_current=True
    )

    # Note: Submissions use ValidationRun, not PrecheckRun

    existing_run = data_file.latest_validation_run
    if existing_run and existing_run.status == 'running':
        message = "Validation is already running; please wait until it completes."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': message}, status=409)
        messages.warning(request, message)
        return redirect('submission_table_manage', submission_id=submission.id, table_name=table_name)

    ensure_validation_run_for_data_file(data_file)
    schedule_submission_file_workflow(submission, data_table, data_file, request.user)

    message = f"Validation re-run queued for {data_file.get_display_name()}"

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': message})

    messages.success(request, message)
    return redirect('submission_table_manage', submission_id=submission.id, table_name=table_name)


@login_required
def revalidate_submission_variable(request, submission_id, table_name, variable_id):
    if request.method != 'POST':
        return HttpResponseForbidden("Revalidation must be triggered via POST")

    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )

    if not SubmissionPermissions.can_edit(request.user, submission):
        return HttpResponseForbidden("You don't have permission to modify this submission.")

    file_type = get_object_or_404(DataFileType, name=table_name)
    data_table = get_object_or_404(
        CohortSubmissionDataTable,
        submission=submission,
        data_file_type=file_type
    )

    from depot.models import ValidationVariable

    variable = get_object_or_404(ValidationVariable.objects.select_related('validation_run'), id=variable_id)
    run = variable.validation_run

    if run.content_type.model_class() is not DataTableFile:
        return HttpResponseForbidden("Invalid validation target.")

    data_file = get_object_or_404(DataTableFile, id=run.object_id)

    if data_file.data_table_id != data_table.id or data_file.data_table.submission_id != submission.id:
        return HttpResponseForbidden("Variable does not belong to this submission table.")

    if run.status == 'running':
        message = "Validation is currently running; please wait until it completes."
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': message}, status=409)
        messages.warning(request, message)
        return redirect('submission_table_manage', submission_id=submission.id, table_name=table_name)

    revalidate_single_variable.delay(variable.id)

    message = "Variable validation re-run queued"
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': message})

    messages.success(request, message)
    return redirect('submission_table_manage', submission_id=submission.id, table_name=table_name)


@login_required
def submission_validation_status(request, submission_id, table_name, validation_run_id):
    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )

    if not SubmissionPermissions.can_view(request.user, submission):
        return HttpResponseForbidden("You don't have permission to view this submission.")

    file_type = get_object_or_404(DataFileType, name=table_name)
    data_table = get_object_or_404(
        CohortSubmissionDataTable,
        submission=submission,
        data_file_type=file_type
    )

    validation_run = get_object_or_404(
        ValidationRun.objects.select_related('content_type', 'data_file_type'),
        id=validation_run_id
    )

    content_object = validation_run.content_object
    if not isinstance(content_object, DataTableFile):
        raise Http404("Validation run is not associated with a submission file.")

    data_file = content_object
    if data_file.data_table_id != data_table.id:
        raise Http404("Validation run does not belong to this table.")

    validation_variables = validation_run.variables.all().order_by('created_at')
    initial_variable_statuses = list(validation_variables.values_list('status', flat=True))
    summary = {
        'total': validation_run.total_variables,
        'completed': validation_run.completed_variables,
        'with_warnings': validation_run.variables_with_warnings,
        'with_errors': validation_run.variables_with_errors,
        'status': validation_run.status,
    }

    # Load definition JSON to get labels for variables
    from depot.services.definition_processing import DefinitionProcessingService
    definition_service = DefinitionProcessingService(validation_run.data_file_type.name)
    definition = definition_service.load_definition()

    # Create label mapping from definition
    definition_labels = {}
    for var_def in definition.get('variables', []):
        column_name = var_def.get('name')
        label = var_def.get('label', column_name)
        if column_name:
            definition_labels[column_name] = label

    # Order variables using VariableOrderingService
    from depot.services.variable_ordering import VariableOrderingService
    print(f"==== STARTING VARIABLE ORDERING for {validation_run.data_file_type.name} ====")
    ordering_service = VariableOrderingService(validation_run.data_file_type.name)
    core_variables, additional_variables = ordering_service.order_variables(list(validation_variables))
    # Also provide fully ordered list for simpler template logic
    ordered_variables = ordering_service.order_all_variables(list(validation_variables))
    print(f"==== FINISHED ORDERING: {len(ordered_variables)} variables ====")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'partials/validation_status.html', {
            'validation_run': validation_run,
            'validation_variables': validation_variables,
            'ordered_variables': ordered_variables,
            'core_variables': core_variables,
            'additional_variables': additional_variables,
            'summary': summary,
            'definition_labels': definition_labels,
        })

    context = {
        'submission': submission,
        'data_table': data_table,
        'data_file': data_file,
        'validation_run': validation_run,
        'validation_variables': validation_variables,
        'ordered_variables': ordered_variables,
        'core_variables': core_variables,
        'additional_variables': additional_variables,
        'summary': summary,
        'initial_variable_statuses': initial_variable_statuses,
        'definition_labels': definition_labels,
    }

    return render(request, 'pages/submission_validation_status.html', context)


@login_required
def submission_validation_status_json(request, submission_id, table_name, validation_run_id):
    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )

    if not SubmissionPermissions.can_view(request.user, submission):
        return HttpResponseForbidden("You don't have permission to view this submission.")

    file_type = get_object_or_404(DataFileType, name=table_name)

    validation_run = get_object_or_404(
        ValidationRun.objects.select_related('content_type', 'data_file_type'),
        id=validation_run_id
    )

    content_object = validation_run.content_object
    if not isinstance(content_object, DataTableFile):
        raise Http404("Validation run is not associated with a submission file.")

    data_table = content_object.data_table
    if data_table.data_file_type_id != file_type.id or data_table.submission_id != submission.id:
        raise Http404("Validation run does not belong to this submission")

    variables_data = []
    for variable in validation_run.variables.all().order_by('created_at'):
        var_payload = {
            'id': variable.id,
            'status': variable.status,
            'status_display': variable.get_status_display(),
            'status_class': _get_status_badge_class(variable.status),
        }
        if variable.status == 'completed':
            var_payload.update({
                'total_rows': variable.total_rows,
                'warning_count': variable.warning_count,
                'error_count': variable.error_count,
                'valid_count': variable.valid_count,
            })
        variables_data.append(var_payload)

    summary = {
        'total': validation_run.total_variables,
        'with_warnings': validation_run.variables_with_warnings,
        'with_errors': validation_run.variables_with_errors,
    }

    return JsonResponse({
        'status': validation_run.status,
        'variables': variables_data,
        'summary': summary,
    })


def _get_status_badge_class(status):
    base_classes = "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium"

    status_classes = {
        'pending': f"{base_classes} bg-gray-100 text-gray-800",
        'running': f"{base_classes} bg-blue-100 text-blue-800",
        'completed': f"{base_classes} bg-green-100 text-green-800",
        'failed': f"{base_classes} bg-red-100 text-red-800",
    }

    return status_classes.get(status, base_classes)


def handle_ajax_file_upload(request, submission, data_table, is_patient_table, patient_file_exists):
    """Handle AJAX file upload for a data table with PHI tracking."""
    logger.info(f"🔥 UPLOAD START: Handling file upload for {data_table.data_file_type.name} table")
    logger.info(f"🔥 UPLOAD START: submission={submission.id}, data_table={data_table.id}, is_patient={is_patient_table}")
    logger.info(f"🔥 UPLOAD START: Files in request: {list(request.FILES.keys())}")

    # Check if this is actually an attachment upload that got here by mistake
    # The attachment form uses 'attachment' as the file field name
    if 'attachment' in request.FILES:
        logger.warning("Attachment upload incorrectly routed to AJAX handler - redirecting")
        return handle_attachment_upload(request, data_table)
    
    # Also check for attachment indicators in POST data
    if 'attachment_name' in request.POST or 'attachment_comments' in request.POST:
        logger.warning("Attachment upload detected by POST fields - redirecting")
        return handle_attachment_upload(request, data_table)
    
    # Get the uploaded file
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No file provided'})

    # Use model method for comprehensive validation
    is_valid, error_message = data_table.validate_file_upload(uploaded_file, request.user)
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message})
    
    # Get file metadata from request
    file_name = request.POST.get('file_name', '')
    file_comments = request.POST.get('file_comments', '')
    file_id = request.POST.get('file_id')
    debug_submission = request.POST.get('debug_submission') == 'true'

    if debug_submission:
        logger.info(f"🔧 DEBUG SUBMISSION: File will be stored for chain of custody only (no processing)")
    
    try:
        # Process file upload using async service for large files
        file_service = FileUploadService()
        # Use SECURE upload that streams directly to NAS
        if True:  # Always use secure method for PHI compliance
            logger.info(f"Processing file ({uploaded_file.size} bytes) with secure NAS streaming")
            upload_result = file_service.process_file_upload_secure(
                uploaded_file=uploaded_file,
                submission=submission,
                data_table=data_table,
                user=request.user,
                file_name=file_name,
                file_comments=file_comments,
                file_id=file_id
            )
        else:
            # Small files can still use sync processing
            upload_result = file_service.process_file_upload(
                uploaded_file=uploaded_file,
                submission=submission,
                data_table=data_table,
                user=request.user,
                file_name=file_name,
                file_comments=file_comments,
                file_id=file_id
            )

        # Check if validation failed
        if not upload_result.get('success', True):
            error_msg = upload_result.get('error', 'File validation failed')
            validation_errors = upload_result.get('validation_errors', [])
            suggest_precheck = upload_result.get('suggest_precheck', False)

            logger.error(f"File validation failed for {uploaded_file.name}: {error_msg}")

            # Format error message for display
            error_details = '\n'.join(validation_errors) if validation_errors else error_msg

            # Build response
            response_data = {
                'success': False,
                'error': error_msg,
                'error_details': error_details,
                'validation_errors': validation_errors
            }

            # Add precheck suggestion if file appears malformed
            if suggest_precheck:
                from django.urls import reverse
                from urllib.parse import urlencode

                # Build URL with pre-filled params
                precheck_url = reverse('precheck_validation_page')

                # Add query params if available
                params = {}
                if 'cohort_id' in upload_result:
                    params['cohort_id'] = upload_result['cohort_id']
                if 'data_file_type_id' in upload_result:
                    params['data_file_type_id'] = upload_result['data_file_type_id']
                if 'cohort_submission_id' in upload_result:
                    params['cohort_submission_id'] = upload_result['cohort_submission_id']

                if params:
                    precheck_url = f"{precheck_url}?{urlencode(params)}"

                response_data['suggest_precheck'] = True
                response_data['precheck_url'] = precheck_url
                response_data['precheck_message'] = (
                    'Run a detailed diagnostic scan to identify specific file issues.'
                )

            return JsonResponse(response_data, status=400)

        data_file = upload_result['data_file']
        version = upload_result['version']
        uploaded_file_record = upload_result['uploaded_file_record']

        # Set debug_submission flag if requested
        if debug_submission:
            data_file.debug_submission = True
            data_file.save(update_fields=['debug_submission'])
            logger.info(f"🔧 DEBUG SUBMISSION: Marked file {data_file.id} as debug submission")

        # Log validation warnings if any
        validation_warnings = upload_result.get('validation_warnings', [])
        if validation_warnings:
            logger.info(f"File validation warnings for {uploaded_file.name}: {', '.join(validation_warnings)}")

        # Log activity
        from depot.services.activity_logger import SubmissionActivityLogger
        activity_logger = SubmissionActivityLogger()
        activity_logger.log_file_uploaded(
            submission=submission,
            user=request.user,
            file_type=data_table.data_file_type.label,
            file_name=uploaded_file.name,
            version=version
        )

        # Skip processing for debug submissions
        if debug_submission:
            logger.info(f"🔧 DEBUG SUBMISSION: Skipping validation workflow for file {data_file.id}")
        else:
            # Note: Submissions use ValidationRun, not PrecheckRun
            # Validation workflow will be started below

            # Use unified sequential workflow for ALL file types
            logger.info(f"Starting unified workflow for file_type={data_table.data_file_type.name}, data_file.id={data_file.id}")

            from depot.tasks import (
                create_duckdb_task,
                cleanup_workflow_files_task
            )
            from depot.tasks.patient_extraction import extract_patient_ids_task

            # Launch workflow after transaction commits

            # Use transaction.on_commit to ensure DB consistency before launching workflow
            def _launch_workflow():
                logger.info(f"WORKFLOW LAUNCH: Starting workflow chain for file {data_file.id}")
                schedule_submission_file_workflow(submission, data_table, data_file, request.user)

            transaction.on_commit(_launch_workflow)

            # Create ValidationRun immediately so spinner shows on page reload
            # (The actual validation will be run by the Celery workflow)
            from django.contrib.contenttypes.models import ContentType
            content_type = ContentType.objects.get_for_model(data_file)
            validation_run = ValidationRun.objects.create(
                content_type=content_type,
                object_id=str(data_file.id),  # CharField expects string
                data_file_type=data_table.data_file_type,
                duckdb_path=None,  # Will be set by workflow
                raw_file_path=data_file.raw_file_path,
                status='pending',  # Explicitly set to pending
            )
            data_file.latest_validation_run = validation_run
            data_file.save(update_fields=['latest_validation_run'])
            logger.info(f"Created ValidationRun {validation_run.id} for immediate UI feedback")

        # Build and return response IMMEDIATELY
        if debug_submission:
            message = f'File uploaded for debugging (v{version}) - no processing'
        else:
            message = f'File uploaded successfully (v{version})'

        response_data = {
            'success': True,
            'message': message,
            'file_id': data_file.id,
            'comments': data_file.comments,
            'debug_submission': debug_submission
        }

        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"File upload failed: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


def handle_mark_not_available(request, data_table):
    """Handle marking a data table as not available (site doesn't collect)."""
    
    # Check if checkbox is checked
    mark_not_available = request.POST.get('mark_not_available')
    reason = request.POST.get('not_available_reason', '')
    
    if mark_not_available:
        # Use the new method to mark as not available
        data_table.mark_not_available(request.user, reason)
        
        # Log activity
        SubmissionActivity.objects.create(
            submission=data_table.submission,
            user=request.user,
            activity_type='file_skipped',
            description=f"Marked {data_table.data_file_type.label} as 'Site doesn't collect this data'"
        )
        
        messages.success(request, f"{data_table.data_file_type.label} marked as 'Site doesn't collect this data'")
    else:
        # If unchecked, clear the not available status
        if data_table.not_available:
            data_table.clear_not_available(request.user)
            messages.info(request, f"{data_table.data_file_type.label} status cleared")
    
    return redirect('submission_table_manage', 
                   submission_id=data_table.submission.id,
                   table_name=data_table.data_file_type.name)

# Keep old function name as alias for backward compatibility
handle_mark_not_collected = handle_mark_not_available


def handle_table_sign_off(request, data_table):
    """Handle signing off on a data table."""
    comments = request.POST.get('comments', '')
    
    # Check if all files have been reviewed
    if not data_table.has_files():
        messages.error(request, "No files have been uploaded for this data table.")
        return redirect('submission_table_manage', 
                       submission_id=data_table.submission.id, 
                       table_name=data_table.data_file_type.name)
    
    # Sign off the data table
    data_table.mark_signed_off(request.user, comments)
    
    # Log activity
    SubmissionActivity.objects.create(
        submission=data_table.submission,
        user=request.user,
        activity_type='file_approved',
        description=f"Signed off on {data_table.data_file_type.label}"
    )
    
    messages.success(request, f"{data_table.data_file_type.label} has been signed off successfully.")
    return redirect('submission_detail', submission_id=data_table.submission.id)


def handle_file_actions(request, data_table):
    """Handle file management actions (add/remove files)."""
    from depot.models import DataTableFile, DataTableFilePatientIDs, SubmissionPatientIDs

    action = request.POST.get('action')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if action == 'remove_file':
        file_id = request.POST.get('file_id')
        if file_id:
            try:
                data_file = get_object_or_404(DataTableFile, id=file_id, data_table=data_table)

                # Delete the actual files from storage
                from depot.storage.phi_manager import PHIStorageManager
                phi_manager = PHIStorageManager()

                # Delete raw file
                if data_file.raw_file_path:
                    try:
                        phi_manager.delete_from_nas(
                            nas_path=data_file.raw_file_path,
                            cohort=data_table.submission.cohort,
                            user=request.user,
                            file_type='raw_csv' if data_file.raw_file_path.endswith('.csv') else 'raw_tsv'
                        )
                        logger.info(f"Deleted raw file from storage: {data_file.raw_file_path}")

                        # Also delete .meta file
                        meta_path = f"{data_file.raw_file_path}.meta"
                        try:
                            phi_manager.delete_from_nas(
                                nas_path=meta_path,
                                cohort=data_table.submission.cohort,
                                user=request.user,
                                file_type='metadata'
                            )
                            logger.info(f"Deleted raw .meta file from storage: {meta_path}")
                        except Exception as meta_error:
                            logger.debug(f"No .meta file to delete or failed: {meta_error}")
                    except Exception as del_error:
                        logger.error(f"Failed to delete raw file from storage: {del_error}")
                        # Continue even if file deletion fails

                # Delete processed file if it exists
                if data_file.processed_file_path:
                    try:
                        phi_manager.delete_from_nas(
                            nas_path=data_file.processed_file_path,
                            cohort=data_table.submission.cohort,
                            user=request.user,
                            file_type='processed_csv' if data_file.processed_file_path.endswith('.csv') else 'processed_tsv'
                        )
                        logger.info(f"Deleted processed file from storage: {data_file.processed_file_path}")

                        # Also delete .meta file
                        meta_path = f"{data_file.processed_file_path}.meta"
                        try:
                            phi_manager.delete_from_nas(
                                nas_path=meta_path,
                                cohort=data_table.submission.cohort,
                                user=request.user,
                                file_type='metadata'
                            )
                            logger.info(f"Deleted processed .meta file from storage: {meta_path}")
                        except Exception as meta_error:
                            logger.debug(f"No .meta file to delete or failed: {meta_error}")
                    except Exception as del_error:
                        logger.error(f"Failed to delete processed file from storage: {del_error}")
                        # Continue even if file deletion fails

                # Delete DuckDB file if it exists
                if data_file.duckdb_file_path:
                    try:
                        phi_manager.delete_from_nas(
                            nas_path=data_file.duckdb_file_path,
                            cohort=data_table.submission.cohort,
                            user=request.user,
                            file_type='duckdb'
                        )
                        logger.info(f"Deleted DuckDB file from storage: {data_file.duckdb_file_path}")

                        # Also delete .meta file
                        meta_path = f"{data_file.duckdb_file_path}.meta"
                        try:
                            phi_manager.delete_from_nas(
                                nas_path=meta_path,
                                cohort=data_table.submission.cohort,
                                user=request.user,
                                file_type='metadata'
                            )
                            logger.info(f"Deleted DuckDB .meta file from storage: {meta_path}")
                        except Exception as meta_error:
                            logger.debug(f"No .meta file to delete or failed: {meta_error}")
                    except Exception as del_error:
                        logger.error(f"Failed to delete DuckDB file from storage: {del_error}")
                        # Continue even if file deletion fails

                # Soft delete the file (sets deleted_at and keeps record)
                data_file.delete()  # This is a soft delete due to SoftDeletableModel

                # Soft delete patient ID validation records for this file
                from django.utils import timezone
                deleted_patient_id_count = DataTableFilePatientIDs.objects.filter(
                    data_file=data_file
                ).update(deleted_at=timezone.now())
                logger.info(f"Soft deleted {deleted_patient_id_count} patient ID validation record(s) for deleted file {file_id}")

                # Soft delete ValidationRun and all related records (ValidationVariable, summaries) for this specific file
                from depot.models import ValidationRun
                from django.contrib.contenttypes.models import ContentType
                try:
                    content_type = ContentType.objects.get_for_model(DataTableFile)
                    validation_runs = ValidationRun.objects.filter(
                        content_type=content_type,
                        object_id=data_file.id
                    )
                    deleted_count = validation_runs.count()
                    validation_runs.update(deleted_at=timezone.now())  # Soft delete preserves audit trail
                    logger.info(f"Soft deleted {deleted_count} ValidationRun record(s) and all related summaries for deleted file {file_id}")
                except Exception as e:
                    logger.warning(f"Failed to soft delete ValidationRun records for file {file_id}: {e}")

                # If this was a patient file, CASCADE DELETE all other data table files
                # Because all other files are validated against patient IDs from patient file
                if data_table.data_file_type.name == 'patient':
                    logger.warning(f"Patient file deleted - cascading deletion to all other files in submission {data_table.submission.id}")

                    # Get all non-patient data tables in this submission
                    other_data_tables = CohortSubmissionDataTable.objects.filter(
                        submission=data_table.submission
                    ).exclude(
                        data_file_type__name='patient'
                    )

                    cascade_deleted_count = 0
                    cascade_deleted_tables = []

                    for other_table in other_data_tables:
                        # Get all files for this table
                        files_to_delete = DataTableFile.objects.filter(
                            data_table=other_table
                        )

                        for file_to_delete in files_to_delete:
                            try:
                                # Delete physical files from storage
                                if file_to_delete.raw_file_path:
                                    try:
                                        phi_manager.delete_from_nas(
                                            nas_path=file_to_delete.raw_file_path,
                                            cohort=data_table.submission.cohort,
                                            user=request.user,
                                            file_type='raw_csv' if file_to_delete.raw_file_path.endswith('.csv') else 'raw_tsv'
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to delete raw file during cascade: {e}")

                                if file_to_delete.duckdb_file_path:
                                    try:
                                        phi_manager.delete_from_nas(
                                            nas_path=file_to_delete.duckdb_file_path,
                                            cohort=data_table.submission.cohort,
                                            user=request.user,
                                            file_type='duckdb'
                                        )
                                    except Exception as e:
                                        logger.error(f"Failed to delete DuckDB file during cascade: {e}")

                                # Soft delete the file
                                file_to_delete.delete()

                                # Soft delete patient ID validation records
                                from django.utils import timezone
                                DataTableFilePatientIDs.objects.filter(
                                    data_file=file_to_delete
                                ).update(deleted_at=timezone.now())

                                # Soft delete ValidationRun records (and cascades to related summaries)
                                content_type = ContentType.objects.get_for_model(DataTableFile)
                                ValidationRun.objects.filter(
                                    content_type=content_type,
                                    object_id=file_to_delete.id
                                ).update(deleted_at=timezone.now())

                                cascade_deleted_count += 1

                            except Exception as e:
                                logger.error(f"Failed to cascade delete file {file_to_delete.id}: {e}")

                        if files_to_delete.exists():
                            cascade_deleted_tables.append(other_table.data_file_type.name)

                    logger.warning(f"CASCADE DELETE: Removed {cascade_deleted_count} files from {len(cascade_deleted_tables)} tables: {', '.join(set(cascade_deleted_tables))}")

                    # Clear the submission's patient IDs since no patient file remains
                    try:
                        patient_ids_record = SubmissionPatientIDs.objects.get(submission=data_table.submission)
                        patient_ids_record.patient_ids = []
                        patient_ids_record.patient_count = 0
                        patient_ids_record.source_file = None
                        patient_ids_record.save()
                        logger.info("Cleared submission patient IDs - patient file deleted")
                    except SubmissionPatientIDs.DoesNotExist:
                        pass  # Nothing to clear
                else:
                    # For non-patient files, the cleanup of DataTableFilePatientIDs above
                    # is sufficient - the deleted file's validation records are removed
                    # and the UI will no longer show stale validation data
                    logger.info(f"Non-patient file deleted - patient ID validation records cleaned up")

                # CRITICAL: For multi-file tables, regenerate combined DuckDB after deletion
                remaining_files = DataTableFile.objects.filter(
                    data_table=data_table,
                    is_current=True
                ).order_by('id')

                if remaining_files.exists():
                    logger.info(f"Regenerating DuckDB for {remaining_files.count()} remaining files in {data_table.data_file_type.name}")

                    # Get raw file paths for regeneration
                    raw_file_paths = [f.raw_file_path for f in remaining_files if f.raw_file_path]

                    if raw_file_paths:
                        # Set table status to in_progress so UI shows spinner
                        data_table.update_status('in_progress')
                        logger.info(f"Set data_table {data_table.id} status to in_progress for regeneration")

                        # Trigger DuckDB regeneration
                        from depot.tasks.duckdb_creation import create_duckdb_task

                        # Use the first remaining file to trigger regeneration
                        # The task will detect all current files and combine them
                        first_file = remaining_files.first()

                        task_data = {
                            'data_file_id': first_file.id,
                            'user_id': request.user.id,
                            'submission_id': data_table.submission.id,
                            'cohort_id': data_table.submission.cohort.id,
                            'file_type_name': data_table.data_file_type.name,
                            'raw_file_path': first_file.raw_file_path,
                        }

                        # Queue the regeneration workflow
                        from celery import chain
                        from depot.tasks import (
                            extract_patient_ids_task,
                            cleanup_workflow_files_task,
                            start_validation_for_data_file,
                        )
                        from depot.tasks.file_integrity import calculate_hashes_in_workflow

                        workflow_steps = [
                            create_duckdb_task.si(task_data),
                            extract_patient_ids_task.s(),
                            calculate_hashes_in_workflow.s(),
                            start_validation_for_data_file.s(),
                            cleanup_workflow_files_task.s(),
                        ]

                        chain(*workflow_steps).apply_async(countdown=2)
                        logger.info(f"Queued DuckDB regeneration and validation for {data_table.data_file_type.name} after file deletion")
                else:
                    logger.info(f"No remaining files in {data_table.data_file_type.name} - cleaning up validation data and resetting to stock state")

                    # Clean up orphaned ValidationRun records
                    from depot.models import ValidationRun
                    try:
                        delete_result = ValidationRun.objects.filter(
                            content_type__model='datatablefile',
                            object_id__in=DataTableFile.all_objects.filter(data_table=data_table).values_list('id', flat=True)
                        ).delete()
                        deleted_count = delete_result[0] if isinstance(delete_result, tuple) else 0
                        logger.info(f"Deleted {deleted_count} orphaned ValidationRun records for {data_table.data_file_type.name}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up ValidationRun records: {e}")

                    # Clean up all physical files from duckdb/ and processed/ directories
                    import os
                    from pathlib import Path

                    # Get the base directory structure for this table
                    cohort = data_table.submission.cohort
                    protocol_year = data_table.submission.protocol_year
                    file_type_name = data_table.data_file_type.name

                    # Construct paths to duckdb/ and processed/ directories
                    base_path = phi_manager.storage.base_path / 'uploads' / f"{cohort.id}_{cohort.name}" / str(protocol_year.year) / file_type_name
                    duckdb_dir = base_path / 'duckdb'
                    processed_dir = base_path / 'processed'

                    # Clean up duckdb directory
                    if duckdb_dir.exists():
                        for file_path in duckdb_dir.iterdir():
                            if file_path.is_file():
                                try:
                                    phi_manager.delete_from_nas(
                                        nas_path=str(file_path),
                                        cohort=cohort,
                                        user=request.user,
                                        file_type='duckdb'
                                    )
                                    logger.info(f"Deleted orphaned DuckDB file: {file_path.name}")
                                except Exception as e:
                                    logger.error(f"Failed to delete orphaned DuckDB file {file_path}: {e}")

                    # Clean up processed directory
                    if processed_dir.exists():
                        for file_path in processed_dir.iterdir():
                            if file_path.is_file():
                                try:
                                    phi_manager.delete_from_nas(
                                        nas_path=str(file_path),
                                        cohort=cohort,
                                        user=request.user,
                                        file_type='processed_csv'
                                    )
                                    logger.info(f"Deleted orphaned processed file: {file_path.name}")
                                except Exception as e:
                                    logger.error(f"Failed to delete orphaned processed file {file_path}: {e}")

                    # Reset table to stock state
                    data_table.update_status('not_started')
                    logger.info(f"Reset data_table {data_table.id} status to not_started (stock state)")

                # Log activity
                from depot.services.activity_logger import SubmissionActivityLogger
                activity_logger = SubmissionActivityLogger()
                activity_logger.log_file_removed(
                    submission=data_table.submission,
                    user=request.user,
                    file_type=data_table.data_file_type.label,
                    file_name=data_file.original_filename or f"File {file_id}"
                )

                # Return JSON for AJAX requests
                if is_ajax:
                    return JsonResponse({'success': True, 'message': 'File removed successfully'})

                messages.success(request, "File removed successfully.")
            except Exception as e:
                logger.error(f"Error removing file {file_id}: {e}")
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)}, status=400)
                messages.error(request, f"Failed to remove file: {e}")

    elif action == 'remove_attachment':
        # Handle attachment removal
        attachment_id = request.POST.get('attachment_id')
        if attachment_id:
            try:
                from depot.models import FileAttachment
                attachment = get_object_or_404(FileAttachment, id=attachment_id)

                # Verify the attachment belongs to this data_table
                if attachment.content_object == data_table:
                    attachment.delete()

                    # Log activity
                    from depot.services.activity_logger import SubmissionActivityLogger
                    activity_logger = SubmissionActivityLogger()
                    activity_logger.log_file_removed(
                        submission=data_table.submission,
                        user=request.user,
                        file_type=f"{data_table.data_file_type.label} Attachment",
                        file_name=attachment.name or attachment.uploaded_file.original_filename
                    )

                    if is_ajax:
                        return JsonResponse({'success': True, 'message': 'Attachment removed successfully'})
                    messages.success(request, "Attachment removed successfully.")
                else:
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': 'Invalid attachment'}, status=403)
                    messages.error(request, "You don't have permission to remove this attachment.")
            except Exception as e:
                logger.error(f"Error removing attachment {attachment_id}: {e}")
                if is_ajax:
                    return JsonResponse({'success': False, 'error': str(e)}, status=400)
                messages.error(request, f"Failed to remove attachment: {e}")

    elif action == 'update_file_name':
        # Handle file name autosave
        file_id = request.POST.get('file_id')
        file_name = request.POST.get('file_name', '')
        if file_id:
            with transaction.atomic():
                data_file = get_object_or_404(DataTableFile, id=file_id, data_table=data_table)
                if data_file.name != file_name:
                    data_file.name = file_name
                    data_file.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})

    elif action == 'update_file':
        file_id = request.POST.get('file_id')
        if file_id:
            with transaction.atomic():
                data_file = get_object_or_404(DataTableFile, id=file_id, data_table=data_table)

                # Store old values for comparison
                old_comments = data_file.comments
                old_name = data_file.name

                # Update with new values
                new_name = request.POST.get(f'file_name_{file_id}', '')
                new_comments = request.POST.get(f'file_comments_{file_id}', '')

                # Only save if something actually changed
                if old_name != new_name or old_comments != new_comments:
                    data_file.name = new_name
                    data_file.comments = new_comments
                    data_file.save()

                    # Use smart logging that merges edits within time window
                    if old_comments != new_comments:  # Only log comment changes
                        SubmissionActivity.log_comment_change(
                            submission=data_table.submission,
                            user=request.user,
                            file_type=data_table.data_file_type.label,
                            old_comments=old_comments,
                            new_comments=new_comments
                        )

            # Return JSON response for AJAX requests
            if is_ajax:
                return JsonResponse({'success': True, 'message': 'Comments saved successfully'})

            messages.success(request, "File updated successfully.")

    # Only redirect for non-AJAX requests
    if not is_ajax:
        return redirect('submission_table_manage',
                       submission_id=data_table.submission.id,
                       table_name=data_table.data_file_type.name)

    # Default JSON response for AJAX
    return JsonResponse({'success': False, 'error': 'Unknown action'})


def handle_attachment_upload(request, data_table):
    """Handle arbitrary file attachment upload - accepts all file types."""
    # Debug what we're receiving
    logger.info(f"handle_attachment_upload - FILES: {list(request.FILES.keys())}, POST: {list(request.POST.keys())}")
    
    attachment_file = request.FILES.get('attachment')
    attachment_name = request.POST.get('attachment_name', '')
    attachment_comments = request.POST.get('attachment_comments', '')
    
    if not attachment_file:
        messages.error(request, "No attachment file provided.")
        return redirect('submission_table_manage', 
                       submission_id=data_table.submission.id,
                       table_name=data_table.data_file_type.name)
    
    # We trust users on this site - accept all file types
    # Common research file types: CSV, TSV, TXT, PDF, Excel, Word, SAS, R, JSON, XML, etc.
    
    try:
        from django.db import transaction

        with transaction.atomic():
            # Initialize service
            file_service = FileUploadService()
            storage = StorageManager.get_submission_storage()

            # Calculate file hash using service
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
                protocol_year=data_table.submission.protocol_year.year,
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
        
        # Check if this is an AJAX request that expects JSON
        # The fetch API includes application/json in Accept header by default
        accept_header = request.META.get('HTTP_ACCEPT', '')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in accept_header:
            logger.info(f"Attachment upload successful, returning JSON (Accept: {accept_header})")
            return JsonResponse({'success': True, 'message': 'Attachment uploaded successfully'})
        
        messages.success(request, "Attachment uploaded successfully.")
        
    except Exception as e:
        error_msg = f"Failed to upload attachment: {str(e)}"
        logger.error(error_msg, exc_info=True)
        
        # Return JSON error if this is an AJAX request
        accept_header = request.META.get('HTTP_ACCEPT', '')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in accept_header:
            logger.error(f"Returning JSON error response (Accept: {accept_header})")
            return JsonResponse({'success': False, 'error': error_msg})
        
        messages.error(request, error_msg)
    
    return redirect('submission_table_manage', 
                   submission_id=data_table.submission.id,
                   table_name=data_table.data_file_type.name)

# Removed submission_validation_report and generate_validation_csv functions
# These will be replaced with inline metrics display and streaming CSV download

@login_required
def download_patient_validation_csv(request, submission_id, table_id, file_id=None):
    """
    Generate and stream CSV file with patient ID validation data.
    Can generate for all files in table or for a specific file.
    """
    from django.http import StreamingHttpResponse
    import csv
    import io

    # Get submission and table
    submission = get_object_or_404(
        CohortSubmission.objects.select_related('cohort', 'protocol_year'),
        pk=submission_id
    )

    data_table = get_object_or_404(
        CohortSubmissionDataTable.objects.select_related('data_file_type'),
        pk=table_id,
        submission=submission
    )

    # Check permissions
    if not SubmissionPermissions.can_view(request.user, submission):
        return HttpResponseForbidden("You don't have permission to view this submission.")

    def generate_csv_rows():
        """Generator function to stream CSV rows."""
        # Create CSV writer with string IO
        output = io.StringIO()
        writer = csv.writer(output)

        # Get patient IDs from submission's patient file
        if hasattr(submission, 'patient_ids_record') and submission.patient_ids_record:
            patient_file_ids = set(submission.patient_ids_record.patient_ids) if submission.patient_ids_record.patient_ids else set()
        else:
            patient_file_ids = set(submission.patient_ids) if submission.patient_ids else set()

        # Get patient ID records
        from depot.models import DataTableFilePatientIDs

        if file_id:
            # Single file mode
            from depot.models import DataTableFile
            data_file = get_object_or_404(DataTableFile, pk=file_id, data_table=data_table)

            # Write simple header for single file
            writer.writerow(['patient_id', 'in_patient_file', 'matching', 'out_of_bounds'])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Get patient IDs for this specific file
            patient_record = DataTableFilePatientIDs.objects.filter(
                data_file=data_file
            ).first()

            file_patient_ids = set(patient_record.patient_ids) if patient_record and patient_record.patient_ids else set()

            # Write rows for ALL patient IDs from patient file (not just this file's IDs)
            for patient_id in sorted(patient_file_ids):
                is_in_file = patient_id in file_patient_ids
                writer.writerow([
                    patient_id,
                    1,  # Always 1 since we're iterating over patient_file_ids
                    1 if is_in_file else 0,  # matching = is this ID in the uploaded file
                    0 if is_in_file else 1   # out_of_bounds (inverted - 1 if NOT in file)
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        else:
            # All files mode - enhanced with per-file columns
            patient_records = DataTableFilePatientIDs.objects.filter(
                data_file__data_table=data_table,
                data_file__is_current=True
            ).select_related('data_file')

            # Build per-file data
            file_data = []
            all_uploaded_ids = set()
            patient_id_to_files = {}

            for record in patient_records:
                file_name = record.data_file.name or record.data_file.original_filename or f"File {record.data_file.id}"
                file_patient_ids = set(record.patient_ids) if record.patient_ids else set()

                file_data.append({
                    'name': file_name,
                    'patient_ids': file_patient_ids
                })

                for pid in file_patient_ids:
                    all_uploaded_ids.add(pid)
                    if pid not in patient_id_to_files:
                        patient_id_to_files[pid] = []
                    patient_id_to_files[pid].append(file_name)

            # Write enhanced header
            header = ['patient_id', 'in_patient_file', 'matching', 'out_of_bounds', 'files_containing_id']
            for file_info in file_data:
                header.append(f"in_{file_info['name']}")
            writer.writerow(header)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            # Write rows for ALL patient IDs from patient file (not just uploaded ones)
            # This ensures we see which patient IDs are missing from uploaded files
            for patient_id in sorted(patient_file_ids):
                is_in_uploaded = patient_id in all_uploaded_ids

                row = [
                    patient_id,
                    1,  # Always 1 since we're iterating over patient_file_ids
                    1 if is_in_uploaded else 0,  # matching = is this ID in any uploaded file
                    0 if is_in_uploaded else 1,  # out_of_bounds (inverted - 1 if NOT in uploaded)
                    '; '.join(patient_id_to_files.get(patient_id, [])) if is_in_uploaded else ''
                ]

                for file_info in file_data:
                    row.append(1 if patient_id in file_info['patient_ids'] else 0)

                writer.writerow(row)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    # Create streaming response
    response = StreamingHttpResponse(
        generate_csv_rows(),
        content_type='text/csv'
    )

    # Set filename based on mode
    if file_id:
        from depot.models import DataTableFile
        data_file = DataTableFile.objects.get(pk=file_id)
        file_name_part = (data_file.name or data_file.original_filename or f"file_{file_id}").replace('.csv', '')
        filename = f"patient_validation_{file_name_part}_{submission_id}.csv"
    else:
        filename = f"patient_validation_{data_table.data_file_type.name}_{submission_id}_all.csv"

    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


def download_file_patient_validation_csv(request, submission_id, table_id, file_id):
    """Download patient validation CSV for a specific file."""
    return download_patient_validation_csv(request, submission_id, table_id, file_id)

@login_required
@submission_view_required
def mark_file_failed(request, submission_id, table_id, file_id, submission=None):
    """Mark a file as failed and clean up any stuck processing."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # submission is passed by decorator
    if not submission:
        submission = get_object_or_404(CohortSubmission, id=submission_id)
    data_table = get_object_or_404(CohortSubmissionDataTable, id=table_id, submission=submission)
    data_file = get_object_or_404(DataTableFile, id=file_id, data_table=data_table)

    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Cancel the latest validation run if it's running
    if data_file.latest_validation_run and data_file.latest_validation_run.status in ['pending', 'running']:
        data_file.latest_validation_run.status = 'failed'
        data_file.latest_validation_run.error_message = 'Manually cancelled by user'
        data_file.latest_validation_run.save()
        logger.info(f"Cancelled validation run {data_file.latest_validation_run.id} for file {data_file.id}")

    # Update data table status if it's stuck in progress
    if data_table.status == 'in_progress':
        data_table.update_status('failed')
        logger.info(f"Set data_table {data_table.id} status to failed")

    # Mark file as failed and clear processing state
    data_file.duckdb_conversion_error = 'Manually marked as failed by user'
    data_file.duckdb_file_path = ''
    data_file.processed_file_path = ''
    data_file.save()

    logger.info(f"File {data_file.id} ({data_file.original_filename}) marked as failed by user {request.user.id}, cleared processing state")

    messages.success(request, f'File marked as failed and processing stopped. You can now retry processing.')

    return JsonResponse({
        'success': True,
        'message': 'File marked as failed and processing stopped'
    })


@login_required
@submission_view_required
def retry_file_processing(request, submission_id, table_id, file_id, submission=None):
    """Retry processing a failed file."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # submission is passed by decorator
    if not submission:
        submission = get_object_or_404(CohortSubmission, id=submission_id)
    data_table = get_object_or_404(CohortSubmissionDataTable, id=table_id, submission=submission)
    data_file = get_object_or_404(DataTableFile, id=file_id, data_table=data_table)
    
    # Check permissions
    if not SubmissionPermissions.can_edit(request.user, submission):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Reset validation run status if it exists
    if data_file.latest_validation_run:
        data_file.latest_validation_run.status = 'pending'
        data_file.latest_validation_run.error_message = ''
        data_file.latest_validation_run.save()
        logger.info(f"Reset validation run {data_file.latest_validation_run.id} to pending")

    # Clear error state
    data_file.duckdb_conversion_error = ''
    data_file.duckdb_file_path = ''
    data_file.processed_file_path = ''
    data_file.duckdb_created_at = None
    data_file.save()

    # Reset data table status if needed
    if data_table.status == 'failed':
        data_table.update_status('in_progress')
        logger.info(f"Reset data_table {data_table.id} status to in_progress")

    # Trigger reprocessing
    schedule_submission_file_workflow(submission, data_table, data_file, request.user)

    logger.info(f"User {request.user.id} triggered reprocessing for file {data_file.id} ({data_file.original_filename})")

    messages.success(request, f'Processing restarted for {data_file.original_filename}')
    
    return JsonResponse({
        'success': True,
        'message': 'Processing restarted'
    })
