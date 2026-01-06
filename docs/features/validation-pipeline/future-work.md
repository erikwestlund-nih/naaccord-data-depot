# Validation Pipeline – Future Requirements

## Single-File Tables (Patient + Precheck)
- Patient and precheck tables remain single-file uploads; UI should hide per-file comments when only one upload exists.
- Removing the lone upload must reset the associated validation run (clear status, variables, patient metrics).
- Patient roster extracted during validation must persist at the submission level so other table validators can reference the canonical ID set.

## Multi-File Tables
- Support multiple uploads per data table while maintaining raw → processed → validated flow for each file.
- Before validation, combine all processed files for a table into a single DuckDB dataset with:
  - an ordinal column (`file_index` 1..n in upload order)
  - a persistent file identifier (`data_table_file_id`)
- Reuse the same merge routine later for the planned “collect” feature that exports unified datasets for analysts.

## Shared Infrastructure
- Store merged DuckDB artifacts somewhere addressable by both the validation tasks and future downstream consumers.
- Ensure orchestration can detect when uploads change (add/remove files) and regenerate the merged dataset + validation runs.
- Expose submission-wide validation summaries that include per-table patient coverage using the stored patient roster.

## Validation Orchestration
- Maintain a single active validation set per submission; starting a new run replaces the prior run’s status and metrics.
- Allow administrators to trigger both submission-wide re-runs and per-variable rechecks from the UI.
- Treat boolean validators as categorical: capture raw value distributions before normalization so unexpected labels surface in reports.

## UI Expectations
- Patient roster metrics should sit inline within the submission page (no nested cards) and stay available to other table validators.
- Inline validation viewer should keep all variables visible without horizontal overflow and scroll smoothly back to the top after variable navigation.
- For single-file attachments, suppress per-file comments and rely on the overall validation messaging instead.
