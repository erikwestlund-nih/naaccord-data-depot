import os
import shutil
import tempfile
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.conf import settings
from depot.models import CohortMembership


class Command(BaseCommand):
    help = '''Complete development environment reset - drops database, recreates with all users/roles, and cleans storage (including NAS)

    WARNING: This command DESTROYS ALL DATA! Use only for development.

    🚫 THIS COMMAND IS BLOCKED IN PRODUCTION AND STAGING ENVIRONMENTS 🚫

    This command performs:
    - Complete database reset and migrations
    - User and role seeding (creates 16 test users)
    - Storage directory cleanup (including NAS storage)
    - Test data generation
    - Environment verification
    '''

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt - use with caution!'
        )
        parser.add_argument(
            '--skip-storage-cleanup',
            action='store_true',
            help='Skip cleaning storage directories'
        )
        parser.add_argument(
            '--skip-test-data',
            action='store_true',
            help='Skip generating test simulation data'
        )

    def style_step(self, text):
        return self.style.HTTP_INFO(f"==== {text} ====")

    def style_success(self, text):
        return self.style.SUCCESS(f"✅ {text}")

    def style_warning(self, text):
        return self.style.WARNING(f"⚠️  {text}")

    def style_error(self, text):
        return self.style.ERROR(f"❌ {text}")

    def handle(self, *args, **options):
        start_time = time.time()

        # 🚫 PRODUCTION/STAGING GUARD - NEVER allow reset in production or staging
        environment = os.environ.get('NAACCORD_ENVIRONMENT', 'development').lower()
        if environment in ['production', 'staging']:
            self.stdout.write(self.style.ERROR("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   🚫 THIS COMMAND IS BLOCKED IN PRODUCTION/STAGING 🚫                        ║
║                                                                              ║
║   Environment detected: {env}
║                                                                              ║
║   Database and NAS resets are PERMANENTLY DISABLED to protect               ║
║   real research data that cannot be recreated.                               ║
║                                                                              ║
║   To add cohorts or users incrementally, use:                                ║
║     python manage.py seed_from_csv --model depot.Cohort --file ...           ║
║     python manage.py load_production_users                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""".format(env=environment.upper())))
            raise CommandError(f"reset_dev_complete is blocked in {environment} environment")

        self.stdout.write(self.style_step("Starting Complete NA-ACCORD Development Environment Reset"))
        self.stdout.write("This will:")
        self.stdout.write("  - Reset and recreate database")
        self.stdout.write("  - Seed all users, roles, and cohorts")
        self.stdout.write("  - Clean storage directories (including NAS)")
        self.stdout.write("  - Generate test data")
        self.stdout.write("")

        # Confirmation unless skipped
        if not options['skip_confirmation']:
            confirm = input("Are you sure you want to continue? This will DELETE ALL DATA! (y/N): ")
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write("Aborted.")
                return

        try:
            # Step 1: Database Reset and Migrations
            self.stdout.write(self.style_step("Step 1: Database Reset and Migrations"))
            self.stdout.write("Dropping and recreating database...")
            call_command('reset_db')
            self.stdout.write(self.style_success("Database reset completed"))

            self.stdout.write("Running migrations...")
            call_command('migrate', verbosity=0)
            self.stdout.write(self.style_success("Migrations completed"))

            # Step 2: Seed Initial Data
            self.stdout.write(self.style_step("Step 2: Seeding Initial Data"))
            self.stdout.write("Seeding basic data (cohorts, groups, data file types, protocol years)...")
            call_command('seed_init', verbosity=0)
            self.stdout.write(self.style_success("Initial data seeded"))

            self.stdout.write("Setting up permission groups...")
            call_command('setup_permission_groups', verbosity=0)
            self.stdout.write(self.style_success("Permission groups created"))

            # Step 3: User Management
            self.stdout.write(self.style_step("Step 3: User Management"))
            self.stdout.write("Loading test users from CSV files...")
            call_command('load_test_users', verbosity=0)
            self.stdout.write(self.style_success("Test users loaded"))

            self.stdout.write("Creating additional test users and assigning to groups...")
            call_command('assign_test_users_to_groups', verbosity=0)
            self.stdout.write(self.style_success("Additional test users created and assigned"))

            # Step 4: Storage Cleanup
            if not options['skip_storage_cleanup']:
                self.stdout.write(self.style_step("Step 4: Storage Cleanup"))
                self._clean_storage()

            # Step 5: Generate Test Data
            if not options['skip_test_data']:
                self.stdout.write(self.style_step("Step 5: Generating Test Data"))
                self.stdout.write("Generating simulation data for VACS cohort...")
                try:
                    call_command('generate_sim_data', '--cohort', 'VACS / VACS8', '--table', 'patient', verbosity=0)
                    self.stdout.write(self.style_success("Test data generated"))
                except Exception as e:
                    self.stdout.write(self.style_warning(f"Test data generation failed: {e}"))

            # Step 6: Final Data Cleanup (ensure everything is truly wiped except seed data)
            self.stdout.write(self.style_step("Step 6: Final Data Cleanup"))
            self._final_cleanup()

            # Step 7: Verification
            self.stdout.write(self.style_step("Step 7: Verification"))
            self._verify_setup()

            # Summary
            duration = int(time.time() - start_time)
            self.stdout.write(self.style_step("Setup Complete!"))
            self.stdout.write("")
            self.stdout.write(self.style_success(f"Total time: {duration} seconds"))
            self.stdout.write("")
            self.stdout.write("🎯 Your development environment is now ready!")
            self.stdout.write("")
            self.stdout.write("Next steps:")
            self.stdout.write("  1. Start tmux session: /Users/erikwestlund/code/projects/tmux/start_naaccord.sh")
            self.stdout.write("  2. Or start services manually:")
            self.stdout.write("     - Django web: python manage.py runserver 0.0.0.0:8000")
            self.stdout.write("     - Django services: python manage.py runserver 0.0.0.0:8001")
            self.stdout.write("     - Celery: celery -A depot worker -l info")
            self.stdout.write("     - Frontend: npm run dev")
            self.stdout.write("")
            self.stdout.write("Test accounts available:")
            self.stdout.write("  - Admin: admin@test.com")
            self.stdout.write("  - VA Admin: admin@va.gov")
            self.stdout.write("  - JH Admin: admin@jh.edu")
            self.stdout.write("  - Manager: coordinator@test.edu")
            self.stdout.write("  - Researcher: researcher@test.edu")
            self.stdout.write("  - Viewer: viewer@test.edu")

        except Exception as e:
            self.stdout.write(self.style_error(f"Setup failed: {e}"))
            raise CommandError(f"Development reset failed: {e}")

    def _clean_storage(self):
        """Clean local and NAS storage directories"""
        # Clean local storage directories
        self.stdout.write("Cleaning local storage directories...")
        storage_path = Path(settings.BASE_DIR) / "storage"

        if storage_path.exists():
            # Remove all contents but PRESERVE directory structure
            for item in storage_path.iterdir():
                if item.is_dir():
                    # Delete contents of subdirectory but keep the directory itself
                    for subitem in item.iterdir():
                        if subitem.is_dir():
                            shutil.rmtree(subitem)
                        else:
                            subitem.unlink()
                else:
                    item.unlink()
            self.stdout.write(self.style_success("Local storage cleaned (directories preserved)"))
        else:
            self.stdout.write(self.style_warning("Storage directory not found, skipping"))

        # Clean NAS storage (check if mounted and accessible)
        self.stdout.write("Checking NAS storage...")
        nas_mount_path = Path(getattr(settings, 'NAS_MOUNT_PATH', '/mnt/nas/submissions'))

        if nas_mount_path.exists():
            self.stdout.write(f"Found NAS storage at {nas_mount_path}")

            # Check if we have write access
            try:
                # Test write access by creating a temporary file
                test_file = nas_mount_path / f'.write_test_{os.getpid()}'
                test_file.touch()
                test_file.unlink()

                # Clean NAS storage - delete contents but preserve directory structure
                for item in nas_mount_path.iterdir():
                    if item.is_dir():
                        # Delete contents of subdirectory but keep the directory itself
                        for subitem in item.iterdir():
                            if subitem.is_dir():
                                shutil.rmtree(subitem)
                            else:
                                subitem.unlink()
                    else:
                        item.unlink()
                self.stdout.write(self.style_success("NAS storage cleaned (directories preserved)"))

            except PermissionError:
                self.stdout.write(self.style_warning("No write access to NAS storage - run with sudo if needed"))
            except Exception as e:
                self.stdout.write(self.style_warning(f"Could not clean NAS storage: {e}"))
        else:
            self.stdout.write(self.style_warning(f"NAS storage not found at {nas_mount_path} (not mounted or different path)"))

        # Clean temporary directories
        self.stdout.write("Cleaning temporary directories...")
        temp_dir = Path(tempfile.gettempdir())

        # Clean naaccord-specific temp files
        for pattern in ['naaccord_*', 'django_*']:
            for temp_file in temp_dir.glob(pattern):
                try:
                    if temp_file.is_dir():
                        shutil.rmtree(temp_file)
                    else:
                        temp_file.unlink()
                except Exception:
                    pass  # Ignore errors for temp cleanup

        self.stdout.write(self.style_success("Temporary directories cleaned"))

    def _final_cleanup(self):
        """Final cleanup to ensure all user-generated data is removed, keeping only seed data"""
        self.stdout.write("Performing final cleanup of user-generated data...")

        # Delete all user-generated submission data but keep seed data
        # IMPORTANT: Order matters due to foreign key constraints
        tables_to_clean = [
            'CohortSubmission',
            'CohortSubmissionDataTable',
            'DataTableFile',
            'DataTableReview',
            'PHIFileTracking',
            'SubmissionActivity',
            'FileAttachment',
            'PrecheckRun',
            'SubmissionPatientIDs',
            'DataTableFilePatientIDs',
            'DataRevision',  # Must be before Activity due to protected FK
            'Activity',
        ]

        from depot.models import (
            CohortSubmission, CohortSubmissionDataTable,
            DataTableFile, DataTableReview, PHIFileTracking,
            SubmissionActivity, Activity, DataRevision, FileAttachment,
            PrecheckRun, SubmissionPatientIDs, DataTableFilePatientIDs
        )

        cleanup_count = 0
        model_map = {
            'CohortSubmission': CohortSubmission,
            'CohortSubmissionDataTable': CohortSubmissionDataTable,
            'DataTableFile': DataTableFile,
            'DataTableReview': DataTableReview,
            'PHIFileTracking': PHIFileTracking,
            'SubmissionActivity': SubmissionActivity,
            'Activity': Activity,
            'DataRevision': DataRevision,
            'FileAttachment': FileAttachment,
            'PrecheckRun': PrecheckRun,
            'SubmissionPatientIDs': SubmissionPatientIDs,
            'DataTableFilePatientIDs': DataTableFilePatientIDs,
        }

        for table_name in tables_to_clean:
            model = model_map.get(table_name)
            if model:
                count = model.objects.count()
                if count > 0:
                    model.objects.all().delete()
                    cleanup_count += count
                    self.stdout.write(f"  Cleaned {count} {table_name} records")

        if cleanup_count > 0:
            self.stdout.write(self.style_success(f"Final cleanup: removed {cleanup_count} user-generated records"))
        else:
            self.stdout.write(self.style_success("Final cleanup: no user-generated data to remove"))

    def _verify_setup(self):
        """Verify the setup completed correctly"""
        self.stdout.write("Verifying setup...")

        # Check user count
        User = get_user_model()
        user_count = User.objects.count()
        if user_count >= 15:
            self.stdout.write(self.style_success(f"User count: {user_count} users created"))
        else:
            self.stdout.write(self.style_warning(f"User count: {user_count} users (expected 15+)"))

        # Check cohort memberships
        membership_count = CohortMembership.objects.count()
        if membership_count > 0:
            self.stdout.write(self.style_success(f"Cohort memberships: {membership_count} memberships created"))
        else:
            self.stdout.write(self.style_error("Cohort memberships: No memberships found - users won't see cohorts!"))

        # Check storage cleanup
        storage_path = Path(settings.BASE_DIR) / "storage"
        if storage_path.exists():
            file_count = sum(1 for _ in storage_path.rglob('*') if _.is_file())
            if file_count == 0:
                self.stdout.write(self.style_success("Storage cleanup: Clean (0 files)"))
            else:
                self.stdout.write(self.style_warning(f"Storage cleanup: {file_count} files remaining"))