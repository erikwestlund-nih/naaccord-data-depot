from django.db import models
from django.conf import settings
from depot.models.basemodel import BaseModel
from depot.models.cohortsubmission import CohortSubmission
from depot.models.datatablefile import DataTableFile


class SubmissionActivity(BaseModel):
    """
    Tracks all activities related to a submission for audit trail purposes.
    
    This model logs all changes and actions taken on a submission including
    status changes, file uploads, approvals, sign-offs, and reopening.
    Works alongside RevisionMixin for complete audit trail.
    """
    
    # Activity types
    ACTIVITY_CREATED = 'created'
    ACTIVITY_STATUS_CHANGED = 'status_changed'
    ACTIVITY_FILE_UPLOADED = 'file_uploaded'
    ACTIVITY_FILE_APPROVED = 'file_approved'
    ACTIVITY_FILE_REJECTED = 'file_rejected'
    ACTIVITY_FILE_SKIPPED = 'file_skipped'
    ACTIVITY_FILE_REMOVED = 'file_removed'
    ACTIVITY_SIGNED_OFF = 'signed_off'
    ACTIVITY_REOPENED = 'reopened'
    ACTIVITY_COMMENT_ADDED = 'comment_added'
    ACTIVITY_PATIENT_IDS_EXTRACTED = 'patient_ids_extracted'

    ACTIVITY_TYPE_CHOICES = [
        (ACTIVITY_CREATED, 'Submission Created'),
        (ACTIVITY_STATUS_CHANGED, 'Status Changed'),
        (ACTIVITY_FILE_UPLOADED, 'File Uploaded'),
        (ACTIVITY_FILE_APPROVED, 'File Approved'),
        (ACTIVITY_FILE_REJECTED, 'File Rejected'),
        (ACTIVITY_FILE_SKIPPED, 'File Skipped'),
        (ACTIVITY_FILE_REMOVED, 'File Removed'),
        (ACTIVITY_SIGNED_OFF, 'Signed Off'),
        (ACTIVITY_REOPENED, 'Reopened'),
        (ACTIVITY_COMMENT_ADDED, 'Comment Added'),
        (ACTIVITY_PATIENT_IDS_EXTRACTED, 'Patient IDs Extracted'),
    ]

    @classmethod
    def log_comment_change(cls, submission, user, file_type, old_comments, new_comments):
        """
        Smart logging for comment changes - merges edits within a time window.
        Only logs if content actually changed.
        """
        from django.utils import timezone
        from datetime import timedelta

        # Don't log if no actual change
        if old_comments == new_comments:
            return None

        # Look for recent comment activity to merge with (5 minute window)
        five_minutes_ago = timezone.now() - timedelta(minutes=5)
        recent_activity = cls.objects.filter(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_COMMENT_ADDED,
            created_at__gte=five_minutes_ago
        ).order_by('-created_at').first()

        if recent_activity:
            # Update existing activity instead of creating new one
            details = recent_activity.details or {}
            details['file_type'] = file_type
            details['latest_comments'] = new_comments
            details['edit_count'] = details.get('edit_count', 1) + 1
            details['last_updated'] = timezone.now().isoformat()
            recent_activity.details = details
            recent_activity.save(update_fields=['details', 'updated_at'])
            return recent_activity
        else:
            # Create new activity for this editing session
            return cls.objects.create(
                submission=submission,
                user=user,
                activity_type=cls.ACTIVITY_COMMENT_ADDED,
                description=f"Updated {file_type} comments",
                details={
                    'file_type': file_type,
                    'original_comments': old_comments if old_comments else '',
                    'latest_comments': new_comments,
                    'edit_count': 1
                }
            )
    
    submission = models.ForeignKey(
        CohortSubmission,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='submission_activities'
    )
    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPE_CHOICES
    )
    description = models.TextField(
        help_text='Human-readable description of the activity'
    )
    file = models.ForeignKey(
        DataTableFile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='activities',
        help_text='Related file if activity is file-specific'
    )
    data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Additional data related to the activity'
    )
    
    class Meta:
        verbose_name = 'Submission Activity'
        verbose_name_plural = 'Submission Activities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['submission', '-created_at']),
            models.Index(fields=['activity_type']),
        ]
    
    def __str__(self):
        return f'{self.get_activity_type_display()} - {self.submission}'
    
    @classmethod
    def log_activity(cls, submission, user, activity_type, description, file=None, **data):
        """
        Create a new activity log entry.
        
        Args:
            submission: CohortSubmission instance
            user: User performing the action
            activity_type: One of the ACTIVITY_* constants
            description: Human-readable description
            file: Optional CohortSubmissionFile instance
            **data: Additional data to store in JSON field
        """
        return cls.objects.create(
            submission=submission,
            user=user,
            activity_type=activity_type,
            description=description,
            file=file,
            data=data
        )
    
    @classmethod
    def log_submission_created(cls, submission, user):
        """Log submission creation."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_CREATED,
            description=f'Submission created for {submission.protocol_year}',
            protocol_year_id=submission.protocol_year_id,
            cohort_id=submission.cohort_id
        )
    
    @classmethod
    def log_status_change(cls, submission, user, old_status, new_status):
        """Log status change."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_STATUS_CHANGED,
            description=f'Status changed from {old_status} to {new_status}',
            old_status=old_status,
            new_status=new_status
        )
    
    @classmethod
    def log_file_upload(cls, submission, user, file, version):
        """Log file upload."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_FILE_UPLOADED,
            description=f'Uploaded {file.data_file_type.name} file (version {version})',
            file=file,
            version=version,
            file_type=file.data_file_type.name
        )
    
    @classmethod
    def log_file_approved(cls, submission, user, file):
        """Log file approval."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_FILE_APPROVED,
            description=f'Approved {file.data_file_type.name} file',
            file=file,
            file_type=file.data_file_type.name
        )
    
    @classmethod
    def log_file_skipped(cls, submission, user, file, reason):
        """Log file being skipped."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_FILE_SKIPPED,
            description=f'Skipped {file.data_file_type.name} file: {reason}',
            file=file,
            reason=reason,
            file_type=file.data_file_type.name
        )
    
    @classmethod
    def log_signed_off(cls, submission, user, comments):
        """Log final sign-off."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_SIGNED_OFF,
            description='Submission signed off and finalized',
            comments=comments
        )
    
    @classmethod
    def log_reopened(cls, submission, user, reason):
        """Log submission reopening."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_REOPENED,
            description=f'Submission reopened: {reason}',
            reason=reason
        )
    
    @classmethod
    def log_patient_ids_extracted(cls, submission, user, file, count):
        """Log patient ID extraction."""
        return cls.log_activity(
            submission=submission,
            user=user,
            activity_type=cls.ACTIVITY_PATIENT_IDS_EXTRACTED,
            description=f'Extracted {count} patient IDs from {file.data_file_type.name} file',
            file=file,
            patient_count=count,
            file_type=file.data_file_type.name
        )