from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from depot.models import CohortSubmission, CohortSubmissionDataTable, DataTableFile, DataFileType


@login_required
def submissions_upload_page(request, submission_id=None):
    # If no submission_id provided, show the old placeholder page
    if submission_id is None:
        submission_types = [
            "Patient Record",
            "Diagnosis Record",
            "Laboratory Test Result Record",
            "Medication Record",
            "Mortality Record",
            "Genetic Data",
            "Insurance Information",
            "Hospitalizations",
            "Substance Use Survey Information",
            "Procedures",
            "Discharge Diagnosis Data",
            "HIV Acquisition Risk Factor Record",
            "Census Table",
        ]

        return render(
            request,
            "pages/submissions/upload.html",
            {
                "title": "Upload A Submission",
                "submission_types": submission_types,
                "legacy_view": True,
            },
        )
    
    # New submission-specific view
    # Get the submission and check permissions
    submission = get_object_or_404(CohortSubmission, id=submission_id)
    
    # Check if user has access to this submission
    if not request.user.is_superuser and not request.user.can_manage_submissions:
        if submission.cohort not in request.user.cohorts.all():
            messages.error(request, "You don't have permission to access this submission.")
            return redirect('submissions')
    
    # Get all available data file types
    file_types = DataFileType.objects.filter(
        is_active=True
    ).order_by('name')
    
    # Get existing submission data tables
    data_tables = CohortSubmissionDataTable.objects.filter(
        submission=submission
    ).select_related('data_file_type').prefetch_related('files')

    # Create a mapping of file type to data table
    table_map = {dt.data_file_type.id: dt for dt in data_tables}
    
    # Build the file type list with status
    file_type_data = []
    patient_file_type = None
    
    for ft in file_types:
        dt = table_map.get(ft.id)

        # Check if this is the patient file type
        is_patient_file = ft.name.lower() == 'patient'
        if is_patient_file:
            patient_file_type = ft

        # Get current file if data table exists
        current_file = None
        if dt:
            current_file = dt.files.filter(is_current=True).first()

        file_type_data.append({
            'id': ft.id,
            'name': ft.name,
            'description': ft.description,
            'is_patient_file': is_patient_file,
            'submission_file': dt,  # Keep same key name for template compatibility
            'status': 'uploaded' if current_file else 'not_uploaded',
            'can_upload': is_patient_file or submission.can_upload_non_patient_files(),
            'audit_id': None,  # Audit system not used in new architecture
            'acknowledged': hasattr(dt, 'review') and dt.review.is_reviewed if dt else False,
            'has_warnings': False,  # Warning system not implemented in new architecture
        })
    
    # Sort to put patient file first
    file_type_data.sort(key=lambda x: (not x['is_patient_file'], x['name']))
    
    # Calculate overall progress
    total_files = len(file_type_data)
    uploaded_files = sum(1 for ft in file_type_data if ft['submission_file'])
    acknowledged_files = sum(1 for ft in file_type_data if ft['acknowledged'])
    
    context = {
        "title": f"Upload Submission - {submission.cohort.name}",
        "submission": submission,
        "file_types": file_type_data,
        "total_files": total_files,
        "uploaded_files": uploaded_files,
        "acknowledged_files": acknowledged_files,
        "progress_percentage": int((uploaded_files / total_files) * 100) if total_files > 0 else 0,
        "can_sign_off": submission.status != 'signed_off' and acknowledged_files == total_files,
        "patient_file_uploaded": submission.patient_file_processed,
        "legacy_view": False,
    }

    return render(
        request,
        "pages/submissions/upload.html",
        context,
    )