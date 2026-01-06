"""
Tests for AuditService
"""
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from depot.services.audit_service import AuditService
from depot.models import (
    PrecheckRun, Cohort, CohortSubmission, ProtocolYear, 
    DataFileType, CohortSubmissionDataTable, DataTableFile,
    UploadedFile, UploadType
)

User = get_user_model()


class TestAuditService(TestCase):
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.cohort = Cohort.objects.create(name='Test Cohort')
        self.protocol_year = ProtocolYear.objects.create(
            name='Test Wave',
            year=2024
        )
        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            started_by=self.user
        )
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient Data'
        )
        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.data_file_type
        )
        self.uploaded_file = UploadedFile.objects.create(
            filename='test.csv',
            storage_path='/test/path',
            file_hash='abc123',
            uploader=self.user,
            type=UploadType.RAW
        )
        self.data_file = DataTableFile.objects.create(
            data_table=self.data_table,
            uploaded_file=self.uploaded_file,
            uploaded_by=self.user,
            version=1
        )
    
    def test_create_audit(self):
        """Test audit creation."""
        audit = AuditService.create_audit(
            submission=self.submission,
            data_table_file=self.data_file,
            uploaded_file_record=self.uploaded_file,
            user=self.user
        )

        self.assertIsNotNone(audit)
        self.assertEqual(audit.cohort, self.cohort)
        self.assertEqual(audit.uploaded_file, self.uploaded_file)
        self.assertEqual(audit.data_file_type, self.data_file_type)
        self.assertEqual(audit.uploaded_by, self.user)

        # Note: PrecheckRun is standalone - not linked to DataTableFile
        # Submissions use ValidationRun, not PrecheckRun
    
    @patch('depot.services.audit_service.process_precheck_run')
    def test_trigger_processing_async_success(self, mock_process_precheck_run):
        """Test successful async processing."""
        mock_delay = Mock()
        mock_process_precheck_run.delay = mock_delay
        
        result = AuditService.trigger_processing(1)
        
        self.assertTrue(result)
        mock_delay.assert_called_once_with(1)
    
    @patch('depot.services.audit_service.process_precheck_run')
    @patch('depot.services.audit_service.settings')
    def test_trigger_processing_fallback_to_sync(self, mock_settings, mock_process_precheck_run):
        """Test fallback to synchronous processing when Celery fails."""
        mock_settings.DEBUG = True
        mock_delay = Mock(side_effect=Exception("Celery not available"))
        mock_process_precheck_run.delay = mock_delay
        
        result = AuditService.trigger_processing(1)
        
        self.assertTrue(result)
        mock_delay.assert_called_once_with(1)
        mock_process_precheck_run.assert_called_once_with(1)
    
    @patch('depot.services.audit_service.process_precheck_run')
    @patch('depot.services.audit_service.settings')
    def test_trigger_processing_production_reraise(self, mock_settings, mock_process_precheck_run):
        """Test that exceptions are re-raised in production."""
        mock_settings.DEBUG = False
        mock_delay = Mock(side_effect=Exception("Celery not available"))
        mock_process_precheck_run.delay = mock_delay
        
        with self.assertRaises(Exception) as context:
            AuditService.trigger_processing(1)
        
        self.assertEqual(str(context.exception), "Celery not available")
    
    def test_check_status(self):
        """Test checking audit status."""
        audit = PrecheckRun.objects.create(
            cohort=self.cohort,
            uploaded_file=self.uploaded_file,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            status='processing'
        )
        
        status = AuditService.check_status(audit.id)
        self.assertEqual(status, 'processing')
        
        # Test non-existent audit
        status = AuditService.check_status(99999)
        self.assertIsNone(status)
    
    def test_mark_failed(self):
        """Test marking audit as failed."""
        audit = PrecheckRun.objects.create(
            cohort=self.cohort,
            uploaded_file=self.uploaded_file,
            data_file_type=self.data_file_type,
            uploaded_by=self.user,
            status='processing'
        )
        
        AuditService.mark_failed(audit.id, "Test error")
        
        audit.refresh_from_db()
        self.assertEqual(audit.status, 'failed')
        self.assertEqual(audit.error, 'Test error')
    
    def test_handle_async_sync_task_async_success(self):
        """Test generic async/sync handler with successful async."""
        mock_async = Mock()
        mock_sync = Mock()
        
        result = AuditService.handle_async_sync_task(
            async_func=mock_async,
            sync_func=mock_sync,
            task_args=(1, 2),
            task_name="test task",
            object_id=123
        )
        
        self.assertTrue(result)
        mock_async.assert_called_once_with(1, 2)
        mock_sync.assert_not_called()
    
    @patch('depot.services.audit_service.settings')
    def test_handle_async_sync_task_sync_fallback(self, mock_settings):
        """Test generic async/sync handler with sync fallback."""
        mock_settings.DEBUG = True
        mock_async = Mock(side_effect=Exception("Async failed"))
        mock_sync = Mock()
        
        result = AuditService.handle_async_sync_task(
            async_func=mock_async,
            sync_func=mock_sync,
            task_args=(1, 2),
            task_name="test task",
            object_id=123
        )
        
        self.assertTrue(result)
        mock_async.assert_called_once_with(1, 2)
        mock_sync.assert_called_once_with(1, 2)