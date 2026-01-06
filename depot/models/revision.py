from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from depot.models import TimeStampedModel


class Revision(TimeStampedModel):
    """Universal revision tracking for audit compliance."""
    
    # What was changed
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Who made the change
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='revisions'
    )
    
    # Type of change
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
    ]
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    
    # What changed
    changes = models.JSONField(default=dict)  # {field: {'old': val, 'new': val}}
    
    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Additional metadata
    model_name = models.CharField(max_length=100)  # For easier querying
    object_repr = models.CharField(max_length=500)  # String representation of object
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['model_name']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.action} {self.model_name}#{self.object_id} by {self.user}"