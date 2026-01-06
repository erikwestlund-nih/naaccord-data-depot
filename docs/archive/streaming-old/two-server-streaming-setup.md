# Two-Server Streaming Architecture Setup

## Overview

NA-ACCORD uses a two-server architecture to separate web-facing functionality from PHI data processing:

- **Web Server**: Handles user interface, authentication, and request routing (no PHI storage)
- **Services Server**: Handles data processing, storage, and PHI operations (secure environment)

All file uploads are streamed from the web server to the services server without local storage.

## Architecture Components

### Storage Manager (`depot/storage/manager.py`)

The `StorageManager` class provides intelligent routing based on server role:

- `get_workspace_storage()`: Automatically detects `SERVER_ROLE` and routes accordingly
  - When `SERVER_ROLE=web`: Returns `RemoteStorageDriver` (streams to services)
  - When `SERVER_ROLE=services`: Returns `LocalFileSystemStorage` (stores on NAS)
  - When `SERVER_ROLE=testing`: Returns `LocalFileSystemStorage` (local testing)

- `get_submission_storage()`: Legacy method (avoid using - doesn't support streaming)

### Remote Storage Driver (`depot/storage/remote.py`)

Implements streaming operations for the web server:
- Forwards all file operations to services server via HTTP
- Never stores files locally
- Uses chunked uploads for large files
- Maintains connection pooling and retry logic

### Internal Storage API (`depot/views/internal_storage.py`)

Services server endpoints that handle storage operations:
- `/internal/storage/upload`: File upload endpoint
- `/internal/storage/download`: File retrieval
- `/internal/storage/delete`: File deletion
- `/internal/storage/list`: Directory listing
- `/internal/storage/health`: Health check

## Configuration

### Environment Variables

Set these environment variables based on server role:

#### Web Server Configuration
```bash
export SERVER_ROLE=web
export INTERNAL_API_KEY=<secure-api-key>
export SERVICES_URL=http://<services-host>:8001
```

#### Services Server Configuration
```bash
export SERVER_ROLE=services
export INTERNAL_API_KEY=<secure-api-key>
# Storage paths configured in settings.py
```

### Django Settings

The storage configuration in `settings.py`:

```python
STORAGE_CONFIG = {
    'disks': {
        'local': {
            'driver': 'local',
            'root': str(BASE_DIR / 'storage' / 'nas'),
        },
        'workspace': {
            'driver': 'local',  # Services server uses local
            'root': str(BASE_DIR / 'storage' / 'workspace'),
        }
    }
}

# Note: Web server dynamically overrides workspace config
# when SERVER_ROLE=web to use RemoteStorageDriver
```

## Running the Two-Server Setup

### Option 1: Using tmux (Development)

```bash
# Start tmux session
tmux new-session -s naaccord

# Tab 1: Services server
export SERVER_ROLE=services
export INTERNAL_API_KEY=test-key-123
python manage.py runserver 127.0.0.1:8001

# Tab 2: Web server
export SERVER_ROLE=web
export INTERNAL_API_KEY=test-key-123
export SERVICES_URL=http://localhost:8001
python manage.py runserver 127.0.0.1:8000
```

### Option 2: Using Management Command

```bash
# Starts both servers automatically
python manage.py test_two_server \
  --web-port 8000 \
  --services-port 8001 \
  --api-key test-key-123
```

### Option 3: Production Deployment

Use the Ansible playbooks with proper role configuration:
- Web servers: Set `SERVER_ROLE=web` in environment
- Services servers: Set `SERVER_ROLE=services` in environment

## Code Implementation

### Correct Usage (Supports Streaming)

```python
from depot.storage.manager import StorageManager

# CORRECT: Uses workspace storage with automatic routing
storage = StorageManager.get_workspace_storage()
saved_path = storage.save(
    path='upload_prechecks/cohort_1/patient/data.csv',
    content=file_content,
    content_type='text/csv'
)
```

### Incorrect Usage (Bypasses Streaming)

```python
# WRONG: Bypasses server role detection
storage = StorageManager.get_submission_storage()  # Don't use this

# WRONG: Direct instantiation
storage = LocalFileSystemStorage('local')  # Never do this
```

## File Upload Flow

1. **User uploads file** through web interface
2. **Web server** receives file in memory
3. **StorageManager.get_workspace_storage()** returns `RemoteStorageDriver`
4. **RemoteStorageDriver** streams file to services server
5. **Services server** receives stream at `/internal/storage/upload`
6. **Services server** saves to NAS using `LocalFileSystemStorage`
7. **Response** returned through chain to user

## Important: Middleware Configuration

The `SignedInMiddleware` must exclude `/internal/` paths to allow API key authentication:

```python
# depot/middleware/signed_in.py
self.excluded_paths = [
    # ... other paths ...
    re.compile(r"^/internal/"),  # Required for services communication
]
```

Without this exclusion, internal API endpoints will redirect to login instead of accepting API key authentication.

## Troubleshooting

### Issue: Files Saving Locally on Web Server

**Symptom**: Files appear in `/storage/nas/` on web server

**Cause**: Code is using `get_submission_storage()` instead of `get_workspace_storage()`

**Fix**: Update code to use:
```python
storage = StorageManager.get_workspace_storage()
```

### Issue: No Streaming Activity in Logs

**Symptom**: No API requests appear in services server logs

**Causes**:
1. `SERVER_ROLE` environment variable not set
2. Using wrong storage method
3. Services server not running

**Verification**:
```bash
# Check environment
echo $SERVER_ROLE  # Should output "web" on web server

# Test services server
curl -H "X-API-Key: test-key-123" \
  http://localhost:8001/internal/storage/health
```

### Issue: Authentication Errors

**Symptom**: 403 Forbidden or 401 Unauthorized

**Cause**: `INTERNAL_API_KEY` mismatch between servers

**Fix**: Ensure same API key on both servers:
```bash
# Both servers need same key
export INTERNAL_API_KEY=<same-secure-key>
```

### Issue: Connection Refused

**Symptom**: Web server can't connect to services server

**Causes**:
1. Services server not running
2. Wrong `SERVICES_URL` configuration
3. Firewall blocking connection

**Fix**:
```bash
# Verify services server is running
curl http://localhost:8001/

# Check SERVICES_URL
echo $SERVICES_URL  # Should be http://localhost:8001
```

## Testing

### Unit Tests
```bash
python manage.py test depot.tests.test_two_server
```

### Integration Testing
```bash
# Start servers with test command
python manage.py test_two_server --run-tests
```

### Manual Testing

1. Set up environment for web server:
```bash
export SERVER_ROLE=web
export INTERNAL_API_KEY=test-key-123
export SERVICES_URL=http://localhost:8001
```

2. Upload a file through the interface
3. Check services server logs for upload requests
4. Verify file appears in services server storage, not web server

## Security Considerations

1. **API Key Security**: Use strong, randomly generated API keys in production
2. **Network Isolation**: Services server should not be publicly accessible
3. **TLS/SSL**: Use HTTPS for production communication between servers
4. **Firewall Rules**: Restrict services server to only accept connections from web servers
5. **No PHI on Web Server**: Regularly audit to ensure no PHI files on web tier

## Migration from Single Server

If migrating from single-server to two-server architecture:

1. **Update all storage calls**:
   - Find: `StorageManager.get_submission_storage()`
   - Replace with: `StorageManager.get_workspace_storage()`

2. **Search for direct storage instantiation**:
   ```bash
   grep -r "LocalFileSystemStorage\|BaseStorage" --include="*.py"
   # Replace with StorageManager calls
   ```

3. **Set environment variables** before starting servers

4. **Test thoroughly** before production deployment

## Related Documentation

- [File Streaming Architecture](file_streaming_architecture.md)
- [Storage Abstraction Layer](storage_abstraction.md)
- [Test Two-Server Setup](test_two_server.md)