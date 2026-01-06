"""
Scratch Manager using storage abstraction.
Manages temporary file storage through the storage interface, enabling
cloud storage, NAS, or local filesystem backends without code changes.
"""
import os
import time
import logging
from typing import Optional, List, Dict, Tuple
from django.conf import settings

from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class ScratchManager:
    """
    Manages temporary file storage using storage abstraction.
    All cleanup logic and scheduling remains in application code.
    """
    
    def __init__(self):
        """Initialize scratch manager with storage backend."""
        # Get the scratch storage backend
        self.storage = StorageManager.get_scratch_storage()
        
        # Define scratch structure as prefixes
        self.scratch_prefix = "scratch/"
        self.precheck_runs_prefix = f"{self.scratch_prefix}precheck_runs/"
        # Alias to support renamed PrecheckRun model
        self.precheck_runs_prefix = self.precheck_runs_prefix
        self.submissions_prefix = f"{self.scratch_prefix}submissions/"
        self.cleanup_logs_prefix = f"{self.scratch_prefix}cleanup_logs/"
        
        # Test write permissions by creating a test file
        try:
            test_key = f"{self.scratch_prefix}.write_test"
            if self.storage.touch(test_key):
                self.storage.delete(test_key)
            else:
                raise PermissionError("Cannot write to scratch storage")
        except Exception as e:
            logger.error(f"Error setting up scratch storage: {e}")
            raise
        
        logger.info(f"Scratch manager initialized with prefix: {self.scratch_prefix}")
    
    def get_precheck_run_dir(self, precheck_run_id: int) -> str:
        """
        Get or create a dedicated directory for an upload precheck.
        
        Args:
            precheck_run_id: The ID of the upload precheck
            
        Returns:
            Storage key prefix for the upload precheck's scratch
        """
        prefix = f"{self.precheck_runs_prefix}{precheck_run_id}/"
        
        # Ensure the prefix exists (no-op for S3, creates dir for local)
        self.storage.ensure_prefix(prefix)
        
        logger.info(f"Created/accessed scratch for precheck_run {precheck_run_id}: {prefix}")
        return prefix

    # Backwards-compatible alias - old name redirects to new name
    def get_upload_precheck_dir(self, precheck_run_id: int) -> str:
        return self.get_precheck_run_dir(precheck_run_id)
    
    def get_submission_dir(self, submission_id: int) -> str:
        """
        Get or create a dedicated directory for a submission.
        
        Args:
            submission_id: The ID of the submission
            
        Returns:
            Storage key prefix for the submission's scratch
        """
        prefix = f"{self.submissions_prefix}{submission_id}/"
        
        # Ensure the prefix exists
        self.storage.ensure_prefix(prefix)
        
        logger.info(f"Created/accessed scratch for submission {submission_id}: {prefix}")
        return prefix
    
    def save_to_scratch(self, prefix: str, filename: str, content) -> str:
        """
        Save a file to the scratch.
        
        Args:
            prefix: The scratch prefix (from get_precheck_run_dir or get_submission_dir)
            filename: The filename to save
            content: The file content
            
        Returns:
            The full storage key of the saved file
        """
        key = f"{prefix}{filename}"
        self.storage.save(key, content)
        return key
    
    def get_from_scratch(self, key: str):
        """
        Retrieve a file from the scratch.
        
        Args:
            key: The storage key of the file
            
        Returns:
            File content or None if not found
        """
        return self.storage.get_file(key)
    
    def cleanup_precheck_run(self, precheck_run_id: int) -> bool:
        """
        Remove the entire scratch directory for an upload precheck.
        Our application controls when this happens, not the storage layer.
        
        Args:
            precheck_run_id: The ID of the upload precheck to clean up
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        prefix = f"{self.precheck_runs_prefix}{precheck_run_id}/"
        
        try:
            # Use storage abstraction to delete all files with this prefix
            deleted_count = self.storage.delete_prefix(prefix)
            
            if deleted_count > 0:
                logger.info(f"Successfully cleaned up precheck_run scratch: {prefix} ({deleted_count} files)")
            else:
                logger.warning(f"Upload precheck scratch {prefix} was already empty or doesn't exist")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup precheck_run scratch {prefix}: {e}")
            return False

    def cleanup_upload_precheck(self, precheck_run_id: int) -> bool:
        """Alias for cleanup_precheck_run using new terminology."""
        return self.cleanup_precheck_run(precheck_run_id)
    
    def cleanup_submission(self, submission_id: int) -> bool:
        """
        Remove the entire scratch directory for a submission.
        
        Args:
            submission_id: The ID of the submission to clean up
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        prefix = f"{self.submissions_prefix}{submission_id}/"
        
        try:
            deleted_count = self.storage.delete_prefix(prefix)
            
            if deleted_count > 0:
                logger.info(f"Successfully cleaned up submission scratch: {prefix} ({deleted_count} files)")
            else:
                logger.warning(f"Submission scratch {prefix} was already empty or doesn't exist")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup submission scratch {prefix}: {e}")
            return False
    
    def get_scratch_usage(self) -> Dict:
        """
        Get disk usage statistics for the scratch.
        
        Returns:
            Dictionary with usage statistics
        """
        try:
            # List all files in scratch with metadata
            all_files = self.storage.list_with_prefix(self.scratch_prefix, include_metadata=True)
            
            total_size = 0
            file_count = 0
            dir_prefixes = set()
            
            for path, mtime, size in all_files:
                file_count += 1
                total_size += size
                
                # Extract directory prefix
                parts = path.split('/')
                if len(parts) > 2:  # scratch/category/id/...
                    dir_prefix = '/'.join(parts[:3])
                    dir_prefixes.add(dir_prefix)
            
            return {
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'file_count': file_count,
                'directory_count': len(dir_prefixes),
                'scratch_prefix': self.scratch_prefix,
                'storage_backend': type(self.storage).__name__,
            }
            
        except Exception as e:
            logger.error(f"Failed to get scratch usage: {e}")
            return {
                'error': str(e),
                'scratch_prefix': self.scratch_prefix,
            }
    
    def list_orphaned_directories(self, hours: int = 4) -> List[str]:
        """
        Find scratch directories that are older than specified hours.
        This is OUR application logic for determining what's orphaned.
        
        Args:
            hours: Age threshold in hours
            
        Returns:
            List of orphaned directory prefixes
        """
        current_time = time.time()
        age_seconds = hours * 3600
        orphaned = []
        
        # Track directories we've seen
        checked_dirs = set()
        
        try:
            # List all files with metadata to check modification times
            for category in ['precheck_runs', 'submissions']:
                prefix = f"{self.scratch_prefix}{category}/"
                files = self.storage.list_with_prefix(prefix, include_metadata=True)
                
                # Group files by directory
                dir_files = {}
                for path, mtime, size in files:
                    # Extract directory ID from path
                    # Format: scratch/category/id/filename
                    parts = path.split('/')
                    if len(parts) >= 3:
                        dir_prefix = '/'.join(parts[:3]) + '/'
                        
                        if dir_prefix not in dir_files:
                            dir_files[dir_prefix] = []
                        dir_files[dir_prefix].append((path, mtime, size))
                
                # Check each directory's newest file
                for dir_prefix, dir_file_list in dir_files.items():
                    if dir_prefix in checked_dirs:
                        continue
                    checked_dirs.add(dir_prefix)
                    
                    # Find newest file in directory
                    newest_mtime = max(mtime for _, mtime, _ in dir_file_list)
                    
                    # Check if directory is orphaned based on newest file
                    if current_time - newest_mtime > age_seconds:
                        orphaned.append(dir_prefix)
                        logger.debug(f"Found orphaned directory: {dir_prefix} (age: {(current_time - newest_mtime) / 3600:.1f} hours)")
            
        except Exception as e:
            logger.error(f"Error listing orphaned directories: {e}")
        
        return orphaned
    
    def cleanup_orphaned_directories(self, hours: int = 4, dry_run: bool = False) -> Dict:
        """
        Clean up orphaned scratch directories older than specified hours.
        This is OUR application-controlled cleanup, not delegated to storage.
        
        Args:
            hours: Age threshold in hours
            dry_run: If True, only report what would be deleted
            
        Returns:
            Dictionary with cleanup statistics
        """
        orphaned = self.list_orphaned_directories(hours)
        cleaned = []
        failed = []
        
        for directory in orphaned:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete: {directory}")
                cleaned.append(directory)
            else:
                try:
                    deleted_count = self.storage.delete_prefix(directory)
                    logger.info(f"Cleaned up orphaned directory: {directory} ({deleted_count} files)")
                    cleaned.append(directory)
                    
                    # Track cleanup in PHIFileTracking if available
                    try:
                        from depot.models import PHIFileTracking
                        PHIFileTracking.log_operation(
                            cohort=None,  # System cleanup
                            user=None,    # Automated
                            action='scratch_cleanup',
                            file_path=directory,
                            file_type='scratch_directory'
                        )
                    except Exception as tracking_error:
                        logger.debug(f"Could not log cleanup to PHIFileTracking: {tracking_error}")
                        
                except Exception as e:
                    logger.error(f"Failed to cleanup {directory}: {e}")
                    failed.append(directory)
        
        return {
            'found': len(orphaned),
            'cleaned': len(cleaned),
            'failed': len(failed),
            'cleaned_paths': cleaned,
            'failed_paths': failed,
            'dry_run': dry_run,
        }
    
    def exists(self, key: str) -> bool:
        """
        Check if a file exists in the scratch.
        
        Args:
            key: The storage key to check
            
        Returns:
            True if the file exists, False otherwise
        """
        return self.storage.exists(key)
    
    def delete_file(self, key: str) -> bool:
        """
        Delete a specific file from the scratch.
        
        Args:
            key: The storage key of the file to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            return self.storage.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete file {key}: {e}")
            return False
