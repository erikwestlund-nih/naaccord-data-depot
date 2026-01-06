from django.db import models
from .basemodel import BaseModel


class NotebookAccess(BaseModel):
    """
    Tracks each time a user views a validation report (notebook).
    Used to determine if a user has reviewed validation results.
    """
    user = models.ForeignKey(
        'depot.User',
        on_delete=models.CASCADE,
        related_name='notebook_accesses'
    )
    notebook = models.ForeignKey(
        'depot.Notebook',
        on_delete=models.CASCADE,
        related_name='access_logs'
    )
    data_table = models.ForeignKey(
        'depot.CohortSubmissionDataTable',
        on_delete=models.CASCADE,
        related_name='notebook_accesses',
        null=True,
        blank=True,
        help_text="The data table this access is associated with"
    )
    
    # Track how they accessed it
    access_method = models.CharField(
        max_length=50,
        choices=[
            ('direct_view', 'Direct View'),
            ('download', 'Download'),
            ('api', 'API Access'),
        ],
        default='direct_view'
    )
    
    # Track duration if viewing in browser
    view_duration_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="How long the report was viewed (if tracked)"
    )
    
    # IP for audit trail
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )
    
    # User agent for debugging
    user_agent = models.TextField(
        null=True,
        blank=True
    )
    
    class Meta:
        db_table = 'depot_notebook_access'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'notebook']),
            models.Index(fields=['data_table', 'created_at']),
        ]
        
    def __str__(self):
        return f"{self.user.username} accessed {self.notebook.name} at {self.created_at}"