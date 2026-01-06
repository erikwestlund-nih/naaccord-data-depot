"""
Remote Storage Driver for Web Server.
Forwards all storage operations to the services server via HTTP.
Never stores files locally on the web server.
"""
import os
import json
import logging
import requests
from io import BytesIO
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from depot.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class RemoteStorageDriver(BaseStorage):
    """
    Storage driver that forwards all operations to a remote services server.
    Used by the web server to ensure no files are stored locally.
    """
    
    # Chunk size for streaming uploads (64KB)
    CHUNK_SIZE = 64 * 1024
    
    def __init__(self, disk_name):
        """
        Initialize the remote storage driver.

        Args:
            disk_name: Name of the disk configuration
        """
        # Don't call parent __init__ as we don't need S3 client
        self.disk_config = self._get_disk_config(disk_name)
        self.disk_name = disk_name  # Store disk name to pass to remote API

        # Map local disk name to remote disk name
        # e.g., 'workspace_remote' -> 'workspace', 'scratch_remote' -> 'scratch'
        self.remote_disk_name = disk_name.replace('_remote', '')

        # Get services server configuration
        self.service_url = self.disk_config.get('service_url', 'http://localhost:8001')

        # Get API key from config, secret file, or environment variable
        self.api_key = self.disk_config.get('api_key')
        if not self.api_key:
            # Try to read from Docker secret file
            api_key_file = os.environ.get('INTERNAL_API_KEY_FILE')
            if api_key_file and os.path.exists(api_key_file):
                try:
                    with open(api_key_file, 'r') as f:
                        self.api_key = f.read().strip()
                except Exception as e:
                    logger.error(f"Failed to read INTERNAL_API_KEY from {api_key_file}: {e}")
            else:
                # Fall back to environment variable
                self.api_key = os.environ.get('INTERNAL_API_KEY')

        # Ensure service URL doesn't have trailing slash
        self.service_url = self.service_url.rstrip('/')

        # Setup session with connection pooling and retry logic
        self.session = self._create_session()

        logger.info(f"RemoteStorageDriver initialized for {self.service_url} (local disk: {disk_name}, remote disk: {self.remote_disk_name})")

    def _normalize_path(self, path: str | None) -> str:
        if not path:
            return ''

        clean = str(path).lstrip('/')
        prefix = f"{self.remote_disk_name}/"
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        return clean

    def _get_disk_config(self, disk_name):
        """Get disk configuration from settings."""
        from django.conf import settings
        
        if 'STORAGE_CONFIG' not in dir(settings):
            raise ValueError("STORAGE_CONFIG not found in Django settings")
        
        if disk_name not in settings.STORAGE_CONFIG['disks']:
            raise ValueError(f"Disk '{disk_name}' not found in STORAGE_CONFIG")
        
        return settings.STORAGE_CONFIG['disks'][disk_name]
    
    def _create_session(self):
        """
        Create a requests session with connection pooling and retry logic.
        
        Returns:
            Configured requests Session
        """
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=retry_strategy
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set default headers
        session.headers.update({
            'X-API-Key': self.api_key,
            'User-Agent': 'RemoteStorageDriver/1.0'
        })
        
        return session
    
    def save(self, path, content, content_type=None, metadata=None):
        """
        Stream file to services server without storing locally.
        Optimized for Django's TemporaryUploadedFile.

        Args:
            path: Storage path for the file
            content: File content (bytes, string, or file-like object)
            content_type: MIME type of the content
            metadata: Additional metadata dict

        Returns:
            Path where file was saved
        """
        try:
            # Initialize metadata if not provided
            if metadata is None:
                metadata = {}

            # Calculate file hash for integrity tracking
            # This is critical for PHI file tracking and auditing
            import hashlib

            # Get content as bytes for hashing
            if hasattr(content, 'read'):
                # File-like object - read, hash, and reset
                if hasattr(content, 'seek'):
                    content.seek(0)
                content_bytes = content.read()
                if hasattr(content, 'seek'):
                    content.seek(0)  # Reset for upload
                file_hash = hashlib.sha256(content_bytes).hexdigest()
                file_size = len(content_bytes)
            elif isinstance(content, bytes):
                file_hash = hashlib.sha256(content).hexdigest()
                file_size = len(content)
            elif isinstance(content, str):
                content_bytes = content.encode('utf-8')
                file_hash = hashlib.sha256(content_bytes).hexdigest()
                file_size = len(content_bytes)
            else:
                file_hash = ''
                file_size = 0
                logger.warning(f"Unable to calculate hash for content type: {type(content)}")

            # Add hash to metadata for PHI tracking
            metadata['file_hash'] = file_hash
            metadata['file_size'] = file_size
            logger.info(f"Calculated file hash: {file_hash[:16]}... (size: {file_size} bytes)")

            # Check if this is a Django TemporaryUploadedFile (large file on disk)
            # These files are > 2.5MB and Django saves them to /tmp
            if hasattr(content, 'temporary_file_path'):
                # This is a TemporaryUploadedFile - stream from disk
                logger.info(f"Detected TemporaryUploadedFile, using chunked upload for optimal streaming")

                # For large files on disk, use chunked upload
                # This avoids loading the entire file into memory
                if hasattr(content, 'size') and content.size > 10 * 1024 * 1024:  # > 10MB
                    return self.save_chunked(path, content, content_type, metadata)

            # For smaller files or in-memory files, use regular upload
            # Prepare the upload URL
            url = urljoin(self.service_url, '/internal/storage/upload')

            # Prepare form data
            normalized_path = self._normalize_path(path)
            data = {
                'path': normalized_path,
                'content_type': content_type or 'application/octet-stream',
                'disk': self.remote_disk_name,  # Tell services server which disk to use
            }

            if metadata:
                data['metadata'] = json.dumps(metadata)

            # Handle different content types
            if hasattr(content, 'read'):
                # File-like object - stream it
                # For Django uploaded files, ensure we're at the start
                if hasattr(content, 'seek'):
                    content.seek(0)
                files = {'file': ('file', content, content_type)}
            elif isinstance(content, bytes):
                # Bytes - wrap in BytesIO
                files = {'file': ('file', BytesIO(content), content_type)}
            elif isinstance(content, str):
                # String - encode and wrap
                files = {'file': ('file', BytesIO(content.encode('utf-8')), content_type)}
            else:
                raise ValueError(f"Unsupported content type: {type(content)}")

            # Stream upload to services server
            # Note: requests will stream file-like objects automatically
            response = self.session.post(
                url,
                data=data,
                files=files,
                timeout=300  # 5 minute timeout for large files
            )

            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage upload failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote upload failed ({response.status_code}): {error_message}"
                )

            result = response.json()
            saved_path = result.get('path', normalized_path)

            logger.info(f"Successfully saved file to services server: {saved_path}")
            return saved_path

        except requests.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                logger.error(
                    "Failed to save file to services server (%s): %s",
                    e.response.status_code,
                    e.response.text
                )
            else:
                logger.error(f"Failed to save file to services server: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving file: {e}")
            raise
    
    def save_chunked(self, path, file_obj, content_type=None, metadata=None):
        """
        Stream large file to services server in chunks.
        Optimized for Django's TemporaryUploadedFile to avoid memory issues.

        Args:
            path: Storage path for the file
            file_obj: File-like object to stream
            content_type: MIME type of the content
            metadata: Additional metadata dict

        Returns:
            Path where file was saved
        """
        try:
            # Initialize metadata if not provided
            if metadata is None:
                metadata = {}

            # Calculate file hash while streaming to avoid loading entire file into memory
            import hashlib
            hasher = hashlib.sha256()

            url = urljoin(self.service_url, '/internal/storage/upload_chunked')

            # For TemporaryUploadedFile, open the actual file for streaming
            if hasattr(file_obj, 'temporary_file_path'):
                # Open the temp file directly for optimal streaming
                temp_path = file_obj.temporary_file_path()
                logger.info(f"Streaming from temporary file: {temp_path}")

                # Calculate hash by reading the file in chunks
                with open(temp_path, 'rb') as hash_file:
                    while True:
                        chunk = hash_file.read(8192)
                        if not chunk:
                            break
                        hasher.update(chunk)

                file_handle = open(temp_path, 'rb')
                file_size = file_obj.size
            else:
                # Regular file object
                file_handle = file_obj
                file_size = file_obj.size if hasattr(file_obj, 'size') else None
                if hasattr(file_handle, 'seek'):
                    file_handle.seek(0)

                # Calculate hash for regular file objects
                while True:
                    chunk = file_handle.read(8192)
                    if not chunk:
                        break
                    hasher.update(chunk)

                # Reset file position for upload
                if hasattr(file_handle, 'seek'):
                    file_handle.seek(0)

            file_hash = hasher.hexdigest()
            metadata['file_hash'] = file_hash
            metadata['file_size'] = file_size
            logger.info(f"Calculated chunked file hash: {file_hash[:16]}... (size: {file_size} bytes)")

            normalized_path = self._normalize_path(path)

            try:
                # Initialize upload
                init_data = {
                    'path': normalized_path,
                    'content_type': content_type or 'application/octet-stream',
                    'action': 'init',
                    'disk': self.remote_disk_name
                }

                if metadata:
                    init_data['metadata'] = json.dumps(metadata)

                init_response = self.session.post(url, data=init_data)
                init_response.raise_for_status()

                upload_id = init_response.json()['upload_id']

                # Use very large chunks to minimize database connections (50MB)
                LARGE_CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks for minimal database load

                # Stream file in chunks
                chunk_num = 0
                bytes_uploaded = 0
                while True:
                    chunk = file_handle.read(LARGE_CHUNK_SIZE)
                    if not chunk:
                        break

                    chunk_data = {
                        'upload_id': upload_id,
                        'chunk_num': chunk_num,
                        'action': 'chunk',
                        'disk': self.remote_disk_name
                    }

                    files = {'chunk': ('chunk', BytesIO(chunk), 'application/octet-stream')}

                    chunk_response = self.session.post(
                        url,
                        data=chunk_data,
                        files=files
                    )
                    if chunk_response.status_code >= 400:
                        error_message = chunk_response.text.strip()
                        logger.error(
                            "Remote chunk upload failed (%s): %s",
                            chunk_response.status_code,
                            error_message
                        )
                        raise RuntimeError(
                            f"Remote chunk upload failed ({chunk_response.status_code}): {error_message}"
                        )

                    chunk_num += 1
                    bytes_uploaded += len(chunk)

                    # Add small delay between chunks to prevent database connection stampede
                    # Only delay if there are more chunks to process
                    if file_size and bytes_uploaded < file_size:
                        import time
                        time.sleep(0.1)  # 100ms delay to throttle database connections

                    # Log progress for each chunk with 50MB chunks
                    if file_size:
                        percent = (bytes_uploaded / file_size) * 100
                        logger.info(f"Upload progress: {percent:.1f}% ({bytes_uploaded / 1024 / 1024:.1f}MB of {file_size / 1024 / 1024:.1f}MB) - chunk {chunk_num}")

                # Complete upload
                complete_data = {
                    'upload_id': upload_id,
                    'action': 'complete',
                    'total_chunks': chunk_num,
                    'disk': self.remote_disk_name
                }

                complete_response = self.session.post(url, data=complete_data)
                if complete_response.status_code >= 400:
                    error_message = complete_response.text.strip()
                    logger.error(
                        "Remote chunk completion failed (%s): %s",
                        complete_response.status_code,
                        error_message
                    )
                    raise RuntimeError(
                        f"Remote chunk completion failed ({complete_response.status_code}): {error_message}"
                    )

                result = complete_response.json()
                saved_path = result.get('path', normalized_path)

                logger.info(f"Successfully uploaded {chunk_num} chunks ({bytes_uploaded / 1024 / 1024:.1f}MB) to services server: {saved_path}")
                return saved_path

            finally:
                # Clean up file handle if we opened it
                if hasattr(file_obj, 'temporary_file_path'):
                    file_handle.close()

        except requests.RequestException as e:
            logger.error(f"Failed to upload chunked file: {e}")
            raise
    
    def get_file(self, path):
        """
        Stream file from services server.
        
        Args:
            path: Storage path of the file
            
        Returns:
            File content as bytes or None if not found
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/download')

            normalized_path = self._normalize_path(path)

            response = self.session.get(
                url,
                params={'path': normalized_path, 'disk': self.remote_disk_name},
                stream=True,
                timeout=300
            )
            
            if response.status_code == 404:
                return None
            
            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage delete failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote delete failed ({response.status_code}): {error_message}"
                )
            
            # Stream content into memory
            # For very large files, consider returning a generator
            content = b''
            for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                if chunk:
                    content += chunk
            
            logger.debug(f"Retrieved file from services server: {path}")
            return content
            
        except requests.RequestException as e:
            logger.error(f"Failed to get file from services server: {e}")
            return None
    
    def delete(self, path):
        """
        Delete file on services server.

        Args:
            path: Storage path of the file to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/delete')

            normalized_path = self._normalize_path(path)

            response = self.session.post(
                url,
                json={
                    'path': normalized_path,
                    'disk': self.remote_disk_name
                }
            )
            
            if response.status_code == 404:
                logger.debug(f"File not found for deletion: {path}")
                return True  # Already gone
            
            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage delete_prefix failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote delete_prefix failed ({response.status_code}): {error_message}"
                )
            
            result = response.json()
            success = result.get('success', False)
            
            if success:
                logger.info(f"Successfully deleted file on services server: {path}")
            else:
                logger.warning(f"Failed to delete file on services server: {path}")
            
            return success
            
        except requests.RequestException as e:
            logger.error(f"Failed to delete file on services server: {e}")
            return False
    
    def delete_prefix(self, prefix):
        """
        Delete all files with given prefix on services server.
        
        Args:
            prefix: The prefix/directory to delete
            
        Returns:
            Number of objects deleted
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/delete_prefix')

            normalized_prefix = self._normalize_path(prefix)

            response = self.session.post(
                url,
                json={'prefix': normalized_prefix}
            )
            
            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage list failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote list failed ({response.status_code}): {error_message}"
                )
            
            result = response.json()
            deleted_count = result.get('deleted_count', 0)
            
            logger.info(f"Deleted {deleted_count} files with prefix '{prefix}' on services server")
            return deleted_count
            
        except requests.RequestException as e:
            logger.error(f"Failed to delete prefix on services server: {e}")
            return 0
    
    def list_with_prefix(self, prefix, include_metadata=False):
        """
        List files with given prefix from services server.
        
        Args:
            prefix: The prefix to list under
            include_metadata: If True, return tuples of (path, mtime, size)
            
        Returns:
            List of paths or tuples depending on include_metadata
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/list')

            normalized_prefix = self._normalize_path(prefix)

            response = self.session.get(
                url,
                params={
                    'prefix': normalized_prefix,
                    'include_metadata': include_metadata
                }
            )
            
            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage exists failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote exists failed ({response.status_code}): {error_message}"
                )
            
            result = response.json()
            files = result.get('files', [])
            
            if include_metadata:
                # Convert list of dicts to tuples
                return [(f['path'], f['mtime'], f['size']) for f in files]
            else:
                return files
            
        except requests.RequestException as e:
            logger.error(f"Failed to list files from services server: {e}")
            return []
    
    def exists(self, path):
        """
        Check if file exists on services server.
        
        Args:
            path: Storage path to check
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/exists')

            normalized_path = self._normalize_path(path)

            response = self.session.get(
                url,
                params={'path': normalized_path, 'disk': self.remote_disk_name}
            )
            
            if response.status_code >= 400:
                error_message = response.text.strip()
                logger.error(
                    "Remote storage metadata failed (%s): %s",
                    response.status_code,
                    error_message
                )
                raise RuntimeError(
                    f"Remote metadata failed ({response.status_code}): {error_message}"
                )
            
            result = response.json()
            return result.get('exists', False)
            
        except requests.RequestException as e:
            logger.error(f"Failed to check file existence on services server: {e}")
            return False
    
    def get_metadata(self, path):
        """
        Get file metadata from services server.
        
        Args:
            path: Storage path
            
        Returns:
            Dict with 'size', 'mtime', 'content_type' or None if not found
        """
        try:
            url = urljoin(self.service_url, '/internal/storage/metadata')

            normalized_path = self._normalize_path(path)

            response = self.session.get(
                url,
                params={'path': normalized_path}
            )
            
            if response.status_code == 404:
                return None
            
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            logger.error(f"Failed to get metadata from services server: {e}")
            return None
    
    def ensure_prefix(self, prefix):
        """
        Ensure prefix exists on services server (no-op for most cases).
        
        Args:
            prefix: The prefix to ensure exists
        """
        # For remote storage, prefixes are created implicitly
        logger.debug(f"Prefix '{prefix}' will be created on services server when needed")
    
    def touch(self, path):
        """
        Create empty file on services server.
        
        Args:
            path: Storage path to create
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.save(path, b'', content_type='application/octet-stream')
            return True
        except Exception as e:
            logger.error(f"Failed to touch file on services server: {e}")
            return False
    
    def url(self, path):
        """
        Get URL for accessing file (not directly accessible from web server).

        Args:
            path: Storage path

        Returns:
            Internal URL string
        """
        # Files are not directly accessible from web server
        # This returns an internal reference URL
        return f"remote://{path}"

    def get_absolute_path(self, relative_path):
        """
        For remote storage, we can't determine the absolute path on the services server.
        We return a pseudo-absolute path indicating it's remote.

        Args:
            relative_path: Relative path within storage

        Returns:
            Pseudo-absolute path indicating remote location
        """
        # For remote storage, we can't know the actual absolute path on services server
        # Return a remote reference that indicates the disk and path
        return f"remote://{self.remote_disk_name}/{relative_path}"
    
    def get_path_for_submission_file(self, cohort_id, cohort_name, protocol_year, file_type, filename):
        """
        Generate the storage path for a submission file.
        
        Args:
            cohort_id: ID of the cohort
            cohort_name: Name of the cohort
            protocol_year: Protocol year name
            file_type: Type of the file
            filename: Original filename
            
        Returns:
            Formatted path string
        """
        # Clean names for storage
        clean_cohort = f"{cohort_id}_{cohort_name}".replace(' ', '_').replace('/', '_')
        clean_protocol = protocol_year.replace(' ', '_').replace('/', '_')
        clean_file_type = file_type.replace(' ', '_').replace('/', '_')
        
        # Build path
        path = f"{clean_cohort}/{clean_protocol}/{clean_file_type}/{filename}"
        return path
