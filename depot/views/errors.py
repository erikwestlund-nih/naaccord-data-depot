from django.shortcuts import render
from django.http import HttpResponseForbidden, HttpResponseNotFound, HttpResponseServerError
import logging

logger = logging.getLogger(__name__)


def handler403(request, exception=None):
    """Custom 403 error handler."""
    # Log the 403 for security monitoring
    logger.warning(
        f"403 Access Denied: User {request.user.email if request.user.is_authenticated else 'Anonymous'} "
        f"attempted to access {request.path} from IP {request.META.get('REMOTE_ADDR', 'unknown')}"
    )
    return render(request, 'errors/403.html', status=403)


def handler404(request, exception=None):
    """Custom 404 error handler."""
    return render(request, 'errors/404.html', status=404)


def handler500(request):
    """Custom 500 error handler."""
    return render(request, 'errors/500.html', status=500)