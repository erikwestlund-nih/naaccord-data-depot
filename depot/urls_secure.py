"""
URL configuration for secure upload endpoints.

These URLs would be deployed on the secure upload server,
not the main web application server.
"""
from django.urls import path
from depot.views.secure_upload_endpoint import (
    secure_upload_handler,
    secure_upload_status
)

app_name = 'secure'

urlpatterns = [
    # Secure upload endpoints (PHI isolation server only)
    path('upload/', secure_upload_handler, name='upload'),
    path('status/<str:upload_id>/', secure_upload_status, name='status'),
]