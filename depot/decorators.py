from functools import wraps
from django.contrib.auth.decorators import user_passes_test, login_required
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from depot.models import CohortSubmission, CohortSubmissionDataTable, Cohort
from depot.permissions import SubmissionPermissions, CohortPermissions


def ajax_login_required(view_func):
    """
    Login required decorator that returns 401 for AJAX requests
    instead of redirecting to login page.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Authentication required'}, status=401)
            return redirect('sign_in')
        return view_func(request, *args, **kwargs)
    return wrapper


def anonymous_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("index")
        return view_func(request, *args, **kwargs)

    return wrapper


def submission_view_required(view_func):
    """
    Decorator that checks if user can view a submission.
    Expects submission_id as a parameter.
    """
    @wraps(view_func)
    def wrapper(request, submission_id=None, *args, **kwargs):
        if submission_id is None:
            # Try to get submission_id from kwargs
            submission_id = kwargs.get('submission_id')
        
        if submission_id is None:
            return HttpResponseForbidden("No submission specified.")
        
        submission = get_object_or_404(CohortSubmission, pk=submission_id)
        
        if not SubmissionPermissions.can_view(request.user, submission):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Permission denied'}, status=403)
            return HttpResponseForbidden("You don't have permission to view this submission.")
        
        # Add submission to kwargs for the view to use
        kwargs['submission'] = submission
        return view_func(request, submission_id=submission_id, *args, **kwargs)
    
    return wrapper


def submission_edit_required(view_func):
    """
    Decorator that checks if user can edit a submission.
    Expects submission_id as a parameter.
    """
    @wraps(view_func)
    def wrapper(request, submission_id=None, *args, **kwargs):
        if submission_id is None:
            submission_id = kwargs.get('submission_id')
        
        if submission_id is None:
            return HttpResponseForbidden("No submission specified.")
        
        submission = get_object_or_404(CohortSubmission, pk=submission_id)
        
        if not SubmissionPermissions.can_edit(request.user, submission):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Permission denied - submission is locked or you lack permission'}, status=403)
            return HttpResponseForbidden("You don't have permission to edit this submission.")
        
        kwargs['submission'] = submission
        return view_func(request, submission_id=submission_id, *args, **kwargs)
    
    return wrapper


def submission_manage_required(view_func):
    """
    Decorator that checks if user can manage a submission (admin operations).
    Expects submission_id as a parameter.
    """
    @wraps(view_func)
    def wrapper(request, submission_id=None, *args, **kwargs):
        if submission_id is None:
            submission_id = kwargs.get('submission_id')
        
        if submission_id is None:
            return HttpResponseForbidden("No submission specified.")
        
        submission = get_object_or_404(CohortSubmission, pk=submission_id)
        
        if not SubmissionPermissions.can_manage(request.user, submission):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Administrator permission required'}, status=403)
            return HttpResponseForbidden("Administrator permission required.")
        
        kwargs['submission'] = submission
        return view_func(request, submission_id=submission_id, *args, **kwargs)
    
    return wrapper


def cohort_member_required(view_func):
    """
    Decorator that checks if user is a member of the cohort.
    Expects cohort_id as a parameter.
    """
    @wraps(view_func)
    def wrapper(request, cohort_id=None, *args, **kwargs):
        if cohort_id is None:
            cohort_id = kwargs.get('cohort_id')
        
        if cohort_id is None:
            return HttpResponseForbidden("No cohort specified.")
        
        cohort = get_object_or_404(Cohort, pk=cohort_id)
        
        if not CohortPermissions.can_view(request.user, cohort):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'You are not a member of this cohort'}, status=403)
            return HttpResponseForbidden("You are not a member of this cohort.")
        
        kwargs['cohort'] = cohort
        return view_func(request, cohort_id=cohort_id, *args, **kwargs)
    
    return wrapper


def patient_file_required(view_func):
    """
    Decorator that checks if a patient file exists for the submission.
    Must be used after submission_view_required or submission_edit_required.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        submission = kwargs.get('submission')
        
        if not submission:
            return HttpResponseForbidden("Submission not found in request context.")
        
        if not submission.has_patient_file():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Patient file must be uploaded first'}, status=400)
            return HttpResponseForbidden("Patient file must be uploaded first.")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
