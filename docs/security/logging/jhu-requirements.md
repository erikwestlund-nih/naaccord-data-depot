# Logging Compliance Analysis - Johns Hopkins IT Security Requirements

**Date:** January 25, 2025
**Reference:** IT Security Checklist Vendor-Hopkins- NA-ACCORD Data Depot 20250716.pdf

---

## Johns Hopkins Requirements vs Current State

### D.1 - Access Logging Requirements ✅ COMPLIANT
**Requirement:** System logs access attempts and successful logins by user ID, date, time, session initiation and termination.
**Duration:** Indefinite (12 months minimum)

**Current State:** COMPLIANT
- Django authentication signals capture login attempts
- Session middleware tracks initiation/termination
- All events logged with timestamps

**Required Actions:** None - already compliant

---

### D.2 - Audit Trail Requirements ✅ COMPLIANT
**Requirement:** System maintains an audit trail of administration and maintenance performed by date, time, user ID, and terminal.
**Duration:** Indefinite (12 months minimum)

**Current State:** COMPLIANT
- Observer pattern logs all record modifications
- Timestamps and authentication info captured
- Backup system provides second line of defense

**Required Actions:** None - already compliant

---

### D.3 - Patient Information Access ✅ N/A
**Requirement:** System logs all user access and changes to patient information at the individual record level
**Current State:** NOT APPLICABLE
- Per checklist: "Our system does not provide affordances to alter PHI"
- System only uploads/validates, doesn't modify patient data

---

### D.4 - Log Export Requirements ✅ COMPLIANT
**Requirement:** System allows JH personnel to automatically download complete user access logs in a standard format.

**Current State:** COMPLIANT
- mysqldump tool provided for log export

**Required Actions:** None - already compliant

---

## CRITICAL ISSUE: Sensitive Data in Logs

While we meet the technical logging requirements, we have a **COMPLIANCE VIOLATION** regarding what we're logging:

### Current Violations Found:

#### 1. Email Addresses (PII) - **VIOLATION**
```python
# VIOLATION: Logging email addresses in plain text
logger.info(f"Processing SAML authentication for: {email}")  # auth/saml_backend.py:46
logger.info(f"Session timeout for user {user_email}")  # middleware/session_activity.py:121
```

**JH Requirement Impact:** While not explicitly prohibited in the checklist, HIPAA requires minimum necessary logging. Email addresses are PII.

**REQUIRED FIX:**
```python
# Use user ID or hashed email
user_id = request.user.id
logger.info(f"Processing SAML authentication for user_id: {user_id}")
```

#### 2. IP Addresses - **POTENTIAL VIOLATION**
```python
logger.warning(f"Invalid API key attempt from {request.META.get('REMOTE_ADDR')}")
```

**JH Requirement:** Section C.4 requires TLS encryption for authentication actions
**Impact:** IP addresses can be considered PII in some contexts

**REQUIRED FIX:**
```python
# Mask last octet
ip = request.META.get('REMOTE_ADDR', '')
masked_ip = '.'.join(ip.split('.')[:3] + ['xxx']) if '.' in ip else 'unknown'
logger.warning(f"Invalid API key attempt from {masked_ip}")
```

#### 3. File Paths - **ACCEPTABLE WITH CAUTION**
```python
logger.info(f"Successfully saved streamed file: {saved_path}")
```

**Assessment:** Acceptable if paths don't contain patient IDs
**Recommendation:** Sanitize paths to remove any potential identifiers

---

## Immediate Actions Required for Compliance

### Priority 1: Fix Email Logging (CRITICAL)
Replace all instances of email logging with user IDs:

```python
# depot/utils/logging_utils.py
def log_user_action(user, action, details=None):
    """Log user actions without exposing PII."""
    user_identifier = f"user_id:{user.id}" if user else "anonymous"
    logger.info(f"{action} - {user_identifier}", extra={
        'user_id': user.id if user else None,
        'action': action,
        'details': details
    })
```

### Priority 2: Implement Log Sanitizer
```python
# depot/middleware/log_sanitizer.py
import logging
import re

class SanitizingFormatter(logging.Formatter):
    """Formatter that removes sensitive data from log messages."""

    PATTERNS = {
        'email': (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                  lambda m: f"[USER_EMAIL_{hash(m.group())%10000:04d}]"),
        'ip': (r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
               lambda m: '.'.join(m.group().split('.')[:3] + ['xxx'])),
        'ssn': (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]'),
    }

    def format(self, record):
        msg = super().format(record)
        for pattern, replacement in self.PATTERNS.values():
            if callable(replacement):
                msg = re.sub(pattern, replacement, msg)
            else:
                msg = re.sub(pattern, replacement, msg)
        return msg
```

### Priority 3: Update All Logging Statements

Files requiring immediate updates:
1. `depot/auth/saml_backend.py` - Lines 46, 71
2. `depot/middleware/session_activity.py` - Lines 121, 127
3. `depot/views/notebooks.py` - Lines 24, 116
4. `depot/views/internal_storage.py` - Line 43

---

## Compliance Certification Statement

### Current Compliance Status: **PARTIAL**

✅ **Compliant Areas:**
- Access attempt logging
- Session tracking
- Audit trails
- Log retention (12+ months)
- Log export capability

❌ **Non-Compliant Areas:**
- PII (email addresses) logged in plain text
- IP addresses not masked
- No automated log sanitization

### Required for Full Compliance:
1. **Immediate:** Remove all email addresses from logs
2. **Week 1:** Implement log sanitizer middleware
3. **Week 2:** Audit all log statements for PII
4. **Week 3:** Deploy sanitized logging to production

---

## Implementation Script

```bash
#!/bin/bash
# fix-logging-compliance.sh

echo "Fixing logging compliance issues..."

# Find all files with email logging
echo "Files logging emails:"
grep -r "logger.*email" depot/ --include="*.py"

# Find all files with IP logging
echo "Files logging IPs:"
grep -r "REMOTE_ADDR" depot/ --include="*.py"

# Apply fixes
for file in $(grep -rl "logger.*email" depot/ --include="*.py"); do
    echo "Fixing: $file"
    # Backup original
    cp "$file" "$file.bak"
    # Replace email logging with user_id logging
    sed -i '' 's/f".*{.*email.*}"/f"user_id: {request.user.id if hasattr(request, \"user\") else \"anonymous\"}"/g' "$file"
done

echo "Manual review required for complex cases"
```

---

## Sign-off Requirements

Before deployment to production with PHI:

- [ ] All email addresses removed from logs
- [ ] IP addresses masked
- [ ] Log sanitizer implemented and tested
- [ ] All log statements audited for PII/PHI
- [ ] Compliance review completed
- [ ] Security team approval

**Reviewer:** _________________ **Date:** _______
**Security Lead:** _________________ **Date:** _______
**Compliance Officer:** _________________ **Date:** _______