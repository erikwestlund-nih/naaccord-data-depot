"""
Mock SAML Authentication Backend for Development
Simulates Shibboleth/SAML authentication flow without requiring actual IdP
"""
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.conf import settings
from depot.models import Cohort, CohortMembership
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class MockSAMLBackend(BaseBackend):
    """
    Mock SAML backend for development - simulates SAML responses
    with predefined test users and their attributes
    """
    
    # Test user configurations matching production SAML attributes
    MOCK_USERS = {
        'admin@test.edu': {
            'first_name': 'Admin',
            'last_name': 'User',
            'display_name': 'Admin User',
            'is_staff': True,
            'is_superuser': True,
            'cohorts': [1, 2, 3],  # Access to multiple cohorts
            'role': 'admin',
            'affiliation': ['staff', 'member'],
            'eppn': 'admin@test.edu',  # eduPersonPrincipalName
        },
        'researcher@test.edu': {
            'first_name': 'Research',
            'last_name': 'User',
            'display_name': 'Research User',
            'is_staff': False,
            'is_superuser': False,
            'cohorts': [1],  # Single cohort access
            'role': 'researcher',
            'affiliation': ['faculty', 'member'],
            'eppn': 'researcher@test.edu',
        },
        'coordinator@test.edu': {
            'first_name': 'Coordinator',
            'last_name': 'User',
            'display_name': 'Coordinator User',
            'is_staff': False,
            'is_superuser': False,
            'cohorts': [2],
            'role': 'coordinator',
            'affiliation': ['staff', 'member'],
            'eppn': 'coordinator@test.edu',
        },
        'viewer@test.edu': {
            'first_name': 'Viewer',
            'last_name': 'User',
            'display_name': 'Viewer User',
            'is_staff': False,
            'is_superuser': False,
            'cohorts': [1],
            'role': 'viewer',
            'affiliation': ['member'],
            'eppn': 'viewer@test.edu',
        },
        # Generic test users for different institutions
        'user@jhu.edu': {
            'first_name': 'Johns Hopkins',
            'last_name': 'User',
            'display_name': 'JHU Test User',
            'is_staff': False,
            'is_superuser': False,
            'cohorts': [5],  # JHHCC cohort
            'role': 'member',
            'affiliation': ['member'],
            'eppn': 'user@jhu.edu',
        },
        'user@ucsd.edu': {
            'first_name': 'UCSD',
            'last_name': 'User',
            'display_name': 'UCSD Test User',
            'is_staff': False,
            'is_superuser': False,
            'cohorts': [13],  # UCSD cohort
            'role': 'member',
            'affiliation': ['member'],
            'eppn': 'user@ucsd.edu',
        },
    }
    
    def authenticate(self, request, username=None, **kwargs):
        """
        Authenticate user based on email stored in session
        This simulates the SAML assertion response
        """
        if not settings.DEBUG:
            return None
        
        # Get email from session (set by login view) or username param
        email = None
        if request and hasattr(request, 'session'):
            email = request.session.get('pending_email', username)
        else:
            email = username
            
        if not email:
            return None
            
        # Check if this is a known test user
        if email not in self.MOCK_USERS:
            # For unknown emails in dev, create a basic user
            if settings.DEBUG and email and '@' in email:
                logger.info("Creating generic mock user")
                mock_data = {
                    'first_name': email.split('@')[0].title(),
                    'last_name': 'User',
                    'display_name': f'{email.split("@")[0].title()} User',
                    'is_staff': False,
                    'is_superuser': False,
                    'cohorts': [1],  # Default to first cohort
                    'role': 'member',
                    'affiliation': ['member'],
                    'eppn': email,
                }
            else:
                return None
        else:
            mock_data = self.MOCK_USERS[email]
        
        # Get or create user
        # Generate unique username to avoid conflicts
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
        
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': username,
                'first_name': mock_data['first_name'],
                'last_name': mock_data['last_name'],
                'is_staff': mock_data.get('is_staff', False),
                'is_superuser': mock_data.get('is_superuser', False),
            }
        )
        
        if created:
            logger.info(f"Created new user from mock SAML: user_id {user.id}")
        else:
            # Update user attributes on each login (simulating SAML refresh)
            user.first_name = mock_data['first_name']
            user.last_name = mock_data['last_name']
            user.is_staff = mock_data.get('is_staff', False)
            user.is_superuser = mock_data.get('is_superuser', False)
            user.save()
            logger.info(f"Updated existing user from mock SAML: user_id {user.id}")
        
        # Update cohort memberships (simulating SAML attribute mapping)
        self._update_cohort_memberships(user, mock_data)
        
        # Clear the pending email from session
        if request and hasattr(request, 'session'):
            request.session.pop('pending_email', None)
            request.session.pop('pending_institution', None)
        
        return user
    
    def _update_cohort_memberships(self, user, mock_data):
        """
        Update user's cohort memberships based on SAML attributes
        This simulates attribute-based authorization
        """
        cohort_ids = mock_data.get('cohorts', [])
        role = mock_data.get('role', 'member')
        
        # Remove old memberships not in current attributes
        CohortMembership.objects.filter(user=user).exclude(
            cohort_id__in=cohort_ids
        ).delete()
        
        # Add/update current memberships
        for cohort_id in cohort_ids:
            try:
                cohort = Cohort.objects.get(id=cohort_id)
                membership, created = CohortMembership.objects.get_or_create(
                    user=user,
                    cohort=cohort
                )
                    
                if created:
                    logger.info(f"Added user_id {user.id} to cohort {cohort.name} with role: {role}")
                    
            except Cohort.DoesNotExist:
                logger.warning(f"Cohort {cohort_id} does not exist for user_id {user.id}")
    
    def get_user(self, user_id):
        """
        Required method for authentication backend
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None