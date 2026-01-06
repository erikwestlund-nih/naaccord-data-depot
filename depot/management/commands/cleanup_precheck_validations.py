"""
Management command to cleanup precheck validation files with PHI tracking.

Handles cleanup of:
- Staged files from AJAX uploads
- Temporary files from validation processing
- Files from completed/failed validations
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from depot.models import PHIFileTracking, PrecheckValidation
from depot.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Cleanup precheck validation files after processing is complete'

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
            help='Clean up all precheck validation files marked for cleanup'
        )
        parser.add_argument(
            '--status',
            choices=['completed', 'failed', 'all'],
            default='all',
            help='Only clean up validations with specific status (default: all)'
        )

    def handle(self, *args, **options):
        hours = options['hours']
        dry_run = options['dry_run']
        cleanup_all = options['all']
        status_filter = options['status']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No files will be deleted'))

        # Get scratch storage
        scratch_storage = StorageManager.get_scratch_storage()

        # Find PHI tracking records for precheck validations that need cleanup
        tracking_query = PHIFileTracking.objects.filter(
            action='precheck_upload_staged',
            cleanup_required=True,
            cleaned_up=False
        )

        # Filter by age if not --all
        if not cleanup_all:
            cutoff_time = timezone.now() - timedelta(hours=hours)
            tracking_query = tracking_query.filter(created_at__lt=cutoff_time)
            self.stdout.write(f"Looking for precheck validation files older than {hours} hours...")
        else:
            self.stdout.write("Looking for ALL precheck validation files marked for cleanup...")

        # Filter by validation status if specified
        if status_filter != 'all':
            # Get validation IDs with specific status
            validation_ids = PrecheckValidation.objects.filter(
                status=status_filter
            ).values_list('id', flat=True)

            # Filter tracking records by validation ID in metadata
            from django.db.models import Q
            tracking_query = tracking_query.filter(
                Q(metadata__precheck_validation_id__in=[str(vid) for vid in validation_ids])
            )
            self.stdout.write(f"Filtering for validations with status: {status_filter}")

        tracking_records = tracking_query.all()
        total_count = tracking_records.count()
        self.stdout.write(f"Found {total_count} files to clean up")

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No files to clean up"))
            return

        success_count = 0
        error_count = 0
        already_deleted_count = 0

        for tracking in tracking_records:
            try:
                file_path = tracking.file_path
                relative_path = tracking.metadata.get('relative_path', file_path)

                self.stdout.write(f"\nProcessing: {file_path}")

                # Check validation status
                validation_id = tracking.metadata.get('precheck_validation_id')
                if validation_id:
                    try:
                        validation = PrecheckValidation.objects.get(id=validation_id)
                        self.stdout.write(f"  Validation status: {validation.status}")
                    except PrecheckValidation.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"  Validation not found: {validation_id}"))

                # Check if file exists
                if scratch_storage.exists(relative_path):
                    if not dry_run:
                        # Delete the file
                        if scratch_storage.delete(relative_path):
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
                                purpose_subdirectory='auto_cleanup_precheck_validation'
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(f"  ✗ Failed to delete: {file_path}")
                            )
                            error_count += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"  Would delete: {file_path}")
                        )
                        success_count += 1
                else:
                    # File already deleted (perhaps manually or by another process)
                    if not dry_run:
                        tracking.mark_cleaned_up()
                        self.stdout.write(
                            self.style.WARNING(f"  ⚠ File already deleted, marking as cleaned: {file_path}")
                        )
                    already_deleted_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Error processing {file_path}: {str(e)}")
                )
                logger.error(f"Error cleaning up precheck validation file {file_path}: {e}", exc_info=True)
                error_count += 1

        # Summary
        self.stdout.write("\n" + "="*60)
        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN COMPLETE"))
            self.stdout.write(f"  Would delete: {success_count}")
        else:
            self.stdout.write(self.style.SUCCESS(f"CLEANUP COMPLETE"))
            self.stdout.write(f"  Successfully deleted: {success_count}")
            self.stdout.write(f"  Already deleted: {already_deleted_count}")
            self.stdout.write(f"  Errors: {error_count}")

        self.stdout.write(f"  Total processed: {total_count}")

        # Check for overdue cleanup
        overdue_tracking = PHIFileTracking.objects.filter(
            action='precheck_upload_staged',
            cleanup_required=True,
            cleaned_up=False,
            expected_cleanup_by__lt=timezone.now()
        )
        overdue_count = overdue_tracking.count()

        if overdue_count > 0:
            self.stdout.write("\n" + "="*60)
            self.stdout.write(
                self.style.WARNING(f"⚠ WARNING: {overdue_count} files are OVERDUE for cleanup")
            )
            self.stdout.write("Run with --all to clean them up immediately")
