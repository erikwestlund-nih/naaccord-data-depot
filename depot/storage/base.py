from abc import ABC, abstractmethod
from django.core.files.storage import Storage
from django.conf import settings
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

class BaseStorage(ABC):
    """Base class for storage backends."""
    
    def __init__(self, disk_name):
        self.disk_name = disk_name
        if 'STORAGE_CONFIG' not in dir(settings):
            raise ValueError("STORAGE_CONFIG not found in Django settings")
        
        if disk_name not in settings.STORAGE_CONFIG['disks']:
            raise ValueError(f"Disk '{disk_name}' not found in STORAGE_CONFIG")
            
        self.disk_config = settings.STORAGE_CONFIG['disks'][disk_name]
        
        # Only initialize S3 if it's an S3 disk
        if self.disk_config.get('driver') == 's3' or self.disk_config.get('type') == 's3':
            self.bucket = self.disk_config.get('bucket')
            if self.bucket:
                self.client = self._get_client()
                # Ensure bucket exists
                self._ensure_bucket_exists()
            else:
                self.client = None
        else:
            self.bucket = None
            self.client = None

    def _get_client(self):
        """Get the S3 client for the storage backend."""
        try:
            client = boto3.client(
                's3',
                endpoint_url=self.disk_config['endpoint'],
                aws_access_key_id=self.disk_config['access_key'],
                aws_secret_access_key=self.disk_config['secret_key'],
                config=Config(
                    s3={'addressing_style': 'path'},
                    signature_version='s3v4',
                    retries={'max_attempts': 3}
                )
            )
            return client
        except NoCredentialsError:
            logger.error("AWS credentials not available")
            raise
        except Exception as e:
            logger.error(f"Error creating S3 client: {e}")
            raise

    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, create if it doesn't."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                try:
                    self.client.create_bucket(Bucket=self.bucket)
                    logger.info(f"Created bucket: {self.bucket}")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket {self.bucket}: {create_error}")
                    raise
            else:
                logger.error(f"Error checking bucket {self.bucket}: {e}")
                raise

    def save(self, path, content, content_type=None, metadata=None):
        """Save content to the specified path.
        
        Args:
            path (str): The path where the file should be saved
            content: The content to save (string, bytes, or file-like object)
            content_type (str, optional): The content type of the file
            metadata (dict, optional): Additional metadata to store with the file
        """
        try:
            # Handle different content types
            if isinstance(content, str):
                content = content.encode('utf-8')
            elif isinstance(content, bytes):
                pass  # Already bytes
            elif hasattr(content, 'read'):
                # File-like object
                if hasattr(content, 'seek'):
                    content.seek(0)  # Reset file pointer
                content = content.read()
                if isinstance(content, str):
                    content = content.encode('utf-8')
            else:
                raise ValueError("Content must be string, bytes, or file-like object")

            # Clean the path (remove leading and trailing slashes)
            clean_path = path.strip('/')

            # Determine content type if not provided
            if not content_type:
                if clean_path.endswith('.html'):
                    content_type = 'text/html'
                elif clean_path.endswith('.json'):
                    content_type = 'application/json'
                elif clean_path.endswith('.csv'):
                    content_type = 'text/csv'
                elif clean_path.endswith('.txt'):
                    content_type = 'text/plain'
                else:
                    content_type = 'application/octet-stream'

            # Prepare metadata (excluding content-type which is set in headers)
            if metadata is None:
                metadata = {}
            
            # Convert metadata values to strings
            metadata = {k: str(v) for k, v in metadata.items()}

            logger.info(f"Saving file to {clean_path} with content type {content_type}")
            logger.info(f"Content length: {len(content)} bytes")

            response = self.client.put_object(
                Bucket=self.bucket,
                Key=clean_path,
                Body=content,
                ContentType=content_type,
                Metadata=metadata
            )
            
            logger.info(f"Successfully saved file to {clean_path}")
            return clean_path
            
        except ClientError as e:
            logger.error(f"Failed to save file {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving file {path}: {e}")
            raise

    def delete(self, path):
        """Delete the file at the specified path."""
        try:
            clean_path = path.lstrip('/')
            self.client.delete_object(
                Bucket=self.bucket,
                Key=clean_path
            )
            logger.info(f"Successfully deleted file {clean_path}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete file {path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting file {path}: {e}")
            return False

    def url(self, path):
        """Get the URL for the file at the specified path."""
        clean_path = path.lstrip('/')
        # Remove trailing slash from endpoint if present
        endpoint = self.disk_config['endpoint'].rstrip('/')
        return f"{endpoint}/{self.bucket}/{clean_path}"

    def exists(self, path):
        """Check if a file exists at the specified path."""
        try:
            clean_path = path.lstrip('/')
            self.client.head_object(
                Bucket=self.bucket,
                Key=clean_path
            )
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                return False
            else:
                logger.error(f"Error checking if file exists {path}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error checking file existence {path}: {e}")
            return False

    def get_file(self, path):
        """Get the file content from the specified path."""
        try:
            clean_path = path.lstrip('/')
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=clean_path
            )
            return response['Body'].read()
        except ClientError as e:
            logger.error(f"Failed to get file {path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting file {path}: {e}")
            return None
    
    def get_path_for_submission_file(self, cohort_id, cohort_name, protocol_year, file_type, filename):
        """Generate the storage path for a submission file.
        
        Args:
            cohort_id: ID of the cohort
            cohort_name: Name of the cohort
            protocol_year: Protocol year name
            file_type: Type of the file
            filename: Original filename
            
        Returns:
            Formatted path string
        """
        # Clean cohort name for filesystem
        clean_cohort = f"{cohort_id}_{cohort_name}".replace(' ', '_').replace('/', '_')
        clean_protocol = protocol_year.replace(' ', '_').replace('/', '_')
        clean_file_type = file_type.replace(' ', '_').replace('/', '_')
        
        # Build path: {cohort_id}_{cohort_name}/{protocol_year}/{file_type}/{filename}
        path = f"{clean_cohort}/{clean_protocol}/{clean_file_type}/{filename}"
        return path

    def debug_file(self, path):
        """Debug method to inspect what's stored at a path."""
        try:
            clean_path = path.strip('/')
            
            # Get object info
            response = self.client.head_object(Bucket=self.bucket, Key=clean_path)
            logger.info(f"Object info for {clean_path}:")
            logger.info(f"  Content-Type: {response.get('ContentType')}")
            logger.info(f"  Content-Length: {response.get('ContentLength')}")
            logger.info(f"  Metadata: {response.get('Metadata')}")
            
            # Get object content
            obj = self.client.get_object(Bucket=self.bucket, Key=clean_path)
            content = obj['Body'].read()
            logger.info(f"Content preview (first 200 bytes): {content[:200]}")
            
            return {
                'content_type': response.get('ContentType'),
                'content_length': response.get('ContentLength'),
                'metadata': response.get('Metadata'),
                'content_preview': content[:200]
            }
            
        except Exception as e:
            logger.error(f"Debug failed for {path}: {e}")
            return None
    
    def delete_prefix(self, prefix):
        """Delete all objects with the given prefix (directory-like deletion).
        
        Args:
            prefix: The prefix/directory to delete
            
        Returns:
            Number of objects deleted
        """
        if not self.client:
            logger.error("S3 client not initialized")
            return 0
            
        try:
            clean_prefix = prefix.strip('/')
            if clean_prefix:
                clean_prefix += '/'  # Ensure trailing slash for prefix
            
            deleted_count = 0
            paginator = self.client.get_paginator('list_objects_v2')
            
            # Collect all objects to delete
            objects_to_delete = []
            for page in paginator.paginate(Bucket=self.bucket, Prefix=clean_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete in batches of 1000 (S3 limit)
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i:i+1000]
                response = self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={
                        'Objects': batch,
                        'Quiet': True
                    }
                )
                deleted_count += len(batch)
                
                # Check for errors
                if 'Errors' in response:
                    for error in response['Errors']:
                        logger.error(f"Failed to delete {error['Key']}: {error['Message']}")
                        deleted_count -= 1
            
            logger.info(f"Deleted {deleted_count} objects with prefix '{clean_prefix}'")
            return deleted_count
            
        except ClientError as e:
            logger.error(f"Failed to delete prefix {prefix}: {e}")
            return 0
    
    def list_with_prefix(self, prefix, include_metadata=False):
        """List all objects under the given prefix with optional metadata.
        
        Args:
            prefix: The prefix to list under
            include_metadata: If True, return tuples of (path, mtime, size)
                            If False, return just paths
            
        Returns:
            List of paths or tuples depending on include_metadata
        """
        if not self.client:
            logger.error("S3 client not initialized")
            return []
            
        try:
            clean_prefix = prefix.strip('/')
            if clean_prefix:
                clean_prefix += '/'
            
            results = []
            paginator = self.client.get_paginator('list_objects_v2')
            
            for page in paginator.paginate(Bucket=self.bucket, Prefix=clean_prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if include_metadata:
                            # Convert LastModified to timestamp
                            mtime = obj['LastModified'].timestamp()
                            results.append((obj['Key'], mtime, obj['Size']))
                        else:
                            results.append(obj['Key'])
            
            return results
            
        except ClientError as e:
            logger.error(f"Failed to list prefix {prefix}: {e}")
            return []
    
    def ensure_prefix(self, prefix):
        """Ensure a prefix exists (no-op for S3, creates dir for filesystem).
        
        For S3, prefixes don't need to be created explicitly.
        This method exists for interface compatibility.
        
        Args:
            prefix: The prefix to ensure exists
        """
        # S3 doesn't require creating prefixes/directories
        # They exist implicitly when objects are created
        logger.debug(f"Prefix '{prefix}' will be created implicitly when objects are added")
        pass
    
    def touch(self, path):
        """Create an empty file (useful for lock files).
        
        Args:
            path: The path to create
            
        Returns:
            True if successful, False otherwise
        """
        try:
            clean_path = path.strip('/')
            self.client.put_object(
                Bucket=self.bucket,
                Key=clean_path,
                Body=b'',
                ContentType='application/octet-stream'
            )
            logger.debug(f"Created empty file at '{clean_path}'")
            return True
        except ClientError as e:
            logger.error(f"Failed to touch {path}: {e}")
            return False
    
    def get_metadata(self, path):
        """Get metadata for a file.
        
        Args:
            path: The path to get metadata for
            
        Returns:
            Dict with 'size', 'mtime', 'content_type' or None if not found
        """
        if not self.client:
            return None
            
        try:
            clean_path = path.strip('/')
            response = self.client.head_object(Bucket=self.bucket, Key=clean_path)
            
            return {
                'size': response.get('ContentLength', 0),
                'mtime': response.get('LastModified').timestamp() if response.get('LastModified') else None,
                'content_type': response.get('ContentType', 'application/octet-stream')
            }
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            logger.error(f"Failed to get metadata for {path}: {e}")
            return None
