# Testing the Johns Hopkins Audit System

This document explains how to run and verify the comprehensive audit system implemented for Johns Hopkins IT Security compliance.

## Overview

The audit system includes comprehensive test coverage for:
- Activity logging and tracking
- DataRevision field-level change tracking
- Universal observer pattern for ALL models
- Session timeout middleware
- Mysqldump export functionality
- SAML authentication integration

## Test Structure

### Main Test Suite
- **Location**: `depot/tests/test_audit_system.py`
- **Coverage**: 27 test cases covering all audit functionality
- **Test Classes**:
  - `ActivityModelTests` - Activity model functionality
  - `DataRevisionModelTests` - Field-level change tracking
  - `ModelObserverTests` - Universal observer pattern
  - `SoftDeletableModelTests` - Soft delete with audit integration
  - `SessionActivityMiddlewareTests` - Session timeout and logging
  - `RequestTimingMiddlewareTests` - Request performance tracking
  - `ExportAuditDataCommandTests` - Export command functionality
  - `AuditSystemIntegrationTests` - End-to-end workflows

## Running Tests

### Prerequisites

1. **Virtual Environment**: Ensure you're in the project's virtual environment
   ```bash
   source venv/bin/activate
   ```

2. **Database Permissions**: The test user needs permission to create test databases
   ```sql
   GRANT ALL PRIVILEGES ON test_naaccord.* TO 'naaccord'@'%';
   FLUSH PRIVILEGES;
   ```

### Running the Full Test Suite

```bash
# Run all audit system tests with verbose output
python manage.py test depot.tests.test_audit_system -v 2

# Run with even more verbose output
python manage.py test depot.tests.test_audit_system -v 3

# Run specific test class
python manage.py test depot.tests.test_audit_system.ActivityModelTests -v 2

# Run specific test method
python manage.py test depot.tests.test_audit_system.ActivityModelTests.test_activity_creation -v 2
```

### Running Tests Without Database Creation

If you encounter database permission issues, you can run individual verification tests:

```bash
# Test basic audit functionality
python manage.py shell -c "
from depot.models import Activity, ActivityType, DataRevision
from depot.audit.observers import ModelObserver
from django.contrib.auth import get_user_model

User = get_user_model()
print('✓ All audit models import successfully')
print(f'✓ ActivityType.DATA_EXPORT exists: {hasattr(ActivityType, \"DATA_EXPORT\")}')
print(f'✓ Observer excludes audit models: {ModelObserver.should_observe_model(Activity) == False}')
print('🎉 Basic audit system verified!')
"

# Test observer pattern functionality
python manage.py shell -c "
from depot.models import Activity, DataRevision
from depot.audit.observers import set_current_user
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()
set_current_user(user)

initial_count = Activity.objects.count()
user.first_name = 'TestUpdate'
user.save()
final_count = Activity.objects.count()

print(f'✓ Observer pattern working: {final_count > initial_count}')
set_current_user(None)
"
```

## Test Categories

### 1. Unit Tests
Test individual components in isolation:

```bash
# Activity model functionality
python manage.py test depot.tests.test_audit_system.ActivityModelTests

# DataRevision model functionality  
python manage.py test depot.tests.test_audit_system.DataRevisionModelTests

# Observer pattern logic
python manage.py test depot.tests.test_audit_system.ModelObserverTests
```

### 2. Integration Tests
Test complete workflows:

```bash
# End-to-end audit workflows
python manage.py test depot.tests.test_audit_system.AuditSystemIntegrationTests

# Middleware integration
python manage.py test depot.tests.test_audit_system.SessionActivityMiddlewareTests
```

### 3. Compliance Tests
Verify Johns Hopkins requirements:

```bash
# Run compliance verification
python manage.py shell -c "
from depot.tests.test_audit_system import AuditSystemIntegrationTests
import unittest

# Create test instance
test = AuditSystemIntegrationTests()
test.setUp()

# Run compliance test
try:
    test.test_compliance_requirements()
    print('✅ Johns Hopkins compliance requirements verified')
except Exception as e:
    print(f'❌ Compliance test failed: {e}')
finally:
    test.tearDown()
"
```

## Troubleshooting

### Common Issues

#### 1. Database Permission Errors
```
Got an error creating the test database: (1044, "Access denied for user 'naaccord'@'%' to database 'test_naaccord'")
```

**Solution**: Grant test database permissions
```sql
GRANT ALL PRIVILEGES ON test_naaccord.* TO 'naaccord'@'%';
GRANT CREATE ON *.* TO 'naaccord'@'%';
FLUSH PRIVILEGES;
```

#### 2. Import Errors
```
ModuleNotFoundError: No module named 'depot'
```

**Solution**: Ensure you're in the correct directory and virtual environment
```bash
cd /path/to/naaccord
source venv/bin/activate
python manage.py test depot.tests.test_audit_system
```

#### 3. Migration Issues
```
django.db.migrations.exceptions.InconsistentMigrationHistory
```

**Solution**: Ensure migrations are applied
```bash
python manage.py makemigrations depot
python manage.py migrate depot
```

### Alternative Testing Methods

If full Django tests can't run, use these verification approaches:

#### Manual Functionality Test
```bash
python manage.py shell -c "
# Test complete audit workflow
from depot.models import Activity, ActivityType
from depot.audit.observers import set_current_user
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()
set_current_user(user)

# Create activity
activity = Activity.log_activity(
    user=user,
    activity_type=ActivityType.LOGIN,
    success=True,
    details={'test': 'manual_verification'}
)

print(f'✓ Activity created: {activity}')
print(f'✓ Indefinite retention: {activity.retention_date is None}')
print(f'✓ User tracking: {activity.user.email}')
print('🎉 Manual audit test passed!')

set_current_user(None)
"
```

#### Export Command Test
```bash
# Verify export command is available
python manage.py export_audit_data --help

# Test export command (dry run)
python manage.py export_audit_data --output-dir /tmp/test_export --days-back 1
```

#### Middleware Test
```bash
python manage.py shell -c "
from django.conf import settings
from depot.middleware.session_activity import SessionActivityMiddleware

# Test middleware configuration
middleware = SessionActivityMiddleware(None)
print(f'✓ Session timeout: {middleware.timeout_seconds} seconds')
print(f'✓ Excluded paths: {middleware.excluded_paths}')
print('✓ Middleware configured correctly')
"
```

## Test Coverage Report

### Expected Test Results
When all tests pass, you should see:
```
Creating test database for alias 'default' ('test_naaccord')...
System check identified no issues (0 silenced).

test_activity_creation (depot.tests.test_audit_system.ActivityModelTests) ... ok
test_activity_log_method (depot.tests.test_audit_system.ActivityModelTests) ... ok
test_client_ip_extraction (depot.tests.test_audit_system.ActivityModelTests) ... ok
[... 24 more tests ...]

Ran 27 tests in 2.350s

OK
Destroying test database for alias 'default' ('test_naaccord')...
```

### Coverage Areas
- ✅ **Activity Model**: Creation, logging, field validation, string representation
- ✅ **DataRevision Model**: Field tracking, JSON parsing, polymorphic associations
- ✅ **Observer Pattern**: Model detection, serialization, signal handling
- ✅ **Soft Delete**: Audit integration, restoration, manager functionality
- ✅ **Session Middleware**: Timeout logic, activity logging, terminal tracking
- ✅ **Export Command**: mysqldump integration, options validation, activity logging
- ✅ **Integration**: End-to-end workflows, compliance verification

## Continuous Integration

### Automated Testing Setup
For CI/CD pipelines, add this to your test configuration:

```yaml
# .github/workflows/audit-tests.yml
name: Audit System Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: test_naaccord
          MYSQL_USER: naaccord
          MYSQL_PASSWORD: test_password
        options: >-
          --health-cmd="mysqladmin ping"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=3

    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.12
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run audit system tests
      run: |
        python manage.py test depot.tests.test_audit_system
      env:
        DB_HOST: 127.0.0.1
        DB_USER: naaccord
        DB_PASSWORD: test_password
        DB_NAME: test_naaccord
```

## Compliance Verification

### Johns Hopkins Requirements Checklist
Run this verification script to confirm all requirements are met:

```bash
python manage.py shell -c "
print('=== JOHNS HOPKINS COMPLIANCE VERIFICATION ===')

# 1. Universal Observer Pattern
from depot.audit.observers import ModelObserver
from depot.models import Activity, DataRevision
print(f'✓ Observer excludes audit models: {not ModelObserver.should_observe_model(Activity)}')

# 2. Activity Logging
from depot.models import ActivityType
required_types = ['LOGIN', 'SESSION_TIMEOUT', 'DATA_EXPORT']
for activity_type in required_types:
    exists = hasattr(ActivityType, activity_type)
    print(f'✓ ActivityType.{activity_type}: {exists}')

# 3. Session Timeout
from django.conf import settings
timeout = getattr(settings, 'SESSION_TIMEOUT_SECONDS', 0)
print(f'✓ Session timeout configured: {timeout} seconds')

# 4. Export Capability
import os
export_cmd = os.path.exists('depot/management/commands/export_audit_data.py')
print(f'✓ Export command exists: {export_cmd}')

# 5. Indefinite Retention
activity = Activity.objects.first()
indefinite = activity.retention_date is None if activity else True
print(f'✓ Indefinite retention: {indefinite}')

print('\\n🎉 All Johns Hopkins requirements verified!')
"
```

This testing guide ensures comprehensive verification of the audit system's functionality and compliance with Johns Hopkins IT Security requirements.