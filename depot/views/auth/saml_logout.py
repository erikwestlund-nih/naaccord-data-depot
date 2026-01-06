"""
SAML-aware logout that performs Single Logout (SLO)
"""
from django.http import HttpResponseRedirect
from django.contrib.auth import logout as django_logout
from django.urls import reverse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def saml_logout_view(request):
    """
    Logout view that handles both SAML and local logout.
    
    If SAML is enabled and user has a SAML session, initiate SAML Single Logout.
    Otherwise, just do a local Django logout.
    """
    # Check if we should use SAML logout
    use_saml = getattr(settings, 'USE_DOCKER_SAML', False) or getattr(settings, 'USE_MOCK_SAML', False)
    
    if use_saml and hasattr(request, 'saml_session'):
        # Initiate SAML Single Logout
        logger.info(f"Initiating SAML logout for user ID: {request.user.id if request.user.is_authenticated else 'anonymous'}")
        
        # Redirect to djangosaml2 logout URL which will handle SLO
        return HttpResponseRedirect(reverse('saml2_logout'))
    else:
        # Just do local logout
        logger.info(f"Performing local logout for user ID: {request.user.id if request.user.is_authenticated else 'anonymous'}")
        django_logout(request)
        return HttpResponseRedirect(reverse("auth.sign_in"))


def saml_logout_complete(request):
    """
    Called after SAML Single Logout completes.
    This ensures the Django session is also cleared.
    """
    logger.info("SAML logout complete, clearing Django session")
    django_logout(request)
    return HttpResponseRedirect(reverse("auth.sign_in"))