# NA-ACCORD Data Depot Administrator Guide

**Version 1.0 | Last Updated: October 2025**

## Table of Contents

1. [Introduction](#introduction)
2. [Access Control System](#access-control-system)
3. [User Management](#user-management)
4. [Cohort Administration](#cohort-administration)
5. [Permission System](#permission-system)
6. [SAML Integration](#saml-integration)
7. [Monitoring User Activity](#monitoring-user-activity)
8. [Security Administration](#security-administration)
9. [Troubleshooting Access Issues](#troubleshooting-access-issues)
10. [Best Practices](#best-practices)

---

## Introduction

### Purpose of This Guide

This guide is for system administrators responsible for managing user access, permissions, and security in the NA-ACCORD Data Depot. You'll learn how to:
- Manage users and their access levels
- Configure cohort assignments
- Set up and maintain permission groups
- Integrate with institutional SSO
- Monitor and audit user activity
- Troubleshoot access issues

### Administrator Roles

**Site Administrator**:
- Full system access
- Manage all users and cohorts
- Configure authentication
- Audit system activity
- Manage permissions and roles

**Cohort Manager** (delegated admin):
- Manage users within assigned cohorts
- Review submissions for their cohorts
- Cannot modify system-wide settings

---

## Access Control System

### Architecture Overview

NA-ACCORD Data Depot is built on Django, a Python web framework. The Depot App uses a **multi-layered access control system**:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Authentication Layer                          │
│  (External Auth (SSO) → Depot App User → Cohort Membership)     │
└─────────────────────┬───────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────┐
│                Authorization Layers                     │
│                                                         │
│  Layer 1: Cohort Groups (Role-Based Access)             │
│  ├─ Site Administrator                                  │
│  ├─ Cohort Manager                                      │
│  ├─ Cohort User                                         │
│  └─ Read Only                                           │
│                                                         │
│  Layer 2: Cohort Membership (Data Access)               │
│  ├─ User ↔ Cohort Association                           │
│  └─ Determines visible data                             │
│                                                         │
│  Layer 3: Depot App Permissions (Feature Access)        │
│  ├─ View permissions                                    │
│  ├─ Add permissions                                     │
│  ├─ Change permissions                                  │
│  └─ Delete permissions                                  │
└─────────────────────────────────────────────────────────┘
```

### Access Control Principles

1. **Authentication First**: Users must authenticate via SAML SSO
2. **Role-Based Access**: Users assigned to Cohort Groups
3. **Cohort Isolation**: Users only see data from assigned cohorts
4. **Least Privilege**: Users granted minimum necessary permissions
5. **Audit Trail**: All access and operations logged

### How Access Control Works

When a user logs in:

1. **SAML/SSO Authentication** validates identity with institution
2. **User Record** created/updated in Depot App
3. **Cohort Group Assignment** determines base permissions
4. **Cohort Membership** determines visible data
5. **View Access Checks** enforce cohort isolation

Example:
```python
# User: john@institution.edu
# Group: Cohort User
# Cohort: VACS / VACS8
#
# Can:
#   ✓ Upload files for VACS cohort
#   ✓ View VACS submissions and reports
#   ✓ Download VACS audit reports
# Cannot:
#   ✗ Access other cohorts' data
#   ✗ Manage users or system settings
#   ✗ View all submissions
```

---

## User Management

### User Lifecycle

```
Registration → Group Assignment → Cohort Assignment → Active Use → Deactivation
```

### Adding New Users

Users are automatically created on first SAML login, but you must configure their access:

#### Method 1: Depot Admin Interface

1. **Navigate to Depot Admin**
   - URL: `https://na-accord-depot.publichealth.jhu.edu/admin`
   - Login with superuser credentials

2. **Locate User**
   - Go to "Users" under Authentication
   - Search by email or name
   - User should exist if they've logged in once

3. **Assign to Cohort Groups**
   - Edit user record
   - Scroll to "Groups" section
   - Select appropriate Cohort Group:
     - **Site Administrator**: Full system access
     - **Cohort Manager**: Cohort-level administration
     - **Cohort User**: Upload and view own cohort data
     - **Read Only**: View-only access
   - Save changes

4. **Assign to Cohorts**
   - Go to "Cohort memberships"
   - Click "Add cohort membership"
   - Select user, cohort, and membership type
   - Save

#### Method 2: Depot App Shell (Bulk Operations)

```python
# Access Depot App shell
docker exec -it naaccord-services python manage.py shell

# Import necessary models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.models import Cohort, CohortMembership

User = get_user_model()

# Find user by email
user = User.objects.get(email='john@institution.edu')

# Assign to Cohort Group
cohort_user_group = Group.objects.get(name='Cohort User')
user.groups.add(cohort_user_group)

# Assign to cohort
vacs_cohort = Cohort.objects.get(acronym='VACS')
CohortMembership.objects.create(
    user=user,
    cohort=vacs_cohort,
    membership_type='member'
)

# Save changes
user.save()

print(f"User {user.email} assigned to {vacs_cohort.name}")
```

#### Method 3: Management Command (Bulk Import)

```bash
# Create CSV file with user assignments
# Format: email,group,cohort_acronym
# Example:
# john@institution.edu,Cohort User,VACS
# jane@institution.edu,Cohort Manager,MACS
# admin@institution.edu,Site Administrator,ALL

# Import users
docker exec naaccord-services python manage.py import_user_assignments users.csv
```

### User Groups Explained

#### Site Administrator
**Purpose**: Full system administration

**Permissions**:
- View all cohorts and data
- Manage all users and permissions
- Configure system settings
- Access Depot admin interface
- Review all submissions
- Manage data definitions

**Use Cases**:
- System administrators
- Data center staff
- Primary support contacts

**Assignment**: Only assign to trusted staff

#### Cohort Manager
**Purpose**: Manage specific cohort operations

**Permissions**:
- View assigned cohort data
- Manage users within assigned cohorts
- Approve/reject cohort submissions
- Upload data for assigned cohorts
- View cohort audit reports
- Cannot access other cohorts

**Use Cases**:
- Lead data managers at cohort sites
- Principal investigators
- Cohort coordinators

**Assignment**: One or more per cohort

#### Cohort User
**Purpose**: Regular data submission and access

**Permissions**:
- Upload data for assigned cohorts
- View own submissions and reports
- Download audit reports for assigned cohorts
- Cannot manage users
- Cannot access other cohorts

**Use Cases**:
- Data managers
- Research coordinators
- Data entry staff

**Assignment**: Most common user type

#### Read Only
**Purpose**: View-only access for oversight

**Permissions**:
- View data for assigned cohorts
- Download reports
- Cannot upload files
- Cannot modify any data

**Use Cases**:
- Auditors
- QA reviewers
- Oversight personnel

**Assignment**: For non-submitting users

### Modifying User Access

#### Change User Group

```python
# Depot App shell
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()
user = User.objects.get(email='john@institution.edu')

# Remove from current groups
user.groups.clear()

# Add to new group
new_group = Group.objects.get(name='Cohort Manager')
user.groups.add(new_group)
user.save()
```

#### Add/Remove Cohort Access

```python
# Add cohort access
from depot.models import Cohort, CohortMembership

user = User.objects.get(email='john@institution.edu')
cohort = Cohort.objects.get(acronym='MACS')

CohortMembership.objects.create(
    user=user,
    cohort=cohort,
    membership_type='member'
)

# Remove cohort access
CohortMembership.objects.filter(
    user=user,
    cohort=cohort
).delete()
```

### Deactivating Users

When users leave or no longer need access:

```python
# Depot App shell
user = User.objects.get(email='john@institution.edu')

# Option 1: Deactivate (preserves audit trail)
user.is_active = False
user.save()
# User cannot login, but records remain

# Option 2: Remove all access
user.groups.clear()
CohortMembership.objects.filter(user=user).delete()
# User can login but sees nothing
```

**Best Practice**: Deactivate rather than delete to preserve audit trail.

---

## Cohort Administration

### Understanding Cohorts

A **cohort** represents a research site or study group in NA-ACCORD. Each cohort:
- Has independent data submissions
- Has its own set of authorized users
- Is isolated from other cohorts' data
- May have custom data definitions

### Cohort Model

```python
class Cohort(models.Model):
    name = "Full Name"          # e.g., "Veterans Aging Cohort Study"
    acronym = "SHORT"           # e.g., "VACS"
    description = "Details"     # Purpose and scope
    is_active = True/False      # Whether accepting submissions
    created_at = datetime       # When added to system
```

### Creating New Cohorts

#### Django Admin Method

1. **Navigate to Cohorts**
   - Django Admin → Depot → Cohorts
   - Click "Add Cohort"

2. **Enter Cohort Details**
   ```
   Name: Veterans Aging Cohort Study
   Acronym: VACS
   Description: Multi-site cohort studying HIV and aging
   Is Active: ✓ (checked)
   ```

3. **Save Cohort**

#### Django Shell Method

```python
from depot.models import Cohort

cohort = Cohort.objects.create(
    name='Veterans Aging Cohort Study',
    acronym='VACS',
    description='Multi-site cohort studying HIV and aging',
    is_active=True
)

print(f"Created cohort: {cohort.name} ({cohort.acronym})")
```

### Assigning Users to Cohorts

#### CohortMembership Model

```python
class CohortMembership(models.Model):
    user = ForeignKey(User)           # Which user
    cohort = ForeignKey(Cohort)       # Which cohort
    membership_type = 'member'        # Membership type
    joined_at = datetime              # When assigned
```

#### Membership Types

- **member**: Standard cohort access (most common)
- **manager**: Cohort-level admin rights (if also in Cohort Manager group)
- **observer**: Read-only cohort access (if also in Read Only group)

#### Assignment Example

```python
from depot.models import CohortMembership

# Assign user to cohort
CohortMembership.objects.create(
    user=user,
    cohort=cohort,
    membership_type='member'
)

# Check user's cohorts
user_cohorts = CohortMembership.objects.filter(user=user)
for membership in user_cohorts:
    print(f"{user.email} → {membership.cohort.acronym}")
```

### Managing Cohort Settings

#### Enable/Disable Submissions

```python
# Disable submissions for a cohort
cohort = Cohort.objects.get(acronym='VACS')
cohort.is_active = False
cohort.save()

# Users will see: "This cohort is not currently accepting submissions"
```

#### View Cohort Statistics

```bash
# Management command
docker exec naaccord-services python manage.py cohort_stats --cohort VACS

# Output:
# Cohort: Veterans Aging Cohort Study (VACS)
# Users: 12
# Submissions: 45
# Files Uploaded: 234
# Last Activity: 2025-10-08
```

---

## Permission System

### Depot App Permissions Overview

The Depot App is built on Django and uses its built-in permission system plus custom permissions:

### Standard Model Permissions

For each model, Django creates 4 permissions:
- `add_<model>`: Can create new records
- `change_<model>`: Can modify existing records
- `view_<model>`: Can view records
- `delete_<model>`: Can delete records

Example for Audit model:
- `depot.add_audit`
- `depot.change_audit`
- `depot.view_audit`
- `depot.delete_audit`

### Custom Permissions

NA-ACCORD defines additional permissions:

```python
class Audit(models.Model):
    class Meta:
        permissions = [
            ("manage_cohort_audits", "Can manage audits for assigned cohorts"),
            ("view_all_audits", "Can view audits from all cohorts"),
            ("approve_submissions", "Can approve cohort submissions"),
        ]
```

### Permission Groups

Permission groups bundle permissions for common roles:

#### Site Administrator Group Permissions

```python
# All permissions for all models
# Key permissions:
- auth.* (all user/group management)
- depot.* (all model access)
- Can manage cohorts
- Can view all data
- Can approve submissions
```

#### Cohort Manager Group Permissions

```python
# Cohort-scoped permissions:
- depot.view_audit (for assigned cohorts only)
- depot.add_audit
- depot.change_audit
- depot.manage_cohort_audits
- depot.approve_submissions (for assigned cohorts)
- depot.view_cohortsubmission
- depot.change_cohortsubmission
```

#### Cohort User Group Permissions

```python
# Basic user permissions:
- depot.view_audit (own submissions only)
- depot.add_audit (own cohorts only)
- depot.view_cohortsubmission (own submissions)
- depot.add_cohortsubmission (own cohorts)
```

#### Read Only Group Permissions

```python
# View-only permissions:
- depot.view_audit (assigned cohorts)
- depot.view_cohortsubmission (assigned cohorts)
- depot.view_notebook
```

### Configuring Permission Groups

#### Using Management Command

```bash
# Setup default permission groups
docker exec naaccord-services python manage.py setup_permission_groups

# This creates all 4 groups with standard permissions
```

#### Manual Configuration

```python
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

# Create group
cohort_manager = Group.objects.create(name='Cohort Manager')

# Get specific permissions
audit_ct = ContentType.objects.get(app_label='depot', model='audit')
view_audit = Permission.objects.get(
    content_type=audit_ct,
    codename='view_audit'
)
add_audit = Permission.objects.get(
    content_type=audit_ct,
    codename='add_audit'
)

# Assign permissions to group
cohort_manager.permissions.add(view_audit, add_audit)
```

### Custom Permission Checks

In views, permissions are checked programmatically:

```python
@login_required
def view_audit_report(request, audit_id):
    audit = get_object_or_404(Audit, id=audit_id)

    # Check 1: User has view_audit permission
    if not request.user.has_perm('depot.view_audit'):
        return HttpResponseForbidden()

    # Check 2: User has access to this cohort
    if not request.user.is_staff:  # Not site admin
        user_cohorts = [m.cohort for m in request.user.cohortmembership_set.all()]
        if audit.cohort not in user_cohorts:
            return HttpResponseForbidden()

    # Authorized - show report
    return render(request, 'audit_report.html', {'audit': audit})
```

---

## SAML Integration

### Overview

NA-ACCORD uses SAML (Security Assertion Markup Language) for Single Sign-On authentication with institutional identity providers.

### SAML Components

```
┌─────────────────────────────────────────────────────┐
│           User's Institution (IdP)                  │
│  ┌────────────────────────────────────────┐        │
│  │   Shibboleth / SAML Identity Provider  │        │
│  └────────────────┬───────────────────────┘        │
└───────────────────┼─────────────────────────────────┘
                    │
                    │ SAML Assertions
                    │ (Encrypted)
                    ▼
┌─────────────────────────────────────────────────────┐
│         NA-ACCORD Data Depot (SP)                   │
│  ┌────────────────────────────────────────┐        │
│  │   Django + django-saml2-auth           │        │
│  │   Receives assertions                   │        │
│  │   Creates/updates user records          │        │
│  └────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### SAML Configuration

#### Required Settings

In `depot/settings.py` or environment variables:

```python
# SAML Settings
SAML_ENTITY_ID = 'https://your-domain.com'
SAML_ACS_URL = 'https://your-domain.com/saml2/acs/'

# Identity Provider Metadata
SAML_METADATA_AUTO_CONF_URL = 'https://idp.institution.edu/idp/shibboleth'

# Or load from file:
SAML_IDP_METADATA_FILE = '/opt/naaccord/depot/idp_metadata.xml'

# Attribute mapping
SAML_ATTRIBUTE_MAPPING = {
    'email': ('email', 'mail'),
    'first_name': ('givenName',),
    'last_name': ('sn',),
    'groups': ('isMemberOf',),  # Optional group mapping
}
```

#### Obtaining IdP Metadata

Each institution's SAML IdP provides metadata XML:

**Johns Hopkins Example:**
```bash
# Download metadata
wget https://idp.jh.edu/idp/shibboleth -O idp_metadata.xml

# Store securely (use Ansible vault in production)
ansible-vault encrypt idp_metadata.xml
```

**Generic Process:**
1. Contact your institution's IT department
2. Request "SAML IdP metadata XML"
3. They may need your SP information (see next section)
4. Save metadata to secure location

#### Registering SP with IdP

Your institution needs information about NA-ACCORD:

**Provide to Institution IT:**
```
Service Provider (SP) Information
==================================
Entity ID: https://your-domain.com
ACS URL: https://your-domain.com/saml2/acs/
Metadata URL: https://your-domain.com/saml2/metadata/

Required Attributes:
- email (required)
- givenName (required)
- sn (required)
- isMemberOf (optional, for group mapping)
```

### SAML User Workflow

1. **User visits**: `https://your-domain.com/sign-in`
2. **Clicks "Sign In"**: Redirected to institution IdP
3. **Authenticates**: With institutional credentials
4. **SAML Assertion**: IdP sends encrypted assertion to SP (ACS URL)
5. **User Created/Updated**: Django creates or updates user record
6. **Session Established**: User logged in, redirected to dashboard

### SAML Group Mapping (Optional)

If your IdP provides group information, you can auto-assign users to groups:

```python
# In settings.py
SAML_AUTO_GROUP_MAPPING = {
    'CN=naaccord-admins,OU=Groups,DC=institution,DC=edu': 'Site Administrator',
    'CN=naaccord-managers,OU=Groups,DC=institution,DC=edu': 'Cohort Manager',
    'CN=naaccord-users,OU=Groups,DC=institution,DC=edu': 'Cohort User',
}
```

When user logs in with `isMemberOf` containing `CN=naaccord-admins...`, they're automatically added to "Site Administrator" group.

### Testing SAML Authentication

```bash
# 1. Check metadata endpoint
curl https://your-domain.com/saml2/metadata/

# Should return XML with SP configuration

# 2. Test login flow
# Visit: https://your-domain.com/saml2/login/
# Should redirect to IdP

# 3. Check Django logs
docker logs naaccord-web --tail 100 | grep -i saml

# 4. Verify user creation
docker exec naaccord-services python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(email='test@institution.edu')
```

### Troubleshooting SAML Issues

#### "SAML Authentication Failed"

**Check IdP metadata:**
```bash
# Verify metadata is accessible
curl https://idp.institution.edu/idp/shibboleth

# Check Django SAML config
docker exec naaccord-web python manage.py shell
>>> from django.conf import settings
>>> print(settings.SAML_METADATA_AUTO_CONF_URL)
```

#### "Attribute mapping error"

**Verify attribute names:**
```python
# Check what attributes IdP is sending
# Enable SAML debug logging in settings.py:
LOGGING = {
    'loggers': {
        'djangosaml2': {
            'level': 'DEBUG',
        }
    }
}

# Check logs for received attributes
docker logs naaccord-web | grep -i "received attributes"
```

#### "User created but no access"

User successfully logged in but sees no cohorts:

```python
# User created but not assigned to groups/cohorts
# Assign manually:
user = User.objects.get(email='user@institution.edu')
group = Group.objects.get(name='Cohort User')
user.groups.add(group)

cohort = Cohort.objects.get(acronym='VACS')
CohortMembership.objects.create(user=user, cohort=cohort)
```

---

## Monitoring User Activity

### Audit Trail System

NA-ACCORD maintains comprehensive audit logs for HIPAA compliance.

### PHI File Tracking

Every file operation is logged:

```bash
# View complete audit trail for a cohort
docker exec naaccord-services python manage.py show_phi_audit_trail \
  --cohort VACS \
  --days 7

# Output:
# Cohort: VACS
# Date Range: 2025-10-03 to 2025-10-10
# Total Operations: 234
#
# Recent Operations:
# 2025-10-10 14:23:01 | john@institution.edu | file_uploaded_via_stream | patient_data.csv
# 2025-10-10 14:23:15 | john@institution.edu | nas_raw_created | /mnt/nas/submissions/...
# 2025-10-10 14:23:45 | john@institution.edu | duckdb_created | /opt/naaccord/storage/...
```

### User Activity Reports

```bash
# Show recent uploads by user
docker exec naaccord-services python manage.py show_user_activity \
  --user john@institution.edu \
  --days 30

# Show failed upload attempts
docker exec naaccord-services python manage.py show_failed_uploads \
  --days 7

# List inactive users
docker exec naaccord-services python manage.py list_inactive_users \
  --days 90
```

### Login Activity

Django logs all authentication attempts:

```bash
# View login activity
docker exec naaccord-services python manage.py shell

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model

User = get_user_model()

# Get user login history (via admin log entries)
user = User.objects.get(email='john@institution.edu')
logins = LogEntry.objects.filter(user=user).order_by('-action_time')[:20]

for entry in logins:
    print(f"{entry.action_time} | {entry.get_action_flag_display()} | {entry}")
```

### Download Activity

```bash
# Track report downloads
docker exec naaccord-services python manage.py show_download_activity \
  --cohort VACS \
  --days 30

# Output shows:
# - Who downloaded reports
# - When they were downloaded
# - Which reports were accessed
```

### Compliance Reports

```bash
# Generate HIPAA compliance report
docker exec naaccord-services python manage.py generate_compliance_report \
  --cohort VACS \
  --month 2025-10 \
  --output /opt/naaccord/reports/compliance_vacs_202510.pdf

# Includes:
# - All user access events
# - File operations
# - Authentication logs
# - Failed access attempts
```

---

## Security Administration

### Security Best Practices

1. **Strong Authentication**
   - Always use SAML SSO
   - Never allow local password authentication for regular users
   - Only use Depot admin passwords for emergency access

2. **Least Privilege**
   - Grant minimum necessary permissions
   - Regularly review user access
   - Remove access when users leave

3. **Audit Everything**
   - Enable comprehensive logging
   - Regularly review audit trails
   - Investigate suspicious activity

4. **Protect Credentials**
   - Store sensitive settings in environment variables
   - Use Ansible Vault for configuration secrets
   - Rotate API keys regularly

5. **Regular Reviews**
   - Monthly user access review
   - Quarterly security audit
   - Annual compliance assessment

### API Key Management

For server-to-server communication:

```bash
# Generate new API key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update in both servers' .env files:
INTERNAL_API_KEY=<new-key>

# Restart services
docker compose restart
```

### Password Policy (Depot Admin)

For Depot admin accounts only:

```python
# In settings.py
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
```

### Session Security

```python
# In settings.py
SESSION_COOKIE_SECURE = True  # HTTPS only
SESSION_COOKIE_HTTPONLY = True  # No JavaScript access
SESSION_COOKIE_SAMESITE = 'Strict'  # CSRF protection
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = 14400  # 4 hours
```

### Failed Login Monitoring

```bash
# Check for failed login attempts
docker logs naaccord-web | grep -i "authentication failed"

# Look for patterns (potential brute force)
docker logs naaccord-web | grep -i "authentication failed" | \
  awk '{print $NF}' | sort | uniq -c | sort -nr
```

---

## Troubleshooting Access Issues

### Common Problems

#### User Can't See Any Cohorts

**Symptoms**: User logs in successfully but sees empty dashboard

**Diagnosis**:
```python
docker exec naaccord-services python manage.py shell

from django.contrib.auth import get_user_model
from depot.models import CohortMembership

User = get_user_model()
user = User.objects.get(email='user@institution.edu')

# Check group membership
print("Groups:", user.groups.all())

# Check cohort membership
memberships = CohortMembership.objects.filter(user=user)
print("Cohorts:", memberships)
```

**Resolution**:
```python
# Assign to group
from django.contrib.auth.models import Group
group = Group.objects.get(name='Cohort User')
user.groups.add(group)

# Assign to cohort
from depot.models import Cohort, CohortMembership
cohort = Cohort.objects.get(acronym='VACS')
CohortMembership.objects.create(user=user, cohort=cohort)
```

#### User Can't Upload Files

**Symptoms**: User sees cohort but upload button disabled or fails

**Diagnosis**:
```python
# Check permissions
user.has_perm('depot.add_audit')  # Should be True
user.groups.all()  # Should include Cohort User or higher
```

**Resolution**:
```python
# Verify group has add_audit permission
from django.contrib.auth.models import Group
group = Group.objects.get(name='Cohort User')
print(group.permissions.filter(codename='add_audit'))

# If missing, run:
# docker exec naaccord-services python manage.py setup_permission_groups
```

#### SAML Login Fails

**Symptoms**: Redirect to IdP works but returns to error page

**Diagnosis**:
```bash
# Check SAML logs
docker logs naaccord-web | grep -i saml | tail -50

# Common issues:
# - Metadata URL unreachable
# - Attribute mapping mismatch
# - SP not registered with IdP
```

**Resolution**:
1. Verify IdP metadata accessible
2. Check attribute mapping in settings
3. Confirm SP registered with institution
4. Test with SAML debug logging enabled

#### User Sees Wrong Cohort Data

**Symptoms**: User sees data from cohorts they shouldn't access

**Diagnosis**:
```python
# Check cohort memberships
memberships = CohortMembership.objects.filter(user=user)
for m in memberships:
    print(f"Cohort: {m.cohort.acronym}, Type: {m.membership_type}")

# Check if user is site admin (sees all cohorts)
print(f"Is staff: {user.is_staff}")
print(f"Is superuser: {user.is_superuser}")
```

**Resolution**:
```python
# Remove incorrect cohort access
CohortMembership.objects.filter(
    user=user,
    cohort__acronym='WRONG_COHORT'
).delete()

# If user is accidentally marked as staff/superuser:
user.is_staff = False
user.is_superuser = False
user.save()
```

---

## Best Practices

### User Onboarding Checklist

When adding new users:

- [ ] User has institutional email address
- [ ] User registered with SAML (first login completed)
- [ ] User assigned to appropriate group
- [ ] User assigned to correct cohort(s)
- [ ] User permissions verified
- [ ] User trained on system usage
- [ ] User contact information documented

### Regular Maintenance Tasks

**Weekly:**
- [ ] Review recent user registrations
- [ ] Check for failed upload attempts
- [ ] Verify no permission errors in logs

**Monthly:**
- [ ] Review user access list
- [ ] Check for inactive users
- [ ] Audit cohort memberships
- [ ] Review failed login attempts

**Quarterly:**
- [ ] Complete access review for all users
- [ ] Verify all users still need access
- [ ] Update user roles if responsibilities changed
- [ ] Generate compliance reports

**Annually:**
- [ ] Full security audit
- [ ] Review all system administrator accounts
- [ ] Update security documentation
- [ ] Compliance training for all users

### Security Checklists

**New Cohort Onboarding:**
- [ ] Cohort created in system
- [ ] Data definitions configured
- [ ] Users identified and approved
- [ ] Users assigned to cohort
- [ ] Test upload completed
- [ ] Audit report reviewed
- [ ] Training provided

**User Access Review:**
- [ ] List all active users
- [ ] Verify current employment
- [ ] Check access levels appropriate
- [ ] Remove access for departed users
- [ ] Document review completion

**Incident Response:**
- [ ] Identify unauthorized access attempt
- [ ] Review audit logs for affected users
- [ ] Disable compromised accounts
- [ ] Reset credentials if needed
- [ ] Document incident
- [ ] Notify affected parties
- [ ] Implement preventive measures

### Documentation Requirements

**Maintain Records Of:**
- User access requests and approvals
- Access changes (grants, revocations)
- Security incidents and responses
- Compliance audit results
- Training completion records

---

## Appendix: Quick Reference

### Common Django Shell Commands

```python
# Access shell
docker exec -it naaccord-services python manage.py shell

# Import models
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.models import Cohort, CohortMembership

User = get_user_model()

# Find user
user = User.objects.get(email='user@institution.edu')

# Show user groups
user.groups.all()

# Show user cohorts
CohortMembership.objects.filter(user=user)

# Assign to group
group = Group.objects.get(name='Cohort User')
user.groups.add(group)

# Assign to cohort
cohort = Cohort.objects.get(acronym='VACS')
CohortMembership.objects.create(user=user, cohort=cohort)

# Check permissions
user.has_perm('depot.view_audit')
user.has_perm('depot.add_audit')

# List all users in a group
Group.objects.get(name='Cohort User').user_set.all()

# List all users in a cohort
cohort = Cohort.objects.get(acronym='VACS')
CohortMembership.objects.filter(cohort=cohort)
```

### Management Commands

```bash
# User management
docker exec naaccord-services python manage.py list_users
docker exec naaccord-services python manage.py list_inactive_users --days 90
docker exec naaccord-services python manage.py import_user_assignments users.csv

# Permission setup
docker exec naaccord-services python manage.py setup_permission_groups

# Audit trails
docker exec naaccord-services python manage.py show_phi_audit_trail --cohort VACS --days 7
docker exec naaccord-services python manage.py show_user_activity --user user@institution.edu

# Cohort management
docker exec naaccord-services python manage.py cohort_stats --cohort VACS
docker exec naaccord-services python manage.py list_cohorts

# Security
docker exec naaccord-services python manage.py generate_compliance_report
docker exec naaccord-services python manage.py check_security_issues
```

### Access Control Decision Tree

```
┌─────────────────────────────────────────────┐
│ Can user upload files for Cohort X?        │
└────────────┬────────────────────────────────┘
             │
             ▼
     ┌───────────────┐
     │ Authenticated?│───No──> Redirect to login
     └───────┬───────┘
             Yes
             │
             ▼
     ┌─────────────────────┐
     │ Has add_audit perm? │───No──> Forbidden (403)
     └──────────┬──────────┘
                Yes
                │
                ▼
     ┌─────────────────────────┐
     │ Member of Cohort X?      │───No──> Forbidden (403)
     │ OR Site Administrator?   │
     └──────────┬───────────────┘
                Yes
                │
                ▼
     ┌─────────────────┐
     │ Cohort Active?  │───No──> Show "Closed" message
     └────────┬────────┘
              Yes
              │
              ▼
     ┌────────────────┐
     │ Allow Upload   │
     └────────────────┘
```

---

**Document Version**: 1.0
**Last Updated**: October 2025
**Maintained By**: NA-ACCORD Administration Team

**Questions?** Contact your system administrator or the NA-ACCORD technical team.

---

*This guide should be reviewed quarterly and updated after any security-related changes.*
