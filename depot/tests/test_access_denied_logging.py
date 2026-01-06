from django.test import Client, override_settings
from depot.tests.base import ActivityTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from unittest.mock import Mock, patch

from depot.models import Activity, ActivityType, Cohort, CohortMembership, Notebook, DataFileType
from depot.constants.groups import Groups

User = get_user_model()


@override_settings(DEBUG=False, DEV_BYPASS_SECURITY=False, TEST_ACTIVITY_LOGGING=True)
class AccessDeniedLoggingTest(ActivityTestCase):
    def setUp(self):
        """Set up test data for access denied logging tests."""
        # Create groups
        self.manager_group = Group.objects.create(name=Groups.COHORT_MANAGERS)
        
        # Create cohorts
        self.cohort_a = Cohort.objects.create(name="Cohort A")
        self.cohort_b = Cohort.objects.create(name="Cohort B")
        
        # Create data file type
        self.data_file_type = DataFileType.objects.create(
            name="test_type",
            label="Test Type",
            description="Test data file type"
        )
        
        # Create users
        self.cohort_a_user = User.objects.create_user(
            username="user_a@test.org",
            email="user_a@test.org",
            password="testpass123"
        )
        self.cohort_a_user.groups.add(self.manager_group)
        
        self.cohort_b_user = User.objects.create_user(
            username="user_b@test.org",
            email="user_b@test.org",
            password="testpass123"
        )
        self.cohort_b_user.groups.add(self.manager_group)
        
        # Create cohort memberships
        CohortMembership.objects.create(user=self.cohort_a_user, cohort=self.cohort_a)
        CohortMembership.objects.create(user=self.cohort_b_user, cohort=self.cohort_b)
        
        # Create a notebook for cohort A
        self.notebook = Notebook.objects.create(
            name="Test Notebook",
            template_path="test/template.qmd",
            status="completed",
            compiled_path="test/compiled.html",
            cohort=self.cohort_a,
            data_file_type=self.data_file_type,
            created_by=self.cohort_a_user
        )
        
        self.client = Client()

    def tearDown(self):
        """Clean up Activity and DataRevision records to avoid foreign key constraint violations."""
        from depot.models import DataRevision
        DataRevision.objects.all().delete()
        Activity.objects.all().delete()
        super().tearDown()

    def test_cohort_access_denied_logged_to_database(self):
        """Access denied to cohort is logged to the database for authenticated users."""
        # Login as cohort B user
        self.client.force_login(self.cohort_b_user)
        
        # Count existing failed access activities for this user
        before_count = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        
        # Try to access cohort A (should be denied)
        response = self.client.get(reverse('cohort_detail', args=[self.cohort_a.id]))
        self.assertEqual(response.status_code, 403)
        
        # Check that activity was logged
        after_count = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        self.assertEqual(after_count, before_count + 1)
        
        # Get the most recent activity
        activities = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp')
        
        activity = activities.first()
        self.assertEqual(activity.status_code, 403)
        self.assertEqual(activity.path, f'/cohorts/{self.cohort_a.id}')
        self.assertEqual(activity.method, 'GET')
        
        # Check details JSON
        self.assertEqual(activity.details['resource_type'], 'cohort')
        self.assertEqual(activity.details['resource_id'], self.cohort_a.id)
        self.assertEqual(activity.details['resource_name'], 'Cohort A')
        self.assertEqual(activity.details['reason'], 'permission_denied')

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_notebook_access_denied_logged_to_database(self, mock_get_storage):
        """Access denied to notebook is logged to the database for authenticated users."""
        # Mock storage
        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = "<html><body>Test</body></html>"
        mock_get_storage.return_value = mock_storage

        # Login as cohort B user
        self.client.force_login(self.cohort_b_user)
        
        # Count existing failed access activities for this user
        before_count = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        
        # Try to access cohort A notebook (should be denied)
        response = self.client.get(reverse('notebook_view', args=[self.notebook.id]))
        self.assertEqual(response.status_code, 403)
        
        # Check that activity was logged
        after_count = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        self.assertEqual(after_count, before_count + 1)
        
        # Get the most recent activity
        activities = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp')
        
        activity = activities.first()
        self.assertEqual(activity.status_code, 403)
        self.assertEqual(activity.path, f'/notebooks/{self.notebook.id}/view')
        self.assertEqual(activity.method, 'GET')
        
        # Check details JSON
        self.assertEqual(activity.details['resource_type'], 'notebook')
        self.assertEqual(activity.details['resource_id'], self.notebook.id)
        self.assertIn('Test Notebook', activity.details['resource_name'])
        self.assertEqual(activity.details['reason'], 'permission_denied')

    def test_unauthenticated_access_denied_not_logged_to_database(self):
        """Access denied for unauthenticated users is NOT logged to the database."""
        # Count existing activities (should be none for anonymous)
        before_count = Activity.objects.filter(
            activity_type=ActivityType.PAGE_ACCESS,
            success=False,
            user__isnull=True
        ).count()
        
        # Try to access cohort without logging in (should redirect to login)
        response = self.client.get(reverse('cohort_detail', args=[self.cohort_a.id]))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Check that NO new activity was logged for anonymous user
        after_count = Activity.objects.filter(
            activity_type=ActivityType.PAGE_ACCESS,
            success=False,
            user__isnull=True
        ).count()
        self.assertEqual(after_count, before_count)

    def test_successful_access_not_logged_as_denied(self):
        """Successful access is not logged as access denied."""
        # Login as cohort A user
        self.client.force_login(self.cohort_a_user)
        
        # Count existing failed access activities for this user
        before_count = Activity.objects.filter(
            user=self.cohort_a_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        
        # Successfully access cohort A
        response = self.client.get(reverse('cohort_detail', args=[self.cohort_a.id]))
        self.assertEqual(response.status_code, 200)
        
        # Check that NO new failed access activity was logged
        after_count = Activity.objects.filter(
            user=self.cohort_a_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        self.assertEqual(after_count, before_count)

    def test_access_denied_includes_session_info(self):
        """Access denied logs include session and user agent information."""
        # Login as cohort B user
        self.client.force_login(self.cohort_b_user)
        
        # Count existing failed access activities for this user
        before_count = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).count()
        
        # Set a custom user agent
        response = self.client.get(
            reverse('cohort_detail', args=[self.cohort_a.id]),
            HTTP_USER_AGENT='Mozilla/5.0 Test Browser'
        )
        self.assertEqual(response.status_code, 403)
        
        # Check that activity includes session info
        activity = Activity.objects.filter(
            user=self.cohort_b_user,
            activity_type=ActivityType.PAGE_ACCESS,
            success=False
        ).order_by('-timestamp').first()
        
        self.assertIsNotNone(activity)
        self.assertIsNotNone(activity.session_id)
        self.assertEqual(activity.user_agent, 'Mozilla/5.0 Test Browser')
        self.assertIsNotNone(activity.ip_address)  # Will be 127.0.0.1 in tests