"""
Refactored secure upload endpoint using service layer pattern.

This endpoint:
1. Runs on a separate server from the main web app
2. Has direct NAS mount access
3. Never exposes PHI to the web tier
4. All processing happens via Celery on secure workers
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from functools import wraps

from depot.services.file_upload_service import FileUploadService
from depot.services.audit_service import AuditService
from depot.services.patient_id_service import PatientIDService
from depot.storage.phi_manager import PHIStorageManager

logger = logging.getLogger(__name__)


def require_secure_token(view_func):
    """Decorator to require valid secure token for inter-service communication."""
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


class SecureUploadService:
    """Service for handling secure file uploads on isolated server."""
    
    def __init__(self):
        self.file_service = FileUploadService()
        self.phi_manager = PHIStorageManager()
        
    def validate_metadata(self, metadata):
        """Validate required metadata fields."""
        required_fields = ['submission_id', 'cohort_id', 'file_type', 'user_id']
        missing = [field for field in required_fields if field not in metadata]
        
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        
        return True
    
    def process_secure_upload(self, uploaded_file, metadata):
        """
        Process secure file upload with PHI protection.
        
        Returns:
            dict: Upload results without PHI
        """
        # Validate metadata
        self.validate_metadata(metadata)
        
        # Calculate file hash
        file_hash = self.file_service.calculate_file_hash(uploaded_file)
        
        # Store file securely on NAS
        storage_path = self.phi_manager.store_secure_file(
            file_content=uploaded_file,
            cohort_id=metadata['cohort_id'],
            protocol_year=metadata.get('protocol_year', ''),
            file_type=metadata['file_type'],
            filename=uploaded_file.name,
            file_hash=file_hash
        )
        
        # Log operation (no PHI)
        logger.info(
            f"Secure upload completed - "
            f"submission: {metadata['submission_id']}, "
            f"type: {metadata['file_type']}, "
            f"size: {uploaded_file.size} bytes"
        )
        
        # Queue processing tasks
        task_ids = self.queue_processing_tasks(metadata)
        
        return {
            'upload_id': f"{metadata['submission_id']}_{uploaded_file.name}",
            'tasks': task_ids,
            'file_hash': file_hash,
            'storage_path': storage_path  # Internal use only, not returned to client
        }
    
    def queue_processing_tasks(self, metadata):
        """Queue appropriate processing tasks based on metadata."""
        task_ids = []
        
        # Queue audit if requested
        if metadata.get('audit_id'):
            success = AuditService.trigger_processing(metadata['audit_id'])
            if success:
                task_ids.append(('audit', metadata['audit_id']))
        
        # Queue patient ID extraction if patient file
        if metadata.get('is_patient_file') and metadata.get('data_file_id'):
            # Use PatientIDService for patient file processing
            from depot.models import DataTableFile
            try:
                data_file = DataTableFile.objects.get(id=metadata['data_file_id'])
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=metadata['user_id'])
                
                result = PatientIDService.process_patient_file(data_file, user)
                if result:
                    task_ids.append(('patient_extraction', 'synchronous'))
                else:
                    task_ids.append(('patient_extraction', 'queued'))
            except Exception as e:
                logger.error(f"Failed to queue patient extraction: {e}")
        
        return task_ids


@csrf_exempt
@require_http_methods(["POST"])
@require_secure_token
def secure_upload_handler(request):
    """
    Handle secure file uploads on isolated server.
    
    Refactored to use service layer for better separation of concerns.
    """
    try:
        # Parse metadata
        metadata = json.loads(request.POST.get('metadata', '{}'))
        uploaded_file = request.FILES.get('file')
        
        if not uploaded_file:
            return JsonResponse({'error': 'No file provided'}, status=400)
        
        # Use service for processing
        upload_service = SecureUploadService()
        result = upload_service.process_secure_upload(uploaded_file, metadata)
        
        # Return success (no PHI in response)
        return JsonResponse({
            'success': True,
            'upload_id': result['upload_id'],
            'tasks': result['tasks'],
            'message': 'File uploaded and processing queued'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid metadata format'}, status=400)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Secure upload failed: {e}", exc_info=True)
        return JsonResponse({'error': 'Upload failed'}, status=500)


@require_http_methods(["GET"])
@require_secure_token
def secure_upload_status(request, upload_id):
    """
    Check status of an upload (without exposing PHI).
    
    Returns only status information, no actual data.
    """
    try:
        # Parse upload_id
        parts = upload_id.split('_', 1)
        if len(parts) != 2:
            return JsonResponse({'error': 'Invalid upload ID'}, status=400)
        
        submission_id, filename = parts
        
        # Use PHIStorageManager to check status without exposing data
        phi_manager = PHIStorageManager()
        exists = phi_manager.check_file_exists(submission_id, filename)
        
        return JsonResponse({
            'upload_id': upload_id,
            'status': 'completed' if exists else 'not_found',
            'exists': exists,
            # No PHI in response
        })
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return JsonResponse({'error': 'Status check failed'}, status=500)


@require_http_methods(["DELETE"])
@require_secure_token
def secure_upload_delete(request, upload_id):
    """
    Mark a secure upload for deletion (soft delete only).
    
    Actual deletion happens via scheduled cleanup tasks.
    """
    try:
        # Parse upload_id
        parts = upload_id.split('_', 1)
        if len(parts) != 2:
            return JsonResponse({'error': 'Invalid upload ID'}, status=400)
        
        submission_id, filename = parts
        
        # Use PHIStorageManager for secure deletion
        phi_manager = PHIStorageManager()
        success = phi_manager.mark_for_deletion(submission_id, filename)
        
        if success:
            logger.info(f"Marked for deletion: {upload_id}")
            return JsonResponse({
                'success': True,
                'message': 'File marked for deletion'
            })
        else:
            return JsonResponse({
                'error': 'File not found or already deleted'
            }, status=404)
            
    except Exception as e:
        logger.error(f"Deletion failed: {e}")
        return JsonResponse({'error': 'Deletion failed'}, status=500)