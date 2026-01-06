"""
Management command to cleanup upload precheck files with PHI tracking.
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from depot.models import PHIFileTracking
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup upload precheck files that have been processed'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Clean up files older than this many hours (default: 24)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clean up all upload precheck files marked for cleanup'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        cleanup_all = options['all']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No files will be deleted'))

        # Get storage for uploads
        storage = StorageManager.get_storage('uploads')

        # Find PHI tracking records for upload prechecks that need cleanup
        # Handle both with and without /media/submissions/ prefix
        from django.db.models import Q
        tracking_query = PHIFileTracking.objects.filter(
            action='file_uploaded_via_stream',
            cleanup_required=True,
            cleaned_up=False
        ).filter(
            Q(file_path__startswith='precheck_runs/') |
            Q(file_path__startswith='/media/submissions/precheck_runs/') |
            Q(file_path__startswith='media/submissions/precheck_runs/')
        )

        if not cleanup_all:
            cutoff_time = timezone.now() - timedelta(hours=hours)
            tracking_query = tracking_query.filter(created_at__lt=cutoff_time)
            self.stdout.write(f"Looking for upload precheck files older than {hours} hours...")
        else:
            self.stdout.write("Looking for ALL upload precheck files marked for cleanup...")

        tracking_records = tracking_query.all()
        self.stdout.write(f"Found {tracking_records.count()} files to clean up")

        success_count = 0
        error_count = 0

        for tracking in tracking_records:
            try:
                file_path = tracking.file_path
                self.stdout.write(f"Processing: {file_path}")

                # Remove /media/submissions/ prefix if present for storage operations
                storage_path = file_path
                if storage_path.startswith('/media/submissions/'):
                    storage_path = storage_path.replace('/media/submissions/', '')
                elif storage_path.startswith('media/submissions/'):
                    storage_path = storage_path.replace('media/submissions/', '')

                # Check if file exists
                if storage.exists(storage_path):
                    if not dry_run:
                        # Delete the file
                        if storage.delete(storage_path):
                            # Mark as cleaned up
                            tracking.mark_cleaned_up()
                            self.stdout.write(
                                self.style.SUCCESS(f"  ✓ Deleted and marked as cleaned: {file_path}")
                            )
                            success_count += 1

                            # Log cleanup action
                            PHIFileTracking.objects.create(
                                cohort=tracking.cohort,
                                user=tracking.user,
                                action='work_copy_deleted',
                                file_path=file_path,
                                file_type=tracking.file_type,
                                server_role='services',
                                purpose_subdirectory='cleanup_command'
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(f"  ✗ Failed to delete: {file_path}")
                            )
                            error_count += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"  [DRY RUN] Would delete: {file_path}")
                        )
                        success_count += 1
                else:
                    # File doesn't exist but tracking says it should
                    if not dry_run:
                        # Mark as cleaned up since file is already gone
                        tracking.mark_cleaned_up()
                        self.stdout.write(
                            self.style.WARNING(f"  ⚠ File already deleted, marking as cleaned: {file_path}")
                        )
                        success_count += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"  [DRY RUN] File already gone: {file_path}")
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing {tracking.file_path}: {e}")
                )
                logger.error(f"Error cleaning up {tracking.file_path}: {e}", exc_info=True)
                error_count += 1

        # Summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"DRY RUN COMPLETE: Would clean {success_count} files")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Cleanup complete: {success_count} files cleaned")
            )
            if error_count > 0:
                self.stdout.write(
                    self.style.ERROR(f"Errors encountered: {error_count} files failed")
                )

        # Show any remaining files that still need cleanup
        remaining = PHIFileTracking.objects.filter(
            action='file_uploaded_via_stream',
            cleanup_required=True,
            cleaned_up=False
        ).filter(
            Q(file_path__startswith='precheck_runs/') |
            Q(file_path__startswith='/media/submissions/precheck_runs/') |
            Q(file_path__startswith='media/submissions/precheck_runs/')
        ).count()

        if remaining > 0:
            self.stdout.write(
                self.style.WARNING(f"\n{remaining} upload precheck files still need cleanup")
            )