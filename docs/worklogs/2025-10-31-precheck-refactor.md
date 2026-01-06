# 2025-10-31 – Precheck Validation Refactor Planning

## Goal

Retire the legacy “Upload Precheck” flow (Auditor + Quarto pipeline) and align the code with the current granular validation architecture. The existing `UploadPrecheck` model is still used by Precheck Validation, so we will rename it and clean up the surrounding tasks and UI.

## Current State

- **Precheck Validation** (new flow) uploads a file, creates an `UploadPrecheck`, triggers `convert_to_duckdb_and_validate`, and then runs the shared validation/summary services.
- **Legacy Upload Precheck** (to be removed) uses the `Auditor` class, Quarto notebooks, and dedicated Celery tasks/templates.
- The `UploadPrecheck` model still contains status fields for the notebook pipeline (processing_notebook, etc.) even though the new flow does not use them.
- Navigation still shows both “Upload Precheck” and “Precheck Validation”.
- `convert_to_duckdb_and_validate` mixes two concerns (conversion + validation kickoff).

## Plan Overview

1. **Rename the model**
   - Rename `UploadPrecheck` to `PrecheckRun` (or similar) via Django migration.
   - Update all Python imports, foreign keys, related names, tests, and management commands.
   - Ensure database tables/columns keep historical data (use `RenameModel`, `RenameField`).

2. **Split the conversion task**
   - Replace `convert_to_duckdb_and_validate` with two Celery tasks:
     - `convert_to_duckdb(precheck_run_id, validation_run_id=None)`
     - `start_validation_run(validation_run_id)` (already exists)
   - Update Precheck Validation view to call the new conversion task and chain validation explicitly.
   - Adjust logging / error handling to match the new sequencing.

3. **Remove legacy Upload Precheck**
   - Delete legacy views (`upload_precheck.py`, templates), Celery tasks (`depot/tasks/upload_precheck.py`), services (`upload_precheck_service.py`), and `Auditor`.
   - Remove menu entries, URLs, docs that expose the old feature.
   - Keep any utilities still needed by Precheck Validation or submissions.

4. **Update navigation/UI**
   - Replace “Upload Precheck” nav item with “Precheck Validation”.
   - Ensure only the new flow is exposed in layouts and dashboards.

5. **Documentation & tests**
   - Update relevant CLAUDE.md files and docs to describe the renamed model and task pipeline.
   - Run/regenerate tests that reference `UploadPrecheck`.
   - Verify no orphaned references remain (`rg upload_precheck`, `rg Auditor`).

## Open Questions

- Desired final name for the model (`PrecheckRun`, `PrecheckValidationRequest`, etc.)?
- Any historical reporting that relies on the old pipeline artifacts (Quarto notebooks)?
- Do we need a data migration to clean up legacy status values or results stored on existing records?
