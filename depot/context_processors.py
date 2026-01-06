import json
import urllib.error
import urllib.request

from django.conf import settings
from django.urls import resolve


def debug(request):
    """Expose the DEBUG setting to the templates."""
    return {"debug": settings.DEBUG}


def get_vite_js_path(asset_name):
    """Reads the Vite manifest.json from the static/.vite/ directory and returns the hashed asset file path."""
    manifest_path = settings.BASE_DIR / "static/.vite/manifest.json"

    try:
        with open(manifest_path) as manifest_file:
            manifest = json.load(manifest_file)
        return manifest[asset_name]["file"]
    except (FileNotFoundError, KeyError):
        return None


def get_vite_css_paths(asset_name):
    """Reads the Vite manifest.json from the static/.vite/ directory and returns ALL hashed CSS file paths."""
    manifest_path = settings.BASE_DIR / "static/.vite/manifest.json"

    try:
        with open(manifest_path) as manifest_file:
            manifest = json.load(manifest_file)
        return manifest[asset_name].get("css", [])
    except (FileNotFoundError, KeyError):
        return []


def vite_asset_processor(request):
    import os

    # Vite runs on host - containers use host.docker.internal
    if os.environ.get('SERVER_ROLE'):
        vite_base_url = "http://localhost:3000"  # Browser accesses via localhost
    else:
        vite_base_url = "http://localhost:3000"

    return {
        "vite_running": vite_running(),
        "vite_base_url": vite_base_url,
        "app_js": get_vite_js_path("resources/js/app.js"),
        "app_css_files": get_vite_css_paths("resources/js/app.js"),
    }


def vite_running():
    """Check if Vite dev server is running locally."""
    import os

    # When running in Docker, use host.docker.internal to reach host
    # When running locally, use localhost
    if os.environ.get('SERVER_ROLE'):
        url = "http://host.docker.internal:3000/@vite/client"
    else:
        url = "http://localhost:3000/@vite/client"

    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.getcode() == 200
    except (urllib.error.URLError, urllib.error.HTTPError):
        return False


def add_url_name(request):
    try:
        return {"url_name": resolve(request.path_info).url_name}
    except Exception:
        # Path may not be in Django's URL patterns (e.g., /simplesaml/ proxied to external service)
        return {"url_name": None}


def user_cohorts(request):
    """Add user's active cohorts to the template context - only those with submissions."""
    if request.user.is_authenticated:
        from depot.models import CohortMembership, CohortSubmission, Cohort

        # Get cohort IDs that have ANY submissions (all-time, not just recent)
        cohort_ids_with_submissions = CohortSubmission.objects.values_list('cohort_id', flat=True).distinct()

        # For admins/superusers: show all active cohorts with submissions
        # For regular users: show only their assigned cohorts with submissions
        if request.user.is_superuser or request.user.is_na_accord_admin():
            # Admins see all active cohorts that have submissions
            cohort_queryset = Cohort.objects.filter(
                status='active',
                id__in=cohort_ids_with_submissions
            ).order_by('name')
        else:
            # Regular users see only their assigned cohorts with submissions
            memberships = CohortMembership.objects.filter(
                user=request.user,
                cohort__status='active',
                cohort_id__in=cohort_ids_with_submissions
            ).select_related('cohort').order_by('cohort__name')
            cohort_queryset = [membership.cohort for membership in memberships]

        cohorts = []
        for cohort in cohort_queryset:
            # Get first letters for the badge (max 2 characters)
            name_parts = cohort.name.split()
            if len(name_parts) >= 2:
                initials = (name_parts[0][0] + name_parts[1][0]).upper()
            else:
                initials = cohort.name[:2].upper()

            cohorts.append({
                'id': cohort.id,
                'name': cohort.name,
                'initials': initials,
                'type': cohort.type,
                'status': cohort.status,
            })

        return {"user_cohorts": cohorts}
    return {"user_cohorts": []}


def user_submissions(request):
    """Add user's accessible submissions to the template context for sidebar navigation."""
    if request.user.is_authenticated:
        from depot.models import CohortMembership, CohortSubmission

        # For admins/superusers: show all active submissions
        # For regular users: show only submissions for their assigned cohorts
        if request.user.is_superuser or request.user.is_na_accord_admin():
            submissions = CohortSubmission.objects.filter(
                cohort__status='active'
            ).select_related('cohort', 'protocol_year').order_by('cohort__name', '-protocol_year__year')
        else:
            # Get user's cohort IDs
            user_cohort_ids = CohortMembership.objects.filter(
                user=request.user,
                cohort__status='active'
            ).values_list('cohort_id', flat=True)

            submissions = CohortSubmission.objects.filter(
                cohort_id__in=user_cohort_ids
            ).select_related('cohort', 'protocol_year').order_by('cohort__name', '-protocol_year__year')

        # Get current submission ID from URL if viewing a submission
        current_submission_id = None
        try:
            resolved = resolve(request.path_info)
            if resolved.url_name in ['submission_detail', 'submission_table_manage']:
                submission_id = resolved.kwargs.get('submission_id')
                if submission_id:
                    current_submission_id = int(submission_id)
        except Exception:
            pass

        return {
            "user_submissions": submissions,
            "current_submission_id": current_submission_id,
        }
    return {"user_submissions": [], "current_submission_id": None}
