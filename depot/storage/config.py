"""
Default storage configuration for NA-ACCORD.
This can be overridden in settings.py
"""

DEFAULT_STORAGE_CONFIG = {
    'default': 'local',
    'disks': {
        'local': {
            'driver': 'local',
            'root': 'storage/submissions',
        },
        'nas': {
            'driver': 's3',
            'endpoint': 'http://nas.local:9000',  # MinIO or S3-compatible endpoint
            'bucket': 'naaccord-submissions',
            'access_key': '',  # Set in environment
            'secret_key': '',  # Set in environment
        },
        's3': {
            'driver': 's3',
            'endpoint': 'https://s3.amazonaws.com',
            'bucket': 'naaccord-submissions',
            'access_key': '',  # Set in environment
            'secret_key': '',  # Set in environment
            'region': 'us-east-1',
        }
    }
}


def get_storage_config():
    """
    Get storage configuration with environment variable substitution.
    """
    import os
    config = DEFAULT_STORAGE_CONFIG.copy()
    
    # Override with environment variables if present
    if os.getenv('STORAGE_DRIVER'):
        config['default'] = os.getenv('STORAGE_DRIVER')
    
    # NAS configuration
    if os.getenv('NAS_ENDPOINT'):
        config['disks']['nas']['endpoint'] = os.getenv('NAS_ENDPOINT')
    if os.getenv('NAS_ACCESS_KEY'):
        config['disks']['nas']['access_key'] = os.getenv('NAS_ACCESS_KEY')
    if os.getenv('NAS_SECRET_KEY'):
        config['disks']['nas']['secret_key'] = os.getenv('NAS_SECRET_KEY')
    
    # S3 configuration
    if os.getenv('AWS_S3_ENDPOINT'):
        config['disks']['s3']['endpoint'] = os.getenv('AWS_S3_ENDPOINT')
    if os.getenv('AWS_ACCESS_KEY_ID'):
        config['disks']['s3']['access_key'] = os.getenv('AWS_ACCESS_KEY_ID')
    if os.getenv('AWS_SECRET_ACCESS_KEY'):
        config['disks']['s3']['secret_key'] = os.getenv('AWS_SECRET_ACCESS_KEY')
    if os.getenv('AWS_S3_REGION'):
        config['disks']['s3']['region'] = os.getenv('AWS_S3_REGION')
    
    return config