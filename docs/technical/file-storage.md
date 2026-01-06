# File Storage System

## Overview
NA-ACCORD uses a multi-tier storage system to handle file uploads, processing, and long-term storage. Files move through several stages from upload to final storage.

## Storage Locations

### 1. Temporary Upload Storage
**Location**: `/tmp/` or configured temp directory
**Purpose**: Initial file upload before processing
**Lifetime**: Deleted after processing or on failure

### 2. Processing Storage
**Location**: System temp directory (e.g., `/var/folders/...`)
**Purpose**: Working directory for validation processing
**Contents**:
- Uploaded CSV/TXT file
- Converted DuckDB file
- Generated Quarto reports
**Lifetime**: Deleted after NAS storage upload

### 3. Permanent Storage (NAS)
**Location**: NAS network storage (driver architecture supports future S3-compatible migration)
**Directory Structure**:
```
naaccord-data/
├── submissions/
│   ├── {submission_id}/
│   │   ├── files/
│   │   │   ├── {file_id}_{timestamp}_{filename}
│   │   ├── reports/
│   │   │   ├── {audit_id}_report.html
│   │   └── attachments/
│   │       ├── {attachment_id}_{filename}
```

## File Upload Process

### Step 1: Initial Upload
```python
# depot/views/submissions.py - table_manage()
if 'patient-file' in request.FILES:
    file = request.FILES['patient-file']
    
    # Create TemporaryFile record
    temp_file = TemporaryFile.objects.create(
        cohort=submission.cohort,
        uploaded_by=request.user,
        file_name=file.name,
        file_path=None,  # Set after saving
        file_size=file.size,
        content_type=file.content_type
    )
    
    # Save to disk
    fs = FileSystemStorage(location=settings.TEMP_UPLOAD_PATH)
    filename = fs.save(f"{temp_file.id}_{file.name}", file)
    temp_file.file_path = fs.path(filename)
    temp_file.save()
```

### Step 2: Create Audit Record
```python
# depot/models/audit.py
audit = Audit.objects.create(
    cohort=submission.cohort,
    data_file_type=data_file_type,
    temp_file=temp_file,
    requested_by=request.user,
    submission=submission,
    cohort_submission_file=cohort_file,
    status='pending'
)
```

### Step 3: Trigger Background Processing
```python
# depot/tasks/audit.py
from celery import shared_task

@shared_task
def process_audit(audit_id):
    audit = Audit.objects.get(id=audit_id)
    
    # Read file from temp storage
    with open(audit.temp_file.file_path, 'r') as f:
        content = f.read()
    
    # Process through validation pipeline
    # ... validation logic ...

    # Upload to NAS storage
    storage_key = upload_to_storage(audit, processed_file_path)
    audit.storage_key = storage_key
    audit.save()
```

## File Retrieval

### For Viewing/Download
```python
# depot/views/files.py
def download_file(request, file_id):
    file = CohortSubmissionFile.objects.get(id=file_id)
    
    if file.temp_file and file.temp_file.file_path:
        # Still in temp storage
        return FileResponse(
            open(file.temp_file.file_path, 'rb'),
            as_attachment=True,
            filename=file.file_name
        )
    elif file.storage_key:
        # In NAS storage - use StorageManager
        storage = StorageManager.get_submission_storage()
        file_content = storage.get_file(file.storage_key)

        return FileResponse(
            file_content,
            as_attachment=True,
            filename=file.file_name
        )
```

### For Validation Reports
```python
# depot/models/audit.py
class Audit(models.Model):
    def get_report_url(self):
        if self.storage_key:
            # Use StorageManager for abstraction (NAS or future S3)
            storage = StorageManager.get_submission_storage()
            return storage.url(f"reports/{self.id}_report.html")
        return None
```

## Database Schema

### TemporaryFile Model
```python
class TemporaryFile(models.Model):
    cohort = models.ForeignKey(Cohort)
    uploaded_by = models.ForeignKey(User)
    file_name = models.CharField(max_length=255)
    file_path = models.TextField()  # Full path to temp file
    file_size = models.BigIntegerField()
    content_type = models.CharField(max_length=100)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
```

### CohortSubmissionFile Model
```python
class CohortSubmissionFile(models.Model):
    submission = models.ForeignKey(CohortSubmission)
    data_file_type = models.ForeignKey(DataFileType)
    temp_file = models.ForeignKey(TemporaryFile, null=True)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    version = models.IntegerField(default=1)
    storage_key = models.CharField(max_length=500, null=True)  # Path in NAS storage
    uploaded_at = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(blank=True)
```

## File Cleanup

### Temporary File Cleanup
```python
# depot/tasks/cleanup.py
@shared_task
def cleanup_temp_files():
    """Run daily to clean up old temp files"""
    cutoff = timezone.now() - timedelta(days=7)
    
    old_files = TemporaryFile.objects.filter(
        uploaded_at__lt=cutoff,
        processed=True,
        deleted=False
    )
    
    for temp_file in old_files:
        if os.path.exists(temp_file.file_path):
            os.remove(temp_file.file_path)
        temp_file.deleted = True
        temp_file.save()
```

## Security Considerations

### File Validation
- Check file extensions (.csv, .txt only)
- Verify MIME types
- Scan for malicious content
- Limit file sizes (configurable, default 2GB)

### Access Control
- Files are never directly web-accessible
- All downloads go through Django views with permission checks
- NAS storage accessed via StorageManager abstraction (supports future S3 migration with pre-signed URLs)
- Audit trail for all file access

### Data Sanitization
- Remove any detected PHI/PII if configured
- Validate against data definitions
- Ensure patient ID anonymization

## Storage Configuration

### Django Settings
```python
# settings.py

# Temporary upload directory
TEMP_UPLOAD_PATH = '/tmp/naaccord_uploads/'

# NAS Storage Configuration
NAS_STORAGE_PATH = env('NAS_STORAGE_PATH', default='/mnt/nas/naaccord')

# Future S3 Configuration (not currently used - driver architecture supports migration)
# AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
# AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
# AWS_STORAGE_BUCKET_NAME = env('AWS_BUCKET', default='naaccord-data')
# AWS_S3_REGION_NAME = env('AWS_REGION', default='us-east-1')
# AWS_S3_FILE_OVERWRITE = False
# AWS_DEFAULT_ACL = None  # Private by default

# Max file sizes
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
```

## Monitoring and Logging

### File Upload Tracking
```python
# depot/models/audit_log.py
class FileAccessLog(models.Model):
    user = models.ForeignKey(User)
    file = models.ForeignKey(CohortSubmissionFile)
    action = models.CharField(max_length=50)  # upload, download, delete
    ip_address = models.GenericIPAddressField()
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField()
```

### Storage Metrics
- Monitor temp directory disk usage
- Monitor NAS storage capacity and usage
- Alert on failed uploads
- Log all file operations

## Storage Implementation Details

### Storage Configuration
The system uses a configurable storage backend defined in `depot/settings.py`:

```python
STORAGE_CONFIG = {
    'disks': {
        'local': {
            'driver': 'local',
            'type': 'local',
            'root': str(BASE_DIR / 'storage' / 'nas'),  # Local development path
        },
        'nas': {
            'driver': 'local',
            'type': 'local',
            'root': '/mnt/nas/naaccord',  # Production NAS mount
        }
    }
}

SUBMISSION_STORAGE_DISK = 'local'  # Development
# SUBMISSION_STORAGE_DISK = 'nas'  # Production

# Note: Driver architecture supports future S3-compatible migration
# Example S3 configuration (not currently used):
# 'data': {
#     'driver': 's3',
#     'type': 's3',
#     'bucket': 'naaccord-data',
# }
```

### Storage Backends
1. **Local Storage** (Development): Files stored in `/storage/nas/` directory
2. **NAS Storage** (Production): Network-attached storage mounted at `/mnt/nas/naaccord`
3. **Future S3 Support**: Driver architecture supports S3-compatible migration if needed

## Example: Patient File Upload (Submission 8)

For patient file `patient_sim_data_values_only.csv` in submission 8:

### 1. File Upload Process
When uploaded via `/submissions/8/patient/` endpoint:

```python
# depot/views/submissions/table_manage.py
storage_path = file_service.build_storage_path(
    cohort_id=submission.cohort.id,        # e.g., 1
    cohort_name=submission.cohort.name,    # e.g., "Test_Cohort"
    protocol_year=submission.protocol_year.year,  # e.g., "2025"
    file_type=data_file_type.name,         # "patient"
    filename=uploaded_file.name             # "patient_sim_data_values_only.csv"
)
# Result: "1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv"
```

### 2. Physical Storage Locations

#### Local Development Storage
```
/Users/erikwestlund/code/naaccord/storage/nas/
├── 1_Test_Cohort/
│   └── 2025/
│       └── patient/
│           ├── v1_patient_sim_data_values_only.csv     # Version 1
│           ├── v2_patient_sim_data_values_only.csv     # Version 2 (if updated)
│           └── attachments/
│               └── data_dictionary.pdf                 # Optional attachments
```

#### Temporary Processing Storage
```
/tmp/naaccord_workspace/
├── processing/
│   └── 1731234567.89_patient_sim_data_values_only.csv  # Temporary copy
└── audit/
    └── temp_8_patient.duckdb                           # DuckDB conversion
```

### 3. Database Records Created

#### UploadedFile Record
```python
UploadedFile.objects.create(
    filename="patient_sim_data_values_only.csv",
    storage_path="1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv",
    uploader=user,
    type=UploadType.RAW,
    file_hash="sha256_hash_here",
    file_size=12345678,
    content_type="text/csv"
)
```

#### PHIFileTracking Audit Trail
```python
PHIFileTracking.log_operation(
    cohort=submission.cohort,
    user=user,
    action='nas_raw_created',
    file_path="1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv",
    file_type='raw_csv',
    file_size=12345678,
    content_object=submission
)
```

#### DataTableFile Record
```python
DataTableFile.objects.create(
    data_table=data_table,  # CohortSubmissionDataTable instance
    uploaded_file=uploaded_file_record,
    version=1,
    name="Patient Demographics Data",
    comments="Initial upload for 2025 submission"
)
```

### 4. Processing Workflow
```
1. Raw CSV stored: storage/nas/1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv
2. Copied to workspace: /tmp/naaccord_workspace/processing/[timestamp]_patient_sim_data_values_only.csv
3. Converted to DuckDB: /tmp/naaccord_workspace/audit/temp_8_patient.duckdb
4. DuckDB stored: storage/nas/1_Test_Cohort/2025/patient/duckdb/patient_8.duckdb
5. Report generated: storage/nas/1_Test_Cohort/2025/patient/reports/audit_8_report.html
6. Workspace files cleaned up (tracked in PHIFileTracking)
```

### 5. File Retrieval

#### Direct Access (Development)
```python
# File path for local storage
file_path = "storage/nas/1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv"

# Read directly from filesystem
with open(file_path, 'r') as f:
    content = f.read()
```

#### Storage Manager Access
```python
# Using StorageManager for abstraction
storage = StorageManager.get_submission_storage()
content = storage.get_file("1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv")
```

#### Web Access URL Generation
```python
# Using StorageManager abstraction (NAS or future S3)
storage = StorageManager.get_submission_storage()
url = storage.url('1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv')

# Future S3 support would enable presigned URLs:
# url = storage.client.generate_presigned_url(
#     'get_object',
#     Params={
#         'Bucket': 'naaccord-data',
#         'Key': '1_Test_Cohort/2025/patient/v1_patient_sim_data_values_only.csv'
#     },
#     ExpiresIn=3600  # 1 hour expiry
# )
```

### 6. Validation Report Storage
```
storage/nas/1_Test_Cohort/2025/patient/reports/
├── audit_8_report.html              # Main validation report
├── audit_8_report_files/            # Supporting files
│   ├── plotly_graph_1.json         # Interactive visualizations
│   └── summary_stats.json          # Statistical summaries
```

## File Tracking and Cleanup

### PHIFileTracking Records
Every file operation creates an audit record:
- `nas_raw_created`: Original file stored
- `work_copy_created`: File copied to workspace
- `conversion_started`: DuckDB conversion begins
- `nas_duckdb_created`: DuckDB file stored
- `nas_report_created`: Report generated
- `work_copy_deleted`: Workspace file cleaned up

### Cleanup Verification
```python
# Check for uncleaned files
uncleaned = PHIFileTracking.get_uncleaned_workspace_files()
for record in uncleaned:
    if record.is_cleanup_overdue:
        # Alert or force cleanup
        logger.warning(f"Overdue cleanup: {record.file_path}")
```