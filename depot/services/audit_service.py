"""
AuditService - Service layer for audit processing and management
"""
from django.conf import settings
from depot.models import PrecheckRun
from depot.tasks import process_precheck_run


class AuditService:
    """Service for managing audit operations."""
    
    @staticmethod
    def create_audit(submission, data_table_file, uploaded_file_record, user):
        """Create a new audit record for a data table file."""
        audit = PrecheckRun.objects.create(
            cohort=submission.cohort,
            uploaded_file=uploaded_file_record,
            data_file_type=data_table_file.data_table.data_file_type,
            uploaded_by=user,
            created_by=user,  # Required for notebook creation
            original_filename=uploaded_file_record.filename,
            file_size=uploaded_file_record.size if hasattr(uploaded_file_record, 'size') else None,
            status='pending'
        )
        
        # Note: PrecheckRun is standalone - not linked to data table files
        
        return audit
    
    @staticmethod
    def trigger_processing(audit_id):
        """Trigger async processing for an audit."""
        return AuditService.handle_async_sync_task(
            async_func=process_precheck_run.delay,
            sync_func=process_precheck_run,
            task_args=(audit_id,),
            task_name="audit processing",
            object_id=audit_id
        )
    
    @staticmethod
    def check_status(audit_id):
        """Check the status of an audit."""
        try:
            audit = PrecheckRun.objects.get(id=audit_id)
            return audit.status
        except PrecheckRun.DoesNotExist:
            return None
    
    @staticmethod
    def mark_failed(audit_id, error_message):
        """Mark an audit as failed."""
        try:
            audit = PrecheckRun.objects.get(id=audit_id)
            audit.mark_failed(error_message)
        except PrecheckRun.DoesNotExist:
            pass
    
    @staticmethod
    def handle_async_sync_task(async_func, sync_func, task_args, task_name, object_id):
        """
        Generic handler for async/sync task execution.
        Tries async first, falls back to sync in debug mode, re-raises in production.
        """
        try:
            # Try async first
            async_func(*task_args)
            return True
        except Exception as e:
            if settings.DEBUG:
                # In debug mode, fall back to synchronous execution
                try:
                    sync_func(*task_args)
                    return True
                except Exception:
                    # If sync also fails, re-raise the original async error
                    raise e
            else:
                # In production, re-raise the exception
                raise e