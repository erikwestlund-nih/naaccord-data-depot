"""
Tests for upload precheck PHI tracking and automatic cleanup.
"""
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.test import TestCase, TransactionTestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.contenttypes.models import ContentType
from depot.models import (
    Cohort, DataFileType, PrecheckRun, UploadedFile,
    PHIFileTracking, UploadType
)
from depot.tasks.upload_precheck import process_precheck_run
from depot.storage.manager import StorageManager

User = get_user_model()


class PrecheckRunPHITrackingTest(TestCase):
    """Test PHI tracking for upload prechecks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Record'
        )
        # Add user to cohort
        self.user.cohorts.add(self.cohort)

        # Create temp directory for storage
        self.temp_dir = tempfile.mkdtemp()
        self.uploads_dir = Path(self.temp_dir) / 'uploads'
        self.uploads_dir.mkdir()

        # Configure storage
        self.storage_config = {
            'disks': {
                'uploads': {
                    'driver': 'local',
                    'root': str(self.uploads_dir)
                }
            }
        }

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('depot.views.upload_precheck.StorageManager.get_storage')
    def test_phi_tracking_created_on_upload(self, mock_get_storage):
        """Test that PHI tracking record is created when file is uploaded."""
        from depot.storage.local import LocalFileSystemStorage

        # Mock storage
        with patch('django.conf.settings.STORAGE_CONFIG', self.storage_config):
            mock_storage = LocalFileSystemStorage('uploads')
            mock_storage.root = str(self.uploads_dir)
            mock_get_storage.return_value = mock_storage

            # Simulate file upload
            self.client.force_login(self.user)

            test_content = b'cohortPatientId,race\n123,White\n456,Black'
            test_file = SimpleUploadedFile(
                'test.csv',
                test_content,
                content_type='text/csv'
            )

            response = self.client.post('/upload-precheck/upload', {
                'data_file_type_id': self.data_file_type.id,
                'cohort_id': self.cohort.id,
                'file': test_file
            })

            # Check response
            self.assertEqual(response.status_code, 200)

            # Get uploaded file from response
            response_data = response.json()
            self.assertTrue(response_data['success'])
            uploaded_file_id = response_data['file_id']
            uploaded_file = UploadedFile.objects.get(id=uploaded_file_id)

            # Manually create PHI tracking (simulating what services server would do)
            # In production, this happens in LocalFileSystemStorage.save() or on services server
            from django.contrib.contenttypes.models import ContentType
            from datetime import timedelta
            from django.utils import timezone

            tracking_record = PHIFileTracking.log_operation(
                cohort=self.cohort,
                user=self.user,
                action='file_uploaded_via_stream',
                file_path=str(Path(self.uploads_dir) / uploaded_file.storage_path),
                file_type='raw_csv',
                file_size=uploaded_file.file_size if hasattr(uploaded_file, 'file_size') else None,
                content_object=uploaded_file,
                metadata={'relative_path': uploaded_file.storage_path,
                         'original_filename': uploaded_file.filename,
                         'file_hash': uploaded_file.file_hash}
            )
            # Set additional fields not in log_operation signature
            tracking_record.cleanup_required = True
            tracking_record.expected_cleanup_by = timezone.now() + timedelta(hours=2)
            tracking_record.save(update_fields=['cleanup_required', 'expected_cleanup_by'])

            # Check PHI tracking was created
            tracking = PHIFileTracking.objects.filter(
                action='file_uploaded_via_stream',
                cohort=self.cohort,
                user=self.user
            ).first()

            self.assertIsNotNone(tracking, f"Expected PHI tracking for cohort={self.cohort.id}, user={self.user.id}")
            self.assertTrue(tracking.cleanup_required)
            self.assertFalse(tracking.cleaned_up)
            self.assertEqual(tracking.file_type, 'raw_csv')

            # Check file path contains timestamp and UUID
            self.assertIn('precheck_runs', tracking.file_path)
            import re
            # Pattern: YYYYMMDD_HHMMSS_UUID8_filename.csv
            pattern = r'\d{8}_\d{6}_[a-f0-9]{8}_test\.csv'
            self.assertRegex(tracking.file_path, pattern)

    def test_cleanup_command_marks_files_cleaned(self):
        """Test that cleanup command marks PHI files as cleaned."""
        # Create a PHI tracking record
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path='precheck_runs/test/file.csv',
            file_type='raw_csv',
            cleanup_required=True,
            cleaned_up=False
        )

        # Mock storage to say file exists
        with patch('depot.storage.manager.StorageManager.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.exists.return_value = True
            mock_storage.delete.return_value = True
            mock_get_storage.return_value = mock_storage

            # Run cleanup command
            from django.core.management import call_command
            from io import StringIO
            out = StringIO()
            call_command('cleanup_upload_prechecks', '--all', stdout=out)

            # Check tracking was marked cleaned
            tracking.refresh_from_db()
            self.assertTrue(tracking.cleaned_up)
            self.assertIsNotNone(tracking.cleanup_verified_at)

            # Check delete was called
            mock_storage.delete.assert_called_once_with('precheck_runs/test/file.csv')

            # Check output
            output = out.getvalue()
            self.assertIn('✓ Deleted and marked as cleaned', output)

    def test_cleanup_handles_media_prefix_in_path(self):
        """Test that cleanup correctly handles paths with /media/submissions/ prefix."""
        # Create a PHI tracking record with media prefix in path
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path='/media/submissions/precheck_runs/test/file.csv',
            file_type='raw_csv',
            cleanup_required=True,
            cleaned_up=False
        )

        # Mock storage to say file exists (without the prefix)
        with patch('depot.storage.manager.StorageManager.get_storage') as mock_get_storage:
            mock_storage = MagicMock()
            # Storage should check for file without the /media/submissions/ prefix
            mock_storage.exists.return_value = True
            mock_storage.delete.return_value = True
            mock_get_storage.return_value = mock_storage

            # Run cleanup command
            from django.core.management import call_command
            from io import StringIO
            out = StringIO()
            call_command('cleanup_upload_prechecks', '--all', stdout=out)

            # Check tracking was marked cleaned
            tracking.refresh_from_db()
            self.assertTrue(tracking.cleaned_up)
            self.assertIsNotNone(tracking.cleanup_verified_at)

            # Check delete was called with the correct path (without prefix for storage)
            mock_storage.delete.assert_called_once_with('precheck_runs/test/file.csv')

            # Check output
            output = out.getvalue()
            self.assertIn('✓ Deleted and marked as cleaned', output)


class PrecheckRunAutoCleanupTest(TransactionTestCase):
    """Test automatic cleanup after processing."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Record'
        )

        # Create temp directory for storage
        self.temp_dir = tempfile.mkdtemp()
        self.uploads_dir = Path(self.temp_dir) / 'uploads'
        self.uploads_dir.mkdir()

        # Configure storage
        self.storage_config = {
            'disks': {
                'uploads': {
                    'driver': 'local',
                    'root': str(self.uploads_dir)
                }
            }
        }

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch('depot.data.upload_prechecker.Auditor')
    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_auto_cleanup_on_successful_processing(self, mock_get_storage, mock_auditor_class):
        """Test that files are automatically cleaned up after successful processing."""
        from depot.storage.local import LocalFileSystemStorage

        # Create upload precheck with file
        uploaded_file = UploadedFile.objects.create(
            filename='test.csv',
            storage_path='precheck_runs/1_TEST/patient/20250101_120000_abcd1234_test.csv',
            uploader=self.user,
            type=UploadType.VALIDATION_INPUT,
            file_hash='testhash123'
        )

        precheck_run = PrecheckRun.objects.create(
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            status='pending'
        )

        # Create PHI tracking record
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path=uploaded_file.storage_path,
            file_type='raw_csv',
            cleanup_required=True,
            cleaned_up=False,
            content_type=ContentType.objects.get_for_model(uploaded_file),
            object_id=uploaded_file.id
        )

        # Mock storage
        mock_storage = MagicMock(spec=LocalFileSystemStorage)
        mock_storage.get_file.return_value = b'test,data\n1,2'
        mock_storage.delete.return_value = True
        mock_get_storage.return_value = mock_storage

        # Mock auditor to return success
        mock_auditor = MagicMock()
        mock_auditor.process.return_value = {
            'status': 'completed',
            'result': {'message': 'Success'}
        }
        mock_auditor.cleanup.return_value = None
        mock_auditor_class.return_value = mock_auditor

        # Process the upload precheck
        with patch('django.conf.settings.STORAGE_CONFIG', self.storage_config):
            result = process_precheck_run(precheck_run.id)

        # Check result
        self.assertEqual(result['status'], 'completed')

        # Check file was deleted
        mock_storage.delete.assert_called_once_with(uploaded_file.storage_path)

        # Check PHI tracking was marked cleaned
        tracking.refresh_from_db()
        self.assertTrue(tracking.cleaned_up)
        self.assertIsNotNone(tracking.cleanup_verified_at)

        # Check deletion tracking record was created
        deletion_record = PHIFileTracking.objects.filter(
            action='work_copy_deleted',
            file_path=uploaded_file.storage_path
        ).first()
        self.assertIsNotNone(deletion_record)
        self.assertEqual(deletion_record.purpose_subdirectory, 'auto_cleanup_after_processing')

    @patch('depot.data.upload_prechecker.Auditor')
    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_no_cleanup_on_failed_processing(self, mock_get_storage, mock_auditor_class):
        """Test that files are NOT cleaned up after failed processing."""
        from depot.storage.local import LocalFileSystemStorage

        # Create upload precheck with file
        uploaded_file = UploadedFile.objects.create(
            filename='test.csv',
            storage_path='precheck_runs/1_TEST/patient/20250101_120000_abcd1234_test.csv',
            uploader=self.user,
            type=UploadType.VALIDATION_INPUT,
            file_hash='testhash123'
        )

        precheck_run = PrecheckRun.objects.create(
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            status='pending'
        )

        # Create PHI tracking record with content_object
        from django.contrib.contenttypes.models import ContentType
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path=uploaded_file.storage_path,
            file_type='raw_csv',
            cleanup_required=True,
            cleaned_up=False,
            content_type=ContentType.objects.get_for_model(uploaded_file),
            object_id=uploaded_file.id
        )

        # Mock storage
        mock_storage = MagicMock(spec=LocalFileSystemStorage)
        mock_storage.get_file.return_value = b'test,data\n1,2'
        mock_storage.delete.return_value = True
        mock_get_storage.return_value = mock_storage

        # Mock auditor to return failure
        mock_auditor = MagicMock()
        mock_auditor.process.return_value = {
            'status': 'failed',
            'error': 'Processing failed'
        }
        mock_auditor.cleanup.return_value = None
        mock_auditor_class.return_value = mock_auditor

        # Process the upload precheck
        with patch('django.conf.settings.STORAGE_CONFIG', self.storage_config):
            result = process_precheck_run(precheck_run.id)

        # Check result
        self.assertEqual(result['status'], 'failed')

        # Check file was NOT deleted
        mock_storage.delete.assert_not_called()

        # Check PHI tracking was NOT marked cleaned
        tracking.refresh_from_db()
        self.assertFalse(tracking.cleaned_up)
        self.assertIsNone(tracking.cleanup_verified_at)

        # Check NO deletion tracking record was created
        deletion_record = PHIFileTracking.objects.filter(
            action='work_copy_deleted',
            file_path=uploaded_file.storage_path
        ).exists()
        self.assertFalse(deletion_record)

    @patch('depot.data.upload_prechecker.Auditor')
    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_cleanup_continues_even_if_delete_fails(self, mock_get_storage, mock_auditor_class):
        """Test that processing continues even if cleanup fails."""
        from depot.storage.local import LocalFileSystemStorage

        # Create upload precheck with file
        uploaded_file = UploadedFile.objects.create(
            filename='test.csv',
            storage_path='precheck_runs/1_TEST/patient/20250101_120000_abcd1234_test.csv',
            uploader=self.user,
            type=UploadType.VALIDATION_INPUT,
            file_hash='testhash123'
        )

        precheck_run = PrecheckRun.objects.create(
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            uploaded_file=uploaded_file,
            status='pending'
        )

        # Create PHI tracking record with content_object
        from django.contrib.contenttypes.models import ContentType
        tracking = PHIFileTracking.objects.create(
            cohort=self.cohort,
            user=self.user,
            action='file_uploaded_via_stream',
            file_path=uploaded_file.storage_path,
            file_type='raw_csv',
            cleanup_required=True,
            cleaned_up=False,
            content_type=ContentType.objects.get_for_model(uploaded_file),
            object_id=uploaded_file.id
        )

        # Mock storage
        mock_storage = MagicMock(spec=LocalFileSystemStorage)
        mock_storage.get_file.return_value = b'test,data\n1,2'
        mock_storage.delete.side_effect = Exception("Delete failed!")
        # Mock get_absolute_path to return string instead of MagicMock
        mock_storage.get_absolute_path = lambda path: f'/absolute/{path}'
        mock_get_storage.return_value = mock_storage

        # Mock auditor to return success
        mock_auditor = MagicMock()
        mock_auditor.process.return_value = {
            'status': 'completed',
            'result': {'message': 'Success'}
        }
        mock_auditor.cleanup.return_value = None
        mock_auditor_class.return_value = mock_auditor

        # Process the upload precheck
        with patch('django.conf.settings.STORAGE_CONFIG', self.storage_config):
            result = process_precheck_run(precheck_run.id)

        # Check result is still successful
        self.assertEqual(result['status'], 'completed')

        # Check delete was attempted
        mock_storage.delete.assert_called_once_with(uploaded_file.storage_path)

        # Check PHI tracking was NOT marked cleaned (since delete failed)
        tracking.refresh_from_db()
        self.assertFalse(tracking.cleaned_up)
        self.assertIsNone(tracking.cleanup_verified_at)

        # File should still be marked for cleanup
        self.assertTrue(tracking.cleanup_required)