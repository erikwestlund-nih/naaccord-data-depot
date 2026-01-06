# Sensitive Data in Logs - Analysis & Remediation

**Date:** January 25, 2025
**Risk Level:** MEDIUM to HIGH (depending on data type)
**Compliance Impact:** HIPAA violation if PHI is logged

---

## Current Sensitive Data Being Logged

### 1. User Identifiable Information

#### Email Addresses (PII)
```python
# Location: Multiple files
logger.info(f"Processing SAML authentication for: {email}")  # auth/saml_backend.py:46
logger.info(f"Created new user from SAML: {email}")  # auth/saml_backend.py:71
logger.info(f"Notebook access check for user {request.user.email}:")  # views/notebooks.py:24
logger.warning(f"Access denied: User {request.user.email} attempted...")  # views/notebooks.py:116
```
**Risk:** Email addresses are PII and could identify researchers

#### User Session Information
```python
# middleware/session_activity.py:121
logger.info(f"Session timeout for user {user_email}")
logger.info(f"User {user_email} logged out due to session timeout")
```

### 2. File Paths and Storage Locations

#### Storage Paths (May Contain Patient IDs)
```python
# views/internal_storage.py:122
logger.info(f"Successfully saved streamed file: {saved_path} ({uploaded_file.size} bytes)")

# services/notebook.py:197
logger.info(f"Storing compiled notebook at: {storage_path}")
```
**Risk:** File paths might contain cohort names, patient IDs, or other identifiers

### 3. Cohort Information

#### Cohort Names
```python
# views/notebooks.py:28
logger.info(f"  - Notebook cohort: {notebook.cohort.name if notebook.cohort else 'None'}")
logger.info(f"  - User cohorts: {[c.name for c in request.user.cohorts.all()]}")
```
**Risk:** Cohort names might be considered sensitive institutional information

### 4. Data Processing Details

#### Patient Counts and IDs
```python
# services/patient_id_service.py:82
logger.info(f"Extracted {patient_record.patient_count} patient IDs from file {file_id}")
```
**Risk:** Aggregate counts combined with other info could be identifying

### 5. API and Authentication Details

#### Failed Authentication Attempts
```python
# views/internal_storage.py:43
logger.warning(f"Invalid API key attempt from {request.META.get('REMOTE_ADDR')}")
```
**Risk:** IP addresses are logged (PII in some jurisdictions)

### 6. SAML Attributes
```python
# auth/saml_backend.py:47
logger.debug(f"SAML attributes: {attributes}")
```
**Risk:** May contain institutional IDs, names, roles

---

## Severity Assessment by Data Type

| Data Type | Current Logging | PHI Risk | PII Risk | Action Required |
|-----------|-----------------|----------|----------|-----------------|
| Email addresses | Full text | Low | HIGH | Redact or hash |
| User IDs | Numeric IDs | Low | Medium | Keep (internal ID) |
| Patient IDs | Not directly logged | HIGH if present | HIGH | Never log |
| File paths | Full paths | Medium | Low | Sanitize |
| Cohort names | Full text | Low | Medium | Consider masking |
| IP addresses | Full address | Low | Medium | Mask last octet |
| Session IDs | Not logged | Low | Low | Keep this way |
| API keys | Not logged (good) | N/A | HIGH | Never log |

---

## Recommended Sanitization Strategy

### 1. Create Log Sanitizer Middleware

```python
# depot/utils/log_sanitizer.py
import re
import hashlib
from typing import Any, Dict

class LogSanitizer:
    """Sanitize sensitive data before logging."""

    # Patterns to detect sensitive data
    PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'patient_id': r'\bPT[0-9]{8}\b',  # Adjust based on your format
        'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
        'ip_address': r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    }

    @classmethod
    def sanitize_email(cls, email: str) -> str:
        """Hash email but keep domain for debugging."""
        if '@' in email:
            local, domain = email.split('@', 1)
            hashed = hashlib.sha256(local.encode()).hexdigest()[:8]
            return f"{hashed}@{domain}"
        return "[INVALID_EMAIL]"

    @classmethod
    def sanitize_ip(cls, ip: str) -> str:
        """Mask last octet of IP address."""
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        return "[INVALID_IP]"

    @classmethod
    def sanitize_path(cls, path: str) -> str:
        """Remove sensitive parts from file paths."""
        # Remove patient IDs if present
        path = re.sub(r'PT[0-9]{8}', '[PATIENT_ID]', path)
        # Keep only last 2 directory levels
        parts = path.split('/')
        if len(parts) > 3:
            return f".../{'/'.join(parts[-3:])}"
        return path

    @classmethod
    def sanitize_message(cls, message: str) -> str:
        """Sanitize a log message."""
        # Replace emails
        message = re.sub(cls.PATTERNS['email'],
                         lambda m: cls.sanitize_email(m.group(0)),
                         message)

        # Replace patient IDs
        message = re.sub(cls.PATTERNS['patient_id'], '[PATIENT_ID]', message)

        # Replace SSNs
        message = re.sub(cls.PATTERNS['ssn'], '[SSN]', message)

        # Replace IPs
        message = re.sub(cls.PATTERNS['ip_address'],
                         lambda m: cls.sanitize_ip(m.group(0)),
                         message)

        return message


# Custom logger that auto-sanitizes
import logging

class SanitizedLogger:
    """Logger wrapper that sanitizes sensitive data."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sanitizer = LogSanitizer()

    def _log(self, level: str, msg: str, *args, **kwargs):
        """Internal logging method with sanitization."""
        sanitized_msg = self.sanitizer.sanitize_message(str(msg))
        getattr(self.logger, level)(sanitized_msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self._log('debug', msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._log('info', msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._log('warning', msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log('error', msg, *args, **kwargs)

# Usage
logger = SanitizedLogger(logging.getLogger(__name__))
logger.info(f"User john.doe@example.com accessed file")
# Output: "User a1b2c3d4@example.com accessed file"
```

### 2. Structured Logging Alternative

```python
# depot/utils/structured_logger.py
import json
import logging

class StructuredLogger:
    """Use structured logging to separate sensitive data."""

    def __init__(self, logger):
        self.logger = logger

    def log_event(self, event_type: str, data: Dict[str, Any],
                  level: str = 'info'):
        """Log structured event with sensitive data in separate fields."""

        # Separate sensitive and non-sensitive data
        safe_data = {}
        sensitive_data = {}

        sensitive_fields = {'email', 'user_id', 'patient_id', 'ip_address',
                           'cohort_name', 'file_path'}

        for key, value in data.items():
            if key in sensitive_fields:
                # Hash sensitive data
                sensitive_data[key] = hashlib.sha256(
                    str(value).encode()
                ).hexdigest()[:16]
            else:
                safe_data[key] = value

        log_entry = {
            'event': event_type,
            'data': safe_data,
            'sensitive': sensitive_data,  # Only in debug mode
            'timestamp': datetime.utcnow().isoformat()
        }

        # In production, don't log sensitive data at all
        if not settings.DEBUG:
            log_entry.pop('sensitive', None)

        getattr(self.logger, level)(json.dumps(log_entry))

# Usage
logger = StructuredLogger(logging.getLogger(__name__))
logger.log_event('user_login', {
    'email': 'user@example.com',
    'cohort_name': 'VACS',
    'action': 'login',
    'success': True
})
```

---

## Implementation Priority

### Phase 1: Immediate (Before Testing)
1. **Remove email addresses from logs**
   - Replace with hashed versions
   - Keep domain for debugging

2. **Sanitize file paths**
   - Remove any patient IDs
   - Truncate to relative paths

3. **Mask IP addresses**
   - Keep first 3 octets for debugging
   - Mask last octet

### Phase 2: During Testing
1. **Implement structured logging**
   - Separate sensitive fields
   - Enable/disable based on environment

2. **Add log aggregation**
   - Send to central logging system
   - Apply retention policies

### Phase 3: Before Production
1. **Complete audit of all log statements**
   - Review every logger.* call
   - Apply sanitization consistently

2. **Implement log retention policies**
   - 90 days for application logs
   - 7 years for audit logs (HIPAA)

---

## Quick Fixes for Specific Files

### auth/saml_backend.py
```python
# Replace line 46:
# OLD: logger.info(f"Processing SAML authentication for: {email}")
# NEW:
email_hash = hashlib.sha256(email.encode()).hexdigest()[:8]
logger.info(f"Processing SAML authentication for user: {email_hash}")
```

### views/notebooks.py
```python
# Replace line 24:
# OLD: logger.info(f"Notebook access check for user {request.user.email}:")
# NEW:
user_id = request.user.id
logger.info(f"Notebook access check for user_id: {user_id}")
```

### middleware/session_activity.py
```python
# Replace line 121:
# OLD: logger.info(f"Session timeout for user {user_email}")
# NEW:
user_hash = hashlib.sha256(user_email.encode()).hexdigest()[:8]
logger.info(f"Session timeout for user: {user_hash}")
```

---

## Testing the Sanitization

```python
# tests/test_log_sanitizer.py
def test_email_sanitization():
    msg = "User john.doe@example.com logged in"
    sanitized = LogSanitizer.sanitize_message(msg)
    assert "john.doe" not in sanitized
    assert "@example.com" in sanitized

def test_ip_sanitization():
    msg = "Failed login from 192.168.1.100"
    sanitized = LogSanitizer.sanitize_message(msg)
    assert "192.168.1.xxx" in sanitized
    assert "192.168.1.100" not in sanitized

def test_path_sanitization():
    path = "/storage/uploads/cohort1/patient/PT12345678.csv"
    sanitized = LogSanitizer.sanitize_path(path)
    assert "PT12345678" not in sanitized
    assert "[PATIENT_ID]" in sanitized
```

---

## Monitoring & Compliance

### Log Review Process
1. Weekly review of log files for sensitive data
2. Automated scanning for patterns
3. Alert on any potential PHI exposure

### Compliance Checklist
- [ ] No email addresses in plain text
- [ ] No patient IDs in any form
- [ ] No full IP addresses
- [ ] No file paths with identifiers
- [ ] No API keys or passwords
- [ ] No SAML attributes with PII
- [ ] Audit logs separate from application logs
- [ ] Retention policies implemented