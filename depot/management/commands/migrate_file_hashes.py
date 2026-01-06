"""
Django management command to migrate existing files with pending hashes.

This command identifies files with "pending_calculation" or "pending_async_calculation"
hashes and triggers background hash calculation to ensure HIPAA compliance.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from depot.models import UploadedFile, DataTableFile
from depot.tasks.file_integrity import calculate_file_hash_task, migrate_pending_hashes
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate existing files with pending hash calculations for HIPAA compliance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of files to process in each batch (default: 50)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without making changes'
        )
        parser.add_argument(
            '--model',
            choices=['uploadedfile', 'datatablefile', 'both'],
            default='both',
            help='Which model to migrate (default: both)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        model_choice = options['model']
        force = options['force']

        # Count files needing migration
        uploadedfile_count = UploadedFile.objects.filter(
            file_hash__in=['pending_calculation', 'pending_async_calculation']
        ).count()

        datatablefile_count = DataTableFile.objects.filter(
            file_hash__in=['pending_calculation', 'pending_async_calculation']
        ).count()

        total_count = 0
        if model_choice in ['uploadedfile', 'both']:
            total_count += uploadedfile_count
        if model_choice in ['datatablefile', 'both']:
            total_count += datatablefile_count

        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    'No files found with pending hash calculations. All files are up to date.'
                )
            )
            return

        self.stdout.write(f'Found files needing hash migration:')
        if model_choice in ['uploadedfile', 'both']:
            self.stdout.write(f'  - UploadedFile: {uploadedfile_count} files')
        if model_choice in ['datatablefile', 'both']:
            self.stdout.write(f'  - DataTableFile: {datatablefile_count} files')
        self.stdout.write(f'  - Total: {total_count} files')
        self.stdout.write(f'  - Batch size: {batch_size}')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('[DRY RUN] Would queue hash calculation tasks for these files')
            )
            return

        if not force:
            confirm = input(
                '\nThis will queue background hash calculation tasks for all pending files.\n'
                'Continue? [y/N]: '
            )
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write('Migration cancelled.')
                return

        # Perform migration using the existing Celery task
        self.stdout.write('Starting hash migration...')

        try:
            if model_choice == 'uploadedfile':
                result = self._migrate_uploaded_files(batch_size)
            elif model_choice == 'datatablefile':
                result = self._migrate_data_table_files(batch_size)
            else:  # both
                result = migrate_pending_hashes.delay(batch_size)
                # Wait for result if running synchronously
                if hasattr(result, 'get'):
                    result = result.get(timeout=300)  # 5 minute timeout
                else:
                    result = {
                        'uploaded_files_processed': 0,
                        'data_table_files_processed': 0,
                        'successful_calculations': 0,
                        'failed_calculations': 0,
                        'errors': []
                    }

            self.stdout.write(
                self.style.SUCCESS(
                    f'Migration completed:\n'
                    f'  - UploadedFile records processed: {result["uploaded_files_processed"]}\n'
                    f'  - DataTableFile records processed: {result["data_table_files_processed"]}\n'
                    f'  - Failed calculations: {result["failed_calculations"]}\n'
                    f'  - Errors: {len(result["errors"])}'
                )
            )

            if result['errors']:
                self.stdout.write(self.style.WARNING('Errors encountered:'))
                for error in result['errors']:
                    self.stdout.write(f'  - {error}')

        except Exception as e:
            raise CommandError(f'Migration failed: {str(e)}')

    def _migrate_uploaded_files(self, batch_size):
        """Migrate only UploadedFile records"""
        pending_files = UploadedFile.objects.filter(
            file_hash__in=['pending_calculation', 'pending_async_calculation']
        )[:batch_size]

        processed = 0
        failed = 0
        errors = []

        for file_record in pending_files:
            try:
                calculate_file_hash_task.delay('UploadedFile', file_record.id)
                processed += 1
                self.stdout.write(f'Queued hash calculation for UploadedFile {file_record.id}')
            except Exception as e:
                failed += 1
                error_msg = f'UploadedFile {file_record.id}: {str(e)}'
                errors.append(error_msg)
                logger.error(error_msg)

        return {
            'uploaded_files_processed': processed,
            'data_table_files_processed': 0,
            'successful_calculations': processed,
            'failed_calculations': failed,
            'errors': errors
        }

    def _migrate_data_table_files(self, batch_size):
        """Migrate only DataTableFile records"""
        pending_files = DataTableFile.objects.filter(
            file_hash__in=['pending_calculation', 'pending_async_calculation']
        )[:batch_size]

        processed = 0
        failed = 0
        errors = []

        for file_record in pending_files:
            try:
                calculate_file_hash_task.delay('DataTableFile', file_record.id)
                processed += 1
                self.stdout.write(f'Queued hash calculation for DataTableFile {file_record.id}')
            except Exception as e:
                failed += 1
                error_msg = f'DataTableFile {file_record.id}: {str(e)}'
                errors.append(error_msg)
                logger.error(error_msg)

        return {
            'uploaded_files_processed': 0,
            'data_table_files_processed': processed,
            'successful_calculations': processed,
            'failed_calculations': failed,
            'errors': errors
        }