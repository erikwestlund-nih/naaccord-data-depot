# Audit Domain - CLAUDE.md

## Domain Overview

The audit domain manages the complete clinical data validation workflow, from file upload through DuckDB conversion to R-based analysis and HTML report generation. This system combines Python data processing with R statistical validation using the NAATools package and Quarto notebook compilation.

## Core Architecture

### Primary Models

**Audit** (`depot/models/audit.py`)
- Central audit record tracking file validation workflow
- Links to uploaded file, cohort, user, and data file type
- Manages processing status and error handling
- Stores paths to processed DuckDB files and generated reports

**TemporaryFile** (`depot/models/temporaryfile.py`)
- Tracks uploaded files before processing
- Handles file storage and cleanup
- Links to audit records for processing

**Notebook** (`depot/models/notebook.py`)
- Manages Quarto notebook compilation
- Polymorphic relationship to audit and other models
- Tracks compilation status and error handling

### Audit Processing Workflow

```
1. File Upload → TemporaryFile
2. Audit Record Creation
3. DuckDB Conversion (async)
4. R Analysis & Report Generation (async)
5. Report Storage & URL Generation
6. Cleanup of Temporary Files
```

## Key Business Logic Patterns

### Audit Creation and Processing

```python
# Create audit record from form submission
def create_audit(user, cohort, data_file_type, uploaded_file):
    """Create audit record and trigger processing"""

    # Create temporary file record
    temp_file = TemporaryFile.objects.create(
        user=user,
        original_filename=uploaded_file.name,
        file_size=uploaded_file.size
    )

    # Store file content
    temp_file.save_content(uploaded_file.read())

    # Create audit record
    audit = Audit.objects.create(
        user=user,
        cohort=cohort,
        data_file_type=data_file_type,
        temporary_file=temp_file,
        status='pending'
    )

    # Trigger async processing
    from depot.tasks.upload_precheck import process_upload_precheck
    process_upload_precheck.delay(audit.id)

    return audit
```

### DuckDB Conversion Process

**Location**: `depot/data/upload_prechecker.py`

```python
class Auditor:
    def __init__(self, audit):
        self.audit = audit
        self.temp_dir = None
        self.db_path = None
        self.conn = None

    def load_duckdb(self):
        """Convert uploaded CSV/TSV to DuckDB format"""
        # Create temporary directory for processing
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "audit_data.duckdb"

        # Connect to DuckDB
        self.conn = duckdb.connect(str(self.db_path))

        # Load data with automatic type detection
        sql = """
            CREATE TABLE data AS
            SELECT * FROM read_csv_auto(?, header=true, sample_size=100000)
        """
        self.conn.execute(sql, [self.audit.temporary_file.s3_key])

        # Store DuckDB path for R processing
        self.audit.duckdb_path = str(self.db_path)
        self.audit.status = 'processing_notebook'
        self.audit.save()

        return self.db_path

    def get_column_info(self):
        """Extract column information for validation"""
        columns_sql = "DESCRIBE data"
        columns_result = self.conn.execute(columns_sql).fetchall()

        return {
            'columns': [col[0] for col in columns_result],
            'types': [col[1] for col in columns_result],
            'row_count': self.conn.execute("SELECT COUNT(*) FROM data").fetchone()[0]
        }
```

### R Integration and NAATools

**NAATools Package Integration**:
```python
def setup_r_environment(self):
    """Configure R environment for audit processing"""
    r_script = f"""
    # Load required libraries
    library(NAATools)
    library(duckdb)
    library(dplyr)
    library(here)

    # Connect to DuckDB
    con <- DBI::dbConnect(duckdb::duckdb(), "{self.db_path}")

    # Read data
    data <- DBI::dbReadTable(con, "data")

    # Load definition
    definition_path <- "{self.get_definition_path()}"
    definition <- NAATools::read_definition(definition_path)

    # Validate data against definition
    validation_results <- NAATools::validate_data(data, definition)

    # Generate summary statistics
    summary_stats <- NAATools::summarize_data(data, definition)
    """

    return r_script
```

### Quarto Notebook Compilation

**Location**: `depot/models/notebook.py`

```python
class Notebook(models.Model):
    # Polymorphic relationship to any model (usually Audit)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    name = models.CharField(max_length=200)
    template_path = models.CharField(max_length=200)
    data_file_type = models.ForeignKey(DataFileType, on_delete=models.CASCADE)

    # Compilation tracking
    status = models.CharField(max_length=50, default='pending')
    compiled_at = models.DateTimeField(null=True)
    error = models.TextField(null=True)

    # Storage
    s3_key = models.CharField(max_length=500, null=True)

    def compile(self):
        """Compile Quarto notebook to HTML"""
        try:
            self.status = 'compiling'
            self.save()

            # Get template and prepare environment
            template_path = self.get_template_path()
            work_dir = self.setup_work_directory()

            # Run Quarto compilation
            result = subprocess.run([
                'quarto', 'render', template_path,
                '--output-dir', work_dir,
                '--execute-params', self.get_params_json()
            ], capture_output=True, text=True)

            if result.returncode == 0:
                # Store compiled HTML
                html_path = work_dir / f"{self.name}.html"
                self.store_compiled_report(html_path)

                self.status = 'completed'
                self.compiled_at = timezone.now()
            else:
                self.status = 'failed'
                self.error = result.stderr

            self.save()

        except Exception as e:
            self.status = 'failed'
            self.error = str(e)
            self.save()
            raise

    def get_params_json(self):
        """Generate parameters for Quarto notebook"""
        audit = self.content_object
        return json.dumps({
            'duckdb_path': audit.duckdb_path,
            'definition_path': audit.data_file_type.definition_path,
            'cohort_name': audit.cohort.name,
            'file_type': audit.data_file_type.name,
            'audit_id': audit.id
        })
```

## Data Definition Integration

### JSON Definition Structure

**Location**: `depot/data/definitions/*.json`

```json
{
    "name": "patient",
    "description": "Patient demographics and enrollment data",
    "variables": [
        {
            "name": "cohortPatientId",
            "type": "id",
            "description": "Unique patient identifier within cohort",
            "validators": ["required"],
            "summarizers": ["count", "unique"]
        },
        {
            "name": "enrollmentDate",
            "type": "date",
            "description": "Date of cohort enrollment",
            "validators": ["required", "date_format"],
            "summarizers": ["min_max", "histogram"]
        },
        {
            "name": "ageAtEnrollment",
            "type": "int",
            "description": "Age at enrollment in years",
            "validators": ["range:0:120"],
            "summarizers": ["summary_stats", "histogram"]
        }
    ]
}
```

### Definition Processing in R

```r
# R code patterns for definition processing
process_definition <- function(data, definition_path) {
    # Load definition
    definition <- NAATools::read_definition(definition_path)

    # Validate each variable
    validation_results <- list()
    for (var in definition$variables) {
        var_validation <- validate_variable(
            data[[var$name]],
            var$validators,
            var$type
        )
        validation_results[[var$name]] <- var_validation
    }

    # Generate summaries
    summary_results <- list()
    for (var in definition$variables) {
        var_summary <- summarize_variable(
            data[[var$name]],
            var$summarizers,
            var$type
        )
        summary_results[[var$name]] <- var_summary
    }

    return(list(
        validation = validation_results,
        summary = summary_results
    ))
}
```

## Celery Task Integration

### Primary Processing Task

**Location**: `depot/tasks/upload_precheck.py`

```python
@shared_task(bind=True)
def process_upload_precheck(self, audit_id):
    """Process audit file through complete workflow"""
    try:
        audit = Audit.objects.get(id=audit_id)
        audit.status = 'processing_duckdb'
        audit.save()

        # Initialize auditor
        auditor = Auditor(audit)

        # Convert to DuckDB
        duckdb_path = auditor.load_duckdb()

        # Track file creation
        PHIFileTracking.log_operation(
            cohort=audit.cohort,
            user=audit.user,
            action='nas_duckdb_created',
            file_path=str(duckdb_path),
            content_object=audit
        )

        # Create and compile notebook
        notebook = Notebook.objects.create(
            content_object=audit,
            name=f"audit_{audit.id}",
            template_path=f"audit/{audit.data_file_type.name}_audit.qmd",
            data_file_type=audit.data_file_type
        )

        notebook.compile()

        if notebook.status == 'completed':
            audit.status = 'completed'
            audit.notebook = notebook
        else:
            audit.status = 'failed'
            audit.error_message = notebook.error

        audit.save()

    except Exception as e:
        audit.status = 'failed'
        audit.error_message = str(e)
        audit.save()

        # Track failure
        PHIFileTracking.log_operation(
            cohort=audit.cohort,
            user=audit.user,
            action='conversion_failed',
            error_message=str(e),
            content_object=audit
        )

        raise self.retry(exc=e, countdown=60, max_retries=3)
```

## Report Generation Patterns

### Quarto Template Structure

**Location**: `depot/notebooks/audit/generic_audit.qmd`

```yaml
---
title: "Data Audit Report"
format:
  html:
    embed-resources: true
    theme: bootstrap
    toc: true
params:
  duckdb_path: ""
  definition_path: ""
  cohort_name: ""
  file_type: ""
  audit_id: 0
---

```{r setup, include=FALSE}
library(NAATools)
library(duckdb)
library(dplyr)
library(ggplot2)
library(knitr)
library(kableExtra)

# Connect to data
con <- DBI::dbConnect(duckdb::duckdb(), params$duckdb_path)
data <- DBI::dbReadTable(con, "data")

# Load definition
definition <- NAATools::read_definition(params$definition_path)
```

## Summary Statistics

Total records: `r nrow(data)`
Total variables: `r ncol(data)`

```{r validation}
# Perform validation
validation_results <- NAATools::validate_data(data, definition)

# Display validation summary
validation_summary <- validation_results %>%
  summarise(
    total_errors = sum(error_count),
    total_warnings = sum(warning_count),
    variables_with_issues = sum(error_count > 0 | warning_count > 0)
  )

kable(validation_summary, caption = "Validation Summary") %>%
  kable_styling(bootstrap_options = c("striped", "hover"))
```
```

### Dynamic Report Content

```python
def generate_report_context(audit):
    """Generate context data for report template"""
    auditor = Auditor(audit)

    # Get basic data info
    data_info = auditor.get_column_info()

    # Load definition for validation context
    definition = load_definition(audit.data_file_type.definition_path)

    context = {
        'audit_id': audit.id,
        'cohort_name': audit.cohort.name,
        'file_type': audit.data_file_type.name,
        'upload_date': audit.created_at,
        'user_name': audit.user.get_full_name(),
        'data_info': data_info,
        'definition': definition,
        'duckdb_path': audit.duckdb_path,
        'expected_columns': [var['name'] for var in definition['variables']]
    }

    return context
```

## Error Handling and Recovery

### Validation Error Patterns

```python
class ValidationError(Exception):
    """Custom validation error with context"""
    def __init__(self, message, error_code=None, context=None):
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}

def handle_validation_error(audit, error):
    """Handle validation errors with detailed logging"""
    audit.status = 'failed'
    audit.error_message = str(error)

    # Store detailed error context
    error_context = {
        'error_type': type(error).__name__,
        'error_code': getattr(error, 'error_code', None),
        'context': getattr(error, 'context', {}),
        'timestamp': timezone.now().isoformat()
    }

    audit.error_context = json.dumps(error_context)
    audit.save()

    # Log for PHI tracking
    PHIFileTracking.log_operation(
        cohort=audit.cohort,
        user=audit.user,
        action='conversion_failed',
        error_message=str(error),
        content_object=audit
    )
```

### Recovery Mechanisms

```python
def retry_failed_audit(audit_id):
    """Retry failed audit with cleanup"""
    audit = Audit.objects.get(id=audit_id)

    # Clean up any partial processing
    if audit.duckdb_path and os.path.exists(audit.duckdb_path):
        os.remove(audit.duckdb_path)

    # Reset status
    audit.status = 'pending'
    audit.error_message = None
    audit.error_context = None
    audit.save()

    # Restart processing
    process_upload_precheck.delay(audit_id)
```

## Performance Optimization

### Large File Handling

```python
def optimize_duckdb_for_large_files(self):
    """Configure DuckDB for large file processing"""
    # Increase memory limit
    self.conn.execute("SET memory_limit='4GB'")

    # Optimize for analytics workload
    self.conn.execute("SET threads TO 4")

    # Use columnar storage for better compression
    self.conn.execute("PRAGMA enable_object_cache")

    # Sample large files for type detection
    if self.audit.temporary_file.file_size > 100 * 1024 * 1024:  # 100MB
        sample_size = 50000
    else:
        sample_size = -1  # Use all data

    return sample_size
```

### R Memory Management

```r
# R patterns for memory-efficient processing
process_large_dataset <- function(duckdb_path, chunk_size = 10000) {
    con <- DBI::dbConnect(duckdb::duckdb(), duckdb_path)

    # Get total row count
    total_rows <- DBI::dbGetQuery(con, "SELECT COUNT(*) as n FROM data")$n

    # Process in chunks
    results <- list()
    for (i in seq(1, total_rows, chunk_size)) {
        chunk_sql <- sprintf(
            "SELECT * FROM data LIMIT %d OFFSET %d",
            chunk_size, i - 1
        )
        chunk_data <- DBI::dbGetQuery(con, chunk_sql)

        # Process chunk
        chunk_result <- process_data_chunk(chunk_data)
        results[[length(results) + 1]] <- chunk_result

        # Clean up chunk data
        rm(chunk_data)
        gc()
    }

    # Combine results
    final_result <- do.call(rbind, results)
    return(final_result)
}
```

## Testing Patterns

### Audit Testing

```python
class AuditTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser')
        self.cohort = Cohort.objects.create(name='TEST_COHORT')
        self.data_file_type = DataFileType.objects.create(
            name='patient',
            definition_path='depot/data/definitions/patient.json'
        )

    def test_audit_creation(self):
        """Test audit record creation and processing trigger"""
        # Create test file
        test_content = b"cohortPatientId,enrollmentDate\n001,2023-01-01\n"
        uploaded_file = SimpleUploadedFile(
            "test_patient.csv",
            test_content,
            content_type="text/csv"
        )

        # Create audit
        audit = create_audit(
            user=self.user,
            cohort=self.cohort,
            data_file_type=self.data_file_type,
            uploaded_file=uploaded_file
        )

        # Verify audit record
        self.assertEqual(audit.status, 'pending')
        self.assertEqual(audit.user, self.user)
        self.assertEqual(audit.cohort, self.cohort)

    def test_duckdb_conversion(self):
        """Test DuckDB conversion process"""
        audit = self.create_test_audit()
        auditor = Auditor(audit)

        # Convert to DuckDB
        duckdb_path = auditor.load_duckdb()

        # Verify conversion
        self.assertTrue(os.path.exists(duckdb_path))

        # Check data accessibility
        conn = duckdb.connect(str(duckdb_path))
        result = conn.execute("SELECT COUNT(*) FROM data").fetchone()
        self.assertGreater(result[0], 0)
```

### R Integration Testing

```python
def test_r_environment_setup(self):
    """Test R environment configuration"""
    audit = self.create_test_audit()
    auditor = Auditor(audit)

    # Setup DuckDB
    duckdb_path = auditor.load_duckdb()

    # Test R environment
    r_script = f"""
    library(NAATools)
    library(duckdb)

    con <- DBI::dbConnect(duckdb::duckdb(), "{duckdb_path}")
    data <- DBI::dbReadTable(con, "data")

    # Test basic operations
    cat("Rows:", nrow(data), "\n")
    cat("Columns:", ncol(data), "\n")
    """

    result = subprocess.run(
        ['R', '--slave', '-e', r_script],
        capture_output=True,
        text=True
    )

    self.assertEqual(result.returncode, 0)
    self.assertIn("Rows:", result.stdout)
```

## Common Query Patterns

### Audit Status Queries

```python
# Get audits by status
pending_audits = Audit.objects.filter(status='pending')
completed_audits = Audit.objects.filter(status='completed')
failed_audits = Audit.objects.filter(status='failed')

# Get audits for specific cohort
cohort_audits = Audit.objects.filter(
    cohort=cohort
).select_related('user', 'data_file_type')

# Get recent audits with reports
recent_with_reports = Audit.objects.filter(
    status='completed',
    created_at__gte=timezone.now() - timedelta(days=7)
).select_related('notebook')
```

### Performance Monitoring

```python
# Monitor processing times
from django.db.models import Avg, Count
from django.utils import timezone

processing_stats = Audit.objects.filter(
    status='completed',
    created_at__gte=timezone.now() - timedelta(days=30)
).aggregate(
    avg_processing_time=Avg('completed_at') - Avg('created_at'),
    total_processed=Count('id')
)

# Check for stuck audits
stuck_audits = Audit.objects.filter(
    status__in=['processing_duckdb', 'processing_notebook'],
    created_at__lt=timezone.now() - timedelta(hours=2)
)
```

## Related Documentation
- [Upload Submission Workflow](../../docs/technical/upload-submission-workflow.md)
- [PHI File Tracking System](../../docs/security/PHIFileTracking-system.md)
- [Data Definitions Guide](../../docs/technical/data-definitions.md)
- [R Integration Patterns](../../docs/technical/r-integration.md)
- [Storage Domain](../storage/CLAUDE.md)
- [Security Domain](../security/CLAUDE.md)