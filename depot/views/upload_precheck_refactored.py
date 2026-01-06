"""
Refactored audit views using service layer pattern.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404, HttpResponseForbidden
from django.conf import settings
import logging

from depot.forms.upload_precheck_submission_form import PrecheckRunSubmissionForm as AuditSubmissionForm
from depot.models import DataFileType, PrecheckRun, Cohort, UploadedFile, UploadType
from depot.services.file_upload_service import FileUploadService
from depot.services.upload_precheck_service import PrecheckRunService
from depot.utils.forms import get_form_data, get_form_options
from depot.decorators import cohort_member_required

logger = logging.getLogger(__name__)


@login_required
def audit_page(request):
    """Handle the audit submission form - refactored."""
    if request.method == "POST":
        form = AuditSubmissionForm(request.POST, request.FILES, user=request.user)
        
        if form.is_valid():
            # Form handles submission internally, including service calls
            audit = form.handle_submission()
            return redirect("precheck_run_status", precheck_run_id=audit.id)
    else:
        form = AuditSubmissionForm(user=request.user)
    
    context = build_audit_form_context(form)
    return render(request, "pages/audit_modern.html", context)


@login_required
def audit_upload(request):
    """Handle AJAX file upload for audit - refactored to use services."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        # Extract and validate parameters
        params = extract_upload_params(request)
        
        # Verify cohort access
        cohort = validate_cohort_access(request.user, params['cohort_id'])
        
        # Get data file type
        data_file_type = get_object_or_404(DataFileType, id=params['data_file_type_id'])
        
        # Process file using service
        file_service = FileUploadService()
        uploaded_file = process_audit_file_upload(
            file=params['file'],
            cohort=cohort,
            data_file_type=data_file_type,
            user=request.user,
            file_service=file_service
        )
        
        return JsonResponse({
            'success': True,
            'file_id': uploaded_file.id,
            'filename': uploaded_file.filename,
            'size': uploaded_file.file_size or 0
        })
        
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Http404 as e:
        return JsonResponse({'success': False, 'error': 'Resource not found'}, status=404)
    except Exception as e:
        logger.error(f"Error uploading audit file: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Upload failed'}, status=500)


@login_required
def audit_status(request, audit_id):
    """Display the status of an audit - refactored to use AuditService."""
    # Get audit and verify access
    audit = get_audit_with_access_check(request.user, audit_id)
    
    # Handle JSON requests for polling
    if request.headers.get('Accept') == 'application/json':
        return get_audit_status_json(audit)
    
    # Build context for HTML response
    context = build_audit_status_context(audit)
    return render(request, "pages/audit_status.html", context)


# Helper functions

def build_audit_form_context(form):
    """Build context dictionary for audit form template."""
    return {
        "title": "Audit A Data File",
        "form": form,
        "errors": form.errors,
        "cohort_options": [
            {"value": c.id, "label": c.name} 
            for c in form.available_cohorts
        ],
        "data_file_type_options": get_form_options(form, "data_file_type_id"),
        "upload_method_options": get_form_options(form, "upload_method"),
        "data": get_form_data(form),
    }


def extract_upload_params(request):
    """Extract and validate upload parameters from request."""
    cohort_id = request.POST.get('cohort_id')
    data_file_type_id = request.POST.get('data_file_type_id')
    file = request.FILES.get('file')
    
    if not all([cohort_id, data_file_type_id, file]):
        raise ValueError('Missing required parameters')
    
    return {
        'cohort_id': cohort_id,
        'data_file_type_id': data_file_type_id,
        'file': file
    }


def validate_cohort_access(user, cohort_id):
    """Validate user has access to cohort."""
    cohort = get_object_or_404(Cohort, id=cohort_id)
    
    # Check cohort restrictions
    if cohort not in user.cohorts.all():
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        return render(request, 'errors/403.html', status=403)
    
    return cohort


def process_audit_file_upload(file, cohort, data_file_type, user, file_service):
    """Process audit file upload using services."""
    # Calculate file hash
    file_hash = file_service.calculate_file_hash(file)
    
    # Build storage path
    storage_path = file_service.build_storage_path(
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        protocol_year='audits',  # Special case for audits
        file_type=data_file_type.name,
        filename=file.name
    )
    
    # Create uploaded file record
    uploaded_file = file_service.create_uploaded_file_record(
        file=file,
        user=user,
        storage_path=storage_path,
        file_hash=file_hash,
        upload_type=UploadType.VALIDATION_INPUT
    )
    
    # Store the actual file content
    from depot.storage.manager import StorageManager
    storage = StorageManager.get_submission_storage()
    
    file.seek(0)  # Reset file position
    saved_path = storage.save(
        path=storage_path,
        content=file.read(),
        content_type='text/csv'
    )

    if not saved_path.startswith('uploads/'):
        saved_path = f"uploads/{saved_path.lstrip('/')}"

    # Update the uploaded file with actual path
    uploaded_file.storage_path = saved_path
    uploaded_file.save()
    
    return uploaded_file


def get_audit_with_access_check(user, audit_id):
    """Get audit and verify user has access."""
    audit = get_object_or_404(PrecheckRun, id=audit_id)
    
    # Check access
    if audit.cohort not in user.cohorts.all():
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        return render(request, 'errors/403.html', status=403)
    
    return audit


def get_audit_status_json(audit):
    """Get audit status as JSON for polling."""
    # Use PrecheckRunService to get enhanced status
    precheck_run_service = PrecheckRunService()
    
    # Get report URL if available
    report_url = precheck_run_service.get_report_url(audit) if audit.status == 'completed' else None
    
    return JsonResponse({
        'status': audit.status,
        'result': audit.result,
        'completed': audit.status in ['completed', 'failed'],
        'report_url': report_url,
        'created_at': audit.created_at.isoformat() if audit.created_at else None,
        'updated_at': audit.updated_at.isoformat() if audit.updated_at else None,
    })


def build_audit_status_context(audit):
    """Build context for audit status template."""
    # Use PrecheckRunService for additional information
    precheck_run_service = PrecheckRunService()
    report_url = precheck_run_service.get_report_url(audit) if audit.status == 'completed' else None
    
    return {
        "title": "Audit Status",
        "audit": audit,
        "report_url": report_url,
        "is_completed": audit.status in ['completed', 'failed'],
        "is_processing": audit.status in ['pending', 'processing_duckdb', 'processing_notebook'],
    }
