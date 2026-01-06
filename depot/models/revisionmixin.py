from django.db import models
from django.forms.models import model_to_dict
from django.contrib.contenttypes.models import ContentType
from datetime import datetime, date
from decimal import Decimal


def serialize_value(value):
    """Convert a value to a JSON-serializable format."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    elif isinstance(value, Decimal):
        return float(value)
    elif hasattr(value, 'pk'):  # Model instance
        return value.pk
    return value


class RevisionMixin:
    """Mixin to add revision tracking to any model."""
    
    # Fields to exclude from revision tracking
    revision_exclude_fields = ['created_at', 'updated_at', 'deleted_at']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = None
        if self.pk:
            self._original_values = model_to_dict(self)
    
    def save_revision(self, user, action='updated', ip_address=None, user_agent=''):
        """Save a revision record."""
        from depot.models import Revision
        
        changes = {}
        if action == 'updated' and self._original_values:
            current_values = model_to_dict(self)
            for field, new_value in current_values.items():
                if field in self.revision_exclude_fields:
                    continue
                old_value = self._original_values.get(field)
                if old_value != new_value:
                    changes[field] = {
                        'old': serialize_value(old_value),
                        'new': serialize_value(new_value)
                    }
        elif action == 'created':
            current_values = model_to_dict(self)
            for field, value in current_values.items():
                if field not in self.revision_exclude_fields and value:
                    changes[field] = {
                        'old': None,
                        'new': serialize_value(value)
                    }
        
        if changes or action == 'deleted':
            Revision.objects.create(
                content_type=ContentType.objects.get_for_model(self),
                object_id=self.pk,
                user=user,
                action=action,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
                model_name=self.__class__.__name__,
                object_repr=str(self)
            )
    
    def delete_with_revision(self, user, ip_address=None, user_agent=''):
        """Delete with revision tracking."""
        self.save_revision(user, 'deleted', ip_address, user_agent)
        super().delete()
    
    def save(self, *args, **kwargs):
        """Override save to track original values after save."""
        super().save(*args, **kwargs)
        # Update original values after successful save
        self._original_values = model_to_dict(self)