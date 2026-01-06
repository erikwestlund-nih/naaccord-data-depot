# Test Accounts for SAML Authentication

## Overview
The NA-ACCORD application now has comprehensive test accounts configured for development testing with Docker SAML IdP.

## Primary Test Accounts

### VA Admin Account
- **Email**: admin@va.gov
- **Password**: admin
- **Cohort Access**: VACS / VACS8 (ID: 18)
- **Groups**: Data Managers
- **Role**: Admin with staff privileges
- **Use Case**: Testing VA administrator workflows and data management

### Johns Hopkins Researcher
- **Email**: admin@jh.edu  
- **Password**: admin
- **Cohort Access**: JHHCC (ID: 5)
- **Groups**: Researchers
- **Role**: Researcher (non-admin)
- **Use Case**: Testing researcher workflows and cohort-specific access

## Additional Test Accounts

| Email | Password | Cohorts | Groups | Role |
|-------|----------|---------|--------|------|
| admin@test.edu | admin | VACS/VACS8, JHHCC, UCSD | - | Super Admin |
| researcher@test.edu | researcher | JHHCC | Researchers | Researcher |
| coordinator@test.edu | coordinator | VACS/VACS8 | Coordinators | Coordinator |
| viewer@test.edu | viewer | JHHCC | Viewers | Viewer (read-only) |
| user@ucsd.edu | ucsd123 | UCSD | - | Member |
| user@case.edu | case123 | CWRU | - | Member |
| user@uab.edu | uab123 | UA-Birmingham | - | Member |

## Testing the Authentication Flow

1. **Ensure Docker IdP is running**:
   ```bash
   docker compose -f docker-compose.dev.yml up mock-idp
   ```

2. **Load environment and start Django**:
   ```bash
   source .env.docker-saml
   python manage.py runserver
   ```

3. **Visit the sign-in page**:
   - Go to http://localhost:8000/sign-in
   - Enter one of the test email addresses
   - Click "Continue with your institution"

4. **SAML IdP Login**:
   - You'll be redirected to the mock IdP at http://localhost:8080
   - Enter the corresponding password for the test account
   - You'll be redirected back to the application, authenticated

## Management Commands

### Load Test Users
```bash
python manage.py load_test_users --clear
```
This command:
- Clears existing test users (optional with --clear flag)
- Loads users from CSV fixtures in `depot/fixtures/test_users/`
- Creates group memberships
- Assigns cohort access

### Verify Setup
```bash
./test_saml.sh
```
This script checks:
- Environment variables are set correctly
- Django SAML configuration
- Docker IdP is running
- Lists available test accounts

## Technical Implementation

### CSV Fixtures
Test data is stored in CSV files for easy management:
- `users.csv` - User accounts
- `groups.csv` - Django auth groups  
- `user_groups.csv` - User-to-group mappings
- `cohort_memberships.csv` - User-to-cohort assignments

### SAML Attributes
The SAML IdP provides these attributes:
- `email` - User's email address
- `givenName` / `sn` - First and last name
- `cohortAccess` - Array of cohort IDs
- `naaccordRole` - User's role (admin, researcher, etc.)
- `groups` - Array of group names
- `organization` - User's organization

### Authentication Backend
The `SAMLBackend` class handles:
- Processing SAML assertions
- Creating/updating user accounts
- Assigning cohort memberships
- Managing group assignments
- Setting admin/staff privileges based on role

## Troubleshooting

### IdP Not Running
If you see "IdP not responding" in the test script:
```bash
docker compose -f docker-compose.dev.yml up mock-idp
```

### Port Conflicts
The application uses:
- Port 8000 - Django development server
- Port 8080 - SimpleSAMLphp IdP
- Port 3306 - MariaDB database

### Missing Dependencies
If SAML authentication fails:
```bash
brew install xmlsec1  # macOS
pip install djangosaml2 pysaml2
```

### Database Issues
Reset test users:
```bash
python manage.py load_test_users --clear
```