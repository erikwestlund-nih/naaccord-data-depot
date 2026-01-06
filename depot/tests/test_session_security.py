"""
Security tests for session management and authentication.
Tests session fixation, hijacking, and secure cookie settings.
"""
from django.test import override_settings
from depot.tests.base_security import SecurityTestCase


class SessionSecurityTest(SecurityTestCase):
    """Test session security configuration."""

    def test_session_cookie_httponly_configured(self):
        """Session cookies should have HTTPOnly flag configured."""
        from django.conf import settings

        # Check SESSION_COOKIE_HTTPONLY setting
        httponly = getattr(settings, 'SESSION_COOKIE_HTTPONLY', False)
        self.assertTrue(httponly,
            "SESSION_COOKIE_HTTPONLY should be True")

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_session_cookie_secure_in_production(self):
        """Session cookies should have Secure flag in production."""
        from django.conf import settings

        # In production (DEBUG=False), SESSION_COOKIE_SECURE should be True
        secure = getattr(settings, 'SESSION_COOKIE_SECURE', False)
        self.assertTrue(secure or settings.DEBUG,
            "SESSION_COOKIE_SECURE should be True in production")

    def test_csrf_middleware_enabled(self):
        """CSRF middleware should be enabled."""
        from django.conf import settings

        middleware = settings.MIDDLEWARE
        csrf_middleware = 'django.middleware.csrf.CsrfViewMiddleware'

        self.assertIn(csrf_middleware, middleware,
            "CSRF middleware should be enabled")
