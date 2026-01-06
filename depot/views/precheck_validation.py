"""
Precheck Validation Views - Granular Validation System (Beta)

This module provides views for the new granular validation system.
It allows users to upload files and see real-time validation progress
with individual validation jobs displayed as they complete.

Key Features:
- Real-time validation progress
- Individual validation job status
- Detailed issue reporting
- No permanent storage (floating ValidationRuns)

See: docs/technical/granular-validation-system.md
"""
import logging
import os
import traceback
import hashlib
from uuid import uuid4
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from depot.models import (
    PrecheckValidation,
    DataFileType,
    Cohort,
    ValidationRun,
    PHIFileTracking
)
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def precheck_validation_page(request):
    """
    Main precheck validation page.

    GET: Display upload form
    POST: Process file upload and start validation
    """
    if request.method == "POST":
        return _handle_precheck_validation_upload(request)

    # GET: Display form
    # Show all cohorts for superusers/admins, or just assigned cohorts for others
    # Note: Using 'form_cohorts' to avoid overwriting context processor's 'user_cohorts' (used for sidebar)
    if request.user.is_superuser or request.user.is_na_accord_admin():
        form_cohorts = Cohort.objects.filter(status='active').order_by('name')
    else:
        form_cohorts = request.user.cohorts.filter(status='active').order_by('name')

    data_file_types = DataFileType.objects.all().order_by('name')

    # Get query params for pre-filling the form (when redirected from upload error)
    prefill_cohort_id = request.GET.get('cohort_id', '')
    prefill_data_file_type_id = request.GET.get('data_file_type_id', '')
    prefill_cohort_submission_id = request.GET.get('cohort_submission_id', '')

    import json

    context = {
        'cohorts': json.dumps([{'id': c.id, 'name': c.name} for c in form_cohorts]),
        'data_file_types': data_file_types,
        'cohort_options': [{'value': str(c.id), 'label': c.name} for c in form_cohorts],
        'data_file_type_options': [{'value': str(d.id), 'label': d.name} for d in data_file_types],
        'upload_method_options': [
            {'value': 'upload', 'label': 'Upload File'},
            {'value': 'paste', 'label': 'Paste Data'},
        ],
        'prefill_cohort_id': prefill_cohort_id,
        'prefill_data_file_type_id': prefill_data_file_type_id,
        'prefill_cohort_submission_id': prefill_cohort_submission_id,
        'form_cohorts': form_cohorts,  # For form dropdown (all cohorts for admins)
        # Note: 'user_cohorts' comes from context processor (sidebar only - filtered by submissions)
    }

    return render(request, 'pages/precheck_validation.html', context)


def _handle_precheck_validation_upload(request):
    """Handle POST request for file upload - PRECHECK VALIDATION SYSTEM"""
    try:
        logger.info("="*80)
        logger.info("PRECHECK VALIDATION FORM SUBMIT STARTED")
        logger.info("="*80)

        # Get form data
        cohort_id = request.POST.get('cohort_id')
        data_file_type_id = request.POST.get('data_file_type_id')
        cohort_submission_id = request.POST.get('cohort_submission_id') or None
        logger.info(f"Form data: cohort_id={cohort_id}, data_file_type_id={data_file_type_id}, submission_id={cohort_submission_id}")

        if not cohort_id or not data_file_type_id:
            return JsonResponse({
                'success': False,
                'error': 'Please select a cohort and data file type'
            })

        cohort = get_object_or_404(Cohort, id=cohort_id)
        data_file_type = get_object_or_404(DataFileType, id=data_file_type_id)

        # Get submission if provided
        cohort_submission = None
        if cohort_submission_id:
            from depot.models import CohortSubmission
            cohort_submission = get_object_or_404(CohortSubmission, id=cohort_submission_id, cohort=cohort)

        # Check user has access to cohort (superusers/admins can access any cohort)
        if not (request.user.is_superuser or request.user.is_na_accord_admin()) and cohort not in request.user.cohorts.all():
            return JsonResponse({
                'success': False,
                'error': 'You do not have access to this cohort'
            })

        # Get staged file information
        staged_token = request.POST.get('staged_token')
        staged_filename = request.POST.get('staged_filename')
        staged_content_type = request.POST.get('staged_content_type') or 'application/octet-stream'
        logger.info(f"Staged file: token={staged_token}, filename={staged_filename}")

        if not staged_token or not staged_filename:
            return JsonResponse({
                'success': False,
                'error': 'No staged file found. Please upload a file before starting validation.'
            })

        # File is already on services server in scratch storage
        # This avoids downloading 500MB+ files from services back to web server
        staging_path = f"precheck_validation/{request.user.id}/{staged_token}/{staged_filename}"
        logger.info(f"Using staging path: {staging_path}")

        # Create PrecheckValidation record for precheck validation
        logger.info("Creating PrecheckValidation record...")
        validation = PrecheckValidation.objects.create(
            user=request.user,
            cohort=cohort,
            data_file_type=data_file_type,
            cohort_submission=cohort_submission,
            original_filename=staged_filename,
            file_path=staging_path,  # Store relative path in scratch storage
            status='pending'
        )
        logger.info(f"Created PrecheckValidation {validation.id} (submission: {cohort_submission.id if cohort_submission else 'None'})")

        # Update PHI tracking record to link to validation
        try:
            staged_records = PHIFileTracking.objects.filter(
                metadata__staged_token=staged_token,
                cleanup_required=True,
                cleaned_up=False
            )
            for record in staged_records:
                record.metadata['precheck_validation_id'] = str(validation.id)
                record.metadata['validation_started'] = timezone.now().isoformat()
                record.save()
                logger.info(f"Updated PHI tracking record {record.id}")
        except Exception as tracking_error:
            logger.warning("Failed to update PHI tracking: %s", tracking_error, exc_info=True)

        # Queue validation to run asynchronously on services server where file is stored
        from depot.tasks.precheck_validation import run_precheck_validation
        logger.info(f"Queueing precheck validation for {validation.id}")
        try:
            run_precheck_validation.delay(validation.id)
        except Exception as validation_error:
            logger.error(f"Failed to queue validation: {validation_error}", exc_info=True)
            # Don't fail the request - validation errors are tracked in the validation record

        # Redirect to polling page with validation ID
        logger.info(f"Redirecting to validation status page")
        return JsonResponse({
            'success': True,
            'validation_id': validation.id,
            'message': 'Validation started'
        })

    except Exception as e:
        logger.error(f"Error in precheck validation upload: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        })


@login_required
def precheck_validation_upload(request):
    """
    Handle file upload endpoint (AJAX).

    This is called via JavaScript to upload the file before form submission.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        file = request.FILES.get('file')
        cohort_id = request.POST.get('cohort_id')
        data_file_type_id = request.POST.get('data_file_type_id')

        if not file:
            return JsonResponse({'success': False, 'error': 'No file provided'})

        cohort = None
        if cohort_id:
            cohort = get_object_or_404(Cohort, id=cohort_id)
            # Check access (superusers/admins can access any cohort)
            if not (request.user.is_superuser or request.user.is_na_accord_admin()) and cohort not in request.user.cohorts.all():
                return JsonResponse({'success': False, 'error': 'Access denied to this cohort'})

        content_type = request.POST.get('content_type') or getattr(file, 'content_type', 'application/octet-stream')

        # Stage file in scratch storage until submission is confirmed
        scratch_storage = StorageManager.get_scratch_storage()

        token = uuid4().hex
        safe_filename = file.name
        staging_path = f"precheck_validation/{request.user.id}/{token}/{safe_filename}"

        file_content = file.read()
        file_size = len(file_content)
        file_hash = hashlib.sha256(file_content).hexdigest()

        scratch_storage.save(staging_path, file_content)

        # Track staged upload for PHI compliance
        absolute_path = staging_path
        try:
            if hasattr(scratch_storage, 'get_absolute_path'):
                absolute_path = scratch_storage.get_absolute_path(staging_path)
            PHIFileTracking.objects.create(
                cohort=cohort,
                user=request.user,
                action='precheck_upload_staged',
                file_path=absolute_path,
                file_type='raw_csv',
                file_size=file_size,
                cleanup_required=True,
                metadata={
                    'relative_path': staging_path,
                    'original_filename': safe_filename,
                    'staged_token': token,
                    'content_type': content_type,
                    'file_hash': file_hash,
                },
                server_role=os.environ.get('SERVER_ROLE', 'testing')
            )
        except Exception as tracking_error:
            logger.warning("Failed to record PHI tracking for staged precheck upload %s: %s", staging_path, tracking_error, exc_info=True)

        logger.info(f"Staged precheck upload: {safe_filename} -> {staging_path} ({file_size} bytes)")

        return JsonResponse({
            'success': True,
            'token': token,
            'filename': safe_filename,
            'content_type': content_type,
            'file_size': file_size,
            'file_hash': file_hash,
        })

    except Exception as e:
        logger.error(f"File upload error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        })


@login_required
def precheck_validation_status(request, validation_run_id):
    """
    Display validation status and results.

    Shows real-time progress of all validation jobs.
    """
    validation_run = get_object_or_404(
        ValidationRun.objects.select_related('data_file_type'),
        id=validation_run_id
    )

    # Get all validation variables (per-variable validation results)
    validation_variables = validation_run.variables.all().order_by('created_at')
    initial_variable_statuses = list(validation_variables.values_list('status', flat=True))

    # Get summary
    summary = {
        'total': validation_run.total_variables,
        'completed': validation_run.completed_variables,
        'with_warnings': validation_run.variables_with_warnings,
        'with_errors': validation_run.variables_with_errors,
        'status': validation_run.status
    }

    # Load definition to get column labels
    from depot.services.definition_processing import DefinitionProcessingService
    definition_service = DefinitionProcessingService(validation_run.data_file_type.name)
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
        logger.warning(f"Failed to load definition labels: {e}")
        # If definition loading fails, use empty dict
        definition_labels = {}

    # Order variables using VariableOrderingService
    from depot.services.variable_ordering import VariableOrderingService
    ordering_service = VariableOrderingService(validation_run.data_file_type.name)
    core_variables, additional_variables = ordering_service.order_variables(list(validation_variables))
    # Also provide fully ordered list for simpler template logic
    ordered_variables = ordering_service.order_all_variables(list(validation_variables))

    # For AJAX requests, return just the validation status partial
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

    # Full page render
    context = {
        'validation_run': validation_run,
        'validation_variables': validation_variables,
        'ordered_variables': ordered_variables,
        'core_variables': core_variables,
        'additional_variables': additional_variables,
        'summary': summary,
        'initial_variable_statuses': initial_variable_statuses,
        'definition_labels': definition_labels,
    }

    return render(request, 'pages/precheck_validation_status.html', context)


@login_required
def precheck_validation_status_json(request, validation_run_id):
    """
    Return validation status as JSON for AJAX polling.

    This allows the frontend to update individual data points without
    destroying Alpine.js component state.
    """
    validation_run = get_object_or_404(
        ValidationRun.objects.select_related('data_file_type'),
        id=validation_run_id
    )

    # Build variable data
    variables_data = []
    for variable in validation_run.variables.all().order_by('created_at'):
        var_data = {
            'id': variable.id,
            'status': variable.status,
            'status_display': variable.get_status_display(),
            'status_class': _get_status_badge_class(variable.status),
        }

        # Add stats if completed
        if variable.status == 'completed':
            var_data.update({
                'total_rows': variable.total_rows,
                'warning_count': variable.warning_count,
                'error_count': variable.error_count,
                'valid_count': variable.valid_count,
            })

        variables_data.append(var_data)

    # Build summary
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
    """Get CSS classes for status badge based on status value."""
    base_classes = "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium"

    status_classes = {
        'pending': f"{base_classes} bg-gray-100 text-gray-800",
        'running': f"{base_classes} bg-blue-100 text-blue-800",
        'completed': f"{base_classes} bg-green-100 text-green-800",
        'failed': f"{base_classes} bg-red-100 text-red-800",
    }

    return status_classes.get(status, base_classes)


@login_required
def precheck_validation_status_page(request, validation_id):
    """
    Display progressive validation status page with Alpine.js polling.

    Shows real-time updates as validation progresses through stages.
    """
    try:
        validation = get_object_or_404(
            PrecheckValidation.objects.select_related('cohort', 'data_file_type', 'validation_run'),
            id=validation_id,
            user=request.user  # Ensure user owns this validation
        )
    except PrecheckValidation.DoesNotExist:
        return render(request, 'pages/error.html', {
            'error': 'Validation not found or access denied'
        }, status=404)

    import json
    context = {
        'validation': validation,
        'polling_url': f'/precheck-validation/api/{validation_id}/status',
        # Include initial data for completed validations (so it shows even without polling)
        'initial_file_metadata': json.dumps(validation.get_metadata_dict()) if validation.status in ['completed', 'failed'] else 'null',
        'initial_integrity_results': json.dumps(validation.get_integrity_dict()) if validation.status in ['completed', 'failed'] else 'null',
        'initial_patient_id_results': json.dumps(validation.patient_id_results) if validation.patient_id_results else 'null',
    }

    # If validation is complete and has a validation run, add validation details for sidebar layout
    if validation.status == 'completed' and validation.validation_run:
        validation_run = validation.validation_run
        validation_variables = validation_run.variables.all().order_by('created_at')

        # Build summary
        context['validation_run'] = validation_run
        context['validation_variables'] = validation_variables
        context['summary'] = {
            'total': validation_run.total_variables,
            'completed': validation_run.completed_variables,
            'with_warnings': validation_run.variables_with_warnings,
            'with_errors': validation_run.variables_with_errors,
            'status': validation_run.status,
        }

        # Load definition labels
        from depot.data.definition_loader import get_definition_for_type
        definition_obj = get_definition_for_type(validation.data_file_type.name)
        definition_list = definition_obj.get_definition()

        definition_labels = {}
        for var_def in definition_list:
            column_name = var_def.get('name')
            label = var_def.get('label', column_name)
            if column_name:
                definition_labels[column_name] = label

        context['definition_labels'] = definition_labels

        # Order variables for sidebar
        from depot.services.variable_ordering import VariableOrderingService
        ordering_service = VariableOrderingService(validation.data_file_type.name)
        ordered_variables = ordering_service.order_all_variables(list(validation_variables))
        context['ordered_variables'] = ordered_variables

    return render(request, 'pages/precheck_validation_diagnostic_status.html', context)


@login_required
@require_http_methods(["GET"])
def precheck_validation_status_api(request, validation_id):
    """
    Poll endpoint for new PrecheckValidation status (diagnostic tool).

    Returns JSON with current validation status, progress, and results.
    Used by Alpine.js frontend for progressive feedback.
    """
    try:
        validation = PrecheckValidation.objects.get(
            id=validation_id,
            user=request.user  # Ensure user owns this validation
        )
    except PrecheckValidation.DoesNotExist:
        return JsonResponse({'error': 'Validation not found'}, status=404)

    # Build response data
    response_data = {
        'status': validation.status,
        'current_stage': validation.current_stage,
        'progress_percent': validation.progress_percent,
        'file_metadata': validation.get_metadata_dict(),
        'integrity_results': validation.get_integrity_dict(),
        'validation_results': validation.get_validation_dict(),
        'patient_id_results': validation.patient_id_results if validation.patient_id_results else None,
        'error': validation.error_message if validation.status == 'failed' else None,
        'completed_at': validation.completed_at.isoformat() if validation.completed_at else None,
        'validation_run_completed': validation.validation_run_id is not None and validation.validation_run.status == 'completed' if validation.validation_run_id else False,
    }

    return JsonResponse(response_data)


@login_required
@require_http_methods(["GET"])
def cohort_submissions_api(request, cohort_id):
    """
    API endpoint to load submissions for a cohort.

    Returns list of submissions with patient_ids available for validation.
    """
    try:
        from depot.models import CohortSubmission

        # Get cohort and verify user has access
        cohort = get_object_or_404(Cohort, id=cohort_id)
        if not request.user.cohorts.filter(id=cohort.id).exists() and not request.user.is_superuser:
            return JsonResponse({'error': 'Access denied'}, status=403)

        # Get all submissions for this cohort
        submissions = CohortSubmission.objects.filter(
            cohort=cohort
        ).select_related('protocol_year').order_by('-created_at')[:20]  # Limit to recent 20

        submissions_data = []
        for submission in submissions:
            # Get patient IDs from SubmissionPatientIDs record, not submission.patient_ids
            from depot.models import SubmissionPatientIDs
            patient_ids_record = SubmissionPatientIDs.objects.filter(submission=submission).first()
            patient_count = len(patient_ids_record.patient_ids) if patient_ids_record and patient_ids_record.patient_ids else 0

            # Include all submissions but mark which have patient IDs
            if patient_count > 0:
                label = f"{submission.protocol_year.name} ({patient_count} patient IDs)"
            else:
                label = f"{submission.protocol_year.name} (no patient IDs yet)"

            submissions_data.append({
                'id': submission.id,
                'label': label,
                'patient_count': patient_count,
                'has_patient_ids': patient_count > 0,
            })

        return JsonResponse({
            'submissions': submissions_data
        })

    except Exception as e:
        logger.error(f'Error loading submissions for cohort {cohort_id}: {e}', exc_info=True)
        return JsonResponse({'error': 'Failed to load submissions'}, status=500)
