"""
Notification Service

Centralized service for handling email and in-app notifications.
Provides consistent notification management across the application.
"""
import logging
from typing import List, Dict, Any, Optional
from django.core.mail import send_mail, send_mass_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationService:
    """Service for managing notifications."""
    
    # Notification types
    UPLOAD_SUCCESS = 'upload_success'
    UPLOAD_FAILED = 'upload_failed'
    AUDIT_COMPLETE = 'audit_complete'
    AUDIT_FAILED = 'audit_failed'
    SUBMISSION_SIGNED_OFF = 'submission_signed_off'
    SUBMISSION_REOPENED = 'submission_reopened'
    VALIDATION_WARNING = 'validation_warning'
    VALIDATION_ERROR = 'validation_error'
    
    @staticmethod
    def send_upload_notification(user, submission, file_type, success=True):
        """Send notification about file upload status."""
        if success:
            subject = f"File Upload Successful - {file_type}"
            template = 'emails/upload_success.html'
            notification_type = NotificationService.UPLOAD_SUCCESS
        else:
            subject = f"File Upload Failed - {file_type}"
            template = 'emails/upload_failed.html'
            notification_type = NotificationService.UPLOAD_FAILED
        
        context = {
            'user': user,
            'submission': submission,
            'file_type': file_type,
            'timestamp': timezone.now()
        }
        
        return NotificationService._send_email(
            subject=subject,
            template=template,
            context=context,
            recipients=[user.email],
            notification_type=notification_type
        )
    
    @staticmethod
    def send_audit_complete_notification(audit, recipients=None):
        """Send notification when audit is complete."""
        if recipients is None:
            recipients = [audit.uploaded_by.email] if audit.uploaded_by else []
        
        subject = f"Audit Complete - {audit.data_file_type.label}"
        
        context = {
            'audit': audit,
            'cohort': audit.cohort,
            'file_type': audit.data_file_type,
            'status': audit.status,
            'has_errors': audit.has_validation_errors(),
            'timestamp': timezone.now()
        }
        
        return NotificationService._send_email(
            subject=subject,
            template='emails/audit_complete.html',
            context=context,
            recipients=recipients,
            notification_type=NotificationService.AUDIT_COMPLETE
        )
    
    @staticmethod
    def send_submission_signed_off_notification(submission, signed_by, cohort_members=None):
        """Send notification when submission is signed off."""
        # Get all cohort members if not provided
        if cohort_members is None:
            from depot.models import CohortMembership
            memberships = CohortMembership.objects.filter(
                cohort=submission.cohort
            ).select_related('user')
            cohort_members = [m.user for m in memberships]
        
        subject = f"Submission Signed Off - {submission.protocol_year.name}"
        
        context = {
            'submission': submission,
            'signed_by': signed_by,
            'cohort': submission.cohort,
            'protocol_year': submission.protocol_year,
            'timestamp': timezone.now()
        }
        
        recipients = [member.email for member in cohort_members if member.email]
        
        return NotificationService._send_email(
            subject=subject,
            template='emails/submission_signed_off.html',
            context=context,
            recipients=recipients,
            notification_type=NotificationService.SUBMISSION_SIGNED_OFF
        )
    
    @staticmethod
    def send_validation_warning(submission, file_type, warnings, user=None):
        """Send notification about validation warnings."""
        recipients = [user.email] if user else []
        
        # Also notify data managers
        data_managers = NotificationService._get_data_managers(submission.cohort)
        recipients.extend([dm.email for dm in data_managers if dm.email])
        
        subject = f"Validation Warnings - {file_type}"
        
        context = {
            'submission': submission,
            'file_type': file_type,
            'warnings': warnings,
            'warning_count': len(warnings),
            'timestamp': timezone.now()
        }
        
        return NotificationService._send_email(
            subject=subject,
            template='emails/validation_warning.html',
            context=context,
            recipients=list(set(recipients)),  # Remove duplicates
            notification_type=NotificationService.VALIDATION_WARNING
        )
    
    @staticmethod
    def send_batch_notifications(notifications: List[Dict[str, Any]]):
        """
        Send multiple notifications in batch.
        
        Args:
            notifications: List of dicts with keys:
                - subject: Email subject
                - template: Template name
                - context: Template context
                - recipients: List of email addresses
        """
        messages = []
        
        for notification in notifications:
            try:
                html_content = render_to_string(
                    notification['template'],
                    notification['context']
                )
                
                # Create plain text version
                text_content = NotificationService._html_to_text(html_content)
                
                messages.append((
                    notification['subject'],
                    text_content,
                    settings.DEFAULT_FROM_EMAIL,
                    notification['recipients']
                ))
                
            except Exception as e:
                logger.error(f"Failed to prepare batch notification: {e}")
        
        if messages:
            try:
                send_mass_mail(messages, fail_silently=False)
                logger.info(f"Sent {len(messages)} batch notifications")
                return True
            except Exception as e:
                logger.error(f"Failed to send batch notifications: {e}")
                return False
        
        return True
    
    @staticmethod
    def create_in_app_notification(user, notification_type, title, message, data=None):
        """
        Create an in-app notification for the user.
        
        This would typically create a database record that the UI can query.
        """
        try:
            from depot.models import UserNotification
            
            notification = UserNotification.objects.create(
                user=user,
                type=notification_type,
                title=title,
                message=message,
                data=data or {},
                is_read=False
            )
            
            logger.info(f"Created in-app notification {notification.id} for user_id {user.id}")
            return notification
            
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")
            return None
    
    @staticmethod
    def mark_notifications_read(user, notification_ids=None):
        """Mark notifications as read for a user."""
        try:
            from depot.models import UserNotification
            
            query = UserNotification.objects.filter(user=user, is_read=False)
            if notification_ids:
                query = query.filter(id__in=notification_ids)
            
            count = query.update(is_read=True, read_at=timezone.now())
            logger.info(f"Marked {count} notifications as read for user_id {user.id}")
            return count
            
        except Exception as e:
            logger.error(f"Failed to mark notifications as read: {e}")
            return 0
    
    # Private helper methods
    
    @staticmethod
    def _send_email(subject, template, context, recipients, notification_type=None):
        """Internal method to send email."""
        if not recipients:
            logger.warning(f"No recipients for notification: {subject}")
            return False
        
        try:
            # Render HTML content
            html_content = render_to_string(template, context)
            
            # Create plain text version
            text_content = NotificationService._html_to_text(html_content)
            
            # Send email
            send_mail(
                subject=subject,
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                html_message=html_content,
                fail_silently=False
            )
            
            logger.info(
                f"Sent {notification_type or 'email'} notification to {len(recipients)} recipients"
            )
            
            # Log notification in database if configured
            if notification_type:
                NotificationService._log_notification(
                    notification_type, subject, recipients
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}", exc_info=True)
            return False
    
    @staticmethod
    def _html_to_text(html_content):
        """Convert HTML to plain text."""
        # Simple conversion - in production, use a library like html2text
        import re
        text = re.sub('<[^<]+?>', '', html_content)
        return text.strip()
    
    @staticmethod
    def _get_data_managers(cohort):
        """Get data managers for a cohort."""
        try:
            from depot.models import CohortMembership
            
            memberships = CohortMembership.objects.filter(
                cohort=cohort,
                role__in=['data_manager', 'admin']
            ).select_related('user')
            
            return [m.user for m in memberships]
            
        except Exception as e:
            logger.error(f"Failed to get data managers: {e}")
            return []
    
    @staticmethod
    def _log_notification(notification_type, subject, recipients):
        """Log notification in database for audit trail."""
        try:
            from depot.models import NotificationLog
            
            NotificationLog.objects.create(
                type=notification_type,
                subject=subject,
                recipients=recipients,
                sent_at=timezone.now()
            )
            
        except Exception as e:
            # Don't fail if logging fails
            logger.debug(f"Failed to log notification: {e}")