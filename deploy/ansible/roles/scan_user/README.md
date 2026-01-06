# Scan User Management Role

Ansible role for managing Acunetix security scan user accounts in NA-ACCORD.

## Overview

This role provides a complete lifecycle management system for security scan support users. The JHU IT Security team requires two separate Acunetix scans:

1. **First Scan**: Normal user-level permissions to test standard functionality
2. **Second Scan**: Admin/superuser permissions to test administrative features

This role manages the user through four distinct states:

| Action | Purpose | User Status After |
|--------|---------|-------------------|
| `create` | Create user for first scan | Normal user in "Scan Support" cohort |
| `escalate` | Prepare for second scan | Superuser with full admin access |
| `deescalate` | Return to normal after second scan | Normal user (no admin) |
| `remove` | Delete user when scanning complete | User deleted |

## Requirements

- Ansible 2.9+
- Docker installed on target services server
- NA-ACCORD services container running (`naaccord-services`)
- Proper Django environment configured

## Role Variables

### Default Variables (from `defaults/main.yml`)

```yaml
# Scan user configuration
scan_user_jhed: "ssuppor2"                 # JHED username
scan_user_email: "ssuppor2@jh.edu"         # Email address
scan_user_first_name: "Scan"               # First name
scan_user_last_name: "Support"             # Last name

# Cohort configuration
scan_cohort_name: "Scan Support"           # Test cohort name
scan_cohort_description: "Test cohort for Acunetix security scanning"

# Operational flags
scan_user_remove_cohort: false             # Remove cohort when deleting user
scan_user_skip_confirmation: false         # Skip confirmation prompts
```

### Required Variables

**`scan_user_action`** (string, required)
- Must be one of: `create`, `escalate`, `deescalate`, `remove`
- Passed via command line with `-e 'scan_user_action=VALUE'`

## Dependencies

None. This role is self-contained.

## Usage Examples

### Staging Environment

```bash
# 1. Create scan user (before first Acunetix scan)
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local

# 2. Run first Acunetix scan with normal user permissions
# (Acunetix configured to use JHED: ssuppor2)

# 3. Escalate to superuser (before second Acunetix scan)
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=escalate' --connection local

# 4. Run second Acunetix scan with admin permissions
# (Same JHED: ssuppor2, now with superuser access)

# 5. Deescalate back to normal user (after second scan)
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=deescalate' --connection local

# 6. Remove user completely (when all scanning is done)
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' --connection local
```

### Production Environment

```bash
# Same commands, just use production inventory and vault password
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local --ask-vault-pass
```

### Custom User Configuration

```bash
# Create user with custom JHED and email
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' \
  -e 'scan_user_jhed=custom_user' \
  -e 'scan_user_email=custom@jh.edu' \
  --connection local
```

### Automated Removal (No Confirmation)

```bash
# Remove user and cohort without confirmation prompt (for automation)
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' \
  -e 'scan_user_remove_cohort=true' \
  -e 'scan_user_skip_confirmation=true' \
  --connection local
```

## Django Management Commands

This role wraps four Django management commands:

### 1. `create_scan_user`

Creates user with normal permissions.

```bash
# Direct command execution (for testing)
python manage.py create_scan_user
python manage.py create_scan_user --jhed custom_user --email custom@jh.edu
```

**What it does:**
- Creates "Scan Support" cohort (if doesn't exist)
- Creates user account with JHED authentication
- Adds user to cohort as viewer role
- Sets `is_staff=False`, `is_superuser=False`

### 2. `escalate_scan_user`

Grants superuser and staff permissions.

```bash
# Direct command execution (for testing)
python manage.py escalate_scan_user
python manage.py escalate_scan_user --jhed custom_user
```

**What it does:**
- Finds existing scan user
- Sets `is_staff=True`, `is_superuser=True`
- Documents escalation timestamp
- Displays security warnings

### 3. `deescalate_scan_user`

Removes superuser and staff permissions.

```bash
# Direct command execution (for testing)
python manage.py deescalate_scan_user
python manage.py deescalate_scan_user --jhed custom_user
```

**What it does:**
- Finds existing scan user
- Sets `is_staff=False`, `is_superuser=False`
- Documents deescalation timestamp
- Confirms normal user status

### 4. `remove_scan_user`

Permanently deletes user account.

```bash
# Direct command execution (for testing)
python manage.py remove_scan_user
python manage.py remove_scan_user --jhed custom_user
python manage.py remove_scan_user --remove-cohort
python manage.py remove_scan_user --skip-confirmation
```

**What it does:**
- Removes all cohort memberships
- Deletes user account
- Optionally deletes "Scan Support" cohort (if no other members)
- Requires confirmation (unless `--skip-confirmation`)

## Security Considerations

### Audit Trail

All operations are automatically logged by Django:
- User creation/deletion events
- Permission changes (escalation/deescalation)
- Cohort membership changes
- Timestamps for all actions

### Access Control

- Role must be run on services server (where Django database lives)
- Requires proper user permissions (become: naaccord)
- Commands execute inside Docker container for isolation

### Best Practices

1. **Create → Scan → Escalate → Scan → Deescalate → Remove**
   - Follow the complete lifecycle
   - Don't leave users with elevated permissions

2. **Document Scans**
   - Record when scans are performed
   - Save Acunetix reports
   - Note any findings

3. **Remove After Completion**
   - Delete scan users when no longer needed
   - Don't leave test accounts active

4. **Use Staging First**
   - Test the workflow in staging
   - Verify Acunetix configuration
   - Then proceed to production

## Troubleshooting

### User Already Exists

```bash
# Check if user exists
docker exec naaccord-services python manage.py shell -c \
  "from django.contrib.auth import get_user_model; \
   print(get_user_model().objects.filter(username='ssuppor2').exists())"

# Remove existing user first
ansible-playbook playbooks/scan-user.yml -e 'scan_user_action=remove'
```

### User Not Found

```bash
# Verify user was created
docker exec naaccord-services python manage.py shell -c \
  "from django.contrib.auth import get_user_model; \
   u = get_user_model().objects.get(username='ssuppor2'); \
   print(f'User: {u.username}, Staff: {u.is_staff}, Super: {u.is_superuser}')"
```

### Cohort Has Other Members

```bash
# Check cohort membership
docker exec naaccord-services python manage.py shell -c \
  "from depot.models import Cohort, CohortMembership; \
   c = Cohort.objects.get(name='Scan Support'); \
   print(f'Members: {CohortMembership.objects.filter(cohort=c).count()}')"

# Cannot remove cohort if other members exist
# Either remove members first or use scan_user_remove_cohort=false
```

### Permission Errors

```bash
# Verify Django container is running
docker ps | grep naaccord-services

# Check container logs
docker logs naaccord-services --tail 50

# Verify database connectivity
docker exec naaccord-services python manage.py check --database default
```

## Testing

### Local Testing (Without Ansible)

```bash
# SSH to services server
ssh user@services-server

# Create user
docker exec naaccord-services python manage.py create_scan_user

# Verify creation
docker exec naaccord-services python manage.py shell -c \
  "from django.contrib.auth import get_user_model; \
   u = get_user_model().objects.get(username='ssuppor2'); \
   print(f'Created: {u.username} ({u.email}), Super: {u.is_superuser}')"

# Escalate
docker exec naaccord-services python manage.py escalate_scan_user

# Verify escalation
docker exec naaccord-services python manage.py shell -c \
  "from django.contrib.auth import get_user_model; \
   u = get_user_model().objects.get(username='ssuppor2'); \
   print(f'Superuser: {u.is_superuser}, Staff: {u.is_staff}')"

# Deescalate
docker exec naaccord-services python manage.py deescalate_scan_user

# Remove
docker exec naaccord-services python manage.py remove_scan_user --skip-confirmation
```

### Integration Testing (With Ansible)

```bash
# Full lifecycle test in staging
cd /opt/naaccord/depot/deploy/ansible

# 1. Create
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local

# 2. Escalate
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=escalate' --connection local

# 3. Deescalate
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=deescalate' --connection local

# 4. Remove
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' \
  -e 'scan_user_skip_confirmation=true' \
  --connection local
```

## File Structure

```
roles/scan_user/
├── README.md                    # This file
├── defaults/
│   └── main.yml                 # Default variables
└── tasks/
    ├── main.yml                 # Entry point (routes to specific tasks)
    ├── create.yml               # Create user with normal permissions
    ├── escalate.yml             # Grant superuser permissions
    ├── deescalate.yml           # Remove superuser permissions
    └── remove.yml               # Delete user account
```

## Related Documentation

- [Acunetix Security Scanning Requirements](../../docs/security/acunetix-scanning.md) (TODO)
- [User Management](../../docs/user-management.md)
- [SAML Authentication](../../docs/security/auth-workflow.md)
- [Emergency Access Procedures](../../docs/deployment/guides/emergency-access.md)

## License

NA-ACCORD project - JHU Biostatistics Center

## Author

Created for NA-ACCORD security scan support - 2025-10-15
