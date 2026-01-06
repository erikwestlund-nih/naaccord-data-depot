import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connection

class Command(BaseCommand):
    help = """Drop and recreate the database only. Does not run migrations or seed data.

    🚫 THIS COMMAND IS BLOCKED IN PRODUCTION AND STAGING ENVIRONMENTS 🚫
    """

    def handle(self, *args, **options):
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
║   Database resets are PERMANENTLY DISABLED to protect real research data.   ║
║                                                                              ║
║   To add cohorts or users incrementally, use:                                ║
║     python manage.py seed_from_csv --model depot.Cohort --file ...           ║
║     python manage.py load_production_users                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""".format(env=environment.upper())))
            raise CommandError(f"reset_db is blocked in {environment} environment")

        # Get database name from settings
        db_settings = settings.DATABASES["default"]
        db_name = db_settings.get("NAME", "naaccord")

        # For development/testing only - use Django's built-in database management
        self.stdout.write(self.style.WARNING(f"Resetting database '{db_name}'..."))

        try:
            # Use Django's flush command to clear data
            # This is safer than dropping the entire database
            self.stdout.write("Flushing all data from database...")
            call_command('flush', '--no-input', verbosity=0)

            self.stdout.write(
                self.style.SUCCESS(f"Database '{db_name}' reset successfully.")
            )
            self.stdout.write(
                self.style.WARNING("Note: Run 'python manage.py migrate' to recreate schema if needed.")
            )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
            raise CommandError(f"Failed to reset database: {e}") 