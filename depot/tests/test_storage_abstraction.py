"""
Test suite for storage abstraction.
Tests respect architectural boundaries - web server vs services server.
"""
import os
from unittest.mock import patch
from django.test import override_settings
from depot.tests.base import IsolatedTestCase

from depot.storage.manager import StorageManager
from depot.storage.local import LocalFileSystemStorage


class TestServicesServerStorage(IsolatedTestCase):
    """Test storage on services server (should use local/S3 directly)."""

    def test_services_server_uses_local_storage(self):
        """Test that services server gets LocalFileSystemStorage for scratch."""
        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}, clear=False):
            with override_settings(
                STORAGE_CONFIG={
                    'disks': {
                        'scratch': {
                            'driver': 'local',
                            'root': '/tmp/test'
                        }
                    }
                },
                WORKSPACE_STORAGE_DISK='scratch'
            ):
                # Clear cached instances
                StorageManager._instances = {}

                storage = StorageManager.get_scratch_storage()
                self.assertIsInstance(storage, LocalFileSystemStorage)


class TestWebServerStorage(IsolatedTestCase):
    """Test storage on web server (should use RemoteStorageDriver)."""

    def test_web_server_uses_remote_storage(self):
        """Test that web server gets RemoteStorageDriver for scratch."""
        with patch.dict(os.environ, {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-key',
            'SERVICES_URL': 'http://localhost:8001'
        }, clear=False):
            # Clear cached instances
            StorageManager._instances = {}

            storage = StorageManager.get_scratch_storage()
            # Should be RemoteStorageDriver, not LocalFileSystemStorage
            self.assertEqual(storage.__class__.__name__, 'RemoteStorageDriver')
            self.assertNotIsInstance(storage, LocalFileSystemStorage)


class TestStorageManagerConfiguration(IsolatedTestCase):
    """Test StorageManager configuration logic without crossing boundaries."""

    def test_default_storage_fallback(self):
        """Test that unknown disk configurations fall back to local storage."""
        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}, clear=False):
            # Clear cached instances
            StorageManager._instances = {}

            # Request a disk that doesn't exist in config
            storage = StorageManager.get_storage('nonexistent')
            self.assertIsInstance(storage, LocalFileSystemStorage)

    def test_storage_manager_caching(self):
        """Test that StorageManager caches instances properly."""
        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}, clear=False):
            # Clear cached instances
            StorageManager._instances = {}

            # Get storage twice
            storage1 = StorageManager.get_storage('local')
            storage2 = StorageManager.get_storage('local')

            # Should be the same instance (cached)
            self.assertIs(storage1, storage2)