from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from depot.models import CohortSubmission, SubmissionActivity
from depot.forms.submission import SubmissionCreateForm


@login_required
def submissions_page(request):
    # Get submissions based on user permissions
    if request.user.is_administrator() or request.user.is_data_manager():
        # Administrators and data managers see all submissions
        submissions_qs = CohortSubmission.objects.select_related(
            'cohort', 'protocol_year', 'started_by'
        ).order_by('-created_at')
    else:
        # Researchers see only their cohort's submissions
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        
        submissions_qs = CohortSubmission.objects.select_related(
            'cohort', 'protocol_year', 'started_by'
        ).filter(
            cohort__in=user_cohorts
        ).order_by('-created_at')
    
    # Transform to match template expectations
    submissions = []
    for submission in submissions_qs:
        # Get notebooks for this submission
        from depot.models import Notebook, CohortSubmissionDataTable, DataTableFile
        notebooks = Notebook.objects.filter(
            content_type__model='cohortsubmission',
            object_id=submission.id,
            status='completed'
        ).values_list('id', flat=True)

        # Get file completion stats - just count data tables with files
        data_tables = CohortSubmissionDataTable.objects.filter(submission=submission)
        tables_with_files = 0

        for table in data_tables:
            # Check if this table has any current files
            has_files = DataTableFile.objects.filter(
                data_table=table,
                is_current=True,
                deleted_at__isnull=True
            ).exists()
            if has_files:
                tables_with_files += 1

        submissions.append({
            "id": submission.id,
            "cohort": submission.cohort.name,
            "for": submission.protocol_year.name,
            "status": submission.get_status_display(),
            "protocol_year": submission.protocol_year.name,
            "started_by": submission.started_by.get_full_name() or submission.started_by.username,
            "created_at": submission.created_at,
            "is_signed_off": submission.status == 'signed_off',
            "notebook_ids": list(notebooks),
            "tables_with_files": tables_with_files,
        })

    # Handle create form submission
    if request.method == 'POST':
        form = SubmissionCreateForm(request.POST, user=request.user)
        if form.is_valid():
            submission = form.save(request.user)

            # Log activity
            SubmissionActivity.log_submission_created(submission, request.user)

            messages.success(
                request,
                f"Submission created for {submission.cohort.name} - {submission.protocol_year.name}"
            )
            return redirect('submission_detail', submission_id=submission.id)
    else:
        # Pre-populate form with smart defaults
        form_temp = SubmissionCreateForm(user=request.user)
        initial = {}

        # Smart protocol year selection: n-1 (current year - 1), or minimum year if not available
        from datetime import datetime
        protocol_years = form_temp.fields['protocol_year'].queryset
        if protocol_years.exists():
            current_year = datetime.now().year
            target_year = current_year - 1  # n-1

            # Try to find the target year (n-1)
            target_py = protocol_years.filter(name=str(target_year)).first()
            if target_py:
                initial['protocol_year'] = target_py
            else:
                # If n-1 doesn't exist, use the earliest year available
                initial['protocol_year'] = protocol_years.order_by('name').first()

        cohorts = form_temp.fields['cohort'].queryset
        if cohorts.exists():
            initial['cohort'] = cohorts.first()

        form = SubmissionCreateForm(initial=initial, user=request.user)

    # Prepare options for c-input.select components
    protocol_year_options = [
        {"value": py.id, "label": str(py)}
        for py in form.fields['protocol_year'].queryset
    ]

    cohort_options = [
        {"value": c.id, "label": c.name}
        for c in form.fields['cohort'].queryset
    ]

    # Get form data for initial values
    form_data = {
        'protocol_year': (
            str(form.data.get('protocol_year'))
            if form.data.get('protocol_year')
            else str(form.initial.get('protocol_year').id if form.initial.get('protocol_year') else '')
        ),
        'cohort': (
            str(form.data.get('cohort'))
            if form.data.get('cohort')
            else str(form.initial.get('cohort').id if form.initial.get('cohort') else '')
        ),
    }

    return render(
        request,
        "pages/submissions/index.html",
        {
            "title": "Submissions",
            "submissions": submissions,
            "form": form,
            "protocol_year_options": protocol_year_options,
            "cohort_options": cohort_options,
            "form_data": form_data,
            "errors": form.errors,
        },
    )