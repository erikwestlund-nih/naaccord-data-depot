"""
Configuration for secure PHI upload architecture.

This configuration supports:
1. Development mode: Local processing with simulated isolation
2. Production mode: Separate secure upload server with NAS mount
"""
from django.conf import settings
import os


# Secure Upload Configuration
SECURE_UPLOAD_CONFIG = {
    # Development configuration (default)
    'development': {
        'mode': 'local',
        'nas_mount': '/tmp/naaccord_nas',  # Simulated NAS
        'use_celery': True,
        'simulate_isolation': True,
    },
    
    # Production configuration
    'production': {
        'mode': 'remote',
        'secure_upload_endpoint': os.getenv('SECURE_UPLOAD_ENDPOINT', 'https://secure-upload.internal'),
        'secure_upload_token': os.getenv('SECURE_UPLOAD_TOKEN'),
        'nas_mount': '/mnt/nas/submissions',  # Real NAS mount
        'use_celery': True,
        'require_tls': True,
        'max_file_size': 10 * 1024 * 1024 * 1024,  # 10GB
    },
    
    # Staging configuration (for testing production setup)
    'staging': {
        'mode': 'remote',
        'secure_upload_endpoint': os.getenv('STAGING_UPLOAD_ENDPOINT', 'https://staging-upload.internal'),
        'secure_upload_token': os.getenv('STAGING_UPLOAD_TOKEN'),
        'nas_mount': '/mnt/staging/submissions',
        'use_celery': True,
        'require_tls': True,
        'max_file_size': 1 * 1024 * 1024 * 1024,  # 1GB for staging
    }
}


def get_upload_config():
    """
    Get the appropriate upload configuration based on environment.
    """
    env = os.getenv('DEPLOYMENT_ENV', 'development')
    return SECURE_UPLOAD_CONFIG.get(env, SECURE_UPLOAD_CONFIG['development'])


def is_secure_mode():
    """
    Check if we're running in secure mode (production/staging).
    """
    config = get_upload_config()
    return config['mode'] == 'remote'


def get_nas_mount_path():
    """
    Get the NAS mount path for the current environment.
    """
    config = get_upload_config()
    return config['nas_mount']


# Export configuration to Django settings
if not hasattr(settings, 'SECURE_UPLOAD_ENDPOINT'):
    config = get_upload_config()
    if config['mode'] == 'remote':
        settings.SECURE_UPLOAD_ENDPOINT = config['secure_upload_endpoint']
        settings.SECURE_UPLOAD_TOKEN = config['secure_upload_token']