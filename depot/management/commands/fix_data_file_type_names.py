from django.core.management.base import BaseCommand
from depot.models import DataFileType


class Command(BaseCommand):
    help = 'Fix data file type names from snake_case to camelCase to match table_config.py'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Mapping of old names to new names
        name_fixes = {
            'substance_survey': 'substanceSurvey',
            'discharge_dx': 'dischargeDx',
            'risk_factor': 'riskFactor',
            'geography': 'geographic',
        }

        self.stdout.write(self.style.WARNING(
            f"{'DRY RUN - ' if dry_run else ''}Fixing data file type names..."
        ))

        updated_count = 0
        not_found = []

        for old_name, new_name in name_fixes.items():
            try:
                file_type = DataFileType.objects.get(name=old_name)

                self.stdout.write(
                    f"  {old_name} -> {new_name} (ID: {file_type.id})"
                )

                if not dry_run:
                    file_type.name = new_name
                    file_type.save()

                updated_count += 1

            except DataFileType.DoesNotExist:
                not_found.append(old_name)
                self.stdout.write(
                    self.style.WARNING(f"  {old_name} not found (may already be fixed)")
                )

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nDRY RUN: Would update {updated_count} data file types"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nSuccessfully updated {updated_count} data file types"
            ))

        if not_found:
            self.stdout.write(self.style.WARNING(
                f"\nNot found: {', '.join(not_found)}"
            ))
