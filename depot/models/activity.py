"""
Activity tracking models for Johns Hopkins compliance audit system.

These models record all user activities and data changes for HIPAA compliance
and Johns Hopkins IT Security requirements.
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import json


User = get_user_model()


class ActivityType(models.TextChoices):
    """
    Enumerated activity types for consistent categorization.
    Johns Hopkins requirement: All user activities must be logged.
    """
    # Authentication events
    LOGIN = 'login', 'Login'
    LOGOUT = 'logout', 'Logout'
    LOGIN_FAILED = 'login_failed', 'Login Failed'
    SESSION_TIMEOUT = 'session_timeout', 'Session Timeout'
    FORCE_LOGOUT = 'force_logout', 'Force Logout'
    
    # Access events
    PAGE_ACCESS = 'page_access', 'Page Access'
    API_ACCESS = 'api_access', 'API Access'
    FILE_DOWNLOAD = 'file_download', 'File Download'
    REPORT_VIEW = 'report_view', 'Report View'
    EXPORT_DATA = 'export_data', 'Data Export'
    
    # Administrative events
    PERMISSION_CHANGE = 'permission_change', 'Permission Change'
    USER_CREATE = 'user_create', 'User Create'
    USER_MODIFY = 'user_modify', 'User Modify'
    ADMIN_ACCESS = 'admin_access', 'Admin Access'
    
    # Data events (high-level, details in DataRevision)
    DATA_CREATE = 'data_create', 'Data Create'
    DATA_UPDATE = 'data_update', 'Data Update'
    DATA_DELETE = 'data_delete', 'Data Delete'
    DATA_EXPORT = 'data_export', 'Data Export'


class Activity(models.Model):
    """
    Unified activity tracking for all user actions.
    
    Johns Hopkins Requirements:
    - Log access attempts and successful logins by user ID, date, time
    - Log session initiation and termination
    - Indefinite retention (minimum 12 months)
    - Export capability using mysqldump
    """
    
    # Core activity fields
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,  # Set to null when user is deleted, preserving activity records
        null=True, blank=True,  # Allow anonymous activities
        help_text="User who performed the activity (null for anonymous)"
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the activity occurred"
    )
    activity_type = models.CharField(
        max_length=50,
        choices=ActivityType.choices,
        db_index=True,
        help_text="Type of activity performed"
    )
    success = models.BooleanField(
        default=True,
        help_text="Whether the activity was successful"
    )
    
    # Request context (Johns Hopkins terminal requirement)
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.TextField(
        null=True, blank=True,
        help_text="User agent string from browser"
    )
    session_id = models.CharField(
        max_length=40,
        null=True, blank=True,
        db_index=True,
        help_text="Django session ID"
    )
    terminal_id = models.CharField(
        max_length=100,
        null=True, blank=True,
        help_text="Terminal/workstation identifier for compliance"
    )
    
    # Access details (for page/API access)
    path = models.CharField(
        max_length=500,
        null=True, blank=True,
        help_text="URL path accessed"
    )
    method = models.CharField(
        max_length=10,
        null=True, blank=True,
        help_text="HTTP method (GET, POST, etc.)"
    )
    status_code = models.IntegerField(
        null=True, blank=True,
        help_text="HTTP response status code"
    )
    duration_ms = models.IntegerField(
        null=True, blank=True,
        help_text="Request duration in milliseconds"
    )
    
    # Flexible data storage
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional activity-specific data"
    )
    
    # Compliance fields
    retention_date = models.DateTimeField(
        null=True, blank=True,
        help_text="Date when record can be deleted (NULL = indefinite retention)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Activity'
        verbose_name_plural = 'Activities'
        
        # Performance indexes for common queries
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['activity_type', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['success', 'activity_type']),
        ]
        
        # Ensure audit data integrity
        permissions = [
            ('export_activities', 'Can export activity logs'),
            ('view_all_activities', 'Can view all user activities'),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.get_activity_type_display()} at {self.timestamp}"

    def save(self, *args, **kwargs):
        """
        Ensure audit data integrity and compliance requirements.
        """
        # Indefinite retention per Johns Hopkins requirement
        if not self.retention_date:
            self.retention_date = None  # Explicit indefinite retention
            
        super().save(*args, **kwargs)

    @classmethod
    def log_activity(cls, user, activity_type, success=True, **kwargs):
        """
        Convenience method for logging activities with consistent format.
        
        Args:
            user: User instance
            activity_type: ActivityType choice
            success: Boolean success flag
            **kwargs: Additional fields (ip_address, path, details, etc.)
        """
        # Extract request context if available
        request = kwargs.pop('request', None)
        if request:
            kwargs.setdefault('ip_address', cls._get_client_ip(request))
            kwargs.setdefault('user_agent', request.META.get('HTTP_USER_AGENT', '')[:500])
            kwargs.setdefault('session_id', request.session.session_key)
            kwargs.setdefault('path', request.get_full_path()[:500])
            kwargs.setdefault('method', request.method)
            
        return cls.objects.create(
            user=user,
            activity_type=activity_type,
            success=success,
            **kwargs
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Extract real client IP from request, handling proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class DataRevision(models.Model):
    """
    Field-level tracking of data changes with polymorphic associations.
    
    Johns Hopkins Requirements:
    - Observer pattern for ALL records to log modifications
    - Links to Activity for security context
    - Backup system integration for secondary audit trail
    """
    
    # Link to activity context
    activity = models.ForeignKey(
        Activity,
        on_delete=models.PROTECT,  # Never delete revisions
        related_name='data_revisions',
        help_text="Activity that caused this data change"
    )
    
    # Polymorphic object reference
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Field-level change tracking
    field_name = models.CharField(
        max_length=100,
        help_text="Name of the field that changed"
    )
    old_value = models.TextField(
        null=True, blank=True,
        help_text="Previous field value (JSON serialized)"
    )
    new_value = models.TextField(
        null=True, blank=True,
        help_text="New field value (JSON serialized)"
    )
    change_type = models.CharField(
        max_length=20,
        choices=[
            ('create', 'Create'),
            ('update', 'Update'),
            ('delete', 'Delete'),
        ],
        help_text="Type of change operation"
    )
    
    # Compliance and backup integration
    backup_reference = models.CharField(
        max_length=200,
        null=True, blank=True,
        help_text="Reference to backup system for secondary audit trail"
    )
    encrypted_data = models.BooleanField(
        default=False,
        help_text="Whether sensitive data in this revision is encrypted"
    )
    
    # Metadata
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        verbose_name = 'Data Revision'
        verbose_name_plural = 'Data Revisions'
        
        # Performance indexes
        indexes = [
            models.Index(fields=['content_type', 'object_id', 'timestamp']),
            models.Index(fields=['activity', 'timestamp']),
            models.Index(fields=['field_name', 'change_type']),
        ]

    def __str__(self):
        return f"{self.content_object} - {self.field_name} {self.change_type} at {self.timestamp}"

    def get_old_value_parsed(self):
        """Parse old value from JSON if possible."""
        if self.old_value:
            try:
                return json.loads(self.old_value)
            except (json.JSONDecodeError, TypeError):
                return self.old_value
        return None

    def get_new_value_parsed(self):
        """Parse new value from JSON if possible."""
        if self.new_value:
            try:
                return json.loads(self.new_value)
            except (json.JSONDecodeError, TypeError):
                return self.new_value
        return None