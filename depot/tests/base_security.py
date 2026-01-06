"""
Base test class for security tests with proper database setup.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.models import Cohort, CohortMembership, DataFileType, ProtocolYear, Notebook
from depot.constants.groups import Groups

User = get_user_model()


class SecurityTestCase(TestCase):
    """
    Base class for security tests with proper database setup.

    Provides:
    - Test users (admin, regular user, viewer)
    - Test cohorts
    - Data file types
    - Protocol years
    - Proper group assignments
    """

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in the class."""
        # Create admin user
        cls.admin = User.objects.create_user(
            username="admin@test.org",
            email="admin@test.org",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )

        # Create regular user
        cls.user = User.objects.create_user(
            username="user@test.org",
            email="user@test.org",
            password="testpass123"
        )

        # Create viewer user
        cls.viewer = User.objects.create_user(
            username="viewer@test.org",
            email="viewer@test.org",
            password="testpass123"
        )

        # Create groups
        cls.admin_group = Group.objects.create(name=Groups.NA_ACCORD_ADMINISTRATORS)
        cls.manager_group = Group.objects.create(name=Groups.COHORT_MANAGERS)
        cls.viewer_group = Group.objects.create(name=Groups.COHORT_VIEWERS)

        # Assign users to groups
        cls.admin.groups.add(cls.admin_group)
        cls.user.groups.add(cls.manager_group)
        cls.viewer.groups.add(cls.viewer_group)

        # Create protocol year
        cls.protocol_year = ProtocolYear.objects.create(
            name="Protocol 2025",
            year=2025,
            is_active=True
        )

        # Create cohorts
        cls.cohort_a = Cohort.objects.create(
            name="Cohort A"
        )

        cls.cohort_b = Cohort.objects.create(
            name="Cohort B"
        )

        # Create cohort memberships
        CohortMembership.objects.create(
            user=cls.user,
            cohort=cls.cohort_a
        )

        CohortMembership.objects.create(
            user=cls.viewer,
            cohort=cls.cohort_a
        )

        # Create data file types
        cls.patient_file_type = DataFileType.objects.create(
            name="patient",
            label="Patient",
            description="Patient data file"
        )

        cls.medication_file_type = DataFileType.objects.create(
            name="medication",
            label="Medication",
            description="Medication data file"
        )

        # Create test notebook
        cls.notebook = Notebook.objects.create(
            name="Test Notebook",
            template_path="audit/generic_audit.qmd",
            cohort=cls.cohort_a,
            data_file_type=cls.patient_file_type,
            created_by=cls.admin
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = Client()
