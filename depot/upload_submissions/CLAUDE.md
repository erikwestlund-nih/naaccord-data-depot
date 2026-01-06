# Upload Submissions Domain - CLAUDE.md

## Domain Overview

The upload submissions system manages multi-file clinical data submissions with patient-first validation, cross-file integrity checking, and table-level acknowledgment workflow. This domain handles the complete submission lifecycle from initial upload through final sign-off.

## Core Architecture

### Primary Models

**CohortSubmission** (`depot/models/cohortsubmission.py`)
- Master submission record for cohort/wave combination
- Tracks extracted patient IDs for cross-file validation
- Manages submission status progression
- Stores final acknowledgment and metadata

**CohortSubmissionFile** (`depot/models/cohortsubmissionfile.py`)
- Individual file uploads within a submission
- Links to Audit records for validation results
- Supports versioning for re-uploads
- Tracks acknowledgment status and comments

**UploadPrecheckSubmissionForm** (`depot/forms/upload_precheck_submission_form.py`)
- Handles file uploads with cohort-specific validation
- Manages submission state transitions
- Integrates with existing audit system

### Key Business Rules

1. **Patient File First**: Must upload patient data file before other file types
2. **Flexible Upload Order**: Non-patient files can be uploaded in any sequence
3. **Warning-Based Validation**: Issues highlighted but don't block submission
4. **Required Acknowledgment**: Each file must be acknowledged with optional comments
5. **Cross-File Validation**: Patient IDs validated across all submitted files
6. **Version Control**: Files can be re-uploaded with automatic versioning

## Critical Workflow Patterns

### Submission Lifecycle

```python
# 1. Initialize submission
submission = CohortSubmission.objects.create(
    cohort=cohort,
    protocol_year=protocol_year,
    status='draft'
)

# 2. Upload patient file first (required)
patient_file = CohortSubmissionFile.objects.create(
    submission=submission,
    data_file_type=patient_file_type,
    version=1,
    acknowledged=False
)

# 3. Process through audit system
audit = Audit.objects.create(
    data_file_type=patient_file_type,
    # ... triggers async processing
)

# 4. Extract patient IDs for validation
submission.extracted_patient_ids = extract_patient_ids(audit.duckdb_path)
submission.save()

# 5. Upload additional files (validated against patient IDs)
# 6. Acknowledge each file with comments
# 7. Final submission sign-off
```

### Cross-File Validation

```python
def validate_patient_ids(submission, new_file_audit):
    """Validate patient IDs against master patient file"""
    if submission.extracted_patient_ids:
        new_patient_ids = extract_patient_ids(new_file_audit.duckdb_path)
        invalid_ids = set(new_patient_ids) - set(submission.extracted_patient_ids)

        if invalid_ids:
            return ValidationResult(
                is_valid=False,
                warnings=[f"Unknown patient IDs: {invalid_ids}"]
            )

    return ValidationResult(is_valid=True)
```

## View Patterns

### Primary Views

**submit_upload_precheck** (`depot/views/upload_precheck.py:267`)
- Main submission interface
- Handles GET: display submission status and file list
- Handles POST: process file uploads and acknowledgments
- Manages submission state transitions

**acknowledge_submission_file** (`depot/views/upload_precheck.py:349`)
- File-level acknowledgment with comments
- Updates CohortSubmissionFile.acknowledged status
- Supports batch acknowledgment operations

### Template Integration

```html
<!-- Submission status display -->
{% if submission.status == 'draft' %}
    <span class="badge badge-secondary">Draft</span>
{% elif submission.status == 'in_progress' %}
    <span class="badge badge-primary">In Progress</span>
{% elif submission.status == 'completed' %}
    <span class="badge badge-success">Completed</span>
{% endif %}

<!-- File upload with validation warnings -->
<form method="post" enctype="multipart/form-data">
    {{ form.as_p }}
    {% if validation_warnings %}
        <div class="alert alert-warning">
            {% for warning in validation_warnings %}
                <p>{{ warning }}</p>
            {% endfor %}
        </div>
    {% endif %}
</form>
```

## Database Schema Patterns

### Key Relationships

```python
# CohortSubmission tracks overall submission
class CohortSubmission(models.Model):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE)
    protocol_year = models.ForeignKey(ProtocolYear, on_delete=models.CASCADE)
    extracted_patient_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, default='draft')

    class Meta:
        unique_together = ['cohort', 'protocol_year']

# CohortSubmissionFile tracks individual file uploads
class CohortSubmissionFile(models.Model):
    submission = models.ForeignKey(CohortSubmission, on_delete=models.CASCADE)
    data_file_type = models.ForeignKey(DataFileType, on_delete=models.CASCADE)
    audit = models.ForeignKey(Audit, on_delete=models.CASCADE)
    version = models.PositiveIntegerField(default=1)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        unique_together = ['submission', 'data_file_type', 'version']
```

## Security and PHI Compliance

### PHI File Tracking Integration

```python
# Automatic tracking for submission files
def create_submission_file(submission, file_data, user):
    # Create audit record (triggers PHI tracking)
    audit = Audit.objects.create(
        cohort=submission.cohort,
        user=user,
        data_file_type=file_type
    )

    # Track submission relationship
    PHIFileTracking.log_operation(
        cohort=submission.cohort,
        user=user,
        action='submission_file_uploaded',
        file_path=audit.temporary_file.s3_key,
        content_object=submission
    )
```

### Access Control Patterns

```python
# Cohort-based submission access
def user_can_access_submission(user, submission):
    """Check if user can access submission"""
    return user.groups.filter(
        name=f"{submission.cohort.name}_users"
    ).exists()

# File-level permissions
def user_can_acknowledge_file(user, submission_file):
    """Check if user can acknowledge specific file"""
    return (
        user_can_access_submission(user, submission_file.submission) and
        submission_file.audit.status == 'completed'
    )
```

## Testing Patterns

### Test Data Generation

```python
# Generate test submission with multiple files
def create_test_submission(cohort, protocol_year):
    submission = CohortSubmission.objects.create(
        cohort=cohort,
        protocol_year=protocol_year
    )

    # Create patient file first
    patient_audit = create_test_audit(
        cohort=cohort,
        data_file_type=DataFileType.objects.get(name='patient')
    )

    CohortSubmissionFile.objects.create(
        submission=submission,
        data_file_type=patient_audit.data_file_type,
        audit=patient_audit,
        acknowledged=True
    )

    return submission
```

### Validation Testing

```python
# Test cross-file patient ID validation
def test_patient_id_validation():
    submission = create_test_submission()

    # Upload lab file with invalid patient ID
    lab_file = upload_file_with_invalid_patient_id(submission)

    # Should show warning but allow upload
    assert lab_file.audit.status == 'completed'
    assert 'Unknown patient IDs' in lab_file.validation_warnings
```

## Common Operations

### Query Patterns

```python
# Get all submissions for a cohort
submissions = CohortSubmission.objects.filter(
    cohort=user_cohort
).prefetch_related('cohortsubmissionfile_set__audit')

# Get submission by cohort and protocol year
submission = CohortSubmission.objects.get(
    cohort=cohort,
    protocol_year=protocol_year
)

# Get files needing acknowledgment
unacknowledged_files = CohortSubmissionFile.objects.filter(
    submission=submission,
    acknowledged=False,
    audit__status='completed'
)
```

### Status Management

```python
# Update submission status based on file progress
def update_submission_status(submission):
    files = submission.cohortsubmissionfile_set.all()

    if not files.exists():
        submission.status = 'draft'
    elif files.filter(acknowledged=False).exists():
        submission.status = 'in_progress'
    else:
        submission.status = 'completed'

    submission.save()
```

## Integration Points

### Audit System Integration
- Leverages existing audit workflow for file validation
- CohortSubmissionFile.audit links to Audit records
- Validation results displayed in submission interface

### Storage System Integration
- Files stored via StorageManager abstraction
- PHI tracking for all uploaded files
- Temporary files cleaned up after processing

### Celery Task Integration
- Async processing maintains existing audit task workflow
- Submission status updated via task completion signals
- Background validation and patient ID extraction

## Error Handling Patterns

### Validation Errors

```python
# Handle file upload validation errors
try:
    submission_file = create_submission_file(submission, file_data)
except ValidationError as e:
    return render(request, 'upload_precheck/submit.html', {
        'form': form,
        'errors': e.messages,
        'submission': submission
    })
```

### Async Processing Errors

```python
# Handle audit processing failures
def handle_audit_failure(submission_file, error_message):
    submission_file.audit.status = 'failed'
    submission_file.audit.error_message = error_message
    submission_file.audit.save()

    # Log for PHI tracking
    PHIFileTracking.log_operation(
        action='submission_file_processing_failed',
        error_message=error_message,
        content_object=submission_file
    )
```

## Development Guidelines

### Adding New File Types
1. Create DataFileType record
2. Add validation rules to existing audit system
3. Update submission templates for new file type
4. Test cross-file validation if patient IDs involved

### Modifying Validation Rules
1. Update audit system validation logic
2. Ensure warnings (not errors) for submission workflow
3. Test acknowledgment workflow with new validation
4. Update PHI tracking if file handling changes

### Performance Considerations
- Use select_related/prefetch_related for submission queries
- Cache patient ID lists for large submissions
- Consider async processing for large file validations
- Monitor PHI tracking record growth

## Related Documentation
- [Upload Submission Workflow](../../docs/technical/upload-submission-workflow.md)
- [PHI File Tracking System](../../docs/security/PHIFileTracking-system.md)
- [Audit System Architecture](./audit/CLAUDE.md)
- [Storage Manager](./storage/CLAUDE.md)