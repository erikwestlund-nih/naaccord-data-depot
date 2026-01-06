# depot/views/auth/sign_in.py

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth import authenticate, login
import logging

logger = logging.getLogger(__name__)


def sign_in_page(request):
    """
    Authentication Entry Point

    - If DISABLE_SAML=True: Show Django login form (ModelBackend)
    - Otherwise: Redirect to SAML IdP (staging mock-idp or production JHU Shibboleth)

    For emergency access, IT team uses Django shell via SSH.
    See: docs/deployment/guides/emergency-access.md
    """

    disable_saml = getattr(settings, 'DISABLE_SAML', False)

    # If SAML is disabled, show Django login form
    if disable_saml:
        if request.method == 'POST':
            email = request.POST.get('email')
            password = request.POST.get('password')
            user = authenticate(request, username=email, password=password)

            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', reverse('index'))
                return redirect(next_url)
            else:
                return render(request, 'pages/auth/sign_in.html', {
                    'error': 'Invalid email or password',
                    'email': email
                })

        return render(request, 'pages/auth/sign_in.html')

    # SAML authentication path
    use_docker_saml = getattr(settings, 'USE_DOCKER_SAML', False)
    use_mock_saml = getattr(settings, 'USE_MOCK_SAML', False)

    # Get next URL for relay state
    next_url = request.GET.get('next', reverse('index'))

    try:
        if use_docker_saml or not settings.DEBUG:
            # Production or Docker SAML: Redirect to real SAML2 IdP
            logger.info("Redirecting to SAML IdP (production or Docker)")
            saml_url = reverse("saml2_login")
            return redirect(f"{saml_url}?next={next_url}")

        elif use_mock_saml:
            # Development: Redirect to mock SAML IdP
            logger.info("Redirecting to mock SAML IdP (development)")
            saml_url = reverse("saml2_login")
            return redirect(f"{saml_url}?next={next_url}")

        else:
            # Fallback: No SAML configured
            logger.error("SAML not configured - no authentication method available")
            from django.http import HttpResponse
            return HttpResponse(
                "<h1>Authentication Not Configured</h1>"
                "<p>SAML authentication is not properly configured. Please contact IT support.</p>"
                "<p>For emergency access, see: docs/deployment/guides/emergency-access.md</p>",
                status=503
            )

    except Exception as e:
        logger.error(f"SAML redirect failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

        from django.http import HttpResponse
        return HttpResponse(
            "<h1>Authentication Error</h1>"
            "<p>Unable to redirect to SAML authentication. Please contact IT support.</p>"
            f"<p>Error: {str(e)}</p>",
            status=500
        )
