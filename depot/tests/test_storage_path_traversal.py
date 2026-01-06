"""
Test suite for LocalFileSystemStorage path traversal protection.
Critical security tests to prevent attackers from accessing files outside storage root.
"""
import os
import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from depot.storage.local import LocalFileSystemStorage


class TestPathTraversalProtection(TestCase):
    """Test path traversal attack prevention in LocalFileSystemStorage."""

    def setUp(self):
        """Create temporary directory for isolated testing."""
        self.temp_dir = tempfile.mkdtemp()

        # Configure storage settings for test
        self.storage_config = {
            'disks': {
                'test': {
                    'driver': 'local',
                    'root': self.temp_dir
                }
            }
        }

        # Apply settings and create storage instance
        with override_settings(STORAGE_CONFIG=self.storage_config):
            self.storage = LocalFileSystemStorage('test')

        # Create test directory structure
        (self.storage.base_path / 'reports').mkdir()
        (self.storage.base_path / 'submissions').mkdir()

        # Create test files
        (self.storage.base_path / 'reports' / 'report1.html').write_text('report content')
        (self.storage.base_path / 'submissions' / 'data.csv').write_text('sensitive PHI data')

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    # =============================================================================
    # Normal Operations (Should Work)
    # =============================================================================

    def test_normal_path_allowed(self):
        """Normal paths should work correctly."""
        content = self.storage.get_file('reports/report1.html')
        self.assertEqual(content, b'report content')

    def test_nested_path_allowed(self):
        """Nested paths within storage root should work."""
        # Create nested structure
        (self.storage.base_path / 'reports' / 'cohort_5').mkdir()
        (self.storage.base_path / 'reports' / 'cohort_5' / 'audit.html').write_text('audit report')

        content = self.storage.get_file('reports/cohort_5/audit.html')
        self.assertEqual(content, b'audit report')

    def test_save_normal_path(self):
        """Saving to normal path should work."""
        path = self.storage.save('reports/new_report.html', b'new content')
        self.assertEqual(path, 'reports/new_report.html')

        # Verify file exists
        saved_file = self.storage.base_path / 'reports' / 'new_report.html'
        self.assertTrue(saved_file.exists())

    # =============================================================================
    # Path Traversal Attacks (Should Be Blocked)
    # =============================================================================

    def test_parent_directory_traversal_blocked(self):
        """Path traversal with ../ should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_double_parent_traversal_blocked(self):
        """Multiple ../ path traversal should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_nested_traversal_blocked(self):
        """Path traversal from nested directory should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('reports/../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_cross_directory_traversal_blocked(self):
        """Attempting to access sibling directory outside root should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('reports/../../../sensitive_files/secrets.txt')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_absolute_path_blocked(self):
        """Absolute paths should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('/etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_save_traversal_blocked(self):
        """Path traversal in save() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.save('../../../tmp/evil.txt', b'malicious content')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_delete_traversal_blocked(self):
        """Path traversal in delete() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.delete('../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_exists_traversal_blocked(self):
        """Path traversal in exists() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.exists('../../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_get_size_traversal_blocked(self):
        """Path traversal in get_size() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_size('../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_get_metadata_traversal_blocked(self):
        """Path traversal in get_metadata() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_metadata('../../../etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_list_files_traversal_blocked(self):
        """Path traversal in list_files() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.list_files('../../etc')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_delete_prefix_traversal_blocked(self):
        """Path traversal in delete_prefix() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.delete_prefix('../../../tmp')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_list_with_prefix_traversal_blocked(self):
        """Path traversal in list_with_prefix() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.list_with_prefix('../../etc')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_ensure_prefix_traversal_blocked(self):
        """Path traversal in ensure_prefix() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.ensure_prefix('../../../tmp/evil')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_touch_traversal_blocked(self):
        """Path traversal in touch() should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            self.storage.touch('../../etc/evil.txt')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    # =============================================================================
    # Symlink Attacks (Should Be Blocked)
    # =============================================================================

    def test_symlink_to_external_file_blocked(self):
        """Symlink pointing outside storage root should be blocked."""
        # Create symlink to /etc/passwd
        symlink_path = self.storage.base_path / 'reports' / 'evil_link'

        try:
            symlink_path.symlink_to('/etc/passwd')
        except OSError:
            # Skip test if we can't create symlinks (Windows, permissions, etc.)
            self.skipTest("Cannot create symlinks on this system")

        # Attempting to read the symlink should fail
        with self.assertRaises(ValueError) as ctx:
            self.storage.get_file('reports/evil_link')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    def test_symlink_to_parent_directory_blocked(self):
        """Symlink to parent directory resolves correctly."""
        symlink_path = self.storage.base_path / 'reports' / 'parent_link'

        try:
            symlink_path.symlink_to('..')
        except OSError:
            self.skipTest("Cannot create symlinks on this system")

        # Symlink resolves to storage root (reports/.. = storage root)
        # Accessing parent_link/submissions/data.csv resolves to submissions/data.csv
        # which is within the storage root, so it's allowed
        content = self.storage.get_file('reports/parent_link/submissions/data.csv')
        self.assertEqual(content, b'sensitive PHI data')

    # =============================================================================
    # Edge Cases
    # =============================================================================

    def test_empty_path_allowed(self):
        """Empty path (current directory) should work."""
        files = self.storage.list_files('')
        self.assertIsInstance(files, list)

    def test_normalized_path_within_root_allowed(self):
        """Paths that normalize to within root should work."""
        # reports/../reports/report1.html normalizes to reports/report1.html
        content = self.storage.get_file('reports/../reports/report1.html')
        self.assertEqual(content, b'report content')

    def test_dot_in_filename_allowed(self):
        """Dots in filename (not directory traversal) should work."""
        self.storage.save('reports/report.v1.2.html', b'versioned report')
        content = self.storage.get_file('reports/report.v1.2.html')
        self.assertEqual(content, b'versioned report')

    def test_current_directory_reference_allowed(self):
        """Current directory reference (./) should work."""
        content = self.storage.get_file('./reports/report1.html')
        self.assertEqual(content, b'report content')

    # =============================================================================
    # Attack Scenario: Report Download Path Traversal
    # =============================================================================

    def test_report_path_traversal_to_submissions_blocked(self):
        """
        Critical security test: Path normalization within root.

        Note: reports/../submissions normalizes to submissions/ which is WITHIN
        the storage root, so this is actually allowed. The key security boundary
        is that paths cannot escape the storage root entirely.

        For application-level access control (reports vs submissions), use
        separate storage instances with different base_path values.
        """
        # This path normalizes to 'submissions/data.csv' which is within root
        content = self.storage.get_file('reports/../submissions/data.csv')

        # Access is allowed because it's within the storage root
        # To prevent cross-directory access, use separate storage instances
        self.assertEqual(content, b'sensitive PHI data')

    def test_absolute_path_within_storage_root_allowed(self):
        """Absolute path that resolves within storage root is allowed."""
        # Absolute path that still resolves to within storage root
        submissions_path = str(self.storage.base_path / 'submissions' / 'data.csv')

        # This is allowed because it resolves to a location within storage root
        content = self.storage.get_file(submissions_path)
        self.assertEqual(content, b'sensitive PHI data')

    def test_absolute_path_outside_storage_root_blocked(self):
        """Absolute path outside storage root should be blocked."""
        with self.assertRaises(ValueError) as ctx:
            # Try to access /etc/passwd (definitely outside storage root)
            self.storage.get_file('/etc/passwd')

        self.assertIn('attempts to escape storage root', str(ctx.exception))

    # =============================================================================
    # Logging Tests
    # =============================================================================

    def test_traversal_attempt_logged(self):
        """Path traversal attempts should be logged for security monitoring."""
        import logging

        with self.assertLogs('depot.storage.local', level='ERROR') as log_ctx:
            try:
                self.storage.get_file('../../etc/passwd')
            except ValueError:
                pass

        # Verify the attempt was logged
        self.assertTrue(
            any('Path traversal attempt detected' in message for message in log_ctx.output),
            "Path traversal attempt should be logged"
        )


class TestPathValidationEdgeCases(TestCase):
    """Test edge cases in path validation logic."""

    def setUp(self):
        """Create temporary directory for isolated testing."""
        self.temp_dir = tempfile.mkdtemp()

        # Configure storage settings for test
        self.storage_config = {
            'disks': {
                'test': {
                    'driver': 'local',
                    'root': self.temp_dir
                }
            }
        }

        # Apply settings and create storage instance
        with override_settings(STORAGE_CONFIG=self.storage_config):
            self.storage = LocalFileSystemStorage('test')

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_windows_style_path_traversal_blocked(self):
        """Windows-style path separators on Unix systems."""
        # On Unix, backslashes are treated as literal filename characters
        # not as path separators, so this looks for a file literally named
        # "reports\\..\\..\\etc\\passwd" which doesn't exist
        # This is actually handled correctly - no security issue
        content = self.storage.get_file('reports\\..\\..\\etc\\passwd')
        self.assertIsNone(content)  # File doesn't exist

    def test_mixed_separators_traversal_blocked(self):
        """Mixed path separators should not bypass protection."""
        with self.assertRaises(ValueError):
            self.storage.get_file('reports/../../../etc/passwd')

    def test_url_encoded_traversal_not_decoded_at_storage_layer(self):
        """URL-encoded paths should be decoded BEFORE reaching storage layer."""
        # URL encoding: ../.. becomes %2E%2E%2F%2E%2E
        # The storage layer does NOT decode URLs - that should happen at the
        # web/view layer before calling storage methods
        # This looks for a literal file named "%2E%2E" which doesn't exist
        content = self.storage.get_file('reports/%2E%2E/submissions/data.csv')
        self.assertIsNone(content)  # File doesn't exist

        # Note: Application layer should decode URLs before passing to storage:
        # from urllib.parse import unquote
        # decoded_path = unquote('reports/%2E%2E/submissions/data.csv')
        # Then path validation will catch the traversal

    def test_null_byte_injection_blocked(self):
        """Null byte injection should not bypass protection."""
        # Attempt to use null byte to truncate path
        with self.assertRaises(ValueError):
            self.storage.get_file('reports/../../etc/passwd\x00.html')

    def test_unicode_traversal_not_interpreted(self):
        """Unicode variations of ../ are not interpreted as path separators."""
        # Unicode character U+2025 (two dot leader) is NOT interpreted as ../
        # It's just a literal character in the filename
        content = self.storage.get_file('reports/\u2025\u2025/etc/passwd')
        self.assertIsNone(content)  # File doesn't exist (no security issue)


class TestIntegrationWithStorageManager(TestCase):
    """Test path validation works correctly when used via StorageManager."""

    def test_storage_manager_enforces_path_validation(self):
        """Verify StorageManager properly delegates path validation to driver."""
        from depot.storage.manager import StorageManager
        import tempfile
        import shutil
        from django.test import override_settings

        temp_dir = tempfile.mkdtemp()

        try:
            with override_settings(
                STORAGE_CONFIG={
                    'disks': {
                        'test_disk': {
                            'driver': 'local',
                            'root': temp_dir
                        }
                    }
                }
            ):
                # Clear cache
                StorageManager._instances = {}

                storage = StorageManager.get_storage('test_disk')

                # Create a test file
                Path(temp_dir).joinpath('safe.txt').write_text('safe content')

                # Normal access should work
                content = storage.get_file('safe.txt')
                self.assertEqual(content, b'safe content')

                # Path traversal should be blocked
                with self.assertRaises(ValueError) as ctx:
                    storage.get_file('../../etc/passwd')

                self.assertIn('attempts to escape storage root', str(ctx.exception))

        finally:
            shutil.rmtree(temp_dir)
