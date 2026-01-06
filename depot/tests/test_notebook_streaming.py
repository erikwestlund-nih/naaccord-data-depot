"""
Tests for notebook streaming functionality.
Verifies that notebooks are streamed from services server to web server.
"""
import os
import json
from unittest.mock import patch, MagicMock, call
from django.test import override_settings
from depot.tests.base import IsolatedTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.http import HttpResponse

from depot.models import Notebook, Cohort, DataFileType, PrecheckRun
from depot.storage.manager import StorageManager
from depot.storage.remote import RemoteStorageDriver
from depot.storage.local import LocalFileSystemStorage

User = get_user_model()


class TestNotebookStreaming(IsolatedTestCase):
    """Test notebook streaming between web and services servers."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True
        )

        # Create test cohort
        self.cohort = Cohort.objects.create(
            name='Test Cohort'
        )
        self.user.cohorts.add(self.cohort)

        # Create data file type
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            label='Patient'
        )

        # Create notebook
        self.notebook = Notebook.objects.create(
            name='Test Report',
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            status='completed',
            compiled_path='notebooks/test/report.html',
            created_by=self.user,
            template_path='test_template.qmd'
        )

        # Clear storage manager instances
        StorageManager._instances = {}

    def tearDown(self):
        """Clean up after each test."""
        # Clear storage manager instances to prevent test contamination
        StorageManager._instances = {}

    def test_web_server_uses_remote_storage(self):
        """Test that web server uses RemoteStorageDriver."""
        with patch.dict(os.environ, {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-key',
            'SERVICES_URL': 'http://localhost:8001'
        }):
            # Reload settings to pick up environment
            with override_settings(
                SERVER_ROLE='web',
                STORAGE_CONFIG={
                    'disks': {
                        'downloads': {
                            'driver': 'remote',
                            'type': 'remote',
                            'service_url': 'http://localhost:8001',
                            'api_key': 'test-key'
                        }
                    }
                }
            ):
                StorageManager._instances = {}
                storage = StorageManager.get_storage('downloads')
                self.assertIsInstance(storage, RemoteStorageDriver)
                self.assertEqual(storage.service_url, 'http://localhost:8001')

    def test_services_server_uses_local_storage(self):
        """Test that services server uses LocalFileSystemStorage."""
        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}):
            with override_settings(
                SERVER_ROLE='services',
                STORAGE_CONFIG={
                    'disks': {
                        'downloads': {
                            'driver': 'local',
                            'type': 'local',
                            'root': '/tmp/test_storage'
                        }
                    }
                }
            ):
                StorageManager._instances = {}
                storage = StorageManager.get_storage('downloads')
                self.assertIsInstance(storage, LocalFileSystemStorage)

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_notebook_view_streams_from_remote(self, mock_get_storage):
        """Test notebook view streams content from remote storage."""
        # Mock the remote storage
        mock_storage = MagicMock(spec=RemoteStorageDriver)
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = b'<html><body>Test Report</body></html>'
        mock_get_storage.return_value = mock_storage

        # Login
        self.client.login(username='testuser@example.com', password='testpass123')

        # Access notebook
        with patch.dict(os.environ, {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-key',
            'SERVICES_URL': 'http://localhost:8001'
        }):
            response = self.client.get(reverse('notebook_view', args=[self.notebook.id]))

        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test Report', response.content)

        # Verify storage was called correctly (without 'reports/' prefix - it's handled by the storage disk config)
        mock_storage.exists.assert_called_once_with('notebooks/test/report.html')
        mock_storage.get_file.assert_called_once_with('notebooks/test/report.html')

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_notebook_download_streams_from_remote(self, mock_get_storage):
        """Test notebook download streams content from remote storage."""
        # Mock the remote storage
        mock_storage = MagicMock(spec=RemoteStorageDriver)
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = b'<html><body>Download Report</body></html>'
        mock_get_storage.return_value = mock_storage

        # Login
        self.client.login(username='testuser@example.com', password='testpass123')

        # Download notebook
        with patch.dict(os.environ, {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-key',
            'SERVICES_URL': 'http://localhost:8001'
        }):
            response = self.client.get(reverse('notebook_download', args=[self.notebook.id]))

        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn(b'Download Report', response.content)

        # Verify storage was called (without 'reports/' prefix - it's handled by the storage disk config)
        mock_storage.exists.assert_called_once_with('notebooks/test/report.html')
        mock_storage.get_file.assert_called_once_with('notebooks/test/report.html')

    @patch('requests.Session')
    def test_remote_storage_driver_notebook_operations(self, mock_session_class):
        """Test RemoteStorageDriver makes correct API calls for notebooks."""
        # Setup mock session
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Create driver
        with override_settings(
            STORAGE_CONFIG={
                'disks': {
                    'downloads': {
                        'driver': 'remote',
                        'service_url': 'http://localhost:8001',
                        'api_key': 'test-key'
                    }
                }
            }
        ):
            driver = RemoteStorageDriver('downloads')

        # Test exists check
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'exists': True, 'path': 'notebooks/18/1/report.html'}
        mock_session.get.return_value = mock_response

        result = driver.exists('notebooks/18/1/report.html')

        # Verify API call
        mock_session.get.assert_called_with(
            'http://localhost:8001/internal/storage/exists',
            params={'path': 'notebooks/18/1/report.html', 'disk': 'downloads'}
        )
        self.assertTrue(result)

        # Test file download
        mock_session.get.reset_mock()
        mock_response.iter_content.return_value = [b'<html>', b'<body>', b'Content', b'</body>', b'</html>']

        content = driver.get_file('notebooks/18/1/report.html')

        # Verify API call
        mock_session.get.assert_called_with(
            'http://localhost:8001/internal/storage/download',
            params={'path': 'notebooks/18/1/report.html', 'disk': 'downloads'},
            stream=True,
            timeout=300
        )
        self.assertEqual(content, b'<html><body>Content</body></html>')

    def test_notebook_not_found_handling(self):
        """Test proper handling when notebook file doesn't exist."""
        with patch('depot.storage.manager.StorageManager.get_storage') as mock_get_storage:
            # Mock storage that returns file not found
            mock_storage = MagicMock()
            mock_storage.exists.return_value = False
            mock_get_storage.return_value = mock_storage

            # Login
            self.client.login(username='testuser@example.com', password='testpass123')

            # Try to access notebook
            response = self.client.get(reverse('notebook_view', args=[self.notebook.id]))

            # Should return 404 with error message
            self.assertEqual(response.status_code, 404)
            # For StreamingHttpResponse, we need to consume the streaming_content
            if hasattr(response, 'streaming_content'):
                content = b''.join(response.streaming_content)
                self.assertIn(b'Notebook Not Found', content)
            else:
                self.assertIn(b'Notebook Not Found', response.content)

    def test_notebook_permissions_with_streaming(self):
        """Test that permissions are still enforced with streaming."""
        # Create user without access to cohort
        other_user = User.objects.create_user(
            username='otheruser@example.com',
            email='otheruser@example.com',
            password='testpass123'
        )

        # Login as other user
        self.client.login(username='otheruser@example.com', password='testpass123')

        # Try to access notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook.id]))

        # Should be denied
        self.assertEqual(response.status_code, 403)

    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_large_file_streaming(self, mock_get_storage):
        """Test that large files are handled efficiently."""
        # Create a large mock HTML content (5MB)
        large_content = b'<html><body>' + (b'X' * 5 * 1024 * 1024) + b'</body></html>'

        # Mock storage
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = large_content
        mock_get_storage.return_value = mock_storage

        # Login
        self.client.login(username='testuser@example.com', password='testpass123')

        # Access notebook
        response = self.client.get(reverse('notebook_view', args=[self.notebook.id]))

        # Verify response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.content), len(large_content))

        # Verify storage was called (without 'reports/' prefix - it's handled by the storage disk config)
        mock_storage.get_file.assert_called_once_with('notebooks/test/report.html')


class TestInternalStorageAPI(IsolatedTestCase):
    """Test internal storage API endpoints used for streaming."""

    def setUp(self):
        """Set up test environment."""
        self.api_key = 'test-api-key'
        StorageManager._instances = {}

    @override_settings(
        SERVER_ROLE='services',
        STORAGE_CONFIG={
            'disks': {
                'downloads': {
                    'driver': 'local',
                    'root': '/tmp/test_storage'
                }
            }
        }
    )
    @patch.dict(os.environ, {
        'INTERNAL_API_KEY': 'test-api-key',
        'SERVER_ROLE': 'services'
    })
    def test_internal_api_requires_authentication(self):
        """Test that internal API endpoints require API key."""
        # Try without API key
        response = self.client.get('/internal/storage/exists', {'path': 'test.txt'})
        self.assertEqual(response.status_code, 403)

        # Try with wrong API key
        response = self.client.get(
            '/internal/storage/exists',
            {'path': 'test.txt'},
            HTTP_X_API_KEY='wrong-key'
        )
        self.assertEqual(response.status_code, 403)

        # Try with correct API key
        with patch('depot.storage.manager.StorageManager.get_storage') as mock_storage:
            mock_storage.return_value.exists.return_value = True

            response = self.client.get(
                '/internal/storage/exists',
                {'path': 'test.txt', 'disk': 'downloads'},
                HTTP_X_API_KEY='test-api-key'
            )
            self.assertEqual(response.status_code, 200)

    @override_settings(
        SERVER_ROLE='services',
        STORAGE_CONFIG={
            'disks': {
                'downloads': {
                    'driver': 'local',
                    'root': '/tmp/test_storage'
                }
            }
        }
    )
    @patch.dict(os.environ, {
        'INTERNAL_API_KEY': 'test-api-key',
        'SERVER_ROLE': 'services'
    })
    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_storage_download_endpoint(self, mock_get_storage):
        """Test the internal storage download endpoint."""
        # Mock storage
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.get_file.return_value = b'test content'
        mock_storage.get_metadata.return_value = {'content_type': 'text/html'}
        mock_get_storage.return_value = mock_storage

        # Make request
        response = self.client.get(
            '/internal/storage/download',
            {'path': 'notebooks/test.html', 'disk': 'downloads'},
            HTTP_X_API_KEY='test-api-key'
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        # For StreamingHttpResponse, consume streaming_content
        content = b''.join(response.streaming_content)
        self.assertEqual(content, b'test content')
        self.assertEqual(response['Content-Type'], 'text/html')

    @override_settings(
        SERVER_ROLE='services',
        STORAGE_CONFIG={
            'disks': {
                'downloads': {
                    'driver': 'local',
                    'root': '/tmp/test_storage'
                }
            }
        }
    )
    @patch.dict(os.environ, {
        'INTERNAL_API_KEY': 'test-api-key',
        'SERVER_ROLE': 'services'
    })
    @patch('depot.storage.manager.StorageManager.get_storage')
    def test_storage_exists_endpoint(self, mock_get_storage):
        """Test the internal storage exists endpoint."""
        # Mock storage
        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_get_storage.return_value = mock_storage

        # Make request
        response = self.client.get(
            '/internal/storage/exists',
            {'path': 'notebooks/test.html', 'disk': 'downloads'},
            HTTP_X_API_KEY='test-api-key'
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['exists'])
        self.assertEqual(data['path'], 'notebooks/test.html')
