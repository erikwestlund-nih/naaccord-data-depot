# Mock IDP Container for NA-ACCORD Staging

SimpleSAMLphp container that mimics JHU Shibboleth IDP for SAML testing in staging environment.

## Overview

The mock-idp container provides a **complete SAML 2.0 Identity Provider** for staging, eliminating the need for real JHU Shibboleth credentials during development and testing. It provides the exact same SAML attributes as production but uses self-signed certificates and predefined test users.

**Production vs Staging SAML:**

| Component | Production | Staging (mock-idp) |
|-----------|-----------|-------------------|
| IDP | JHU Shibboleth (login.jh.edu) | SimpleSAMLphp container |
| Certificates | JHU-issued (in vault) | Self-signed (generated locally) |
| Users | Real JHU accounts | Predefined test users |
| Metadata | From JHU | From container |
| DNS | na-accord-depot.publichealth.jhu.edu | naaccord.pequod.sh |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Staging Environment (192.168.50.x)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐         ┌──────────────────┐        │
│  │ Mock IDP         │         │ NA-ACCORD Web    │        │
│  │ (SimpleSAMLphp)  │◄────────┤ (Django + SAML)  │        │
│  │                  │  SAML   │                  │        │
│  │ Port: 8080       │  Flow   │ Port: 443        │        │
│  │                  │─────────►│                  │        │
│  └──────────────────┘         └──────────────────┘        │
│                                                             │
│  Test Users:                   Entity ID:                  │
│  - admin@jh.edu               https://naaccord.pequod.sh   │
│  - vacs.manager@jh.edu                                     │
│  - macs.user@jh.edu           Metadata URL:                │
│  - (see authsources.php)      http://192.168.50.10:8080/   │
│                               simplesaml/saml2/idp/        │
│                               metadata.php                 │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Generate Certificates (One-time)

```bash
cd /Users/erikwestlund/code/naaccord/deploy/containers/mock-idp
./generate-certs.sh
```

This creates:
- `cert/idp.{key,crt}` - IDP signing certificate
- `cert/sp-staging.{key,crt}` - Service Provider certificate for staging

### 2. Add SP Certificates to Staging Vault

The SP certificates need to be in the staging vault for Django to use them.

**Option A: Regenerate entire staging vault:**
```bash
cd /Users/erikwestlund/code/naaccord/deploy/scripts
./generate-vault.sh staging
# When prompted for SAML SP cert, paste contents of cert/sp-staging.crt
# When prompted for SAML SP key, paste contents of cert/sp-staging.key
```

**Option B: Manually edit existing vault:**
```bash
# Decrypt vault
ansible-vault edit deploy/ansible/inventories/staging/group_vars/all/vault.yml

# Add these entries:
vault_saml_sp_cert: |
  -----BEGIN CERTIFICATE-----
  <contents of cert/sp-staging.crt>
  -----END CERTIFICATE-----

vault_saml_sp_key: |
  -----BEGIN PRIVATE KEY-----
  <contents of cert/sp-staging.key>
  -----END PRIVATE KEY-----
```

### 3. Build and Push Container

```bash
cd /Users/erikwestlund/code/naaccord/deploy/containers
./build-mock-idp.sh
./push-mock-idp.sh
```

### 4. Deploy to Staging

The mock-idp is included in staging docker-compose. Deploy with:

```bash
# On staging server
cd /opt/naaccord/depot
docker compose -f deploy/containers/compose/mock-idp.yml pull
docker compose -f deploy/containers/compose/mock-idp.yml up -d
```

Or use the main staging compose:
```bash
docker compose -f docker-compose.staging.yml up -d
```

### 5. Test SAML Login

1. Navigate to https://naaccord.pequod.sh/
2. Click "Sign in with SAML"
3. You'll be redirected to mock-idp login page
4. Login with any test user (see below)
5. You'll be redirected back to NA-ACCORD with SAML attributes

## Test Users

All test users use password: `password`

| Username | Role | Cohorts | Description |
|----------|------|---------|-------------|
| admin@jh.edu | site_admin | All | System administrator |
| vacs.manager@jh.edu | cohort_manager | VACS / VACS8 | Can manage VACS data |
| macs.user@jh.edu | cohort_user | MACS | Can upload/view MACS data |
| wihs.user@jh.edu | cohort_user | WIHS | Can upload/view WIHS data |
| viewer@jh.edu | viewer | VACS, MACS | Read-only access |
| multi.cohort@jh.edu | cohort_user | VACS, MACS, WIHS | Multi-cohort access |
| nocohort@jh.edu | viewer | None | No cohort access (for auth testing) |

**Note:** Production users (real names/emails) are configured via JHU Shibboleth in production, not in this mock-idp.

**SAML Attributes Provided:**
- `uid` - User ID
- `eduPersonPrincipalName` - Principal name (username@jh.edu)
- `email` - Email address
- `displayName` - Full name
- `givenName` - First name
- `sn` - Last name
- `eduPersonAffiliation` - Affiliations (employee, staff, faculty, etc.)
- `cohortAccess` - Comma-separated list of cohort names
- `naaccordRole` - Role (site_admin, cohort_manager, cohort_user, viewer)
- `organization` - Organization name

## Configuration Files

### Directory Structure

```
mock-idp/
├── Dockerfile                     # Container definition
├── README.md                      # This file
├── generate-certs.sh              # Certificate generation script
├── cert/                          # Certificates (git-ignored)
│   ├── idp.key                   # IDP private key (self-signed)
│   ├── idp.crt                   # IDP certificate
│   ├── sp-staging.key            # SP private key (for Django)
│   └── sp-staging.crt            # SP certificate (for Django)
├── config/                        # SimpleSAMLphp configuration
│   ├── config.php                # Main configuration
│   └── authsources.php           # Test user definitions
└── metadata/                      # SAML metadata
    ├── saml20-idp-hosted.php     # IDP metadata (this server)
    └── saml20-sp-remote.php      # SP metadata (NA-ACCORD)
```

### Key Configuration Points

**IDP Metadata URL:**
```
http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php
```

**SP Entity ID (NA-ACCORD):**
```
https://naaccord.pequod.sh
```

**SP ACS URL (where SAML responses go):**
```
https://naaccord.pequod.sh/saml2/acs/
```

**SP SLS URL (logout):**
```
https://naaccord.pequod.sh/saml2/ls/
```

## Django Configuration

Django needs these environment variables to use mock-idp:

```bash
# Use Docker SAML (not mock SAML backend)
USE_DOCKER_SAML=true
USE_MOCK_SAML=false

# SAML configuration
SAML_ENTITY_ID=https://naaccord.pequod.sh
SAML_ACS_URL=https://naaccord.pequod.sh/saml2/acs/
SAML_SLS_URL=https://naaccord.pequod.sh/saml2/ls/
SAML_IDP_METADATA_URL=http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php

# SP certificates (deployed by Ansible from vault)
SAML_CERT_FILE=/opt/naaccord/depot/deploy/saml_certs/sp-staging.crt
SAML_KEY_FILE=/opt/naaccord/depot/deploy/saml_certs/sp-staging.key
```

## Ansible Deployment

The SAML role deploys certificates and metadata for both production and staging:

**For staging (with mock-idp):**
1. Reads `vault_saml_sp_cert` and `vault_saml_sp_key` from vault
2. Deploys to `/opt/naaccord/depot/deploy/saml_certs/sp-staging.{crt,key}`
3. Django reads these files via `SAML_CERT_FILE` and `SAML_KEY_FILE`

**For production (with JHU Shibboleth):**
1. Uses production certificates in vault
2. Deploys to `/opt/naaccord/depot/deploy/saml_certs/sp-prod.{crt,key}`
3. Reads JHU metadata from template

## Troubleshooting

### Mock-IDP not accessible

```bash
# Check if container is running
docker ps | grep mock-idp

# View logs
docker logs naaccord-mock-idp

# Test endpoint
curl http://192.168.50.10:8080/simplesaml/
```

### SAML login fails

```bash
# Check Django SAML configuration
docker exec naaccord-web python manage.py shell
>>> from django.conf import settings
>>> print(settings.SAML_CONFIG)

# Verify metadata URL is accessible
curl http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php
```

### Certificate errors

```bash
# Regenerate certificates
cd /Users/erikwestlund/code/naaccord/deploy/containers/mock-idp
rm -rf cert/
./generate-certs.sh

# Update vault with new SP certificates
# Rebuild and redeploy
```

### User attributes not appearing in Django

Check `config/authsources.php` - attributes must match Django's expectations:
- Email is REQUIRED
- eduPersonPrincipalName is REQUIRED
- cohortAccess and naaccordRole are optional but recommended

## Security Notes

⚠️ **This is for STAGING ONLY**

- Self-signed certificates are NOT suitable for production
- Test users have hardcoded passwords
- No rate limiting or brute force protection
- Admin interface is not password-protected
- Debug mode is enabled

**Never use mock-idp in production.**

## Differences from Production

| Feature | Mock-IDP (Staging) | JHU Shibboleth (Production) |
|---------|-------------------|----------------------------|
| Authentication | Static user list | JHU Active Directory |
| Certificates | Self-signed | JHU-issued |
| Metadata | Container | JHU enterprise |
| Users | 7 test accounts | All JHU employees/students |
| MFA | None | JHU Duo required |
| Password Policy | None | JHU enterprise policy |
| Session Duration | 8 hours | JHU policy |
| Logout | Local only | JHU global logout |

## Maintenance

### Adding New Test Users

Edit `config/authsources.php` and add to the `example-userpass` array:

```php
'newuser@jh.edu:password' => [
    'uid' => ['newuser'],
    'eduPersonPrincipalName' => ['newuser@jh.edu'],
    'email' => ['newuser@jh.edu'],
    'displayName' => ['New User'],
    'givenName' => ['New'],
    'sn' => ['User'],
    'eduPersonAffiliation' => ['member'],
    'cohortAccess' => ['VACS / VACS8'],
    'naaccordRole' => ['cohort_user'],
    'organization' => ['Test Organization'],
],
```

Rebuild and redeploy container for changes to take effect.

### Updating SimpleSAMLphp Version

Edit `Dockerfile` and change `SIMPLESAMLPHP_VERSION`:

```dockerfile
ENV SIMPLESAMLPHP_VERSION=2.3.5  # Update version here
```

Rebuild and test thoroughly before deploying.

## Related Documentation

- **[deploy/ansible/roles/saml/README.md](../../ansible/roles/saml/README.md)** - SAML Ansible role
- **[docs/deployment/guides/saml-configuration.md](../../../docs/deployment/guides/saml-configuration.md)** - SAML architecture
- **[depot/auth/saml_backend.py](../../../depot/auth/saml_backend.py)** - Django SAML backend

## Support

For issues with mock-idp:
1. Check container logs: `docker logs naaccord-mock-idp`
2. Verify certificates exist: `ls -la cert/`
3. Test metadata endpoint: `curl http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php`
4. Review Django SAML settings in `depot/settings.py`

For SimpleSAMLphp documentation:
- https://simplesamlphp.org/docs/stable/
