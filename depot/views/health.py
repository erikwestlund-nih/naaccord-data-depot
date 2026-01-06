"""
Public health check endpoint for container health monitoring.

This endpoint MUST NOT require authentication as it's used by Docker health checks.
"""

from django.http import JsonResponse
from django.db import connection
from django.conf import settings


def health_check(request):
    """
    Simple health check endpoint for Docker/Kubernetes health monitoring.

    Returns 200 OK with basic status information.
    Does NOT require authentication.

    Checks:
    - Database connectivity
    - Django app is running

    Response:
    - 200 OK: Service is healthy
    - 500 Internal Server Error: Service is unhealthy
    """
    try:
        # Check database connectivity
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        return JsonResponse({
            "status": "healthy",
            "database": "connected",
            "server_role": settings.SERVER_ROLE,
        }, status=200)

    except Exception as e:
        return JsonResponse({
            "status": "unhealthy",
            "error": str(e),
            "server_role": settings.SERVER_ROLE,
        }, status=500)
