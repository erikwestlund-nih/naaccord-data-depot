"""
Migration utilities for transitioning from filesystem-based ScratchManager
to storage-abstraction-based ScratchManager.

This module provides compatibility shims and migration helpers to ensure
a smooth transition without breaking existing code.
"""
import os
import logging
from pathlib import Path
from typing import Union
from django.conf import settings

logger = logging.getLogger(__name__)


class ScratchManagerCompatibility:
    """
    Compatibility layer that provides both old Path-based interface
    and new storage-based interface during migration.
    """
    
    def __init__(self, use_new_implementation=None):
        """
        Initialize with option to force old or new implementation.
        
        Args:
            use_new_implementation: True to force new, False to force old,
                                  None to check environment variable
        """
        if use_new_implementation is None:
            # Check environment variable for migration control
            use_new_implementation = os.environ.get('USE_STORAGE_ABSTRACTION', 'false').lower() == 'true'
        
        self.use_new = use_new_implementation
        
        if self.use_new:
            from depot.storage.workspace_manager_refactored import WorkspaceManager as NewWorkspaceManager
            self._impl = NewWorkspaceManager()
            logger.info("Using NEW storage-abstraction-based WorkspaceManager")
        else:
            from depot.storage.workspace_manager import WorkspaceManager as OldWorkspaceManager
            self._impl = OldWorkspaceManager()
            logger.info("Using OLD filesystem-based WorkspaceManager")
    
    def get_precheck_run_dir(self, precheck_run_id: int) -> Union[Path, str]:
        """
        Get workspace directory for upload precheck.
        Returns Path for old implementation, string for new.
        """
        result = self._impl.get_precheck_run_dir(precheck_run_id)
        
        # Convert to Path if needed for compatibility
        if self.use_new and os.environ.get('WORKSPACE_COMPAT_MODE') == 'true':
            # In compatibility mode, convert string keys to Path objects
            # This helps during migration but should be removed eventually
            return Path(result)
        
        return result
    
    def cleanup_precheck_run(self, precheck_run_id: int) -> bool:
        """Compatible cleanup method."""
        return self._impl.cleanup_precheck_run(precheck_run_id)
    
    def get_workspace_usage(self) -> dict:
        """Compatible usage statistics method."""
        return self._impl.get_workspace_usage()
    
    def cleanup_orphaned_directories(self, hours: int = 4, dry_run: bool = False) -> dict:
        """Compatible orphaned cleanup method."""
        return self._impl.cleanup_orphaned_directories(hours, dry_run)


def migrate_existing_workspace_files():
    """
    One-time migration script to move existing filesystem workspace files
    to the new storage abstraction.
    
    This should be run once during deployment to migrate any existing
    temporary files from the old location to the new storage backend.
    """
    logger.info("Starting workspace migration...")
    
    # Get old workspace location
    nas_mount = os.environ.get('NAS_WORKSPACE_PATH')
    if nas_mount:
        old_workspace = Path(nas_mount) / 'workspace'
    else:
        old_workspace = Path(settings.BASE_DIR).parent / 'storage' / 'workspace'
    
    if not old_workspace.exists():
        logger.info("No old workspace found, nothing to migrate")
        return
    
    # Get new storage backend
    from depot.storage.manager import StorageManager
    new_storage = StorageManager.get_workspace_storage()
    
    migrated_count = 0
    failed_count = 0
    
    # Migrate each file
    for file_path in old_workspace.rglob('*'):
        if file_path.is_file():
            try:
                # Calculate relative path for storage key
                relative_path = file_path.relative_to(old_workspace.parent)
                storage_key = str(relative_path).replace('\\', '/')
                
                # Read file content
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                # Save to new storage
                new_storage.save(storage_key, content)
                
                # Delete old file after successful migration
                file_path.unlink()
                
                migrated_count += 1
                logger.debug(f"Migrated: {file_path} -> {storage_key}")
                
            except Exception as e:
                logger.error(f"Failed to migrate {file_path}: {e}")
                failed_count += 1
    
    # Clean up empty directories
    for dir_path in sorted(old_workspace.rglob('*'), reverse=True):
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            dir_path.rmdir()
            logger.debug(f"Removed empty directory: {dir_path}")
    
    logger.info(f"Migration complete: {migrated_count} files migrated, {failed_count} failed")
    
    if migrated_count > 0:
        logger.info("Remember to update USE_STORAGE_ABSTRACTION=true in environment")


def validate_storage_configuration():
    """
    Validate that storage is properly configured for workspace operations.
    """
    from depot.storage.manager import StorageManager
    
    try:
        # Test workspace storage
        storage = StorageManager.get_workspace_storage()
        
        # Test operations
        test_key = "workspace/validation_test.txt"
        test_content = b"Storage validation test"
        
        # Test save
        storage.save(test_key, test_content)
        logger.info("✓ Save operation successful")
        
        # Test exists
        if storage.exists(test_key):
            logger.info("✓ Exists check successful")
        else:
            logger.error("✗ Exists check failed")
            return False
        
        # Test get
        retrieved = storage.get_file(test_key)
        if retrieved == test_content:
            logger.info("✓ Get operation successful")
        else:
            logger.error("✗ Get operation returned incorrect content")
            return False
        
        # Test list
        files = storage.list_with_prefix("workspace/", include_metadata=True)
        if any(test_key in str(f[0]) for f in files):
            logger.info("✓ List operation successful")
        else:
            logger.error("✗ List operation failed to find test file")
            return False
        
        # Test delete
        storage.delete(test_key)
        if not storage.exists(test_key):
            logger.info("✓ Delete operation successful")
        else:
            logger.error("✗ Delete operation failed")
            return False
        
        # Test delete_prefix
        storage.save("workspace/test_prefix/file1.txt", b"test1")
        storage.save("workspace/test_prefix/file2.txt", b"test2")
        deleted = storage.delete_prefix("workspace/test_prefix/")
        if deleted == 2:
            logger.info("✓ Delete prefix operation successful")
        else:
            logger.error(f"✗ Delete prefix deleted {deleted} files, expected 2")
            return False
        
        logger.info("\n✓ All storage operations validated successfully!")
        logger.info(f"Storage backend: {type(storage).__name__}")
        return True
        
    except Exception as e:
        logger.error(f"Storage validation failed: {e}")
        return False


# Migration steps for deployment:
# 
# 1. Deploy new code with USE_STORAGE_ABSTRACTION=false (default)
# 2. Run validation: python manage.py shell -c "from depot.storage.migrate_to_storage_abstraction import validate_storage_configuration; validate_storage_configuration()"
# 3. Run migration: python manage.py shell -c "from depot.storage.migrate_to_storage_abstraction import migrate_existing_workspace_files; migrate_existing_workspace_files()"
# 4. Set USE_STORAGE_ABSTRACTION=true in staging
# 5. Monitor for 24 hours
# 6. Set USE_STORAGE_ABSTRACTION=true in production
# 7. After 7 days, remove old WorkspaceManager code