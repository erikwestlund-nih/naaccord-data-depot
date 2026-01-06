"""
Cohort detail view for viewing cohort information.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from depot.models import Cohort, CohortMembership, CohortSubmission
from depot.utils.decorators import can_user_view_cohort
from depot.utils.activity_logging import log_access_denied
import logging

logger = logging.getLogger(__name__)


@login_required
def cohort_detail(request, cohort_id):
    """
    Display detailed view of a cohort with members and recent submissions.
    """
    cohort = get_object_or_404(Cohort, pk=cohort_id)
    
    # Check if user can view this cohort
    if not can_user_view_cohort(request.user, cohort):
        # Log to both application logs and database
        logger.warning(
            f"Access denied: User {request.user.email} attempted to view cohort {cohort_id} ({cohort.name}) "
            f"from IP {request.META.get('REMOTE_ADDR', 'unknown')}"
        )
        log_access_denied(request, 'cohort', cohort_id, cohort.name)
        return render(request, 'errors/403.html', status=403)
    
    # Get cohort members
    memberships = CohortMembership.objects.filter(cohort=cohort).select_related('user')
    members = []
    for membership in memberships:
        members.append({
            'name': membership.user.get_full_name() or membership.user.username,
            'email': membership.user.email,
            'groups': ', '.join([g.name for g in membership.user.groups.all()]) or 'None',
        })
    
    # Get recent submissions for this cohort
    recent_submissions_qs = CohortSubmission.objects.filter(
        cohort=cohort
    ).select_related('protocol_year', 'started_by').order_by('-created_at')[:10]
    
    # Add permission info for each submission
    from depot.permissions import SubmissionPermissions
    recent_submissions = []
    for submission in recent_submissions_qs:
        recent_submissions.append({
            'submission': submission,
            'can_manage': SubmissionPermissions.can_manage(request.user, submission)
        })
    
    # Check if user can edit cohort (only NA Accord Administrators)
    can_edit_cohort = request.user.is_na_accord_admin()
    
    # Check if user can create submissions for this cohort
    from depot.permissions import CohortPermissions
    can_create_submission = CohortPermissions.can_create_submission(request.user, cohort)
    
    context = {
        'cohort': cohort,
        'members': members,
        'member_count': len(members),
        'recent_submissions': recent_submissions,
        'can_edit_cohort': can_edit_cohort,
        'can_create_submission': can_create_submission,
    }
    
    return render(request, 'pages/cohort_detail.html', context)