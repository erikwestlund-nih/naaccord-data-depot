# Upload Submission Workflow

## Overview

The Upload Submission system enables cohorts to submit complete datasets across multiple file types for a given submission wave. This sophisticated workflow builds on the existing audit system to provide validation while allowing flexible submission with documented issues, version tracking, and comprehensive patient ID validation.

## Architecture

### Core Model Hierarchy

```
CohortSubmission
├── CohortSubmissionDataTable (one per data file type)
│   ├── DataTableFile (version tracking for each file)
│   ├── DataTableReview (validation tracking)
│   └── FileAttachment (supporting documents)
└── CohortSubmissionPatientIDs (extracted patient IDs)
```

### Workflow States

```
draft → in_progress → completed → signed_off
  ↑                                  ↓
  └── reopen (admin only) ←──────────┘
```

## Key Workflow Requirements

### 1. Patient File First Rule

**Critical Constraint**: Patient files must be uploaded before any other data files.

```python
def can_upload_file(self, user):
    # For non-patient tables, check if patient file exists
    if not is_patient_table and not self.submission.has_patient_file():
        return False, "Patient file must be uploaded first"
```

**Rationale**: Patient files establish the cohort's patient ID universe, enabling validation of all subsequent files.

### 2. Flexible Upload Order

After patient file upload:
- Other files can be uploaded in any order
- Files can be skipped with documented reasons
- Multiple versions of each file are supported

### 3. Warning-Based Validation

Unlike the strict audit system:
- Issues generate warnings but don't block submission
- Cohorts can acknowledge warnings and proceed
- Final sign-off requires explicit acknowledgment

## Core Models

### CohortSubmission

**Purpose**: Tracks overall submission for a cohort/wave combination

```python
class CohortSubmission(BaseModel):
    protocol_year = models.ForeignKey('ProtocolYear', ...)
    cohort = models.ForeignKey('Cohort', ...)
    started_by = models.ForeignKey('User', ...)

    # Status tracking
    status = models.CharField(choices=STATUS_CHOICES, default='draft')

    # Patient ID tracking
    patient_ids = models.JSONField(default=list)
    patient_file_processed = models.BooleanField(default=False)

    # Validation settings
    validation_mode = models.CharField(choices=['permissive', 'strict'])
    validation_threshold = models.IntegerField(default=0)

    # Final sign-off
    final_acknowledged = models.BooleanField(default=False)
    signed_off = models.DateTimeField(null=True)
    closed_at = models.DateTimeField(null=True)
```

**Key Methods**:
- `has_patient_file()` - Check if patient file uploaded
- `can_accept_files(user)` - Permission and status checks
- `mark_signed_off(user)` - Final submission completion

### CohortSubmissionDataTable

**Purpose**: Represents individual data table (patient, laboratory, etc.) within submission

```python
class CohortSubmissionDataTable(BaseModel):
    submission = models.ForeignKey('CohortSubmission', ...)
    data_file_type = models.ForeignKey('DataFileType', ...)

    # Status tracking
    status = models.CharField(choices=STATUS_CHOICES, default='not_started')

    # Skip functionality
    is_skipped = models.BooleanField(default=False)
    skip_reason = models.TextField(blank=True)
    not_available = models.BooleanField(default=False)

    # Sign-off tracking (table level)
    signed_off = models.BooleanField(default=False)
    signed_off_by = models.ForeignKey('User', ...)
    sign_off_comments = models.TextField(blank=True)

    # Validation aggregates
    validation_warnings = models.JSONField(default=dict)
    patient_id_mismatches = models.JSONField(default=list)
    warning_count = models.IntegerField(default=0)
```

**Key Features**:
- **Skip with reason**: Tables can be marked as skipped or not available
- **Table-level sign-off**: Each table signed off independently
- **Validation aggregation**: Warnings collected from all file versions

### DataTableFile

**Purpose**: Individual file within data table, supporting versioning

```python
class DataTableFile(BaseModel):
    data_table = models.ForeignKey('CohortSubmissionDataTable', ...)

    # File identity and versioning
    name = models.CharField(max_length=255, blank=True)
    version = models.IntegerField(default=1)
    is_current = models.BooleanField(default=True)

    # File references
    uploaded_file = models.ForeignKey('UploadedFile', ...)
    upload_precheck = models.ForeignKey('UploadPrecheck', ...)

    # Storage paths
    raw_file_path = models.CharField(max_length=500)
    duckdb_file_path = models.CharField(max_length=500)

    # Per-file validation
    validation_warnings = models.JSONField(default=dict)
    patient_id_mismatches = models.JSONField(default=list)
    warning_count = models.IntegerField(default=0)
```

**Version Management**:
```python
def create_new_version(self, user, uploaded_file):
    # Mark current version as not current
    self.version += 1
    self.is_current = True
    self.uploaded_file = uploaded_file

    # Clear previous validation results
    self.validation_warnings = {}
    self.warning_count = 0

    # Clear parent table sign-off
    if self.data_table.signed_off:
        self.data_table.clear_sign_off()
```

## Patient ID Validation System

### Patient ID Extraction

When patient files are uploaded:

1. **Automatic Processing**: DuckDB conversion extracts all patient IDs
2. **Storage**: Patient IDs stored in `CohortSubmissionPatientIDs` model
3. **Validation**: Duplicate detection and statistics calculation
4. **Reference**: Becomes validation universe for other files

```python
# Patient ID extraction process
def process_patient_file(submission, uploaded_file):
    # Convert to DuckDB
    duckdb_path = convert_to_duckdb(uploaded_file)

    # Extract patient IDs
    patient_ids = extract_patient_ids_from_duckdb(duckdb_path)

    # Store and validate
    patient_record = CohortSubmissionPatientIDs.objects.create(
        submission=submission,
        patient_ids=patient_ids,
        patient_count=len(set(patient_ids)),
        has_duplicates=len(patient_ids) != len(set(patient_ids))
    )

    # Mark submission as having patient file
    submission.patient_file_processed = True
    submission.save()
```

### Cross-File Validation

Non-patient files validated against patient ID universe:

```python
def validate_against_patient_ids(data_file, submission):
    # Get patient ID universe
    patient_universe = set(submission.patient_ids)

    # Extract IDs from current file
    file_patient_ids = extract_patient_ids_from_duckdb(data_file.duckdb_path)

    # Calculate validation metrics
    matching = patient_universe & file_patient_ids
    out_of_bounds = file_patient_ids - patient_universe

    # Store results
    validation_record = DataTableFilePatientIDs.objects.create(
        data_file=data_file,
        patient_ids=list(file_patient_ids),
        validation_status='validated' if not out_of_bounds else 'has_warnings'
    )

    # Update file validation warnings
    if out_of_bounds:
        data_file.patient_id_mismatches = list(out_of_bounds)
        data_file.warning_count += len(out_of_bounds)
        data_file.save()
```

### Validation Metrics

Comprehensive patient ID validation metrics:

```python
def get_patient_validation_metrics(self):
    # Per-file metrics
    file_metrics = []
    for file_record in patient_records:
        file_patient_ids = set(file_record.patient_ids)
        matching = patient_universe & file_patient_ids
        out_of_bounds = file_patient_ids - patient_universe

        file_metrics.append({
            'file_name': file_record.data_file.name,
            'total': len(file_patient_ids),
            'matching_count': len(matching),
            'matching_percent': len(matching) / len(file_patient_ids) * 100,
            'out_of_bounds_count': len(out_of_bounds),
            'validation_status': file_record.validation_status
        })

    # Aggregate metrics
    return {
        'total_patient_file': len(patient_universe),
        'total_uploaded': len(all_uploaded_ids),
        'coverage_percent': coverage,  # How much of patient file covered
        'validation_percent': validation,  # What % of uploads are valid
        'file_metrics': file_metrics
    }
```

## Upload Workflow Process

### 1. Submission Creation

```python
# Create new submission
submission = CohortSubmission.objects.create(
    protocol_year=protocol_year,
    cohort=cohort,
    started_by=user,
    status='draft'
)

# Create data tables for all file types
for file_type in DataFileType.objects.filter(active=True):
    CohortSubmissionDataTable.objects.create(
        submission=submission,
        data_file_type=file_type,
        status='not_started'
    )
```

### 2. Patient File Upload (Required First)

```python
def upload_patient_file(submission, user, uploaded_file):
    # Get patient data table
    patient_table = submission.get_patient_data_table()

    # Validate upload permission
    can_upload, error = patient_table.validate_file_upload(uploaded_file, user)
    if not can_upload:
        raise ValidationError(error)

    # Create file record
    data_file = DataTableFile.objects.create(
        data_table=patient_table,
        uploaded_file=uploaded_file,
        uploaded_by=user,
        original_filename=uploaded_file.filename
    )

    # Trigger processing pipeline
    trigger_upload_precheck.delay(data_file.id)

    return data_file
```

### 3. Processing Pipeline

```python
@shared_task
def process_submission_file(data_file_id):
    data_file = DataTableFile.objects.get(id=data_file_id)

    # Convert to DuckDB with PHI tracking
    duckdb_path = convert_to_duckdb_with_tracking(data_file)
    data_file.duckdb_file_path = duckdb_path
    data_file.duckdb_created_at = timezone.now()

    # Extract patient IDs if patient file
    if data_file.data_table.data_file_type.name.lower() == 'patient':
        extract_patient_ids_for_submission(data_file)
    else:
        # Validate against existing patient IDs
        validate_patient_ids_cross_file(data_file)

    # Generate validation report
    create_validation_report(data_file)

    # Update table status
    data_file.data_table.update_status('completed')

    data_file.save()
```

### 4. Other File Uploads

```python
def upload_other_file(submission, file_type, user, uploaded_file):
    # Verify patient file exists
    if not submission.has_patient_file():
        raise ValidationError("Patient file must be uploaded first")

    # Get or create data table
    data_table = submission.data_tables.get(data_file_type=file_type)

    # Check for existing files (versioning)
    existing_files = data_table.get_current_files()

    if existing_files.exists():
        # Create new version
        existing_file = existing_files.first()
        data_file = existing_file.create_new_version(user, uploaded_file)
    else:
        # Create first file
        data_file = DataTableFile.objects.create(
            data_table=data_table,
            uploaded_file=uploaded_file,
            uploaded_by=user
        )

    # Trigger processing
    trigger_upload_precheck.delay(data_file.id)

    return data_file
```

### 5. Table Sign-off

```python
def sign_off_data_table(data_table, user, comments=''):
    # Validate all files are processed
    for file in data_table.get_current_files():
        if not file.upload_precheck or file.upload_precheck.status != 'completed':
            raise ValidationError("All files must be processed before sign-off")

    # Mark table as signed off
    data_table.mark_signed_off(user, comments)

    # Check if all tables are signed off
    submission = data_table.submission
    unsigned_tables = submission.data_tables.filter(
        signed_off=False,
        is_skipped=False,
        not_available=False
    )

    if not unsigned_tables.exists():
        # All tables complete, enable final sign-off
        submission.status = 'completed'
        submission.save()
```

### 6. Final Submission Sign-off

```python
def final_sign_off(submission, user, comments=''):
    # Validate all required tables are signed off or skipped
    incomplete_tables = submission.data_tables.filter(
        signed_off=False,
        is_skipped=False,
        not_available=False
    )

    if incomplete_tables.exists():
        raise ValidationError("All data tables must be completed or skipped")

    # Final acknowledgment
    submission.final_comments = comments
    submission.mark_signed_off(user)

    # Generate final submission report
    generate_submission_summary_report.delay(submission.id)
```

## File Versioning System

### Version Management

Each `DataTableFile` supports versioning:

```python
# File versioning workflow
class DataTableFile(BaseModel):
    version = models.IntegerField(default=1)
    is_current = models.BooleanField(default=True)

    def create_new_version(self, user, uploaded_file):
        # Mark current as not current
        DataTableFile.objects.filter(
            data_table=self.data_table,
            id=self.id,
            is_current=True
        ).update(is_current=False)

        # Increment version
        self.version += 1
        self.is_current = True
        self.uploaded_file = uploaded_file

        # Clear previous validation
        self.validation_warnings = {}
        self.warning_count = 0

        # Clear parent table sign-off
        if self.data_table.signed_off:
            self.data_table.clear_sign_off()

        self.save()
```

### Version Display

UI shows version history:

```python
def get_file_version_history(data_table):
    """Get version history for data table files."""
    files = DataTableFile.objects.filter(
        data_table=data_table
    ).order_by('-version')

    return [{
        'version': file.version,
        'is_current': file.is_current,
        'uploaded_by': file.uploaded_by.username,
        'uploaded_at': file.uploaded_at,
        'filename': file.original_filename,
        'warnings': file.warning_count,
        'has_report': bool(file.upload_precheck)
    } for file in files]
```

## Skip and Not Available System

### Skip Functionality

Tables can be skipped with documented reasons:

```python
def skip_data_table(data_table, user, reason):
    """Skip a data table with documented reason."""
    data_table.mark_skipped(user, reason)

    # Update submission progress
    check_submission_completion(data_table.submission)

def mark_not_available(data_table, user, reason=''):
    """Mark table as not available (cohort doesn't collect this data)."""
    data_table.mark_not_available(user, reason)

    # Update submission progress
    check_submission_completion(data_table.submission)
```

### Skip Types

- **Skipped**: Temporary skip with reason (can be un-skipped)
- **Not Available**: Permanent - cohort doesn't collect this data type
- **Not Required**: Administrative flag - not required for this cohort

## Validation and Warning System

### Multi-Level Validation

1. **File Level**: Individual file validation warnings
2. **Table Level**: Aggregated warnings from all file versions
3. **Submission Level**: Overall submission health

```python
# Validation aggregation
def aggregate_validation_warnings(data_table):
    """Aggregate warnings from all current files."""
    all_warnings = {}
    total_count = 0

    for file in data_table.get_current_files():
        if file.validation_warnings:
            all_warnings[file.name or f"File {file.id}"] = file.validation_warnings
            total_count += file.warning_count

    data_table.validation_warnings = all_warnings
    data_table.warning_count = total_count
    data_table.save()
```

### Warning Types

- **Patient ID Mismatches**: IDs not in patient file
- **Data Validation**: Field format/value issues
- **Missing Required Fields**: Required columns absent
- **Duplicate Records**: Within-file duplicates

## Integration with PHI Tracking

All file operations create PHI tracking records:

```python
def save_submission_file_with_tracking(submission_file, content):
    """Save submission file with comprehensive PHI tracking."""

    # Save via StorageManager
    storage = StorageManager.get_submission_storage()
    path = storage.save(submission_file.nas_path, content)

    # Create PHI tracking record
    PHIFileTracking.log_operation(
        cohort=submission_file.submission.cohort,
        user=submission_file.uploaded_by,
        action='nas_raw_created',
        file_path=path,
        file_type='submission_file',
        content_object=submission_file
    )

    return path
```

## Security and Access Control

### Permission Checks

```python
class SubmissionPermissions:
    @staticmethod
    def can_view(user, submission):
        """Check if user can view submission."""
        # Cohort membership required
        return user.cohorts.filter(id=submission.cohort.id).exists()

    @staticmethod
    def can_edit(user, submission):
        """Check if user can edit submission."""
        # Must be cohort member and submission not closed
        if not SubmissionPermissions.can_view(user, submission):
            return False

        return submission.status not in ['signed_off', 'closed']

    @staticmethod
    def can_sign_off(user, submission):
        """Check if user can sign off submission."""
        # Must have edit permission and be site admin
        if not SubmissionPermissions.can_edit(user, submission):
            return False

        return user.groups.filter(name='site_admin').exists()
```

### Audit Trail

Complete audit trail via RevisionMixin:

```python
# Automatic revision tracking
def save_revision(self, user, action_type):
    """Save revision record for audit trail."""
    Revision.objects.create(
        content_object=self,
        user=user,
        action_type=action_type,
        changed_fields=self.get_changed_fields(),
        timestamp=timezone.now()
    )
```

## API Endpoints

### Core Submission Endpoints

```python
# REST API endpoints
GET    /api/submissions/                 # List submissions
POST   /api/submissions/                 # Create submission
GET    /api/submissions/{id}/            # Get submission details
PATCH  /api/submissions/{id}/            # Update submission
POST   /api/submissions/{id}/sign-off/   # Final sign-off

# Data table endpoints
GET    /api/submissions/{id}/tables/     # List data tables
POST   /api/submissions/{id}/tables/{table_id}/files/  # Upload file
GET    /api/submissions/{id}/tables/{table_id}/files/  # List files
POST   /api/submissions/{id}/tables/{table_id}/skip/   # Skip table
POST   /api/submissions/{id}/tables/{table_id}/sign-off/  # Sign off table

# File management
GET    /api/files/{id}/                  # Get file details
GET    /api/files/{id}/download/         # Download file
POST   /api/files/{id}/new-version/      # Upload new version
GET    /api/files/{id}/validation/       # Get validation report
```

### Upload Endpoint Example

```python
@api_view(['POST'])
def upload_file_to_table(request, submission_id, table_id):
    """Upload file to data table."""
    submission = get_object_or_404(CohortSubmission, id=submission_id)
    data_table = get_object_or_404(
        CohortSubmissionDataTable,
        submission=submission,
        id=table_id
    )

    # Permission check
    if not SubmissionPermissions.can_edit(request.user, submission):
        return Response({'error': 'Permission denied'}, status=403)

    # File validation
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response({'error': 'No file provided'}, status=400)

    is_valid, error = data_table.validate_file_upload(uploaded_file, request.user)
    if not is_valid:
        return Response({'error': error}, status=400)

    # Create file record
    data_file = create_data_table_file(data_table, request.user, uploaded_file)

    # Trigger processing
    trigger_upload_precheck.delay(data_file.id)

    return Response({
        'file_id': data_file.id,
        'version': data_file.version,
        'status': 'processing'
    })
```

## Performance Considerations

### Large File Handling

- **Streaming uploads**: Large files transferred in chunks
- **Background processing**: DuckDB conversion via Celery tasks
- **Progress tracking**: Real-time status updates

### Database Optimization

```python
# Optimized queries
submissions = CohortSubmission.objects.select_related(
    'cohort', 'protocol_year', 'started_by'
).prefetch_related(
    'data_tables__data_file_type',
    'data_tables__files'
)

# Indexed fields for performance
class CohortSubmission(BaseModel):
    class Meta:
        indexes = [
            models.Index(fields=['cohort', 'protocol_year']),
            models.Index(fields=['status', 'created_at']),
        ]
```

## Error Handling

### Upload Errors

```python
def handle_upload_error(data_file, error):
    """Handle upload processing errors."""
    data_file.upload_precheck.status = 'failed'
    data_file.upload_precheck.error_message = str(error)
    data_file.upload_precheck.save()

    # Log error with PHI tracking
    PHIFileTracking.log_operation(
        cohort=data_file.data_table.submission.cohort,
        user=data_file.uploaded_by,
        action='conversion_failed',
        file_path=data_file.raw_file_path,
        error_message=str(error),
        content_object=data_file
    )

    # Notify user
    notify_upload_error(data_file.uploaded_by, data_file, error)
```

### Validation Errors

```python
def handle_validation_errors(data_file, warnings):
    """Handle validation warnings."""
    data_file.validation_warnings = warnings
    data_file.warning_count = len(warnings)
    data_file.save()

    # Aggregate to table level
    data_file.data_table.aggregate_validation_warnings()

    # Create review record
    review = data_file.data_table.get_or_create_review()
    review.has_validation_warnings = True
    review.save()
```

## Monitoring and Reporting

### Submission Metrics

```python
def get_submission_metrics(protocol_year):
    """Get submission statistics for protocol year."""
    submissions = CohortSubmission.objects.filter(
        protocol_year=protocol_year
    )

    return {
        'total_submissions': submissions.count(),
        'completed': submissions.filter(status='signed_off').count(),
        'in_progress': submissions.filter(status='in_progress').count(),
        'draft': submissions.filter(status='draft').count(),

        # File metrics
        'total_files': DataTableFile.objects.filter(
            data_table__submission__protocol_year=protocol_year,
            is_current=True
        ).count(),

        # Warning metrics
        'files_with_warnings': DataTableFile.objects.filter(
            data_table__submission__protocol_year=protocol_year,
            is_current=True,
            warning_count__gt=0
        ).count()
    }
```

### Progress Tracking

```python
def get_submission_progress(submission):
    """Get detailed progress for submission."""
    total_tables = submission.data_tables.count()

    completed_tables = submission.data_tables.filter(
        models.Q(signed_off=True) |
        models.Q(is_skipped=True) |
        models.Q(not_available=True)
    ).count()

    progress_percent = (completed_tables / total_tables * 100) if total_tables > 0 else 0

    return {
        'total_tables': total_tables,
        'completed_tables': completed_tables,
        'progress_percent': round(progress_percent, 1),
        'status': submission.status,
        'can_sign_off': completed_tables == total_tables
    }
```

## Best Practices

### 1. Always Validate Patient File First

```python
# GOOD: Check patient file requirement
if not submission.has_patient_file() and file_type.name.lower() != 'patient':
    raise ValidationError("Patient file must be uploaded first")

# BAD: Skip patient file validation
upload_file_directly(file_type, uploaded_file)  # May cause validation issues
```

### 2. Use Version Management

```python
# GOOD: Create new version for existing files
existing_files = data_table.get_current_files()
if existing_files.exists():
    existing_file = existing_files.first()
    data_file = existing_file.create_new_version(user, uploaded_file)

# BAD: Overwrite existing files
data_file.uploaded_file = uploaded_file  # Loses version history
```

### 3. Comprehensive Error Handling

```python
# GOOD: Handle all error scenarios
try:
    data_file = upload_and_process_file(data_table, uploaded_file)
except ValidationError as e:
    return JsonResponse({'error': str(e)}, status=400)
except Exception as e:
    logger.error(f"Upload failed: {e}")
    return JsonResponse({'error': 'Upload failed'}, status=500)

# BAD: Let exceptions bubble up
data_file = upload_and_process_file(data_table, uploaded_file)  # May crash
```

### 4. Track All Operations

```python
# GOOD: Log important operations
def sign_off_table(data_table, user, comments):
    data_table.mark_signed_off(user, comments)
    data_table.save_revision(user, 'signed_off')

# BAD: Skip audit trail
data_table.signed_off = True  # No tracking of who/when
```

## Related Documentation

- [PHI File Tracking System](../security/PHIFileTracking-system.md)
- [Storage Manager Abstraction](../technical/storage-manager-abstraction.md)
- [Audit System](../../CLAUDE.md#audit-system)
- [Patient ID Validation](../patient-id-validation-system.md)

## Implementation Files

- **Models**:
  - `depot/models/cohortsubmission.py`
  - `depot/models/cohortsubmissiondatatable.py`
  - `depot/models/datatablefile.py`
- **Views**: `depot/views/submissions/`
- **Tasks**: `depot/tasks/upload_precheck.py`
- **Tests**: `depot/tests/test_submission_workflow.py`