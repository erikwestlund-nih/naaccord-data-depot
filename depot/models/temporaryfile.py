from django.db import models
from django.utils import timezone

from depot.models import BaseModel


class TemporaryFile(BaseModel):
    path = models.TextField()  # Full absolute path on disk
    uploaded_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()  # When to auto-delete
    purpose = models.CharField(max_length=100)  # e.g., "audit_upload"
    metadata = models.JSONField(default=dict)  # Optional context (user, job ID, etc.)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def read_contents(self):
        """Read the contents of the temporary file."""
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()
