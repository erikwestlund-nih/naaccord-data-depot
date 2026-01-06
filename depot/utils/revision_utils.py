from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from depot.models import Revision


def get_object_history(obj):
    """Get all revisions for an object.
    
    Args:
        obj: Any model instance that has revision tracking
        
    Returns:
        QuerySet of Revision objects ordered by creation date (newest first)
    """
    ct = ContentType.objects.get_for_model(obj)
    return Revision.objects.filter(
        content_type=ct,
        object_id=obj.pk
    ).order_by('-created_at')


def get_user_activity(user, days=30):
    """Get user's recent activity.
    
    Args:
        user: User instance
        days: Number of days to look back (default: 30)
        
    Returns:
        QuerySet of Revision objects for the user's recent activity
    """
    since = timezone.now() - timedelta(days=days)
    return Revision.objects.filter(
        user=user,
        created_at__gte=since
    ).order_by('-created_at')


def get_model_changes(model_name, days=7):
    """Get recent changes for a specific model type.
    
    Args:
        model_name: String name of the model (e.g., 'CohortSubmission')
        days: Number of days to look back (default: 7)
        
    Returns:
        QuerySet of Revision objects for the model
    """
    since = timezone.now() - timedelta(days=days)
    return Revision.objects.filter(
        model_name=model_name,
        created_at__gte=since
    ).order_by('-created_at')


def get_submission_audit_trail(submission):
    """Get complete audit trail for a submission and all its files.
    
    Args:
        submission: CohortSubmission instance
        
    Returns:
        Dictionary with submission and file revisions
    """
    # Get submission revisions
    submission_revisions = get_object_history(submission)
    
    # Get all file revisions
    file_revisions = {}
    for file in submission.files.all():
        file_revisions[file.id] = get_object_history(file)
    
    return {
        'submission': submission_revisions,
        'files': file_revisions
    }


def format_revision_changes(revision):
    """Format revision changes for display.
    
    Args:
        revision: Revision instance
        
    Returns:
        List of formatted change strings
    """
    changes = []
    for field, change in revision.changes.items():
        old_val = change.get('old', 'None')
        new_val = change.get('new', 'None')
        changes.append(f"{field}: {old_val} → {new_val}")
    return changes


def get_field_history(obj, field_name):
    """Get the history of changes for a specific field.
    
    Args:
        obj: Model instance
        field_name: Name of the field to track
        
    Returns:
        List of tuples (timestamp, user, old_value, new_value)
    """
    history = []
    revisions = get_object_history(obj)
    
    for revision in revisions:
        if field_name in revision.changes:
            change = revision.changes[field_name]
            history.append((
                revision.created_at,
                revision.user,
                change.get('old'),
                change.get('new')
            ))
    
    return history