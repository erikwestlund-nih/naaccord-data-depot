"""
Universal observer pattern for tracking all Django model changes.

Johns Hopkins Requirements:
- "We will use an observer pattern of all records to log modifications"
- Track all changes with appropriate timestamps and authentication information
- Observer pattern on ALL models (not selective)
"""
from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
import json
import threading
from typing import Optional, Any, Dict


# Thread-local storage for current user context
_thread_local = threading.local()


def get_current_user():
    """Get the current user from thread-local storage."""
    return getattr(_thread_local, 'user', None)


def set_current_user(user):
    """Set the current user in thread-local storage."""
    _thread_local.user = user


def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_thread_local, 'request', None)


def set_current_request(request):
    """Set the current request in thread-local storage."""
    _thread_local.request = request


class ModelObserver:
    """
    Universal observer for Django model changes.
    Implements the observer pattern required by Johns Hopkins.
    """
    
    # Models to exclude from automatic observation
    EXCLUDED_MODELS = {
        # Core audit system (avoid recursion)
        'Activity',
        'DataRevision',

        # Django system models
        'ContentType',
        'Permission',
        'Session',
        'LogEntry',

        # Internal tracking models (high-volume, automatic)
        'PHIFileTracking',  # File security tracking - creates hundreds per upload
        'AccessLog',        # Page access tracking - one per page load
        'Revision',         # Generic revision tracking - automatic
        'SubmissionActivity',  # Already has its own logging system
        'PrecheckRun',   # Automatic validation results

        # Supporting models that are created as side effects
        'DataTableFilePatientIDs',  # Auto-extracted during processing
        'NotebookAccess',   # Automatic when notebooks are viewed
        'CeleryResult',     # Task execution results
        'TaskResult',       # Django-celery-results task storage - creates microsecond updates
        'AxesAccessLog',    # Security attempt logging
        'PHIFileTracking',  # File security tracking - creates dozens per upload (back to excluded)
        'PrecheckRun',   # Automatic validation results (back to excluded)
    }
    
    @classmethod
    def should_observe_model(cls, model_class) -> bool:
        """Determine if a model should be observed for changes."""
        model_name = model_class.__name__
        
        # Skip excluded models
        if model_name in cls.EXCLUDED_MODELS:
            return False
            
        # Skip abstract models
        if model_class._meta.abstract:
            return False
            
        return True
    
    @classmethod
    def serialize_field_value(cls, value: Any) -> str:
        """
        Serialize field value for storage in DataRevision.
        Handles complex types like dates, decimals, foreign keys.
        """
        if value is None:
            return None
            
        # Handle Django model instances (foreign keys)
        if isinstance(value, models.Model):
            return json.dumps({
                'model': value.__class__.__name__,
                'pk': value.pk,
                'str': str(value)
            })
            
        # Handle other complex types
        try:
            # Try JSON serialization first
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            # Fallback to string representation
            return str(value)
    
    @classmethod
    def get_model_field_values(cls, instance: models.Model) -> Dict[str, Any]:
        """Get all field values for a model instance."""
        values = {}
        
        for field in instance._meta.fields:
            field_name = field.name
            try:
                field_value = getattr(instance, field_name)
                values[field_name] = cls.serialize_field_value(field_value)
            except Exception:
                # Skip fields that can't be accessed
                values[field_name] = None
                
        return values
    
    @classmethod
    def create_data_revision(
        cls,
        instance: models.Model,
        field_name: str,
        old_value: Any,
        new_value: Any,
        change_type: str,
        activity_instance=None
    ):
        """Create a DataRevision record for field changes."""
        try:
            from depot.models import Activity, DataRevision, ActivityType
            
            # Get or create activity context
            if activity_instance is None:
                current_user = get_current_user()
                current_request = get_current_request()
                
                if current_user:
                    activity_instance = Activity.log_activity(
                        user=current_user,
                        activity_type=getattr(ActivityType, f'DATA_{change_type.upper()}', ActivityType.DATA_UPDATE),
                        request=current_request,
                        details={
                            'model': instance.__class__.__name__,
                            'object_id': instance.pk,
                            'observer_pattern': True
                        }
                    )
                else:
                    # System changes without user context - still need to log
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    
                    # Try to get a system user or create activity without user
                    try:
                        system_user = User.objects.filter(is_staff=True, email__contains='system').first()
                        if not system_user:
                            system_user = User.objects.filter(is_superuser=True).first()
                            
                        if system_user:
                            activity_instance = Activity.log_activity(
                                user=system_user,
                                activity_type=getattr(ActivityType, f'DATA_{change_type.upper()}', ActivityType.DATA_UPDATE),
                                details={
                                    'model': instance.__class__.__name__,
                                    'object_id': instance.pk,
                                    'observer_pattern': True,
                                    'system_change': True
                                }
                            )
                    except Exception:
                        # If we can't find a system user, skip activity logging
                        # but continue with DataRevision creation
                        pass
            
            if activity_instance:
                # Create the DataRevision record
                DataRevision.objects.create(
                    activity=activity_instance,
                    content_type=ContentType.objects.get_for_model(instance),
                    object_id=instance.pk,
                    field_name=field_name,
                    old_value=cls.serialize_field_value(old_value),
                    new_value=cls.serialize_field_value(new_value),
                    change_type=change_type
                )
                
        except Exception as e:
            # Don't fail the original model save if audit logging fails
            # In production, we'd want to log this error
            import logging
            logger = logging.getLogger('depot.audit')
            logger.error(f"Failed to create DataRevision: {e}")


# Store original field values before save
_pre_save_instances = {}


@receiver(pre_save)
def pre_save_observer(sender, instance, **kwargs):
    """
    Capture model state before save to detect field changes.
    Johns Hopkins requirement: Observer pattern for ALL records.
    """
    if not ModelObserver.should_observe_model(sender):
        return
        
    # Store the instance state before changes
    instance_key = (sender.__name__, instance.pk) if instance.pk else None
    
    if instance_key and instance.pk:
        # Get the existing instance from database
        try:
            original_instance = sender.objects.get(pk=instance.pk)
            _pre_save_instances[instance_key] = ModelObserver.get_model_field_values(original_instance)
        except sender.DoesNotExist:
            # New instance
            _pre_save_instances[instance_key] = {}
    else:
        # New instance without PK yet
        _pre_save_instances[instance_key] = {}


@receiver(post_save)
def post_save_observer(sender, instance, created, **kwargs):
    """
    Track model changes after save.
    Creates DataRevision records for all field changes.
    """
    # Skip during tests to avoid foreign key constraint issues
    from django.conf import settings
    if getattr(settings, 'TESTING', False) and not getattr(settings, 'TEST_ACTIVITY_LOGGING', False):
        return

    if not ModelObserver.should_observe_model(sender):
        return
        
    instance_key = (sender.__name__, instance.pk)
    
    if created:
        # New record created - log all fields as "new"
        current_values = ModelObserver.get_model_field_values(instance)
        
        # Create single activity for the entire record creation
        current_user = get_current_user()
        activity_instance = None
        
        if current_user:
            from depot.models import Activity, ActivityType
            from uuid import UUID

            # Convert UUID primary keys to strings for JSON serialization
            object_id = instance.pk
            if isinstance(object_id, UUID):
                object_id = str(object_id)

            activity_instance = Activity.log_activity(
                user=current_user,
                activity_type=ActivityType.DATA_CREATE,
                request=get_current_request(),
                details={
                    'model': sender.__name__,
                    'object_id': object_id,
                    'created': True
                }
            )
        
        # Create DataRevision for each field
        for field_name, new_value in current_values.items():
            ModelObserver.create_data_revision(
                instance=instance,
                field_name=field_name,
                old_value=None,
                new_value=new_value,
                change_type='create',
                activity_instance=activity_instance
            )
    else:
        # Existing record updated - compare with pre-save values
        original_values = _pre_save_instances.get(instance_key, {})
        current_values = ModelObserver.get_model_field_values(instance)
        
        changed_fields = []
        activity_instance = None
        
        for field_name, new_value in current_values.items():
            old_value = original_values.get(field_name)
            
            # Compare values (handle serialization differences)
            if old_value != new_value:
                changed_fields.append(field_name)
                
                # Create activity instance on first change
                if activity_instance is None:
                    current_user = get_current_user()
                    if current_user:
                        from depot.models import Activity, ActivityType
                        from uuid import UUID

                        # Convert UUID to string for JSON serialization
                        object_id = str(instance.pk) if isinstance(instance.pk, UUID) else instance.pk

                        activity_instance = Activity.log_activity(
                            user=current_user,
                            activity_type=ActivityType.DATA_UPDATE,
                            request=get_current_request(),
                            details={
                                'model': sender.__name__,
                                'object_id': object_id,
                                'fields_changed': changed_fields
                            }
                        )
                
                # Create DataRevision for this field change
                ModelObserver.create_data_revision(
                    instance=instance,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    change_type='update',
                    activity_instance=activity_instance
                )
    
    # Clean up stored instance data
    if instance_key in _pre_save_instances:
        del _pre_save_instances[instance_key]


@receiver(post_delete)
def post_delete_observer(sender, instance, **kwargs):
    """Track model deletions."""
    if not ModelObserver.should_observe_model(sender):
        return
        
    current_user = get_current_user()
    if current_user:
        from depot.models import Activity, ActivityType
        from uuid import UUID

        # Convert UUID to string for JSON serialization
        object_id = str(instance.pk) if isinstance(instance.pk, UUID) else instance.pk

        activity_instance = Activity.log_activity(
            user=current_user,
            activity_type=ActivityType.DATA_DELETE,
            request=get_current_request(),
            details={
                'model': sender.__name__,
                'object_id': object_id,
                'force_delete': True  # Distinguish from soft delete
            }
        )
        
        # Create DataRevision showing deletion
        ModelObserver.create_data_revision(
            instance=instance,
            field_name='__deleted__',
            old_value=True,
            new_value=None,
            change_type='delete',
            activity_instance=activity_instance
        )