"""
Permission decorators and helper functions for cohort-based access control.
"""
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from depot.models import Cohort, CohortMembership


def cohort_permission_required(permission='view', cohort_param='cohort_id'):
    """
    Decorator to check cohort permissions for function-based views.
    
    Args:
        permission: Required permission level ('view', 'edit', 'manage')
        cohort_param: Name of the parameter containing cohort ID
    
    Usage:
        @login_required
        @cohort_permission_required('edit', cohort_param='cohort_id')
        def my_view(request, cohort_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Get cohort ID from kwargs
            cohort_id = kwargs.get(cohort_param)
            if not cohort_id:
                raise PermissionDenied("No cohort specified.")
            
            # Get cohort object
            cohort = get_object_or_404(Cohort, pk=cohort_id)
            
            # Check permission
            user = request.user
            has_permission = False
            
            if permission in ['edit', 'manage']:
                # Edit/manage permission
                if user.is_administrator() or user.is_data_manager():
                    has_permission = True
                elif user.groups.filter(name='Coordinators').exists():
                    has_permission = CohortMembership.objects.filter(
                        user=user,
                        cohort=cohort
                    ).exists()
            else:
                # View permission
                if user.is_administrator() or user.is_data_manager():
                    has_permission = True
                else:
                    has_permission = CohortMembership.objects.filter(
                        user=user,
                        cohort=cohort
                    ).exists()
            
            if not has_permission:
                raise PermissionDenied(
                    f"You don't have {permission} permission for this cohort."
                )
            
            # Add cohort to request for convenience
            request.cohort = cohort
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def filter_cohorts_for_user(user):
    """
    Get cohorts that the user has access to.
    
    Args:
        user: User object
        
    Returns:
        QuerySet of Cohort objects
    """
    # Administrators and data managers see all cohorts
    if user.is_administrator() or user.is_data_manager():
        return Cohort.objects.all()
    
    # Other users see only their assigned cohorts
    return user.cohorts.filter(cohortmembership__user=user)


def can_user_edit_cohort(user, cohort):
    """
    Check if user can edit/write data for a cohort.
    
    Args:
        user: User object
        cohort: Cohort object
        
    Returns:
        Boolean indicating edit permission
    """
    # Administrators and data managers can edit all cohorts
    if user.is_administrator() or user.is_data_manager():
        return True
    
    # Coordinators can edit their assigned cohorts
    if user.groups.filter(name='Coordinators').exists():
        return CohortMembership.objects.filter(
            user=user,
            cohort=cohort
        ).exists()
    
    # Researchers and Viewers have read-only access
    return False


def can_user_view_cohort(user, cohort):
    """
    Check if user can view a cohort.
    
    Args:
        user: User object
        cohort: Cohort object
        
    Returns:
        Boolean indicating view permission
    """
    # Administrators and data managers can view all cohorts
    if user.is_administrator() or user.is_data_manager():
        return True
    
    # Check membership for other users
    return CohortMembership.objects.filter(
        user=user,
        cohort=cohort
    ).exists()


def add_cohort_permission_context(request):
    """
    Add cohort permission context to request for use in templates.
    
    Args:
        request: HttpRequest object
        
    Returns:
        Dictionary with permission context
    """
    if not request.user.is_authenticated:
        return {
            'user_cohorts': Cohort.objects.none(),
            'is_administrator': False,
            'is_data_manager': False,
            'can_create_submissions': False,
        }
    
    user_cohorts = filter_cohorts_for_user(request.user)
    
    return {
        'user_cohorts': user_cohorts,
        'is_administrator': request.user.is_administrator(),
        'is_data_manager': request.user.is_data_manager(),
        'can_create_submissions': (
            request.user.is_administrator() or
            request.user.is_data_manager() or
            request.user.groups.filter(name='Coordinators').exists()
        ),
    }


def require_cohort_membership(view_func):
    """
    Simple decorator to ensure user has at least one cohort membership.
    
    Usage:
        @login_required
        @require_cohort_membership
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required.")
        
        # Admins and data managers don't need cohort membership
        if request.user.is_administrator() or request.user.is_data_manager():
            return view_func(request, *args, **kwargs)
        
        # Check if user has any cohort memberships
        if not request.user.cohorts.exists():
            raise PermissionDenied(
                "You must be assigned to at least one cohort to access this resource."
            )
        
        return view_func(request, *args, **kwargs)
    return wrapper