# Production User Seeding Guide

## Overview

This directory contains CSV files for seeding production users for NA-ACCORD Data Depot.

## Files

- **`users_production.csv`** - User accounts with staff/superuser flags
- **`user_groups_production.csv`** - Assigns users to Cohort Groups (roles)
- **`cohort_memberships_production.csv`** - Assigns users to specific cohorts (optional for admins)

## Current Production Setup

All production users are assigned to the **"NA Accord Administrators"** group, which provides:
- ✅ Full access to Django admin panel (requires `is_staff=True`)
- ✅ Can view ALL cohorts (bypasses cohort membership restrictions)
- ✅ Can manage ALL submissions (approve, reopen, etc.)
- ✅ Can edit ALL cohorts
- ✅ Can create and manage submissions for any cohort
- ✅ Full system-wide access

### Current Users

| User | Email | Staff | Superuser | Group |
|------|-------|-------|-----------|-------|
| Erik Westlund | ewestlund@jhu.edu | ✓ | ✓ | NA Accord Administrators |
| Andre Hackman | ahackman@jhu.edu | ✓ | ✓ | NA Accord Administrators |
| Keri Althoff | kalothoff@jhu.edu | ✓ | ✗ | NA Accord Administrators |
| Brenna Hogan | bhogan7@jhu.edu | ✓ | ✗ | NA Accord Administrators |
| Catherine Lesko | clesko2@jhu.edu | ✓ | ✗ | NA Accord Administrators |

**Note:** NA Accord Administrators do NOT need explicit cohort memberships - they can see all cohorts automatically.

## Deployment Instructions

### On Production Services Server

```bash
# SSH to production services server
ssh user@mrpznaaccorddb01.hosts.jhmi.edu

# Navigate to application directory
cd /opt/naaccord/depot

# Load production users
docker exec -it naaccord-services python manage.py load_users_from_csv \
  --csv-dir resources/data/seed \
  --clear

# Verify users were created
docker exec -it naaccord-services python manage.py shell
```

### Verification in Django Shell

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
User = get_user_model()

# Check all users were created
User.objects.filter(email__endswith='@jhu.edu').values_list('email', 'is_staff', 'is_superuser')

# Check NA Accord Administrators group
admin_group = Group.objects.get(name='NA Accord Administrators')
admin_group.user_set.all().values_list('email', flat=True)

# Verify a specific user has full access
user = User.objects.get(email='kalothoff@jhu.edu')
print(f"is_staff: {user.is_staff}")
print(f"is_superuser: {user.is_superuser}")
print(f"is_na_accord_admin: {user.is_na_accord_admin()}")
print(f"Groups: {list(user.groups.values_list('name', flat=True))}")
```

## File Formats

### users_production.csv

```csv
username,email,first_name,last_name,is_staff,is_superuser
ewestlund,ewestlund@jhu.edu,Erik,Westlund,True,True
```

**Fields:**
- `username` - Unique username (typically matches email prefix)
- `email` - Email address (used for SAML authentication)
- `first_name` - First name
- `last_name` - Last name
- `is_staff` - `True` for Django admin access, `False` otherwise
- `is_superuser` - `True` for unrestricted access (use sparingly)

### user_groups_production.csv

```csv
user_email,group_name
ewestlund@jhu.edu,NA Accord Administrators
```

**Fields:**
- `user_email` - User's email address (must match users_production.csv)
- `group_name` - Cohort Group name (see Available Groups below)

**Available Groups:**
- `NA Accord Administrators` - Full system access
- `Cohort Managers` - Can manage submissions for assigned cohorts
- `Cohort Viewers` - Read-only access to assigned cohorts

### cohort_memberships_production.csv

```csv
user_email,cohort_id,cohort_name
researcher@jhu.edu,5,JHHCC
```

**Fields:**
- `user_email` - User's email address
- `cohort_id` - Numeric cohort ID (from database)
- `cohort_name` - Cohort name (for reference only, not used)

**Note:** NA Accord Administrators do NOT need cohort memberships.

## Adding New Users

### Steps

1. **Edit `users_production.csv`** - Add new user row
2. **Edit `user_groups_production.csv`** - Assign to appropriate group
3. **Edit `cohort_memberships_production.csv`** - Only if needed (not for admins)
4. **Commit changes** to git repository
5. **Deploy to production** following Deployment Instructions above

### Example: Adding a Cohort Manager

```csv
# users_production.csv
jsmith,jsmith@jhu.edu,Jane,Smith,True,False

# user_groups_production.csv
jsmith@jhu.edu,Cohort Managers

# cohort_memberships_production.csv
jsmith@jhu.edu,5,JHHCC
jsmith@jhu.edu,12,VACS
```

## Security Notes

- **is_superuser should be minimal** - Only 1-2 users need this level of access
- **is_staff is required for admin access** - All admin users need this flag
- **NA Accord Administrators see everything** - Use this group for site-wide access
- **SAML is required for login** - Users must authenticate via JHU Shibboleth
- **No password authentication** - All access via SSO only

## Troubleshooting

### Users can't log in

- Verify user exists: Check `users_production.csv` and re-run seeding
- Check SAML mapping: User's JHU email must match email in CSV
- Verify staff flag: `is_staff=True` required for admin panel access

### Users can't see cohorts

- Check group membership: Verify `user_groups_production.csv` was loaded
- For admins: Ensure user is in "NA Accord Administrators" group
- For others: Check `cohort_memberships_production.csv` has correct assignments

### Permission denied errors

- Verify group assignment: Run verification commands in Django shell
- Check is_staff flag: Must be `True` for admin panel access
- For full access: User needs "NA Accord Administrators" group membership

## Related Documentation

- **[../../../docs/manuals/technical/administrator-guide.md](../../../docs/manuals/technical/administrator-guide.md)** - Access control guide
- **[../../../docs/manuals/technical/system-administration-guide.md](../../../docs/manuals/technical/system-administration-guide.md)** - System administration
- **[../../../deploy/CLAUDE.md](../../../deploy/CLAUDE.md)** - Deployment procedures
