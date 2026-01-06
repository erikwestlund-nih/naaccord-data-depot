# Acunetix Security Scan User Management

## Overview

JHU IT Security performs Acunetix vulnerability scans that require a test user account. The scan occurs in two phases:
1. **First scan**: Normal user permissions (authenticated but not admin)
2. **Second scan**: Superuser/admin permissions (full admin access)

This document describes how to create, escalate, deescalate, and remove the scan support user using Ansible playbooks.

## User Details

- **JHED**: ssuppor2
- **Email**: ssuppor2@jh.edu
- **SSO Email**: ssuppor2@johnshopkins.edu (for SAML authentication)
- **Cohort**: "Scan Support" (automatically created)
- **Default Role**: Normal cohort user (no admin privileges)
- **Authentication**: SAML-only (no password login)
- **Default Group**: Cohort Managers

## Prerequisites

- SSH access to production services server: `mrpznaaccorddb01.hosts.jhmi.edu`
- Ansible vault password for production environment
- JHU VPN connection (required for production access)

## Workflow

### 1. Create Scan User (Before First Scan)

Run this command **before** JHU IT performs the first Acunetix scan:

```bash
# SSH to production services server
ssh mrpznaaccorddb01.hosts.jhmi.edu

# Navigate to Ansible directory
cd /opt/naaccord/depot/deploy/ansible

# Create user with normal permissions
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local --ask-vault-pass
```

**What this does:**
- Creates user `ssuppor2` with normal permissions
- Sets SSO email to `ssuppor2@johnshopkins.edu` for SAML authentication
- Sets password as unusable (SAML-only authentication)
- Adds user to "Cohort Managers" permission group
- Creates "Scan Support" cohort (if it doesn't exist)
- Assigns user to the cohort
- User can authenticate via SAML but has NO admin privileges
- User can access cohort data but cannot perform admin functions

**Command is idempotent**: Can be run multiple times to update existing user (including sso_email)

**Provide to JHU IT:**
- SSO Email: `ssuppor2@johnshopkins.edu` (for SAML authentication)
- Username: `ssuppor2` (JHED)
- Login URL: `https://naaccord.jh.edu/saml2/login/`
- Note: Password login is disabled - SAML-only authentication

### 2. Escalate to Superuser (Before Second Scan)

After the first scan completes, JHU IT will request admin-level access for a second scan. Run this command:

```bash
# SSH to production services server (if not already connected)
ssh mrpznaaccorddb01.hosts.jhmi.edu
cd /opt/naaccord/depot/deploy/ansible

# Escalate user to superuser/admin
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=escalate' --connection local --ask-vault-pass
```

**What this does:**
- Removes user from "Cohort Managers" group
- Adds user to "NA Accord Administrators" group
- Grants `is_staff=True` (Django admin access)
- Grants `is_superuser=True` (full admin privileges)
- User can now access admin interface and perform admin functions

**Notify JHU IT:**
- User now has admin privileges
- They can proceed with the second scan

### 3. Deescalate from Superuser (After Second Scan)

After the second scan completes, remove admin privileges:

```bash
# SSH to production services server (if not already connected)
ssh mrpznaaccorddb01.hosts.jhmi.edu
cd /opt/naaccord/depot/deploy/ansible

# Remove admin privileges
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=deescalate' --connection local --ask-vault-pass
```

**What this does:**
- Removes user from "NA Accord Administrators" group
- Adds user back to "Cohort Managers" group
- Removes `is_staff` flag (no Django admin access)
- Removes `is_superuser` flag (no admin privileges)
- User returns to normal cohort user status
- User remains active and can still authenticate

### 4. Remove User (After All Scanning Complete)

Once JHU IT confirms all scanning is complete, permanently delete the user:

```bash
# SSH to production services server (if not already connected)
ssh mrpznaaccorddb01.hosts.jhmi.edu
cd /opt/naaccord/depot/deploy/ansible

# Permanently delete user
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' --connection local --ask-vault-pass
```

**What this does:**
- Permanently deletes the user account (hard delete, not soft delete)
- Removes cohort memberships
- User can no longer authenticate
- "Scan Support" cohort remains (can be reused for future scans)

**Optional**: Remove the cohort as well:
```bash
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' \
  -e 'scan_user_remove_cohort=true' \
  -e 'scan_user_skip_confirmation=true' \
  --connection local --ask-vault-pass
```

## Verification

After each step, verify the user status:

```bash
# Check user exists and current permissions
sudo docker exec naaccord-services python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    user = User.objects.get(username='ssuppor2')
    print(f'User: {user.username}')
    print(f'Email: {user.email}')
    print(f'Active: {user.is_active}')
    print(f'Staff: {user.is_staff}')
    print(f'Superuser: {user.is_superuser}')
    print(f'Cohorts: {[m.cohort.name for m in user.cohortmembership_set.all()]}')
except User.DoesNotExist:
    print('User does not exist')
"
```

## Staging Testing

Before running in production, you can test the workflow in staging:

```bash
# SSH to staging services server
ssh services.naaccord.lan
cd /opt/naaccord/depot/deploy/ansible

# Test create
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local --ask-vault-pass

# Test escalate
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=escalate' --connection local --ask-vault-pass

# Test deescalate
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=deescalate' --connection local --ask-vault-pass

# Test remove
ansible-playbook -i inventories/staging/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' --connection local --ask-vault-pass
```

**Note**: Staging uses mock-idp for SAML authentication. The user credentials for staging are:
- Username: `ssuppor2@jh.edu`
- Password: `ScanSupport2025!`

## Troubleshooting

### Vault Password Issues

If you get "no vault secrets found" error, ensure you have the vault password:

```bash
# Create vault password file (if missing)
read -sp "Enter vault password: " VAULT_PASS && \
echo "$VAULT_PASS" > ~/.naaccord_vault_production && \
unset VAULT_PASS && \
chmod 600 ~/.naaccord_vault_production
```

Then use `--vault-password-file` instead of `--ask-vault-pass`:

```bash
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production
```

### User Already Exists

If you try to create a user that already exists:

```bash
# Remove the existing user first
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=remove' --connection local --ask-vault-pass

# Then create fresh
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local --ask-vault-pass
```

### User Not Found

If you try to escalate/deescalate/remove a user that doesn't exist, the playbook will fail. Create the user first:

```bash
ansible-playbook -i inventories/production/hosts.yml playbooks/scan-user.yml \
  -e 'scan_user_action=create' --connection local --ask-vault-pass
```

## Security Notes

1. **Time-Limited Access**: The scan user should only exist during active scanning periods
2. **Privilege Escalation**: Admin privileges should only be granted for the second scan phase
3. **Permanent Deletion**: Use `force_delete()` to ensure user is truly removed, not soft-deleted
4. **Audit Trail**: All user operations are logged in Django admin history
5. **SAML Authentication**: Production uses JHU Shibboleth, credentials managed by JHU IT

## SAML-Only Authentication System

NA-ACCORD enforces SAML-only authentication system-wide. **No users can authenticate with passwords.**

### Fresh Database Deploys

Fresh database deploys automatically create all users with unusable passwords:

```bash
# Database reset role automatically runs:
# 1. reset_db + migrate
# 2. seed_init (cohorts, data file types)
# 3. setup_permission_groups
# 4. load_test_users ✅ Sets set_unusable_password() for all users
# 5. assign_test_users_to_groups

# Result: All users have password field set to "!" (unusable)
```

### Existing Production Deployment

For existing production environments with users that have passwords, run this **one-time** migration:

```bash
# SSH to production services server
ssh mrpznaaccorddb01.hosts.jhmi.edu

# Navigate to Ansible directory
cd /opt/naaccord/depot/deploy/ansible

# Run password disable playbook
ansible-playbook -i inventories/production/hosts.yml playbooks/disable-passwords.yml \
  --connection local --ask-vault-pass

# Or skip confirmation prompt for automation
ansible-playbook -i inventories/production/hosts.yml playbooks/disable-passwords.yml \
  -e 'skip_confirmation=true' --connection local --ask-vault-pass
```

**What this command does:**
- Finds all users with usable passwords (including empty password fields)
- Sets all passwords to unusable (Django's "!" prefix standard)
- Updates both legacy password hashes and empty password fields
- Requires confirmation (use `--skip-confirmation` for automation)
- Safe to run multiple times (idempotent)

**Verification:**
```bash
# Check password status for specific user
sudo docker exec naaccord-services python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='ssuppor2')
print(f'Has usable password: {user.has_usable_password()}')
print(f'Password field: {user.password}')
"

# Expected output:
# Has usable password: False
# Password field: !
```

### Authentication Flow

1. **User visits**: `https://naaccord.jh.edu/`
2. **Auto-redirect**: Redirected to `https://naaccord.jh.edu/saml2/login/`
3. **SAML authentication**: JHU Shibboleth authentication
4. **Session creation**: Django creates session after successful SAML auth
5. **Password login disabled**: Django's authentication backend skips password check

**Password field values:**
- `!` prefix = Unusable password (Django standard)
- Empty string = Considered "usable" by Django (security issue, should be `!`)
- Any other value = Legacy password hash (should be migrated to `!`)

### Related Commands

**Create users without passwords:**
```bash
# Creates new scan user with SAML-only auth
python manage.py create_scan_user

# Loads test users with SAML-only auth
python manage.py load_test_users
```

**Disable all passwords:**
```bash
# One-time migration for existing deployments
python manage.py disable_all_passwords

# With automatic confirmation
python manage.py disable_all_passwords --skip-confirmation
```

## Related Documentation

- **Ansible Playbooks**:
  - `/deploy/ansible/playbooks/scan-user.yml` - Scan user lifecycle management
  - `/deploy/ansible/playbooks/disable-passwords.yml` - System-wide password enforcement
- **Ansible Role**: `/deploy/ansible/roles/scan_user/`
- **Django Commands**:
  - `/depot/management/commands/create_scan_user.py` - Create scan user with SAML-only auth
  - `/depot/management/commands/escalate_scan_user.py` - Escalate to superuser/admin
  - `/depot/management/commands/deescalate_scan_user.py` - Deescalate back to normal user
  - `/depot/management/commands/remove_scan_user.py` - Permanently delete scan user
  - `/depot/management/commands/disable_all_passwords.py` - System-wide password enforcement
  - `/depot/management/commands/load_test_users.py` - Database seeding with SAML-only users

## Contact

For questions about Acunetix scanning or scan user management:
- **JHU IT Security**: enterprisesecurity@jh.edu
- **NA-ACCORD Technical Lead**: Erik Westlund (ewestlu2@jh.edu)
