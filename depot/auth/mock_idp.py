"""
Mock SAML IdP for Development
Simulates the full SAML redirect/return flow
"""
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View
from django.contrib.auth import authenticate, login
from django.conf import settings
from django.http import HttpResponse
import urllib.parse
import base64
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MockSAMLLogin(View):
    """
    Simulates SAML SSO redirect to IdP
    This is where the SP would redirect to the IdP with a SAML AuthnRequest
    """
    
    def get(self, request):
        """Handle SAML login redirect"""
        if not settings.DEBUG:
            return HttpResponse("Mock IdP only available in DEBUG mode", status=403)
        
        # Get the pending email from session (set by sign_in view)
        email = request.session.get('pending_email')
        institution = request.session.get('pending_institution', 'mock_idp')
        
        if not email:
            # No email in session, redirect back to sign in
            return redirect(reverse('auth.sign_in'))
        
        # Store SAML request data in session (simulating SAML RelayState)
        relay_state = {
            'return_to': request.GET.get('next', reverse('index')),
            'request_id': f"ONELOGIN_{datetime.now().timestamp()}",
            'institution': institution
        }
        request.session['mock_saml_relay_state'] = relay_state
        
        # Redirect to mock IdP login page
        return redirect(reverse('mock_idp_login'))


class MockIdPLogin(View):
    """
    Mock IdP login page
    Simulates the institution's SSO login page
    """
    
    def get(self, request):
        """Display mock IdP login page"""
        if not settings.DEBUG:
            return HttpResponse("Mock IdP only available in DEBUG mode", status=403)
        
        email = request.session.get('pending_email', '')
        institution = request.session.get('pending_institution', 'Mock IdP')
        
        # Map institution to display name
        institution_names = {
            'johns_hopkins': 'Johns Hopkins University',
            'uc_san_diego': 'UC San Diego',
            'case_western': 'Case Western Reserve University',
            'ua_birmingham': 'University of Alabama Birmingham',
            'mock_idp': 'Mock Institution SSO'
        }
        
        institution_display = institution_names.get(institution, 'Institution SSO')
        
        context = {
            'email': email,
            'institution': institution_display,
            'title': f'{institution_display} Sign In'
        }
        
        return render(request, 'pages/auth/mock_idp_login.html', context)
    
    def post(self, request):
        """Process mock IdP login"""
        if not settings.DEBUG:
            return HttpResponse("Mock IdP only available in DEBUG mode", status=403)
        
        email = request.session.get('pending_email')
        password = request.POST.get('password', '')
        
        # For mock IdP, any password works (or we can check specific ones)
        # In real SAML, the IdP handles authentication completely
        mock_passwords = {
            'admin@test.edu': 'admin',
            'researcher@test.edu': 'researcher',
            # Default: any non-empty password works
        }
        
        expected_password = mock_passwords.get(email, 'password')
        
        # Simple mock validation
        if not password:
            return render(request, 'pages/auth/mock_idp_login.html', {
                'email': email,
                'error': 'Password is required',
                'institution': request.session.get('pending_institution', 'Mock IdP')
            })
        
        # Simulate successful IdP authentication
        # In real SAML, this would generate a signed SAML Response
        logger.info("Mock IdP authenticated user")
        
        # Redirect back to SP with SAML response
        return redirect(reverse('mock_saml_acs'))


class MockSAMLACS(View):
    """
    Mock SAML Assertion Consumer Service (ACS)
    This simulates receiving and processing the SAML response from IdP
    """
    
    def get(self, request):
        """Handle SAML response (normally would be POST)"""
        if not settings.DEBUG:
            return HttpResponse("Mock IdP only available in DEBUG mode", status=403)
        
        # Get email and relay state from session
        email = request.session.get('pending_email')
        relay_state = request.session.get('mock_saml_relay_state', {})
        
        if not email:
            logger.error("No email in session for SAML ACS")
            return redirect(reverse('auth.sign_in'))
        
        # Simulate SAML response validation
        logger.info("Processing mock SAML assertion")
        
        # Create mock SAML response data (what we'd extract from real SAML)
        saml_attributes = {
            'email': email,
            'eduPersonPrincipalName': email,
            'displayName': email.split('@')[0].title(),
            'eduPersonAffiliation': ['member', 'staff'] if 'admin' in email else ['member'],
            # Add more attributes as needed
        }
        
        # Authenticate using our mock backend
        user = authenticate(request, username=email)
        
        if user:
            # Login the user
            login(request, user)
            logger.info(f"Successfully logged in via mock SAML: user_id {user.id}")
            
            # Clean up session
            request.session.pop('pending_email', None)
            request.session.pop('pending_institution', None)
            request.session.pop('mock_saml_relay_state', None)
            
            # Redirect to original destination
            return_to = relay_state.get('return_to', reverse('index'))
            return redirect(return_to)
        else:
            logger.error("Failed to authenticate user from SAML")
            return redirect(reverse('auth.sign_in'))


class MockSAMLMetadata(View):
    """
    Mock SAML metadata endpoint
    Simulates SP metadata for IdP configuration
    """
    
    def get(self, request):
        """Return mock SP metadata"""
        if not settings.DEBUG:
            return HttpResponse("Mock metadata only available in DEBUG mode", status=403)
        
        # Mock SP metadata (simplified)
        metadata = f"""<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata"
                  entityID="http://localhost:8000/saml2/metadata/">
    <SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <AssertionConsumerService 
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="http://localhost:8000/auth/saml/acs/"
            index="0"/>
    </SPSSODescriptor>
    <Organization>
        <OrganizationName>NA-ACCORD Data Depot (Dev)</OrganizationName>
        <OrganizationURL>http://localhost:8000</OrganizationURL>
    </Organization>
</EntityDescriptor>"""
        
        return HttpResponse(metadata, content_type='application/xml')


class MockSAMLLogout(View):
    """
    Mock SAML Single Logout (SLO)
    """
    
    def get(self, request):
        """Handle SAML logout"""
        if not settings.DEBUG:
            return HttpResponse("Mock logout only available in DEBUG mode", status=403)
        
        # Regular Django logout
        from django.contrib.auth import logout
        logout(request)
        
        # Clear any SAML session data
        request.session.pop('pending_email', None)
        request.session.pop('pending_institution', None)
        request.session.pop('mock_saml_relay_state', None)
        
        return redirect(reverse('auth.sign_in'))