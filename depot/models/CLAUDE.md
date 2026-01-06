# Models Domain - CLAUDE.md

## Summary Hierarchy Update

- Added dedicated summary models: `VariableSummary`, `DataTableSummary`, and `SubmissionSummary`.
- Each summary model uses `BaseModel` (created/updated/deleted timestamps, revisions) with one-to-one links:
  - `VariableSummary` ↔ `ValidationVariable`
  - `DataTableSummary` ↔ `ValidationRun`
  - `SubmissionSummary` ↔ `CohortSubmission` (+ optional `SubmissionValidation` pointer)
- `VariableSummaryService` (new in `depot/services/variable_summary_service.py`) pulls column data from DuckDB, runs the legacy summarizers, and stores numeric aggregates, chart payloads, and examples on the model.

## Database Migrations

Always run schema changes inside the services container so we hit the correct Python environment and database:

```bash
docker exec naaccord-test-services python manage.py migrate
```

If a migration fails, capture the error, roll back the migration, and fix the underlying issue before retrying.
