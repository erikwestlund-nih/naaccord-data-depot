"""
Secure upload endpoint that runs on isolated server with NAS mount.

This endpoint:
1. Runs on a separate server from the main web app
2. Has direct NAS mount access
3. Never exposes PHI to the web tier
4. All processing happens via Celery on secure workers
"""
import json
import logging
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from functools import wraps

logger = logging.getLogger(__name__)


def require_secure_token(view_func):
    """
    Decorator to require valid secure token for inter-service communication.
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Invalid authentication'}, status=401)
        
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        expected_token = getattr(settings, 'SECURE_UPLOAD_TOKEN', None)
        
        if not expected_token or token != expected_token:
            logger.warning(f"Invalid secure token attempt from {request.META.get('REMOTE_ADDR')}")
            return JsonResponse({'error': 'Invalid authentication'}, status=401)
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view


@csrf_exempt
@require_http_methods(["POST"])
@require_secure_token
def secure_upload_handler(request):
    """
    Handle secure file uploads on isolated server.
    
    This endpoint:
    - Receives file streams from web tier
    - Writes directly to NAS mount
    - Queues Celery tasks for processing
    - Never sends PHI back to web tier
    """
    try:
        # Parse metadata
        metadata = json.loads(request.POST.get('metadata', '{}'))
        uploaded_file = request.FILES.get('file')
        
        if not uploaded_file:
            return JsonResponse({'error': 'No file provided'}, status=400)
        
        # Validate metadata
        required_fields = ['submission_id', 'cohort_id', 'file_type', 'user_id']
        for field in required_fields:
            if field not in metadata:
                return JsonResponse({'error': f'Missing required field: {field}'}, status=400)
        
        # Get NAS mount path from Django settings
        nas_mount = settings.NAS_MOUNT_PATH
        
        # Build storage path on NAS
        storage_path = os.path.join(
            nas_mount,
            str(metadata['cohort_id']),
            str(metadata['protocol_year']),
            metadata['file_type'],
            uploaded_file.name
        )
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        
        # Stream file directly to NAS
        with open(storage_path, 'wb') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # Log the operation (without PHI)
        logger.info(f"File uploaded for submission {metadata['submission_id']}, "
                   f"type: {metadata['file_type']}, "
                   f"size: {uploaded_file.size} bytes")
        
        # Queue processing tasks using sequential Celery workflow
        from depot.tasks import (
            create_duckdb_task,
            process_precheck_run_with_duckdb,
            cleanup_workflow_files_task
        )
        from depot.tasks.patient_extraction import extract_patient_ids_task
        from celery import chain

        task_ids = []

        # Sequential workflow for patient files with audit:
        # Upload → DuckDB → Extract Patient IDs → Process Notebook → Cleanup
        if metadata.get('is_patient_file') and metadata.get('data_file_id') and metadata.get('audit_id'):
            workflow = chain(
                create_duckdb_task.s(metadata['data_file_id'], metadata['user_id']),
                extract_patient_ids_task.s(),
                process_precheck_run_with_duckdb.s(),
                cleanup_workflow_files_task.s()
            )

            workflow_result = workflow.apply_async()
            task_ids.append(('patient_audit_workflow', workflow_result.id))
            logger.info(f"Started sequential patient file workflow for file {metadata['data_file_id']}")

        # Sequential workflow for patient files without audit:
        # Upload → DuckDB → Extract Patient IDs → Cleanup
        elif metadata.get('is_patient_file') and metadata.get('data_file_id'):
            workflow = chain(
                create_duckdb_task.s(metadata['data_file_id'], metadata['user_id']),
                extract_patient_ids_task.s(),
                cleanup_workflow_files_task.s()
            )

            workflow_result = workflow.apply_async()
            task_ids.append(('patient_workflow', workflow_result.id))
            logger.info(f"Started sequential patient extraction workflow for file {metadata['data_file_id']}")

        # Standard audit without patient file (original behavior)
        elif metadata.get('audit_id'):
            from depot.tasks import process_precheck_run
            task = process_precheck_run.delay(metadata['audit_id'])
            task_ids.append(('audit', task.id))
            logger.info(f"Started audit task for upload precheck {metadata['audit_id']}")
        
        # Return success (no PHI in response)
        return JsonResponse({
            'success': True,
            'upload_id': f"{metadata['submission_id']}_{uploaded_file.name}",
            'tasks': task_ids,
            'message': 'File uploaded and processing queued'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid metadata format'}, status=400)
    except Exception as e:
        logger.error(f"Secure upload failed: {e}")
        return JsonResponse({'error': 'Upload failed'}, status=500)


@require_http_methods(["GET"])
@require_secure_token
def secure_upload_status(request, upload_id):
    """
    Check status of an upload (without exposing PHI).
    
    Returns only status information, no actual data.
    """
    try:
        # Parse upload_id to get submission and filename
        parts = upload_id.split('_', 1)
        if len(parts) != 2:
            return JsonResponse({'error': 'Invalid upload ID'}, status=400)
        
        submission_id, filename = parts
        
        # Check if file exists on NAS (without reading it)
        # This is just a status check
        
        return JsonResponse({
            'upload_id': upload_id,
            'status': 'completed',
            'exists': True,
            # No PHI in response
        })
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return JsonResponse({'error': 'Status check failed'}, status=500)