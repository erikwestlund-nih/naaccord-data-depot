from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from depot.forms.upload_precheck_submission_form import PrecheckRunSubmissionForm
from depot.models import DataFileType, PrecheckRun, Cohort, UploadedFile, UploadType, PHIFileTracking, Activity, ActivityType
from depot.storage.temp_files import TemporaryStorage
from depot.storage.manager import StorageManager
from depot.validators.file_security import validate_data_file_upload

import tempfile
import os
import hashlib
import logging

from depot.utils.forms import get_form_data, get_form_options, extract_form_errors

logger = logging.getLogger(__name__)


@login_required
def precheck_run_page(request):
    """Handle the upload precheck submission form."""
    if request.method == "POST":
        form = PrecheckRunSubmissionForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            precheck_run = form.handle_submission()
            return redirect("precheck_run_status", precheck_run_id=precheck_run.id)
    else:
        form = PrecheckRunSubmissionForm(user=request.user)

    return render(
        request,
        "pages/precheck_run.html",
        {
            "title": "Upload Precheck A Data File",
            "form": form,
            "errors": form.errors,
            "cohort_options": get_form_options(form, "cohort_id"),
            "data_file_type_options": get_form_options(form, "data_file_type_id"),
            "upload_method_options": get_form_options(form, "upload_method"),
            "data": get_form_data(form),
        },
    )


@login_required
def precheck_run_upload(request):
    """Handle AJAX file upload for upload precheck."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        # Get required parameters
        data_file_type_id = request.POST.get('data_file_type_id')
        cohort_id = request.POST.get('cohort_id')
        file = request.FILES.get('file')
        
        if not all([data_file_type_id, cohort_id, file]):
            return JsonResponse({'success': False, 'error': 'Missing required parameters'})
        
        # Get and validate cohort access
        cohort = get_object_or_404(Cohort, id=cohort_id)
        # Superusers can access any cohort, regular users must be members
        if not request.user.is_superuser and cohort not in request.user.cohorts.all():
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        # Get data file type
        data_file_type = get_object_or_404(DataFileType, id=data_file_type_id)

        # Validate file security (CSV only for data files)
        try:
            validate_data_file_upload(file)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'File validation failed: {str(e)}'}, status=400)

        # Read file content
        content = file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Save to uploads storage (streams to services server when SERVER_ROLE=web)
        from django.utils import timezone
        import uuid
        storage = StorageManager.get_storage('uploads')
        cohort_name = cohort.name.replace(' ', '_').replace('/', '-')

        # Add timestamp and UUID to prevent overwrites
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]  # First 8 chars of UUID

        # Keep original extension
        file_parts = file.name.rsplit('.', 1)
        if len(file_parts) > 1:
            base_name, extension = file_parts
            unique_filename = f"{timestamp}_{unique_id}_{base_name}.{extension}"
        else:
            unique_filename = f"{timestamp}_{unique_id}_{file.name}"

        storage_path = f"precheck_runs/{cohort.id}_{cohort_name}/{data_file_type.name}/{unique_filename}"

        # Create UploadedFile record first to get ID
        from django.contrib.contenttypes.models import ContentType
        uploaded_file = UploadedFile.objects.create(
            filename=file.name,
            storage_path=storage_path,  # Will be actual path after save
            uploader=request.user,
            type=UploadType.VALIDATION_INPUT,
            file_hash=file_hash
        )

        # Prepare metadata for PHI tracking on services server
        from datetime import timedelta
        cleanup_time = timezone.now() + timedelta(hours=2)

        saved_path = storage.save(
            path=storage_path,
            content=content,
            content_type='text/csv',
            metadata={
                'cohort_id': cohort.id,
                'user_id': request.user.id,
                'file_type': 'raw_csv',
                'purpose': 'precheck_run',
                'file_hash': file_hash,
                'original_filename': file.name,
                'content_object_id': uploaded_file.id,
                'content_type_id': ContentType.objects.get_for_model(uploaded_file).id,
                'expected_cleanup_by': cleanup_time.isoformat()
            }
        )

        if not saved_path.startswith('uploads/'):
            saved_path = f"uploads/{saved_path.lstrip('/')}"

        # Update uploaded file with actual saved path
        uploaded_file.storage_path = saved_path
        uploaded_file.save(update_fields=['storage_path'])

        # Note: PHI tracking is created by services server with actual filesystem path
        logger.info(f"File uploaded and streamed to services server: {saved_path}, size={len(content)}")
        
        return JsonResponse({
            'success': True,
            'file_id': uploaded_file.id,
            'filename': file.name,
            'size': len(content)
        })
        
    except Exception as e:
        logger.error(f"Error uploading upload precheck file: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def precheck_run_status(request, precheck_run_id):
    """Display the status of an upload precheck."""
    # Get the upload precheck record or 404
    precheck_run = get_object_or_404(PrecheckRun, id=precheck_run_id)

    # Check if user has access to this upload precheck through cohort membership
    can_access = precheck_run.can_access(request.user)

    if not can_access:
        logger.warning(f"Access denied: User ID {request.user.id} attempted to access upload precheck {precheck_run_id} from cohort {precheck_run.cohort.name if precheck_run.cohort else 'None'}")
        return render(request, 'errors/403.html', status=403)

    # Log successful upload precheck report access
    Activity.log_activity(
        user=request.user,
        activity_type=ActivityType.REPORT_VIEW,
        success=True,
        request=request,
        details={
            'precheck_run_id': precheck_run_id,
            'cohort': precheck_run.cohort.name if precheck_run.cohort else None,
            'data_file_type': precheck_run.data_file_type.name if precheck_run.data_file_type else None,
            'report_type': 'precheck_run_status'
        }
    )

    # If it's a JSON request (from Alpine.js polling), return JSON response
    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'status': precheck_run.status,
            'result': precheck_run.result,
            'completed': precheck_run.status in ['completed', 'failed']
        })

    # Otherwise return the HTML template
    return render(
        request,
        "pages/precheck_run_status.html",
        {
            "title": "Upload Precheck Status",
            "precheck_run": precheck_run,
        },
    )
