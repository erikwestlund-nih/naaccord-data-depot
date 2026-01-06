import os
import shutil
import logging
from pathlib import Path
from typing import BinaryIO, Optional
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from depot.storage.base import BaseStorage

logger = logging.getLogger(__name__)


class LocalFileSystemStorage(BaseStorage):
    """
    Local filesystem storage driver for development.
    Stores files in a local directory structure.
    """

    def __init__(self, disk_name='local'):
        """
        Initialize local storage driver.

        Args:
            disk_name: Name of the disk configuration
        """
        super().__init__(disk_name)

        # Set base path from config or use default
        if 'root' in self.disk_config:
            self.base_path = Path(self.disk_config['root'])
        else:
            self.base_path = Path(settings.MEDIA_ROOT) / 'submissions'

        # Create base directory if it doesn't exist
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initialized storage directory: {self.base_path}")
        except FileExistsError as e:
            # This can happen if a file (not directory) exists at this path
            logger.error(f"Cannot create directory {self.base_path}: a file exists at this location")
            raise
        except PermissionError as e:
            logger.error(f"Permission denied creating directory {self.base_path}: {e}")
            raise
        except OSError as e:
            # Catch other OS errors like "Device or resource busy", stale NFS handles, etc.
            logger.error(f"OS error creating directory {self.base_path}: {e}")
            raise

        # Resolve base_path once for security checks
        self.base_path_resolved = self.base_path.resolve()

    def _normalize_for_disk(self, path: str | os.PathLike | None) -> str:
        """Normalize an incoming storage path so it can be resolved on disk."""
        if path is None:
            return ''

        if isinstance(path, Path):
            path = str(path)

        normalized = path.lstrip('/')
        prefix = f"{self.disk_name}/"

        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]

        return normalized

    def _validate_path(self, path):
        """
        Validate that a path stays within base_path boundaries.

        Args:
            path: Relative path to validate

        Returns:
            Resolved Path object

        Raises:
            ValueError: If path attempts to escape base_path
        """
        # Convert to string if Path object
        if isinstance(path, Path):
            path = str(path)

        # Handle absolute paths
        if path.startswith('/'):
            # Absolute paths are only allowed if they're within base_path
            abs_path = Path(path).resolve()
            try:
                abs_path.relative_to(self.base_path_resolved)
                # It's within base_path, return it
                return abs_path
            except ValueError:
                # It's outside base_path, block it
                logger.error(f"Absolute path outside storage root blocked: {path}")
                raise ValueError(f"Invalid path: {path} attempts to escape storage root")

        normalized_path = self._normalize_for_disk(path)

        target_base = self.base_path
        target = target_base if not normalized_path else target_base / normalized_path

        # Construct full path and resolve it (this handles .. and symlinks)
        full_path = target.resolve()

        # Check that resolved path is still under base_path
        try:
            full_path.relative_to(self.base_path_resolved)
        except ValueError:
            logger.error(f"Path traversal attempt detected: {path}")
            raise ValueError(f"Invalid path: {path} attempts to escape storage root")

        return full_path
    
    def save(self, path, content, content_type=None, metadata=None):
        """
        Save content to local filesystem.

        Args:
            path: Relative path for the file
            content: File content (bytes, string, or file-like object)
            content_type: MIME type (stored as metadata)
            metadata: Additional metadata (stored as .meta file)

        Returns:
            URL to access the file

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)

        # Create parent directories if needed
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create parent directory {full_path.parent}: {e}")
            raise

        # Handle different content types
        if isinstance(content, str):
            content = content.encode('utf-8')
            # Write string content directly
            with open(full_path, 'wb') as f:
                f.write(content)
        elif hasattr(content, 'temporary_file_path'):
            # IT'S A TEMPORARY UPLOADED FILE - just MOVE it, don't copy!
            import shutil
            temp_path = content.temporary_file_path()

            # Just move the file - this is INSTANT
            shutil.move(temp_path, full_path)

            logger.info(f"MOVED TemporaryUploadedFile from {temp_path} to {full_path} (instant)")
        elif hasattr(content, 'read'):
            # Stream file-like objects instead of loading into memory
            if hasattr(content, 'seek'):
                content.seek(0)

            # Stream in chunks to avoid loading large files into memory
            with open(full_path, 'wb') as f:
                if hasattr(content, 'chunks'):
                    # Django uploaded file with chunks method
                    for chunk in content.chunks():
                        f.write(chunk)
                else:
                    # Regular file-like object
                    while True:
                        chunk = content.read(65536)  # 64KB chunks
                        if not chunk:
                            break
                        if isinstance(chunk, str):
                            chunk = chunk.encode('utf-8')
                        f.write(chunk)
        else:
            # Direct bytes
            with open(full_path, 'wb') as f:
                f.write(content)
        
        # Save metadata if provided (always save for integrity tracking)
        if metadata or content_type or True:  # Always create .meta files
            import json
            import hashlib
            from datetime import datetime

            meta_path = full_path.with_suffix(full_path.suffix + '.meta')
            meta_data = metadata or {}

            # Add content type
            if content_type:
                meta_data['content_type'] = content_type

            # Calculate file hash for integrity verification (SHA256 only)
            if isinstance(content, bytes):
                content_for_hash = content
            else:
                content_for_hash = content.encode('utf-8') if isinstance(content, str) else str(content).encode('utf-8')

            file_hash = hashlib.sha256(content_for_hash).hexdigest()

            # Add integrity information
            meta_data['file_size'] = len(content_for_hash)
            meta_data['sha256'] = file_hash
            meta_data['created_at'] = datetime.utcnow().isoformat()
            meta_data['storage_driver'] = 'local'

            with open(meta_path, 'w') as f:
                json.dump(meta_data, f, indent=2)

        # Create PHI tracking if metadata contains PHI tracking parameters
        if metadata and 'cohort_id' in metadata and 'user_id' in metadata:
            self._create_phi_tracking_from_metadata(str(full_path), metadata)

        # Return the relative path, not the URL
        return path

    def _create_phi_tracking_from_metadata(self, absolute_path, metadata):
        """
        Create PHI tracking record from metadata.

        This is called when LocalFileSystemStorage is used directly (not via RemoteStorageDriver).
        In the two-server architecture, PHI tracking is created on the services server.

        Args:
            absolute_path: Absolute filesystem path where file was saved
            metadata: Metadata dict containing cohort_id, user_id, file_type, etc.
        """
        try:
            from depot.models import PHIFileTracking, Cohort
            from django.contrib.auth import get_user_model
            from django.contrib.contenttypes.models import ContentType
            from django.utils import timezone
            from datetime import timedelta

            User = get_user_model()

            # Get cohort and user
            cohort_id = metadata.get('cohort_id')
            user_id = metadata.get('user_id')

            if not cohort_id or not user_id:
                return

            cohort = Cohort.objects.get(id=cohort_id)
            user = User.objects.get(id=user_id)

            # Determine action based on purpose
            purpose = metadata.get('purpose', 'upload')
            if purpose == 'precheck_run':
                action = 'file_uploaded_via_stream'
            else:
                action = 'nas_raw_created'

            # Get content object if provided
            content_object = None
            if metadata.get('content_object_id') and metadata.get('content_type_id'):
                content_type = ContentType.objects.get(id=metadata['content_type_id'])
                content_object = content_type.get_object_for_this_type(id=metadata['content_object_id'])

            # Parse expected cleanup time
            expected_cleanup_by = None
            if metadata.get('expected_cleanup_by'):
                from dateutil import parser as date_parser
                expected_cleanup_by = date_parser.isoparse(metadata['expected_cleanup_by'])

            # Create PHI tracking record
            tracking_record = PHIFileTracking.log_operation(
                cohort=cohort,
                user=user,
                action=action,
                file_path=absolute_path,
                file_type=metadata.get('file_type', 'raw_csv'),
                file_size=Path(absolute_path).stat().st_size if Path(absolute_path).exists() else None,
                content_object=content_object,
                metadata={
                    'relative_path': metadata.get('relative_path', ''),
                    'original_filename': metadata.get('original_filename', ''),
                    'file_hash': metadata.get('file_hash', '')
                }
            )

            # Set additional fields not in log_operation signature
            tracking_record.cleanup_required = True
            tracking_record.expected_cleanup_by = expected_cleanup_by
            tracking_record.save(update_fields=['cleanup_required', 'expected_cleanup_by'])

            logger.debug(f"Created PHI tracking for {absolute_path}")

        except Exception as e:
            logger.error(f"Failed to create PHI tracking from metadata: {e}", exc_info=True)

    def get_absolute_path(self, relative_path):
        """
        Get the absolute filesystem path for a relative storage path.

        Args:
            relative_path: Relative path within storage

        Returns:
            Absolute path as string
        """
        full_path = self._validate_path(relative_path)
        return str(full_path)
    
    def get_file(self, path):
        """
        Read file content from local filesystem.

        Args:
            path: Relative path to the file

        Returns:
            File content as bytes or None if not found

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)

        if not full_path.exists():
            return None

        with open(full_path, 'rb') as f:
            return f.read()
    
    def delete(self, path):
        """
        Delete a file from local filesystem.

        Args:
            path: Relative path to the file

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)

        try:
            if full_path.exists():
                full_path.unlink()

                # Also remove metadata file if it exists
                meta_path = full_path.with_suffix(full_path.suffix + '.meta')
                if meta_path.exists():
                    meta_path.unlink()

                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")
            return False
    
    def exists(self, path):
        """
        Check if a file exists.

        Args:
            path: Relative path to check

        Returns:
            True if file exists, False otherwise

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)
        return full_path.exists()
    
    def url(self, path):
        """
        Get URL for accessing the file.
        
        Args:
            path: Relative path to the file
            
        Returns:
            URL string (for local storage, returns file:// URL)
        """
        # For local development, return a relative URL
        # This would be served by Django's static file handler
        return f"/media/submissions/{path}"
    
    def get_size(self, path):
        """
        Get file size in bytes.

        Args:
            path: Relative path to the file

        Returns:
            Size in bytes or 0 if file doesn't exist

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)

        if full_path.exists():
            return full_path.stat().st_size
        return 0
    
    def list_files(self, prefix=''):
        """
        List all files with given prefix.

        Args:
            prefix: Path prefix to filter files

        Returns:
            List of relative file paths

        Raises:
            ValueError: If prefix attempts to escape storage root
        """
        search_path = self._validate_path(prefix) if prefix else self.base_path

        if not search_path.exists():
            return []

        files = []
        for item in search_path.rglob('*'):
            if item.is_file() and not item.name.endswith('.meta'):
                relative_path = item.relative_to(self.base_path)
                files.append(str(relative_path))

        return files
    
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
        # Clean names for filesystem
        clean_cohort = f"{cohort_id}_{cohort_name}".replace(' ', '_').replace('/', '_')
        clean_protocol = protocol_year.replace(' ', '_').replace('/', '_')
        clean_file_type = file_type.replace(' ', '_').replace('/', '_')
        
        # Build path: {cohort_id}_{cohort_name}/{protocol_year}/{file_type}/{filename}
        path = f"{clean_cohort}/{clean_protocol}/{clean_file_type}/{filename}"
        return path
    
    def delete_prefix(self, prefix):
        """Delete all files under the given prefix (directory).

        Args:
            prefix: The prefix/directory to delete

        Returns:
            Number of files deleted

        Raises:
            ValueError: If prefix attempts to escape storage root
        """
        full_path = self._validate_path(prefix)

        if not full_path.exists():
            logger.debug(f"Path {full_path} does not exist, nothing to delete")
            return 0

        deleted_count = 0
        try:
            if full_path.is_dir():
                # Count files before deletion (excluding .meta files)
                for item in full_path.rglob('*'):
                    if item.is_file() and not item.name.endswith('.meta'):
                        deleted_count += 1

                # Remove the directory and all contents
                shutil.rmtree(full_path)
                logger.info(f"Deleted {deleted_count} files from {full_path}")
            elif full_path.is_file():
                full_path.unlink()
                deleted_count = 1
                logger.info(f"Deleted file {full_path}")

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete prefix {prefix}: {e}")
            return 0
    
    def list_with_prefix(self, prefix, include_metadata=False):
        """List all files under the given prefix with optional metadata.

        Args:
            prefix: The prefix to list under
            include_metadata: If True, return tuples of (path, mtime, size)
                            If False, return just paths

        Returns:
            List of paths or tuples depending on include_metadata

        Raises:
            ValueError: If prefix attempts to escape storage root
        """
        full_path = self._validate_path(prefix)

        if not full_path.exists():
            return []

        results = []
        try:
            # If it's a file, return just that file
            if full_path.is_file():
                relative_path = str(full_path.relative_to(self.base_path))
                if include_metadata:
                    stat = full_path.stat()
                    results.append((relative_path, stat.st_mtime, stat.st_size))
                else:
                    results.append(relative_path)
            # If it's a directory, list all files recursively
            elif full_path.is_dir():
                for item in full_path.rglob('*'):
                    if item.is_file():
                        relative_path = str(item.relative_to(self.base_path))
                        if include_metadata:
                            stat = item.stat()
                            results.append((relative_path, stat.st_mtime, stat.st_size))
                        else:
                            results.append(relative_path)

            return results

        except Exception as e:
            logger.error(f"Failed to list prefix {prefix}: {e}")
            return []
    
    def ensure_prefix(self, prefix):
        """Ensure a directory exists.

        Args:
            prefix: The directory path to ensure exists

        Raises:
            ValueError: If prefix attempts to escape storage root
        """
        full_path = self._validate_path(prefix)
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {full_path}")
        except Exception as e:
            logger.error(f"Failed to create directory {prefix}: {e}")
    
    def touch(self, path):
        """Create an empty file (useful for lock files).

        Args:
            path: The path to create

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)
        try:
            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)
            # Create empty file
            full_path.touch()
            logger.debug(f"Created empty file at {full_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to touch {path}: {e}")
            return False
    
    def get_metadata(self, path):
        """Get metadata for a file.

        Args:
            path: The path to get metadata for

        Returns:
            Dict with 'size', 'mtime', 'content_type' or None if not found

        Raises:
            ValueError: If path attempts to escape storage root
        """
        full_path = self._validate_path(path)

        if not full_path.exists():
            return None

        try:
            stat = full_path.stat()

            # Try to read content type from .meta file if it exists
            meta_path = full_path.with_suffix(full_path.suffix + '.meta')
            content_type = 'application/octet-stream'
            if meta_path.exists():
                import json
                with open(meta_path, 'r') as f:
                    meta_data = json.load(f)
                    content_type = meta_data.get('content_type', content_type)

            return {
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'content_type': content_type
            }
        except Exception as e:
            logger.error(f"Failed to get metadata for {path}: {e}")
            return None

    def verify_integrity(self, path, hash_type='sha256'):
        """Verify file integrity using stored hash in .meta file.

        Args:
            path: The path to verify
            hash_type: Hash algorithm to use (only 'sha256' is supported)

        Returns:
            Dict with verification results:
            {
                'valid': bool,
                'file_hash': str,
                'stored_hash': str,
                'file_size': int,
                'stored_size': int,
                'message': str
            }

        Raises:
            ValueError: If path attempts to escape storage root
            FileNotFoundError: If file or .meta file doesn't exist
        """
        import hashlib
        import json

        full_path = self._validate_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        meta_path = full_path.with_suffix(full_path.suffix + '.meta')
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {path}.meta")

        try:
            # Read metadata
            with open(meta_path, 'r') as f:
                meta_data = json.load(f)

            # Only look for 'sha256' key (standardized)
            stored_hash = meta_data.get('sha256')
            stored_size = meta_data.get('file_size')

            if not stored_hash:
                return {
                    'valid': False,
                    'message': 'No sha256 hash found in metadata',
                    'file_hash': None,
                    'stored_hash': None,
                    'file_size': None,
                    'stored_size': stored_size
                }

            # Calculate current file hash (SHA256 only)
            if hash_type == 'sha256':
                hasher = hashlib.sha256()
            else:
                raise ValueError(f"Unsupported hash type: {hash_type}. Only SHA256 is supported.")

            with open(full_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)

            file_hash = hasher.hexdigest()
            file_size = full_path.stat().st_size

            # Verify hash and size
            hash_valid = file_hash == stored_hash
            size_valid = file_size == stored_size if stored_size else True

            return {
                'valid': hash_valid and size_valid,
                'file_hash': file_hash,
                'stored_hash': stored_hash,
                'file_size': file_size,
                'stored_size': stored_size,
                'hash_match': hash_valid,
                'size_match': size_valid,
                'message': 'Integrity verified' if (hash_valid and size_valid) else 'Integrity check failed'
            }

        except Exception as e:
            logger.error(f"Failed to verify integrity for {path}: {e}")
            raise
