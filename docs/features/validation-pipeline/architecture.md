# Validation Pipeline Architecture

## Overview

The validation pipeline provides comprehensive data quality feedback for both precheck validation (transient) and file submission (permanent) workflows. The system validates data files against JSON definitions, providing detailed per-column feedback without rejecting submissions.

**Key Principle**: We provide feedback to improve data quality, not pass/fail judgments. All validation results are warnings/informational.

## Design Decisions (Locked)

### Data Flow & Storage

#### 1. DuckDB Conversion Service
- **Service**: `DuckDBConversionService.convert(raw_or_processed_path) -> duckdb_path`
- **Responsibilities**:
  - Convert CSV/TSV/Parquet to DuckDB
  - Track PHI lineage (source file id, column mapping, PHI-sensitivity flags)
  - Write metadata alongside DuckDB file
  - Store in temp/scratch with automatic lifecycle cleanup hooks
- **Composition**: Can optionally call `DataFileStatisticsService` for statistics artifact
- **Separation**: Keep statistics generation separate; allow composition but don't overstuff

#### 2. Precheck Task Chain (Transient Flow)
```
Upload Raw → Store Raw (transient)
  → Process File (transient copy; pass-through for now)
  → Convert Processed → Run Validation (parallel per variable)
  → Generate Summary → Cleanup (delete raw + processed + duckdb)
```

**Notes**:
- Add "processing" layer between raw and convert for future column renaming, encoding standardization
- For now, processing is pass-through copy to transient "processed" storage
- Precheck keeps only validation artifacts in DB; all files removed
- Use scratch/temp storage with PHI tracking for all transient files

#### 3. Submission Task Chain (Retained Flow)
```
Upload Raw → Store Raw (permanent)
  → Process File (persist processed; keep copy)
  → Convert Processed → Run Validation (parallel per variable)
  → Generate Summary → Cleanup (delete duckdb; keep raw + processed)
```

**Notes**:
- Uses same conversion service as precheck
- Differs only in retention policy (keep raw + processed)
- DuckDB always deleted after validation completes

### Model Structure

#### Naming Convention (Locked)
- **ValidationRun** (`validation_runs`) - Top level: a single run of a single file
- **ValidationVariable** (`validation_variables`) - Mid level: one per column/variable
- **ValidationCheck** (`validation_checks`) - Leaf level: individual rule outcomes
- **ValidationTask** - Runtime/Celery concept (separate from DB models)

#### Relationships
```
ValidationRun (polymorphic parent: PrecheckValidationRun OR CohortSubmissionFile)
  ↓ hasMany
ValidationVariable (one per column: cohortPatientId, birthSex, etc.)
  ↓ hasMany
ValidationCheck (individual validation failures/warnings)
```

#### ValidationRun Model
```python
class ValidationRun(models.Model):
    # Polymorphic relationship to either PrecheckValidationRun or CohortSubmissionFile
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # File information
    data_file_type = models.ForeignKey(DataFileType, on_delete=models.CASCADE)
    duckdb_path = models.CharField(max_length=500)  # Temporary, cleaned up after validation
    raw_file_path = models.CharField(max_length=500)

    # Status tracking
    status = models.CharField(max_length=20)  # pending, running, completed, failed
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    # Summary counts
    total_variables = models.IntegerField(default=0)
    completed_variables = models.IntegerField(default=0)
    variables_with_warnings = models.IntegerField(default=0)
    variables_with_errors = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### ValidationVariable Model
```python
class ValidationVariable(models.Model):
    validation_run = models.ForeignKey(ValidationRun, on_delete=models.CASCADE, related_name='variables')

    # Column information
    column_name = models.CharField(max_length=100)  # e.g., "cohortPatientId"
    column_type = models.CharField(max_length=50)   # e.g., "id", "enum", "date"

    # Status tracking
    status = models.CharField(max_length=20)  # pending, running, completed, failed
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    # Summary statistics (per-column)
    total_rows = models.IntegerField(default=0)
    null_count = models.IntegerField(default=0)
    empty_count = models.IntegerField(default=0)
    valid_count = models.IntegerField(default=0)
    invalid_count = models.IntegerField(default=0)
    warning_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)

    # Summary JSON (flexible for variable-specific stats)
    summary = models.JSONField(default=dict)  # e.g., {"duplicate_count": 3, "out_of_range_count": 5}

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### ValidationCheck Model
```python
class ValidationCheck(models.Model):
    validation_variable = models.ForeignKey(ValidationVariable, on_delete=models.CASCADE, related_name='checks')

    # Rule information
    rule_key = models.CharField(max_length=100)  # e.g., "type_is_boolean", "range", "required_when"
    rule_params = models.JSONField(default=dict)  # e.g., {"min": 1900, "max": 2025}

    # Result
    passed = models.BooleanField(default=False)
    severity = models.CharField(max_length=20)  # "warning", "error"
    message = models.TextField()  # Human-readable message

    # Issue details (PHI-safe)
    affected_row_count = models.IntegerField(default=0)
    row_numbers = models.TextField(null=True)  # Comma-separated or JSON array; never with patient IDs
    invalid_value = models.CharField(max_length=500, null=True)  # Only if not PHI-sensitive

    # Metadata
    meta = models.JSONField(default=dict)  # Additional rule-specific information
    created_at = models.DateTimeField(auto_now_add=True)
```

### Services (Abstraction & Reusability)

#### 1. DuckDBConversionService
**Location**: `depot/services/duckdb_conversion.py`

```python
class DuckDBConversionService:
    @staticmethod
    def convert(source_path: str, cohort=None, user=None) -> dict:
        """
        Convert CSV/TSV/Parquet to DuckDB with PHI tracking.

        Args:
            source_path: Path to raw or processed file
            cohort: Cohort for PHI tracking (optional)
            user: User for PHI tracking (optional)

        Returns:
            {
                'duckdb_path': str,
                'row_count': int,
                'column_count': int,
                'column_names': list,
                'file_size_bytes': int,
                'phi_tracking_id': int
            }
        """
```

**Responsibilities**:
- Create DuckDB file in scratch storage
- Add row_no column for tracking
- Log PHI tracking for DuckDB creation
- Store metadata alongside DuckDB
- Return structured result for next step

#### 2. DataFileStatisticsService
**Location**: `depot/services/data_statistics.py`

```python
class DataFileStatisticsService:
    @staticmethod
    def generate_statistics(duckdb_path: str) -> dict:
        """
        Generate summary statistics from DuckDB file.

        Returns:
            {
                'row_count': int,
                'unique_rows': int,
                'null_count': int,
                'column_stats': {
                    'column_name': {
                        'null_count': int,
                        'empty_count': int,
                        'distinct_count': int,
                        'most_common_value': str,
                        'most_common_count': int
                    }
                }
            }
        """
```

**Responsibilities**:
- Generate basic profiling statistics
- Per-column null/empty/distinct counts
- Most common values (non-PHI columns only)
- Keep separate from conversion; called optionally

#### 3. ValidationExecutionService
**Location**: `depot/services/validation_execution.py`

```python
class ValidationExecutionService:
    def __init__(self, validation_run: ValidationRun):
        self.validation_run = validation_run
        self.duckdb_conn = None
        self.definition = None

    def execute(self):
        """
        Fan out validators per variable, collect and store results.

        Workflow:
        1. Load definition for data_file_type
        2. Parse definition to create ValidationVariable records
        3. For each variable, dispatch Celery task
        4. Tasks run validators and store ValidationCheck records
        5. Update ValidationVariable summaries
        6. Update ValidationRun summary
        """

    def validate_variable(self, validation_variable_id: int):
        """
        Run all validators for a single variable.
        Called by Celery task.
        """
```

**Responsibilities**:
- Orchestrate validation execution
- Create ValidationVariable records from definition
- Dispatch Celery tasks per variable
- Aggregate results into ValidationRun summary

#### 4. ValidationReportService
**Location**: `depot/services/validation_report.py`

```python
class ValidationReportService:
    @staticmethod
    def generate_summary(validation_run: ValidationRun) -> dict:
        """Generate UI-friendly summary."""

    @staticmethod
    def export_csv(validation_run: ValidationRun) -> str:
        """Export all validation issues to CSV."""

    @staticmethod
    def export_excel(validation_run: ValidationRun) -> bytes:
        """Export all validation issues to Excel with formatting."""
```

**Responsibilities**:
- Generate human-readable reports
- Support multiple export formats
- Redact PHI from exports
- Database-driven (not Quarto-based)

#### 5. DefinitionProcessingService
**Location**: `depot/services/definition_processing.py`

```python
class DefinitionProcessingService:
    @staticmethod
    def parse_definition(data_file_type) -> dict:
        """
        Read JSON definition and create structured execution plan.

        Returns:
            {
                'variables': [
                    {
                        'name': 'cohortPatientId',
                        'type': 'id',
                        'validators': [
                            {'rule': 'no_duplicates', 'params': {}}
                        ]
                    },
                    {
                        'name': 'birthYear',
                        'type': 'year',
                        'validators': [
                            {'rule': 'type_is_year', 'params': {}},
                            {'rule': 'range', 'params': {'min': 1900, 'max': 2025}}
                        ]
                    }
                ]
            }
        """
```

**Responsibilities**:
- Load JSON definition
- Map columns to validators with parameters
- Handle type-based validators (enum, boolean, date, etc.)
- Handle explicit validators array
- Return structured plan for execution

### Validator Library

#### Layout
```
depot/validation/validators/
├── __init__.py
├── validate_base.py          # BaseValidator abstract class
├── validate_type.py           # enum, boolean, date, year, id, string
├── validate_constraint.py     # range, no_duplicates, allowed_values
└── validate_conditional.py    # required_when, forbidden_when
```

#### BaseValidator
```python
# depot/validation/validators/validate_base.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseValidator(ABC):
    def __init__(self, duckdb_conn, table_name: str, column_name: str, params: Dict[str, Any] = None):
        self.conn = duckdb_conn
        self.table_name = table_name
        self.column_name = column_name
        self.params = params or {}

    @abstractmethod
    def validate(self) -> Dict[str, Any]:
        """
        Run validation and return standardized result.

        Returns:
            {
                'passed': bool,
                'severity': 'warning' | 'error',
                'message': str,
                'affected_row_count': int,
                'row_numbers': str,  # Comma-separated
                'invalid_value': str | None,
                'meta': dict  # Additional rule-specific data
            }
        """
        pass

    def get_total_rows(self) -> int:
        """Helper to get total row count."""
        result = self.conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()
        return result[0] if result else 0

    def column_exists(self) -> bool:
        """Check if column exists in table."""
        columns = self.conn.execute(f"PRAGMA table_info('{self.table_name}')").fetchall()
        column_names = [col[1] for col in columns]
        return self.column_name in column_names
```

#### Type Validators (Examples)
```python
# depot/validation/validators/validate_type.py

class EnumValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate enum/categorical values against allowed_values list."""
        allowed_values = self.params.get('allowed_values', [])
        # ... implementation follows R validate_enum pattern

class BooleanValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate boolean values."""
        # ... implementation follows R validate_boolean pattern

class DateValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate date values with format checking."""
        date_format = self.params.get('date_format', 'YYYY-MM-DD')
        # ... implementation follows R validate_date pattern

class YearValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate year values (4-digit integers)."""
        # ... implementation follows R validate_year pattern
```

#### Constraint Validators (Examples)
```python
# depot/validation/validators/validate_constraint.py

class RangeValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate numeric values within range."""
        min_val = self.params.get('min')
        max_val = self.params.get('max')
        # ... implementation follows R validate_range pattern

class NoDuplicatesValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate no duplicate values in column."""
        # ... implementation follows R validate_no_duplicates pattern
        # IMPORTANT: For cohortPatientId, only show row numbers, not actual IDs

class AllowedValuesValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate values against allowed list (for enums)."""
        # ... implementation follows R validate_enum_allowed_values pattern
```

#### Conditional Validators (Examples)
```python
# depot/validation/validators/validate_conditional.py

class RequiredWhenValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate conditional required fields."""
        # params: {'absent': 'presentSex'} or {'present': 'deathDate'}
        # ... implementation follows R validate_required_when pattern

class ForbiddenWhenValidator(BaseValidator):
    def validate(self) -> Dict[str, Any]:
        """Validate conditionally forbidden fields."""
        # params: {'absent': 'birthSex'} or {'present': 'deathDate'}
        # ... implementation follows R validate_forbidden_when pattern
```

### PHI & Security

#### Value Storage Rules (Locked)

**✅ SAFE - Can Store**:
```python
# Row references without patient identifiers
ValidationCheck(
    column_name='birthSex',
    row_numbers='45, 67, 89',
    invalid_value='Malee',  # Typo, not PHI
    message='Invalid categorical value'
)
```

**❌ UNSAFE - Never Store Together**:
```python
# Patient identifier + invalid value
ValidationCheck(
    column_name='cohortPatientId',
    row_numbers='10, 45, 67',
    invalid_value='ABC123',  # NEVER store patient IDs as "invalid values"
    message='Duplicate patient ID'
)
```

#### Duplicate Detection Special Case

**For cohortPatientId duplicates**:

**Default UI Display**:
- "3 duplicate patient IDs found in rows 10, 45, 67"
- Do NOT show the actual patient IDs

**Admin/Privileged Mode** (future):
- Gated view requiring authorization
- Show duplicated IDs in secure audit screen
- Log all access to patient ID details
- Never include in exports by default

**Export Redaction**:
- All CSV/Excel exports redact patient identifiers unless explicitly authorized
- Log all authorized PHI exports for audit trail

#### Column PHI Sensitivity

Mark columns as PHI-sensitive in definition metadata:
```json
{
  "name": "cohortPatientId",
  "type": "id",
  "phi_sensitive": true,  // NEW: suppress invalid_value storage
  "validators": ["no_duplicates"]
}
```

For PHI-sensitive columns:
- Store affected_row_count and row_numbers
- Do NOT store invalid_value
- Show category-level info only: "3 duplicate IDs found"

### UI & Progress Tracking

#### Real-time Updates

**Polling Strategy**:
- Frontend polls every 10 seconds (not 2 seconds)
- Lightweight spinner/skeleton during running state
- No aggressive polling

**Status Tracking**:
```python
# ValidationVariable status flow
pending → running → completed|failed

# Real-time updates show:
- Overall progress: "Validating 5/14 variables"
- Per-variable status with counts
- Summary counts (errors, warnings)
```

**Progress Display**:
- Overall: "12 variables validated, 3 with warnings, 1 with errors"
- Optional per-variable progress if cheaply available
- Keep it simple: status + counts, not percentage progress bars

#### Results Display

**Top-level Summary**:
```
✓ Validation Complete
  - 14 variables validated
  - 3 with warnings
  - 1 with errors
```

**Expandable Per-Variable**:
```
▼ cohortPatientId (1 error)
  ✗ no_duplicates: 3 duplicate patient IDs found in rows 10, 45, 67

▼ birthSex (2 warnings)
  ⚠ type_is_enum: 2 invalid values in rows 45, 67
  ⚠ required_when: Missing in 5 rows where presentSex is absent
```

**Exports**:
- Downloadable CSV/Excel of all issues
- Columns: variable_name, rule, severity, affected_rows, row_numbers, message
- PHI redaction enforced
- Audit log for all exports

**Primary Approach**:
- Database-driven reports (ValidationRun → ValidationVariable → ValidationCheck)
- Quarto HTML notebooks optional, not source of truth
- Keep notebooks for legacy compatibility during transition

### Cleanup Policies (Locked)

#### Precheck Validation
```
Files to Delete After Validation:
✓ Raw file (transient storage)
✓ Processed file (transient storage)
✓ DuckDB file (scratch storage)

Files to Keep:
✓ Validation results (database: ValidationRun + ValidationVariable + ValidationCheck)
```

**PHI Tracking**:
- Log creation of raw, processed, DuckDB
- Log deletion of all three
- Verify cleanup completed via PHI tracking queries

#### File Submission
```
Files to Delete After Validation:
✓ DuckDB file (scratch storage)

Files to Keep:
✓ Raw file (permanent storage)
✓ Processed file (permanent storage)
✓ Validation results (database)
```

**PHI Tracking**:
- Log creation of raw (permanent), processed (permanent), DuckDB (scratch)
- Log deletion of DuckDB only
- Raw and processed remain for future reprocessing

## Implementation Phases

### Phase 1: Foundation (Models + Services)
1. Create ValidationRun, ValidationVariable, ValidationCheck models
2. Implement DuckDBConversionService with PHI tracking
3. Implement DataFileStatisticsService
4. Implement DefinitionProcessingService
5. Create BaseValidator abstract class

### Phase 2: Validator Library
1. Implement type validators (enum, boolean, date, year, id, string)
2. Implement constraint validators (range, no_duplicates, allowed_values)
3. Implement conditional validators (required_when, forbidden_when)
4. Write tests for each validator against R reference implementation

### Phase 3: Execution Service
1. Implement ValidationExecutionService
2. Create Celery tasks for per-variable validation
3. Integrate with existing task chains
4. Add progress tracking and status updates

### Phase 4: UI & Reporting
1. Update precheck validation UI to show ValidationVariable progress
2. Implement expandable per-variable issue display
3. Implement ValidationReportService (CSV/Excel exports)
4. Add PHI redaction and audit logging

### Phase 5: Integration
1. Update precheck workflow to use new validation pipeline
2. Update submission workflow to use new validation pipeline
3. Deprecate UploadPrecheck and Quarto notebook approach
4. Migration path for existing precheck data

## Migration Strategy

### Deprecating UploadPrecheck

**Current State**:
- UploadPrecheck model stores audit results
- Quarto notebooks generate HTML reports
- Single-task processing (not granular)

**New State**:
- ValidationRun (polymorphic) replaces UploadPrecheck
- Database-driven results replace Quarto notebooks
- Per-variable Celery tasks for granularity

**Migration Steps**:
1. Build new validation pipeline alongside existing system
2. Run both systems in parallel for testing
3. Compare results to ensure parity
4. Switch precheck to new system
5. Deprecate UploadPrecheck model (keep for historical data)
6. Archive Quarto notebook templates

### Compatibility Period

During migration:
- Keep UploadPrecheck read-only for historical data
- New validations use ValidationRun
- Both UIs available during transition
- Provide data export from old to new format if needed

## Testing Strategy

### Validator Parity Testing

For each validator:
1. Use same test data as R NAATools tests
2. Compare Python results to R results
3. Ensure SQL queries produce identical row matches
4. Verify message formatting matches

### Integration Testing

1. Test precheck workflow end-to-end
2. Test submission workflow end-to-end
3. Test PHI tracking and cleanup
4. Test parallel task execution
5. Test failure scenarios and rollback

### Performance Testing

1. Test with large files (40M rows, 2GB)
2. Test parallel validation (14 variables simultaneously)
3. Test DuckDB conversion performance
4. Test database query performance for results display

## Open Questions for Future

1. Should we support custom validators per cohort?
2. Should we version validation rules for historical comparison?
3. Should we add a "validation review" workflow for data managers?
4. Should we generate trend reports (data quality over time)?
5. Should we integrate with external data quality tools?

## References

- Patient Definition: `depot/data/definitions/patient_definition.json`
- R Validators: `NAATools/R/validate_*.R`
- Current Auditor: `depot/data/upload_prechecker.py`
- PHI Tracking: `depot/models/phi_tracking.py`
