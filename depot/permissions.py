"""
Permission checking utilities for NA-ACCORD depot.
Centralizes authorization logic for submissions and cohorts.
"""
from depot.models import CohortMembership


class SubmissionPermissions:
    """Handles permission checks for submission-related operations."""
    
    @staticmethod
    def can_view(user, submission):
        """Check if user can view a submission."""
        # NA Accord Administrators can view all submissions
        if user.is_na_accord_admin() or user.is_administrator():
            return True
        
        # Cohort Managers and Viewers can only view submissions for their cohorts
        if user.is_cohort_manager() or user.is_cohort_viewer() or user.is_data_manager():
            return CohortMembership.objects.filter(
                user=user, 
                cohort=submission.cohort
            ).exists()
        
        # Check if user is a member of the submission's cohort
        return CohortMembership.objects.filter(
            user=user, 
            cohort=submission.cohort
        ).exists()
    
    @staticmethod
    def can_edit(user, submission):
        """Check if user can edit a submission (upload files, add comments)."""
        # Cannot edit if submission is finalized
        if submission.status in ['signed_off', 'closed']:
            return False
        
        # NA Accord Administrators can edit all submissions
        if user.is_na_accord_admin() or user.is_administrator():
            return True
        
        # Cohort Managers can edit submissions for their cohorts
        if user.is_cohort_manager() or user.is_data_manager():
            return CohortMembership.objects.filter(
                user=user, 
                cohort=submission.cohort
            ).exists()
        
        # Cohort Viewers cannot edit
        return False
    
    @staticmethod
    def can_manage(user, submission):
        """Check if user can manage a submission (approve files, reopen)."""
        # NA Accord Administrators can manage all submissions
        if user.is_na_accord_admin() or user.is_administrator():
            return True
        
        # Cohort Managers can manage submissions for their cohorts
        if user.is_cohort_manager() or user.is_data_manager():
            return CohortMembership.objects.filter(
                user=user, 
                cohort=submission.cohort
            ).exists()
        
        return False
    
    @staticmethod
    def can_sign_off(user, submission):
        """Check if user can sign off on submission files."""
        # Same as edit permission - only managers can sign off
        return SubmissionPermissions.can_edit(user, submission)
    
    @staticmethod
    def can_delete(user, submission):
        """Check if user can delete a submission."""
        # Only NA Accord administrators can delete
        return (
            user.is_na_accord_admin() or  # New simplified check
            # Legacy fallback during transition
            user.is_administrator()
        )


class CohortPermissions:
    """Handles permission checks for cohort-related operations."""
    
    @staticmethod
    def can_view(user, cohort):
        """Check if user can view a cohort."""
        return (
            user.is_na_accord_admin() or  # New simplified check
            user.is_cohort_manager() or   # New simplified check
            user.is_cohort_viewer() or    # New simplified check
            # Legacy fallback during transition
            user.is_administrator() or
            user.is_data_manager() or
            CohortMembership.objects.filter(
                user=user, 
                cohort=cohort
            ).exists()
        )
    
    @staticmethod
    def can_create_submission(user, cohort):
        """Check if user can create a submission for a cohort."""
        return (
            user.is_na_accord_admin() or  # New simplified check
            user.is_cohort_manager() or   # New simplified check
            # Legacy fallback during transition
            user.is_administrator() or
            user.is_data_manager() or
            CohortMembership.objects.filter(
                user=user, 
                cohort=cohort
            ).exists()  # Any cohort member can create submissions
        )
    
    @staticmethod
    def can_manage(user, cohort):
        """Check if user can manage a cohort (add members, change settings)."""
        return (
            user.is_na_accord_admin() or  # New simplified check - only NA Accord admins can manage cohorts
            # Legacy fallback during transition
            user.is_administrator() or
            user.is_data_manager()
        )