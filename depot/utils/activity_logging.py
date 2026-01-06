"""
Utility functions for logging activities to the database.
"""
from depot.models import Activity, ActivityType


def log_access_denied(request, resource_type, resource_id, resource_name=None):
    """
    Log an access denied (403) event to the activity table for authenticated users only.

    Args:
        request: The Django request object
        resource_type: Type of resource (e.g., 'notebook', 'cohort', 'submission')
        resource_id: ID of the resource being accessed
        resource_name: Optional human-readable name of the resource
    """
    # Skip logging during tests to avoid foreign key issues
    # unless explicitly testing activity logging
    from django.conf import settings
    if getattr(settings, 'TESTING', False) and not getattr(settings, 'TEST_ACTIVITY_LOGGING', False):
        return

    # Only log to database for authenticated users
    if not request.user.is_authenticated:
        return
    
    metadata = {
        'resource_type': resource_type,
        'resource_id': resource_id,
        'reason': 'permission_denied'
    }
    
    if resource_name:
        metadata['resource_name'] = resource_name
    
    Activity.objects.create(
        user=request.user,
        activity_type=ActivityType.PAGE_ACCESS,
        success=False,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        session_id=request.session.session_key if hasattr(request, 'session') else None,
        path=request.path,
        method=request.method,
        status_code=403,
        details=metadata  # JSONField accepts dict directly, no need to json.dumps
    )