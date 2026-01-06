"""
Simple tests for streaming architecture without full Django request cycle.
Tests the core functionality without authentication middleware.
"""
import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock
from django.test import override_settings

from depot.storage.manager import StorageManager
from depot.storage.remote import RemoteStorageDriver
from depot.storage.local import LocalFileSystemStorage


class TestStreamingComponents(TestCase):
    """Test individual streaming components."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(self.cleanup_temp_dir)
        StorageManager._instances = {}
        
    def cleanup_temp_dir(self):
        """Clean up temporary directory."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_storage_manager_role_detection(self):
        """Test StorageManager correctly detects server roles."""
        test_cases = [
            ('web', RemoteStorageDriver),
            ('services', LocalFileSystemStorage),
            ('testing', LocalFileSystemStorage),
        ]
        
        for role, expected_class in test_cases:
            with self.subTest(role=role):
                env_vars = {'SERVER_ROLE': role}
                if role == 'web':
                    env_vars.update({
                        'INTERNAL_API_KEY': 'test-key',
                        'SERVICES_URL': 'http://localhost:8001'
                    })
                
                with patch.dict(os.environ, env_vars):
                    with override_settings(
                        STORAGE_CONFIG={
                            'disks': {
                                'scratch': {
                                    'driver': 'local',
                                    'root': self.temp_dir
                                }
                            }
                        },
                        WORKSPACE_STORAGE_DISK='scratch'
                    ):
                        StorageManager._instances = {}
                        storage = StorageManager.get_scratch_storage()
                        self.assertIsInstance(storage, expected_class)
    
    def test_remote_storage_driver_configuration(self):
        """Test RemoteStorageDriver is configured correctly."""
        with patch.dict(os.environ, {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-api-key',
            'SERVICES_URL': 'http://services:8001'
        }):
            with override_settings(
                STORAGE_CONFIG={'disks': {}},
                WORKSPACE_STORAGE_DISK='scratch'
            ):
                StorageManager._instances = {}
                storage = StorageManager.get_scratch_storage()
                
                self.assertIsInstance(storage, RemoteStorageDriver)
                self.assertEqual(storage.service_url, 'http://services:8001')
                self.assertEqual(storage.api_key, 'test-api-key')
    
    @patch('requests.Session')
    def test_remote_storage_driver_operations(self, mock_session_class):
        """Test RemoteStorageDriver operations make correct HTTP calls."""
        # Setup mock session
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Create RemoteStorageDriver
        with override_settings(
            STORAGE_CONFIG={
                'disks': {
                    'test': {
                        'driver': 'remote',
                        'service_url': 'http://services:8001',
                        'api_key': 'test-key'
                    }
                }
            }
        ):
            driver = RemoteStorageDriver('test')
        
        # Test save operation
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'path': 'test/file.txt'}
        mock_session.post.return_value = mock_response
        
        result = driver.save('test/file.txt', b'test content')
        
        # Verify HTTP call
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], 'http://services:8001/internal/storage/upload')
        self.assertEqual(result, 'test/file.txt')
        
        # Test exists operation
        mock_response.json.return_value = {'exists': True}
        mock_session.get.return_value = mock_response
        
        result = driver.exists('test/file.txt')
        
        mock_session.get.assert_called()
        self.assertTrue(result)
    
    def test_local_storage_with_scratch_operations(self):
        """Test LocalFileSystemStorage with scratch operations."""
        with override_settings(
            STORAGE_CONFIG={
                'disks': {
                    'scratch': {
                        'driver': 'local',
                        'root': self.temp_dir
                    }
                }
            }
        ):
            storage = LocalFileSystemStorage('scratch')
            
            # Test save
            content = b'test scratch content'
            storage.save('scratch/test.txt', content)
            
            # Test exists
            self.assertTrue(storage.exists('scratch/test.txt'))
            
            # Test get
            retrieved = storage.get_file('scratch/test.txt')
            self.assertEqual(retrieved, content)
            
            # Test delete_prefix
            storage.save('scratch/dir1/file1.txt', b'file1')
            storage.save('scratch/dir1/file2.txt', b'file2')
            storage.save('scratch/dir2/file3.txt', b'file3')
            
            deleted = storage.delete_prefix('scratch/dir1/')
            self.assertEqual(deleted, 2)
            
            # Verify deletion
            self.assertFalse(storage.exists('scratch/dir1/file1.txt'))
            self.assertFalse(storage.exists('scratch/dir1/file2.txt'))
            self.assertTrue(storage.exists('scratch/dir2/file3.txt'))
    
    def test_scratch_manager_with_streaming(self):
        """Test ScratchManager works with streaming storage."""
        from depot.storage.scratch_manager import ScratchManager
        
        # Test with local storage (services server)
        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}):
            with override_settings(
                STORAGE_CONFIG={
                    'disks': {
                        'scratch': {
                            'driver': 'local', 
                            'root': self.temp_dir
                        }
                    }
                },
                WORKSPACE_STORAGE_DISK='scratch'
            ):
                StorageManager._instances = {}
                scratch = ScratchManager()
                
                # Test directory creation
                upload_id = 123
                prefix = scratch.get_precheck_run_dir(upload_id)
                self.assertEqual(prefix, 'scratch/precheck_runs/123/')
                
                # Test file operations
                key = scratch.save_to_scratch(prefix, 'test.csv', b'col1,col2\nval1,val2')
                self.assertEqual(key, 'scratch/precheck_runs/123/test.csv')
                
                content = scratch.get_from_scratch(key)
                self.assertEqual(content, b'col1,col2\nval1,val2')
                
                # Test cleanup
                success = scratch.cleanup_precheck_run(upload_id)
                self.assertTrue(success)
                
                # Verify cleanup
                self.assertFalse(scratch.exists(key))
    
    def test_phi_tracking_model_fields(self):
        """Test PHIFileTracking model has streaming fields."""
        from depot.models import PHIFileTracking
        
        # Check that streaming-specific fields exist
        field_names = [f.name for f in PHIFileTracking._meta.fields]
        
        streaming_fields = [
            'server_role',
            'stream_start', 
            'stream_complete',
            'bytes_transferred',
            'cleanup_scheduled_for',
            'metadata'
        ]
        
        for field in streaming_fields:
            self.assertIn(field, field_names, f'PHIFileTracking missing field: {field}')
        
        # Check that new action choices exist
        action_choices = [choice[0] for choice in PHIFileTracking.ACTION_CHOICES]
        
        streaming_actions = [
            'file_uploaded_via_stream',
            'file_uploaded_chunked',
            'file_downloaded_via_stream',
            'file_deleted_via_api',
            'scratch_cleanup'
        ]
        
        for action in streaming_actions:
            self.assertIn(action, action_choices, f'PHIFileTracking missing action: {action}')


class TestIntegrationScenarios(TestCase):
    """Test realistic integration scenarios."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(self.cleanup_temp_dir)
        
    def cleanup_temp_dir(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_two_server_simulation(self):
        """Test simulating two servers on one machine."""
        # Services server configuration
        services_env = {
            'SERVER_ROLE': 'services',
            'INTERNAL_API_KEY': 'test-key',
            'WORKSPACE_STORAGE_DISK': 'scratch'
        }
        
        services_settings = {
            'STORAGE_CONFIG': {
                'disks': {
                    'scratch': {
                        'driver': 'local',
                        'root': self.temp_dir
                    }
                }
            }
        }
        
        # Web server configuration  
        web_env = {
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': 'test-key',
            'SERVICES_URL': 'http://localhost:8001'
        }
        
        web_settings = {
            'STORAGE_CONFIG': {
                'disks': {
                    'scratch_remote': {
                        'driver': 'remote',
                        'service_url': 'http://localhost:8001',
                        'api_key': 'test-key'
                    }
                }
            }
        }
        
        # Test services server storage
        with patch.dict(os.environ, services_env):
            with override_settings(**services_settings):
                StorageManager._instances = {}
                services_storage = StorageManager.get_scratch_storage()
                self.assertIsInstance(services_storage, LocalFileSystemStorage)
        
        # Test web server storage 
        with patch.dict(os.environ, web_env):
            with override_settings(**web_settings):
                StorageManager._instances = {}
                web_storage = StorageManager.get_scratch_storage()
                self.assertIsInstance(web_storage, RemoteStorageDriver)
                self.assertEqual(web_storage.service_url, 'http://localhost:8001')
    
    def test_configuration_validation(self):
        """Test that configurations are validated properly."""
        # Test missing API key for web server
        with patch.dict(os.environ, {'SERVER_ROLE': 'web'}, clear=True):
            with override_settings(STORAGE_CONFIG={'disks': {}}, INTERNAL_API_KEY=None):
                StorageManager._instances = {}
                with self.assertRaises(ValueError) as cm:
                    StorageManager.get_scratch_storage()
                self.assertIn('INTERNAL_API_KEY required', str(cm.exception))
    
    def test_cleanup_coordination_logic(self):
        """Test cleanup coordination between servers."""
        from depot.storage.scratch_manager import ScratchManager

        with patch.dict(os.environ, {'SERVER_ROLE': 'services'}, clear=False):
            with override_settings(
                STORAGE_CONFIG={
                    'disks': {
                        'scratch': {
                            'driver': 'local',
                            'root': self.temp_dir
                        }
                    }
                },
                WORKSPACE_STORAGE_DISK='scratch'
            ):
                StorageManager._instances = {}
                scratch = ScratchManager()

                # Test basic functionality - just verify that cleanup coordination exists
                # The details of orphan detection are complex and should be in unit tests
                upload_id = 123
                prefix = scratch.get_precheck_run_dir(upload_id)

                # Test save/retrieve cycle
                key = scratch.save_to_scratch(prefix, 'test.txt', b'test content')
                content = scratch.get_from_scratch(key)
                self.assertEqual(content, b'test content')

                # Test cleanup
                success = scratch.cleanup_precheck_run(upload_id)
                self.assertTrue(success)