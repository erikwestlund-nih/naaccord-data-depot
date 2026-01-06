from django.db import models
from django.conf import settings
from django.utils import timezone
from pathlib import Path
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notebook(models.Model):
    """Model to manage Quarto notebooks and their compiled outputs."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('compiling', 'Compiling'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # Core fields
    name = models.CharField(max_length=255)
    template_path = models.CharField(max_length=1024)  # Path to .qmd template
    compiled_path = models.CharField(max_length=1024, null=True, blank=True)  # Path to compiled HTML
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    compiled_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    # Generic relation to either Audit or Upload
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Foreign keys
    cohort = models.ForeignKey('Cohort', on_delete=models.CASCADE)
    data_file_type = models.ForeignKey('DataFileType', on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.data_file_type.name})"

    def get_template_path(self):
        """Get the full path to the notebook template."""
        return Path(settings.BASE_DIR) / 'depot' / 'notebooks' / self.template_path

    def get_compiled_path(self):
        """Get the full path to the compiled notebook."""
        if not self.compiled_path:
            return None
        return Path(settings.BASE_DIR) / 'depot' / 'notebooks' / 'compiled' / self.compiled_path

    def mark_compiling(self):
        """Mark the notebook as being compiled."""
        self.status = 'compiling'
        self.save()

    def mark_completed(self, compiled_path):
        """Mark the notebook as completed with the compiled path."""
        self.status = 'completed'
        self.compiled_path = compiled_path
        self.compiled_at = timezone.now()
        self.save()

    def mark_failed(self, error):
        """Mark the notebook as failed with error message."""
        self.status = 'failed'
        self.error = error
        self.save()

    def can_access(self, user):
        """Check if a user has permission to access this notebook."""
        # NA Accord Administrators can access everything
        if user.is_na_accord_admin():
            return True
            
        # Check if user is a member of this notebook's cohort
        from depot.models import CohortMembership
        return CohortMembership.objects.filter(
            user=user,
            cohort=self.cohort
        ).exists() 