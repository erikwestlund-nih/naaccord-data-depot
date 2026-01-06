from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404
from django.conf import settings
from pathlib import Path
import logging

from depot.models import Notebook, Activity, ActivityType
from depot.storage.manager import StorageManager
from depot.utils.activity_logging import log_access_denied

logger = logging.getLogger(__name__)


@login_required
def notebook_view(request, notebook_id):
    """Serve the compiled notebook HTML file."""
    # Get the notebook record
    notebook = get_object_or_404(Notebook, id=notebook_id)
    
    # Check if user has access to this notebook
    can_access = notebook.can_access(request.user)

    logger.info(f"Notebook access check for user_id {request.user.id}:")
    logger.info(f"  - Notebook ID: {notebook_id}")
    logger.info(f"  - Notebook cohort: {notebook.cohort.name if notebook.cohort else 'None'}")
    logger.info(f"  - User cohort count: {request.user.cohorts.count()}")
    logger.info(f"  - notebook.can_access(): {can_access}")
    logger.info(f"  - Will allow access: {can_access}")

    if not can_access:
        if getattr(settings, 'TESTING', False):
            logger.debug(f"Access denied: User ID {request.user.id} attempted to access notebook {notebook_id} from cohort {notebook.cohort.name}")
        else:
            logger.warning(f"Access denied: User ID {request.user.id} attempted to access notebook {notebook_id} from cohort {notebook.cohort.name}")
        log_access_denied(request, 'notebook', notebook_id, f"{notebook.name} ({notebook.cohort.name})")
        return render(request, 'errors/403.html', status=403)
    
    # Log successful report viewing access
    Activity.log_activity(
        user=request.user,
        activity_type=ActivityType.REPORT_VIEW,
        success=True,
        request=request,
        details={
            'notebook_id': notebook_id,
            'notebook_name': notebook.name,
            'cohort': notebook.cohort.name if notebook.cohort else None,
            'data_file_type': notebook.data_file_type.name if notebook.data_file_type else None
        }
    )

    # Check if the notebook has been compiled
    if notebook.status != 'completed' or not notebook.compiled_path:
        return HttpResponse(
            "<html><body><h1>Notebook Not Ready</h1><p>This notebook is still being compiled. Please check back later.</p></body></html>",
            content_type='text/html'
        )
    
    try:
        # Get the storage system for reports
        storage = StorageManager.get_storage('reports')

        # Use the compiled_path directly (already includes notebooks/ prefix)
        full_path = notebook.compiled_path

        # Check if the file exists in storage
        if not storage.exists(full_path):
            logger.error(f"Notebook file not found in storage: {full_path}")
            return HttpResponse(
                "<html><body><h1>Notebook Not Found</h1><p>The compiled notebook file could not be found.</p></body></html>",
                content_type='text/html',
                status=404
            )

        # Read the HTML content from storage
        # The RemoteStorageDriver will handle streaming internally if SERVER_ROLE=web
        try:
            html_content = storage.get_file(full_path)

            # If get_file returns bytes, decode it
            if isinstance(html_content, bytes):
                html_content = html_content.decode('utf-8')

            # Return the HTML content
            response = HttpResponse(html_content, content_type='text/html')

            # Set appropriate headers for inline display
            response['Content-Disposition'] = f'inline; filename="audit_report_{notebook.id}.html"'

            logger.info(f"Serving notebook {notebook_id} via storage driver: {type(storage).__name__}")
            return response

        except Exception as read_error:
            logger.error(f"Error reading notebook from storage: {read_error}")
            return HttpResponse(
                "<html><body><h1>Error Reading Notebook</h1><p>The notebook could not be read from storage.</p></body></html>",
                content_type='text/html',
                status=500
            )
        
    except Exception as e:
        logger.error(f"Error serving notebook {notebook_id}: {e}", exc_info=True)
        return HttpResponse(
            "<html><body><h1>Error</h1><p>An error occurred while loading the notebook.</p></body></html>",
            content_type='text/html',
            status=500
        )


@login_required
def notebook_download(request, notebook_id):
    """Download the compiled notebook HTML file."""
    # Get the notebook record
    notebook = get_object_or_404(Notebook, id=notebook_id)
    
    # Check if user has access to this notebook (same logic as view)
    can_access = notebook.can_access(request.user)

    logger.info(f"Notebook download request for user_id {request.user.id}:")
    logger.info(f"  - Notebook ID: {notebook_id}")
    logger.info(f"  - Notebook cohort: {notebook.cohort.name if notebook.cohort else 'None'}")
    logger.info(f"  - User cohorts: {[c.name for c in request.user.cohorts.all()]}")
    logger.info(f"  - notebook.can_access(): {can_access}")
    logger.info(f"  - Will allow download: {can_access}")

    if not can_access:
        logger.warning(f"Download denied: User ID {request.user.id} attempted to download notebook {notebook_id} from cohort {notebook.cohort.name}")
        log_access_denied(request, 'notebook_download', notebook_id, f"{notebook.name} ({notebook.cohort.name})")
        return render(request, 'errors/403.html', status=403)
    
    # Log successful report download access
    Activity.log_activity(
        user=request.user,
        activity_type=ActivityType.FILE_DOWNLOAD,
        success=True,
        request=request,
        details={
            'notebook_id': notebook_id,
            'notebook_name': notebook.name,
            'cohort': notebook.cohort.name if notebook.cohort else None,
            'data_file_type': notebook.data_file_type.name if notebook.data_file_type else None,
            'download_type': 'report'
        }
    )

    # Check if the notebook has been compiled
    if notebook.status != 'completed' or not notebook.compiled_path:
        return HttpResponse(
            "<html><body><h1>Notebook Not Ready</h1><p>This notebook is still being compiled. Please check back later.</p></body></html>",
            content_type='text/html',
            status=404
        )
    
    try:
        # Get the storage system for reports
        storage = StorageManager.get_storage('reports')

        # Use the compiled_path directly (already includes notebooks/ prefix)
        full_path = notebook.compiled_path

        # Check if the file exists in storage
        if not storage.exists(full_path):
            logger.error(f"Notebook file not found in storage for download: {full_path}")
            return HttpResponse(
                "<html><body><h1>Notebook Not Found</h1><p>The compiled notebook file could not be found.</p></body></html>",
                content_type='text/html',
                status=404
            )

        # Generate a descriptive filename
        safe_name = "".join(c for c in notebook.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_name}_report_{notebook.id}.html"

        # Read the HTML content from storage
        # The RemoteStorageDriver will handle streaming internally if SERVER_ROLE=web
        try:
            html_content = storage.get_file(full_path)

            # If get_file returns bytes, decode it
            if isinstance(html_content, bytes):
                html_content = html_content.decode('utf-8')

            # Return the HTML content for download
            response = HttpResponse(html_content, content_type='text/html')

            # Set download headers
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            return response

        except Exception as read_error:
            logger.error(f"Error reading notebook from storage for download: {read_error}")
            return HttpResponse(
                "<html><body><h1>Error Reading Notebook</h1><p>The notebook could not be read from storage.</p></body></html>",
                content_type='text/html',
                status=500
            )
        
    except Exception as e:
        logger.error(f"Error downloading notebook {notebook_id}: {e}", exc_info=True)
        return HttpResponse(
            "<html><body><h1>Error</h1><p>An error occurred while downloading the notebook.</p></body></html>",
            content_type='text/html',
            status=500
        )