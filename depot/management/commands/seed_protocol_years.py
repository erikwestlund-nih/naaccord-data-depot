"""
Management command to seed protocol years.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from depot.models import ProtocolYear
from datetime import date


class Command(BaseCommand):
    help = 'Seeds protocol years including current and next year'

    def add_arguments(self, parser):
        parser.add_argument(
            '--years',
            nargs='+',
            type=int,
            help='Specific years to add (e.g., --years 2024 2025 2026)'
        )
        parser.add_argument(
            '--from-year',
            type=int,
            default=2020,
            help='Starting year (default: 2020)'
        )
        parser.add_argument(
            '--to-year',
            type=int,
            help='Ending year (default: next year)'
        )

    def handle(self, *args, **options):
        current_year = timezone.now().year
        
        if options['years']:
            # Specific years provided
            years_to_create = options['years']
        else:
            # Range of years
            from_year = options['from_year']
            to_year = options['to_year'] or (current_year + 1)
            years_to_create = range(from_year, to_year + 1)
        
        created_count = 0
        updated_count = 0
        
        for year in years_to_create:
            # Determine if this year should be active
            # 2024 and 2025 are active for the current development cycle
            is_active = year in [2024, 2025]
            
            protocol_year, created = ProtocolYear.objects.update_or_create(
                year=year,
                defaults={
                    'name': str(year),
                    'description': f'Protocol Year {year}',
                    'is_active': is_active,
                    'start_date': date(year, 1, 1),
                    'end_date': date(year, 12, 31),
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created protocol year {year} (active: {is_active})')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated protocol year {year} (active: {is_active})')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: Created {created_count} new protocol years, updated {updated_count} existing ones.'
            )
        )
        
        # Show current status
        self.stdout.write('\nCurrent protocol years:')
        for py in ProtocolYear.objects.all().order_by('year'):
            status = self.style.SUCCESS('ACTIVE') if py.is_active else self.style.WARNING('inactive')
            self.stdout.write(f'  {py.year}: {status}')