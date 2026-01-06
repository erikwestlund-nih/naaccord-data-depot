# Middleware to detect if logged in and forward to login
import re

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse


class SignedInMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

        self.excluded_paths = [
            re.compile(r"^/test"),
            re.compile(r"^/auth"),
            re.compile(r"^/sign-in$"),
            re.compile(r"^/sign-out$"),
            re.compile(r"^/admin/"),
            re.compile(r"^/saml2/"),  # Allow SAML authentication flow
            re.compile(r"^/simplesaml/"),  # Allow SimpleSAMLphp mock IDP (staging)
            re.compile(r"^/internal/"),  # Allow internal API endpoints for services communication
            re.compile(r"^/health/$"),  # Allow public health check for container monitoring
        ]

    def __call__(self, request):
        if any(pattern.match(request.path) for pattern in self.excluded_paths):
            return self.get_response(request)

        if not request.user.is_authenticated:
            # Redirect to LOGIN_URL (respects SAML configuration)
            login_url = getattr(settings, 'LOGIN_URL', '/sign-in')
            return HttpResponseRedirect(f"{login_url}?next={request.path}")

        return self.get_response(request)
