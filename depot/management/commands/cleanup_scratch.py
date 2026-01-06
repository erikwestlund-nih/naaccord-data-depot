"""
Management command to manually clean up scratch files and verify cleanup status.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pathlib import Path


class Command(BaseCommand):
    help = 'Clean up orphaned scratch files and verify cleanup status'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours',
            type=int,
            default=4,
            help='Age threshold in hours for considering files orphaned (default: 4)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without actually deleting'
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify consistency without cleaning'
        )
        parser.add_argument(
            '--show-usage',
            action='store_true',
            help='Show scratch disk usage statistics'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup even for recent files (use with caution)'
        )
    
    def handle(self, *args, **options):
        from depot.storage.scratch_manager import ScratchManager
        from depot.storage.temp_file_manager import TempFileManager
        from depot.models import PHIFileTracking
        from depot.tasks.cleanup_orphaned_files import verify_cleanup_consistency
        
        # Show scratch usage if requested
        if options['show_usage']:
            self.show_scratch_usage()
            return
        
        # Verify consistency if requested
        if options['verify_only']:
            self.verify_consistency()
            return
        
        # Perform cleanup
        hours = options['hours']
        dry_run = options['dry_run']
        force = options['force']
        
        if force:
            self.stdout.write(
                self.style.WARNING(
                    "Force mode enabled - will clean ALL scratch files!"
                )
            )
            hours = 0  # Clean everything
        
        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}Cleaning up files older than {hours} hours..."
        )
        
        # Clean up using TempFileManager (PHI tracked files)
        self.clean_phi_tracked_files(hours, dry_run)
        
        # Clean up using WorkspaceManager (directory-based)
        self.clean_scratch_directories(hours, dry_run)
        
        # Show final status
        self.show_cleanup_status()
    
    def show_scratch_usage(self):
        """Display scratch disk usage statistics."""
        from depot.storage.scratch_manager import ScratchManager
        
        scratch = ScratchManager()
        usage = scratch.get_scratch_usage()
        
        self.stdout.write(self.style.SUCCESS("\n=== Workspace Usage ==="))
        self.stdout.write(f"Root: {usage['scratch_root']}")
        self.stdout.write(f"Total Size: {usage['total_size_mb']} MB")
        self.stdout.write(f"Files: {usage['file_count']}")
        self.stdout.write(f"Directories: {usage['directory_count']}")
        
        # List directories by size
        self.stdout.write("\n=== Directory Breakdown ===")
        for category in ['precheck_runs', 'submissions']:
            category_dir = Path(usage['scratch_root']) / category
            if category_dir.exists():
                dirs = list(category_dir.iterdir())
                self.stdout.write(f"\n{category}: {len(dirs)} directories")
                
                # Show largest directories
                dir_sizes = []
                for d in dirs:
                    if d.is_dir():
                        size = sum(f.stat().st_size for f in d.rglob('*') if f.is_file())
                        dir_sizes.append((d.name, size))
                
                dir_sizes.sort(key=lambda x: x[1], reverse=True)
                for name, size in dir_sizes[:5]:  # Top 5
                    size_mb = round(size / (1024 * 1024), 2)
                    self.stdout.write(f"  {name}: {size_mb} MB")
    
    def verify_consistency(self):
        """Verify PHIFileTracking consistency with filesystem."""
        from depot.tasks.cleanup_orphaned_files import verify_cleanup_consistency
        
        self.stdout.write(self.style.SUCCESS("\n=== Verifying Consistency ==="))
        
        results = verify_cleanup_consistency()
        
        # Show untracked files
        if results['untracked_files']:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFound {len(results['untracked_files'])} untracked files:"
                )
            )
            for path in results['untracked_files'][:10]:
                self.stdout.write(f"  - {path}")
            if len(results['untracked_files']) > 10:
                self.stdout.write(f"  ... and {len(results['untracked_files']) - 10} more")
        
        # Show missing tracked files
        if results['missing_tracked_files']:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFound {len(results['missing_tracked_files'])} missing tracked files:"
                )
            )
            for path in results['missing_tracked_files'][:10]:
                self.stdout.write(f"  - {path}")
        
        # Show inconsistent states
        if results['inconsistent_cleanup']:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFixed {len(results['inconsistent_cleanup'])} inconsistent tracking states"
                )
            )
        
        if not any([results['untracked_files'], results['missing_tracked_files'], 
                   results['inconsistent_cleanup']]):
            self.stdout.write(self.style.SUCCESS("\nAll files are properly tracked!"))
    
    def clean_phi_tracked_files(self, hours, dry_run):
        """Clean up files tracked in PHIFileTracking."""
        from depot.storage.temp_file_manager import TempFileManager
        
        self.stdout.write("\n=== Cleaning PHI Tracked Files ===")
        
        temp_manager = TempFileManager()
        results = temp_manager.cleanup_all_orphaned(hours=hours, dry_run=dry_run)
        
        self.stdout.write(f"Found: {results['found']} files")
        self.stdout.write(
            self.style.SUCCESS(f"Cleaned: {results['cleaned']} files")
        )
        if results['failed'] > 0:
            self.stdout.write(
                self.style.ERROR(f"Failed: {results['failed']} files")
            )
    
    def clean_scratch_directories(self, hours, dry_run):
        """Clean up scratch directories."""
        from depot.storage.scratch_manager import ScratchManager
        
        self.stdout.write("\n=== Cleaning Workspace Directories ===")
        
        scratch = ScratchManager()
        results = scratch.cleanup_orphaned_directories(hours=hours, dry_run=dry_run)
        
        self.stdout.write(f"Found: {results['found']} directories")
        self.stdout.write(
            self.style.SUCCESS(f"Cleaned: {results['cleaned']} directories")
        )
        if results['failed'] > 0:
            self.stdout.write(
                self.style.ERROR(f"Failed: {results['failed']} directories")
            )
        
        # Show cleaned paths if not too many
        if results['cleaned_paths'] and len(results['cleaned_paths']) <= 20:
            self.stdout.write("\nCleaned:")
            for path in results['cleaned_paths']:
                self.stdout.write(f"  - {path}")
    
    def show_cleanup_status(self):
        """Show current cleanup status."""
        from depot.models import PHIFileTracking
        
        self.stdout.write(self.style.SUCCESS("\n=== Cleanup Status ==="))
        
        # Count files needing cleanup
        pending_cleanup = PHIFileTracking.objects.filter(
            cleanup_required=True,
            cleaned_up=False
        ).count()
        
        # Count stuck files
        stuck_files = PHIFileTracking.objects.filter(
            cleanup_required=True,
            cleanup_attempted_count__gte=5
        ).count()
        
        # Recent cleanup activity
        recent_cleanup = PHIFileTracking.objects.filter(
            action='work_copy_deleted',
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        
        self.stdout.write(f"Files pending cleanup: {pending_cleanup}")
        if stuck_files > 0:
            self.stdout.write(
                self.style.ERROR(f"Files stuck (5+ attempts): {stuck_files}")
            )
        self.stdout.write(f"Files cleaned in last 24h: {recent_cleanup}")
        
        # Show stuck files if any
        if stuck_files > 0:
            stuck_records = PHIFileTracking.objects.filter(
                cleanup_required=True,
                cleanup_attempted_count__gte=5
            ).order_by('-cleanup_attempted_count')[:5]
            
            self.stdout.write("\nStuck files (require manual intervention):")
            for record in stuck_records:
                self.stdout.write(
                    f"  - {record.file_path} "
                    f"(attempts={record.cleanup_attempted_count}, "
                    f"created={record.created_at.strftime('%Y-%m-%d %H:%M')})"
                )