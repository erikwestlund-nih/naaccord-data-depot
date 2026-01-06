"""
Scheduled task to clean up orphaned temporary files.
Runs periodically to ensure no files are left behind after processing failures.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def cleanup_orphaned_files(self, hours: int = 4, dry_run: bool = False):
    """
    Clean up orphaned files older than specified hours.
    
    This task:
    1. Finds files marked for cleanup in PHIFileTracking
    2. Attempts to clean them up using TempFileManager
    3. Also checks WorkspaceManager for orphaned directories
    4. Logs all actions and sends alerts for failures
    
    Args:
        hours: Age threshold in hours (default 4)
        dry_run: If True, only report what would be cleaned (default False)
        
    Returns:
        Dictionary with cleanup statistics
    """
    from depot.storage.temp_file_manager import TempFileManager
    from depot.storage.scratch_manager import ScratchManager
    from depot.models import PHIFileTracking
    
    logger.info(f"Starting cleanup of orphaned files older than {hours} hours (dry_run={dry_run})")
    
    results = {
        'phi_tracking': {},
        'scratch_dirs': {},
        'total_cleaned': 0,
        'total_failed': 0,
        'alerts_sent': []
    }
    
    try:
        # Clean up files tracked in PHIFileTracking
        temp_manager = TempFileManager()
        phi_results = temp_manager.cleanup_all_orphaned(hours=hours, dry_run=dry_run)
        results['phi_tracking'] = phi_results
        
        # Clean up orphaned workspace directories
        scratch = ScratchManager()
        workspace_results = scratch.cleanup_orphaned_directories(hours=hours, dry_run=dry_run)
        results['scratch_dirs'] = workspace_results
        
        # Calculate totals
        results['total_cleaned'] = (
            phi_results.get('cleaned', 0) + 
            workspace_results.get('cleaned', 0)
        )
        results['total_failed'] = (
            phi_results.get('failed', 0) + 
            workspace_results.get('failed', 0)
        )
        
        # Check for files that have failed too many times
        if not dry_run:
            stuck_files = PHIFileTracking.objects.filter(
                cleanup_required=True,
                cleanup_attempted_count__gte=5
            )
            
            if stuck_files.exists():
                # Send alert for files that can't be cleaned
                alert_message = f"Found {stuck_files.count()} files that failed cleanup after 5 attempts"
                logger.error(alert_message)
                results['alerts_sent'].append(alert_message)
                
                # Log details of stuck files
                for stuck in stuck_files[:10]:  # Limit to first 10 for logging
                    logger.error(
                        f"Stuck file: {stuck.file_path} "
                        f"(attempts={stuck.cleanup_attempted_count}, "
                        f"created={stuck.created_at}, "
                        f"cohort={stuck.cohort.name if stuck.cohort else 'None'})"
                    )
        
        # Log summary
        logger.info(
            f"Cleanup complete: {results['total_cleaned']} cleaned, "
            f"{results['total_failed']} failed"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in cleanup task: {e}", exc_info=True)
        self.retry(exc=e, countdown=300)  # Retry in 5 minutes


@shared_task
def check_workspace_usage():
    """
    Monitor workspace disk usage and alert if too high.
    
    Returns:
        Dictionary with usage statistics
    """
    from depot.storage.scratch_manager import ScratchManager
    
    scratch = ScratchManager()
    usage = scratch.get_workspace_usage()
    
    # Alert if workspace is using more than 1GB
    if usage['total_size_mb'] > 1024:
        logger.warning(
            f"Workspace usage is high: {usage['total_size_mb']}MB "
            f"({usage['file_count']} files in {usage['directory_count']} directories)"
        )
    
    return usage


@shared_task
def verify_cleanup_consistency():
    """
    Verify that PHIFileTracking records match actual filesystem state.
    
    This task checks for:
    - Files that exist but aren't tracked
    - Tracked files that don't exist
    - Inconsistent cleanup states
    
    Returns:
        Dictionary with verification results
    """
    from depot.storage.scratch_manager import ScratchManager
    from depot.models import PHIFileTracking
    from pathlib import Path
    
    scratch = ScratchManager()
    results = {
        'untracked_files': [],
        'missing_tracked_files': [],
        'inconsistent_cleanup': [],
    }
    
    # Check scratch directories using storage abstraction
    # List all files in scratch prefixes
    try:
        all_files = scratch.storage.list_with_prefix(scratch.scratch_prefix, include_metadata=True)
        scratch_files = set()
        for file_path, mtime, size in all_files:
            scratch_files.add(file_path)
    except Exception as e:
        logger.error(f"Failed to list scratch files: {e}")
        scratch_files = set()

    # Check tracked files in PHI system
    tracked_files = list(PHIFileTracking.objects.filter(
        cleanup_required=True
    ).values_list('file_path', flat=True))

    # Find untracked files (exist but not tracked)
    for file_path in scratch_files:
        if file_path not in tracked_files:
            results['untracked_files'].append(file_path)

    # Find missing tracked files (tracked but don't exist) and fix them
    for tracked_path in tracked_files:
        file_exists = False

        # Check if file exists
        if tracked_path.startswith('scratch/'):
            file_exists = tracked_path in scratch_files
        else:
            # For non-scratch files, check filesystem directly (legacy behavior)
            from pathlib import Path
            path = Path(tracked_path)
            file_exists = path.exists()

        if not file_exists:
            results['missing_tracked_files'].append(tracked_path)
            logger.warning(f"Tracked file missing: {tracked_path}")

            # Fix: mark missing files as cleaned up (but preserve cleanup_required for inconsistency check)
            PHIFileTracking.objects.filter(
                file_path=tracked_path,
                cleanup_required=True,
                cleaned_up=False  # Only update records that aren't already cleaned
            ).update(cleaned_up=True)

    # Check for inconsistent cleanup states and fix them
    cleaned_tracking = PHIFileTracking.objects.filter(
        cleanup_required=True,
        cleaned_up=True
    )

    for tracking in cleaned_tracking:
        # This is inconsistent - cleanup_required=True but cleaned_up=True
        results['inconsistent_cleanup'].append(tracking.file_path)
        logger.warning(f"Inconsistent tracking state: {tracking.file_path} (cleanup_required=True but cleaned_up=True)")

        # Fix: remove cleanup requirement since it's already cleaned
        tracking.cleanup_required = False
        tracking.save()
    
    logger.info(
        f"Verification complete: {len(results['untracked_files'])} untracked, "
        f"{len(results['missing_tracked_files'])} missing, "
        f"{len(results['inconsistent_cleanup'])} inconsistent"
    )
    
    return results