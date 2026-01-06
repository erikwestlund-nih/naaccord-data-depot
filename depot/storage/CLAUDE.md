# Storage Domain - CLAUDE.md

## Domain Overview

The storage domain provides sophisticated multi-driver abstraction for file operations across NA-ACCORD's two-server architecture. This system enables seamless switching between local filesystem, S3-compatible storage, and remote server communication while maintaining security boundaries and PHI compliance.

## Known Issues and Solutions

### Corrupted Directory Entries (Stale NFS/Docker Volumes)

**Symptom**: `[Errno 17] File exists` errors when trying to create storage directories, even though `mkdir(parents=True, exist_ok=True)` is used correctly.

**Root Cause**: Directories can appear in `ls` output as `d??????????` (permission denied/inaccessible), indicating stale NFS handles or corrupted Docker volume state. This prevents Python from determining if they're actual directories, causing `mkdir` to fail.

**Solution**: Restart the container to clear stale directory entries:
```bash
docker restart naaccord-test-services
# or for production:
docker restart naaccord-prod-services
```

**Prevention**: The `LocalFileSystemStorage` class now includes comprehensive error handling and logging:
- Logs successful directory creation
- Provides specific error messages for FileExistsError, PermissionError, and OSError
- Helps diagnose issues like stale NFS handles, device busy errors, etc.

**Code Location**: `depot/storage/local.py:37-50` (base directory) and `depot/storage/local.py:137-141` (parent directories)

## Core Architecture

### StorageManager System

**Location**: `depot/storage/manager.py`

```
StorageManager (manager.py)
├── BaseStorage (base.py) - Abstract interface
├── LocalFileSystemStorage (local.py) - Local disk operations
├── RemoteStorageDriver (remote.py) - Web→Services communication
└── S3Storage (s3.py) - S3-compatible cloud storage
```

### Multi-Driver Architecture

The StorageManager dynamically selects appropriate storage drivers based on:
- **Server role** (web/services/testing)
- **Storage type** (submission/scratch/general)
- **Configuration** (local/S3/remote)

```python
# Automatic driver selection
storage = StorageManager.get_scratch_storage()
# Returns appropriate driver based on server role and configuration
```

## Server-Role Based Storage Selection

### Web Server (SERVER_ROLE=web)

**Scratch Storage**: Always uses RemoteStorageDriver
- Streams all temporary files to services server
- Never stores PHI locally on web server
- Maintains security boundary for HIPAA compliance

```python
# Web server configuration (automatic)
def get_scratch_storage():
    if get_server_role() == 'web':
        return RemoteStorageDriver()  # Stream to services
    else:
        return get_configured_storage()  # Local or S3
```

### Services Server (SERVER_ROLE=services)

**All Storage**: Uses configured local or S3 storage
- Handles actual file storage operations
- Processes all temporary files from web server
- Manages conversion to DuckDB and report generation

```python
# Services server uses real storage backend
storage = StorageManager.get_scratch_storage()
# Returns: LocalFileSystemStorage or S3Storage
```

### Testing Environment (SERVER_ROLE=testing)

**All Storage**: Uses local filesystem
- Single-machine testing with local storage
- Simulates production behavior without complexity

## Storage Types and Use Cases

### 1. Submission Storage

**Purpose**: Permanent storage for cohort submission files
**Access**: `StorageManager.get_submission_storage()`

```python
# Save cohort submission file
storage = StorageManager.get_submission_storage()
path = StorageManager.save_submission_file(submission_file, content)

# Generate signed URL for access
url = StorageManager.get_submission_file_url(submission_file, expires_in=3600)
```

**Features**:
- Automatic path generation based on cohort/protocol/file type
- Metadata storage with submission details
- Signed URL generation for secure access
- Version tracking support

**Path Structure**:
```
submissions/{cohort_name}/{protocol_year}/{file_type}/{filename}
Example: submissions/VACS/2024/patient/patient_data_v2.csv
```

### 2. Scratch Storage

**Purpose**: Temporary processing files requiring cleanup
**Access**: `StorageManager.get_scratch_storage()`

```python
# Get appropriate scratch storage (role-dependent)
storage = StorageManager.get_scratch_storage()

# Automatically streams to services server if on web server
temp_path = storage.save('temp/audit_123/data.csv', content)
```

**Features**:
- Automatic server role detection
- Remote streaming for web server
- Integration with PHIFileTracking
- Automatic cleanup scheduling

### 3. General Storage

**Purpose**: Generic file storage with configurable drivers
**Access**: `StorageManager.get_storage(disk_name)`

```python
# Get specific storage disk
nas_storage = StorageManager.get_storage('nas_s3')
local_storage = StorageManager.get_storage('local')
```

## Configuration System

### Settings Structure

```python
# settings.py storage configuration
STORAGE_CONFIG = {
    'disks': {
        'local': {
            'driver': 'local',
            'root': '/app/storage'
        },
        'nas_s3': {
            'driver': 's3',
            'bucket': 'naaccord-submissions',
            'endpoint': 'https://s3.naaccord.internal',
            'access_key': os.environ.get('S3_ACCESS_KEY'),
            'secret_key': os.environ.get('S3_SECRET_KEY'),
            'region': 'us-east-1'
        },
        'scratch': {
            'driver': 'local',
            'root': '/tmp/naaccord-scratch'
        }
    }
}

# Default disk selections
DEFAULT_STORAGE_DISK = 'local'
SUBMISSION_STORAGE_DISK = 'nas_s3'
SCRATCH_STORAGE_DISK = 'scratch'
```

### Environment Configuration

```bash
# Server role (affects driver selection)
SERVER_ROLE=web|services|testing

# Override default disk selections
SUBMISSION_STORAGE_DISK=nas_s3
SCRATCH_STORAGE_DISK=local_fast

# Remote communication (for web server)
SERVICES_URL=https://services.naaccord.internal:8001
INTERNAL_API_KEY=your-secure-api-key

# S3 configuration
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_ENDPOINT=https://nas.naaccord.internal
```

## Remote Storage Driver

### Architecture

```
Web Server                    Services Server
┌─────────────────┐          ┌─────────────────┐
│ RemoteStorage   │ HTTPS    │ LocalStorage/S3 │
│ Driver          ├────────→ │ via API         │
│                 │          │                 │
│ No local PHI    │          │ Actual storage  │
└─────────────────┘          └─────────────────┘
```

### Features

**Streaming Operations**:
- Chunked uploads for large files (64KB chunks)
- Connection pooling and retry logic
- Authentication via API keys
- Full S3-compatible API forwarding

**API Endpoints** (services server):
```
POST   /internal/storage/save/        - Save file content
GET    /internal/storage/get/{path}   - Retrieve file
DELETE /internal/storage/delete/{path} - Delete file
GET    /internal/storage/exists/{path} - Check existence
POST   /internal/storage/list/        - List directory contents
```

### Implementation

```python
class RemoteStorageDriver(BaseStorage):
    def __init__(self):
        self.service_url = os.environ.get('SERVICES_URL')
        self.api_key = os.environ.get('INTERNAL_API_KEY')
        self.session = self._create_session()

    def save(self, path, content, content_type=None, metadata=None):
        """Stream file to services server"""
        response = self.session.post(
            f"{self.service_url}/internal/storage/save/",
            headers={
                'X-API-Key': self.api_key,
                'Content-Type': 'application/json'
            },
            json={
                'path': path,
                'content': base64.b64encode(content).decode(),
                'content_type': content_type,
                'metadata': metadata or {}
            }
        )

        if response.status_code != 200:
            raise StorageError(f"Remote save failed: {response.text}")

        return response.json()['path']

    def get_file(self, path):
        """Retrieve file from services server"""
        response = self.session.get(
            f"{self.service_url}/internal/storage/get/{path}",
            headers={'X-API-Key': self.api_key}
        )

        if response.status_code == 404:
            raise FileNotFoundError(f"File not found: {path}")

        return base64.b64decode(response.json()['content'])
```

## Storage Driver Interface

### Common Methods

All storage drivers implement the same interface:

```python
class BaseStorage:
    def save(self, path, content, content_type=None, metadata=None):
        """Save content to path with optional metadata"""
        raise NotImplementedError

    def get_file(self, path):
        """Retrieve file content as bytes"""
        raise NotImplementedError

    def delete(self, path):
        """Delete file at path"""
        raise NotImplementedError

    def exists(self, path):
        """Check if file exists at path"""
        raise NotImplementedError

    def list_files(self, prefix):
        """List files with given prefix"""
        raise NotImplementedError

    def url(self, path, expires_in=3600):
        """Get URL for file access"""
        raise NotImplementedError

    def get_metadata(self, path):
        """Get file metadata"""
        raise NotImplementedError
```

### Path Generation

```python
# Automatic path generation for structured storage
def get_path_for_submission_file(self, cohort_id, cohort_name,
                                protocol_year, file_type, filename):
    """
    Generate structured path for submission files
    Returns: submissions/{cohort_name}/{protocol_year}/{file_type}/{filename}
    Example: submissions/VACS/2024/patient/patient_data_v2.csv
    """
    return f"submissions/{cohort_name}/{protocol_year}/{file_type}/{filename}"

def get_path_for_scratch_file(self, audit_id, filename):
    """
    Generate path for temporary scratch files
    Returns: scratch/audit_{audit_id}/{filename}
    Example: scratch/audit_123/converted_data.duckdb
    """
    return f"scratch/audit_{audit_id}/{filename}"
```

## Integration with PHI Tracking

### Automatic Tracking

```python
def save_with_tracking(self, path, content, cohort, user, file_type, **kwargs):
    """Save file and create PHI tracking record"""
    try:
        # Calculate file hash for integrity
        file_hash = calculate_sha256(content)

        # Save the file
        result = self.storage.save(path, content)

        # Create tracking record
        PHIFileTracking.log_operation(
            cohort=cohort,
            user=user,
            action='nas_raw_created',
            file_path=path,
            file_type=file_type,
            file_size=len(content) if isinstance(content, (str, bytes)) else None,
            file_hash=file_hash,
            content_object=kwargs.get('content_object'),
            metadata=kwargs.get('metadata', {})
        )

        return result

    except Exception as e:
        # Log failure
        PHIFileTracking.log_operation(
            cohort=cohort,
            user=user,
            action='nas_raw_creation_failed',
            file_path=path,
            error_message=str(e),
            content_object=kwargs.get('content_object')
        )
        raise
```

### Cleanup Integration

```python
def create_temp_file_with_cleanup(self, path, content, cleanup_hours=2):
    """Create temporary file with automatic cleanup tracking"""
    # Save the file
    result = self.save(path, content)

    # Track for cleanup
    PHIFileTracking.log_operation(
        action='work_copy_created',
        file_path=path,
        cleanup_required=True,
        expected_cleanup_by=timezone.now() + timedelta(hours=cleanup_hours)
    )

    return result

def cleanup_temp_file(self, path, user):
    """Delete temporary file and verify cleanup"""
    # Delete the file
    self.delete(path)

    # Update tracking record
    tracking = PHIFileTracking.objects.get(file_path=path)
    tracking.mark_cleaned_up(user=user)
```

## Performance Optimizations

### Connection Pooling

```python
def _create_session(self):
    """Create HTTP session with connection pooling"""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )

    # Add adapter with pooling
    adapter = HTTPAdapter(
        pool_connections=10,
        pool_maxsize=10,
        max_retries=retry_strategy
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session
```

### Chunked Transfers

```python
CHUNK_SIZE = 64 * 1024  # 64KB chunks

def stream_large_file(self, path, content):
    """Stream large files in chunks to prevent timeouts"""
    chunks = [content[i:i+self.CHUNK_SIZE]
              for i in range(0, len(content), self.CHUNK_SIZE)]

    for i, chunk in enumerate(chunks):
        is_final = (i == len(chunks) - 1)

        response = self.session.post(
            f"{self.service_url}/internal/storage/append/",
            json={
                "path": path,
                "chunk": base64.b64encode(chunk).decode(),
                "is_final": is_final,
                "chunk_index": i
            }
        )

        if response.status_code != 200:
            raise StorageError(f"Chunk {i} upload failed")
```

### Instance Caching

```python
class StorageManager:
    _instances = {}  # Cache storage instances

    @classmethod
    def get_storage(cls, disk_name):
        """Get cached storage instance"""
        if disk_name in cls._instances:
            return cls._instances[disk_name]

        # Create new instance
        instance = cls._create_storage_instance(disk_name)
        cls._instances[disk_name] = instance

        return instance

    @classmethod
    def clear_cache(cls):
        """Clear instance cache (for testing)"""
        cls._instances.clear()
```

## Security Features

### API Authentication

```python
def _authenticate_request(self, headers):
    """Validate API key authentication"""
    api_key = headers.get('X-API-Key')
    expected_key = os.environ.get('INTERNAL_API_KEY')

    if not api_key or api_key != expected_key:
        raise AuthenticationError("Invalid or missing API key")

    return True

def _add_security_headers(self, request_headers):
    """Add security headers to all requests"""
    request_headers.update({
        'X-API-Key': self.api_key,
        'User-Agent': 'NAACCORDRemoteStorage/1.0',
        'X-Server-Role': os.environ.get('SERVER_ROLE', 'unknown'),
        'X-Request-ID': str(uuid.uuid4())
    })
```

### Server Role Enforcement

```python
def enforce_storage_security(self):
    """Ensure storage operations respect server role boundaries"""
    server_role = os.environ.get('SERVER_ROLE', '').lower()

    if server_role == 'web':
        # Web server MUST use remote storage for scratch files
        if not isinstance(self, RemoteStorageDriver):
            raise SecurityError(
                "Web server must use remote storage for PHI operations"
            )

    elif server_role == 'services':
        # Services server should not use remote storage
        if isinstance(self, RemoteStorageDriver):
            logger.warning(
                "Services server using remote storage - possible misconfiguration"
            )
```

### Automatic HTTPS Enforcement

```python
def validate_security_configuration(self):
    """Validate security settings before operations"""
    if self.service_url.startswith('http://'):
        if not settings.DEBUG:
            raise SecurityError(
                "HTTPS required for remote storage in production"
            )
        else:
            logger.warning(
                "Using HTTP for remote storage in development mode"
            )

    # Validate API key strength
    if len(self.api_key) < 32:
        logger.warning("API key should be at least 32 characters")
```

## Error Handling and Resilience

### Retry Logic

```python
class RetryableStorageOperation:
    def __init__(self, max_retries=3, backoff_factor=1):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def execute_with_retry(self, operation, *args, **kwargs):
        """Execute storage operation with exponential backoff retry"""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except (ConnectionError, TimeoutError, StorageError) as e:
                last_exception = e

                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(f"Storage operation failed, retrying in {sleep_time}s: {e}")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Storage operation failed after {self.max_retries} retries: {e}")

        raise last_exception
```

### Fallback Mechanisms

```python
def save_with_fallback(self, path, content, **kwargs):
    """Save with fallback to local storage if remote fails"""
    try:
        # Try primary storage
        return self.primary_storage.save(path, content, **kwargs)

    except (ConnectionError, StorageError) as e:
        logger.warning(f"Primary storage failed, using fallback: {e}")

        # Use local fallback
        fallback_path = f"fallback/{path}"
        result = self.fallback_storage.save(fallback_path, content, **kwargs)

        # Queue for sync when primary is available
        self._queue_for_sync(path, fallback_path)

        return result
```

## Storage Configuration Examples

### Production Two-Server Setup

**Web Server Configuration**:
```python
# Web server streams everything to services
STORAGE_CONFIG = {
    'disks': {
        'remote_scratch': {
            'driver': 'remote',
            'service_url': 'https://services.naaccord.internal:8001',
            'api_key': os.environ.get('INTERNAL_API_KEY')
        }
    }
}

SERVER_ROLE = 'web'
SCRATCH_STORAGE_DISK = 'remote_scratch'
```

**Services Server Configuration**:
```python
# Services server handles actual storage
STORAGE_CONFIG = {
    'disks': {
        'nas_s3': {
            'driver': 's3',
            'bucket': 'naaccord-prod-submissions',
            'endpoint': 'https://nas.naaccord.internal',
            'access_key': os.environ.get('S3_ACCESS_KEY'),
            'secret_key': os.environ.get('S3_SECRET_KEY')
        },
        'local_scratch': {
            'driver': 'local',
            'root': '/mnt/fast-ssd/scratch'
        }
    }
}

SERVER_ROLE = 'services'
SUBMISSION_STORAGE_DISK = 'nas_s3'
SCRATCH_STORAGE_DISK = 'local_scratch'
```

### Development Single-Server Setup

```python
# Development - everything local
STORAGE_CONFIG = {
    'disks': {
        'local': {
            'driver': 'local',
            'root': '/app/storage'
        },
        'scratch': {
            'driver': 'local',
            'root': '/tmp/naaccord-scratch'
        }
    }
}

SERVER_ROLE = 'testing'
SUBMISSION_STORAGE_DISK = 'local'
SCRATCH_STORAGE_DISK = 'scratch'
```

## Best Practices

### Use Appropriate Storage Type

```python
# GOOD: Use specific storage for purpose
submission_storage = StorageManager.get_submission_storage()  # Permanent files
scratch_storage = StorageManager.get_scratch_storage()        # Temp files

# BAD: Use generic storage
storage = StorageManager.get_storage('local')  # Too generic
```

#### Granular Validation (Precheck)

- `depot/tasks/validation.convert_to_duckdb_and_validate` now stages both the raw CSV and the generated DuckDB file in `scratch/upload_prechecks/<id>/` via `ScratchManager`.
- Each artefact is logged in `PHIFileTracking` (`work_copy_created`, `conversion_started/completed`, `work_copy_deleted`) with `cleanup_required=True` so scheduled cleanup jobs can verify no precheck files linger on NAS.
- The task deletes the scratch CSV immediately after conversion; the DuckDB workspace file remains until cleanup verifies that the validation run has finished.

### Handle Server Roles Properly

```python
# GOOD: Let StorageManager handle role detection
storage = StorageManager.get_scratch_storage()  # Automatic role-based selection

# BAD: Manual role checking
if os.environ.get('SERVER_ROLE') == 'web':
    storage = RemoteStorageDriver()  # Manual role handling
```

### Include Metadata for Debugging

```python
# GOOD: Include useful metadata
storage.save(
    path='submissions/cohort_5/data.csv',
    content=content,
    metadata={
        'cohort_id': '5',
        'uploaded_by': user.username,
        'upload_timestamp': timezone.now().isoformat(),
        'file_version': '2'
    }
)

# BAD: No metadata
storage.save('submissions/cohort_5/data.csv', content)
```

### Use Context Managers for Cleanup

```python
# GOOD: Automatic cleanup
with StorageManager.temp_file_context() as temp_path:
    storage.save(temp_path, content)
    process_data(temp_path)
    # Automatically cleaned up

# BAD: Manual cleanup (error-prone)
temp_path = storage.save('temp/file.csv', content)
try:
    process_data(temp_path)
finally:
    storage.delete(temp_path)  # May fail
```

## Monitoring and Health Checks

### Storage Health Verification

```python
def check_storage_health():
    """Comprehensive storage health check"""
    results = {}

    for disk_name in ['submission', 'scratch']:
        try:
            storage = StorageManager.get_storage(disk_name)

            # Test basic operations
            test_path = f'health-check/{uuid.uuid4()}.txt'
            test_content = b'health check content'

            # Save
            storage.save(test_path, test_content)

            # Retrieve
            retrieved = storage.get_file(test_path)
            assert retrieved == test_content

            # Delete
            storage.delete(test_path)

            results[disk_name] = {'status': 'healthy'}

        except Exception as e:
            results[disk_name] = {
                'status': 'unhealthy',
                'error': str(e)
            }

    return results
```

### Performance Monitoring

```python
import time
from django.core.cache import cache

def monitor_storage_performance(operation_name, storage_func, *args, **kwargs):
    """Monitor and cache storage operation performance"""
    start_time = time.time()

    try:
        result = storage_func(*args, **kwargs)
        duration = time.time() - start_time

        # Log performance metrics
        logger.info(f"Storage {operation_name} completed in {duration:.2f}s")

        # Cache performance data
        cache.set(f"storage_perf_{operation_name}", duration, 300)

        return result

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Storage {operation_name} failed after {duration:.2f}s: {e}")
        raise
```

## Related Documentation
- [PHI File Tracking System](../../docs/security/PHIFileTracking-system.md)
- [Storage Manager Abstraction](../../docs/technical/storage-manager-abstraction.md)
- [Security Domain](../security/CLAUDE.md)
- [Upload Submissions Domain](../upload_submissions/CLAUDE.md)
- [Audit Domain](../audit/CLAUDE.md)
