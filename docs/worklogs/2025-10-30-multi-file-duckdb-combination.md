# Multi-File DuckDB Combination & Deletion Workflow

**Date:** 2025-10-30
**Status:** ✅ COMPLETED

## Problem Statement

Multi-file tables (non-patient tables like diagnosis, laboratory, etc.) were not combining files correctly:

1. **Upload Issue**: When uploading multiple files to the same table, each file overwrote the previous DuckDB instead of combining them
2. **Deletion Issue**: When deleting a file from a multi-file table, the combined DuckDB wasn't regenerated with remaining files
3. **UI Issue**: No processing indicators showing during upload or after deletion

## Root Causes

### 1. DuckDB Overwriting (depot/storage/phi_manager.py:238)
```python
# OLD - All files used same submission_id in filename
duckdb_nas_path = f".../{file_type}_{submission.id}.duckdb"
# Result: Second file overwrites first file's DuckDB
```

### 2. Per-File Processing (depot/tasks/duckdb_creation.py:56)
```python
# OLD - Each file processed independently
conversion_result = phi_manager.convert_to_duckdb(
    raw_nas_path=data_file.raw_file_path,  # Only ONE file!
    ...
)
```

### 3. Validation Trying to Re-combine (depot/tasks/validation_orchestration.py:375)
```python
# OLD - Always tried to combine when seeing multiple files
if current_files.count() > 1:
    combiner.combine_files(...)  # Failed because files already pointed to same DuckDB
```

### 4. No Deletion Regeneration
When a file was deleted, the system didn't trigger DuckDB regeneration with remaining files.

## Solutions Implemented

### 1. New Multi-File Combination Method (✅ COMPLETED)

**File:** `depot/storage/phi_manager.py:101-370`

Added `convert_multiple_files_to_duckdb()` method:
- Takes list of raw file paths
- Processes each through data mapping individually
- Combines all processed CSVs into one file
- Creates single DuckDB from combined data
- Names with `_combined` suffix to prevent overwrites
- Logs all operations with PHI tracking

**Example:**
```python
# Input: ['diagnosis_1.csv', 'diagnosis_2.csv']
# Output: diagnosis_2_combined.duckdb with ALL rows from both files
```

### 2. Updated DuckDB Creation Task (✅ COMPLETED)

**File:** `depot/tasks/duckdb_creation.py:60-102`

Modified to:
- Detect if table is patient (single-file) or other (multi-file)
- For multi-file: fetch ALL current files and combine them
- Use `convert_multiple_files_to_duckdb()` when multiple files exist
- Update ALL DataTableFile records with same combined DuckDB path

### 3. Fixed Validation Orchestration (✅ COMPLETED)

**File:** `depot/tasks/validation_orchestration.py:375-405`

Updated to:
- Check if all files already point to same DuckDB (already combined)
- If yes: use it directly without re-combining
- If no: combine them (legacy case)

### 4. Fixed DuckDB Workspace Cleanup (✅ COMPLETED)

**File:** `depot/storage/phi_manager.py:257-262`

Added cleanup to prevent "table already exists" errors:
```python
# Delete existing workspace DuckDB before creating new one
if workspace_db.exists():
    workspace_db.unlink()
```

### 5. File Deletion Regeneration (✅ COMPLETED)

**File:** `depot/views/submissions/table_manage.py:922-976`

Added workflow after file deletion:
1. Deletes file from storage (raw + DuckDB)
2. Checks for remaining files
3. If files remain:
   - Sets `data_table.status = 'in_progress'`
   - Triggers full workflow: DuckDB regeneration → validation → cleanup
4. If no files remain:
   - Logs "skipping DuckDB regeneration"

### 6. UI Processing Indicator (✅ COMPLETED)

**File:** `depot/templates/pages/submissions/table_manage.html:569`

Fixed template condition:
```django
<!-- OLD: Status hidden if validation completed -->
{% if file.latest_validation_run and file.latest_validation_run.status != 'completed' %}

<!-- NEW: Always show if table is processing -->
{% if file.latest_validation_run and file.latest_validation_run.status != 'completed' or data_table.status == 'in_progress' %}
```

### 7. Last File Deletion Cleanup (✅ COMPLETED)

**File:** `depot/views/submissions/table_manage.py:975-1032`

When deleting the last file from a table, system now:
1. Detects no remaining files
2. Cleans up orphaned ValidationRun records
3. **Deletes all physical files** from `duckdb/` directory
4. **Deletes all physical files** from `processed/` directory
5. Resets `data_table.status` to 'not_started' (stock state)
6. Logs all cleanup operations with PHI tracking

**Why Physical Cleanup is Critical:**
- Multi-file tables create combined DuckDB files (e.g., `diagnosis_2_combined.duckdb`)
- Multiple DataTableFile records may point to same combined DuckDB
- Individual file deletions can't reliably clean shared files
- Orphaned files waste storage and create confusion

**Implementation:**
```python
else:
    logger.info(f"No remaining files - cleaning up validation data and resetting to stock state")

    # Clean up orphaned ValidationRun records
    from depot.models import ValidationRun
    deleted_count = ValidationRun.objects.filter(
        content_type__model='datatablefile',
        object_id__in=DataTableFile.all_objects.filter(data_table=data_table).values_list('id', flat=True)
    ).delete()[0]
    logger.info(f"Deleted {deleted_count} orphaned ValidationRun records")

    # Clean up all physical files from duckdb/ and processed/ directories
    import os
    from pathlib import Path

    base_path = phi_manager.storage_driver.get_base_path() / 'uploads' / f"{cohort.id}_{cohort.name}" / str(protocol_year.year) / file_type_name
    duckdb_dir = base_path / 'duckdb'
    processed_dir = base_path / 'processed'

    # Clean up duckdb directory
    if duckdb_dir.exists():
        for file_path in duckdb_dir.iterdir():
            if file_path.is_file():
                phi_manager.delete_from_nas(
                    nas_path=str(file_path),
                    cohort=cohort,
                    user=request.user,
                    file_type='duckdb'
                )
                logger.info(f"Deleted orphaned DuckDB file: {file_path.name}")

    # Clean up processed directory (same pattern)
    # ...

    # Reset table to stock state
    data_table.update_status('not_started')
    logger.info(f"Reset data_table to not_started (stock state)")
```

## Testing Results

### Multi-File Upload Test
✅ **PASS**: Uploaded 2 diagnosis files (1,775 + 553 rows)
- Combined DuckDB created: `diagnosis_2_combined.duckdb`
- Row count: 2,328 (correct!)
- Both DataTableFile records point to same DuckDB

### File Deletion Test
✅ **PASS**: Deleted one file, regeneration triggered
- DuckDB regenerated with only remaining file
- Validation reran automatically
- Processing spinner appeared (after template fix)

### Last File Deletion
⏳ **READY FOR TESTING**: Cleanup code implemented and saved

## Files Modified

1. `depot/storage/phi_manager.py` - Added multi-file combination method
2. `depot/tasks/duckdb_creation.py` - Updated to detect and combine multi-file tables
3. `depot/tasks/validation_orchestration.py` - Fixed duplicate combination attempt
4. `depot/views/submissions/table_manage.py` - Added deletion regeneration workflow
5. `depot/templates/pages/submissions/table_manage.html` - Fixed status display condition

## Implementation Complete ✅

All features have been implemented:
1. ✅ Multi-file DuckDB combination
2. ✅ File deletion with DuckDB regeneration
3. ✅ Last file deletion cleanup to stock state
4. ✅ UI processing indicators
5. ✅ PHI tracking for all operations

## Next Steps

1. **Manual testing** of complete workflow:
   - Upload 2 files → verify combination
   - Delete 1 file → verify regeneration
   - Delete last file → verify return to stock state
2. **Deploy to test environment**
3. **Full acceptance testing**

## Technical Notes

- **Patient tables**: Always single-file only (special handling)
- **Non-patient tables**: Support multiple files (combined at DuckDB creation)
- **DuckDB naming**: Uses `_combined` suffix when multiple files
- **Status updates**: Critical for UI spinner visibility
- **PHI tracking**: All file operations logged with hashes

## Related Documentation

- Multi-file upload workflow: `docs/technical/upload-submission-workflow.md`
- Storage architecture: `depot/storage/CLAUDE.md`
- PHI tracking system: `docs/security/PHIFileTracking-system.md`
