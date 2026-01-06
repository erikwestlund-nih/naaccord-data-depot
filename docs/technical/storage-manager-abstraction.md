# Storage Manager Abstraction

## Overview

The StorageManager system provides a sophisticated abstraction layer for file storage operations in NA-ACCORD's two-server architecture. This system currently uses NAS network storage with a driver architecture that supports future migration to S3-compatible storage if needed. The system handles local filesystem, NAS mounts, and remote server communication while maintaining security boundaries and PHI compliance.

## Architecture

### Core Components

```
StorageManager (depot/storage/manager.py)
├── BaseStorage (abstract base class)
├── LocalFileSystemStorage (local disk and NAS operations)
├── RemoteStorageDriver (web→services communication)
└── Future: S3-compatible storage support (via BaseStorage if migration needed)
```

### Multi-Driver Architecture

The StorageManager dynamically selects appropriate storage drivers based on:
- **Server role** (web/services/testing)
- **Storage type** (submission/scratch/general)
- **Configuration** (local/NAS/remote) - driver architecture supports future S3 migration if needed

## Server-Role Based Storage Selection

### Web Server (SERVER_ROLE=web)

**Scratch Storage**: Always uses RemoteStorageDriver
- Streams all temporary files to services server
- Never stores PHI locally on web server
- Maintains security boundary for HIPAA compliance

```python
# Web server automatically configured for remote streaming
storage = StorageManager.get_scratch_storage()
# Returns: RemoteStorageDriver -> streams to services server
```

### Services Server (SERVER_ROLE=services)

**All Storage**: Uses NAS network storage via LocalFileSystemStorage
- Handles actual file storage operations on NAS mount
- Processes all temporary files from web server
- Manages conversion to DuckDB and report generation
- Driver architecture supports future S3-compatible migration if needed

```python
# Services server uses NAS storage via LocalFileSystemStorage
storage = StorageManager.get_scratch_storage()
# Returns: LocalFileSystemStorage (pointing to NAS mount)
```

### Testing Environment (SERVER_ROLE=testing)

**All Storage**: Uses local filesystem
- Single-machine testing with local storage
- Simulates production behavior without complexity

## Storage Types and Use Cases

### 1. Submission Storage

**Purpose**: Permanent storage for cohort submission files
**Driver**: NAS network storage (driver architecture supports future S3-compatible migration)
**Access**: `StorageManager.get_submission_storage()`

```python
# Save a cohort submission file
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

### 2. Scratch Storage

**Purpose**: Temporary processing files requiring cleanup
**Driver**: Role-dependent (remote for web, NAS for services)
**Access**: `StorageManager.get_scratch_storage()`

```python
# Get appropriate scratch storage based on server role
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
**Driver**: Configurable per disk name
**Access**: `StorageManager.get_storage(disk_name)`

## Configuration System

### Settings Structure

```python
# settings.py
STORAGE_CONFIG = {
    'disks': {
        'local': {
            'driver': 'local',
            'root': '/app/storage'
        },
        'nas': {
            'driver': 'local',  # NAS mounted as local filesystem
            'root': '/mnt/nas/naaccord'
        },
        'scratch': {
            'driver': 'local',
            'root': '/tmp/naaccord-scratch'
        }
    }
}

# Default disk selections
DEFAULT_STORAGE_DISK = 'local'
SUBMISSION_STORAGE_DISK = 'nas'
SCRATCH_STORAGE_DISK = 'scratch'

# Note: Driver architecture supports future S3-compatible storage migration
# Example S3 configuration (not currently used):
# 'nas_s3': {
#     'driver': 's3',
#     'bucket': 'naaccord-submissions',
#     'endpoint': 'https://s3.example.com',
#     'access_key': 'ACCESS_KEY',
#     'secret_key': 'SECRET_KEY'
# }
```

### Environment Variable Configuration

```bash
# Server role (affects storage driver selection)
SERVER_ROLE=web|services|testing

# Override default disk selections
SUBMISSION_STORAGE_DISK=nas
SCRATCH_STORAGE_DISK=local_fast

# Remote communication (for web server)
SERVICES_URL=http://services-server:8001
INTERNAL_API_KEY=your-secure-api-key
```

## Remote Storage Driver

### Purpose

The RemoteStorageDriver enables the web server to stream all file operations to the services server, maintaining the security boundary where no PHI is stored on the web tier.

### Architecture

```
Web Server                    Services Server
┌─────────────────┐          ┌─────────────────┐
│ RemoteStorage   │ HTTP(S)  │ LocalStorage    │
│ Driver          ├────────→ │ (NAS) via API   │
│                 │          │                 │
│ No local PHI    │          │ Actual storage  │
└─────────────────┘          └─────────────────┘
```

### Features

**Streaming Operations**:
- Chunked uploads for large files (64KB chunks)
- Connection pooling and retry logic
- Authentication via API keys
- API forwarding to NAS storage (driver architecture supports future S3 migration)

**API Endpoints** (services server):
```
POST   /internal/storage/save/        - Save file content
GET    /internal/storage/get/{path}   - Retrieve file
DELETE /internal/storage/delete/{path} - Delete file
GET    /internal/storage/exists/{path} - Check existence
POST   /internal/storage/list/        - List directory contents
```

**Request Format**:
```python
# Upload request to services server
POST /internal/storage/save/
Headers:
  X-API-Key: internal-api-key
  Content-Type: application/json
Body:
{
  "path": "submissions/cohort_5/patient_data.csv",
  "content": "base64-encoded-content",
  "content_type": "text/csv",
  "metadata": {
    "cohort_id": "5",
    "file_type": "patient"
  }
}
```

## Storage Driver Interface

### Common Methods

All storage drivers implement the same interface:

```python
class BaseStorageInterface:
    def save(self, path, content, content_type=None, metadata=None):
        """Save content to path with optional metadata."""

    def get_file(self, path):
        """Retrieve file content."""

    def delete(self, path):
        """Delete file at path."""

    def exists(self, path):
        """Check if file exists."""

    def list_files(self, prefix):
        """List files with given prefix."""

    def url(self, path):
        """Get URL for file access."""
```

### Path Generation

Automatic path generation for structured storage:

```python
# Submission file paths
def get_path_for_submission_file(self, cohort_id, cohort_name,
                                protocol_year, file_type, filename):
    """
    Generate: submissions/{cohort_name}/{protocol_year}/{file_type}/{filename}
    Example: submissions/VACS/2024/patient/patient_data_v2.csv
    """
```

## Integration with PHI Tracking

### Automatic Tracking

Storage operations automatically create PHIFileTracking records:

```python
def save_with_tracking(self, path, content, cohort, user, file_type):
    """Save file and create tracking record."""
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
        content_object=related_object
    )

    return result
```

### Cleanup Integration

Scratch storage integrates with cleanup tracking:

```python
# Temporary file with cleanup tracking
scratch = StorageManager.get_scratch_storage()
temp_path = scratch.save('temp/processing/data.csv', content)

# Automatically tracked for cleanup
PHIFileTracking.log_operation(
    action='work_copy_created',
    file_path=temp_path,
    cleanup_required=True,
    expected_cleanup_by=timezone.now() + timedelta(hours=2)
)
```

## Performance Considerations

### Connection Pooling

RemoteStorageDriver uses connection pooling for efficient HTTP communication:

```python
# Session configuration with pooling
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=10,    # Connection pool size
    pool_maxsize=10,       # Max connections per pool
    max_retries=retry_strategy
)
```

### Chunked Transfers

Large files are transferred in chunks to prevent timeouts:

```python
CHUNK_SIZE = 64 * 1024  # 64KB chunks

def stream_upload(self, path, content):
    """Stream large files in chunks."""
    for chunk in self._chunk_content(content, self.CHUNK_SIZE):
        response = self.session.post(
            f"{self.service_url}/internal/storage/append/",
            json={
                "path": path,
                "chunk": base64.b64encode(chunk).decode(),
                "is_final": is_last_chunk
            }
        )
```

### Caching

StorageManager caches driver instances to prevent re-initialization:

```python
# Instance caching
_instances = {}

@classmethod
def get_storage(cls, disk_name):
    if disk_name in cls._instances:
        return cls._instances[disk_name]  # Return cached instance

    instance = cls._create_storage_instance(disk_name)
    cls._instances[disk_name] = instance  # Cache for reuse
    return instance
```

## Security Features

### 1. API Authentication

All remote operations use API key authentication:

```python
session.headers.update({
    'X-API-Key': self.api_key,
    'User-Agent': 'RemoteStorageDriver/1.0'
})
```

### 2. Server Role Enforcement

Storage selection enforces architectural boundaries:

```python
def get_scratch_storage(cls):
    server_role = os.environ.get('SERVER_ROLE', '').lower()

    if server_role == 'web':
        # Web server MUST use remote driver
        return cls._get_remote_driver()
    else:
        # Services server uses local/S3
        return cls._get_configured_driver()
```

### 3. Automatic HTTPS

Production configurations enforce HTTPS for remote operations:

```python
# Service URL validation
if self.service_url.startswith('http://') and not is_development:
    logger.warning("Using HTTP in production - should use HTTPS")
```

## Error Handling and Resilience

### Retry Logic

Automatic retry for transient failures:

```python
retry_strategy = Retry(
    total=3,                              # Max 3 retries
    backoff_factor=1,                     # Exponential backoff
    status_forcelist=[429, 500, 502, 503, 504],  # Retry these HTTP codes
    allowed_methods=["HEAD", "GET", "PUT", "DELETE", "POST"]
)
```

### Fallback Mechanisms

Graceful degradation when services are unavailable:

```python
def save_with_fallback(self, path, content):
    try:
        # Try primary storage
        return self.primary_storage.save(path, content)
    except ConnectionError:
        # Fall back to local cache
        logger.warning("Primary storage unavailable, using local fallback")
        return self.fallback_storage.save(path, content)
```

### Error Logging

Comprehensive error logging for troubleshooting:

```python
except IOError as e:
    logger.error(f"Storage operation failed: {e}")

    # Log to PHI tracking for audit
    PHIFileTracking.log_operation(
        action='nas_raw_creation_failed',
        file_path=path,
        error_message=f"Storage error: {str(e)}"
    )
    raise
```

## Best Practices

### 1. Use Appropriate Storage Type

```python
# GOOD: Use specific storage for purpose
submission_storage = StorageManager.get_submission_storage()  # For permanent files
scratch_storage = StorageManager.get_scratch_storage()        # For temp files

# BAD: Use generic storage
storage = StorageManager.get_storage('local')  # Too generic
```

### 2. Handle Server Roles Properly

```python
# GOOD: Let StorageManager handle role detection
storage = StorageManager.get_scratch_storage()  # Automatically selects correct driver

# BAD: Manually check server role
if os.environ.get('SERVER_ROLE') == 'web':
    storage = RemoteStorageDriver('remote')  # Manual role handling
```

### 3. Use Context Managers for Cleanup

```python
# GOOD: Automatic cleanup with context manager
with StorageManager.get_scratch_storage().temp_file() as temp_path:
    # Process file
    process_data(temp_path)
    # Automatically cleaned up

# BAD: Manual cleanup
temp_path = storage.save('temp/file.csv', content)
try:
    process_data(temp_path)
finally:
    storage.delete(temp_path)  # Manual cleanup (error-prone)
```

### 4. Include Metadata for Debugging

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

## Monitoring and Debugging

### 1. Storage Operation Logging

Monitor storage operations across the system:

```python
# Enable storage debugging
LOGGING = {
    'loggers': {
        'depot.storage': {
            'level': 'DEBUG',
            'handlers': ['console', 'file']
        }
    }
}
```

### 2. Health Checks

Verify storage connectivity:

```python
# Health check endpoint
def storage_health_check():
    try:
        storage = StorageManager.get_submission_storage()
        # Test basic operations
        test_path = 'health-check/test.txt'
        storage.save(test_path, 'test content')
        storage.get_file(test_path)
        storage.delete(test_path)
        return {'status': 'healthy'}
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}
```

### 3. Performance Monitoring

Track storage operation performance:

```python
import time

def save_with_metrics(self, path, content):
    start_time = time.time()
    try:
        result = self.storage.save(path, content)
        duration = time.time() - start_time

        logger.info(f"Storage save completed in {duration:.2f}s: {path}")
        return result
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Storage save failed after {duration:.2f}s: {path} - {e}")
        raise
```

## Configuration Examples

### Production Two-Server Setup

**Web Server Configuration**:
```python
# Web server - streams everything to services
STORAGE_CONFIG = {
    'disks': {
        'scratch_remote': {
            'driver': 'remote',
            'service_url': 'https://services.naaccord.internal:8001',
            'api_key': os.environ.get('INTERNAL_API_KEY')
        }
    }
}

# Environment
SERVER_ROLE=web
SERVICES_URL=https://services.naaccord.internal:8001
INTERNAL_API_KEY=your-secure-production-key
```

**Services Server Configuration**:
```python
# Services server - handles actual storage on NAS
STORAGE_CONFIG = {
    'disks': {
        'nas': {
            'driver': 'local',  # NAS mounted as local filesystem
            'root': '/mnt/nas/naaccord'
        },
        'scratch': {
            'driver': 'local',
            'root': '/mnt/fast-ssd/scratch'
        }
    }
}

SUBMISSION_STORAGE_DISK = 'nas'
SCRATCH_STORAGE_DISK = 'scratch'

# Environment
SERVER_ROLE=services

# Note: Driver architecture supports future S3-compatible migration
# Example S3 configuration (not currently used):
# 'nas_s3': {
#     'driver': 's3',
#     'bucket': 'naaccord-prod-submissions',
#     'endpoint': 'https://nas.naaccord.internal',
#     'access_key': os.environ.get('S3_ACCESS_KEY'),
#     'secret_key': os.environ.get('S3_SECRET_KEY')
# }
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

SUBMISSION_STORAGE_DISK = 'local'
SCRATCH_STORAGE_DISK = 'scratch'

# Environment
SERVER_ROLE=testing
```

## Related Documentation

- [PHI File Tracking System](../security/PHIFileTracking-system.md)
- [Upload Submission Workflow](../technical/upload-submission-workflow.md)
- [Security Architecture](../security/security-overview.md)
- [Two-Server Deployment](../deployment/production-deployment.md)

## Implementation Files

- **Manager**: `depot/storage/manager.py`
- **Base Storage**: `depot/storage/base.py`
- **Local Storage**: `depot/storage/local.py`
- **Remote Storage**: `depot/storage/remote.py`
- **Tests**: `depot/tests/test_storage_abstraction.py`
- **Integration**: Multiple files across views, tasks, and services