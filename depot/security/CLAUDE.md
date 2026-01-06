# Security Domain - CLAUDE.md

## Domain Overview

The security domain encompasses PHI (Protected Health Information) compliance, HIPAA audit trails, multi-server access control, and comprehensive file tracking systems. This domain ensures all clinical data operations maintain strict security boundaries and complete accountability.

## Core Security Architecture

### Two-Server PHI Isolation

```
Web Server (DMZ)              Services Server (Secure Zone)
┌─────────────────────┐      ┌─────────────────────────┐
│ - Public access     │      │ - PHI data processing   │
│ - Authentication    │ ──── │ - File storage          │
│ - File streaming    │      │ - R analysis            │
│ - No PHI storage    │      │ - Database operations   │
└─────────────────────┘      └─────────────────────────┘
         │                                │
         └── Encrypted WireGuard Tunnel ──┘
```

**Key Security Principles:**
- **PHI Isolation**: Web server never stores PHI data
- **Encrypted Transport**: All inter-server communication via WireGuard
- **Audit Everything**: Complete trail of all PHI operations
- **Role-Based Access**: Server roles enforce security boundaries
- **Cleanup Verification**: Mandatory cleanup of temporary files

## PHI File Tracking System

### Core Model: PHIFileTracking

**Location**: `depot/models/phifiletracking.py`

Provides comprehensive audit trail for all PHI file operations with HIPAA compliance:

```python
# Log every PHI file operation
PHIFileTracking.log_operation(
    cohort=cohort,
    user=user,
    action='nas_raw_created',
    file_path='/mnt/nas/submissions/cohort_123/patient_data.csv',
    file_type='raw_csv',
    file_size=1024000,
    content_object=audit_instance
)
```

### Critical Action Types

**NAS Operations:**
- `nas_raw_created` - Raw file stored on NAS
- `nas_raw_deleted` - Raw file removed from NAS
- `nas_duckdb_created` - DuckDB conversion completed
- `nas_report_created` - Report generated and stored

**Workspace Operations:**
- `work_copy_created` - Temporary file for processing
- `work_copy_deleted` - Temporary file cleanup verified

**Processing Operations:**
- `conversion_started/completed/failed` - DuckDB conversion tracking
- `patient_id_extraction_started/completed/failed` - ID extraction tracking

**Streaming Operations:**
- `file_uploaded_via_stream` - Web→Services file transfer
- `file_downloaded_via_stream` - Services→Web file transfer
- `scratch_cleanup` - Temporary directory cleanup

### Cleanup Management

```python
# Track files requiring cleanup
PHIFileTracking.log_operation(
    action='work_copy_created',
    file_path=temp_path,
    cleanup_required=True,
    expected_cleanup_by=timezone.now() + timedelta(hours=2)
)

# Verify cleanup completion
tracking_record.mark_cleaned_up(user=request.user)

# Monitor overdue cleanups
overdue_files = PHIFileTracking.get_overdue_cleanups()
```

**Cleanup Fields:**
- `cleanup_required` - File needs cleanup
- `expected_cleanup_by` - Cleanup deadline
- `cleanup_attempted_count` - Retry attempts
- `cleaned_up` - Cleanup verified
- `cleanup_verified_by` - User who verified

## Access Control Patterns

### Cohort-Based Security

```python
# User access to cohort data
def user_can_access_cohort(user, cohort):
    """Check if user belongs to cohort group"""
    return user.groups.filter(
        name=f"{cohort.name}_users"
    ).exists()

# Decorator for cohort-protected views
@cohort_required
def view_cohort_data(request, cohort_id):
    cohort = get_object_or_404(Cohort, id=cohort_id)
    if not user_can_access_cohort(request.user, cohort):
        raise PermissionDenied
    # ... view logic
```

### Role-Based Server Security

```python
# Server role enforcement
def get_server_role():
    """Get current server role from environment"""
    return os.environ.get('SERVER_ROLE', 'testing').lower()

def enforce_server_role(required_role):
    """Decorator to enforce server role requirements"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if get_server_role() != required_role:
                raise PermissionDenied(f"Operation requires {required_role} server")
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Example usage
@enforce_server_role('services')
def process_phi_data(data_path):
    """PHI processing only on services server"""
    # ... processing logic
```

### API Authentication

```python
# Internal API key authentication
class InternalAPIAuthentication:
    def authenticate(self, request):
        api_key = request.headers.get('X-API-Key')
        expected_key = os.environ.get('INTERNAL_API_KEY')

        if not api_key or api_key != expected_key:
            raise AuthenticationFailed('Invalid or missing API key')

        # Return internal system user
        return (InternalUser(), None)
```

## Storage Security Patterns

### Storage Manager Integration

**Location**: `depot/storage/manager.py`

```python
# Automatic server role detection
def get_scratch_storage():
    server_role = os.environ.get('SERVER_ROLE', '').lower()

    if server_role == 'web':
        # Web server MUST use remote driver (no local PHI)
        return RemoteStorageDriver()
    else:
        # Services server uses local/S3 storage
        return get_configured_storage()
```

### Remote Storage Security

```python
# Secure remote file operations
class RemoteStorageDriver:
    def __init__(self):
        self.service_url = os.environ.get('SERVICES_URL')
        self.api_key = os.environ.get('INTERNAL_API_KEY')

        # Enforce HTTPS in production
        if self.service_url.startswith('http://') and not settings.DEBUG:
            raise SecurityError("Remote storage requires HTTPS in production")

    def save(self, path, content):
        """Stream file to services server"""
        response = requests.post(
            f"{self.service_url}/internal/storage/save/",
            headers={'X-API-Key': self.api_key},
            json={
                'path': path,
                'content': base64.b64encode(content).decode(),
                'metadata': self._get_security_metadata()
            }
        )
        return response.json()

    def _get_security_metadata(self):
        """Add security context to all operations"""
        return {
            'server_hostname': socket.gethostname(),
            'server_role': os.environ.get('SERVER_ROLE'),
            'timestamp': timezone.now().isoformat(),
            'process_id': os.getpid()
        }
```

## Encryption and Transport Security

### WireGuard Configuration

**Production Setup:**
```ini
# Web server WireGuard config
[Interface]
PrivateKey = web_server_private_key
Address = 10.100.0.1/24

[Peer]
PublicKey = services_server_public_key
Endpoint = services.naaccord.internal:51820
AllowedIPs = 10.100.0.2/32
```

### Database Encryption

```python
# Encrypted database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
            'use_unicode': True,
            # Enable encryption at rest
            'ssl': {
                'ca': '/etc/ssl/certs/ca-certificates.crt',
                'cert': '/etc/ssl/certs/client-cert.pem',
                'key': '/etc/ssl/private/client-key.pem',
            }
        }
    }
}
```

## HIPAA Compliance Features

### Complete Audit Trail

```python
# Every operation tracked with full context
def track_phi_operation(action, file_path, user, cohort, **kwargs):
    """Log operation with HIPAA-required details"""
    PHIFileTracking.objects.create(
        cohort=cohort,
        user=user,
        action=action,
        file_path=file_path,
        file_size=kwargs.get('file_size'),
        file_hash=kwargs.get('file_hash'),
        server_hostname=socket.gethostname(),
        server_role=os.environ.get('SERVER_ROLE'),
        parent_process_id=os.getpid(),
        error_message=kwargs.get('error_message'),
        metadata=kwargs.get('metadata', {})
    )
```

### Data Integrity Verification

```python
# File integrity monitoring
def verify_file_integrity(file_path, expected_hash=None):
    """Verify file integrity with SHA256 hash"""
    if not os.path.exists(file_path):
        return IntegrityResult(
            is_valid=False,
            error="File does not exist"
        )

    actual_hash = calculate_sha256(file_path)

    if expected_hash and actual_hash != expected_hash:
        return IntegrityResult(
            is_valid=False,
            error="Hash mismatch - file corrupted"
        )

    return IntegrityResult(is_valid=True, hash=actual_hash)
```

### Retention and Cleanup

```python
# Mandatory cleanup verification
def verify_cleanup_completion(tracking_records):
    """Verify all temporary files cleaned up"""
    for record in tracking_records:
        if record.cleanup_required and not record.cleaned_up:
            # Check if file actually exists
            if os.path.exists(record.file_path):
                raise CleanupError(
                    f"File still exists: {record.file_path}"
                )

            # Mark as cleaned if file is gone
            record.mark_cleaned_up(user=system_user)
```

## Security Monitoring and Alerts

### Integrity Checks

```python
# Regular integrity verification
@periodic_task(run_every=timedelta(hours=24))
def daily_integrity_check():
    """Daily verification of PHI file integrity"""
    issues = []

    # Check NAS file existence
    tracking_records = PHIFileTracking.objects.filter(
        action__startswith='nas_',
        created_at__gte=timezone.now() - timedelta(days=7)
    )

    for record in tracking_records:
        if not storage.exists(record.file_path):
            issues.append(f"Missing file: {record.file_path}")

    if issues:
        send_security_alert("PHI Integrity Issues", issues)
```

### Cleanup Monitoring

```python
# Monitor overdue cleanup
@periodic_task(run_every=timedelta(hours=1))
def check_overdue_cleanup():
    """Alert on overdue temporary file cleanup"""
    overdue = PHIFileTracking.get_overdue_cleanups()

    if overdue.exists():
        send_security_alert(
            "Overdue PHI Cleanup",
            [f"{r.file_path} - {r.expected_cleanup_by}" for r in overdue]
        )
```

### Access Pattern Monitoring

```python
# Monitor unusual access patterns
def monitor_access_patterns(user, cohort, action):
    """Detect unusual access patterns"""
    recent_access = PHIFileTracking.objects.filter(
        user=user,
        cohort=cohort,
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()

    if recent_access > settings.MAX_HOURLY_ACCESS:
        send_security_alert(
            "Unusual Access Pattern",
            f"User {user.username} accessed {cohort.name} {recent_access} times in 1 hour"
        )
```

## Management Commands

### Security Administration

```bash
# View PHI audit trail
python manage.py show_phi_audit_trail --cohort 5 --days 7

# Verify PHI integrity
python manage.py verify_phi_integrity --check-hashes

# Check cleanup status
python manage.py verify_phi_cleanup

# Security health check
python manage.py security_health_check
```

### Emergency Procedures

```bash
# Emergency cleanup of all temporary files
python manage.py emergency_cleanup --force --confirm

# Verify server role configuration
python manage.py verify_server_security

# Check WireGuard tunnel status
python manage.py check_wireguard_status
```

## Development Security Guidelines

### Secure Coding Patterns

```python
# GOOD: Proper PHI handling
def process_phi_file(file_path, user, cohort):
    try:
        # Log start of processing
        PHIFileTracking.log_operation(
            action='processing_started',
            file_path=file_path,
            user=user,
            cohort=cohort
        )

        # Process file
        result = perform_analysis(file_path)

        # Log successful completion
        PHIFileTracking.log_operation(
            action='processing_completed',
            file_path=file_path,
            user=user,
            cohort=cohort
        )

        return result

    except Exception as e:
        # Log failure with error details
        PHIFileTracking.log_operation(
            action='processing_failed',
            file_path=file_path,
            user=user,
            cohort=cohort,
            error_message=str(e)
        )
        raise

# BAD: No tracking or error handling
def process_phi_file(file_path):
    return perform_analysis(file_path)  # No audit trail!
```

### Environment Security

```python
# GOOD: Validate security environment
def validate_security_environment():
    """Ensure secure configuration before processing PHI"""
    checks = [
        ('SERVER_ROLE', os.environ.get('SERVER_ROLE')),
        ('INTERNAL_API_KEY', os.environ.get('INTERNAL_API_KEY')),
        ('SERVICES_URL', os.environ.get('SERVICES_URL')),
    ]

    for key, value in checks:
        if not value:
            raise SecurityError(f"Missing required security setting: {key}")

    # Verify server role matches expected configuration
    role = os.environ.get('SERVER_ROLE').lower()
    if role not in ['web', 'services', 'testing']:
        raise SecurityError(f"Invalid server role: {role}")

    return True

# BAD: Assume environment is secure
def process_without_validation():
    # Process PHI without checking security config
    pass
```

## Testing Security Features

### Security Test Suite

**Location**: `depot/tests/test_*_security.py`

The security test suite includes 62+ tests across 8 test files covering all major security domains:

**Base Test Infrastructure:**
- `base_security.py` - SecurityTestCase base class with standardized test data setup
  - Creates test users (admin, user, viewer) with proper group assignments
  - Sets up test cohorts and cohort memberships
  - Provides data file types and protocol years
  - Ensures consistent test database state

**Security Test Files:**
1. `test_storage_path_traversal.py` - 34 tests
   - Path validation in LocalFileSystemStorage
   - Path traversal attack prevention
   - Relative path resolution checks

2. `test_sql_injection_security.py` - 10 tests
   - Django ORM parameterized query protection
   - Complex Q object query safety
   - Annotation and aggregation security

3. `test_xss_security.py` - 5 tests
   - Django template auto-escaping
   - Script tag escaping
   - Event handler attribute escaping
   - Safe filter behavior

4. `test_api_security.py` - 2 tests
   - INTERNAL_API_KEY configuration
   - SERVER_ROLE environment validation

5. `test_access_control_security.py` - 2 tests
   - CohortMembership model integrity
   - User-cohort relationship validation

6. `test_session_security.py` - 3 tests
   - SESSION_COOKIE_HTTPONLY flag
   - SESSION_COOKIE_SECURE in production
   - CSRF middleware configuration

7. `test_file_upload_security.py` - 3 tests
   - DATA_UPLOAD_MAX_MEMORY_SIZE limits
   - File extension validation
   - Path validation in storage layer

8. `test_rate_limiting_security.py` - 3 tests
   - django-axes package availability
   - AXES_FAILURE_LIMIT configuration
   - AXES_COOLOFF_TIME settings

### Running Security Tests

```bash
# Run all security tests (62 tests)
python manage.py test depot.tests.test_storage_path_traversal \
    depot.tests.test_sql_injection_security \
    depot.tests.test_xss_security \
    depot.tests.test_api_security \
    depot.tests.test_access_control_security \
    depot.tests.test_session_security \
    depot.tests.test_file_upload_security \
    depot.tests.test_rate_limiting_security \
    --parallel 4

# Run specific security domain
python manage.py test depot.tests.test_api_security -v 2
python manage.py test depot.tests.test_access_control_security -v 2

# Quick smoke test (13 configuration tests)
python manage.py test depot.tests.test_api_security \
    depot.tests.test_access_control_security \
    depot.tests.test_session_security \
    depot.tests.test_file_upload_security \
    depot.tests.test_rate_limiting_security
```

### Security Test Patterns

```python
# Base test class with proper setup
class SecurityTestCase(TestCase):
    """Base class for all security tests."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests."""
        # Create users, cohorts, groups automatically
        cls.admin = User.objects.create_user(...)
        cls.user = User.objects.create_user(...)
        cls.cohort_a = Cohort.objects.create(...)
        CohortMembership.objects.create(user=cls.user, cohort=cls.cohort_a)

# Example: Cohort access control test
class CohortAccessControlTest(SecurityTestCase):
    def test_user_has_cohort_membership(self):
        """Users should have cohort memberships."""
        memberships = CohortMembership.objects.filter(user=self.user)
        self.assertGreater(memberships.count(), 0)

# Example: API authentication test
class InternalAPIAuthenticationTest(SecurityTestCase):
    def test_api_key_configuration_exists(self):
        """INTERNAL_API_KEY setting should be configurable."""
        import os
        api_key = os.environ.get('INTERNAL_API_KEY', '')
        self.assertTrue(isinstance(api_key, str))

# Example: PHI tracking test
def test_phi_tracking_creation(self):
    """Test PHI tracking record creation"""
    PHIFileTracking.log_operation(
        cohort=self.cohort_a,
        user=self.user,
        action='nas_raw_created',
        file_path='/test/path/file.csv'
    )

    # Verify record created with correct details
    tracking = PHIFileTracking.objects.get(file_path='/test/path/file.csv')
    self.assertEqual(tracking.user, self.user)
    self.assertEqual(tracking.cohort, self.cohort_a)
    self.assertEqual(tracking.action, 'nas_raw_created')
```

## Related Documentation
- [PHI File Tracking System](../../docs/security/PHIFileTracking-system.md)
- [Storage Manager Abstraction](../../docs/technical/storage-manager-abstraction.md)
- [Production Deployment](../../docs/deployment/production-deployment.md)
- [Security Architecture Overview](../../docs/security/security-overview.md)
- [Storage Domain](../storage/CLAUDE.md)
- [Audit Domain](../audit/CLAUDE.md)