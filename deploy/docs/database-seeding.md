# Database Seeding Guide

**How to seed the NA-ACCORD database with initial data and users**

## Overview

The database seeding process loads:
- **Core data**: Cohorts, data file types, protocol years, permission groups
- **Users**: Test users (staging) or production users (production)
- **Relationships**: User-group assignments and cohort memberships

## Quick Start

### Staging (Automatic)

On the staging server, simply run:

```bash
naseed
```

This automatically:
1. Runs database migrations
2. Seeds cohorts, data file types, protocol years
3. Creates permission groups
4. **Loads test users** from fixtures
5. Assigns users to groups and cohorts

### Production (Requires Setup)

On production, you must first create user CSV files:

**Step 1: Create production user CSV files**

```bash
cd /opt/naaccord/depot

# Copy templates
cp resources/data/seed/users_production_template.csv resources/data/seed/users_production.csv
cp resources/data/seed/user_groups_production_template.csv resources/data/seed/user_groups_production.csv
cp resources/data/seed/cohort_memberships_production_template.csv resources/data/seed/cohort_memberships_production.csv
```

**Step 2: Edit CSV files with real user data**

Edit each file with production user information:

```bash
nano resources/data/seed/users_production.csv
nano resources/data/seed/user_groups_production.csv
nano resources/data/seed/cohort_memberships_production.csv
```

**Step 3: Run seeding**

```bash
naseed
```

## CSV File Formats

### users_production.csv

```csv
username,email,first_name,last_name,is_staff,is_superuser
jdoe,john.doe@jhu.edu,John,Doe,True,True
jsmith,jane.smith@jhu.edu,Jane,Smith,False,False
```

**Fields:**
- `username`: Unique username (used for login if not using SAML)
- `email`: User's email address (must match SAML attribute)
- `first_name`: First name
- `last_name`: Last name
- `is_staff`: `True` if user can access Django admin, `False` otherwise
- `is_superuser`: `True` for superadmin (full permissions), `False` otherwise

### user_groups_production.csv

```csv
user_email,group_name
john.doe@jhu.edu,Cohort Managers
jane.smith@jhu.edu,Cohort Managers
```

**Fields:**
- `user_email`: Email of the user (must match users_production.csv)
- `group_name`: One of: `Cohort Managers`, `Cohort Viewers`, `Site Administrators`

**Available Groups:**
- **Site Administrators**: Full system access
- **Cohort Managers**: Can manage cohort data, upload files, view reports
- **Cohort Viewers**: Read-only access to cohort data

### cohort_memberships_production.csv

```csv
user_email,cohort_id,cohort_name
john.doe@jhu.edu,5,JHHCC
john.doe@jhu.edu,18,VACS / VACS8
jane.smith@jhu.edu,5,JHHCC
```

**Fields:**
- `user_email`: Email of the user
- `cohort_id`: Numeric ID of the cohort (see cohort list below)
- `cohort_name`: Name of the cohort (for reference, not used)

**Available Cohorts:**

| ID | Name | ID | Name |
|----|------|----|------|
| 1 | CWRU | 17 | UCSF |
| 2 | Fenway | 18 | VACS / VACS8 |
| 3 | HIV-CAUSAL | 19 | Vanderbilt - Nashville |
| 4 | HOPS | 20 | WIHS / MWCCS |
| 5 | JHHCC | 21 | NA-ACCORD DCC |
| 6 | John Stroger | 22 | REACH |
| 7 | Kaiser Northern California | 23 | SUN |
| 8 | Kaiser Southern California | 24 | HAILO |
| 9 | MACS / MWCCS | 25 | AFRICOS |
| 10 | Pitt CRS | 26 | CFAR |
| 11 | SouthernAlberta | 27 | DOD-NATURAL HISTORY STUDY |
| 12 | UA - Birmingham | 28 | HANA |
| 13 | UCSD | 29 | SALSA |
| 14 | UNC | 30 | CNICS |
| 15 | UW | 31 | ALL SITES |
| 16 | Ontario |  |  |

## Manual Seeding (Alternative)

If you prefer to run commands manually instead of using Ansible:

### Staging

```bash
# On services server
docker exec naaccord-services python manage.py migrate
docker exec naaccord-services python manage.py seed_init
docker exec naaccord-services python manage.py setup_permission_groups
docker exec naaccord-services python manage.py load_test_users --fixture-dir depot/fixtures/test_users
docker exec naaccord-services python manage.py assign_test_users_to_groups
```

### Production

```bash
# On services server (after creating production CSV files)
docker exec naaccord-services python manage.py migrate
docker exec naaccord-services python manage.py seed_init
docker exec naaccord-services python manage.py setup_permission_groups
docker exec naaccord-services python manage.py load_users_from_csv --csv-dir resources/data/seed
```

## Ansible Playbook

The seeding is handled by the `db_seed` Ansible role and `seed.yml` playbook.

**Run via Ansible directly:**

```bash
cd /opt/naaccord/depot/deploy/ansible

# Staging
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/seed.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging

# Production
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/seed.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production
```

## Test Users (Staging Only)

Staging includes pre-configured test users for SAML testing:

| Email | Role | Groups | Cohorts |
|-------|------|--------|---------|
| admin@test.edu | Site Admin | Site Administrators | VACS, JHHCC, UCSD |
| admin@va.gov | Cohort Manager | Cohort Managers | VACS |
| admin@jh.edu | Cohort Manager | Cohort Managers | JHHCC |
| researcher@test.edu | Researcher | Cohort Managers | JHHCC |
| coordinator@test.edu | Coordinator | Cohort Managers | VACS |
| viewer@test.edu | Viewer | Cohort Viewers | JHHCC |

**SAML Login:** These users authenticate via the mock SAML IDP in staging. Use the email as the username.

## Troubleshooting

### Error: Production users CSV not found

**Problem:** Running `naseed` on production fails with CSV not found error.

**Solution:** Create production user CSV files from templates (see Production setup above).

### Error: Cohort not found

**Problem:** cohort_memberships.csv references invalid cohort ID.

**Solution:** Check the cohort ID in the database or use the cohort list above.

### Error: Group not found

**Problem:** user_groups.csv references invalid group name.

**Solution:** Ensure group name exactly matches one of:
- `Site Administrators`
- `Cohort Managers`
- `Cohort Viewers`

### Users created but can't log in

**Problem:** Users exist but SAML login fails.

**Solution:**
1. Verify user email matches SAML attribute mapping
2. Check SAML metadata configuration
3. Verify user is in a permission group
4. Check user has cohort membership (required for sidebar)

### Cohorts don't appear in sidebar

**Problem:** User logs in but sidebar shows no cohorts.

**Solution:** User needs cohort membership. Add entries to `cohort_memberships_production.csv` and re-run `naseed`.

## Related Documentation

- [Deployment Steps](../deploy-steps.md) - Full deployment workflow
- [Aliases Reference](aliases-reference.md) - Shell aliases including `naseed`
- [SAML Configuration](saml-configuration.md) - SAML authentication setup

## See Also

**Management Commands:**
- `seed_init` - Seeds core data (cohorts, data types, years, groups)
- `setup_permission_groups` - Creates permission groups with Django permissions
- `load_test_users` - Loads test users from fixtures (staging)
- `load_users_from_csv` - Loads users from CSV directory (production)
- `assign_test_users_to_groups` - Assigns test users to groups (staging)
