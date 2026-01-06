# SAML Authentication Testing Guide

## Overview

This guide documents how to test SAML authentication in the NA-ACCORD development environment using Docker SimpleSAMLphp IdP.

## Prerequisites

### 1. Environment Setup

Ensure your `.env` file has these settings:

```bash
# Enable Docker SAML Authentication
USE_DOCKER_SAML=true
USE_MOCK_SAML=false

# SAML Configuration
SAML_ENTITY_ID=http://localhost:8000
SAML_ACS_URL=http://localhost:8000/saml2/acs/
SAML_SLS_URL=http://localhost:8000/saml2/ls/
SAML_IDP_METADATA_URL=http://localhost:8080/simplesaml/saml2/idp/metadata.php
```

### 2. Docker Services

Start the required Docker services:

```bash
# Start all development services
docker-compose -f docker-compose.dev.yml up -d

# Or just the IdP
docker-compose -f docker-compose.dev.yml up -d mock-idp
```

Verify the IdP is running:
```bash
docker ps | grep mock-idp
# Should show: naaccord-mock-idp running on ports 8080 and 8443
```

### 3. Django Services

Start Django with the development server:

```bash
# Activate virtual environment
source venv/bin/activate

# Start Django
python manage.py runserver

# In separate terminals:
npm run watch  # Frontend assets
celery -A depot worker  # Background tasks
```

## Test User Accounts

The Docker IdP is configured with multiple test users representing different roles and institutions:

### Administrative Users

| Email | Password | Role | Cohorts | Description |
|-------|----------|------|---------|-------------|
| `admin@test.edu` | `admin` | Admin | 1, 2, 3 | Full system administrator |
| `admin@va.gov` | `admin` | Admin | 18 (VACS) | VA administrator |
| `admin@jh.edu` | `admin` | Researcher | 5 (JHHCC) | Johns Hopkins researcher |

### Research & Coordination Users

| Email | Password | Role | Cohorts | Description |
|-------|----------|------|---------|-------------|
| `researcher@test.edu` | `researcher` | Researcher | 1 | Single cohort researcher |
| `coordinator@test.edu` | `coordinator` | Coordinator | 2 | Cohort coordinator |
| `viewer@test.edu` | `viewer` | Viewer | 5 | Read-only access |

### Institution-Specific Users

| Email | Password | Institution | Cohort |
|-------|----------|-------------|--------|
| `user@jhu.edu` | `jhu123` | Johns Hopkins | 5 |
| `user@ucsd.edu` | `ucsd123` | UC San Diego | 13 |
| `user@case.edu` | `case123` | Case Western | 7 |
| `user@uab.edu` | `uab123` | UAB | 8 |

## Testing Workflow

### Step 1: Access the Application

1. Open browser to `http://localhost:8000`
2. You should be redirected to `/sign-in`

### Step 2: Initiate SAML Login

1. Enter an email from the test users above (e.g., `admin@test.edu`)
2. Click "Sign In"
3. You should be redirected to the SimpleSAMLphp login page at `http://localhost:8080`

### Step 3: Authenticate at IdP

1. On the SimpleSAMLphp login page, enter:
   - **Username**: The full email (e.g., `admin@test.edu`)
   - **Password**: The corresponding password (e.g., `admin`)
2. Click "Login"

### Step 4: Return to Application

After successful authentication:
1. You'll be redirected back to `http://localhost:8000/saml2/acs/`
2. The SAML assertion will be processed
3. You'll be logged into the application
4. Check that user attributes are correctly populated

### Step 5: Verify User Creation

Check the Django admin or shell:

```python
python manage.py shell
from depot.models import User, CohortMembership

# Check if user was created
user = User.objects.get(email='admin@test.edu')
print(f"User: {user.email}")
print(f"Name: {user.first_name} {user.last_name}")
print(f"Staff: {user.is_staff}")

# Check cohort memberships
memberships = CohortMembership.objects.filter(user=user)
for m in memberships:
    print(f"Cohort: {m.cohort.name}")
```

## Testing Different Scenarios

### 1. First-Time User Login

Test with a user that doesn't exist in Django yet:
- Use any test account
- Verify user is created with correct attributes
- Check cohort memberships are assigned

### 2. Existing User Login

Test with a user that already exists:
- Login once to create the user
- Logout (`/sign-out`)
- Login again
- Verify attributes are updated (if changed in IdP)

### 3. Multiple Cohort Access

Test with `admin@test.edu` who has access to cohorts 1, 2, and 3:
- Login and verify all cohort memberships are created
- Check user can access data from all assigned cohorts

### 4. Single Cohort Access

Test with `researcher@test.edu` who has access to only cohort 1:
- Login and verify only one cohort membership
- Verify user cannot access other cohorts' data

### 5. Invalid Credentials

Test authentication failure:
- Enter valid email but wrong password
- Should remain on IdP login page with error

### 6. Logout Flow

Test SAML logout:
1. Login successfully
2. Navigate to `/sign-out`
3. Should clear Django session
4. Optional: Can implement full SAML logout to also logout from IdP

## Troubleshooting

### Common Issues and Solutions

#### 1. "secretsalt" Configuration Error

**Error**: `The "secretsalt" configuration option must be set to a secret value`

**Solution**: The secretsalt is configured via environment variable in `docker-compose.dev.yml`:
```bash
# Recreate the container to apply environment changes
docker-compose -f docker-compose.dev.yml down mock-idp
docker-compose -f docker-compose.dev.yml up -d mock-idp

# Verify environment variable is set
docker exec naaccord-mock-idp printenv | grep SIMPLESAMLPHP_SECRET_SALT
```

#### 2. Redirect Loop to /sign-in

**Error**: After entering email, browser returns to /sign-in instead of IdP

**Causes & Solutions**:
- Check `SignedInMiddleware` excludes `/saml2/` paths
- Verify `SamlSessionMiddleware` is installed
- Ensure `USE_DOCKER_SAML=true` in environment

#### 3. 500 Error on /saml2/login/

**Error**: Internal server error when accessing SAML login

**Solution**: Check Django logs for specific error:
```bash
# Common issues:
# - Missing middleware
# - Metadata fetch failure
# - Configuration errors
```

#### 4. User Not Created After Login

**Error**: SAML login succeeds but user not in Django

**Checks**:
- Verify `SAML_CREATE_UNKNOWN_USER = True` in settings
- Check `SAMLBackend` is in `AUTHENTICATION_BACKENDS`
- Review Django logs for backend errors

#### 5. Cohort Memberships Not Created

**Error**: User created but no cohort access

**Checks**:
- Verify cohorts exist in database with correct IDs
- Check SAML assertion includes `cohortAccess` attribute
- Review `SAMLBackend._update_cohort_memberships()` logs

### Debug Commands

```bash
# Test SAML configuration
python manage.py shell -c "
from djangosaml2.utils import available_idps
from djangosaml2.conf import get_config
conf = get_config()
print('Available IDPs:', available_idps(conf))
"

# Test metadata fetch
curl http://localhost:8080/simplesaml/saml2/idp/metadata.php

# Check SAML login redirect
curl -I http://localhost:8000/saml2/login/

# View Docker IdP logs
docker logs naaccord-mock-idp --tail 50

# Test direct auth request creation
python manage.py shell -c "
from djangosaml2.conf import get_config
from saml2.client import Saml2Client
from saml2 import BINDING_HTTP_REDIRECT

conf = get_config()
client = Saml2Client(conf)
idp = 'http://localhost:8080/simplesaml/saml2/idp/metadata.php'

reqid, info = client.prepare_for_authenticate(
    entityid=idp,
    relay_state='/',
    binding=BINDING_HTTP_REDIRECT,
)
print('Auth request created:', reqid)
"
```

### Viewing SAML Assertions

To see the actual SAML assertion data:

1. Enable debug logging in Django:
```python
LOGGING = {
    'loggers': {
        'djangosaml2': {
            'level': 'DEBUG',
        },
        'saml2': {
            'level': 'DEBUG',
        },
    }
}
```

2. Check Django logs during authentication to see assertion attributes

## Configuration Files Reference

### Key Configuration Files

1. **Django Settings**: `depot/settings.py`
   - SAML_CONFIG dictionary
   - Authentication backends
   - Middleware configuration

2. **Docker IdP Config**: `deploy/containers/saml-idp/`
   - `config.php` - SimpleSAMLphp configuration
   - `authsources.php` - Test user definitions
   - `saml20-sp-remote.php` - Service Provider metadata

3. **Environment**: `.env`
   - USE_DOCKER_SAML flag
   - SAML URLs and entity IDs

4. **Middleware**: `depot/middleware/signed_in.py`
   - Must exclude `/saml2/` paths

5. **Backend**: `depot/auth/saml_backend.py`
   - User creation/update logic
   - Attribute mapping
   - Cohort membership assignment

## Production Considerations

When moving to production with real Shibboleth:

1. **Update metadata URL** to point to institutional IdP
2. **Use HTTPS** for all URLs (entity ID, ACS, etc.)
3. **Rotate certificates** in `saml_certs/`
4. **Change secret salt** in IdP configuration
5. **Implement proper session timeout**
6. **Enable signature verification**
7. **Configure attribute release policies** with institutions
8. **Test with real institutional accounts**
9. **Implement audit logging** for authentication events
10. **Set up monitoring** for IdP availability

## Automated Testing

For CI/CD, you can automate SAML testing:

```python
# tests/test_saml_auth.py
from django.test import TestCase, Client
from unittest.mock import patch, MagicMock

class SAMLAuthenticationTest(TestCase):
    def setUp(self):
        self.client = Client()
    
    @patch('djangosaml2.views.LoginView.post')
    def test_saml_login_redirect(self, mock_post):
        """Test that sign-in redirects to SAML login"""
        response = self.client.post('/sign-in', {
            'email': 'test@test.edu'
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/saml2/login/', response.url)
    
    @patch('depot.auth.saml_backend.SAMLBackend.authenticate')
    def test_saml_user_creation(self, mock_auth):
        """Test user creation from SAML assertion"""
        mock_auth.return_value = User.objects.create_user(
            email='test@test.edu',
            username='test_user'
        )
        # Test assertion processing
        # ...
```

## Additional Resources

- [SimpleSAMLphp Documentation](https://simplesamlphp.org/docs/stable/)
- [djangosaml2 Documentation](https://djangosaml2.readthedocs.io/)
- [SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html)
- [Shibboleth Documentation](https://www.shibboleth.net/)