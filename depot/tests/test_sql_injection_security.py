"""
Security tests for SQL injection prevention.
Tests that Django ORM properly parameterizes queries.
"""
from django.db import connection
from django.db.models import Q, Count
from depot.models import Cohort, Notebook
from depot.tests.base_security import SecurityTestCase


class SQLInjectionPreventionTest(SecurityTestCase):
    """Test that SQL injection attacks are prevented."""

    def test_orm_filter_with_malicious_string(self):
        """ORM filter should handle SQL injection attempts safely."""
        malicious_inputs = [
            "'; DROP TABLE depot_cohort; --",
            "1' OR '1'='1",
            "1' UNION SELECT * FROM depot_user; --",
            "'; DELETE FROM depot_cohort WHERE '1'='1",
        ]

        for malicious_input in malicious_inputs:
            # Should not execute SQL - should be treated as literal string
            result = Cohort.objects.filter(name=malicious_input)

            # Should return empty (not find a match)
            self.assertEqual(result.count(), 0,
                f"SQL injection attempt should not match: {malicious_input}")

            # Verify table still exists (wasn't dropped)
            self.assertTrue(Cohort.objects.exists(),
                "Cohort table should still exist after injection attempt")

    def test_orm_get_with_malicious_input(self):
        """ORM get() should handle SQL injection attempts safely."""
        malicious_inputs = [
            "1' OR '1'='1",
            "'; DROP TABLE depot_notebook; --",
        ]

        for malicious_input in malicious_inputs:
            # Should raise DoesNotExist, not execute SQL
            with self.assertRaises(Notebook.DoesNotExist):
                Notebook.objects.get(name=malicious_input)

            # Verify tables still exist
            self.assertTrue(Notebook.objects.exists(),
                "Notebook table should still exist")

    def test_orm_raw_query_with_parameters(self):
        """Raw SQL queries should use parameters, not string interpolation."""
        malicious_id = "1 OR 1=1"

        # Using parameterized query (SAFE)
        results = list(Cohort.objects.raw(
            'SELECT * FROM depot_cohort WHERE id = %s',
            [malicious_id]
        ))

        # Should return empty (malicious_id is not a valid ID)
        self.assertEqual(len(results), 0,
            "Parameterized query should not be vulnerable to injection")

        # Verify cohort still exists
        self.assertTrue(Cohort.objects.filter(id=self.cohort_a.id).exists())

    def test_q_objects_with_malicious_input(self):
        """Q objects should handle SQL injection safely."""
        malicious_input = "Test' OR '1'='1"

        # Q objects should be safe
        result = Cohort.objects.filter(
            Q(name=malicious_input) | Q(name__contains="Cohort")
        )

        # Should only match legitimate entries (Cohort A, Cohort B)
        self.assertLessEqual(result.count(), 2,
            "Q object query should be safe from injection")

    def test_order_by_with_malicious_field(self):
        """order_by should reject invalid field names."""
        malicious_fields = [
            "name; DROP TABLE depot_cohort; --",
            "name' OR '1'='1",
        ]

        for malicious_field in malicious_fields:
            # Should raise FieldError, not execute SQL
            with self.assertRaises(Exception):  # FieldError or similar
                list(Cohort.objects.order_by(malicious_field))

    def test_extra_with_parameters(self):
        """extra() queries should use parameters."""
        malicious_value = "'; DROP TABLE depot_cohort; --"

        result = Cohort.objects.extra(
            where=["name = %s"],
            params=[malicious_value]
        )

        # Should return empty, not execute DROP
        self.assertEqual(result.count(), 0)

        # Verify table exists
        self.assertTrue(Cohort.objects.exists())

    def test_connection_execute_with_parameters(self):
        """Direct connection.execute should use parameters."""
        with connection.cursor() as cursor:
            malicious_id = "1; DROP TABLE depot_cohort; --"

            # Parameterized query (SAFE)
            cursor.execute(
                "SELECT * FROM depot_cohort WHERE id = %s",
                [malicious_id]
            )
            results = cursor.fetchall()

            # Should return empty
            self.assertEqual(len(results), 0)

        # Verify table exists
        self.assertTrue(Cohort.objects.exists())

    def test_exclude_with_malicious_input(self):
        """exclude() should handle SQL injection safely."""
        malicious_input = "Test' OR '1'='1"

        result = Cohort.objects.exclude(name=malicious_input)

        # Should return all cohorts (none match malicious string)
        self.assertEqual(result.count(), Cohort.objects.count())

    def test_annotate_with_safe_aggregation(self):
        """annotate() should handle malicious input safely."""
        malicious_input = "'; DROP TABLE depot_notebook; --"

        result = Cohort.objects.filter(
            name=malicious_input
        ).annotate(
            notebook_count=Count('notebook')
        )

        # Should return empty, not execute SQL
        self.assertEqual(result.count(), 0)

        # Verify table exists
        self.assertTrue(Notebook.objects.exists())

    def test_values_with_malicious_field_names(self):
        """values() should reject invalid field names."""
        malicious_fields = [
            "name'; DROP TABLE depot_cohort; --",
            "name' OR '1'='1",
        ]

        for malicious_field in malicious_fields:
            # Should raise FieldError
            with self.assertRaises(Exception):
                list(Cohort.objects.values(malicious_field))
