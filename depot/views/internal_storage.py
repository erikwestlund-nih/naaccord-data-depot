"""
Internal Storage API for Services Server.
Handles file operations from the web server via HTTP.
Only accessible via internal API key authentication.
"""
import os
import json
import logging
import tempfile
import uuid
from pathlib import Path
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from functools import wraps
from typing import Dict, Any

from depot.storage.manager import StorageManager
from depot.models import PHIFileTracking

logger = logging.getLogger(__name__)


def require_internal_api_key(view_func):
    """
    Decorator to require internal API key for authentication.
    This ensures only the web server can access these endpoints.
    """
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        # Get API key from header
        api_key = request.headers.get('X-API-Key')

        # Get expected key from secret file or environment variable
        expected_key = None
        api_key_file = os.environ.get('INTERNAL_API_KEY_FILE')

        if api_key_file and os.path.exists(api_key_file):
            # Read from Docker secret file
            try:
                with open(api_key_file, 'r') as f:
                    expected_key = f.read().strip()
            except Exception as e:
                logger.error(f"Failed to read INTERNAL_API_KEY from {api_key_file}: {e}")
        else:
            # Fall back to environment variable (for testing/development)
            expected_key = os.environ.get('INTERNAL_API_KEY')

        if not expected_key:
            logger.error("INTERNAL_API_KEY not configured (checked file and environment)")
            raise PermissionDenied("Internal API not configured")
        
        if not api_key or api_key != expected_key:
            # Mask IP address for privacy
            ip = request.META.get('REMOTE_ADDR', 'unknown')
            if ip != 'unknown' and '.' in ip:
                parts = ip.split('.')
                if len(parts) == 4:
                    ip = f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
            logger.warning(f"Invalid API key attempt from {ip}")
            raise PermissionDenied("Invalid API key")
        
        return view_func(request, *args, **kwargs)
    
    return wrapped_view


@csrf_exempt
@require_http_methods(["POST"])
@require_internal_api_key
def storage_upload(request):
    """
    Handle file upload from web server.
    Optimized to handle Django's TemporaryUploadedFile efficiently.
    """
    try:
        # Get parameters
        path = request.POST.get('path')
        content_type = request.POST.get('content_type', 'application/octet-stream')
        metadata_json = request.POST.get('metadata')

        if not path:
            return JsonResponse({'error': 'Path is required'}, status=400)

        # Parse metadata if provided
        metadata = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError:
                logger.warning(f"Invalid metadata JSON: {metadata_json}")

        # Get file from request
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return JsonResponse({'error': 'No file provided'}, status=400)

        # Get storage backend
        # Use disk parameter if provided, otherwise determine based on path prefix
        disk_name = request.POST.get('disk')

        if disk_name:
            # Use explicitly specified disk
            storage = StorageManager.get_storage(disk_name)
            logger.info(f"Using disk '{disk_name}' from request parameter")
        elif path.startswith('precheck_runs/'):
            storage = StorageManager.get_storage('uploads')
        elif path.startswith('data/'):
            storage = StorageManager.get_storage('data')
        elif path.startswith('downloads/'):
            storage = StorageManager.get_storage('downloads')
        elif '/attachment' in path or 'attachment/' in path:
            # Attachment paths (table attachments or submission attachments)
            storage = StorageManager.get_storage('attachments')
            logger.info(f"Using attachments disk for path: {path}")
        else:
            # Default to uploads for any other path
            storage = StorageManager.get_storage('uploads')

        # Optimize for Django's TemporaryUploadedFile (files > 2.5MB)
        if hasattr(uploaded_file, 'temporary_file_path'):
            # File is already on disk - stream from disk file
            logger.info(f"Streaming TemporaryUploadedFile ({uploaded_file.size} bytes) from disk")
            temp_path = uploaded_file.temporary_file_path()

            # Open and stream the temp file
            with open(temp_path, 'rb') as temp_file:
                saved_path = storage.save(path, temp_file, content_type=content_type, metadata=metadata)
        else:
            # Small file in memory - save directly
            logger.info(f"Saving InMemoryUploadedFile ({uploaded_file.size} bytes)")
            saved_path = storage.save(path, uploaded_file, content_type=content_type, metadata=metadata)
        
        # Create PHI tracking with actual filesystem path
        # This replaces the web-side tracking which has a remote:// pseudo-path
        if 'cohort_id' in metadata:
            try:
                # Get absolute path for this file
                absolute_path = storage.get_absolute_path(saved_path)

                PHIFileTracking.objects.create(
                    cohort_id=metadata['cohort_id'],
                    user_id=metadata.get('user_id'),
                    action='file_uploaded_via_stream',
                    file_path=absolute_path,  # Actual filesystem path for cleanup
                    file_type=metadata.get('file_type', 'raw_csv'),
                    file_size=uploaded_file.size,
                    file_hash=metadata.get('file_hash', ''),
                    object_id=metadata.get('content_object_id'),  # Fixed: object_id not content_object_id
                    content_type_id=metadata.get('content_type_id'),
                    cleanup_required=True,
                    expected_cleanup_by=metadata.get('expected_cleanup_by'),
                    server_role='services',
                    bytes_transferred=uploaded_file.size,
                    metadata={'relative_path': saved_path, 'original_filename': metadata.get('original_filename')}
                )
                logger.info(f"PHI tracking created: {absolute_path} (size={uploaded_file.size})")
            except Exception as e:
                logger.error(f"Failed to track file upload: {e}", exc_info=True)
        
        logger.info(f"Successfully saved streamed file: {saved_path} ({uploaded_file.size} bytes)")
        
        return JsonResponse({
            'success': True,
            'path': saved_path,
            'size': uploaded_file.size
        })
        
    except Exception as e:
        logger.error(f"Error in storage_upload: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@require_internal_api_key
def storage_upload_chunked(request):
    """
    Handle chunked file upload for very large files.
    Supports init, chunk, and complete actions.
    """
    try:
        action = request.POST.get('action')
        
        if action == 'init':
            # Initialize chunked upload
            path = request.POST.get('path')
            content_type = request.POST.get('content_type', 'application/octet-stream')
            metadata_json = request.POST.get('metadata')
            
            if not path:
                return JsonResponse({'error': 'Path is required'}, status=400)
            
            # Create temporary file for accumulating chunks
            # Use a unique ID that we can reconstruct later
            # Use /var/tmp instead of /tmp (tmpfs) for large files
            upload_id = str(uuid.uuid4())
            temp_dir = os.path.join('/var/tmp', f'chunked_upload_{upload_id}')
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, 'upload.tmp')
            
            # Store upload metadata
            meta_file = os.path.join(temp_dir, 'metadata.json')
            with open(meta_file, 'w') as f:
                json.dump({
                    'path': path,
                    'content_type': content_type,
                    'metadata': json.loads(metadata_json) if metadata_json else {}
                }, f)
            
            logger.info(f"Initialized chunked upload {upload_id} for {path}")
            
            return JsonResponse({
                'success': True,
                'upload_id': upload_id
            })
            
        elif action == 'chunk':
            # Receive a chunk
            upload_id = request.POST.get('upload_id')
            chunk_num = int(request.POST.get('chunk_num', 0))

            if not upload_id:
                return JsonResponse({'error': 'Upload ID required'}, status=400)

            # Get chunk file
            chunk_file = request.FILES.get('chunk')
            if not chunk_file:
                return JsonResponse({'error': 'No chunk provided'}, status=400)

            # Append to temporary file
            # Use /var/tmp instead of /tmp (tmpfs) for large files
            temp_dir = os.path.join('/var/tmp', f'chunked_upload_{upload_id}')
            # Ensure directory exists (in case init failed or was cleaned up)
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, 'upload.tmp')

            # Create temp file if it doesn't exist yet (first chunk)
            if not os.path.exists(temp_file):
                open(temp_file, 'wb').close()

            with open(temp_file, 'ab') as f:
                for chunk_data in chunk_file.chunks():
                    f.write(chunk_data)
            
            logger.debug(f"Received chunk {chunk_num} for upload {upload_id}")
            
            return JsonResponse({
                'success': True,
                'chunk_num': chunk_num
            })
            
        elif action == 'complete':
            # Complete the upload
            upload_id = request.POST.get('upload_id')
            total_chunks = int(request.POST.get('total_chunks', 0))
            
            if not upload_id:
                return JsonResponse({'error': 'Upload ID required'}, status=400)

            # Use /var/tmp instead of /tmp (tmpfs) for large files
            temp_dir = os.path.join('/var/tmp', f'chunked_upload_{upload_id}')
            temp_file = os.path.join(temp_dir, 'upload.tmp')
            meta_file = os.path.join(temp_dir, 'metadata.json')
            
            # Load metadata
            with open(meta_file, 'r') as f:
                upload_meta = json.load(f)
            
            # Get storage backend
            storage = StorageManager.get_storage('uploads')
            
            # Save complete file to storage
            with open(temp_file, 'rb') as f:
                saved_path = storage.save(
                    upload_meta['path'],
                    f.read(),
                    content_type=upload_meta['content_type'],
                    metadata=upload_meta['metadata']
                )
            
            # Get file size for tracking
            file_size = os.path.getsize(temp_file)
            
            # Track if PHI
            if 'cohort_id' in upload_meta['metadata']:
                try:
                    PHIFileTracking.objects.create(
                        cohort_id=upload_meta['metadata']['cohort_id'],
                        user_id=upload_meta['metadata'].get('user_id'),
                        action='file_uploaded_chunked',
                        file_path=saved_path,
                        file_type=upload_meta['metadata'].get('file_type', 'unknown'),
                        server_role='services',
                        bytes_transferred=file_size
                    )
                except Exception as e:
                    logger.error(f"Failed to track chunked upload: {e}")
            
            # Clean up temporary files
            try:
                os.unlink(temp_file)
                os.unlink(meta_file)
                os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp files for {upload_id}: {e}")
            
            logger.info(f"Completed chunked upload {upload_id}: {saved_path} ({file_size} bytes, {total_chunks} chunks)")
            
            return JsonResponse({
                'success': True,
                'path': saved_path,
                'size': file_size,
                'chunks': total_chunks
            })
            
        else:
            return JsonResponse({'error': f'Invalid action: {action}'}, status=400)
            
    except Exception as e:
        logger.error(f"Error in storage_upload_chunked: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@require_internal_api_key
def storage_download(request):
    """
    Stream file from storage to web server.
    """
    try:
        path = request.GET.get('path')
        disk = request.GET.get('disk', 'local')  # Default to 'local' disk

        if not path:
            return JsonResponse({'error': 'Path is required'}, status=400)

        # Get storage backend for the specified disk
        storage = StorageManager.get_storage(disk)
        
        # Check if file exists
        if not storage.exists(path):
            return JsonResponse({'error': 'File not found'}, status=404)
        
        # Get file metadata for content type
        metadata = storage.get_metadata(path)
        content_type = 'application/octet-stream'
        if metadata and 'content_type' in metadata:
            content_type = metadata['content_type']
        
        # Stream file content
        def file_iterator():
            """Generator to stream file in chunks."""
            content = storage.get_file(path)
            if content:
                # Stream in 64KB chunks
                chunk_size = 64 * 1024
                for i in range(0, len(content), chunk_size):
                    yield content[i:i + chunk_size]
        
        response = StreamingHttpResponse(
            file_iterator(),
            content_type=content_type
        )
        
        # Add content disposition header
        filename = os.path.basename(path)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Track download if we have metadata
        if metadata and 'cohort_id' in metadata:
            try:
                PHIFileTracking.objects.create(
                    cohort_id=metadata['cohort_id'],
                    user_id=metadata.get('user_id'),
                    action='file_downloaded_via_stream',
                    file_path=path,
                    file_type=metadata.get('file_type', 'unknown'),
                    server_role='services'
                )
            except Exception as e:
                logger.error(f"Failed to track file download: {e}")
        
        logger.info(f"Streaming file to web server: {path}")
        return response
        
    except Exception as e:
        logger.error(f"Error in storage_download: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@require_internal_api_key
def storage_delete(request):
    """
    Delete file from storage.
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        path = data.get('path')
        disk_name = data.get('disk', 'scratch')  # Default to scratch for precheck cleanup

        if not path:
            return JsonResponse({'error': 'Path is required'}, status=400)

        # Get storage backend
        storage = StorageManager.get_storage(disk_name)

        # Get absolute path for PHI tracking
        absolute_path = storage.get_absolute_path(path)

        # Delete file
        success = storage.delete(path)

        if success:
            # Track deletion
            try:
                PHIFileTracking.objects.create(
                    action='file_deleted_via_api',
                    file_path=absolute_path,
                    server_role='services',
                    metadata={'relative_path': path}
                )
            except Exception as e:
                logger.error(f"Failed to track file deletion: {e}")

            logger.info(f"Deleted file via API: {path}")
        else:
            logger.warning(f"Failed to delete file: {path}")
        
        return JsonResponse({
            'success': success,
            'path': path
        })
        
    except Exception as e:
        logger.error(f"Error in storage_delete: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@require_internal_api_key
def storage_delete_prefix(request):
    """
    Delete all files with given prefix.
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        prefix = data.get('prefix')
        
        if not prefix:
            return JsonResponse({'error': 'Prefix is required'}, status=400)
        
        # Get storage backend
        storage = StorageManager.get_storage('uploads')
        
        # Delete all files with prefix
        deleted_count = storage.delete_prefix(prefix)
        
        # Track bulk deletion
        try:
            PHIFileTracking.objects.create(
                action='prefix_deleted_via_api',
                file_path=prefix,
                server_role='services',
                metadata={'deleted_count': deleted_count}
            )
        except Exception as e:
            logger.error(f"Failed to track prefix deletion: {e}")
        
        logger.info(f"Deleted {deleted_count} files with prefix: {prefix}")
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'prefix': prefix
        })
        
    except Exception as e:
        logger.error(f"Error in storage_delete_prefix: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@require_internal_api_key
def storage_list(request):
    """
    List files with given prefix.
    """
    try:
        prefix = request.GET.get('prefix', '')
        include_metadata = request.GET.get('include_metadata', 'false').lower() == 'true'
        
        # Get storage backend
        storage = StorageManager.get_storage('uploads')
        
        # List files
        files = storage.list_with_prefix(prefix, include_metadata=include_metadata)
        
        # Format response
        if include_metadata:
            # Convert tuples to dicts for JSON
            formatted_files = [
                {
                    'path': path,
                    'mtime': mtime,
                    'size': size
                }
                for path, mtime, size in files
            ]
        else:
            formatted_files = files
        
        return JsonResponse({
            'success': True,
            'files': formatted_files,
            'count': len(files),
            'prefix': prefix
        })
        
    except Exception as e:
        logger.error(f"Error in storage_list: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@require_internal_api_key
def storage_exists(request):
    """
    Check if file exists.
    """
    try:
        path = request.GET.get('path')
        disk = request.GET.get('disk', 'local')  # Default to 'local' disk

        if not path:
            return JsonResponse({'error': 'Path is required'}, status=400)

        # Get storage backend for the specified disk
        storage = StorageManager.get_storage(disk)
        
        # Check existence
        exists = storage.exists(path)
        
        return JsonResponse({
            'success': True,
            'exists': exists,
            'path': path
        })
        
    except Exception as e:
        logger.error(f"Error in storage_exists: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@require_internal_api_key
def storage_metadata(request):
    """
    Get file metadata.
    """
    try:
        path = request.GET.get('path')
        
        if not path:
            return JsonResponse({'error': 'Path is required'}, status=400)
        
        # Get storage backend
        storage = StorageManager.get_storage('uploads')
        
        # Get metadata
        metadata = storage.get_metadata(path)
        
        if metadata is None:
            return JsonResponse({'error': 'File not found'}, status=404)
        
        return JsonResponse({
            'success': True,
            'path': path,
            'metadata': metadata
        })
        
    except Exception as e:
        logger.error(f"Error in storage_metadata: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@require_internal_api_key
def cleanup_scratch(request):
    """
    Trigger scratch cleanup on services server.
    Called by web server to coordinate cleanup.
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        hours = data.get('hours', 4)
        dry_run = data.get('dry_run', False)
        
        # Import workspace manager
        from depot.storage.scratch_manager import ScratchManager
        
        # Run cleanup
        scratch = ScratchManager()
        result = scratch.cleanup_orphaned_directories(hours=hours, dry_run=dry_run)
        
        logger.info(f"Scratch cleanup: found={result['found']}, cleaned={result['cleaned']}, failed={result['failed']}")
        
        return JsonResponse({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"Error in cleanup_scratch: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@require_internal_api_key
def storage_health(request):
    """
    Health check endpoint for storage API.
    """
    try:
        # Test storage backend
        storage = StorageManager.get_storage('uploads')
        
        # Try a simple operation
        test_key = "workspace/.health_check"
        storage.touch(test_key)
        exists = storage.exists(test_key)
        storage.delete(test_key)
        
        return JsonResponse({
            'status': 'healthy',
            'storage_backend': type(storage).__name__,
            'server_role': os.environ.get('SERVER_ROLE', 'unknown'),
            'test_passed': exists
        })
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=500)