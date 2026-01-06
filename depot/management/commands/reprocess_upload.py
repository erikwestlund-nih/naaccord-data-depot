from django.core.management.base import BaseCommand
from depot.models import DataTableFile
from depot.tasks.duckdb_creation import create_duckdb_task


class Command(BaseCommand):
    help = 'Reprocess a failed upload by re-triggering DuckDB conversion'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_id',
            type=int,
            help='DataTableFile ID to reprocess'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Reprocess even if DuckDB already exists'
        )

    def handle(self, *args, **options):
        file_id = options['file_id']
        force = options['force']

        try:
            data_file = DataTableFile.objects.select_related(
                'data_table__submission__cohort',
                'data_table__data_file_type',
                'uploaded_by'
            ).get(id=file_id)
        except DataTableFile.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'DataTableFile {file_id} not found'))
            return

        self.stdout.write(f'Found DataTableFile {file_id}:')
        self.stdout.write(f'  Name: {data_file.name or "(unnamed)"}')
        self.stdout.write(f'  Cohort: {data_file.data_table.submission.cohort.name}')
        self.stdout.write(f'  File Type: {data_file.data_table.data_file_type.name}')
        self.stdout.write(f'  Version: {data_file.version}')
        self.stdout.write(f'  Raw Path: {data_file.raw_file_path}')
        self.stdout.write(f'  DuckDB Path: {data_file.duckdb_file_path or "(not created)"}')
        self.stdout.write(f'  Conversion Error: {data_file.duckdb_conversion_error or "(none)"}')

        # Check if already processed
        if data_file.duckdb_file_path and not force:
            self.stdout.write(self.style.WARNING(
                'DuckDB file already exists. Use --force to reprocess anyway.'
            ))
            return

        # Clear previous errors and paths
        data_file.duckdb_file_path = ''
        data_file.processed_file_path = ''
        data_file.duckdb_conversion_error = ''
        data_file.duckdb_created_at = None
        data_file.save()

        self.stdout.write(self.style.SUCCESS('Cleared previous DuckDB state'))

        # Trigger reprocessing
        task_data = {
            'data_file_id': data_file.id,
            'user_id': data_file.uploaded_by.id,
            'submission_id': data_file.data_table.submission.id,
            'cohort_id': data_file.data_table.submission.cohort.id,
            'file_type_name': data_file.data_table.data_file_type.name,
            'raw_file_path': data_file.raw_file_path,
        }

        self.stdout.write('Dispatching Celery task...')
        result = create_duckdb_task.apply_async(args=[task_data], queue='default')

        self.stdout.write(self.style.SUCCESS(
            f'Task dispatched: {result.id}\n'
            f'Monitor with: sudo docker logs naaccord-celery -f'
        ))
