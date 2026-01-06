# Database Refresh Guide

## Overview
This guide documents how to completely refresh the NA-ACCORD database, removing all test data and starting fresh with clean seed data and test accounts.

## Quick Refresh (Recommended)

### One-Command Complete Refresh
```bash
# Complete database refresh with all test data
python manage.py refresh_database
```

This single command will:
1. Check and start Docker services (MariaDB, Redis, mock-idp)
2. Drop and recreate the database
3. Run all migrations
4. Load seed data (groups, cohorts, data file types)
5. Create admin superuser
6. Load test users with cohort assignments
7. Clean up any uploaded files
8. Verify the refresh was successful

### Command Options
```bash
# Skip confirmation prompt
python manage.py refresh_database --force

# Skip Docker checks (if services are already running)
python manage.py refresh_database --no-docker

# Skip loading test users
python manage.py refresh_database --skip-users

# Combine options
python manage.py refresh_database --force --no-docker
```

### Manual Step-by-Step (Alternative)
```bash
# 1. Reset database and load base seed data
python manage.py build_test_env

# 2. Load SAML test users
python manage.py load_test_users --clear
```

## Detailed Steps

### Step 1: Reset Database
```bash
python manage.py reset_db
```
This command:
- Drops the existing database
- Creates a new empty database
- **WARNING**: This deletes ALL data permanently

### Step 2: Run Migrations
```bash
python manage.py migrate
```
Creates all database tables and schema.

### Step 3: Load Seed Data
```bash
# Load groups (Data Managers, Researchers, etc.)
python manage.py seed_from_csv --model=auth.group --file=resources/data/seed/groups.csv

# Load cohorts (JHHCC, VACS/VACS8, UCSD, etc.)
python manage.py seed_from_csv --model=depot.Cohort --file=resources/data/seed/cohorts.csv

# Load data file types (patient, laboratory, medication, etc.)
python manage.py seed_from_csv --model=depot.DataFileType --file=resources/data/seed/data_file_types.csv

# Load protocol years (2020-2025, with 2024 and 2025 marked as active)
python manage.py seed_from_csv --model=depot.ProtocolYear --file=resources/data/seed/protocol_years.csv
# Or use the custom command to ensure 2024 and 2025 are active:
# python manage.py seed_protocol_years
```

### Step 4: Create Admin User
```bash
# Create default admin superuser
python manage.py createsuperuser --username admin --email admin@test.com

# Or seed admin with cohort access
python manage.py seed_admin
```

### Step 5: Load Test Users
```bash
python manage.py load_test_users --clear
```
This loads test users from CSV fixtures including:
- admin@va.gov (VA Admin with VACS/VACS8 access)
- admin@jh.edu (JH Researcher with JHHCC access)
- Additional test accounts for different roles

## Alternative Commands

### Build Complete Test Environment
```bash
python manage.py build_test_env
```
This single command runs steps 1-4 automatically.

### Load Only Test Users (Without Database Reset)
```bash
python manage.py load_test_users --clear
```
Use when you want to refresh test users without resetting the entire database.

### Generate Simulated Data
```bash
python manage.py generate_sim_data
```
Creates simulated patient data for testing (if implemented).

## Cleaning Up Test Data

### Remove Uploaded Files
```bash
# Remove all uploaded CSV/TSV files
find storage/uploads -type f \( -name "*.csv" -o -name "*.tsv" \) -delete

# Remove all DuckDB files
find storage/uploads -type f -name "*.duckdb" -delete

# Remove all temporary files
rm -rf /tmp/audit_*
rm -rf /tmp/tmp*
```

### Clear Specific Tables
```python
# In Django shell
python manage.py shell

from depot.models import Audit, CohortSubmission, TemporaryFile
from django.contrib.auth import get_user_model

# Clear all audits
Audit.objects.all().delete()

# Clear all submissions
CohortSubmission.objects.all().delete()

# Clear temporary files
TemporaryFile.objects.all().delete()

# Clear test users only
User = get_user_model()
test_domains = ['@test.edu', '@va.gov', '@jh.edu', '@ucsd.edu', '@case.edu', '@uab.edu']
for domain in test_domains:
    User.objects.filter(email__endswith=domain).delete()
```

## Verification

### Check Database State
```bash
# Check if test users exist
python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print(f'Total users: {User.objects.count()}'); print('Test users:', list(User.objects.filter(email__endswith='@va.gov').values_list('email', flat=True)))"

# Check cohorts
python manage.py shell -c "from depot.models import Cohort; print(f'Total cohorts: {Cohort.objects.count()}')"

# Check groups
python manage.py shell -c "from django.contrib.auth.models import Group; print('Groups:', list(Group.objects.values_list('name', flat=True)))"
```

### Test SAML Configuration
```bash
./test_saml.sh
```

## Environment-Specific Notes

### Development
- Safe to use `reset_db` command
- Test users should be loaded for SAML testing
- Keep Docker IdP running for authentication

### Staging
- Use migrations instead of reset_db
- Be careful with data deletion
- Coordinate with team before refresh

### Production
- **NEVER** use reset_db
- Only use migrations for schema changes
- Data refresh requires approval and backup

## Troubleshooting

### Permission Denied
If you get permission errors:
```bash
# Check database user permissions
mysql -u naaccord -p -e "SHOW GRANTS;"
```

### Migration Errors
If migrations fail after reset:
```bash
# Remove migration files (development only!)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# Recreate migrations
python manage.py makemigrations
python manage.py migrate
```

### Test Users Not Authenticating
If SAML authentication fails after refresh:
1. Restart Docker IdP: `docker compose -f docker-compose.dev.yml restart mock-idp`
2. Clear browser cookies for localhost
3. Check environment variables: `source .env.docker-saml`

## Complete Refresh Script

Create a `refresh_db.sh` script for convenience:

```bash
#!/bin/bash

echo "==================================="
echo "NA-ACCORD Database Refresh"
echo "==================================="
echo ""
echo "WARNING: This will DELETE all data!"
echo "Press Ctrl+C to cancel, Enter to continue..."
read

# Load environment
source .env.docker-saml

# Reset database
echo "Step 1: Resetting database..."
python manage.py build_test_env

# Load test users
echo "Step 2: Loading test users..."
python manage.py load_test_users --clear

# Clean up uploads
echo "Step 3: Cleaning uploads directory..."
find storage/uploads -type f \( -name "*.csv" -o -name "*.tsv" -o -name "*.duckdb" \) -delete 2>/dev/null

# Verify
echo ""
echo "Database refresh complete!"
echo ""
echo "Verification:"
python manage.py shell -c "
from django.contrib.auth import get_user_model
from depot.models import Cohort
from django.contrib.auth.models import Group

User = get_user_model()
print(f'✓ Users: {User.objects.count()}')
print(f'✓ Cohorts: {Cohort.objects.count()}')
print(f'✓ Groups: {Group.objects.count()}')
print('')
print('Test accounts loaded:')
for email in ['admin@va.gov', 'admin@jh.edu', 'admin@test.edu']:
    if User.objects.filter(email=email).exists():
        print(f'  ✓ {email}')
"

echo ""
echo "To test SAML authentication:"
echo "  1. Visit http://localhost:8000/sign-in"
echo "  2. Use admin@va.gov or admin@jh.edu"
echo "  3. Password: admin"
```

Make it executable:
```bash
chmod +x refresh_db.sh
./refresh_db.sh
```