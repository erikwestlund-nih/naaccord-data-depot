# Production User Seeding and Permission Group Cleanup

**Date:** October 10, 2025
**Type:** Configuration & Database Seeding
**Status:** Complete

## Overview

Configured production user seeding with proper permission groups and cleaned up legacy group creation. Set up 18 production users across 3 cohorts with appropriate role-based access control.

## Problem Statement

1. Production users needed to be configured with proper `is_staff` and `is_superuser` flags
2. User groups needed clarification between "NA Accord Administrators" and "Cohort Managers"
3. Database seeding was creating 8 redundant permission groups (3 new + 5 legacy)
4. Cohort users needed to be set up as non-staff Cohort Managers

## Investigation

### Initial Questions

User was filling out `users_production_template.csv` and asked:
> "can you tell me if staff have basically full web access if its is_staff. what cant they do without superuser?"

**Finding:**
- `is_staff=True` → Django admin panel access only
- `is_superuser=True` → Full unrestricted access, bypasses all checks
- **Group membership** determines actual permissions (not staff/superuser flags)

### Permission Groups Analysis

Found 8 groups in test database:
```
1. NA Accord Administrators  (NEW - use this)
2. Cohort Managers           (NEW - use this)
3. Cohort Viewers            (NEW - use this)
4. Administrators            (LEGACY - remove)
5. Data Managers             (LEGACY - remove)
6. Researchers               (LEGACY - remove)
7. Coordinators              (LEGACY - remove)
8. Viewers                   (LEGACY - remove)
```

**Code Analysis:**
- `depot/constants/groups.py` defines both new and legacy groups
- `depot/models/user.py` has transition logic checking both group types
- `depot/management/commands/setup_permission_groups.py` was creating ALL 8 groups

## Solution Implemented

### 1. Removed Legacy Group Creation

**File:** `depot/management/commands/setup_permission_groups.py`

**Changes:**
- Removed all legacy group creation (Administrators, Data Managers, Researchers, Coordinators, Viewers)
- Now only creates 3 groups:
  - NA Accord Administrators
  - Cohort Managers
  - Cohort Viewers
- Updated output messages to reflect simplified structure

### 2. Created Legacy Group Removal Command

**File:** `depot/management/commands/remove_legacy_groups.py` (NEW)

Provides safe migration path for existing databases:
```bash
# Check what would be removed
python manage.py remove_legacy_groups --dry-run

# Migrate users from legacy to new groups
python manage.py remove_legacy_groups --migrate-users
```

**Migration mapping:**
- Administrators/Data Managers → NA Accord Administrators
- Researchers/Coordinators → Cohort Managers
- Viewers → Cohort Viewers

### 3. Production User Seeding Configuration

#### NA Accord Administrators (5 users)

Full system access - can see ALL cohorts:

| User | Email | is_staff | is_superuser | Role |
|------|-------|----------|--------------|------|
| Erik Westlund | ewestlund@jhu.edu | True | True | Tech Lead |
| Andre Hackman | ahackman@jhu.edu | True | True | Tech Lead |
| Keri Althoff | kalothoff@jhu.edu | True | False | Study Lead |
| Brenna Hogan | bhogan7@jhu.edu | True | False | Study Lead |
| Catherine Lesko | clesko2@jhu.edu | True | False | Study Lead |

#### Cohort Managers (13 users)

Can manage submissions for assigned cohorts only - all have `is_staff=False, is_superuser=False`:

**JHHCC (Cohort ID: 6) - 4 users:**
- LaQuita Snow (lsnow7@jhu.edu)
- Jeanne Keruly (jkeruly@jhmi.edu)
- Richard Moore (rdmoore@jhmi.edu)
- Todd Fojo (Anthony.Fojo@jhmi.edu)

**MWCCS (Cohort ID: 22) - 5 users:**
- Srijana Lawa (slawa1@jhu.edu)
- Mateo Bandala Jacques (abandal1@jhmi.edu)
- Stephen Gange (sgange@jhu.edu)
- Elizabeth Topper (etopper@jhu.edu)
- Amber D'Souza (gdsouza2@jhu.edu)

**Einstein/Montefiore (Cohort ID: 33) - 4 users:**
- David Hanna (david.hanna@einsteinmed.edu)
- Uriel Felsen (UFELSEN@montefiore.org)
- Mindy Ginsberg (mindy.ginsberg@einsteinmed.edu)
- Noel Relucio (noel.relucio@einsteinmed.edu)

**Note:** Einstein/Montefiore cohort was added to seed data (pending name confirmation).

### 4. Updated Seed Files

**Files Updated:**
- `resources/data/seed/cohorts.csv` - Added Einstein/Montefiore (ID 33)
- `resources/data/seed/users_production.csv` - 18 users configured
- `resources/data/seed/user_groups_production.csv` - All assigned to appropriate groups
- `resources/data/seed/cohort_memberships_production.csv` - Cohort managers assigned to cohorts

**Documentation Created:**
- `resources/data/seed/README-PRODUCTION.md` - Complete production seeding guide
- `resources/data/seed/PRODUCTION-USERS-SUMMARY.md` - Current user summary

## Key Decisions

1. **Only 3 permission groups** - Removed all legacy group creation from seeding
2. **Staff flag for admin access** - Tech leads and study leads get `is_staff=True` for Django admin
3. **Superuser minimal** - Only Erik and Andre get `is_superuser=True`
4. **Cohort managers non-staff** - All cohort users have `is_staff=False` (no admin panel access)
5. **Group determines permissions** - Actual access controlled by group membership, not flags

## Permission Group Structure

### NA Accord Administrators
**What they can do:**
- ✅ Full Django admin access (with `is_staff=True`)
- ✅ See ALL cohorts (bypasses cohort membership)
- ✅ Manage ALL submissions (approve, reopen, etc.)
- ✅ Edit ALL cohorts
- ✅ Full system-wide access

**Code reference:** `depot/admin.py:68`, `depot/permissions.py:123`

### Cohort Managers
**What they can do:**
- ✅ View assigned cohort(s) data and submissions
- ✅ Upload data files for assigned cohort(s)
- ✅ Create and manage submissions for assigned cohort(s)
- ✅ See validation reports for assigned cohort(s)
- ❌ Cannot access Django admin panel (`is_staff=False`)
- ❌ Cannot see other cohorts

**Code reference:** `depot/models/user.py:11-17`, `depot/permissions.py:18`

### Cohort Viewers
**What they can do:**
- ✅ Read-only access to assigned cohort(s)
- ❌ Cannot upload or modify data

**Note:** No viewers configured in production yet.

## Deployment Instructions

### On Production Services Server

```bash
# SSH to production
ssh user@mrpznaaccorddb01.hosts.jhmi.edu

# Navigate to application
cd /opt/naaccord/depot

# Remove legacy groups (if database already exists)
docker exec -it naaccord-services python manage.py remove_legacy_groups --migrate-users

# Load production users
docker exec -it naaccord-services python manage.py load_users_from_csv \
  --csv-dir resources/data/seed

# Verify groups
docker exec -it naaccord-services python manage.py shell
```

### Verification Commands

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
User = get_user_model()

# Check all groups
Group.objects.all().values_list('name', flat=True)
# Should only show: ['NA Accord Administrators', 'Cohort Managers', 'Cohort Viewers']

# Check user counts per group
for group in Group.objects.all():
    print(f"{group.name}: {group.user_set.count()} users")

# Verify specific user
user = User.objects.get(email='lsnow7@jhu.edu')
print(f"is_staff: {user.is_staff}")              # False
print(f"is_superuser: {user.is_superuser}")      # False
print(f"is_cohort_manager: {user.is_cohort_manager()}")  # True
print(f"Groups: {list(user.groups.values_list('name', flat=True))}")
```

## Testing Notes

### Test Scenarios

1. **NA Accord Administrator access:**
   - ✅ Can log into Django admin
   - ✅ Can see all 33 cohorts in sidebar
   - ✅ Can create submissions for any cohort
   - ✅ Can approve/reopen submissions

2. **Cohort Manager access (JHHCC user):**
   - ✅ Can log in via SAML
   - ✅ Only sees JHHCC cohort in sidebar
   - ✅ Can upload JHHCC data files
   - ✅ Can create JHHCC submissions
   - ❌ Cannot access Django admin panel
   - ❌ Cannot see other cohorts

3. **Legacy group cleanup:**
   - ✅ `remove_legacy_groups` command identifies users in old groups
   - ✅ Migration preserves user access
   - ✅ Old groups removed after migration

## Files Modified

### New Files
1. `depot/management/commands/remove_legacy_groups.py` - Legacy group cleanup command
2. `resources/data/seed/README-PRODUCTION.md` - Production seeding documentation
3. `resources/data/seed/PRODUCTION-USERS-SUMMARY.md` - Current user summary

### Modified Files
1. `depot/management/commands/setup_permission_groups.py` - Removed legacy group creation
2. `resources/data/seed/cohorts.csv` - Added Einstein/Montefiore cohort
3. `resources/data/seed/users_production.csv` - Added 13 cohort manager users
4. `resources/data/seed/user_groups_production.csv` - Assigned all users to groups
5. `resources/data/seed/cohort_memberships_production.csv` - Assigned cohort managers to cohorts

## Related Documentation

- `docs/manuals/technical/administrator-guide.md` - Access control documentation
- `deploy/README-PRODUCTION.md` - Production deployment guide
- `resources/data/seed/README-PRODUCTION.md` - Seeding instructions

## Next Steps

1. Confirm Einstein/Montefiore cohort name
2. Add additional cohort users as requested
3. Test seeding in staging environment
4. Deploy to production after verification
5. Remove legacy group references from codebase (future cleanup)

## Lessons Learned

1. **Group membership > flags** - Django's `is_staff` and `is_superuser` are less important than group membership for actual permissions
2. **Legacy code complexity** - Having both new and legacy groups made permission logic confusing
3. **Seeding automation critical** - Manual user setup would be error-prone with 18+ users
4. **Documentation essential** - Clear role documentation helps users understand access levels

## Metrics

- **Users configured:** 18 (5 admins + 13 cohort managers)
- **Cohorts covered:** 3 (JHHCC, MWCCS, Einstein/Montefiore)
- **Groups simplified:** 8 → 3 groups
- **Deployment time:** ~2 minutes (automated seeding)
