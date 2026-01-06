"""
Real SAML Authentication Backend using djangosaml2
Handles authentication via Docker SimpleSAMLphp IdP or production Shibboleth
"""
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.conf import settings
from depot.models import Cohort, CohortMembership
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class SAMLBackend(BaseBackend):
    """
    Real SAML backend for both development (Docker IdP) and production (Shibboleth)
    Processes actual SAML assertions from djangosaml2
    """
    
    def authenticate(self, request, session_info=None, **kwargs):
        """
        Authenticate user based on SAML assertion data
        session_info contains attributes from the SAML IdP
        """
        logger.info("=== SAMLBackend.authenticate() called ===")
        logger.info(f"session_info provided: {session_info is not None}")

        if not session_info:
            logger.warning("No session_info provided to SAMLBackend")
            return None

        # Extract user data from SAML assertion
        attributes = session_info.get('ava', {})  # Attribute Value Assertion

        logger.info(f"SAML attributes received: {list(attributes.keys())}")
        logger.info(f"Full attributes: {attributes}")
        
        # Get primary identifier (email) - check multiple possible attribute names
        # JHU Shibboleth uses eduPersonPrincipalName for the canonical email (@johnshopkins.edu)
        # while 'mail' contains the internal email (@jhmi.edu)
        email = self._get_attribute_value(attributes, ['eduPersonPrincipalName', 'email', 'emailAddress', 'mail', 'Email'])
        if not email:
            # Try to get from pending_email in session (set by sign_in view)
            email = request.session.get('pending_email')
            if not email:
                logger.error("No email found in SAML assertion. Check SAML configuration.")
                return None

        # Log without PII - email will be sanitized by middleware
        logger.info("Processing SAML authentication for user")
        logger.debug("SAML attributes received (sanitized by middleware)")
        
        # Try to find existing user by SSO email first, then by regular email
        # DO NOT auto-create users - they must be pre-provisioned
        user = None

        # First try: Match on sso_email (SAML-returned email)
        try:
            user = User.objects.get(sso_email=email)
            logger.info(f"Found user by sso_email: user_id {user.id}")
        except User.DoesNotExist:
            # Second try: Match on email (user-facing email)
            try:
                user = User.objects.get(email=email)
                logger.info(f"Found user by email: user_id {user.id}")
            except User.DoesNotExist:
                logger.warning(f"Access denied: No user found for SAML email: {email}")
                return None  # User not found - deny access

        # Update SSO email only - names are managed in the database
        user.sso_email = email  # Store SAML-returned email
        user.save()
        logger.info(f"Updated sso_email: user_id {user.id}")

        # NOTE: Permissions, cohorts, and groups are managed within Django
        # SAML is only used for authentication, not authorization
        # NOTE: Login activity is logged automatically via Django signals

        return user
    
    def _get_attribute_value(self, attributes, keys):
        """
        Get first non-empty attribute value from a list of possible keys
        SAML attributes come as lists, so we need the first value
        """
        for key in keys:
            if key in attributes and attributes[key]:
                value = attributes[key]
                return value[0] if isinstance(value, list) else value
        return None
    
    def _extract_user_profile(self, attributes):
        """
        Extract basic user profile information from SAML attributes.
        Only extracts name and profile info - NO permissions or role data.
        """
        # Try to get first name
        first_name = self._get_attribute_value(attributes, ['givenName', 'firstName', 'given_name'])
        if not first_name:
            # Try to extract from displayName
            display_name = self._get_attribute_value(attributes, ['displayName', 'cn', 'commonName'])
            if display_name:
                first_name = display_name.split(' ')[0]
            else:
                first_name = 'User'

        # Try to get last name
        last_name = self._get_attribute_value(attributes, ['sn', 'surname', 'lastName', 'last_name'])
        if not last_name:
            # Try to extract from displayName
            display_name = self._get_attribute_value(attributes, ['displayName', 'cn', 'commonName'])
            if display_name:
                parts = display_name.split(' ')
                last_name = ' '.join(parts[1:]) if len(parts) > 1 else 'User'
            else:
                last_name = 'User'

        return {
            'first_name': first_name,
            'last_name': last_name,
        }
    
    def get_user(self, user_id):
        """
        Required method for authentication backend
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None