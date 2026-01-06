"""
Permission mixins for cohort-based access control.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db.models import Q
from depot.models import Cohort, CohortMembership


class CohortPermissionMixin(LoginRequiredMixin):
    """
    Mixin to handle cohort-based permissions for views.
    
    Provides:
    - Automatic queryset filtering based on user's cohort membership
    - Permission checking for view/edit/manage operations
    - Helper methods for permission context in templates
    
    Usage:
    - Inherit this in your view class
    - Set cohort_field_name to specify the field name for cohort filtering (default: 'cohort')
    - Set permission_required to 'view', 'edit', or 'manage' (default: 'view')
    - Override get_cohort_object() for custom cohort lookup logic
    """
    
    cohort_field_name = 'cohort'  # Field name for cohort filtering in queryset
    permission_required = 'view'   # Required permission level
    
    def get_user_cohorts(self):
        """
        Get cohorts the current user has access to.
        
        Returns:
            QuerySet of Cohort objects the user can access
        """
        user = self.request.user
        
        # Administrators and data managers see all cohorts
        if user.is_administrator() or user.is_data_manager():
            return Cohort.objects.all()
        
        # Other users see only their assigned cohorts
        return user.cohorts.filter(cohortmembership__user=user)
    
    def can_edit_cohort(self, cohort):
        """
        Check if user can edit/write data for a cohort.
        
        Args:
            cohort: Cohort object to check permissions for
            
        Returns:
            Boolean indicating edit permission
        """
        user = self.request.user
        
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
    
    def can_view_cohort(self, cohort):
        """
        Check if user can view a cohort.
        
        Args:
            cohort: Cohort object to check permissions for
            
        Returns:
            Boolean indicating view permission
        """
        user = self.request.user
        
        # Administrators and data managers can view all cohorts
        if user.is_administrator() or user.is_data_manager():
            return True
        
        # Check membership for other users
        return CohortMembership.objects.filter(
            user=user,
            cohort=cohort
        ).exists()
    
    def has_cohort_permission(self, cohort, permission='view'):
        """
        Check if user has specific permission for a cohort.
        
        Args:
            cohort: Cohort object to check permissions for
            permission: Required permission ('view', 'edit', 'manage')
            
        Returns:
            Boolean indicating permission
        """
        if permission in ['edit', 'manage']:
            return self.can_edit_cohort(cohort)
        return self.can_view_cohort(cohort)
    
    def filter_queryset_by_cohort(self, queryset):
        """
        Filter a queryset by user's cohort permissions.
        
        Args:
            queryset: QuerySet to filter
            
        Returns:
            Filtered QuerySet
        """
        user = self.request.user
        
        # Skip filtering for admins and data managers
        if user.is_administrator() or user.is_data_manager():
            return queryset
        
        # Filter by user's cohorts
        user_cohorts = self.get_user_cohorts()
        
        # Handle nested cohort relationships (e.g., submission__cohort)
        filter_kwargs = {f'{self.cohort_field_name}__in': user_cohorts}
        return queryset.filter(**filter_kwargs)
    
    def get_queryset(self):
        """
        Override to automatically filter queryset by user's cohort permissions.
        """
        queryset = super().get_queryset()
        return self.filter_queryset_by_cohort(queryset)
    
    def get_cohort_object(self):
        """
        Get the cohort object for permission checking.
        Override this for custom cohort lookup logic.
        
        Returns:
            Cohort object or None
        """
        # Try to get cohort from URL kwargs
        cohort_id = self.kwargs.get('cohort_id') or self.kwargs.get('pk')
        if cohort_id:
            # If this is a Cohort view
            if hasattr(self, 'model') and self.model == Cohort:
                return get_object_or_404(Cohort, pk=cohort_id)
            # If this is a related model view with cohort_id
            return get_object_or_404(Cohort, pk=cohort_id)
        
        # Try to get cohort from object (for UpdateView, DetailView)
        if hasattr(self, 'get_object'):
            obj = self.get_object()
            if hasattr(obj, self.cohort_field_name):
                return getattr(obj, self.cohort_field_name)
        
        return None
    
    def dispatch(self, request, *args, **kwargs):
        """
        Check permissions before dispatching the request.
        """
        # Get cohort for permission checking
        cohort = self.get_cohort_object()
        
        if cohort:
            # Check permission based on required level
            if not self.has_cohort_permission(cohort, self.permission_required):
                raise PermissionDenied(
                    f"You don't have {self.permission_required} permission for this cohort."
                )
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """
        Add permission context for templates.
        """
        context = super().get_context_data(**kwargs)
        
        # Add user's cohorts to context
        context['user_cohorts'] = self.get_user_cohorts()
        
        # Add permission flags for current cohort if available
        cohort = self.get_cohort_object()
        if cohort:
            context['can_edit_cohort'] = self.can_edit_cohort(cohort)
            context['can_view_cohort'] = self.can_view_cohort(cohort)
        
        # Add global permission flags
        context['is_administrator'] = self.request.user.is_administrator()
        context['is_data_manager'] = self.request.user.is_data_manager()
        
        return context