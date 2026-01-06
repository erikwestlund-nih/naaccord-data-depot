"""
Security tests for cohort-based access control.
Ensures users can only access data from their assigned cohorts.
"""
from depot.tests.base_security import SecurityTestCase


class CohortAccessControlTest(SecurityTestCase):
    """Test that cohort-based access control is enforced."""

    def test_user_has_cohort_membership(self):
        """Users should have cohort memberships."""
        from depot.models import CohortMembership

        # Check that test user has cohort membership
        memberships = CohortMembership.objects.filter(user=self.user)
        self.assertGreater(memberships.count(), 0,
            "User should have at least one cohort membership")

    def test_cohort_membership_links_user_and_cohort(self):
        """CohortMembership should properly link users to cohorts."""
        from depot.models import CohortMembership

        membership = CohortMembership.objects.filter(
            user=self.user,
            cohort=self.cohort_a
        ).first()

        self.assertIsNotNone(membership,
            "User should be member of cohort_a")
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.cohort, self.cohort_a)
