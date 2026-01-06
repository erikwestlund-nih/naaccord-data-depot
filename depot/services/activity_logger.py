"""
Submission Activity Logger Service

Centralized service for logging submission activities.
Provides consistent activity tracking across the application.
"""
import logging
from typing import Optional, Dict, Any
from django.utils import timezone
from depot.models import SubmissionActivity, CohortSubmission, DataTableFile

logger = logging.getLogger(__name__)


class SubmissionActivityLogger:
    """Service for logging submission activities."""
    
    @staticmethod
    def log_submission_created(submission: CohortSubmission, user):
        """Log submission creation."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_CREATED,
            description=f"Submission created for {submission.cohort.name} - {submission.protocol_year.name}"
        )
    
    @staticmethod
    def log_status_changed(submission: CohortSubmission, user, old_status: str, new_status: str):
        """Log submission status change."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_STATUS_CHANGED,
            description=f"Status changed from {old_status} to {new_status}",
            old_status=old_status,
            new_status=new_status
        )
    
    @staticmethod
    def log_file_uploaded(submission: CohortSubmission, user, file_type: str,
                         file_name: str, version: int, file_id: Optional[int] = None):
        """Log file upload activity."""
        description = f"Uploaded {file_type} file: {file_name} (v{version})"

        file = None
        if file_id:
            try:
                file = DataTableFile.objects.get(id=file_id)
            except DataTableFile.DoesNotExist:
                logger.warning(f"File {file_id} not found for activity logging")

        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_FILE_UPLOADED,
            description=description,
            file=file,
            file_type=file_type,
            file_name=file_name,
            version=version
        )
    
    @staticmethod
    def log_file_approved(submission: CohortSubmission, user, file_type: str,
                         file_name: str, file: Optional[DataTableFile] = None):
        """Log file approval."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_FILE_APPROVED,
            description=f"Approved {file_type} file: {file_name}",
            file=file,
            file_type=file_type,
            file_name=file_name
        )
    
    @staticmethod
    def log_file_rejected(submission: CohortSubmission, user, file_type: str,
                         file_name: str, reason: str, file: Optional[DataTableFile] = None):
        """Log file rejection."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_FILE_REJECTED,
            description=f"Rejected {file_type} file: {file_name}. Reason: {reason}",
            file=file,
            file_type=file_type,
            file_name=file_name,
            rejection_reason=reason
        )
    
    @staticmethod
    def log_file_skipped(submission: CohortSubmission, user, file_type: str, reason: str):
        """Log file skipping."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_FILE_SKIPPED,
            description=f"Skipped {file_type} file. Reason: {reason}",
            file_type=file_type,
            skip_reason=reason
        )

    @staticmethod
    def log_file_removed(submission: CohortSubmission, user, file_type: str,
                        file_name: str, file: Optional[DataTableFile] = None):
        """Log file removal."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_FILE_REMOVED,
            description=f"Removed {file_type} file: {file_name}",
            file=file,
            file_type=file_type,
            file_name=file_name
        )
    
    @staticmethod
    def log_signed_off(submission: CohortSubmission, user, comments: Optional[str] = None):
        """Log submission sign-off."""
        description = "Submission signed off"
        if comments:
            description += f" with comments: {comments}"
        
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_SIGNED_OFF,
            description=description,
            comments=comments,
            signed_off_at=timezone.now().isoformat()
        )
    
    @staticmethod
    def log_reopened(submission: CohortSubmission, user, reason: str):
        """Log submission reopening."""
        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_REOPENED,
            description=f"Submission reopened. Reason: {reason}",
            reopen_reason=reason,
            reopened_at=timezone.now().isoformat()
        )
    
    @staticmethod
    def log_comment_added(submission: CohortSubmission, user, comment: str,
                         file: Optional[DataTableFile] = None):
        """Log comment addition."""
        description = "Comment added"
        if file:
            description += f" to file"

        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_COMMENT_ADDED,
            description=description,
            file=file,
            comment=comment
        )
    
    @staticmethod
    def log_patient_ids_extracted(submission: CohortSubmission, user,
                                 patient_count: int, file_id: Optional[int] = None):
        """Log patient ID extraction."""
        description = f"Extracted {patient_count} patient IDs"

        file = None
        if file_id:
            try:
                file = DataTableFile.objects.get(id=file_id)
            except DataTableFile.DoesNotExist:
                logger.warning(f"DataTableFile {file_id} not found for activity logging")

        return SubmissionActivity.log_activity(
            submission=submission,
            user=user,
            activity_type=SubmissionActivity.ACTIVITY_PATIENT_IDS_EXTRACTED,
            description=description,
            file=file,
            patient_count=patient_count
        )
    
    @staticmethod
    def get_submission_activities(submission: CohortSubmission, limit: Optional[int] = None):
        """
        Get activities for a submission.
        
        Args:
            submission: The submission to get activities for
            limit: Optional limit on number of activities to return
            
        Returns:
            QuerySet of SubmissionActivity objects
        """
        activities = submission.activities.all().order_by('-created_at')
        
        if limit:
            activities = activities[:limit]
        
        return activities
    
    @staticmethod
    def get_file_activities(submission: CohortSubmission, file: DataTableFile):
        """
        Get activities for a specific file.

        Args:
            submission: The submission
            file: The file to get activities for

        Returns:
            QuerySet of SubmissionActivity objects
        """
        return submission.activities.filter(file=file).order_by('-created_at')
    
    @staticmethod
    def get_user_activities(user, limit: Optional[int] = None):
        """
        Get recent activities by a user.
        
        Args:
            user: The user to get activities for
            limit: Optional limit on number of activities
            
        Returns:
            QuerySet of SubmissionActivity objects
        """
        activities = SubmissionActivity.objects.filter(user=user).order_by('-created_at')
        
        if limit:
            activities = activities[:limit]
        
        return activities
    
    @staticmethod
    def batch_log_activities(activities_data: list):
        """
        Log multiple activities at once for efficiency.
        
        Args:
            activities_data: List of dicts with activity data
            
        Returns:
            List of created SubmissionActivity objects
        """
        activities = []
        
        for data in activities_data:
            try:
                activity = SubmissionActivity.log_activity(**data)
                activities.append(activity)
            except Exception as e:
                logger.error(f"Failed to log activity: {e}, data: {data}")
        
        return activities