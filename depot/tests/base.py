"""
Base test classes for NA-ACCORD tests with proper isolation.
"""
from django.test import TestCase, TransactionTestCase
from django.db.models.signals import post_save, pre_save
from django.test.utils import override_settings
import logging

# Disable logging during tests to reduce noise
logging.disable(logging.CRITICAL)


class IsolatedTestCase(TestCase):
    """
    Test case with proper signal isolation to prevent Activity logging
    from interfering with test database constraints.

    Similar to Laravel's RefreshDatabase trait.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Disconnect problematic signals during tests
        from depot.audit.observers import post_save_observer, pre_save_observer
        post_save.disconnect(post_save_observer)
        pre_save.disconnect(pre_save_observer)

    def tearDown(self):
        """Close database connections after each test method to prevent leaks."""
        from django.db import connections
        for conn in connections.all():
            conn.close()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        # Close all database connections to prevent connection leaks
        from django.db import connections
        for conn in connections.all():
            conn.close()

        super().tearDownClass()
        # Reconnect signals after tests
        from depot.audit.observers import post_save_observer, pre_save_observer
        post_save.connect(post_save_observer)
        pre_save.connect(pre_save_observer)

        # Re-enable logging
        logging.disable(logging.NOTSET)


class IsolatedTransactionTestCase(TransactionTestCase):
    """
    Transaction test case with signal isolation for tests that need
    transaction control (like testing database transactions).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Disconnect problematic signals during tests
        from depot.audit.observers import post_save_observer, pre_save_observer
        post_save.disconnect(post_save_observer)
        pre_save.disconnect(pre_save_observer)

    def tearDown(self):
        """Close database connections after each test method to prevent leaks."""
        from django.db import connections
        for conn in connections.all():
            conn.close()
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        # Close all database connections to prevent connection leaks
        from django.db import connections
        for conn in connections.all():
            conn.close()

        super().tearDownClass()
        # Reconnect signals after tests
        from depot.audit.observers import post_save_observer, pre_save_observer
        post_save.connect(post_save_observer)
        pre_save.connect(pre_save_observer)

        # Re-enable logging
        logging.disable(logging.NOTSET)


class ActivityTestCase(TestCase):
    """
    Test case for tests that specifically need Activity logging enabled.
    Use this for tests that verify Activity/audit functionality.

    This class keeps signals connected but enables clean logging.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Keep signals connected for activity tests - don't disconnect them

        # Configure logging to be less noisy
        logging.getLogger('depot.views.notebooks').setLevel(logging.ERROR)
        logging.getLogger('depot.views.precheck_run').setLevel(logging.ERROR)
        logging.getLogger('depot.middleware').setLevel(logging.ERROR)

    def setUp(self):
        super().setUp()
        # Enable activity logging for these tests
        from django.conf import settings
        settings.TEST_ACTIVITY_LOGGING = True

    def tearDown(self):
        super().tearDown()
        # Don't delete TEST_ACTIVITY_LOGGING if it was set via @override_settings
        # The override_settings decorator will handle cleanup automatically