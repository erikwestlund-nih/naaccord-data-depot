from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from unittest.mock import Mock, patch

from depot.models import Notebook, Cohort, CohortMembership, DataFileType
from depot.constants.groups import Groups

User = get_user_model()


@override_settings(DEBUG=False, DEV_BYPASS_SECURITY=False)
class NotebookAccessControlTest(TestCase):
    def setUp(self):
        """Set up test data for notebook access control tests."""
        # Create groups
        self.admin_group = Group.objects.create(name=Groups.NA_ACCORD_ADMINISTRATORS)
        self.manager_group = Group.objects.create(name=Groups.COHORT_MANAGERS)
        self.viewer_group = Group.objects.create(name=Groups.COHORT_VIEWERS)
        
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
        self.admin_user = User.objects.create_user(
            username="admin@naaccord.org",
            email="admin@naaccord.org",
            password="testpass123"
        )
        self.admin_user.groups.add(self.admin_group)
        
        self.cohort_a_manager = User.objects.create_user(
            username="manager@cohorta.org",
            email="manager@cohorta.org", 
            password="testpass123"
        )
        self.cohort_a_manager.groups.add(self.manager_group)
        
        self.cohort_a_viewer = User.objects.create_user(
            username="viewer@cohorta.org",
            email="viewer@cohorta.org",
            password="testpass123"
        )
        self.cohort_a_viewer.groups.add(self.viewer_group)
        
        self.cohort_b_manager = User.objects.create_user(
            username="manager@cohortb.org", 
            email="manager@cohortb.org",
            password="testpass123"
        )
        self.cohort_b_manager.groups.add(self.manager_group)
        
        self.unauthorized_user = User.objects.create_user(
            username="unauthorized@example.org",
            email="unauthorized@example.org",
            password="testpass123"
        )
        
        # Create cohort memberships
        CohortMembership.objects.create(user=self.cohort_a_manager, cohort=self.cohort_a)
        CohortMembership.objects.create(user=self.cohort_a_viewer, cohort=self.cohort_a)
        CohortMembership.objects.create(user=self.cohort_b_manager, cohort=self.cohort_b)
        
        # Create notebooks for each cohort
        self.notebook_cohort_a = Notebook.objects.create(
            name="Cohort A Notebook",
            template_path="test/template.qmd",
            status="completed",
            compiled_path="test/compiled.html",
            cohort=self.cohort_a,
            data_file_type=self.data_file_type,
            created_by=self.admin_user
        )
        
        self.notebook_cohort_b = Notebook.objects.create(
            name="Cohort B Notebook", 
            template_path="test/template2.qmd",
            status="completed", 
            compiled_path="test/compiled2.html",
            cohort=self.cohort_b,
            data_file_type=self.data_file_type,
            created_by=self.admin_user
        )
        
        self.client = Client()

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_admin_can_access_all_notebooks(self, mock_get_storage):
        """NA Accord Administrators can access notebooks from any cohort."""
        # Mock storage to return HTML content
        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = "<html><body>Test notebook content</body></html>"
        mock_get_storage.return_value = mock_storage
        
        self.client.login(username="admin@naaccord.org", password="testpass123")
        
        # Should be able to access Cohort A notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 200)
        
        # Should be able to access Cohort B notebook  
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_b.id]))
        self.assertEqual(response.status_code, 200)

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_cohort_members_can_access_own_cohort_notebooks(self, mock_get_storage):
        """Cohort members can access notebooks from their own cohort."""
        # Mock storage to return HTML content
        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = "<html><body>Test notebook content</body></html>"
        mock_get_storage.return_value = mock_storage
        
        # Cohort A manager accessing Cohort A notebook
        self.client.login(username="manager@cohorta.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 200)
        
        # Cohort A viewer accessing Cohort A notebook
        self.client.login(username="viewer@cohorta.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 200)
        
        # Cohort B manager accessing Cohort B notebook
        self.client.login(username="manager@cohortb.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_b.id]))
        self.assertEqual(response.status_code, 200)

    def test_cohort_members_cannot_access_other_cohort_notebooks(self):
        """Cohort members cannot access notebooks from other cohorts."""
        # Cohort A manager trying to access Cohort B notebook
        self.client.login(username="manager@cohorta.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_b.id]))
        self.assertEqual(response.status_code, 403)
        
        # Cohort A viewer trying to access Cohort B notebook
        self.client.login(username="viewer@cohorta.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_b.id]))
        self.assertEqual(response.status_code, 403)
        
        # Cohort B manager trying to access Cohort A notebook
        self.client.login(username="manager@cohortb.org", password="testpass123")
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 403)

    def test_unauthorized_users_cannot_access_any_notebooks(self):
        """Users without cohort membership cannot access any notebooks."""
        self.client.login(username="unauthorized@example.org", password="testpass123")
        
        # Should not be able to access Cohort A notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 403)
        
        # Should not be able to access Cohort B notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_b.id]))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_users_redirected_to_login(self):
        """Unauthenticated users are redirected to login page."""
        # Don't login, try to access notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook_cohort_a.id]))
        self.assertEqual(response.status_code, 302)
        # Should redirect to login (either /sign-in or /saml2/login/)
        self.assertTrue('/sign-in' in response.url or '/saml2/login/' in response.url)

    def test_notebook_can_access_method(self):
        """Test the notebook.can_access() method directly."""
        # Admin should have access to all notebooks
        self.assertTrue(self.notebook_cohort_a.can_access(self.admin_user))
        self.assertTrue(self.notebook_cohort_b.can_access(self.admin_user))
        
        # Cohort A members should have access to Cohort A notebook only
        self.assertTrue(self.notebook_cohort_a.can_access(self.cohort_a_manager))
        self.assertTrue(self.notebook_cohort_a.can_access(self.cohort_a_viewer))
        self.assertFalse(self.notebook_cohort_b.can_access(self.cohort_a_manager))
        self.assertFalse(self.notebook_cohort_b.can_access(self.cohort_a_viewer))
        
        # Cohort B members should have access to Cohort B notebook only
        self.assertTrue(self.notebook_cohort_b.can_access(self.cohort_b_manager))
        self.assertFalse(self.notebook_cohort_a.can_access(self.cohort_b_manager))
        
        # Unauthorized user should have no access
        self.assertFalse(self.notebook_cohort_a.can_access(self.unauthorized_user))
        self.assertFalse(self.notebook_cohort_b.can_access(self.unauthorized_user))

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_all_notebooks_enforce_access_control(self, mock_get_storage):
        """Comprehensive test to ensure all notebooks enforce access control."""
        # Mock storage to return HTML content
        mock_storage = Mock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = "<html><body>Test notebook content</body></html>"
        mock_get_storage.return_value = mock_storage
        
        # Get all notebooks in the database
        all_notebooks = Notebook.objects.all()
        
        for notebook in all_notebooks:
            # Test with unauthorized user
            self.client.login(username="unauthorized@example.org", password="testpass123")
            response = self.client.get(reverse('notebook_view', args=[notebook.id]))
            self.assertEqual(
                response.status_code, 
                403, 
                f"Unauthorized user should not access notebook {notebook.id} ({notebook.name})"
            )
            
            # Test with admin (should always work)
            self.client.login(username="admin@naaccord.org", password="testpass123")
            response = self.client.get(reverse('notebook_view', args=[notebook.id]))
            self.assertEqual(
                response.status_code,
                200,
                f"Admin should be able to access notebook {notebook.id} ({notebook.name})"
            )