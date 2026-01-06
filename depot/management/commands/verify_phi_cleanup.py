from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from depot.models import PHIFileTracking
from depot.storage.phi_manager import PHIStorageManager
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verify PHI files have been properly cleaned up and clean orphaned files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Actually cleanup orphaned files (default is dry run)',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Files older than this many hours are considered overdue (default: 24)',
        )

    def handle(self, *args, **options):
        cleanup = options['cleanup']
        hours = options['hours']
        
        self.stdout.write("=" * 70)
        self.stdout.write("PHI File Cleanup Verification")
        self.stdout.write("=" * 70)
        
        # Check for overdue cleanups
        overdue = PHIFileTracking.get_overdue_cleanups()
        
        if overdue.exists():
            self.stdout.write(f"\nFound {overdue.count()} overdue cleanups:")
            for record in overdue[:20]:  # Show first 20
                age = timezone.now() - record.created_at
                self.stdout.write(
                    f"  - {record.file_path} "
                    f"(created {age.days}d {age.seconds//3600}h ago, "
                    f"should have been cleaned by {record.expected_cleanup_by})"
                )
        else:
            self.stdout.write(self.style.SUCCESS("\nNo overdue cleanups found!"))
        
        # Check for uncleaned workspace files
        uncleaned = PHIFileTracking.get_uncleaned_workspace_files()
        
        if uncleaned.exists():
            self.stdout.write(f"\nFound {uncleaned.count()} uncleaned workspace files:")
            for record in uncleaned[:20]:  # Show first 20
                self.stdout.write(f"  - {record.file_path}")
        else:
            self.stdout.write(self.style.SUCCESS("\nNo uncleaned workspace files found!"))
        
        # Perform cleanup if requested
        if cleanup and (overdue.exists() or uncleaned.exists()):
            self.stdout.write("\nPerforming cleanup...")
            phi_manager = PHIStorageManager()
            cleaned, errors = phi_manager.cleanup_all_workspace_files()
            
            self.stdout.write(f"Cleaned {cleaned} files")
            if errors:
                self.stdout.write(self.style.ERROR(f"Encountered {errors} errors during cleanup"))
        elif not cleanup and (overdue.exists() or uncleaned.exists()):
            self.stdout.write(
                self.style.WARNING(
                    "\nRun with --cleanup flag to actually clean these files"
                )
            )
        
        # Summary statistics
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("PHI Tracking Statistics:")
        self.stdout.write("=" * 70)
        
        total_tracked = PHIFileTracking.objects.count()
        nas_files = PHIFileTracking.objects.filter(
            action__in=['nas_raw_created', 'nas_duckdb_created']
        ).count()
        workspace_created = PHIFileTracking.objects.filter(
            action='work_copy_created'
        ).count()
        workspace_deleted = PHIFileTracking.objects.filter(
            action='work_copy_deleted'
        ).count()
        
        self.stdout.write(f"Total tracked operations: {total_tracked}")
        self.stdout.write(f"Files on NAS: {nas_files}")
        self.stdout.write(f"Workspace files created: {workspace_created}")
        self.stdout.write(f"Workspace files deleted: {workspace_deleted}")
        self.stdout.write(f"Workspace files pending cleanup: {workspace_created - workspace_deleted}")
        
        # Check for files without proper cleanup tracking
        missing_cleanup = PHIFileTracking.objects.filter(
            action='work_copy_created',
            cleaned_up=False,
            expected_cleanup_by__lt=timezone.now() - timedelta(hours=hours)
        ).count()
        
        if missing_cleanup > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWARNING: {missing_cleanup} workspace files are missing cleanup tracking!"
                )
            )