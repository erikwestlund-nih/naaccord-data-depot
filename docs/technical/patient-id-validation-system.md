# Patient ID Validation System
## NA-ACCORD Data Submission Workflow Enhancement

### Document Information
- **Date Created**: 2025-09-23
- **Status**: Planning Complete
- **Author**: System Architecture Team
- **Version**: 1.0

---

## Executive Summary

This document outlines the comprehensive patient ID validation system for NA-ACCORD data submissions. The system enforces patient file upload as a prerequisite, automatically extracts and validates patient IDs from all uploaded files, and provides detailed validation reports with configurable strictness levels.

---

## Requirements

### Core Requirements
1. **Enforced Upload Sequence**: Patient file must be uploaded first; other tables disabled until patient file exists
2. **Automatic ID Extraction**: Extract patient IDs from all uploaded files
3. **ID Validation**: Compare extracted IDs against the patient file's valid ID list
4. **Detailed Reports**: Show which IDs are invalid with downloadable reports
5. **Deletion Handling**: Clean up patient IDs when patient file is deleted
6. **Configurable Strictness**: Allow sites to choose between blocking invalid submissions or allowing with warnings
7. **Extensibility**: Design for future validation rules

### Performance Requirements
- Handle files up to 40M rows (2GB+)
- Complete extraction within 5 minutes for 10M rows
- Generate validation reports within 30 seconds
- Support concurrent file uploads without blocking

---

## System Architecture

### High-Level Flow
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│Patient File │ --> │Extract IDs   │ --> │Master List  │
│  (Required) │     │Store in DB   │     │(Source)     │
└─────────────┘     └──────────────┘     └─────────────┘
                                                │
                                                v
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│Other Tables │ --> │Extract IDs   │ --> │Validate     │
│  (Blocked)  │     │Via DuckDB    │     │Against List │
└─────────────┘     └──────────────┘     └─────────────┘
                                                │
                                                v
                                          ┌─────────────┐
                                          │Report       │
                                          │Generation   │
                                          └─────────────┘
```

### Component Architecture

#### Data Models
- **SubmissionPatientIDs**: Master patient ID list from patient file (source of truth)
- **DataTableFilePatientIDs**: Patient IDs extracted from each non-patient file with validation results
- **PatientIDValidation**: To be deprecated (redundant with SubmissionPatientIDs)

#### Processing Pipeline
- **Celery Tasks**: Async processing for extraction, validation, and report generation
- **DuckDB**: High-performance extraction from large CSV/TSV files
- **S3 Storage**: Validation reports with time-limited access URLs

#### User Interface
- **HTMX**: Dynamic updates without page refresh
- **Alpine.js**: Client-side state management for table enable/disable
- **Progress Indicators**: Real-time validation progress

---

## Implementation Plan

## Phase 1: Data Model Foundation

### 1.1 Model Consolidation
Clarify responsibilities of existing models:
- Keep `SubmissionPatientIDs` as master list
- Enhance `DataTableFilePatientIDs` for validation tracking
- Deprecate `PatientIDValidation` model

### 1.2 New Model Fields

#### CohortSubmission Additions
```python
validation_mode = models.CharField(
    max_length=20,
    choices=[
        ('permissive', 'Allow with warnings'),
        ('strict', 'Block if invalid IDs found'),
    ],
    default='permissive'
)
validation_threshold = models.IntegerField(
    default=0,  # Number of invalid IDs to tolerate in strict mode
    help_text="Max invalid IDs allowed before blocking (0 = no tolerance)"
)
```

#### DataTableFilePatientIDs Enhancements
```python
validation_status = models.CharField(
    max_length=20,
    choices=[
        ('pending', 'Pending'),
        ('validating', 'Validating'),
        ('valid', 'Valid'),
        ('invalid', 'Invalid'),
    ],
    default='pending'
)
validation_report_url = models.CharField(
    max_length=500,
    null=True,
    blank=True,
    help_text="S3 URL for validation report download"
)
invalid_count = models.IntegerField(
    default=0,
    help_text="Number of invalid patient IDs found"
)
progress = models.IntegerField(
    default=0,
    help_text="Validation progress percentage (0-100)"
)
```

### 1.3 Database Optimization
```sql
-- Add indexes for performance
CREATE INDEX idx_validation_status
ON depot_datatablefilepatientids(data_file_id, validation_status);

CREATE INDEX idx_submission_validation
ON depot_cohortsubmission(id, validation_mode);
```

### 1.4 Cascade Delete Handler
Implement Django signal to handle patient file deletion:
- Clear `SubmissionPatientIDs` record
- Mark all `DataTableFilePatientIDs` as needing revalidation
- Log deletion event for audit trail

---

## Phase 2: Extraction & Validation Pipeline

### 2.1 Celery Task Chain
```python
# Task flow for non-patient file upload
chain(
    extract_patient_ids_task.si(file_id),
    validate_patient_ids_task.si(file_id),
    generate_validation_report_task.si(file_id)
)
```

### 2.2 Task Implementations

#### Extract Patient IDs Task
```python
@shared_task(bind=True, max_retries=3)
def extract_patient_ids_from_file(self, file_id):
    """
    Extract patient IDs using DuckDB for performance.
    Handles files up to 40M rows efficiently.
    """
    # 1. Load file into DuckDB
    # 2. SELECT DISTINCT cohortPatientId
    # 3. Handle >1M ID limit with sampling
    # 4. Update DataTableFilePatientIDs
    # 5. Send progress updates (0-50%)
```

#### Validate Patient IDs Task
```python
@shared_task(bind=True)
def validate_file_patient_ids(self, file_id):
    """
    Validate extracted IDs against master patient list.
    """
    # 1. Get master IDs from SubmissionPatientIDs
    # 2. Perform set operations for validation
    # 3. Store invalid IDs (max 10,000 for display)
    # 4. Update validation_status and counts
    # 5. Send progress updates (50-90%)
```

#### Generate Report Task
```python
@shared_task(bind=True)
def generate_validation_report(self, file_id):
    """
    Create downloadable validation report.
    """
    # 1. Create CSV with all invalid IDs
    # 2. Upload to S3
    # 3. Generate time-limited access URL
    # 4. Update validation_report_url
    # 5. Send progress updates (90-100%)
```

### 2.3 Progress Tracking
- Update `progress` field in 10% increments
- Send Celery signals for HTMX polling
- Display estimated time remaining for large files

---

## Phase 3: User Interface

### 3.1 Visual Status Indicators

#### Table Status Display
```
┌─────────────────────────────────────────────┐
│ Table Name    │ Files │ Status              │
├───────────────┼───────┼─────────────────────┤
│ Patient       │   1   │ ✓ Valid             │
│ Laboratory    │   2   │ ⚠ 15 Invalid IDs    │
│ Medication    │   1   │ ⟳ Validating (45%)  │
│ Diagnosis     │   0   │ ○ Upload Disabled   │
└─────────────────────────────────────────────┘
```

#### Status States
- **Disabled**: Gray background, tooltip "Upload patient file first"
- **Pending**: Yellow clock icon "Validation Pending"
- **Validating**: Blue spinner with progress percentage
- **Valid**: Green checkmark "Valid"
- **Invalid**: Red warning with "View Report" link

### 3.2 Alpine.js Implementation
```html
<div x-data="{
    hasPatientFile: {{ submission.has_patient_file|json }},
    validationStatus: '{{ table.validation_status }}'
}">
    <button
        :disabled="!hasPatientFile && tableType !== 'patient'"
        :class="!hasPatientFile ? 'opacity-50 cursor-not-allowed' : ''"
        @click="uploadFile()"
    >
        Upload File
    </button>
</div>
```

### 3.3 HTMX Progress Updates
```html
<div hx-get="/api/validation-progress/{{ file.id }}/"
     hx-trigger="every 2s"
     hx-target="#progress-bar">
    <div id="progress-bar" class="w-full bg-gray-200 rounded">
        <div class="bg-blue-600 text-xs text-white text-center p-0.5"
             style="width: {{ file.progress }}%">
            {{ file.progress }}%
        </div>
    </div>
</div>
```

### 3.4 Validation Report View
```
┌──────────────────────────────────────┐
│ Validation Report - Laboratory File  │
├──────────────────────────────────────┤
│ Total IDs:        10,523             │
│ Valid IDs:        10,508 (99.9%)     │
│ Invalid IDs:      15 (0.1%)          │
│                                       │
│ Invalid Patient IDs:                 │
│ • PAT99999                          │
│ • PAT88888                          │
│ • INVALID_001                       │
│ ... (12 more)                       │
│                                       │
│ [Download Full Report] [Override]    │
└──────────────────────────────────────┘
```

---

## Phase 4: Configuration & Testing

### 4.1 Configuration Settings
```python
# settings.py
PATIENT_VALIDATION = {
    'ENABLED': True,
    'DEFAULT_MODE': 'permissive',  # or 'strict'
    'MAX_INVALID_IDS_DISPLAY': 100,
    'MAX_INVALID_IDS_STORE': 10000,
    'REPORT_EXPIRY_HOURS': 24,
    'CHUNK_SIZE': 100000,  # Rows per chunk for large files
}
```

### 4.2 Management Commands
```bash
# Revalidate all files in a submission
python manage.py revalidate_submission <submission_id>

# Clear validation cache
python manage.py clear_validation_cache

# Generate validation summary report
python manage.py validation_summary --cohort <cohort_id>
```

### 4.3 Testing Strategy
1. Unit tests for each validation component
2. Integration tests for full workflow
3. Performance tests with 40M+ row files
4. UI tests for all validation states
5. Deletion cascade tests

---

## File Structure

### Files to Modify
```
depot/
├── models/
│   ├── cohortsubmission.py         # Add validation_mode, threshold
│   ├── datatablefilepatientids.py  # Add status, progress, report_url
│   └── submissionpatientids.py     # Keep as master list
├── tasks/
│   └── patient_extraction.py       # New validation tasks
├── views/submissions/
│   ├── table_manage.py            # Validation UI logic
│   └── validation_report.py       # New report view (create)
├── templates/pages/submissions/
│   ├── table_manage.html          # Visual indicators
│   └── validation_report.html     # New report template (create)
├── signals.py                     # Patient file deletion handler
└── migrations/
    └── XXXX_add_validation_fields.py  # New migration
```

### New Files to Create
- `depot/views/submissions/validation_report.py`
- `depot/templates/pages/submissions/validation_report.html`
- `depot/static/js/validation-progress.js`
- `depot/tests/test_patient_validation.py`

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Patient file enforcement | 100% | No uploads possible without patient file |
| Extraction speed | <5 min | Timer for 10M row file processing |
| Validation accuracy | 100% | All mismatches correctly identified |
| Report generation | <30 sec | Time from completion to accessible URL |
| Deletion cleanup | 100% | No orphaned patient IDs in database |
| User comprehension | >90% | Survey/feedback on validation clarity |

---

## Rollback Plan

### Feature Flag Implementation
```python
if settings.PATIENT_VALIDATION['ENABLED']:
    # New validation system
    validate_patient_ids(file)
else:
    # Original behavior
    pass
```

### Rollback Steps
1. Set `PATIENT_VALIDATION['ENABLED'] = False`
2. Restart Celery workers
3. Clear any pending validation tasks
4. Hide validation UI elements
5. Monitor for issues

### Data Preservation
- No destructive changes to existing models
- New fields are additive only
- Validation data can be cleared without affecting uploads

---

## Security Considerations

1. **Patient ID Privacy**: Never expose full patient ID lists in UI
2. **Report Access**: Time-limited S3 URLs (24 hours)
3. **Audit Trail**: Log all validation overrides
4. **Rate Limiting**: Prevent validation DoS attacks
5. **File Size Limits**: Enforce maximum upload sizes

---

## Future Enhancements

1. **Additional Validation Rules**
   - Date range validation
   - Required field checks
   - Cross-table consistency

2. **Performance Optimizations**
   - Redis caching for master patient list
   - Parallel validation for multiple files
   - Incremental validation for file updates

3. **Advanced Reporting**
   - Validation history graphs
   - Cohort-wide validation dashboard
   - Automated validation emails

4. **Integration Points**
   - API endpoints for external validation
   - Webhook notifications
   - Third-party validation services

---

## Appendix A: Database Schema Changes

```sql
-- Migration SQL
ALTER TABLE depot_cohortsubmission
ADD COLUMN validation_mode VARCHAR(20) DEFAULT 'permissive',
ADD COLUMN validation_threshold INTEGER DEFAULT 0;

ALTER TABLE depot_datatablefilepatientids
ADD COLUMN validation_status VARCHAR(20) DEFAULT 'pending',
ADD COLUMN validation_report_url VARCHAR(500),
ADD COLUMN invalid_count INTEGER DEFAULT 0,
ADD COLUMN progress INTEGER DEFAULT 0;

CREATE INDEX idx_validation_status
ON depot_datatablefilepatientids(data_file_id, validation_status);
```

---

## Appendix B: API Endpoints

### Validation Progress
```
GET /api/validation-progress/<file_id>/
Response: {
    "status": "validating",
    "progress": 45,
    "estimated_time_remaining": 120
}
```

### Validation Report
```
GET /api/validation-report/<file_id>/
Response: {
    "total_ids": 10523,
    "valid_ids": 10508,
    "invalid_ids": 15,
    "invalid_id_list": ["PAT99999", "PAT88888", ...],
    "report_url": "https://s3.../report.csv"
}
```

### Override Validation
```
POST /api/override-validation/<file_id>/
Body: {
    "reason": "Known test IDs",
    "override_by": "user@example.com"
}
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-09-23 | System Architecture Team | Initial plan creation |

---

## Contact

For questions or clarifications about this implementation plan, contact the development team.