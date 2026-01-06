"""
Tests for SubmissionActivityLogger service
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from depot.services.activity_logger import SubmissionActivityLogger
from depot.models import (
    Cohort, CohortSubmission, ProtocolYear,
    SubmissionActivity, DataFileType
)

User = get_user_model()


class TestSubmissionActivityLogger(TestCase):
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
            started_by=self.user,
            status='draft'
        )
        self.logger = SubmissionActivityLogger()
    
    def test_log_submission_created(self):
        """Test logging submission creation."""
        activity = self.logger.log_submission_created(self.submission, self.user)
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.submission, self.submission)
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_CREATED)
        self.assertIn('Test Cohort', activity.description)
        self.assertIn('Test Wave', activity.description)
    
    def test_log_status_changed(self):
        """Test logging status change."""
        activity = self.logger.log_status_changed(
            self.submission, self.user, 'draft', 'in_progress'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_STATUS_CHANGED)
        self.assertIn('draft', activity.description)
        self.assertIn('in_progress', activity.description)
        self.assertEqual(activity.data.get('old_status'), 'draft')
        self.assertEqual(activity.data.get('new_status'), 'in_progress')
    
    def test_log_file_uploaded(self):
        """Test logging file upload."""
        activity = self.logger.log_file_uploaded(
            submission=self.submission,
            user=self.user,
            file_type='Patient Data',
            file_name='patients.csv',
            version=1
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_FILE_UPLOADED)
        self.assertIn('Patient Data', activity.description)
        self.assertIn('patients.csv', activity.description)
        self.assertIn('v1', activity.description)
        self.assertEqual(activity.data.get('file_type'), 'Patient Data')
        self.assertEqual(activity.data.get('version'), 1)
    
    def test_log_file_approved(self):
        """Test logging file approval."""
        activity = self.logger.log_file_approved(
            submission=self.submission,
            user=self.user,
            file_type='Laboratory Data',
            file_name='lab_results.csv'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_FILE_APPROVED)
        self.assertIn('Approved', activity.description)
        self.assertIn('Laboratory Data', activity.description)
    
    def test_log_file_rejected(self):
        """Test logging file rejection."""
        activity = self.logger.log_file_rejected(
            submission=self.submission,
            user=self.user,
            file_type='Medication Data',
            file_name='meds.csv',
            reason='Invalid format'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_FILE_REJECTED)
        self.assertIn('Rejected', activity.description)
        self.assertIn('Invalid format', activity.description)
        self.assertEqual(activity.data.get('rejection_reason'), 'Invalid format')
    
    def test_log_file_skipped(self):
        """Test logging file skipping."""
        activity = self.logger.log_file_skipped(
            submission=self.submission,
            user=self.user,
            file_type='Optional Data',
            reason='Not collected by cohort'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_FILE_SKIPPED)
        self.assertIn('Skipped', activity.description)
        self.assertIn('Not collected', activity.description)
    
    def test_log_signed_off(self):
        """Test logging submission sign-off."""
        activity = self.logger.log_signed_off(
            submission=self.submission,
            user=self.user,
            comments='All data verified'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_SIGNED_OFF)
        self.assertIn('signed off', activity.description)
        self.assertIn('All data verified', activity.description)
        self.assertIsNotNone(activity.data.get('signed_off_at'))
    
    def test_log_reopened(self):
        """Test logging submission reopening."""
        activity = self.logger.log_reopened(
            submission=self.submission,
            user=self.user,
            reason='Additional data needed'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_REOPENED)
        self.assertIn('reopened', activity.description)
        self.assertIn('Additional data needed', activity.description)
        self.assertIsNotNone(activity.data.get('reopened_at'))
    
    def test_log_comment_added(self):
        """Test logging comment addition."""
        activity = self.logger.log_comment_added(
            submission=self.submission,
            user=self.user,
            comment='Please review the patient counts'
        )
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_COMMENT_ADDED)
        self.assertIn('Comment added', activity.description)
        self.assertEqual(activity.data.get('comment'), 'Please review the patient counts')
    
    def test_log_patient_ids_extracted(self):
        """Test logging patient ID extraction."""
        activity = self.logger.log_patient_ids_extracted(
            submission=self.submission,
            user=self.user,
            patient_count=150,
            file_id=123
        )

        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, SubmissionActivity.ACTIVITY_PATIENT_IDS_EXTRACTED)
        self.assertIn('150 patient IDs', activity.description)
        self.assertEqual(activity.data.get('patient_count'), 150)
        # File reference is now stored in the 'file' ForeignKey field, not in data
        # Since file_id=123 doesn't exist in test DB, file will be None
        self.assertIsNone(activity.file)
    
    def test_get_submission_activities(self):
        """Test getting activities for a submission."""
        # Create some activities
        self.logger.log_submission_created(self.submission, self.user)
        self.logger.log_status_changed(self.submission, self.user, 'draft', 'in_progress')
        self.logger.log_file_uploaded(
            self.submission, self.user, 'Patient', 'test.csv', 1
        )
        
        # Get all activities
        activities = self.logger.get_submission_activities(self.submission)
        self.assertEqual(activities.count(), 3)
        
        # Get limited activities
        activities = self.logger.get_submission_activities(self.submission, limit=2)
        self.assertEqual(len(activities), 2)
    
    def test_batch_log_activities(self):
        """Test batch logging of activities."""
        activities_data = [
            {
                'submission': self.submission,
                'user': self.user,
                'activity_type': SubmissionActivity.ACTIVITY_COMMENT_ADDED,
                'description': 'Comment 1',
            },
            {
                'submission': self.submission,
                'user': self.user,
                'activity_type': SubmissionActivity.ACTIVITY_COMMENT_ADDED,
                'description': 'Comment 2',
            },
            {
                'submission': self.submission,
                'user': self.user,
                'activity_type': SubmissionActivity.ACTIVITY_COMMENT_ADDED,
                'description': 'Comment 3',
            }
        ]
        
        activities = self.logger.batch_log_activities(activities_data)
        
        self.assertEqual(len(activities), 3)
        self.assertEqual(
            SubmissionActivity.objects.filter(submission=self.submission).count(),
            3
        )