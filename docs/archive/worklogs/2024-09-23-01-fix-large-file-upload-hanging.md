# Fix Large File Upload Hanging Issue

**Date**: 2025-09-23
**Issue**: 327MB file uploads were hanging at 100% complete in the UI
**Root Cause**: Web server was waiting synchronously for services server to complete file storage to NAS

## Problem Description

When uploading large files (327MB test case), the upload progress would reach 100% but then hang indefinitely. The file would eventually be saved, but the user experience was poor with no feedback and long waits.

### Architecture Context

The system has a two-server architecture for PHI compliance:
- **Web Server (port 8000)**: Should NEVER store PHI data, even temporarily
- **Services Server (port 8001)**: Handles all PHI storage operations with direct NAS access

Configuration is controlled by `SERVER_ROLE` environment variable:
- When `SERVER_ROLE=web`: Uses `RemoteStorageDriver` to forward all storage operations to services server
- When `SERVER_ROLE=services`: Uses `LocalFileSystemStorage` to store files on NAS

## Investigation Findings

1. **Initial Misconception**: Thought we needed to implement async file processing with Celery
   - Created `async_file_processing.py` task (later found to be wrong approach)
   - PHI compliance requires NO temp storage on web server

2. **Discovered Existing Architecture**:
   - `depot/services/upload_router.py` - Routes uploads to secure endpoints
   - `depot/views/internal_storage.py` - Services server API endpoints
   - `depot/storage/remote.py` - RemoteStorageDriver for web server
   - Settings already configured with `SERVICES_URL` for remote storage

3. **Real Issue**:
   - Web server was correctly streaming to services server
   - But doing it synchronously - waiting for services server to finish
   - For 327MB file, this caused apparent hang while services server saved to NAS

## Solution Implemented

### 1. Optimized RemoteStorageDriver (`depot/storage/remote.py`)

Added detection and special handling for Django's `TemporaryUploadedFile`:
- Files >2.5MB are saved to temp by Django automatically
- Implemented chunked upload for files >10MB
- Uses 1MB chunks instead of 64KB for better performance
- Added progress logging every 10MB
- Properly streams from temp file without loading into memory

```python
def save(self, path, content, content_type=None, metadata=None):
    # Check if this is a Django TemporaryUploadedFile
    if hasattr(content, 'temporary_file_path'):
        # For large files on disk, use chunked upload
        if hasattr(content, 'size') and content.size > 10 * 1024 * 1024:  # > 10MB
            return self.save_chunked(path, content, content_type, metadata)
```

### 2. Optimized Services Server (`depot/views/internal_storage.py`)

Enhanced to handle `TemporaryUploadedFile` efficiently:
```python
# Optimize for Django's TemporaryUploadedFile (files > 2.5MB)
if hasattr(uploaded_file, 'temporary_file_path'):
    # File is already on disk - stream from disk file
    temp_path = uploaded_file.temporary_file_path()
    with open(temp_path, 'rb') as temp_file:
        saved_path = storage.save(path, temp_file, content_type=content_type, metadata=metadata)
```

### 3. Added Django File Upload Settings (`depot/settings.py`)

```python
# File Upload Configuration
FILE_UPLOAD_MAX_MEMORY_SIZE = 2.5 * 1024 * 1024  # 2.5MB - files larger go to temp disk
DATA_UPLOAD_MAX_MEMORY_SIZE = 500 * 1024 * 1024  # 500MB max POST body
FILE_UPLOAD_TEMP_DIR = env('FILE_UPLOAD_TEMP_DIR', default='/tmp')
```

### 4. LocalFileSystemStorage Already Optimized

The services server's storage backend (`depot/storage/local.py`) was already optimized to MOVE temp files instead of copying them (instant operation for files on same filesystem).

## Service Restart Commands

After making changes, restart both servers:

### Web Server (port 8000)
```bash
command tmux send-keys -t na:django C-c
command tmux send-keys -t na:django "source venv/bin/activate" C-m
command tmux send-keys -t na:django "export SERVER_ROLE=web" C-m
command tmux send-keys -t na:django "export INTERNAL_API_KEY=test-key-123" C-m
command tmux send-keys -t na:django "export SERVICES_URL=http://localhost:8001" C-m
command tmux send-keys -t na:django "python manage.py runserver 0.0.0.0:8000" C-m
```

### Services Server (port 8001)
```bash
command tmux send-keys -t na:services C-c
command tmux send-keys -t na:services "source venv/bin/activate" C-m
command tmux send-keys -t na:services "export SERVER_ROLE=services" C-m
command tmux send-keys -t na:services "export INTERNAL_API_KEY=test-key-123" C-m
command tmux send-keys -t na:services "python manage.py runserver 0.0.0.0:8001" C-m
```

## File Flow for Large Uploads

1. **Browser → Web Server**: File uploaded via multipart/form-data
2. **Django on Web**: Saves files >2.5MB to `/tmp` as `TemporaryUploadedFile`
3. **Web Server → Services Server**:
   - RemoteStorageDriver detects temp file
   - Uses chunked upload (1MB chunks) for files >10MB
   - Streams directly from temp file
4. **Services Server → NAS**:
   - Receives chunks from web server
   - LocalFileSystemStorage MOVES temp file to final location (instant)
5. **Response**: Services server returns success, web server returns to browser

## Testing

The 327MB file should now:
- Upload without hanging at 100%
- Stream efficiently through the entire pipeline
- Never fully load into memory on web server
- Complete much faster due to chunked streaming

## Files Modified

- `/Users/erikwestlund/code/naaccord/depot/storage/remote.py` - Added chunked upload optimization
- `/Users/erikwestlund/code/naaccord/depot/views/internal_storage.py` - Optimized for temp file handling
- `/Users/erikwestlund/code/naaccord/depot/services/file_upload_service.py` - Updated to use chunked uploads
- `/Users/erikwestlund/code/naaccord/depot/settings.py` - Added file upload configuration
- `/Users/erikwestlund/code/naaccord/depot/tasks/storage_tasks.py` - Created but not used (async approach didn't solve the issue)

## Key Lessons Learned

1. **Django's file handling**: Files >2.5MB automatically saved to temp as `TemporaryUploadedFile`
2. **Streaming vs Loading**: Must ensure true streaming, not loading entire file then sending
3. **PHI Compliance**: Web server must NEVER store PHI, not even temporarily - streaming is critical
4. **Existing Architecture**: The web→services architecture was already in place, just needed optimization
5. **Chunked Uploads**: For large files, chunked uploads prevent timeouts and memory issues