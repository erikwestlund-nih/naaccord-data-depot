# PHI File Tracking System

## Overview

The PHIFileTracking system provides comprehensive audit trail capabilities for all Protected Health Information (PHI) file operations in NA-ACCORD. This system ensures HIPAA compliance by tracking every movement, creation, modification, and deletion of PHI data across the platform's multi-server architecture.

## Architecture

### Core Model: PHIFileTracking

The PHIFileTracking model (`depot/models/phifiletracking.py`) serves as the central audit log for all PHI file operations. Every file operation that involves PHI data creates a tracking record to maintain complete accountability.

```python
# Example: Logging a file operation
PHIFileTracking.log_operation(
    cohort=cohort,
    user=user,
    action='nas_raw_created',
    file_path='/mnt/nas/submissions/cohort_123/patient_data.csv',
    file_type='raw_csv',
    file_size=1024000,
    content_object=audit_instance
)
```

### Tracked Operations

#### NAS Operations
- `nas_raw_created` - Raw file created on NAS storage
- `nas_raw_deleted` - Raw file deleted from NAS storage
- `nas_duckdb_created` - DuckDB file created on NAS storage
- `nas_duckdb_deleted` - DuckDB file deleted from NAS storage
- `nas_report_created` - Report created on NAS storage
- `nas_report_deleted` - Report deleted from NAS storage

#### Workspace Operations
- `work_copy_created` - File copied to workspace for processing
- `work_copy_deleted` - File deleted from workspace after processing

#### Processing Operations
- `conversion_started` - File conversion to DuckDB initiated
- `conversion_completed` - File conversion completed successfully
- `conversion_failed` - File conversion failed with error
- `patient_id_extraction_started` - Patient ID extraction initiated
- `patient_id_extraction_completed` - Patient ID extraction completed
- `patient_id_extraction_failed` - Patient ID extraction failed

#### Streaming Operations
- `file_uploaded_via_stream` - File uploaded via streaming API
- `file_uploaded_chunked` - File uploaded in chunks
- `file_downloaded_via_stream` - File downloaded via streaming
- `file_deleted_via_api` - File deleted via internal API
- `prefix_deleted_via_api` - Directory prefix deleted via API
- `scratch_cleanup` - Scratch directory cleanup operation

## Key Features

### 1. Complete Audit Trail

Every PHI file operation is tracked with:
- **User accountability** - Who performed the operation
- **Cohort association** - Which cohort the data belongs to
- **Timestamp** - When the operation occurred
- **File details** - Path, size, type, and SHA256 hash
- **Server tracking** - Which server performed the operation
- **Error logging** - Detailed error messages for failed operations

### 2. Cleanup Management

The system includes sophisticated cleanup tracking:

```python
# Check for files requiring cleanup
overdue_files = PHIFileTracking.get_overdue_cleanups()

# Mark file as cleaned up
tracking_record.mark_cleaned_up(user=request.user)
```

**Cleanup Fields:**
- `cleanup_required` - Whether file needs cleanup
- `expected_cleanup_by` - When file should be cleaned up
- `cleanup_attempted_count` - Number of cleanup attempts
- `cleaned_up` - Whether cleanup is verified complete
- `cleanup_verified_at` - When cleanup was verified
- `cleanup_verified_by` - User who verified cleanup

### 3. Orphan Detection

Tracks process IDs to detect orphaned files:
- `parent_process_id` - Process that created the file
- Enables detection of files left behind by crashed processes
- Supports automated cleanup of orphaned temporary files

### 4. Multi-Server Support

Designed for the two-server NA-ACCORD architecture:
- `server_hostname` - Automatically populated with server name
- `server_role` - web/services/testing role identification
- Tracks file movements between servers

## Management Commands

### Show Audit Trail

```bash
# Show recent operations
python manage.py show_phi_audit_trail

# Filter by cohort
python manage.py show_phi_audit_trail --cohort 5

# Filter by file pattern
python manage.py show_phi_audit_trail --file "*/patient_data*"

# Show specific data file trail
python manage.py show_phi_audit_trail --data-file 123

# Filter by action type
python manage.py show_phi_audit_trail --action nas_raw_created
```

**Output includes:**
- Chronological timeline of file operations
- Color-coded action types (create/delete/error)
- File size and status indicators
- Error messages and cleanup status
- Summary statistics by operation type

### Verify PHI Integrity

```bash
# Verify all PHI files
python manage.py verify_phi_integrity

# Verify specific cohort
python manage.py verify_phi_integrity --cohort 5

# Verify with hash checking (slower but thorough)
python manage.py verify_phi_integrity --check-hashes
```

**Verification includes:**
- Check NAS file existence against tracking records
- Verify file hashes for corruption detection
- Validate DataTableFile consistency
- Identify missing DuckDB conversions
- Report files without tracking records

### Cleanup Verification

```bash
# Verify cleanup completion
python manage.py verify_phi_cleanup

# Force cleanup of specific files
python manage.py cleanup_upload_prechecks --force
```

## Integration Points

### 1. StorageManager Integration

The PHIFileTracking system integrates with StorageManager to track all file operations:

```python
# Example from storage operations
def store_file(self, file_path, content):
    # Store the file
    result = storage.put_file(file_path, content)

    # Log the operation
    PHIFileTracking.log_operation(
        cohort=self.cohort,
        user=self.user,
        action='nas_raw_created',
        file_path=file_path,
        file_type='raw_csv',
        content_object=self
    )
```

### 2. Audit System Integration

Audit processing automatically creates tracking records:

```python
# From audit processing workflow
def process_duckdb_conversion(self):
    try:
        # Log conversion start
        PHIFileTracking.log_operation(
            cohort=self.cohort,
            user=self.user,
            action='conversion_started',
            file_path=self.duckdb_path,
            content_object=self
        )

        # Perform conversion
        result = self.convert_to_duckdb()

        # Log successful completion
        PHIFileTracking.log_operation(
            cohort=self.cohort,
            user=self.user,
            action='conversion_completed',
            file_path=self.duckdb_path,
            file_size=result.size,
            content_object=self
        )

    except Exception as e:
        # Log failure
        PHIFileTracking.log_operation(
            cohort=self.cohort,
            user=self.user,
            action='conversion_failed',
            file_path=self.duckdb_path,
            error_message=str(e),
            content_object=self
        )
```

### 3. Celery Task Integration

Background tasks automatically track file operations:

```python
@shared_task
def process_upload_precheck(audit_id):
    audit = Audit.objects.get(id=audit_id)

    # Track workspace file creation
    PHIFileTracking.log_operation(
        cohort=audit.cohort,
        user=audit.user,
        action='work_copy_created',
        file_path=workspace_path,
        cleanup_required=True,
        expected_cleanup_by=timezone.now() + timedelta(hours=2)
    )

    try:
        # Process the file
        result = process_file(workspace_path)

    finally:
        # Track workspace cleanup
        PHIFileTracking.log_operation(
            cohort=audit.cohort,
            user=audit.user,
            action='work_copy_deleted',
            file_path=workspace_path
        )
```

## HIPAA Compliance Features

### 1. Complete Accountability

- **User Tracking**: Every operation linked to authenticated user
- **Timestamp Precision**: Microsecond-level timestamps
- **Action Documentation**: Detailed operation descriptions
- **Error Logging**: Complete error messages for audit purposes

### 2. Data Integrity

- **File Hashing**: SHA256 hashes for corruption detection
- **Size Tracking**: File size validation
- **Existence Verification**: Regular integrity checks

### 3. Retention and Cleanup

- **Mandatory Cleanup**: Temporary files must be tracked and cleaned
- **Verification Requirements**: Cleanup must be verified and logged
- **Overdue Detection**: Automated detection of cleanup failures

### 4. Multi-Server Audit

- **Server Identification**: Every operation tagged with server hostname
- **Role Tracking**: Server role (web/services) recorded
- **Cross-Server Verification**: Validate file movements between servers

## Security Considerations

### 1. Access Control

- Records are created automatically by system operations
- Read access restricted to authorized administrators
- Modification requires special permissions

### 2. Data Protection

- No PHI content stored in tracking records
- Only file paths and metadata tracked
- Hashes provide integrity without exposing content

### 3. Audit Immutability

- Tracking records should not be deleted
- Updates limited to cleanup verification
- Complete historical trail maintained

## Performance Considerations

### 1. Database Indexing

Optimized indexes for common queries:
- `cohort + action` - Cohort-specific operations
- `file_path` - File-specific queries
- `cleaned_up + action` - Cleanup status queries
- `cleanup_required + created_at` - Pending cleanup queries

### 2. Batch Operations

For high-volume operations:
- Use `bulk_create()` for multiple tracking records
- Consider async logging for performance-critical paths
- Regular cleanup of old tracking records

### 3. Storage Efficiency

- JSON metadata field for extensible tracking
- Efficient action choice enumeration
- Optimized field lengths for common data

## Best Practices

### 1. Always Track File Operations

```python
# GOOD: Track every file operation
def create_file(self, content):
    file_path = self.store_content(content)
    PHIFileTracking.log_operation(...)
    return file_path

# BAD: Missing tracking
def create_file(self, content):
    return self.store_content(content)  # No tracking!
```

### 2. Use Appropriate Action Types

```python
# GOOD: Specific action type
PHIFileTracking.log_operation(action='nas_raw_created', ...)

# BAD: Generic action
PHIFileTracking.log_operation(action='file_created', ...)  # Too vague
```

### 3. Include Error Context

```python
# GOOD: Detailed error logging
except Exception as e:
    PHIFileTracking.log_operation(
        action='conversion_failed',
        error_message=f"DuckDB conversion failed: {str(e)}",
        ...
    )

# BAD: Missing error context
except Exception as e:
    PHIFileTracking.log_operation(action='conversion_failed', ...)
```

### 4. Set Cleanup Expectations

```python
# GOOD: Set cleanup timeline
PHIFileTracking.log_operation(
    action='work_copy_created',
    cleanup_required=True,
    expected_cleanup_by=timezone.now() + timedelta(hours=2)
)

# BAD: No cleanup planning
PHIFileTracking.log_operation(action='work_copy_created')
```

## Monitoring and Alerting

### 1. Regular Integrity Checks

Run verification commands regularly:
```bash
# Daily integrity check
python manage.py verify_phi_integrity

# Weekly hash verification
python manage.py verify_phi_integrity --check-hashes
```

### 2. Cleanup Monitoring

Monitor for overdue cleanups:
```python
# Check for overdue cleanups
overdue = PHIFileTracking.get_overdue_cleanups()
if overdue.exists():
    # Alert administrators
    send_cleanup_alert(overdue)
```

### 3. Volume Monitoring

Track operation volume for anomaly detection:
```python
# Daily operation counts
daily_ops = PHIFileTracking.objects.filter(
    created_at__date=timezone.now().date()
).count()

# Alert on unusual volume
if daily_ops > normal_threshold:
    send_volume_alert(daily_ops)
```

## Related Documentation

- [Storage Manager Abstraction](../technical/storage-manager-abstraction.md)
- [Upload Submission Workflow](../technical/upload-submission-workflow.md)
- [Security Architecture](../security/security-overview.md)
- [HIPAA Compliance Guide](../security/compliance-checklist.md)

## Implementation Files

- **Model**: `depot/models/phifiletracking.py`
- **Management Commands**:
  - `depot/management/commands/show_phi_audit_trail.py`
  - `depot/management/commands/verify_phi_integrity.py`
  - `depot/management/commands/verify_phi_cleanup.py`
- **Integration**: Multiple files across audit, storage, and task systems
- **Tests**: `depot/tests/test_duckdb_phi_tracking.py`