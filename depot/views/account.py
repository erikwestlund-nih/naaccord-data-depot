from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from depot.models import Activity, ActivityType
from django.db.models import Q


@login_required
def account_page(request):
    # Get recent meaningful activities for this user (very restrictive)
    activity_query = Activity.objects.filter(user=request.user).select_related('user')

    recent_activities = activity_query.filter(
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
            activity_type__in=[ActivityType.DATA_CREATE, ActivityType.DATA_UPDATE]
        ).filter(
            details__model__in=[
                'CohortSubmission',     # New submissions
                'DataTableFile',        # File uploads (when hash calculated)
                'UploadedFile',         # Attachment uploads
                'FileAttachment',       # Document attachments
            ]
        ).exclude(
            # Exclude routine field updates
            Q(details__fields_changed__contained_by=['updated_at', 'created_at']) |
            Q(details__fields_changed__exact=['updated_at']) |
            Q(details__fields_changed__exact=['created_at'])
        )
    ).order_by('-timestamp')[:10]
    
    return render(
        request,
        "pages/account.html",
        {
            "title": "Account",
            "recent_activities": recent_activities,
        },
    )
