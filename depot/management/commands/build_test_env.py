from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Rebuild the test environment from scratch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="admin",
            help="Username for superuser (default: admin)",
        )
        parser.add_argument(
            "--email",
            type=str,
            default="admin@test.com",
            help="Email for superuser (default: admin@test.com)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        User = get_user_model()

        # Reset database using reset_db command
        self.stdout.write(self.style.WARNING("Resetting database..."))
        call_command("reset_db")

        # Run migrations before seeding or user logic
        self.stdout.write(self.style.WARNING("Running migrations..."))
        call_command("migrate")

        # Explicitly seed the four CSV files
        self.stdout.write(self.style.WARNING("Seeding groups from CSV..."))
        call_command("seed_from_csv", model="auth.group", file="resources/data/seed/groups.csv")
        self.stdout.write(self.style.WARNING("Seeding cohorts from CSV..."))
        call_command("seed_from_csv", model="depot.Cohort", file="resources/data/seed/cohorts.csv")
        self.stdout.write(self.style.WARNING("Seeding data file types from CSV..."))
        call_command("seed_from_csv", model="depot.DataFileType", file="resources/data/seed/data_file_types.csv")
        self.stdout.write(self.style.WARNING("Seeding protocol years from CSV..."))
        call_command("seed_from_csv", model="depot.ProtocolYear", file="resources/data/seed/protocol_years.csv")

        # Create superuser if it doesn't exist
        if not User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"Creating superuser '{username}'..."))
            call_command(
                "createsuperuser",
                username=username,
                email=email,
                interactive=False,
            )
        else:
            self.stdout.write(
                self.style.NOTICE(f"Superuser '{username}' already exists.")
            )

        # Seed admin cohort
        self.stdout.write(self.style.WARNING("Seeding admin cohort..."))
        call_command("seed_admin")

        self.stdout.write(self.style.SUCCESS("Test environment successfully built."))
