from django.core.management.base import BaseCommand
from django.utils import timezone
from depot.models import PHIFileTracking, DataTableFile
from datetime import datetime, timedelta
import re


class Command(BaseCommand):
    help = 'Show audit trail for PHI file operations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Show audit trail for a specific file path (supports wildcards)',
        )
        parser.add_argument(
            '--cohort',
            type=int,
            help='Filter by cohort ID',
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Filter by username',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Show operations from the last N days (default: 7)',
        )
        parser.add_argument(
            '--action',
            type=str,
            help='Filter by action type (e.g., nas_raw_created, work_copy_created)',
        )
        parser.add_argument(
            '--data-file',
            type=int,
            help='Show audit trail for a specific DataTableFile ID',
        )

    def handle(self, *args, **options):
        file_pattern = options.get('file')
        cohort_id = options.get('cohort')
        username = options.get('user')
        days = options.get('days')
        action = options.get('action')
        data_file_id = options.get('data_file')
        
        self.stdout.write("=" * 100)
        self.stdout.write("PHI File Audit Trail")
        self.stdout.write("=" * 100)
        
        # Build query
        query = PHIFileTracking.objects.all()
        
        # Filter by DataTableFile if specified
        if data_file_id:
            try:
                data_file = DataTableFile.objects.get(id=data_file_id)
                self.stdout.write(f"Showing trail for DataTableFile {data_file_id}:")
                self.stdout.write(f"  File: {data_file.original_filename}")
                self.stdout.write(f"  Raw path: {data_file.raw_file_path}")
                self.stdout.write(f"  DuckDB path: {data_file.duckdb_file_path}")
                self.stdout.write("")
                
                # Filter by file paths
                if data_file.raw_file_path:
                    query = query.filter(
                        file_path__in=[data_file.raw_file_path, data_file.duckdb_file_path]
                    )
            except DataTableFile.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"DataTableFile {data_file_id} not found"))
                return
        
        # Filter by file pattern
        if file_pattern and not data_file_id:
            if '*' in file_pattern:
                # Convert wildcard to regex
                pattern = file_pattern.replace('*', '.*')
                query = query.filter(file_path__regex=pattern)
            else:
                query = query.filter(file_path__icontains=file_pattern)
        
        # Filter by cohort
        if cohort_id:
            query = query.filter(cohort_id=cohort_id)
        
        # Filter by user
        if username:
            query = query.filter(user__username__icontains=username)
        
        # Filter by time period
        if days:
            cutoff = timezone.now() - timedelta(days=days)
            query = query.filter(created_at__gte=cutoff)
        
        # Filter by action
        if action:
            query = query.filter(action=action)
        
        # Order by creation time
        query = query.order_by('-created_at')
        
        # Display results
        total = query.count()
        if total == 0:
            self.stdout.write("No matching PHI file operations found.")
            return
        
        self.stdout.write(f"Found {total} operations:")
        self.stdout.write("")
        
        # Group by file path for better readability
        file_groups = {}
        for record in query[:100]:  # Limit to first 100 for readability
            if record.file_path not in file_groups:
                file_groups[record.file_path] = []
            file_groups[record.file_path].append(record)
        
        for file_path, records in file_groups.items():
            self.stdout.write(f"\nFile: {file_path}")
            self.stdout.write("-" * 95)
            
            for record in records:
                timestamp = record.created_at.strftime("%Y-%m-%d %H:%M:%S")
                user = record.user.username if record.user else "system"
                
                # Color code by action type
                if 'created' in record.action:
                    action_str = self.style.SUCCESS(f"{record.get_action_display():30}")
                elif 'deleted' in record.action:
                    action_str = self.style.WARNING(f"{record.get_action_display():30}")
                elif 'failed' in record.action:
                    action_str = self.style.ERROR(f"{record.get_action_display():30}")
                else:
                    action_str = f"{record.get_action_display():30}"
                
                # Build status indicators
                status = []
                if record.cleaned_up:
                    status.append("✓ cleaned")
                if record.error_message:
                    status.append("⚠ error")
                if record.is_cleanup_overdue:
                    status.append("⏰ overdue")
                
                status_str = " | ".join(status) if status else ""
                
                self.stdout.write(
                    f"  {timestamp} | {user:15} | {action_str} {status_str}"
                )
                
                if record.error_message:
                    self.stdout.write(
                        self.style.ERROR(f"    Error: {record.error_message[:100]}")
                    )
                
                if record.file_size:
                    size_mb = record.file_size / (1024 * 1024)
                    self.stdout.write(f"    Size: {size_mb:.2f} MB")
                
                if record.expected_cleanup_by and not record.cleaned_up:
                    self.stdout.write(
                        f"    Expected cleanup: {record.expected_cleanup_by.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
        
        if total > 100:
            self.stdout.write(f"\n... and {total - 100} more operations")
        
        # Summary statistics
        self.stdout.write("\n" + "=" * 100)
        self.stdout.write("Summary Statistics")
        self.stdout.write("=" * 100)
        
        # Count by action type
        action_counts = {}
        for record in query:
            if record.action not in action_counts:
                action_counts[record.action] = 0
            action_counts[record.action] += 1
        
        self.stdout.write("\nOperations by type:")
        for action_type, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            display = dict(PHIFileTracking.ACTION_CHOICES).get(action_type, action_type)
            self.stdout.write(f"  {display:40} {count:6}")
        
        # Cleanup status
        pending_cleanup = query.filter(
            action='work_copy_created',
            cleaned_up=False
        ).count()
        
        if pending_cleanup > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nFiles pending cleanup: {pending_cleanup}"
                )
            )