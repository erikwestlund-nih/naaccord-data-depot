# depot/views/cohorts.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from depot.models import Cohort
from depot.utils.decorators import filter_cohorts_for_user


@login_required
def cohorts_page(request):
    """
    Display cohorts that the user has permission to view.
    """
    # Get cohorts based on user permissions
    user_cohorts = filter_cohorts_for_user(request.user)
    
    # Build cohorts list
    cohorts = []
    for cohort in user_cohorts.order_by('name'):
        # Hide "Scan Support" cohort for everyone except scan support user (ssuppor2)
        if cohort.name == "Scan Support" and request.user.username != "ssuppor2":
            continue

        cohorts.append({
            'id': cohort.id,
            'name': cohort.name,
            'type': cohort.get_type_display() if hasattr(cohort, 'get_type_display') else cohort.type,
            'status': cohort.get_status_display() if hasattr(cohort, 'get_status_display') else cohort.status,
            'member_count': cohort.users.count(),
        })
    
    # Determine if user can add new cohorts (admins and data managers)
    can_add_cohorts = request.user.is_administrator() or request.user.is_data_manager()

    # Try to get admin add URL if it exists
    add_url = None
    if can_add_cohorts:
        try:
            add_url = reverse("admin:depot_cohort_add")
        except Exception:
            # Admin URL doesn't exist - cohorts managed via CSV/fixtures
            pass

    return render(
        request,
        "pages/cohorts.html",
        {
            "title": "Cohorts",
            "cohorts": cohorts,
            "add_url": add_url,
            "can_add_cohorts": can_add_cohorts,
            "is_administrator": request.user.is_administrator(),
            "is_data_manager": request.user.is_data_manager(),
        },
    )
