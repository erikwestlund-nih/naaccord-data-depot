# Deployment Security TODOs

**Date:** January 25, 2025
**Target:** Internal Testing Deployment (Non-PHI Data)
**Priority:** Complete before production with real PHI

---

## ✅ Completed Security Fixes

### 1. ✅ SQL Injection in reset_db.py
- **Status:** FIXED
- **Action Taken:** Removed direct SQL execution with f-strings, replaced with Django's flush command
- **File:** `depot/management/commands/reset_db.py`
- **Date Completed:** January 25, 2025

### 2. ✅ DEV_BYPASS_SECURITY Flag Removed
- **Status:** FIXED
- **Action Taken:**
  - Removed flag from settings.py
  - Updated all views that used the flag
  - Deleted dev_bypass middleware
- **Files Updated:**
  - `depot/settings.py`
  - `depot/views/submissions/upload.py`
  - `depot/views/upload_precheck.py`
  - `depot/views/upload_precheck_refactored.py`
  - `depot/views/notebooks.py`
  - `depot/middleware/dev_bypass.py` (deleted)
- **Date Completed:** January 25, 2025

---

## 🔴 Critical - Fix Before Internal Testing

### 3. Containerize Quarto/R Execution
- **Priority:** CRITICAL
- **Risk:** Unsandboxed code execution vulnerability
- **Location:** `depot/services/notebook.py:150`
- **Action Required:**
  ```yaml
  # Docker container for R/Quarto execution
  - Create Dockerfile with minimal R environment
  - No network access (--network=none)
  - Read-only filesystem except /tmp
  - Memory limits (1GB max)
  - CPU limits (50% of one core)
  - Non-root user
  - Timeout enforcement (5 minutes max)
  ```
- **Assignee:** [TBD]
- **Due Date:** Before internal testing

### 4. Implement Basic PHI Encryption
- **Priority:** CRITICAL (for production, not internal testing)
- **Risk:** HIPAA violation when real PHI is used
- **Action Required:**
  - For internal testing: Document that NO REAL PHI should be used
  - For production: Implement AES-256 encryption at rest
- **Note:** Since internal testing uses non-PHI data, this can wait until pre-production

---

## 🟠 High Priority - Fix Within 1 Week of Internal Testing

### 5. Replace Hardcoded API Keys
- **Priority:** HIGH
- **Location:** `depot/views/internal_storage.py:36`
- **Action Required:**
  - Implement JWT tokens with 1-hour expiry
  - OR use mutual TLS between services
  - Add key rotation mechanism
- **Assignee:** [TBD]
- **Due Date:** Week 1 of testing

### 6. Enable HTTPS for Internal Services
- **Priority:** HIGH
- **Current:** HTTP between web (8000) and services (8001)
- **Action Required:**
  ```bash
  # Generate self-signed certificates for testing
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout services.key -out services.crt
  ```
- **Assignee:** [TBD]
- **Due Date:** Week 1 of testing

### 7. Remove PHI from Logs
- **Priority:** HIGH
- **Location:** Multiple files logging user emails and file paths
- **Action Required:**
  - Create log sanitizer middleware
  - Hash or redact sensitive information
  - Review all logger.info() calls
- **Assignee:** [TBD]
- **Due Date:** Week 1 of testing

### 8. Add File Type Validation
- **Priority:** HIGH
- **Location:** `depot/views/internal_storage.py:54-80`
- **Action Required:**
  - Use python-magic to validate actual file content
  - Reject non-CSV files regardless of extension
  - Add virus scanning (ClamAV)
- **Assignee:** [TBD]
- **Due Date:** Week 1 of testing

---

## 🟡 Medium Priority - Fix During Testing Phase

### 9. Add Rate Limiting
- **Priority:** MEDIUM
- **Action Required:**
  ```python
  # Install django-ratelimit
  pip install django-ratelimit

  # Add to views
  @ratelimit(key='user', rate='100/hour')
  ```
- **Target Endpoints:**
  - `/sign-in` - 5 attempts/minute
  - `/api/*` - 100 requests/hour
  - `/upload` - 10 uploads/hour
- **Assignee:** [TBD]
- **Due Date:** During testing

### 10. Fix Session Regeneration
- **Priority:** MEDIUM
- **Location:** `depot/views/auth/sign_in.py:119`
- **Action Required:**
  ```python
  # After successful auth
  request.session.cycle_key()
  ```
- **Assignee:** [TBD]
- **Due Date:** During testing

### 11. Add Security Headers
- **Priority:** MEDIUM
- **Action Required:**
  - X-Frame-Options: DENY
  - X-Content-Type-Options: nosniff
  - Content-Security-Policy
  - Strict-Transport-Security (for production)
- **Assignee:** [TBD]
- **Due Date:** During testing

### 12. Implement CSRF Protection
- **Priority:** MEDIUM
- **Location:** API endpoints with @csrf_exempt
- **Action Required:**
  - Enable CSRF for state-changing operations
  - Use API tokens for service-to-service calls
- **Assignee:** [TBD]
- **Due Date:** During testing

---

## 📋 Pre-Production Checklist (Before Real PHI)

### Data Protection
- [ ] PHI encryption at rest (AES-256)
- [ ] PHI encryption in transit (TLS 1.3)
- [ ] Database encryption enabled
- [ ] Backup encryption configured

### Authentication & Access
- [ ] Multi-factor authentication (MFA)
- [ ] Strong password policy (12+ chars)
- [ ] Session timeout (15 min idle)
- [ ] Audit logging for all PHI access

### Infrastructure
- [ ] WAF configured (CloudFlare/AWS)
- [ ] DDoS protection enabled
- [ ] Intrusion detection system
- [ ] Security monitoring (SIEM)

### Compliance
- [ ] HIPAA compliance audit
- [ ] Penetration testing completed
- [ ] Security training for all staff
- [ ] Incident response plan

---

## 🚀 Deployment Environment Requirements

### Internal Testing (Current Phase)
```yaml
Environment: Development/Staging
Data: Synthetic test data only (NO REAL PHI)
Access: Internal team only
Security Level: Basic
Key Requirements:
  - Containerized Quarto execution
  - Basic access controls
  - HTTPS for external access
  - Application logging
```

### Production (Future)
```yaml
Environment: Production
Data: Real PHI data
Access: Authorized researchers
Security Level: Full HIPAA compliance
Key Requirements:
  - All security fixes implemented
  - Encryption at rest and in transit
  - MFA required
  - Full audit logging
  - 24/7 security monitoring
```

---

## 📝 Notes

1. **Test Data Only:** For internal testing, use ONLY synthetic/test data. No real patient information.

2. **Security Review:** Schedule security review after 2 weeks of internal testing.

3. **Monitoring:** Set up basic monitoring for internal testing:
   - Application errors
   - Failed login attempts
   - File upload sizes
   - API response times

4. **Documentation:** Update security documentation as fixes are applied.

5. **Training:** Ensure team knows security best practices before testing begins.

---

## 🔄 Update History

- **2025-01-25:** Initial document created
  - Fixed SQL injection
  - Removed DEV_BYPASS_SECURITY
  - Created deployment checklist

---

## 📧 Contact

**Security Lead:** [TBD]
**DevOps Lead:** [TBD]
**Compliance Officer:** [TBD]