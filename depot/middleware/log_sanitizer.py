"""
Log Sanitizer Middleware for HIPAA Compliance
Removes PII/PHI from log messages before they're written
"""

import logging
import re
import hashlib
from typing import Any, Dict


class SanitizingFilter(logging.Filter):
    """Filter that sanitizes sensitive data from log records."""

    # Patterns to detect and sanitize
    PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'patient_id': r'\bPT[0-9]{8}\b',  # Adjust based on your format
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'ip_address': r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
        'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    }

    @staticmethod
    def hash_email(email: str) -> str:
        """Hash email keeping domain for debugging."""
        if '@' in email:
            local, domain = email.split('@', 1)
            hashed = hashlib.sha256(local.encode()).hexdigest()[:8]
            return f"user_{hashed}@{domain}"
        return "[INVALID_EMAIL]"

    @staticmethod
    def mask_ip(ip: str) -> str:
        """Mask last octet of IP address."""
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        return "[INVALID_IP]"

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and sanitize the log record."""
        # Sanitize the main message
        if hasattr(record, 'msg'):
            msg = str(record.msg)

            # Replace emails
            msg = re.sub(
                self.PATTERNS['email'],
                lambda m: self.hash_email(m.group(0)),
                msg
            )

            # Replace patient IDs
            msg = re.sub(self.PATTERNS['patient_id'], '[PATIENT_ID]', msg)

            # Replace SSNs
            msg = re.sub(self.PATTERNS['ssn'], '[SSN_REDACTED]', msg)

            # Replace IPs
            msg = re.sub(
                self.PATTERNS['ip_address'],
                lambda m: self.mask_ip(m.group(0)),
                msg
            )

            # Replace phone numbers
            msg = re.sub(self.PATTERNS['phone'], '[PHONE_REDACTED]', msg)

            record.msg = msg

        # Sanitize any args that might contain sensitive data
        if hasattr(record, 'args') and record.args:
            sanitized_args = []
            for arg in record.args:
                arg_str = str(arg)
                # Apply same sanitization to args
                arg_str = re.sub(
                    self.PATTERNS['email'],
                    lambda m: self.hash_email(m.group(0)),
                    arg_str
                )
                arg_str = re.sub(self.PATTERNS['patient_id'], '[PATIENT_ID]', arg_str)
                arg_str = re.sub(self.PATTERNS['ssn'], '[SSN_REDACTED]', arg_str)
                arg_str = re.sub(
                    self.PATTERNS['ip_address'],
                    lambda m: self.mask_ip(m.group(0)),
                    arg_str
                )
                sanitized_args.append(arg_str)
            record.args = tuple(sanitized_args)

        return True


class LogSanitizerMiddleware:
    """
    Middleware to ensure all Django logging is sanitized.
    This should be added early in the middleware stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Install the sanitizing filter on all loggers
        self._install_sanitizer()

    def _install_sanitizer(self):
        """Install the sanitizing filter on the root logger."""
        root_logger = logging.getLogger()

        # Check if sanitizer already installed
        for filter in root_logger.filters:
            if isinstance(filter, SanitizingFilter):
                return

        # Add sanitizing filter
        sanitizer = SanitizingFilter()
        root_logger.addFilter(sanitizer)

        # Also add to all existing loggers
        for name in logging.Logger.manager.loggerDict:
            logger = logging.getLogger(name)
            logger.addFilter(sanitizer)

    def __call__(self, request):
        response = self.get_response(request)
        return response


# Utility functions for safe logging

def get_safe_user_identifier(user) -> str:
    """Get a safe user identifier for logging."""
    if not user or user.is_anonymous:
        return "anonymous"
    return f"user_id:{user.id}"


def log_user_action(logger: logging.Logger, user, action: str, details: Dict[str, Any] = None):
    """
    Log a user action with sanitized user information.

    Args:
        logger: The logger instance to use
        user: Django user object
        action: Description of the action
        details: Optional additional details (will be sanitized)
    """
    user_id = get_safe_user_identifier(user)

    log_data = {
        'user': user_id,
        'action': action,
    }

    if details:
        # Sanitize any details
        sanitized_details = {}
        for key, value in details.items():
            if key in ['email', 'username', 'first_name', 'last_name']:
                # Skip PII fields
                continue
            sanitized_details[key] = value
        log_data['details'] = sanitized_details

    logger.info(f"User action: {action} by {user_id}", extra=log_data)


def log_access_attempt(logger: logging.Logger, request, success: bool, reason: str = None):
    """
    Log an access attempt with sanitized request information.

    Args:
        logger: The logger instance to use
        request: Django request object
        success: Whether the access was successful
        reason: Optional reason for failure
    """
    # Get sanitized IP
    ip = request.META.get('REMOTE_ADDR', 'unknown')
    if ip != 'unknown' and '.' in ip:
        parts = ip.split('.')
        if len(parts) == 4:
            ip = f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"

    user_id = get_safe_user_identifier(request.user) if hasattr(request, 'user') else 'anonymous'

    status = "successful" if success else "failed"
    msg = f"Access {status} from {ip} for {user_id}"

    if reason:
        msg += f" - Reason: {reason}"

    if success:
        logger.info(msg)
    else:
        logger.warning(msg)