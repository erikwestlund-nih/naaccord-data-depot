from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from depot.models import ProtocolYear, Cohort, SubmissionActivity
from depot.forms.submission import SubmissionCreateForm
from depot.permissions import CohortPermissions


@login_required
def submission_create_page(request, cohort_id=None):
    # Check if user can create submissions in general
    if not request.user.can_create_submission():
        return HttpResponseForbidden("You don't have permission to create submissions.")
    
    # Get cohort if specified
    cohort = None
    if cohort_id:
        cohort = get_object_or_404(Cohort, id=cohort_id)
        # Check if user can create submission for this specific cohort
        if not CohortPermissions.can_create_submission(request.user, cohort):
            return HttpResponseForbidden("You don't have permission to create submissions for this cohort.")
    
    # Get protocol year from query parameter
    protocol_year_id = request.GET.get('protocol_year')
    protocol_year = None
    
    if protocol_year_id:
        protocol_year = get_object_or_404(ProtocolYear, id=protocol_year_id)
    
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
            # Redirect to the submission detail page
            return redirect('submission_detail', submission_id=submission.id)
    else:
        initial = {}
        
        # Create temporary form to get querysets
        form_temp = SubmissionCreateForm(user=request.user)
        
        # Set protocol year - either from parameter or select first available
        if protocol_year:
            initial['protocol_year'] = protocol_year
        else:
            protocol_years = form_temp.fields['protocol_year'].queryset
            if protocol_years.exists():
                initial['protocol_year'] = protocol_years.first()
        
        # Set cohort - either from parameter or select first available
        if cohort:
            initial['cohort'] = cohort
        else:
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
        "pages/submissions/create.html",
        {
            "title": "Create Submission",
            "form": form,
            "protocol_year": protocol_year,
            "cohort": cohort,
            "protocol_year_options": protocol_year_options,
            "cohort_options": cohort_options,
            "form_data": form_data,
            "errors": form.errors,
        },
    )