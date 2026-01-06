"""
Session timeout middleware.

Johns Hopkins Requirements:
- "Application automatically terminates user sessions after a specified period of inactivity"
- Log session initiation and termination
- 1-hour configurable timeout
- Terminal tracking for compliance

Note: Page access is tracked via server logs, not in the database, to prevent bloat.
"""
from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from datetime import timedelta
import logging

logger = logging.getLogger('depot.session')


class SessionActivityMiddleware(MiddlewareMixin):
    """
    Middleware that handles session timeout.
    
    Features:
    - Configurable session timeout (default 1 hour)
    - Automatic logout after inactivity
    - Logging for session initiation/termination events only
    - Terminal/workstation tracking
    - Page access tracked via server logs (not database)
    """
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        
        # Get timeout from settings (in seconds)
        self.timeout_seconds = getattr(settings, 'SESSION_TIMEOUT_SECONDS', 3600)  # 1 hour default
        self.timeout_delta = timedelta(seconds=self.timeout_seconds)
        
        # Paths to exclude from timeout checking
        self.excluded_paths = getattr(settings, 'SESSION_TIMEOUT_EXCLUDED_PATHS', [
            '/sign-in',
            '/saml2/',
            '/admin/',
        ])
    
    def process_request(self, request):
        """
        Process incoming request for session timeout and activity logging.
        """
        # Set current user and request in thread-local storage for observer pattern
        if request.user.is_authenticated:
            from depot.audit import set_current_user, set_current_request
            set_current_user(request.user)
            set_current_request(request)
        
        # Skip timeout check for excluded paths
        if self._is_excluded_path(request.path):
            return None
            
        # Skip timeout check for unauthenticated users
        if not request.user.is_authenticated:
            return None
            
        # Check session timeout
        return self._check_session_timeout(request)
    
    def process_response(self, request, response):
        """
        Process response to update last activity timestamp.
        """
        if request.user.is_authenticated:
            # Only update last activity timestamp, don't log every page access
            self._update_last_activity(request)
            
        return response
    
    def _is_excluded_path(self, path):
        """Check if path should be excluded from timeout checking."""
        return any(path.startswith(excluded) for excluded in self.excluded_paths)
    
    def _check_session_timeout(self, request):
        """
        Check if session has timed out and handle accordingly.
        """
        last_activity = request.session.get('last_activity')
        
        if last_activity:
            try:
                last_activity_time = timezone.datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_activity_time):
                    last_activity_time = timezone.make_aware(last_activity_time)
                    
                time_since_activity = timezone.now() - last_activity_time
                
                if time_since_activity > self.timeout_delta:
                    # Session has timed out
                    self._handle_session_timeout(request)
                    return redirect(reverse('auth.sign_in'))
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid last_activity format in session: {e}")
                # Reset last activity to current time
                self._update_last_activity(request)
        else:
            # No last activity recorded - set it now
            self._update_last_activity(request)
            self._log_session_initiation(request)
        
        return None
    
    def _handle_session_timeout(self, request):
        """
        Handle session timeout by logging activity and logging out user.
        """
        # Capture user ID before logout (since logout() sets user to AnonymousUser)
        user_id = request.user.id if request.user.is_authenticated else None

        logger.info(f"Session timeout for user_id: {user_id}")
        
        # Log timeout activity before logout
        self._log_session_timeout(request)
        
        # Clear session data
        session_key = request.session.session_key
        request.session.flush()
        
        # Logout user
        logout(request)
        
        logger.info(f"User ID {user_id} logged out due to session timeout")
    
    def _update_last_activity(self, request):
        """Update last activity timestamp in session."""
        request.session['last_activity'] = timezone.now().isoformat()
        
        # Also track session metadata for compliance
        if 'session_metadata' not in request.session:
            request.session['session_metadata'] = {
                'created_at': timezone.now().isoformat(),
                'ip_address': self._get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                'terminal_id': self._get_terminal_id(request),
            }
    
    def _get_client_ip(self, request):
        """Extract real client IP from request, handling proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _get_terminal_id(self, request):
        """
        Generate terminal ID for Johns Hopkins compliance requirement.
        Combines IP address and user agent for workstation identification.
        """
        ip = self._get_client_ip(request)
        user_agent_hash = str(hash(request.META.get('HTTP_USER_AGENT', '')))[-8:]
        return f"{ip}_{user_agent_hash}"
    
    def _log_session_initiation(self, request):
        """Log session initiation activity."""
        try:
            from depot.models import Activity, ActivityType
            
            # Check if user exists in database before logging
            # This prevents foreign key constraint errors during SAML auth
            if hasattr(request.user, 'pk') and request.user.pk:
                Activity.log_activity(
                    user=request.user,
                    activity_type=ActivityType.LOGIN,
                    success=True,
                    request=request,
                    details={
                        'session_initiated': True,
                        'timeout_seconds': self.timeout_seconds,
                        'terminal_id': self._get_terminal_id(request),
                    }
                )
            else:
                logger.debug(f"Skipping activity log for user without database record: user_id {getattr(request.user, 'id', 'unknown')}")
        except Exception as e:
            logger.error(f"Failed to log session initiation: {e}")
    
    def _log_session_timeout(self, request):
        """Log session timeout activity."""
        try:
            from depot.models import Activity, ActivityType
            
            # Check if user exists in database before logging
            if not (hasattr(request.user, 'pk') and request.user.pk):
                logger.debug(f"Skipping timeout log for user without database record: user_id {getattr(request.user, 'id', 'unknown')}")
                return
            
            session_metadata = request.session.get('session_metadata', {})
            session_duration = None
            
            if session_metadata.get('created_at'):
                try:
                    created_at = timezone.datetime.fromisoformat(session_metadata['created_at'])
                    if timezone.is_naive(created_at):
                        created_at = timezone.make_aware(created_at)
                    session_duration = (timezone.now() - created_at).total_seconds()
                except (ValueError, TypeError):
                    pass
            
            Activity.log_activity(
                user=request.user,
                activity_type=ActivityType.SESSION_TIMEOUT,
                success=True,
                request=request,
                details={
                    'timeout_seconds': self.timeout_seconds,
                    'session_duration_seconds': session_duration,
                    'terminal_id': session_metadata.get('terminal_id'),
                    'auto_logout': True,
                }
            )
        except Exception as e:
            logger.error(f"Failed to log session timeout: {e}")
    


class RequestTimingMiddleware(MiddlewareMixin):
    """
    Simple middleware to add request timing for activity logging.
    """
    
    def process_request(self, request):
        request._start_time = timezone.now().timestamp()
    
    def process_response(self, request, response):
        if hasattr(request, '_start_time'):
            duration = timezone.now().timestamp() - request._start_time
            response['X-Response-Time'] = f"{duration:.3f}s"
        return response