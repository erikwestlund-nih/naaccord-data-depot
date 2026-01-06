from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from depot.models import (
    CohortSubmission, Cohort, CohortMembership, Activity, 
    ActivityType, PrecheckRun, User, DataFileType
)
from django.db.models import Count, Q, Max
from django.utils import timezone
from datetime import timedelta


@login_required
def dashboard_page(request):
    """
    Dashboard view that adapts to user permissions.
    - NA Accord Administrators: See aggregate stats and all cohorts
    - Cohort Managers/Viewers: See their cohort-specific data
    """
    user = request.user

    # Only superusers and NA Accord Administrators see system overview
    # Note: is_administrator() checks for legacy "Administrators" group which should also see overview
    is_admin = user.is_superuser or user.is_na_accord_admin()

    # Get cohort status filter from request (default to 'active')
    cohort_status_filter = request.GET.get('cohort_status', 'active')

    # Get user's cohorts with submission counts
    if is_admin:
        # Admins can filter by all/active/inactive cohorts
        if cohort_status_filter == 'all':
            cohorts_query = Cohort.objects.all()
        else:
            cohorts_query = Cohort.objects.filter(status=cohort_status_filter)

        if user.username != 'ssuppor2':
            cohorts_query = cohorts_query.exclude(name='Scan Support')

        cohorts_with_stats = cohorts_query.annotate(
            submission_count=Count('submissions'),
            in_progress_submissions=Count(
                'submissions',
                filter=Q(submissions__status='in_progress')
            ),
            completed_submissions=Count(
                'submissions',
                filter=Q(submissions__status='completed')
            ),
            member_count=Count('cohortmembership'),
            last_activity=Max('submissions__updated_at')
        ).order_by('name')
    else:
        # Regular users can filter their cohorts by status
        if cohort_status_filter == 'all':
            cohorts_query = Cohort.objects.filter(cohortmembership__user=user)
        else:
            cohorts_query = Cohort.objects.filter(
                cohortmembership__user=user,
                status=cohort_status_filter
            )

        if user.username != 'ssuppor2':
            cohorts_query = cohorts_query.exclude(name='Scan Support')

        cohorts_with_stats = cohorts_query.annotate(
            submission_count=Count('submissions'),
            in_progress_submissions=Count(
                'submissions',
                filter=Q(submissions__status='in_progress')
            ),
            completed_submissions=Count(
                'submissions',
                filter=Q(submissions__status='completed')
            ),
            member_count=Count('cohortmembership'),
            last_activity=Max('submissions__updated_at')
        ).distinct().order_by('name')
    
    # Aggregate statistics (for administrators only)
    aggregate_stats = None
    if is_admin:
        total_users = User.objects.filter(is_active=True).count()
        total_cohorts = Cohort.objects.filter(status='active').count()
        total_submissions = CohortSubmission.objects.count()
        total_prechecks = PrecheckRun.objects.count()
        
        # Activity in last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_logins = Activity.objects.filter(
            activity_type=ActivityType.LOGIN,
            timestamp__gte=thirty_days_ago
        ).values('user').distinct().count()
        
        recent_submissions = CohortSubmission.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()
        
        recent_prechecks = PrecheckRun.objects.filter(
            created_at__gte=thirty_days_ago
        ).count()
        
        aggregate_stats = {
            'total_users': total_users,
            'total_cohorts': total_cohorts,
            'total_submissions': total_submissions,
            'total_prechecks': total_prechecks,
            'recent_logins': recent_logins,
            'recent_submissions': recent_submissions,
            'recent_prechecks': recent_prechecks,
        }
    
    # Get data file types for quick links
    data_file_types = DataFileType.objects.filter(is_active=True).order_by('order', 'name')[:5]

    # Get active submissions for user's cohorts
    active_submissions = []
    # Show active submissions if user can create or manage submissions, or is a cohort viewer/manager
    if user.can_create_submission() or user.can_manage_submissions or user.is_cohort_viewer() or user.is_cohort_manager():
        # Get user's cohorts
        if is_admin:
            # Admins see all active submissions (draft and in_progress)
            active_submissions = CohortSubmission.objects.filter(
                status__in=['draft', 'in_progress']
            ).select_related(
                'cohort', 'protocol_year', 'started_by'
            ).order_by('-updated_at')[:10]  # Show latest 10
        else:
            # Regular users see only their active cohorts' submissions
            user_cohorts = Cohort.objects.filter(
                cohortmembership__user=user,
                status='active'
            ).distinct()
            active_submissions = CohortSubmission.objects.filter(
                cohort__in=user_cohorts,
                status__in=['draft', 'in_progress']
            ).select_related(
                'cohort', 'protocol_year', 'started_by'
            ).order_by('-updated_at')[:10]  # Show latest 10

    # Get recent activity
    recent_activities = []
    if user.can_create_submission() or user.can_manage_submissions or user.is_cohort_viewer() or user.is_cohort_manager():
        # Build activity query based on user permissions
        activity_query = Activity.objects.select_related('user')

        if is_admin:
            # Admins see only meaningful user activities (very restrictive)
            recent_activities = activity_query.filter(
                # Only show these meaningful activity types
                activity_type__in=[
                    ActivityType.LOGIN,         # User logins are meaningful
                    ActivityType.USER_CREATE,
                    ActivityType.USER_MODIFY,
                    ActivityType.PERMISSION_CHANGE,
                    ActivityType.DATA_EXPORT,
                    ActivityType.FILE_DOWNLOAD,
                    ActivityType.REPORT_VIEW,
                ]
            ).union(
                # Include meaningful data operations on core business models
                activity_query.filter(
                    activity_type=ActivityType.DATA_CREATE  # Only creation events, not updates
                ).filter(
                    details__model__in=[
                        'CohortSubmission',     # User starts new submission
                        'DataTableFile',        # User uploads data files
                        'UploadedFile',         # User uploads attachments
                        'FileAttachment',       # User adds document attachments
                    ]
                )
            ).order_by('-timestamp')[:15]
        else:
            # Regular users see their own activities and activities for their active cohorts
            # Since cohort info is in details JSON field, we'll filter by user for now
            # TODO: Implement cohort-based filtering using details field
            user_cohorts = Cohort.objects.filter(
                cohortmembership__user=user,
                status='active'
            ).distinct()
            cohort_names = list(user_cohorts.values_list('name', flat=True))

            # Regular users see only their meaningful activities (very restrictive)
            recent_activities = activity_query.filter(
                user=user
            ).filter(
                # Only show meaningful activity types
                activity_type__in=[
                    ActivityType.LOGIN,         # User logins are meaningful
                    ActivityType.DATA_EXPORT,
                    ActivityType.FILE_DOWNLOAD,
                    ActivityType.REPORT_VIEW,
                ]
            ).union(
                # Include meaningful data operations on core business models
                activity_query.filter(
                    user=user,
                    activity_type=ActivityType.DATA_CREATE  # Only creation events, not updates
                ).filter(
                    details__model__in=[
                        'CohortSubmission',     # User starts new submission
                        'DataTableFile',        # User uploads data files
                        'UploadedFile',         # User uploads attachments
                        'FileAttachment',       # User adds document attachments
                    ]
                )
            ).order_by('-timestamp')[:15]

    context = {
        "title": "Dashboard",
        "is_admin": is_admin,
        "cohorts_with_stats": cohorts_with_stats,
        "aggregate_stats": aggregate_stats,
        "data_file_types": data_file_types,
        "active_submissions": active_submissions,
        "recent_activities": recent_activities,
        "cohort_status_filter": cohort_status_filter,
        "user_role": "Administrator" if is_admin else
                     "Cohort Manager" if user.is_cohort_manager() else
                     "Cohort Viewer" if user.is_cohort_viewer() else "User",
    }

    return render(request, "pages/dashboard.html", context)
