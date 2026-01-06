import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command


class Command(BaseCommand):
    help = "Seed multiple models with data from CSV files"

    def get_environment_file(self, base_file):
        """
        Get environment-specific CSV file if it exists, otherwise return base file.

        Checks for files in this order:
        1. {base_name}.{environment}.csv (e.g., cohorts.production.csv)
        2. {base_name}.csv (e.g., cohorts.csv)

        Environment is determined by NAACCORD_ENVIRONMENT env var (default: development)
        """
        environment = os.environ.get('NAACCORD_ENVIRONMENT', 'development')

        # Parse base file path
        file_path = Path(base_file)
        base_name = file_path.stem  # e.g., "cohorts"
        extension = file_path.suffix  # e.g., ".csv"
        directory = file_path.parent  # e.g., "resources/data/seed"

        # Check for environment-specific file first
        env_file = directory / f"{base_name}.{environment}{extension}"
        if env_file.exists():
            self.stdout.write(
                self.style.WARNING(f"Using environment-specific file: {env_file}")
            )
            return str(env_file)

        # Fall back to base file
        if file_path.exists():
            self.stdout.write(
                self.style.WARNING(f"Using base file (no {environment}-specific file found): {base_file}")
            )
            return base_file

        # File not found
        raise FileNotFoundError(f"Neither {env_file} nor {base_file} exists")

    def handle(self, *args, **kwargs):
        environment = os.environ.get('NAACCORD_ENVIRONMENT', 'staging')

        seeds = [
            {
                "model": "auth.group",
                "file": "resources/data/seed/groups.csv",
            },
            {
                "model": "depot.Cohort",
                "file": "resources/data/seed/cohorts.csv",
                # Cohorts are same in all environments (31 NA-ACCORD cohorts)
            },
            {
                "model": "depot.DataFileType",
                "file": "resources/data/seed/data_file_types.csv",
            },
            {
                "model": "depot.ProtocolYear",
                "file": "resources/data/seed/protocol_years.csv",
            },
        ]

        for seed in seeds:
            model = seed["model"]
            base_file = seed["file"]

            # Get environment-specific file if enabled
            try:
                if seed.get("use_environment", False):
                    file_path = self.get_environment_file(base_file)
                else:
                    file_path = base_file
            except FileNotFoundError as e:
                self.stderr.write(self.style.ERROR(f"Error: {e}"))
                continue

            self.stdout.write(f"Seeding data for {model} from {file_path}...")

            try:
                call_command("seed_from_csv", model=model, file=file_path)
            except CommandError as e:
                self.stderr.write(f"Error seeding {model} from {file_path}: {e}")
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully seeded {model} from {file_path}")
                )
