# Quick Start: File Streaming Architecture

## Overview

This guide will help you quickly set up and test the NA-ACCORD two-server file streaming architecture. This system ensures the web server never stores files locally, streaming everything to a secure services server.

## Prerequisites

- Fresh database (migrations applied)
- Python virtual environment activated
- All dependencies installed

## Quick Setup

### 1. Create Default Superuser

```bash
# Create the default superuser (fixes VA bug)
python manage.py create_default_superuser
```

**Login Credentials:**
- Email: `ewestlund@jhu.edu`
- Password: `admin123`
- Role: Superuser + NAAccord Administrator

### 2. Start Development with Streaming (Recommended)

**Option A: Use Tmux Script (Erik's Setup)**
```bash
# Start Docker services
dockerna start

# Start tmux session with streaming
tmna  # or /Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

This creates:
- Web server on port 8000 (`SERVER_ROLE=web`)
- Services server on port 8001 (`SERVER_ROLE=services`)
- All other development tools (Celery, NPM, R, etc.)

**Option B: Manual Two-Server Setup**

```bash
# Start both servers on different ports with test runner
python manage.py test_two_server --web-port 8000 --services-port 8001 --run-tests

# Or start manually for interactive testing
python manage.py test_two_server --web-port 8000 --services-port 8001
```

This will:
- Start services server on port 8001 (handles actual file storage)
- Start web server on port 8000 (streams files to services server)
- Run the test suite automatically if `--run-tests` is used

### 3. Verify Setup

#### Access Web Interface
1. Open browser to `http://localhost:8000`
2. Login with `ewestlund@jhu.edu` / `admin123`
3. Upload a file through the interface

#### Verify Streaming
1. **Web Server** (port 8000): Should have NO files stored locally
2. **Services Server** (port 8001): Should contain all uploaded files
3. **PHI Tracking**: Check database for streaming operation records

```bash
# Check files on web server (should be empty)
ls -la /tmp/

# Check files on services server (should contain files)  
ls -la /path/to/test_storage/workspace/

# Check PHI tracking in Django shell
python manage.py shell
>>> from depot.models import PHIFileTracking
>>> PHIFileTracking.objects.filter(action__contains='stream').count()
```

## Production Deployment

### Environment Variables

#### Web Server (port 80/443)
```bash
export SERVER_ROLE=web
export SERVICES_URL=http://services-server:8001
export INTERNAL_API_KEY=your-secure-api-key-here
```

#### Services Server (internal network)
```bash
export SERVER_ROLE=services  
export INTERNAL_API_KEY=your-secure-api-key-here
export NAS_WORKSPACE_PATH=/mnt/nas/naaccord
export WORKSPACE_STORAGE_DISK=workspace
```

### Storage Configuration

#### Services Server (with NAS)
```python
# In settings.py or environment
STORAGE_CONFIG = {
    'disks': {
        'workspace': {
            'driver': 'local',
            'root': '/mnt/nas/naaccord/workspace'
        }
    }
}
```

#### Services Server (with S3)
```python
STORAGE_CONFIG = {
    'disks': {
        'workspace': {
            'driver': 's3',
            'bucket': 'naaccord-workspace',
            'endpoint': 'https://s3.amazonaws.com',
            'access_key': 'YOUR_ACCESS_KEY',
            'secret_key': 'YOUR_SECRET_KEY'
        }
    }
}
```

### Deployment Steps

1. **Deploy Services Server First**
   ```bash
   # Set environment variables
   export SERVER_ROLE=services
   export INTERNAL_API_KEY=production-key
   
   # Start services server
   python manage.py runserver 0.0.0.0:8001
   ```

2. **Test Internal API**
   ```bash
   curl -H "X-API-Key: production-key" \
        http://services-server:8001/internal/storage/health
   ```

3. **Deploy Web Server**
   ```bash
   # Set environment variables
   export SERVER_ROLE=web
   export SERVICES_URL=http://services-server:8001
   export INTERNAL_API_KEY=production-key
   
   # Start web server
   python manage.py runserver 0.0.0.0:8000
   ```

4. **Test End-to-End**
   - Upload file through web interface
   - Verify no local storage on web server
   - Verify file exists on services server
   - Check PHI tracking records

## Testing

### Run All Streaming Tests
```bash
# Run comprehensive test suite
python manage.py test depot.tests.test_streaming_simple -v 2

# Run original two-server tests  
python manage.py test depot.tests.test_two_server.TestStorageManagerServerRoles -v 2
python manage.py test depot.tests.test_two_server.TestRemoteStorageDriver -v 2
```

### Manual Testing Scenarios

#### 1. File Upload Test
1. Upload file via web interface
2. Check that web server has no local files
3. Verify file exists on services server
4. Confirm PHI tracking record created

#### 2. Large File Test  
1. Upload file >10MB (triggers chunked upload)
2. Verify successful transfer
3. Check PHI tracking shows chunked upload action

#### 3. Cleanup Test
1. Upload files to different upload prechecks
2. Wait or modify timestamps to make files "old" 
3. Run cleanup: `python manage.py cleanup_orphaned_files --hours 0`
4. Verify old files removed, recent files preserved

### Debug Commands

```bash
# Check current server role
echo $SERVER_ROLE

# Test storage configuration
python manage.py shell -c "
from depot.storage.manager import StorageManager
storage = StorageManager.get_workspace_storage()
print(f'Storage type: {type(storage).__name__}')
if hasattr(storage, 'service_url'):
    print(f'Service URL: {storage.service_url}')
"

# Test internal API connectivity (from web server)
curl -H "X-API-Key: $INTERNAL_API_KEY" \
     $SERVICES_URL/internal/storage/health

# Manual cleanup test
python manage.py shell -c "
from depot.storage.workspace_manager_refactored import WorkspaceManager
w = WorkspaceManager()
result = w.cleanup_orphaned_directories(hours=0, dry_run=True)
print(f'Found {result[\"found\"]} orphaned directories')
"
```

## Troubleshooting

### Common Issues

#### "INTERNAL_API_KEY required for web server role"
- **Cause**: Missing API key environment variable
- **Fix**: Set `INTERNAL_API_KEY` on both servers

#### "Connection refused" errors
- **Cause**: Services server not running or wrong URL
- **Fix**: Check `SERVICES_URL` and services server status

#### Files not being cleaned up
- **Cause**: Cleanup job not running or wrong configuration  
- **Fix**: Run manual cleanup and check PHI tracking

#### Web server storing files locally
- **Cause**: Wrong server role or storage configuration
- **Fix**: Verify `SERVER_ROLE=web` and storage driver

### Health Checks

```bash
# Services server health
curl -H "X-API-Key: $INTERNAL_API_KEY" \
     http://services-server:8001/internal/storage/health

# Storage operations test
python manage.py shell -c "
from depot.storage.manager import StorageManager
from depot.storage.workspace_manager_refactored import WorkspaceManager

# Test storage
storage = StorageManager.get_workspace_storage()
print(f'Storage: {type(storage).__name__}')

# Test workspace manager
workspace = WorkspaceManager()
usage = workspace.get_workspace_usage()
print(f'Workspace usage: {usage}')
"
```

## Architecture Summary

✅ **Web Server**: Never stores files, streams to services  
✅ **Services Server**: Handles all file storage (NAS/S3)  
✅ **PHI Tracking**: Complete audit trail of all operations  
✅ **Security**: Internal API key authentication  
✅ **Testing**: Single-machine simulation for development  
✅ **Cleanup**: Application-controlled file lifecycle  

The system is now ready for production use with complete file streaming between servers!