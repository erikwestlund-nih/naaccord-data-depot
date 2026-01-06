"""
Test to verify the test suite is actually running tests.
This test intentionally takes time to demonstrate tests are executing.
"""
import time
from django.test import TestCase

class TestTimingVerification(TestCase):
    """Tests to verify the test suite is working."""
    
    def test_simple_assertion(self):
        """Quick test with basic assertion."""
        self.assertEqual(2 + 2, 4)
        self.assertTrue(True)
        self.assertFalse(False)
    
    def test_with_intentional_delay(self):
        """Test that intentionally takes time to verify tests are running."""
        start = time.time()
        time.sleep(0.1)  # Sleep for 100ms
        end = time.time()
        
        # Verify the sleep actually happened
        elapsed = end - start
        self.assertGreaterEqual(elapsed, 0.1, "Test should have taken at least 100ms")
        
        # Also do some actual testing
        test_list = [1, 2, 3, 4, 5]
        self.assertEqual(len(test_list), 5)
        self.assertIn(3, test_list)
    
    def test_failure_example(self):
        """Test that would fail if uncommented - demonstrates tests are running."""
        # Uncomment the line below to see a test failure
        # self.assertEqual(1, 2, "This test intentionally fails when uncommented")
        
        # Instead, we'll pass
        self.assertEqual(1, 1)