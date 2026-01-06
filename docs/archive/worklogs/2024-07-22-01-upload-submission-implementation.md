# Upload Submission Implementation

## Date: 2025-07-22

## Overview
Planning and implementation of the multi-file clinical data submission workflow for NA-ACCORD.

## Requirements Gathered
- Users submit data files for a specific DataSubmissionWave
- Patient file must be uploaded first to extract valid patient IDs
- All other files validated against patient ID list
- Files can be skipped with reason and acknowledgment
- Warning-based validation (highlight issues but allow submission)
- Multi-user access (anyone with cohort permissions)
- Re-upload capability with version history
- Final sign-off with comments required

## Architecture Decisions
1. **Storage**: Custom NAS driver with S3-like interface
   - Path: `{cohort_id}_{cohort_name}/{wave}/{file_type}/`
   - Version tracking for all uploads
   
2. **Validation**: Warnings not errors approach
   - Extract patient IDs from patient file
   - Cross-validate all other files
   - Store warnings but allow submission

3. **Workflow States**: draft → in_progress → completed → signed_off

## Implementation Plan

### Phase 1: Core Infrastructure
- [x] Create CohortSubmission model
- [x] Create CohortSubmissionFile model  
- [x] Create Revision model for audit tracking
- [x] Create RevisionMixin for all models
- [x] Update BaseModel to include revision tracking
- [x] Create model migrations
- [x] Run migrations successfully
- [x] Create Django admin interfaces
- [x] Create revision utility functions
- [ ] Implement NAS storage driver
- [ ] Set up basic views and URLs

### Phase 2: Upload & Validation
- [ ] Implement file upload workflow
- [ ] Add patient ID extraction service
- [ ] Integrate cross-file validation
- [ ] Connect to existing audit system

### Phase 3: Review & Acknowledgment
- [ ] Build audit review interface
- [ ] Add acknowledgment UI
- [ ] Implement skip file functionality
- [ ] Create version history viewer

### Phase 4: Finalization
- [ ] Implement final sign-off process
- [ ] Add permission checks
- [ ] Create cleanup tasks
- [ ] Comprehensive testing

## Key Models

### CohortSubmission
```python
class CohortSubmission(BaseModel):
    submission_wave = ForeignKey(DataSubmissionWave)
    cohort = ForeignKey(Cohort)
    started_by = ForeignKey(User)
    status = CharField(choices=['draft', 'in_progress', 'completed', 'signed_off'])
    patient_ids = JSONField(default=list)
    final_comments = TextField(blank=True)
    final_acknowledged = BooleanField(default=False)
    final_acknowledged_by = ForeignKey(User, null=True)
    final_acknowledged_at = DateTimeField(null=True)
```

### CohortSubmissionFile
```python
class CohortSubmissionFile(BaseModel):
    submission = ForeignKey(CohortSubmission)
    data_file_type = ForeignKey(DataFileType)
    version = IntegerField(default=1)
    is_current = BooleanField(default=True)
    temp_file = ForeignKey(TemporaryFile, null=True)
    nas_path = CharField(max_length=500, null=True)
    audit = ForeignKey(Audit, null=True)
    acknowledged = BooleanField(default=False)
    acknowledged_by = ForeignKey(User, null=True)
    acknowledged_at = DateTimeField(null=True)
    comments = TextField(blank=True)
    skip_reason = TextField(blank=True)
    validation_warnings = JSONField(default=dict)
    patient_id_mismatches = JSONField(default=list)
```

## Documentation Created
1. `/Users/erikwestlund/code/naaccord/.cursor/rules/features/upload-submission.mdc`
   - Comprehensive feature documentation
   - Architecture patterns and code examples
   
2. Updated `CLAUDE.md` with Upload Submission section

## Next Steps
Begin Phase 1 implementation starting with model creation.

## Notes
- Builds on existing audit system infrastructure
- Designed for future microservice architecture
- Maintains complete audit trail for security
- Flexible enough to handle incomplete submissions