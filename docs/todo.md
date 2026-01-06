# NA-ACCORD TODO

## High Priority

### Scheduled Cleanup Jobs

**Background:** During development testing, failed upload prechecks left 43MB of orphaned CSV files in `storage/uploads/upload_prechecks/` because cleanup only ran on successful processing. This has been fixed (both success and failure now clean up), but we need scheduled jobs as a safety net.

**Required Cleanup Jobs:**

1. **Orphaned Upload Files** - Scan `storage/uploads/upload_prechecks/` for files older than 24 hours and delete them
   - Files should normally be cleaned up immediately after processing
   - This catches any missed by failed tasks or crashes
   - Priority: HIGH - Can accumulate quickly with large CSV files

2. **Temp DuckDB Files** - Clean up `/tmp/r-workspace/*.duckdb` older than 24 hours
   - These are created during notebook rendering
   - Should be cleaned up by code, but crashes can leave them

3. **PHIFileTracking Audit** - Find files marked `cleanup_required=True` but `cleaned_up=False` older than 48 hours
   - Log warnings and attempt cleanup
   - Update PHIFileTracking records

**Implementation:**
- Use Celery Beat for scheduled tasks
- Add management command for manual cleanup: `python manage.py cleanup_orphaned_files`
- Log all cleanup operations for audit trail
- Consider alerts/notifications for large orphan accumulations

**Related Files:**
- `depot/tasks/upload_precheck.py` - Current cleanup logic
- `depot/models/phi_tracking.py` - PHI file tracking
- `depot/storage/manager.py` - Storage operations
