# Seed Data Files

This directory contains CSV files used to seed the database with initial data.

## Environment-Specific Seeding

The `seed_init` management command supports environment-specific CSV files. This allows different cohorts, users, or other data for staging vs production environments.

### How It Works

When running `python manage.py seed_init`, the command checks the `NAACCORD_ENVIRONMENT` environment variable:

- `staging` - Uses `cohorts.staging.csv` if it exists
- `production` - Uses `cohorts.production.csv` if it exists
- `development` (default) - Uses `cohorts.csv` (base file)

If an environment-specific file doesn't exist, it falls back to the base file.

### File Naming Convention

```
{base_name}.csv                    # Base file (development)
{base_name}.staging.csv            # Staging environment
{base_name}.production.csv         # Production environment
```

### Currently Supported

**Cohorts are the same in all environments:**
- `cohorts.csv` - All 31 NA-ACCORD cohorts (used in dev, staging, and production)

**Users will be environment-specific (future implementation):**
- `users.csv` - Development and staging test users (same mock accounts)
- `users.production.csv` - Production users with real JHU accounts (future)

### Adding Environment Support to Other Models

To enable environment-specific files for other models, edit `depot/management/commands/seed_init.py`:

```python
{
    "model": "depot.YourModel",
    "file": "resources/data/seed/your_model.csv",
    "use_environment": True,  # Add this flag
},
```

### Usage

**All environments use the same cohorts:**
```bash
python manage.py seed_init
# Loads all 31 NA-ACCORD cohorts from cohorts.csv
# Same cohorts in development, staging, and production
```

**Environment-specific user seeding (future):**
```bash
# When user seeding is implemented with environment support:
export NAACCORD_ENVIRONMENT=production
python manage.py seed_users  # Would use users.production.csv
```

### Deployment Integration

The Ansible deployment automatically sets `NAACCORD_ENVIRONMENT` in the `.env` file based on the inventory (staging/production), so no manual environment variable setting is needed on deployed servers.

## Standard Seed Files

These files are used in all environments:

- `groups.csv` - Django permission groups
- `data_file_types.csv` - Data submission file types (patient, laboratory, etc.)
- `protocol_years.csv` - Protocol year definitions

## Production Template Files

These files are templates for production user/group setup:

- `users_production_template.csv` - Template for production users
- `user_groups_production_template.csv` - Template for user group assignments
- `cohort_memberships_production_template.csv` - Template for cohort memberships

Copy these templates, populate with actual production data, and save as environment-specific files if needed.
