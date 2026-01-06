from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from depot.models import PHIFileTracking, DataTableFile, CohortSubmission
from depot.storage.manager import StorageManager
from pathlib import Path
import hashlib
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verify integrity of PHI files on NAS and their tracking records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cohort',
            type=int,
            help='Limit verification to a specific cohort ID',
        )
        parser.add_argument(
            '--submission',
            type=int,
            help='Limit verification to a specific submission ID',
        )
        parser.add_argument(
            '--check-hashes',
            action='store_true',
            help='Verify file hashes (slower but more thorough)',
        )

    def handle(self, *args, **options):
        cohort_id = options.get('cohort')
        submission_id = options.get('submission')
        check_hashes = options.get('check_hashes')
        
        self.stdout.write("=" * 70)
        self.stdout.write("PHI File Integrity Verification")
        self.stdout.write("=" * 70)
        
        storage = StorageManager.get_submission_storage()
        
        # Build query filters
        tracking_filter = Q()
        if cohort_id:
            tracking_filter &= Q(cohort_id=cohort_id)
            self.stdout.write(f"Filtering by cohort ID: {cohort_id}")
        if submission_id:
            submission = CohortSubmission.objects.get(id=submission_id)
            tracking_filter &= Q(cohort_id=submission.cohort_id)
            self.stdout.write(f"Filtering by submission ID: {submission_id}")
        
        # Check NAS files
        self.stdout.write("\nChecking NAS files...")
        nas_records = PHIFileTracking.objects.filter(
            tracking_filter,
            action__in=['nas_raw_created', 'nas_duckdb_created']
        )
        
        missing_files = []
        corrupt_files = []
        valid_files = 0
        
        for record in nas_records:
            try:
                # Check if file exists
                if not storage.exists(record.file_path):
                    missing_files.append(record)
                    continue
                
                # Optionally check hash
                if check_hashes and record.file_hash:
                    content = storage.get_file(record.file_path)
                    if isinstance(content, str):
                        content = content.encode()
                    calculated_hash = hashlib.sha256(content).hexdigest()
                    if calculated_hash != record.file_hash:
                        corrupt_files.append((record, calculated_hash))
                        continue
                
                valid_files += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error checking {record.file_path}: {e}")
                )
        
        # Report NAS file status
        self.stdout.write(f"\nNAS File Status:")
        self.stdout.write(f"  Valid files: {valid_files}")
        if missing_files:
            self.stdout.write(self.style.ERROR(f"  Missing files: {len(missing_files)}"))
            for record in missing_files[:10]:  # Show first 10
                self.stdout.write(f"    - {record.file_path}")
        if corrupt_files:
            self.stdout.write(self.style.ERROR(f"  Corrupt files: {len(corrupt_files)}"))
            for record, new_hash in corrupt_files[:10]:  # Show first 10
                self.stdout.write(
                    f"    - {record.file_path} (expected: {record.file_hash[:8]}..., "
                    f"got: {new_hash[:8]}...)"
                )
        
        # Check DataTableFile consistency
        self.stdout.write("\nChecking DataTableFile consistency...")
        
        # Build DataTableFile query
        dtf_filter = Q()
        if submission_id:
            dtf_filter &= Q(data_table__submission_id=submission_id)
        elif cohort_id:
            dtf_filter &= Q(data_table__submission__cohort_id=cohort_id)
        
        data_files = DataTableFile.objects.filter(dtf_filter).exclude(
            Q(raw_file_path='') | Q(raw_file_path__isnull=True)
        )
        
        files_without_tracking = []
        files_without_duckdb = []
        files_with_issues = []
        
        for data_file in data_files:
            # Check if raw file has tracking record
            if not PHIFileTracking.objects.filter(
                file_path=data_file.raw_file_path,
                action='nas_raw_created'
            ).exists():
                files_without_tracking.append(data_file)
            
            # Check if DuckDB exists when it should
            if data_file.duckdb_file_path:
                if not storage.exists(data_file.duckdb_file_path):
                    files_with_issues.append((data_file, "DuckDB file missing"))
            else:
                files_without_duckdb.append(data_file)
        
        # Report DataTableFile status
        self.stdout.write(f"\nDataTableFile Status:")
        self.stdout.write(f"  Total files with paths: {data_files.count()}")
        if files_without_tracking:
            self.stdout.write(
                self.style.WARNING(
                    f"  Files without tracking records: {len(files_without_tracking)}"
                )
            )
        if files_without_duckdb:
            self.stdout.write(
                self.style.WARNING(
                    f"  Files without DuckDB conversion: {len(files_without_duckdb)}"
                )
            )
        if files_with_issues:
            self.stdout.write(
                self.style.ERROR(
                    f"  Files with issues: {len(files_with_issues)}"
                )
            )
            for data_file, issue in files_with_issues[:10]:
                self.stdout.write(f"    - File {data_file.id}: {issue}")
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("Summary")
        self.stdout.write("=" * 70)
        
        total_issues = len(missing_files) + len(corrupt_files) + len(files_with_issues)
        if total_issues == 0:
            self.stdout.write(
                self.style.SUCCESS("All PHI files verified successfully!")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Found {total_issues} total issues requiring attention")
            )
            self.stdout.write("\nRecommendations:")
            if missing_files:
                self.stdout.write("  - Investigate missing NAS files")
            if corrupt_files:
                self.stdout.write("  - Re-upload corrupt files")
            if files_without_tracking:
                self.stdout.write("  - Create tracking records for untracked files")
            if files_without_duckdb:
                self.stdout.write("  - Convert files to DuckDB format")