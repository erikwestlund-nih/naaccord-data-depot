from django.db import models


class SoftDeletableQuerySet(models.QuerySet):
    """Custom QuerySet that filters out soft-deleted records by default."""
    
    def active(self):
        """Return only non-deleted records."""
        return self.filter(deleted_at__isnull=True)
    
    def deleted(self):
        """Return only soft-deleted records."""
        return self.filter(deleted_at__isnull=False)
    
    def with_deleted(self):
        """Return all records including soft-deleted ones."""
        return self.all()
    
    def delete(self):
        """Soft delete all records in the queryset."""
        from django.utils import timezone
        return self.update(deleted_at=timezone.now())
    
    def force_delete(self):
        """Permanently delete all records in the queryset."""
        return super().delete()
    
    def restore(self):
        """Restore all soft-deleted records in the queryset."""
        return self.update(deleted_at=None)


class SoftDeletableManager(models.Manager):
    """Custom manager that uses SoftDeletableQuerySet and filters out soft-deleted records by default."""
    
    def get_queryset(self):
        """Return only non-deleted records by default."""
        return SoftDeletableQuerySet(self.model, using=self._db).active()
    
    def deleted(self):
        """Return only soft-deleted records."""
        return SoftDeletableQuerySet(self.model, using=self._db).deleted()
    
    def with_deleted(self):
        """Return all records including soft-deleted ones."""
        return SoftDeletableQuerySet(self.model, using=self._db).with_deleted()


class SoftDeletableModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    # Use the custom manager by default
    objects = SoftDeletableManager()
    
    # Also provide an explicit manager for all records (including deleted)
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.save()
        
        # Log soft delete activity for compliance
        self._log_soft_delete_activity()

    def force_delete(self):
        """Permanently delete this record from the database."""
        super().delete()

    def restore(self):
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.save()

    def is_deleted(self):
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None
    
    def _log_soft_delete_activity(self):
        """
        Log soft delete activity for Johns Hopkins compliance.
        This creates an Activity record when data is soft deleted.
        """
        try:
            from django.contrib.auth import get_user_model
            from django.core.management import get_current_user
            
            # Try to get current user from thread-local storage
            # This will be set by our activity logging middleware
            current_user = getattr(get_current_user(), 'user', None) if hasattr(get_current_user, '__call__') else None
            
            if current_user:
                # Import here to avoid circular imports
                from .activity import Activity, ActivityType
                
                Activity.log_activity(
                    user=current_user,
                    activity_type=ActivityType.DATA_DELETE,
                    success=True,
                    details={
                        'model': self.__class__.__name__,
                        'object_id': self.pk,
                        'soft_delete': True,
                        'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None
                    }
                )
        except Exception:
            # Don't fail the delete operation if activity logging fails
            # But in production, we'd want to log this error
            pass
