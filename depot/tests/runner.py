"""
Custom test runner to ensure proper database cleanup between tests.
"""
import logging
import os
import sys
from django.test.runner import DiscoverRunner
from django.db import connection


class CleanupTestRunner(DiscoverRunner):
    """Test runner that ensures proper cleanup between tests."""

    def setup_test_environment(self, **kwargs):
        # Set testing flag
        os.environ['TESTING'] = 'True'

        # Suppress all database warnings and output
        import warnings
        warnings.filterwarnings('ignore')

        # Don't override verbosity - let it be controlled by command line
        # self.verbosity = 0

        super().setup_test_environment(**kwargs)

        # Configure comprehensive logging suppression
        loggers_to_suppress = [
            'depot.views.notebooks',
            'depot.views.precheck_run',
            'depot.views.internal_storage',
            'depot.middleware',
            'depot.audit.observers',
            'django.db.backends',
            'django.db.backends.schema',
            'django.request',
            'django.security',
            'django.utils.autoreload',
            'django.contrib.staticfiles',
            'django.contrib.sessions',
            'django.contrib.auth',
            'celery',
            'urllib3',
            'requests',
            'boto3',
            'botocore',
            'paramiko',
            'root'
        ]

        for logger_name in loggers_to_suppress:
            logging.getLogger(logger_name).setLevel(logging.CRITICAL)

        # Suppress root logger completely during tests
        logging.getLogger().setLevel(logging.CRITICAL)

        # Disable foreign key checks for SQLite during tests
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = OFF;')

    def teardown_test_environment(self, **kwargs):
        # Close all database connections to prevent connection leaks
        from django.db import connections
        for conn in connections.all():
            conn.close()

        # Re-enable foreign key checks
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA foreign_keys = ON;')

        # Clean up testing flag
        if 'TESTING' in os.environ:
            del os.environ['TESTING']

        super().teardown_test_environment(**kwargs)

    def run_tests(self, test_labels, **kwargs):
        """Override to suppress stdout during test runs while preserving test indicators."""
        return super().run_tests(test_labels, **kwargs)