"""
Celery task orchestration for granular validation system.

This module coordinates validation execution, creating ValidationVariable
records for each column in the data definition.

Key features:
- Creates ValidationVariable records from definition
- Tracks validation progress
- Handles errors gracefully

See: docs/technical/granular-validation-system.md
"""
from celery import shared_task
import logging
import traceback
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from depot.models import ValidationRun, ValidationVariable, ValidationCheck, DataTableFile, SubmissionValidation
from depot.services.submission_validation_service import SubmissionValidationService
from depot.data.definition_loader import get_definition_for_type
from depot.tasks.summary_generation import generate_variable_summary_task

logger = logging.getLogger(__name__)


def _refresh_submission_summary_for_run(validation_run: ValidationRun):
    try:
        if validation_run.content_type.model_class() is not DataTableFile:
            return

        data_file = validation_run.content_object
        if not data_file:
            return

        submission = data_file.data_table.submission
        summary, _ = SubmissionValidation.objects.get_or_create(submission=submission)

        data_files = DataTableFile.objects.filter(
            data_table__submission=submission,
            is_current=True
        ).select_related('latest_validation_run')

        total_files = data_files.count()
        errors = 0
        warnings = 0
        has_running = False
        has_failed = False
        has_pending = False
        latest_run = summary.latest_run

        for file in data_files:
            run = file.latest_validation_run
            if not run:
                has_pending = True
                continue

            if latest_run is None:
                latest_run = run
            else:
                candidate = run.completed_at or run.started_at
                chosen = latest_run.completed_at or latest_run.started_at
                if candidate and chosen and candidate > chosen:
                    latest_run = run

            if run.status in ('pending', 'running'):
                has_running = True
            elif run.status == 'failed':
                has_failed = True

            if run.variables_with_errors > 0:
                errors += 1
            if run.variables_with_warnings > 0:
                warnings += 1

        total_runs = ValidationRun.objects.filter(
            content_type=ContentType.objects.get_for_model(DataTableFile),
            object_id__in=data_files.values_list('id', flat=True)
        ).count()

        if has_failed:
            summary.status = 'failed'
        elif has_running:
            summary.status = 'running'
        elif has_pending or total_files == 0:
            summary.status = 'pending'
        else:
            summary.status = 'completed'

        summary.total_files = total_files
        summary.files_with_errors = errors
        summary.files_with_warnings = warnings
        summary.total_runs = total_runs
        summary.latest_run = latest_run

        if latest_run:
            summary.last_started_at = latest_run.started_at
            if latest_run.status == 'completed':
                summary.last_completed_at = latest_run.completed_at

        try:
            report = SubmissionValidationService(submission).get_comprehensive_validation_report()
            summary.patient_validation_summary = report.get('summary', {})
        except Exception as exc:
            logger.warning("Unable to compute patient validation summary: %s", exc)

        summary.save()
    except Exception as exc:
        logger.warning("Failed to refresh submission validation summary: %s", exc, exc_info=True)


@shared_task
def start_validation_run(validation_run_id):
    """
    Start a validation run by creating ValidationVariable records.

    This is the main entry point for validation. It:
    1. Loads the data definition for the file type
    2. Creates ValidationVariable instances for each column
    3. Marks the run as completed (actual validation logic TBD)

    Args:
        validation_run_id: ID of ValidationRun to process

    Returns:
        dict: Summary of created variables
    """
    try:
        validation_run = ValidationRun.objects.get(id=validation_run_id)

        # Mark as running
        validation_run.mark_started()
        logger.info(f"Starting validation run {validation_run_id}")

        _refresh_submission_summary_for_run(validation_run)

        # Ensure no residual variables remain
        ValidationCheck.objects.with_deleted().filter(
            validation_variable__validation_run=validation_run
        ).force_delete()
        ValidationVariable.objects.with_deleted().filter(
            validation_run=validation_run
        ).force_delete()

        # Load data definition
        try:
            definition = get_definition_for_type(validation_run.data_file_type.name)
        except Exception as e:
            error_msg = f'Failed to load data definition: {str(e)}'
            logger.error(f"Failed to load definition: {e}")
            validation_run.mark_failed(error_msg)
            return {
                'status': 'failed',
                'error': error_msg
            }

        # Create ValidationVariable objects for each column in the definition
        variables = []
        definition_list = definition.get_definition()

        # Definition is a list of variable definitions
        if not isinstance(definition_list, list):
            error_msg = f"Definition is not a list: {type(definition_list)}"
            logger.error(error_msg)
            validation_run.mark_failed(error_msg)
            return {
                'status': 'failed',
                'error': error_msg
            }

        for var_def in definition_list:
            column_name = var_def.get('name')
            column_type = var_def.get('type', 'string')
            display_name = var_def.get('label', column_name)  # Use label as display name, fallback to column name

            variable = ValidationVariable.objects.create(
                validation_run=validation_run,
                column_name=column_name,
                column_type=column_type,
                display_name=display_name,
                status='pending'
            )
            variables.append(variable)
            logger.info(f"Created ValidationVariable: {column_name} (id={variable.id})")

        # Update total variable count
        validation_run.total_variables = len(variables)
        validation_run.save(update_fields=['total_variables'])

        if len(variables) == 0:
            logger.warning(f"No variables found in definition for run {validation_run_id}")
            validation_run.mark_completed()
            return {
                'validation_run_id': validation_run_id,
                'total_variables': 0,
                'message': 'No variables in definition'
            }

        logger.info(f"Created {len(variables)} validation variables for run {validation_run_id}")

        # Execute validation for each variable
        for variable in variables:
            try:
                execute_variable_validation.delay(variable.id, definition_list)
            except Exception as e:
                logger.error(f"Failed to queue validation for variable {variable.id}: {e}")

        _refresh_submission_summary_for_run(validation_run)

        return {
            'validation_run_id': validation_run_id,
            'total_variables': len(variables),
            'status': 'running'
        }

    except Exception as e:
        logger.error(f"Failed to start validation run {validation_run_id}: {e}", exc_info=True)
        try:
            validation_run = ValidationRun.objects.get(id=validation_run_id)
            validation_run.mark_failed(str(e))
        except Exception as save_error:
            logger.error(f"Failed to mark validation run as failed: {save_error}")
        raise


# Helper function to create ValidationRun from upload
def create_validation_run_for_upload(content_object, duckdb_path, user):
    """
    Create and start a ValidationRun for an uploaded file.

    This is a convenience function for integrating the validation system
    with existing upload workflows (Audit, PrecheckRun, etc.).

    Args:
        content_object: Object being validated (Audit, PrecheckRun, etc.)
        duckdb_path: Path to DuckDB file
        user: User who initiated validation

    Returns:
        ValidationRun: Created validation run
    """
    # Get content type
    content_type = ContentType.objects.get_for_model(content_object)

    # Determine data file type
    if hasattr(content_object, 'data_file_type'):
        data_file_type = content_object.data_file_type
    else:
        raise ValueError("Content object must have data_file_type attribute")

    # Create ValidationRun
    validation_run = ValidationRun.objects.create(
        content_type=content_type,
        object_id=content_object.id,
        data_file_type=data_file_type,
        duckdb_path=duckdb_path
    )

    logger.info(f"Created validation run {validation_run.id} for {content_type.model} {content_object.id}")

    # Start validation
    start_validation_run.delay(validation_run.id)

    return validation_run


def _reset_validation_run(
    validation_run: ValidationRun,
    duckdb_path: str | None = None,
    raw_file_path: str | None = None,
    processing_metadata: dict | None = None,
):
    """Reset an existing validation run so it can be reused."""

    ValidationCheck.objects.with_deleted().filter(
        validation_variable__validation_run=validation_run
    ).force_delete()
    ValidationVariable.objects.with_deleted().filter(
        validation_run=validation_run
    ).force_delete()

    updates = {
        'status': 'pending',
        'started_at': None,
        'completed_at': None,
        'error_message': '',
        'total_variables': 0,
        'completed_variables': 0,
        'variables_with_warnings': 0,
        'variables_with_errors': 0,
    }

    if duckdb_path is not None:
        updates['duckdb_path'] = duckdb_path
    if raw_file_path is not None:
        updates['raw_file_path'] = raw_file_path
    if processing_metadata is not None:
        updates['processing_metadata'] = processing_metadata

    for field, value in updates.items():
        setattr(validation_run, field, value)

    validation_run.save(update_fields=list(updates.keys()) + ['updated_at'])


def ensure_validation_run_for_data_file(
    data_file: DataTableFile,
    duckdb_path: str | None = None,
    processing_metadata: dict | None = None,
):
    """Ensure a validation run exists for a data file, reusing a single run."""

    if not data_file:
        raise ValueError("data_file must be provided")

    data_table = data_file.data_table
    data_file_type = data_table.data_file_type

    run = data_file.latest_validation_run
    if run:
        _reset_validation_run(
            run,
            duckdb_path or data_file.duckdb_file_path,
            data_file.raw_file_path,
            processing_metadata,
        )
        logger.info("Reusing validation run %s for DataTableFile %s", run.id, data_file.id)
        _refresh_submission_summary_for_run(run)
        return run

    content_type = ContentType.objects.get_for_model(data_file)
    run = ValidationRun.objects.create(
        content_type=content_type,
        object_id=data_file.id,
        data_file_type=data_file_type,
        duckdb_path=duckdb_path or data_file.duckdb_file_path,
        raw_file_path=data_file.raw_file_path,
        processing_metadata=processing_metadata or {},
    )

    logger.info(
        "Created validation run %s for DataTableFile %s (type=%s)",
        run.id,
        data_file.id,
        data_file_type.name,
    )

    DataTableFile.objects.filter(id=data_file.id).update(latest_validation_run=run)
    _refresh_submission_summary_for_run(run)
    return run


@shared_task(bind=True)
def start_validation_for_data_file(self, task_data):
    """
    Celery task wrapper to kick off validation for a DataTableFile.

    If the table has multiple files, combines their DuckDB files into one
    for unified validation.
    """
    # Check if workflow should stop (file was rejected)
    if task_data and task_data.get('workflow_should_stop'):
        logger.info(f"VALIDATION: Workflow stopped (file rejected), skipping validation")
        return task_data

    data_file_id = task_data.get('data_file_id')
    if not data_file_id:
        raise ValueError('task_data missing data_file_id')

    try:
        data_file = DataTableFile.objects.get(id=data_file_id)
    except DataTableFile.DoesNotExist as exc:
        logger.error("Validation start failed: DataTableFile %s not found", data_file_id)
        raise exc

    # Check if we need to combine multiple DuckDB files
    data_table = data_file.data_table
    current_files = data_table.get_current_files()

    if current_files.count() > 1:
        # Check if all files already point to the same DuckDB (already combined at creation time)
        duckdb_paths = set(f.duckdb_file_path for f in current_files if f.duckdb_file_path)

        if len(duckdb_paths) == 1:
            # All files point to same DuckDB - already combined!
            duckdb_path = duckdb_paths.pop()
            logger.info(f"Table {data_table.id} has {current_files.count()} files, but they all point to the same combined DuckDB: {duckdb_path}")
        else:
            # Different DuckDB files - need to combine them (legacy case)
            logger.info(f"Table {data_table.id} has {current_files.count()} files with different DuckDBs, combining them")

            from depot.services.duckdb_combiner import DuckDBCombinerService
            from pathlib import Path
            import tempfile

            workspace_dir = Path(tempfile.gettempdir()) / 'naaccord_workspace' / 'validation'
            combiner = DuckDBCombinerService(workspace_dir)

            # Get user for PHI tracking
            from depot.models import User
            user = User.objects.get(id=task_data.get('user_id'))

            combined_path = combiner.combine_files(
                data_files=list(current_files),
                cohort=data_file.data_table.submission.cohort,
                user=user
            )

            duckdb_path = combined_path
            logger.info(f"Using combined DuckDB at {combined_path}")
    else:
        # Single file - use its DuckDB directly
        duckdb_path = task_data.get('duckdb_path') or data_file.duckdb_file_path
        logger.info(f"Single file, using DuckDB at {duckdb_path}")

    processing_metadata = task_data.get('processing_metadata')
    run = ensure_validation_run_for_data_file(
        data_file,
        duckdb_path=duckdb_path,
        processing_metadata=processing_metadata,
    )

    start_validation_run.delay(run.id)

    # CRITICAL: If using combined DuckDB, update ALL files in the table to point to this validation run
    # This ensures the UI shows the latest validation for all files, not just the one that triggered upload
    if current_files.count() > 1:
        logger.info(f"Updating all {current_files.count()} files in table {data_table.id} to use ValidationRun {run.id}")
        current_files.update(latest_validation_run=run)

    updated = task_data.copy()
    updated['validation_run_id'] = run.id
    updated['used_combined_duckdb'] = current_files.count() > 1

    return updated


def _reset_validation_variable(variable: ValidationVariable):
    variable.status = 'pending'
    variable.started_at = None
    variable.completed_at = None
    variable.error_message = ''
    variable.total_rows = 0
    variable.null_count = 0
    variable.empty_count = 0
    variable.valid_count = 0
    variable.invalid_count = 0
    variable.warning_count = 0
    variable.error_count = 0
    variable.summary = {}
    variable.save(update_fields=[
        'status', 'started_at', 'completed_at', 'error_message',
        'total_rows', 'null_count', 'empty_count', 'valid_count',
        'invalid_count', 'warning_count', 'error_count', 'summary', 'updated_at'
    ])


@shared_task
def revalidate_single_variable(variable_id):
    """Reset and re-run validation for a single variable."""
    try:
        variable = ValidationVariable.objects.select_related('validation_run').get(id=variable_id)
    except ValidationVariable.DoesNotExist:
        logger.error("Validation variable %s not found", variable_id)
        return {'status': 'missing'}

    _reset_validation_variable(variable)
    run = variable.validation_run
    run.mark_started()
    _refresh_submission_summary_for_run(run)

    definition = get_definition_for_type(run.data_file_type.name)
    definition_list = definition.get_definition()

    execute_variable_validation.delay(variable.id, definition_list)

    return {
        'status': 'queued',
        'validation_run_id': run.id,
        'variable_id': variable.id,
    }


@shared_task
def execute_variable_validation(validation_variable_id, definition_list):
    """
    Execute validation for a single variable.

    Args:
        validation_variable_id: ID of ValidationVariable to validate
        definition_list: Full definition list (to find this variable's definition)

    Returns:
        dict: Validation results
    """
    from depot.validators.variable_validator import VariableValidator

    try:
        variable = ValidationVariable.objects.select_related('validation_run').get(id=validation_variable_id)
        variable.mark_started()

        logger.info(f"Validating variable {variable.column_name} (id={variable.id})")

        # Find this variable's definition
        variable_def = None
        for var_def in definition_list:
            if var_def.get('name') == variable.column_name:
                variable_def = var_def
                break

        if not variable_def:
            error_msg = f"Definition not found for variable '{variable.column_name}'"
            logger.error(error_msg)
            variable.mark_failed(error_msg)
            return {'status': 'failed', 'error': error_msg}

        # Get submission and data_file context for cross-file validation
        submission = None
        data_file = None

        try:
            from depot.models import DataTableFile, PrecheckValidation
            content_object = variable.validation_run.content_object

            if isinstance(content_object, DataTableFile):
                # Extract from DataTableFile
                data_file = content_object
                submission = data_file.data_table.submission
                logger.info(f"Cross-file validation context: submission={submission.id}, data_file={data_file.id}")
            elif isinstance(content_object, PrecheckValidation):
                # Extract from PrecheckValidation
                submission = content_object.cohort_submission
                if submission:
                    logger.info(f"Cross-file validation context from precheck: submission={submission.id}")
                else:
                    logger.info("PrecheckValidation has no cohort_submission - cross-file validation disabled")
        except Exception as e:
            logger.warning(f"Could not extract submission context for cross-file validation: {e}")

        # Run validation
        validator = VariableValidator(
            duckdb_path=variable.validation_run.duckdb_path,
            variable_def=variable_def,
            validation_variable=variable,
            submission=submission,
            data_file=data_file
        )

        with validator:
            results = validator.validate()

        # Update variable with results
        variable.total_rows = results['total_rows']
        variable.null_count = results['null_count']
        variable.empty_count = results['empty_count']
        variable.valid_count = results['valid_count']
        variable.invalid_count = results['invalid_count']
        variable.warning_count = results['warning_count']
        variable.error_count = results['error_count']
        variable.summary = results.get('summary', {})
        variable.save(update_fields=[
            'total_rows', 'null_count', 'empty_count', 'valid_count',
            'invalid_count', 'warning_count', 'error_count', 'summary', 'updated_at'
        ])

        # Delete old checks (in case of re-validation)
        variable.checks.all().delete()

        # Create ValidationCheck records for each check
        for check in results['checks']:
            # Extract affected rows information if present
            affected_rows = check.get('affected_rows', [])
            affected_count = check.get('affected_row_count', 0)

            # Format row_numbers string for display (file_id:row format)
            row_numbers_str = None
            meta_data = check.get('details', {})

            if affected_rows:
                # Create display string: "file_5:row_123, file_5:row_456, file_7:row_12, ..."
                row_numbers_list = [
                    f"file_{row['file_id']}:row_{row['source_row']}"
                    for row in affected_rows[:100]  # Limit to first 100 for display
                ]
                row_numbers_str = ", ".join(row_numbers_list)

                # Store full affected_rows data in meta for detailed analysis
                meta_data['affected_rows'] = affected_rows
                meta_data['has_file_tracking'] = True

            ValidationCheck.objects.create(
                validation_variable=variable,
                rule_key=check['check_type'],
                passed=check['passed'],
                severity=check['severity'],
                message=check['message'],
                rule_params=check.get('details', {}),
                affected_row_count=affected_count,
                row_numbers=row_numbers_str,
                meta=meta_data
            )

        # Mark as completed
        variable.mark_completed()
        try:
            generate_variable_summary_task.delay(variable.id)
        except Exception as exc:
            logger.warning("Failed to enqueue VariableSummary generation for variable %s: %s", variable.id, exc)

        run = variable.validation_run
        run.update_summary()
        _refresh_submission_summary_for_run(run)

        logger.info(f"Variable {variable.column_name} validation completed: {results['error_count']} errors, {results['warning_count']} warnings")

        return {
            'validation_variable_id': validation_variable_id,
            'column_name': variable.column_name,
            'passed': results['passed'],
            'error_count': results['error_count'],
            'warning_count': results['warning_count']
        }

    except Exception as e:
        logger.error(f"Failed to validate variable {validation_variable_id}: {e}", exc_info=True)
        try:
            variable = ValidationVariable.objects.get(id=validation_variable_id)
            variable.mark_failed(str(e))
        except Exception as save_error:
            logger.error(f"Failed to mark variable as failed: {save_error}")
        raise


@shared_task(bind=True)
def run_validation_for_precheck(self, precheck_validation_id):
    """
    Run full validation for PrecheckValidation asynchronously.
    
    Creates ValidationRun and executes per-variable validation.
    Updates PrecheckValidation when complete.
    """
    import tempfile
    import duckdb
    import os
    from depot.models import PrecheckValidation
    from depot.storage.manager import StorageManager
    
    try:
        logger.info(f"Starting async validation for precheck {precheck_validation_id}")
        
        validation = PrecheckValidation.objects.get(id=precheck_validation_id)
        validation.update_status('validating', 'Running full validation', 90)
        
        # Load definition
        definition_obj = get_definition_for_type(validation.data_file_type.name)
        definition_list = definition_obj.get_definition()
        
        # Create ValidationRun
        content_type = ContentType.objects.get_for_model(validation)
        validation_run = ValidationRun.objects.create(
            content_type=content_type,
            object_id=validation.id,
            data_file_type=validation.data_file_type,
            duckdb_path=None,
            raw_file_path=validation.file_path,
            status='pending'
        )
        
        logger.info(f'Created ValidationRun {validation_run.id}')
        
        # Get file content and create temp DuckDB
        storage = StorageManager.get_scratch_storage()
        file_bytes = storage.get_file(validation.file_path)
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.csv', delete=False) as temp_csv:
            temp_csv.write(file_bytes)
            temp_csv_path = temp_csv.name

        try:
            # Apply data processing (cohort-specific transformations: column renames, value remaps, etc.)
            from depot.services.data_mapping import DataMappingService

            cohort_name = validation.cohort.name if validation.cohort else 'Unknown'

            processing_service = DataMappingService(
                cohort_name=cohort_name,
                data_file_type=validation.data_file_type.name
            )

            # Create temporary processed CSV file
            processed_csv_path = tempfile.mktemp(suffix='.csv')

            logger.info(f'Applying data processing for cohort: {cohort_name}')
            processing_results = processing_service.process_file(temp_csv_path, processed_csv_path)

            if processing_results.get('errors'):
                error_msg = f"Data processing failed: {processing_results['errors']}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Save processing metadata for UI display (matches phi_manager.py structure)
            validation_run.processing_metadata = {
                'mapping': processing_service.get_mapping_info(),
                'summary': processing_results,
                'row_count_in': processing_results.get('summary', {}).get('rows_processed', 0)
            }

            # Use processed CSV (not raw CSV) for DuckDB creation
            csv_for_duckdb = processed_csv_path

            # Create temp DuckDB file
            temp_db_fd, temp_db_path = tempfile.mkstemp(suffix='.duckdb')
            os.close(temp_db_fd)

            if os.path.exists(temp_db_path):
                os.unlink(temp_db_path)

            conn = duckdb.connect(temp_db_path)
            conn.execute("""
                CREATE TABLE data AS
                SELECT * FROM read_csv_auto(?, header=true, ignore_errors=false)
            """, [csv_for_duckdb])
            conn.close()

            validation_run.duckdb_path = temp_db_path
            validation_run.status = 'running'
            validation_run.save(update_fields=['duckdb_path', 'status', 'processing_metadata'])
            
            # Create ValidationVariable records
            variables = []
            for var_def in definition_list:
                variable = ValidationVariable.objects.create(
                    validation_run=validation_run,
                    column_name=var_def['name'],
                    column_type=var_def.get('type', 'string'),
                    display_name=var_def.get('label', var_def['name']),
                    status='pending'
                )
                variables.append(variable)
            
            logger.info(f'Created {len(variables)} validation variables')
            
            # Execute validation for each variable
            for variable in variables:
                execute_variable_validation.delay(variable.id, definition_list)
            
            # Store reference to validation run
            validation.validation_run = validation_run
            validation.save(update_fields=['validation_run', 'updated_at'])

            logger.info(f'Validation queued for {len(variables)} variables')
            validation.update_status('validating', 'Validation running...', 95)

            # Clean up scratch file after validation is queued
            validation.cleanup_scratch_file()

        finally:
            if os.path.exists(temp_csv_path):
                os.unlink(temp_csv_path)

            # Clean up processed CSV
            if 'processed_csv_path' in locals() and os.path.exists(processed_csv_path):
                os.unlink(processed_csv_path)

    except Exception as e:
        logger.error(f'Failed to run validation for precheck {precheck_validation_id}: {e}', exc_info=True)
        try:
            validation = PrecheckValidation.objects.get(id=precheck_validation_id)
            validation.error_message = str(e)
            error_summary = str(e)[:90] + '...' if len(str(e)) > 90 else str(e)
            validation.update_status('failed', f'Validation error: {error_summary}', 0)
            # Clean up scratch file on error too
            validation.cleanup_scratch_file()
        except Exception as save_error:
            logger.error(f'Failed to update validation status: {save_error}')
        raise
