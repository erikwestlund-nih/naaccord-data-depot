"""
Audit system for Johns Hopkins compliance.

This package implements the comprehensive audit system required by 
Johns Hopkins IT Security Checklist, including:

- Universal observer pattern for ALL model changes
- Activity logging for authentication and access events
- Session timeout and security monitoring
- HIPAA-compliant audit trail with indefinite retention
"""
from .observers import ModelObserver, get_current_user, set_current_user, get_current_request, set_current_request

__all__ = [
    'ModelObserver',
    'get_current_user', 
    'set_current_user',
    'get_current_request',
    'set_current_request',
]