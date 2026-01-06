from django.db import models
from django.utils import timezone
from .basemodel import BaseModel


class DataTableReview(BaseModel):
    """
    Tracks review status and comments for each data table.
    Provides lightweight acknowledgment system without blocking submission.
    """
    data_table = models.OneToOneField(
        'depot.CohortSubmissionDataTable',
        on_delete=models.CASCADE,
        related_name='review'
    )
    
    # Review status
    is_reviewed = models.BooleanField(
        default=False,
        help_text="User has acknowledged reviewing this table"
    )
    reviewed_by = models.ForeignKey(
        'depot.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='table_reviews'
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    # Comments for issues or notes
    comments = models.TextField(
        blank=True,
        help_text="Notes about validation issues or other concerns"
    )
    comments_updated_by = models.ForeignKey(
        'depot.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='table_comment_updates'
    )
    comments_updated_at = models.DateTimeField(
        null=True,
        blank=True
    )
    
    # Track if validation report was viewed
    validation_report_viewed = models.BooleanField(
        default=False,
        help_text="Automatically set when user views the validation report"
    )
    validation_report_first_viewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    validation_report_last_viewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    validation_report_view_count = models.IntegerField(
        default=0,
        help_text="Number of times the validation report was viewed"
    )
    
    # Track issues found
    has_validation_errors = models.BooleanField(
        default=False,
        help_text="Set if validation report contains errors"
    )
    has_validation_warnings = models.BooleanField(
        default=False,
        help_text="Set if validation report contains warnings"
    )
    issue_count = models.IntegerField(
        default=0,
        help_text="Total number of validation issues"
    )
    
    class Meta:
        db_table = 'depot_datatable_review'
        ordering = ['data_table__data_file_type__order']
        
    def __str__(self):
        status = "reviewed" if self.is_reviewed else "pending"
        return f"{self.data_table} - {status}"
    
    def mark_reviewed(self, user):
        """Mark this table as reviewed by the user."""
        self.is_reviewed = True
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.save(update_fields=['is_reviewed', 'reviewed_by', 'reviewed_at', 'updated_at'])
    
    def unmark_reviewed(self):
        """Remove the reviewed status."""
        self.is_reviewed = False
        self.reviewed_by = None
        self.reviewed_at = None
        self.save(update_fields=['is_reviewed', 'reviewed_by', 'reviewed_at', 'updated_at'])
    
    def update_comments(self, comments, user):
        """Update comments with user tracking."""
        self.comments = comments
        self.comments_updated_by = user
        self.comments_updated_at = timezone.now()
        self.save(update_fields=['comments', 'comments_updated_by', 'comments_updated_at', 'updated_at'])
    
    def record_report_view(self, user=None):
        """Record that the validation report was viewed."""
        now = timezone.now()
        if not self.validation_report_first_viewed_at:
            self.validation_report_first_viewed_at = now
        self.validation_report_last_viewed_at = now
        self.validation_report_view_count += 1
        self.validation_report_viewed = True
        self.save(update_fields=[
            'validation_report_viewed', 
            'validation_report_first_viewed_at',
            'validation_report_last_viewed_at',
            'validation_report_view_count',
            'updated_at'
        ])
    
    @property
    def needs_attention(self):
        """Check if this table needs attention (has issues but not reviewed)."""
        return (self.has_validation_errors or self.has_validation_warnings) and not self.is_reviewed
    
    @property
    def review_status_display(self):
        """Get human-readable review status."""
        if self.is_reviewed:
            return "Reviewed"
        elif self.validation_report_viewed:
            return "Report Viewed"
        elif self.has_validation_errors:
            return "Errors - Needs Review"
        elif self.has_validation_warnings:
            return "Warnings - Needs Review"
        else:
            return "Pending Review"