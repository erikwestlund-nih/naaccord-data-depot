from django.core.management.base import BaseCommand
from depot.models import DataFileType


class Command(BaseCommand):
    help = 'Set the correct order for DataFileTypes'
    
    def handle(self, *args, **options):
        self.stdout.write('Setting DataFileType order...')
        
        # Define the correct order based on requirements
        file_type_order = [
            ('patient', 1),
            ('diagnosis', 2),
            ('laboratory', 3),
            ('medication', 4),
            ('mortality', 5),  # Cause of death/mortality
            ('cause_of_death', 5),  # Alternative name
            ('geography', 6),  # Geographic data
            ('geographic', 6),  # Alternative name
            ('encounter', 7),
            ('insurance', 8),
            ('hospitalization', 9),  # Hospitalizations
            ('hospitalizations', 9),  # Alternative name
            ('substance_survey', 10),  # Substance use
            ('substance_use', 10),  # Alternative name
            ('substance', 10),  # Alternative name
            ('procedure', 11),  # Procedures
            ('procedures', 11),  # Alternative name
            ('discharge_dx', 12),  # Discharge diagnosis
            ('discharge_diagnosis', 12),  # Alternative name
            ('discharge', 12),  # Alternative name
            ('risk_factor', 13),  # Risk factor
            ('risk', 13),  # Alternative name
            ('census', 14),
        ]
        
        updated_count = 0
        for name, order in file_type_order:
            # Try to find by name (case-insensitive)
            file_types = DataFileType.objects.filter(name__iexact=name)
            for file_type in file_types:
                file_type.order = order
                file_type.save()
                self.stdout.write(f'  Set {file_type.name} to order {order}')
                updated_count += 1
        
        # List any file types that didn't get an order assigned
        unordered = DataFileType.objects.filter(order=0)
        if unordered.exists():
            self.stdout.write(self.style.WARNING('\nFile types without order:'))
            for ft in unordered:
                self.stdout.write(f'  - {ft.name} ({ft.label})')
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated_count} file types'))