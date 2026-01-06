"""
Temporary File Manager with guaranteed cleanup using context managers.
Ensures all temporary files are tracked in PHIFileTracking and cleaned up
even if the process fails or is terminated.
"""
import os
import shutil
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Union
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class TempFileManager:
    """
    Manages temporary files with guaranteed cleanup and tracking.
    Uses context managers to ensure cleanup even on exceptions.
    """
    
    @contextmanager
    def track_temp_file(
        self,
        file_path: Union[str, Path],
        cohort,
        user,
        file_type: str = 'temp_working',
        retention_hours: int = 4,
        content_object=None
    ):
        """
        Context manager for tracking and cleaning up temporary files.
        
        Args:
            file_path: Path to the temporary file or directory
            cohort: Cohort object for access control
            user: User who created the file
            file_type: Type of file for tracking
            retention_hours: How long the file should be retained
            content_object: Optional related object (e.g., PrecheckRun)
            
        Yields:
            Path object for the file
            
        Example:
            with temp_manager.track_temp_file(path, cohort, user) as temp_path:
                # Use temp_path
                pass
            # File is automatically cleaned up here
        """
        from depot.models import PHIFileTracking
        
        file_path = Path(file_path)
        tracking = None
        
        try:
            # Calculate file size if it exists
            file_size = None
            if file_path.exists():
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                elif file_path.is_dir():
                    file_size = sum(
                        f.stat().st_size for f in file_path.rglob('*') if f.is_file()
                    )
            
            # Create tracking record
            tracking = PHIFileTracking.objects.create(
                cohort=cohort,
                user=user,
                action='work_copy_created',
                file_path=str(file_path),
                file_type=file_type,
                file_size=file_size,
                cleanup_required=True,
                parent_process_id=os.getpid(),
                expected_cleanup_by=timezone.now() + timedelta(hours=retention_hours),
                content_object=content_object,
            )
            
            logger.info(f"Tracking temporary file: {file_path} (tracking_id={tracking.id})")
            
            # Yield the path for use
            yield file_path
            
        finally:
            # Always attempt cleanup
            if tracking:
                success = self._cleanup_with_retry(file_path, tracking, user)
                if not success:
                    logger.error(f"Failed to cleanup {file_path} after all retries")
    
    @contextmanager
    def track_temp_directory(
        self,
        directory_path: Union[str, Path],
        cohort,
        user,
        retention_hours: int = 4,
        content_object=None
    ):
        """
        Context manager specifically for temporary directories.
        
        Args:
            directory_path: Path to the temporary directory
            cohort: Cohort object for access control
            user: User who created the directory
            retention_hours: How long the directory should be retained
            content_object: Optional related object
            
        Yields:
            Path object for the directory
        """
        with self.track_temp_file(
            file_path=directory_path,
            cohort=cohort,
            user=user,
            file_type='temp_working',
            retention_hours=retention_hours,
            content_object=content_object
        ) as temp_dir:
            yield temp_dir
    
    def _cleanup_with_retry(
        self,
        file_path: Path,
        tracking,
        user,
        max_attempts: int = 3
    ) -> bool:
        """
        Attempt to clean up a file with retry logic.
        
        Args:
            file_path: Path to clean up
            tracking: PHIFileTracking record
            user: User performing cleanup
            max_attempts: Maximum number of attempts
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        from depot.models import PHIFileTracking
        
        for attempt in range(max_attempts):
            try:
                if file_path.exists():
                    if file_path.is_dir():
                        shutil.rmtree(file_path)
                        logger.info(f"Cleaned up directory: {file_path}")
                    else:
                        os.unlink(file_path)
                        logger.info(f"Cleaned up file: {file_path}")
                else:
                    logger.info(f"File already gone: {file_path}")
                
                # Mark as cleaned up in tracking
                if tracking:
                    tracking.cleanup_required = False
                    tracking.cleaned_up = True
                    tracking.cleanup_verified_at = timezone.now()
                    tracking.cleanup_verified_by = user
                    tracking.save()
                    
                    # Log the cleanup
                    PHIFileTracking.objects.create(
                        cohort=tracking.cohort,
                        user=user,
                        action='work_copy_deleted',
                        file_path=str(file_path),
                        file_type=tracking.file_type,
                        content_object=tracking.content_object,
                    )
                
                return True
                
            except Exception as e:
                logger.warning(
                    f"Cleanup attempt {attempt + 1}/{max_attempts} failed for {file_path}: {e}"
                )
                if tracking:
                    tracking.cleanup_attempted_count += 1
                    tracking.error_message = str(e)
                    tracking.save()
                
                # If this was the last attempt, return False
                if attempt == max_attempts - 1:
                    return False
                    
        return False
    
    def cleanup_orphaned_file(self, tracking_record) -> bool:
        """
        Clean up a file based on its tracking record.
        Used by scheduled cleanup jobs.
        
        Args:
            tracking_record: PHIFileTracking record
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        file_path = Path(tracking_record.file_path)
        return self._cleanup_with_retry(
            file_path=file_path,
            tracking=tracking_record,
            user=None,  # System cleanup
            max_attempts=1  # Single attempt for scheduled cleanup
        )
    
    def find_orphaned_files(self, hours: int = 4) -> list:
        """
        Find files that should have been cleaned up.
        
        Args:
            hours: Age threshold in hours
            
        Returns:
            QuerySet of PHIFileTracking records needing cleanup
        """
        from depot.models import PHIFileTracking
        
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        return PHIFileTracking.objects.filter(
            cleanup_required=True,
            created_at__lt=cutoff_time,
            cleanup_attempted_count__lt=5  # Don't keep trying forever
        ).select_related('cohort', 'user')
    
    def cleanup_all_orphaned(self, hours: int = 4, dry_run: bool = False) -> dict:
        """
        Clean up all orphaned files older than specified hours.
        
        Args:
            hours: Age threshold in hours
            dry_run: If True, only report what would be cleaned
            
        Returns:
            Dictionary with cleanup statistics
        """
        orphaned = self.find_orphaned_files(hours)
        
        cleaned = 0
        failed = 0
        
        for tracking in orphaned:
            if dry_run:
                logger.info(f"[DRY RUN] Would clean up: {tracking.file_path}")
                cleaned += 1
            else:
                if self.cleanup_orphaned_file(tracking):
                    cleaned += 1
                else:
                    failed += 1
                    if tracking.cleanup_attempted_count >= 5:
                        # Alert on repeated failures
                        logger.error(
                            f"Failed to cleanup {tracking.file_path} after 5 attempts. "
                            f"Manual intervention required."
                        )
        
        return {
            'found': orphaned.count(),
            'cleaned': cleaned,
            'failed': failed,
            'dry_run': dry_run,
        }