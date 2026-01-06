#!/usr/bin/env python
"""
Test runner for FileUploadService tests.
Can be run directly without Django test database.
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'depot.settings')
django.setup()

if __name__ == '__main__':
    from django.test import TestCase
    from depot.tests.services.test_file_upload_service import TestFileUploadService
    import unittest
    
    # Create a test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add our service tests
    suite.addTests(loader.loadTestsFromTestCase(TestFileUploadService))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)