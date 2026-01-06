"""
Custom SAML login view that enforces ForceAuthn for security
"""
from django.http import HttpResponseRedirect, HttpResponseServerError
from django.urls import reverse
from django.conf import settings
from djangosaml2.conf import get_config
from djangosaml2.utils import available_idps
from saml2.client import Saml2Client
from saml2 import BINDING_HTTP_REDIRECT
import logging

logger = logging.getLogger(__name__)


def saml_login_force_auth(request):
    """
    Custom SAML login that always forces re-authentication.
    This is critical for security to prevent session hijacking.
    """
    try:
        conf = get_config()
        client = Saml2Client(conf)
        
        # Get available IdPs
        idps = available_idps(conf)
        if not idps:
            logger.error("No SAML IdPs configured")
            return HttpResponseServerError("No identity providers configured")
        
        # Use first available IdP
        idp_entityid = list(idps.keys())[0]
        logger.info(f"Initiating SAML login with ForceAuthn for IdP: {idp_entityid}")
        
        # Get relay state (where to go after auth)
        next_url = request.GET.get('next', reverse('index'))
        
        # Create authentication request with ForceAuthn=true
        reqid, info = client.prepare_for_authenticate(
            entityid=idp_entityid,
            relay_state=next_url,
            binding=BINDING_HTTP_REDIRECT,
            force_authn="true",  # CRITICAL: Forces re-authentication
            # You can also add:
            # is_passive="false",  # Ensures user interaction
        )
        
        # Store request ID in session for response validation
        request.session['saml_request_id'] = reqid
        
        # Get the redirect URL from the info dict
        redirect_url = None
        for header, value in info.get('headers', []):
            if header == 'Location':
                redirect_url = value
                break
        
        if not redirect_url:
            logger.error("No redirect URL in SAML request")
            return HttpResponseServerError("Failed to create SAML request")
        
        logger.info(f"Redirecting to IdP with ForceAuthn: {redirect_url[:100]}...")
        return HttpResponseRedirect(redirect_url)
        
    except Exception as e:
        logger.error(f"SAML login error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return HttpResponseServerError("SAML authentication error")