"""
Upload routing service to handle secure PHI uploads.

In production, this will route uploads to a secure endpoint
that runs on a different server with direct NAS access.
"""
import logging
import requests
from django.conf import settings
from typing import BinaryIO, Dict, Any
import json

logger = logging.getLogger(__name__)


class UploadRouter:
    """
    Routes file uploads to appropriate endpoints based on configuration.
    
    In development: Handles uploads locally
    In production: Routes to secure upload server
    """
    
    @classmethod
    def get_upload_endpoint(cls) -> str:
        """
        Get the appropriate upload endpoint based on environment.
        
        Returns:
            URL of the upload endpoint
        """
        if hasattr(settings, 'SECURE_UPLOAD_ENDPOINT'):
            # Production: Use secure upload server
            return settings.SECURE_UPLOAD_ENDPOINT
        else:
            # Development: Use local endpoint
            return 'local'
    
    @classmethod
    def upload_file(cls, file_content: BinaryIO, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a file through the appropriate channel.
        
        Args:
            file_content: File content to upload
            metadata: Metadata about the file (submission_id, file_type, etc.)
            
        Returns:
            Response from the upload process
        """
        endpoint = cls.get_upload_endpoint()
        
        if endpoint == 'local':
            # Development mode: Process locally
            return cls._handle_local_upload(file_content, metadata)
        else:
            # Production mode: Stream to secure server
            return cls._stream_to_secure_server(endpoint, file_content, metadata)
    
    @classmethod
    def _handle_local_upload(cls, file_content: BinaryIO, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle upload locally (development mode).
        
        This simulates what the secure server would do:
        1. Save to NAS
        2. Queue processing tasks
        3. Return upload confirmation
        """
        from depot.storage.phi_manager import PHIStorageManager
        from depot.tasks import process_precheck_run
        from depot.tasks.patient_extraction import extract_patient_ids_task
        
        try:
            # Initialize PHI manager
            phi_manager = PHIStorageManager()
            
            # Store file on NAS (simulated in dev)
            nas_path, file_hash = phi_manager.store_raw_file(
                file_content=file_content,
                submission=metadata['submission'],
                file_type=metadata['file_type'],
                filename=metadata['filename'],
                user=metadata['user']
            )
            
            # Queue processing tasks
            if metadata.get('trigger_audit'):
                process_precheck_run.delay(metadata['audit_id'])
            
            if metadata.get('is_patient_file'):
                extract_patient_ids_task.delay(
                    metadata['data_file_id'],
                    metadata['user'].id
                )
            
            return {
                'success': True,
                'nas_path': nas_path,
                'file_hash': file_hash,
                'message': 'File uploaded successfully'
            }
            
        except Exception as e:
            logger.error(f"Local upload failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @classmethod
    def _stream_to_secure_server(cls, endpoint: str, file_content: BinaryIO, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stream file to secure upload server (production mode).
        
        The secure server:
        1. Has direct NAS mount
        2. Never exposes PHI to web
        3. Handles all PHI processing
        """
        try:
            # Prepare multipart upload
            files = {
                'file': (metadata['filename'], file_content, metadata.get('content_type', 'application/octet-stream'))
            }
            
            # Prepare metadata (excluding objects that can't be serialized)
            upload_metadata = {
                'submission_id': metadata['submission'].id,
                'cohort_id': metadata['submission'].cohort.id,
                'protocol_year': metadata['submission'].protocol_year.year,
                'file_type': metadata['file_type'],
                'user_id': metadata['user'].id,
                'is_patient_file': metadata.get('is_patient_file', False),
                'audit_id': metadata.get('audit_id'),
                'data_file_id': metadata.get('data_file_id'),
            }
            
            # Add authentication token
            headers = {
                'Authorization': f'Bearer {cls._get_secure_token()}',
                'X-Request-ID': metadata.get('request_id', '')
            }
            
            # Stream to secure server
            response = requests.post(
                endpoint,
                files=files,
                data={'metadata': json.dumps(upload_metadata)},
                headers=headers,
                timeout=300,  # 5 minute timeout for large files
                stream=True
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                logger.error(f"Secure upload failed with status {response.status_code}")
                return {
                    'success': False,
                    'error': f'Upload failed with status {response.status_code}'
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stream to secure server: {e}")
            return {
                'success': False,
                'error': 'Failed to connect to secure upload server'
            }
        except Exception as e:
            logger.error(f"Unexpected error streaming to secure server: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @classmethod
    def _get_secure_token(cls) -> str:
        """
        Get authentication token for secure server communication.
        
        In production, this would use proper service-to-service auth
        (OAuth2, JWT, mutual TLS, etc.)
        """
        return getattr(settings, 'SECURE_UPLOAD_TOKEN', 'dev-token')
    
    @classmethod
    def get_upload_status(cls, upload_id: str) -> Dict[str, Any]:
        """
        Check status of an upload on the secure server.
        
        Args:
            upload_id: ID of the upload to check
            
        Returns:
            Status information
        """
        endpoint = cls.get_upload_endpoint()
        
        if endpoint == 'local':
            # Development: Check local status
            # This would check Celery task status
            return {'status': 'completed', 'upload_id': upload_id}
        else:
            # Production: Query secure server
            try:
                response = requests.get(
                    f"{endpoint}/status/{upload_id}",
                    headers={'Authorization': f'Bearer {cls._get_secure_token()}'},
                    timeout=10
                )
                return response.json()
            except Exception as e:
                logger.error(f"Failed to check upload status: {e}")
                return {'status': 'unknown', 'error': str(e)}