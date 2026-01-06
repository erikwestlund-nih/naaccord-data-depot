# Quick Hits - October 31, 2025

Post-deployment improvements and small fixes to address after production launch.

## Storage & Cleanup

- [ ] **Cleanup scratch directories, not just files**
  - Currently cleanup only removes individual files
  - Need to remove empty directories like `storage/scratch/precheck_validation/1/2abf13a83d29490c8c2206b38b837e4b/`
  - Update `cleanup_scratch` management command to recursively clean up empty parent directories
  - Example path structure that needs cleanup:
    ```
    storage/scratch/precheck_validation/
      └── 1/                          # User ID
          └── 2abf13a83d29...4b/      # Token/UUID
              └── file.csv            # Actual file
    ```
  - After file removal, should clean up token dir and user dir if empty

## Infrastructure & Configuration

- [x] **Increase file upload limit to 3GB** ✅ COMPLETED
  - ✅ Django `DATA_UPLOAD_MAX_MEMORY_SIZE` increased to 3GB
  - ✅ Nginx `client_max_body_size` increased to 3072m (3GB) in all configs
  - ✅ Model validation `max_size` increased to 3GB (cohortsubmissiondatatable.py)
  - Files to deploy:
    - `depot/settings.py`
    - `depot/models/cohortsubmissiondatatable.py`
    - `deploy/containers/nginx/nginx.conf`
    - `deploy/containers/nginx/conf.d/naaccord.conf`
    - `deploy/ansible/roles/docker_services/templates/nginx-prod.conf.j2`

## UI/UX

- [ ] **Add data table navigator to file submission pages**
  - Currently users must navigate back to submission detail to switch between tables
  - Add sidebar or dropdown navigation to quickly jump between data tables (Patient, Laboratory, Diagnosis, etc.)
  - Should show completion status for each table (not started, in progress, completed)
  - Make it easy to move through tables sequentially during data entry

- [ ] **Fix plot/chart widths in validation summaries**
  - Review Plotly chart widths in validation summary partials
  - Ensure charts are responsive and don't overflow containers
  - Check consistency across all variable types (enum, date, numeric, ID, boolean)

- [ ] Consider adding progress bar for validation runs instead of just spinner
- [ ] Add estimated time remaining based on completed variables
- [ ] Show validation start time and elapsed time

## Performance

- [ ] Review database query patterns in validation status polling (5s intervals)
- [ ] Consider caching validation summary data for completed runs
- [ ] Evaluate WebSocket as alternative to polling for real-time updates

## Documentation

- [ ] Update deployment docs with precheck-validation vs submissions architecture
- [ ] Document the ValidationRun workflow for future developers
- [ ] Add architecture diagram showing PrecheckRun (standalone) vs Submission ValidationRun

## Testing

- [ ] **Check on data file deletion/overwriting behavior**
  - Verify file replacement works correctly when re-uploading
  - Ensure old files are properly deleted or marked as non-current
  - Test PHI tracking for file overwrites
  - Confirm validation results update correctly on re-upload
- [ ] Add integration tests for precheck validation workflow
- [ ] Test concurrent validation runs from different users
- [ ] Verify PHI tracking cleanup works correctly for staged files
