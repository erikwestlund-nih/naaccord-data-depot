from django.contrib.auth.models import AbstractUser
from django.db import models

from depot.gates import member_of
from depot.models import BaseModel
from depot.constants.groups import Groups


class User(AbstractUser, BaseModel):
    # SSO email returned by SAML provider (may differ from user's email)
    # Example: user logs in with ewestlu1@jh.edu, but SAML returns ewestlu1@johnshopkins.edu
    sso_email = models.EmailField(
        max_length=254,
        blank=True,
        null=True,
        unique=True,
        help_text="Email address returned by SAML provider during authentication"
    )

    # Override inherited fields to provide clearer labels for NA-ACCORD context
    is_staff = models.BooleanField(
        "NA-ACCORD staff",
        default=False,
        help_text="Grants access to this admin site and allows managing all cohorts and submissions."
    )
    is_active = models.BooleanField(
        "Active account",
        default=True,
        help_text="Allows this user to log in. Uncheck instead of deleting accounts."
    )

    @property
    def can_manage_submissions(self):
        return (
            self.is_superuser or 
            self.is_na_accord_admin() or
            self.is_cohort_manager() or
            member_of(self, "Data Managers")  # Legacy support
        )
    
    def is_administrator(self):
        """Check if user is in Administrators group (legacy compatibility)."""
        # Transition logic - check both new and legacy groups
        return (
            self.is_na_accord_admin() or
            self.groups.filter(name=Groups.LEGACY_ADMINISTRATORS).exists()
        )
    
    def is_data_manager(self):
        """Check if user is in Data Managers group (legacy compatibility)."""
        # Transition logic - check both new and legacy groups
        return (
            self.is_na_accord_admin() or
            self.groups.filter(name=Groups.LEGACY_DATA_MANAGERS).exists()
        )
    
    def is_researcher(self):
        """Check if user is in Researchers group (legacy compatibility)."""
        # Transition logic - check both new and legacy groups
        return (
            self.is_cohort_manager() or
            self.groups.filter(name=Groups.LEGACY_RESEARCHERS).exists()
        )
    
    def can_approve_files(self):
        """Check if user can approve submission files."""
        return self.is_data_manager() or self.is_administrator()
    
    def can_reopen_submission(self):
        """Check if user can reopen a submission."""
        return self.is_administrator()
    
    def can_create_submission(self):
        """Check if user can create new submissions."""
        return (
            self.groups.filter(name=Groups.LEGACY_COORDINATORS).exists() or
            self.is_cohort_manager() or  # New logic
            self.is_researcher() or 
            self.is_data_manager() or 
            self.is_administrator()
        )

    # New simplified permission methods
    def is_na_accord_admin(self):
        """Check if user is in NA Accord Administrators group."""
        return self.groups.filter(name=Groups.NA_ACCORD_ADMINISTRATORS).exists()
    
    def is_cohort_manager(self):
        """Check if user is in Cohort Managers group."""
        return self.groups.filter(name=Groups.COHORT_MANAGERS).exists()
    
    def is_cohort_viewer(self):
        """Check if user is in Cohort Viewers group."""
        return self.groups.filter(name=Groups.COHORT_VIEWERS).exists()

    def __str__(self):
        return self.username
