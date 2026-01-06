import os
import logging
from django.conf import settings
from typing import Optional

from depot.storage.base import BaseStorage
from depot.storage.local import LocalFileSystemStorage

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Manager class to handle different storage backends.
    Selects appropriate driver based on configuration.
    """
    
    _instances = {}
    
    @classmethod
    def get_storage(cls, disk_name: Optional[str] = None) -> BaseStorage:
        """
        Get a storage instance for the specified disk.
        
        Args:
            disk_name: Name of the disk configuration to use.
                      If None, uses the default disk from settings.
        
        Returns:
            Storage driver instance
        """
        # Use default disk if not specified
        if disk_name is None:
            disk_name = getattr(settings, 'DEFAULT_STORAGE_DISK', 'local')
        
        # Return cached instance if available
        if disk_name in cls._instances:
            return cls._instances[disk_name]
        
        # Create new instance based on configuration
        storage_config = getattr(settings, 'STORAGE_CONFIG', {})
        disks = storage_config.get('disks', {})
        
        if disk_name not in disks:
            # Default to local storage if not configured
            logger.warning(f"Disk '{disk_name}' not configured, using local storage")
            instance = LocalFileSystemStorage('local')
        else:
            disk_config = disks[disk_name]
            driver = disk_config.get('driver', 'local')
            
            if driver == 'local':
                instance = LocalFileSystemStorage(disk_name)
            elif driver == 's3' or driver == 'nas':
                # Use the existing BaseStorage for S3-compatible storage
                instance = BaseStorage(disk_name)
            elif driver == 'remote':
                # Remote storage driver for web server to services server communication
                from depot.storage.remote import RemoteStorageDriver
                instance = RemoteStorageDriver(disk_name)
            else:
                logger.error(f"Unknown storage driver: {driver}")
                raise ValueError(f"Unknown storage driver: {driver}")
        
        # Cache the instance
        cls._instances[disk_name] = instance
        return instance
    
    @classmethod
    def get_submission_storage(cls) -> BaseStorage:
        """
        Get the storage instance specifically for submission files.
        
        Returns:
            Storage driver instance for submissions
        """
        # Use a specific disk for submissions if configured
        submission_disk = getattr(settings, 'SUBMISSION_STORAGE_DISK', None)
        return cls.get_storage(submission_disk)
    
    @classmethod
    def get_workspace_storage(cls) -> BaseStorage:
        """
        Get the storage instance specifically for in-process work files.

        This includes upload prechecks, validation files, DuckDB conversions,
        and other temporary processing artifacts that require PHI tracking
        and cleanup.

        Automatically selects appropriate driver based on SERVER_ROLE:
        - 'web': Uses RemoteStorageDriver to stream to services server
        - 'services': Uses NAS workspace mount (/mnt/nas/workspace)
        - 'testing': Uses local storage for single-machine testing
        - None/other: Uses configured storage

        This storage is used for all in-process PHI work and must integrate
        with the PHIFileTracking system for cleanup and audit compliance.

        Returns:
            Storage driver instance for workspace
        """
        # Get server role
        server_role = os.environ.get('SERVER_ROLE', '').lower()

        # Special handling for web server role
        if server_role == 'web':
            # Web server always uses remote driver to stream to services
            disk_name = 'workspace_remote'

            # Check if already configured
            if disk_name in cls._instances:
                return cls._instances[disk_name]

            # Get connection details from environment
            services_url = os.environ.get('SERVICES_URL', 'http://localhost:8001')
            api_key = os.environ.get('INTERNAL_API_KEY')

            if not api_key:
                logger.warning("INTERNAL_API_KEY not set for web server, falling back to settings")
                api_key = getattr(settings, 'INTERNAL_API_KEY', None)

            if not api_key:
                raise ValueError("INTERNAL_API_KEY required for web server role")

            # Create dynamic configuration for remote driver
            storage_config = getattr(settings, 'STORAGE_CONFIG', {})
            disks = storage_config.get('disks', {})

            # Add remote workspace configuration
            disks[disk_name] = {
                'driver': 'remote',
                'service_url': services_url,
                'api_key': api_key,
            }

            storage_config['disks'] = disks
            settings.STORAGE_CONFIG = storage_config

            logger.info(f"Web server configured to use remote workspace storage: {services_url}")
            return cls.get_storage(disk_name)

        # For services, testing, or unspecified roles, use normal configuration
        # Check environment variable first
        workspace_disk = os.environ.get('WORKSPACE_STORAGE_DISK')

        # Fall back to settings
        if not workspace_disk:
            workspace_disk = getattr(settings, 'WORKSPACE_STORAGE_DISK', 'workspace')

        # If workspace disk is not configured, create a default local one
        storage_config = getattr(settings, 'STORAGE_CONFIG', {})
        disks = storage_config.get('disks', {})

        if workspace_disk not in disks:
            logger.info(f"Workspace disk '{workspace_disk}' not configured, creating default workspace")
            # Create a default workspace configuration
            disks[workspace_disk] = {
                'driver': 'local',
                'root': '/mnt/nas/workspace'
            }
            storage_config['disks'] = disks
            settings.STORAGE_CONFIG = storage_config

        return cls.get_storage(workspace_disk)

    @classmethod
    def get_scratch_storage(cls) -> BaseStorage:
        """
        Get the storage instance specifically for temporary scratch files.

        Automatically selects appropriate driver based on SERVER_ROLE:
        - 'web': Uses RemoteStorageDriver to stream to services server
        - 'services': Uses configured storage (local or S3)
        - 'testing': Uses local storage for single-machine testing
        - None/other: Uses configured storage

        This storage is used for all temporary processing files that need
        cleanup. It can be configured separately from permanent storage to
        use local disk even in cloud deployments for performance.

        Returns:
            Storage driver instance for scratch
        """
        # Get server role
        server_role = os.environ.get('SERVER_ROLE', '').lower()
        
        # Special handling for web server role
        if server_role == 'web':
            # Web server always uses remote driver to stream to services
            disk_name = 'scratch_remote'
            
            # Check if already configured
            if disk_name in cls._instances:
                return cls._instances[disk_name]
            
            # Get connection details from environment
            services_url = os.environ.get('SERVICES_URL', 'http://localhost:8001')
            api_key = os.environ.get('INTERNAL_API_KEY')
            
            if not api_key:
                logger.warning("INTERNAL_API_KEY not set for web server, falling back to settings")
                api_key = getattr(settings, 'INTERNAL_API_KEY', None)
            
            if not api_key:
                raise ValueError("INTERNAL_API_KEY required for web server role")
            
            # Create dynamic configuration for remote driver
            storage_config = getattr(settings, 'STORAGE_CONFIG', {})
            disks = storage_config.get('disks', {})
            
            # Add remote scratch configuration
            disks[disk_name] = {
                'driver': 'remote',
                'service_url': services_url,
                'api_key': api_key,
            }
            
            storage_config['disks'] = disks
            settings.STORAGE_CONFIG = storage_config
            
            logger.info(f"Web server configured to use remote storage: {services_url}")
            return cls.get_storage(disk_name)
        
        # For services, testing, or unspecified roles, use normal configuration
        # Check environment variable first
        scratch_disk = os.environ.get('SCRATCH_STORAGE_DISK')

        # Fall back to settings
        if not scratch_disk:
            scratch_disk = getattr(settings, 'SCRATCH_STORAGE_DISK', 'scratch')
        
        # If scratch disk is not configured, create a default local one
        storage_config = getattr(settings, 'STORAGE_CONFIG', {})
        disks = storage_config.get('disks', {})

        if scratch_disk not in disks:
            logger.info(f"Scratch disk '{scratch_disk}' not configured, creating default local scratch")
            # Create a default local scratch configuration
            disks[scratch_disk] = {
                'driver': 'local',
                'root': os.path.join(settings.BASE_DIR, '..', 'storage', 'scratch')
            }
            storage_config['disks'] = disks
            settings.STORAGE_CONFIG = storage_config

        return cls.get_storage(scratch_disk)
    
    @classmethod
    def save_submission_file(cls, submission_file, content):
        """
        Save a submission file using the appropriate storage driver.

        Args:
            submission_file: File model instance (e.g., DataTableFile)
            content: File content to save

        Returns:
            Path where the file was saved
        """
        storage = cls.get_submission_storage()
        
        # Generate the storage path
        path = storage.get_path_for_submission_file(
            cohort_id=submission_file.submission.cohort.id,
            cohort_name=submission_file.submission.cohort.name,
            protocol_year=submission_file.submission.protocol_year.name,
            file_type=submission_file.data_file_type.name,
            filename=submission_file.original_filename
        )
        
        # Save the file
        saved_path = storage.save(
            path=path,
            content=content,
            content_type='text/csv',  # Most submission files are CSV
            metadata={
                'submission_id': str(submission_file.submission.id),
                'file_type': submission_file.data_file_type.name,
                'version': str(submission_file.version),
                'uploaded_by': submission_file.uploaded_by.username
            }
        )
        
        # Update the submission file with the storage path
        submission_file.nas_path = path
        submission_file.save()
        
        logger.info(f"Saved submission file to {path}")
        return path
    
    @classmethod
    def get_submission_file_url(cls, submission_file, expires_in: Optional[int] = 3600):
        """
        Get a URL for accessing a submission file.

        Args:
            submission_file: File model instance (e.g., DataTableFile)
            expires_in: Optional expiration time in seconds for signed URLs

        Returns:
            URL to access the file
        """
        if not submission_file.nas_path:
            return None
        
        storage = cls.get_submission_storage()
        
        # For S3-compatible storage, generate a signed URL
        if hasattr(storage, 'client'):
            try:
                from botocore.exceptions import ClientError
                url = storage.client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': storage.bucket,
                        'Key': submission_file.nas_path.lstrip('/')
                    },
                    ExpiresIn=expires_in
                )
                return url
            except ClientError as e:
                logger.error(f"Error generating signed URL: {e}")
                return None
        else:
            # For local storage, return direct URL
            return storage.url(submission_file.nas_path)
    
    @classmethod
    def delete_submission_file(cls, submission_file):
        """
        Delete a submission file from storage.

        Args:
            submission_file: File model instance (e.g., DataTableFile)

        Returns:
            True if successful, False otherwise
        """
        if not submission_file.nas_path:
            return True  # Nothing to delete
        
        storage = cls.get_submission_storage()
        success = storage.delete(submission_file.nas_path)
        
        if success:
            logger.info(f"Deleted submission file from {submission_file.nas_path}")
            submission_file.nas_path = None
            submission_file.save()
        else:
            logger.error(f"Failed to delete submission file from {submission_file.nas_path}")
        
        return success