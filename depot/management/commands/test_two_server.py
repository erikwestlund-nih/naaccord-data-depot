"""
Management command to test two-server architecture on a single machine.
Starts both web and services servers on different ports for testing.
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Test two-server architecture on single machine'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--web-port',
            type=int,
            default=8000,
            help='Port for web server (default: 8000)'
        )
        parser.add_argument(
            '--services-port',
            type=int,
            default=8001,
            help='Port for services server (default: 8001)'
        )
        parser.add_argument(
            '--api-key',
            type=str,
            default='test-internal-api-key-12345',
            help='Internal API key for server communication'
        )
        parser.add_argument(
            '--storage-path',
            type=str,
            default=None,
            help='Path for storage (default: temp directory)'
        )
        parser.add_argument(
            '--run-tests',
            action='store_true',
            help='Run test suite after starting servers'
        )
    
    def handle(self, *args, **options):
        web_port = options['web_port']
        services_port = options['services_port']
        api_key = options['api_key']
        storage_path = options['storage_path'] or Path(settings.BASE_DIR).parent / 'test_storage'
        
        self.stdout.write(self.style.SUCCESS('Starting two-server test environment...'))
        self.stdout.write(f'Web Server: http://localhost:{web_port}')
        self.stdout.write(f'Services Server: http://localhost:{services_port}')
        self.stdout.write(f'Storage Path: {storage_path}')
        self.stdout.write(f'API Key: {api_key[:10]}...')
        
        # Ensure storage directory exists
        storage_path = Path(storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        
        # Start services server
        services_env = os.environ.copy()
        services_env.update({
            'SERVER_ROLE': 'services',
            'INTERNAL_API_KEY': api_key,
            'STORAGE_PATH': str(storage_path),
            'STORAGE_CONFIG': f'''{{
                "disks": {{
                    "workspace": {{
                        "driver": "local",
                        "root": "{storage_path}"
                    }}
                }}
            }}''',
            'WORKSPACE_STORAGE_DISK': 'workspace',
        })
        
        services_cmd = [
            sys.executable,
            'manage.py',
            'runserver',
            f'0.0.0.0:{services_port}',
            '--noreload'
        ]
        
        self.stdout.write(self.style.SUCCESS(f'\nStarting SERVICES server on port {services_port}...'))
        services_process = subprocess.Popen(
            services_cmd,
            env=services_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give services server time to start
        time.sleep(2)
        
        # Start web server
        web_env = os.environ.copy()
        web_env.update({
            'SERVER_ROLE': 'web',
            'INTERNAL_API_KEY': api_key,
            'SERVICES_URL': f'http://localhost:{services_port}',
            'STORAGE_CONFIG': f'''{{
                "disks": {{
                    "workspace": {{
                        "driver": "remote",
                        "service_url": "http://localhost:{services_port}",
                        "api_key": "{api_key}"
                    }}
                }}
            }}''',
            'WORKSPACE_STORAGE_DISK': 'workspace',
        })
        
        web_cmd = [
            sys.executable,
            'manage.py',
            'runserver',
            f'0.0.0.0:{web_port}',
            '--noreload'
        ]
        
        self.stdout.write(self.style.SUCCESS(f'\nStarting WEB server on port {web_port}...'))
        web_process = subprocess.Popen(
            web_cmd,
            env=web_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Give web server time to start
        time.sleep(2)
        
        self.stdout.write(self.style.SUCCESS('\nBoth servers started successfully!'))
        self.stdout.write(self.style.WARNING('\nServer Configuration:'))
        self.stdout.write(f'  Web Server (http://localhost:{web_port}):')
        self.stdout.write('    - Role: Web-facing application server')
        self.stdout.write('    - Storage: Streams to services server')
        self.stdout.write('    - No local file storage')
        self.stdout.write(f'  Services Server (http://localhost:{services_port}):')
        self.stdout.write('    - Role: Backend services and storage')
        self.stdout.write(f'    - Storage: Local filesystem at {storage_path}')
        self.stdout.write('    - Handles all file operations')
        
        # Test the connection
        self.stdout.write(self.style.WARNING('\nTesting connection...'))
        if self.test_connection(services_port, api_key):
            self.stdout.write(self.style.SUCCESS('✓ Services server is responding'))
        else:
            self.stdout.write(self.style.ERROR('✗ Services server not responding'))
        
        # Run tests if requested
        if options['run_tests']:
            self.stdout.write(self.style.WARNING('\nRunning test suite...'))
            self.run_tests(web_port, services_port, api_key)
        
        try:
            self.stdout.write(self.style.WARNING('\nServers running. Press Ctrl+C to stop...'))
            self.stdout.write(self.style.SUCCESS('\nYou can now:'))
            self.stdout.write(f'  1. Access web interface at http://localhost:{web_port}')
            self.stdout.write(f'  2. Upload files (they stream to services server)')
            self.stdout.write(f'  3. Check storage at {storage_path}')
            self.stdout.write('  4. Monitor that web server has no local files')
            
            # Keep running until interrupted
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\nShutting down servers...'))
            
            # Terminate processes
            services_process.terminate()
            web_process.terminate()
            
            # Wait for clean shutdown
            services_process.wait(timeout=5)
            web_process.wait(timeout=5)
            
            self.stdout.write(self.style.SUCCESS('Servers stopped.'))
    
    def test_connection(self, services_port, api_key):
        """Test that services server is responding."""
        import requests
        
        try:
            response = requests.get(
                f'http://localhost:{services_port}/internal/storage/health',
                headers={'X-API-Key': api_key},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def run_tests(self, web_port, services_port, api_key):
        """Run the two-server test suite."""
        test_env = os.environ.copy()
        test_env.update({
            'WEB_PORT': str(web_port),
            'SERVICES_PORT': str(services_port),
            'INTERNAL_API_KEY': api_key,
            'TWO_SERVER_TESTING': 'true',
        })
        
        test_cmd = [
            sys.executable,
            'manage.py',
            'test',
            'depot.tests.test_two_server',
            '--verbosity=2'
        ]
        
        result = subprocess.run(test_cmd, env=test_env)
        
        if result.returncode == 0:
            self.stdout.write(self.style.SUCCESS('✓ All tests passed!'))
        else:
            self.stdout.write(self.style.ERROR('✗ Some tests failed'))
        
        return result.returncode == 0