from django.test import Client, override_settings
from depot.tests.base import ActivityTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from unittest.mock import Mock, patch

from depot.models import (
    Activity, ActivityType, Cohort, CohortMembership, 
    CohortSubmission, ProtocolYear
)
from depot.constants.groups import Groups

User = get_user_model()


@override_settings(DEBUG=False, DEV_BYPASS_SECURITY=False, TEST_ACTIVITY_LOGGING=True)
class SubmissionSecurityTest(ActivityTestCase):
    def setUp(self):
        """Set up test data for submission security tests."""
        # Create groups
        self.admin_group = Group.objects.create(name=Groups.NA_ACCORD_ADMINISTRATORS)
        self.manager_group = Group.objects.create(name=Groups.COHORT_MANAGERS)
        self.viewer_group = Group.objects.create(name=Groups.COHORT_VIEWERS)
        
        # Create cohorts
        self.cohort_va = Cohort.objects.create(name="VA Cohort")
        self.cohort_jh = Cohort.objects.create(name="JH Cohort")
        
        # Create protocol year
        self.protocol_year = ProtocolYear.objects.create(
            name="2024 Protocol",
            year=2024,
            is_active=True
        )
        
        # Create users
        self.va_manager = User.objects.create_user(
            username="va_manager@test.org",
            email="va_manager@test.org",
            password="testpass123"
        )
        self.va_manager.groups.add(self.manager_group)
        
        self.jh_manager = User.objects.create_user(
            username="jh_manager@test.org",
            email="jh_manager@test.org",
            password="testpass123"
        )
        self.jh_manager.groups.add(self.manager_group)
        
        self.va_viewer = User.objects.create_user(
            username="va_viewer@test.org",
            email="va_viewer@test.org",
            password="testpass123"
        )
        self.va_viewer.groups.add(self.viewer_group)
        
        self.admin = User.objects.create_user(
            username="admin@test.org",
            email="admin@test.org",
            password="testpass123"
        )
        self.admin.groups.add(self.admin_group)
        
        # Create cohort memberships
        CohortMembership.objects.create(user=self.va_manager, cohort=self.cohort_va)
        CohortMembership.objects.create(user=self.jh_manager, cohort=self.cohort_jh)
        CohortMembership.objects.create(user=self.va_viewer, cohort=self.cohort_va)
        
        # Create submissions for each cohort
        self.va_submission = CohortSubmission.objects.create(
            cohort=self.cohort_va,
            protocol_year=self.protocol_year,
            started_by=self.va_manager,
            status='in_progress'
        )
        
        self.jh_submission = CohortSubmission.objects.create(
            cohort=self.cohort_jh,
            protocol_year=self.protocol_year,
            started_by=self.jh_manager,
            status='in_progress'
        )
        
        self.client = Client()
    
    def tearDown(self):
        """Clean up Activity and DataRevision records to avoid foreign key constraint violations."""
        from depot.models import DataRevision
        DataRevision.objects.all().delete()
        Activity.objects.all().delete()
        super().tearDown()

    def test_cohort_manager_cannot_access_other_cohort_submission(self):
        """VA manager cannot access JH cohort submission."""
        self.client.login(username="va_manager@test.org", password="testpass123")
        
        # Count existing failed access activities
        before_count = Activity.objects.filter(
            user=self.va_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        
        # Try to access JH submission (should be denied)
        response = self.client.get(reverse('submission_detail', args=[self.jh_submission.id]))
        self.assertEqual(response.status_code, 403)
        
        # Check that activity was logged
        after_count = Activity.objects.filter(
            user=self.va_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        self.assertEqual(after_count, before_count + 1)
        
        # Verify the activity details
        activity = Activity.objects.filter(
            user=self.va_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp').first()
        
        self.assertEqual(activity.status_code, 403)
        self.assertEqual(activity.path, f'/submissions/{self.jh_submission.id}')
        self.assertEqual(activity.details['resource_type'], 'submission')
        self.assertEqual(activity.details['resource_id'], self.jh_submission.id)
        self.assertIn('JH Cohort', activity.details['resource_name'])

    def test_cohort_viewer_cannot_access_other_cohort_submission(self):
        """VA viewer cannot access JH cohort submission."""
        self.client.login(username="va_viewer@test.org", password="testpass123")
        
        # Try to access JH submission (should be denied)
        response = self.client.get(reverse('submission_detail', args=[self.jh_submission.id]))
        self.assertEqual(response.status_code, 403)

    def test_cohort_manager_can_access_own_cohort_submission(self):
        """VA manager can access VA cohort submission."""
        self.client.login(username="va_manager@test.org", password="testpass123")
        
        # Access VA submission (should succeed)
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 200)
        
        # Verify NO failed access activity was logged
        failed_activities = Activity.objects.filter(
            user=self.va_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False,
            path=f'/submissions/{self.va_submission.id}'
        ).count()
        self.assertEqual(failed_activities, 0)

    def test_cohort_viewer_can_access_own_cohort_submission(self):
        """VA viewer can access VA cohort submission (read-only)."""
        self.client.login(username="va_viewer@test.org", password="testpass123")
        
        # Access VA submission (should succeed)
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 200)
        
        # Should not be able to edit (can't see final sign off button)
        self.assertNotIn(b'Sign Off Entire Submission', response.content)

    def test_admin_can_access_any_submission(self):
        """NA Accord Administrator can access any submission."""
        self.client.login(username="admin@test.org", password="testpass123")
        
        # Access VA submission (should succeed)
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 200)
        
        # Access JH submission (should succeed)
        response = self.client.get(reverse('submission_detail', args=[self.jh_submission.id]))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated user redirects to login for submission."""
        # Count existing activities for anonymous (should be none)
        before_count = Activity.objects.filter(
            activity_type=ActivityType.PAGE_ACCESS,
            success=False,
            user__isnull=True
        ).count()
        
        # Try to access submission without login
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        # Should redirect to login (either /sign-in or /saml2/login/)
        self.assertTrue('/sign-in' in response.url or '/saml2/login/' in response.url)
        
        # Verify NO activity was logged for anonymous user
        after_count = Activity.objects.filter(
            activity_type=ActivityType.PAGE_ACCESS,
            success=False,
            user__isnull=True
        ).count()
        self.assertEqual(after_count, before_count)

    def test_cross_cohort_manager_access_denied(self):
        """JH manager cannot access VA submission."""
        self.client.login(username="jh_manager@test.org", password="testpass123")
        
        # Try to access VA submission (should be denied)
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 403)
        
        # Verify activity was logged with correct details
        activity = Activity.objects.filter(
            user=self.jh_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp').first()
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.details['resource_type'], 'submission')
        self.assertEqual(activity.details['resource_id'], self.va_submission.id)
        self.assertIn('VA Cohort', activity.details['resource_name'])

    def test_non_member_with_no_groups_denied(self):
        """User with no groups and no cohort membership cannot access submission."""
        # Create a user with no groups or cohort memberships
        no_access_user = User.objects.create_user(
            username="no_access@test.org",
            email="no_access@test.org",
            password="testpass123"
        )
        
        self.client.login(username="no_access@test.org", password="testpass123")
        
        # Try to access any submission (should be denied)
        response = self.client.get(reverse('submission_detail', args=[self.va_submission.id]))
        self.assertEqual(response.status_code, 403)
        
        # Verify activity was logged
        activity = Activity.objects.filter(
            user=no_access_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).first()
        
        self.assertIsNotNone(activity)
        self.assertEqual(activity.status_code, 403)

    def test_access_denied_includes_session_info(self):
        """Access denied logs include session and user agent information."""
        self.client.login(username="va_manager@test.org", password="testpass123")
        
        # Try to access JH submission with custom user agent
        response = self.client.get(
            reverse('submission_detail', args=[self.jh_submission.id]),
            HTTP_USER_AGENT='Mozilla/5.0 Test Browser'
        )
        self.assertEqual(response.status_code, 403)
        
        # Check that activity includes session info
        activity = Activity.objects.filter(
            user=self.va_manager,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp').first()
        
        self.assertIsNotNone(activity)
        self.assertIsNotNone(activity.session_id)
        self.assertEqual(activity.user_agent, 'Mozilla/5.0 Test Browser')
        self.assertIsNotNone(activity.ip_address)