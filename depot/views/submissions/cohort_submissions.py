from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.db.models import Q, Count, Max, Case, When, F, Value, CharField
from django.db.models.functions import Coalesce

from depot.models import Cohort, CohortSubmission, CohortMembership, ProtocolYear


@login_required
def cohort_submissions_page(request, cohort_id):
    """
    Display submissions for a specific cohort.
    Users can only see submissions for cohorts they belong to,
    unless they are administrators or data managers.
    """
    cohort = get_object_or_404(Cohort, pk=cohort_id)
    
    # Check permissions
    can_view = (
        request.user.is_administrator() or
        request.user.is_data_manager() or
        CohortMembership.objects.filter(user=request.user, cohort=cohort).exists()
    )
    
    if not can_view:
        return HttpResponseForbidden("You don't have permission to view submissions for this cohort.")
    
    # Get submissions for this cohort
    submissions = CohortSubmission.objects.filter(cohort=cohort).select_related(
        'protocol_year', 'started_by', 'final_acknowledged_by'
    ).annotate(
        file_count=Count('files'),
        last_activity=Max('activities__created_at'),
        status_display=Case(
            When(status='draft', then=Value('Draft')),
            When(status='in_progress', then=Value('In Progress')),
            When(status='completed', then=Value('Completed')),
            When(status='signed_off', then=Value('Signed Off')),
            default=F('status'),
            output_field=CharField(),
        )
    ).order_by('-protocol_year__year', '-created_at')
    
    # Get available protocol years for creating new submission
    protocol_years = ProtocolYear.objects.filter(is_active=True).order_by('-year')
    
    # Check if user can create submissions
    can_create = request.user.can_create_submission() and CohortMembership.objects.filter(
        user=request.user, cohort=cohort
    ).exists()
    
    # Check if user can manage submissions (approve files, etc.)
    can_manage = request.user.is_data_manager() or request.user.is_administrator()
    
    context = {
        'cohort': cohort,
        'submissions': submissions,
        'protocol_years': protocol_years,
        'can_create': can_create,
        'can_manage': can_manage,
    }
    
    return render(request, 'pages/submissions/cohort_submissions.html', context)