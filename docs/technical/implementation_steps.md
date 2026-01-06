# File Streaming Implementation Steps

## Overview
Implementation of a secure two-server file handling system where the web server streams files directly to the services server without local storage.

## Step-by-Step Implementation Guide

### Step 1: Create RemoteStorageDriver
- [ ] Create `depot/storage/remote.py` with RemoteStorageDriver class
- [ ] Implement streaming methods (save, get_file, delete, list_with_prefix)
- [ ] Add chunked upload support for large files
- [ ] Implement authentication with internal API key
- [ ] Add connection pooling for efficiency
- [ ] Create retry logic for network failures

### Step 2: Build Internal Storage API
- [x] Create `depot/views/internal_storage.py` for API endpoints
- [x] Implement `/internal/storage/upload` endpoint with streaming
- [x] Implement `/internal/storage/download` endpoint  
- [x] Implement `/internal/storage/delete` endpoint
- [x] Implement `/internal/storage/list` endpoint
- [x] Add authentication middleware for internal API key
- [x] Add request validation and error handling
- [x] Configure URL routing for internal endpoints

### Step 3: Setup Testing Environment
- [x] Create `depot/tests/test_two_server.py` test suite
- [x] Implement server startup helper for multiple instances
- [x] Create environment variable configuration for testing
- [x] Add test for streaming upload through web to services
- [x] Add test for no local storage on web server
- [x] Add test for cleanup coordination between servers
- [x] Create management command for two-server testing mode

### Step 4: Update StorageManager
- [x] Add logic to detect server role from environment
- [x] Configure RemoteStorageDriver for web server role
- [x] Configure LocalStorageDriver for services server role
- [x] Add TestingStorageDriver for development
- [x] Update get_workspace_storage() method
- [x] Add configuration validation

### Step 5: Enhance PHIFileTracking
- [x] Add migration for new streaming fields
- [x] Add server_role field
- [x] Add stream_start and stream_complete timestamps
- [x] Add bytes_transferred field
- [x] Add cleanup_scheduled_for field
- [x] Update tracking methods for streaming operations

### Step 6: Implement Cleanup System
- [ ] Update WorkspaceManager for remote cleanup
- [ ] Add cleanup request forwarding from web to services
- [ ] Implement orphan detection with streaming awareness
- [ ] Add retry logic for failed cleanups
- [ ] Update PHIFileTracking for cleanup operations

### Step 7: Setup Celery Scheduling
- [ ] Create `depot/tasks/file_management.py`
- [ ] Implement cleanup_orphaned_files task
- [ ] Implement verify_file_integrity task
- [ ] Implement generate_storage_report task
- [ ] Configure Celery beat schedule
- [ ] Add task monitoring and alerts

### Step 8: Create Documentation
- [ ] Write architecture documentation
- [ ] Create deployment guide
- [ ] Document configuration options
- [ ] Create troubleshooting guide
- [ ] Write API reference
- [ ] Create workflow diagrams

### Step 9: Integration Testing
- [ ] Test large file uploads (2GB)
- [ ] Test concurrent uploads
- [ ] Test network interruption handling
- [ ] Test cleanup during active upload
- [ ] Test server role switching
- [ ] Performance testing

### Step 10: Production Preparation
- [ ] Security audit
- [ ] Load testing
- [ ] Monitoring setup
- [ ] Backup procedures
- [ ] Disaster recovery plan
- [ ] Deployment checklist

## Current Status
- **Current Step**: Implementation Complete - Documentation Phase
- **Completed**: 
  - Step 1 (RemoteStorageDriver) ✓
  - Step 2 (Internal Storage API) ✓
  - Step 3 (Testing Environment) ✓
  - Step 4 (StorageManager Updates) ✓
  - Step 5 (PHIFileTracking Enhancement) ✓
  - Step 8 (Core Documentation) ✓
- **Remaining Steps**:
  - Step 6: Cleanup System (using existing implementation)
  - Step 7: Celery Scheduling (optional - can use existing)
  - Step 9: Integration Testing
  - Step 10: Production Preparation
- **Started**: 2025-09-17
- **Completion**: Core implementation complete

## Notes
- All file operations must maintain PHI tracking
- Web server must never store files locally
- All cleanup operations controlled by application logic
- Testing must work on single machine for development