# Mock-IDP Setup Summary

## What Was Created

Complete SimpleSAMLphp mock IDP container for NA-ACCORD staging that exactly mimics JHU Shibboleth production configuration.

### Files Created

```
deploy/containers/mock-idp/
├── Dockerfile                           # SimpleSAMLphp container
├── README.md                            # Complete documentation
├── SETUP-SUMMARY.md                     # This file
├── generate-certs.sh                    # Certificate generation
├── cert/                                # Generated certificates
│   ├── idp.key                         # IDP private key
│   ├── idp.crt                         # IDP certificate
│   ├── sp-staging.key                  # SP private key (for vault)
│   └── sp-staging.crt                  # SP certificate (for vault)
├── config/
│   ├── config.php                      # SimpleSAMLphp main config
│   └── authsources.php                 # 7 test users with all SAML attributes
└── metadata/
    ├── saml20-idp-hosted.php           # IDP metadata
    └── saml20-sp-remote.php            # SP (NA-ACCORD) metadata

deploy/containers/
├── build-mock-idp.sh                    # Build script
├── push-mock-idp.sh                     # Push to GHCR
└── compose/
    └── mock-idp.yml                     # Docker Compose service definition
```

### Certificates Generated

✅ **IDP certificates** (self-signed, 10-year expiry):
- `/Users/erikwestlund/code/naaccord/deploy/containers/mock-idp/cert/idp.{key,crt}`
- Used by SimpleSAMLphp to sign SAML responses

✅ **SP certificates** (self-signed, 10-year expiry):
- `/Users/erikwestlund/code/naaccord/deploy/containers/mock-idp/cert/sp-staging.{key,crt}`
- Used by Django SAML to verify and sign requests

### Test Users Configured

| Username | Password | Role | Cohorts |
|----------|----------|------|---------|
| admin@jh.edu | password | site_admin | All |
| vacs.manager@jh.edu | password | cohort_manager | VACS / VACS8 |
| macs.user@jh.edu | password | cohort_user | MACS |
| wihs.user@jh.edu | password | cohort_user | WIHS |
| viewer@jh.edu | password | viewer | VACS, MACS |
| multi.cohort@jh.edu | password | cohort_user | VACS, MACS, WIHS |
| nocohort@jh.edu | password | viewer | None |

All users provide complete SAML attributes matching production.

## Configuration Matches Production Exactly

### Production (JHU Shibboleth)
```yaml
Entity ID: https://na-accord-depot.publichealth.jhu.edu
ACS URL: https://na-accord-depot.publichealth.jhu.edu/saml2/acs/
Metadata: JHU-provided XML
Certificates: JHU-issued (in vault)
Users: Real JHU accounts with Duo MFA
```

### Staging (Mock-IDP)
```yaml
Entity ID: https://naaccord.pequod.sh
ACS URL: https://naaccord.pequod.sh/saml2/acs/
Metadata: http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php
Certificates: Self-signed (need to add to vault)
Users: 7 test accounts (no MFA)
```

**Only differences are credentials and domain - architecture is identical.**

## Next Steps (What You Need To Do)

### 1. Add SP Certificates to Staging Vault

The SP certificates need to be in the staging vault for Ansible to deploy them.

**Option A: Regenerate staging vault (RECOMMENDED):**
```bash
cd /Users/erikwestlund/code/naaccord/deploy/scripts
./generate-vault.sh staging
```

When prompted:
- For "SAML SP Certificate", paste contents of:
  `/Users/erikwestlund/code/naaccord/deploy/containers/mock-idp/cert/sp-staging.crt`
- For "SAML SP Private Key", paste contents of:
  `/Users/erikwestlund/code/naaccord/deploy/containers/mock-idp/cert/sp-staging.key`

**Option B: Edit existing vault manually:**
```bash
ansible-vault edit deploy/ansible/inventories/staging/group_vars/all/vault.yml

# Add these sections at the bottom:
vault_saml_sp_cert: |
  -----BEGIN CERTIFICATE-----
  MIID5zCCAs+gAwIBAgIUTuNy/Yr6CrNLYaGVgZggULaFym0wDQYJKoZIhvcNAQEL
  ... (full contents of sp-staging.crt)
  -----END CERTIFICATE-----

vault_saml_sp_key: |
  -----BEGIN PRIVATE KEY-----
  MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCpReMqbUWvN3dV
  ... (full contents of sp-staging.key)
  -----END PRIVATE KEY-----
```

### 2. Update Staging Ansible to Deploy SAML Config

Update `deploy/ansible/inventories/staging/group_vars/all/main.yml`:

```yaml
# SAML Configuration (Mock IDP for staging)
saml_entity_id: "https://naaccord.pequod.sh"
saml_acs_url: "https://naaccord.pequod.sh/saml2/acs/"
saml_sls_url: "https://naaccord.pequod.sh/saml2/ls/"
saml_idp_metadata_url: "http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php"

# Use staging SP certificates
saml_sp_cert_file: "/opt/naaccord/depot/deploy/saml_certs/sp-staging.crt"
saml_sp_key_file: "/opt/naaccord/depot/deploy/saml_certs/sp-staging.key"
```

### 3. Build and Push Mock-IDP Container

```bash
cd /Users/erikwestlund/code/naaccord/deploy/containers
./build-mock-idp.sh
./push-mock-idp.sh
```

This pushes to `ghcr.io/jhbiostatcenter/naaccord/mock-idp:latest`

### 4. Update Staging Docker Compose

Add mock-idp to your main staging compose file, or reference it:

```bash
# Either create docker-compose.staging.yml with:
services:
  mock-idp:
    extends:
      file: deploy/containers/compose/mock-idp.yml
      service: mock-idp

# Or include it in your compose command:
docker compose \
  -f docker-compose.yml \
  -f deploy/containers/compose/mock-idp.yml \
  up -d
```

### 5. Deploy to Staging and Test

```bash
# On your staging server (or use Ansible)
cd /opt/naaccord/depot

# Pull latest images
docker compose pull

# Start services (including mock-idp)
docker compose up -d

# Verify mock-idp is running
docker logs naaccord-mock-idp
curl http://192.168.50.10:8080/simplesaml/

# Test SAML login
# Navigate to https://naaccord.pequod.sh/
# Click "Sign in with SAML"
# Login as: admin@jh.edu / password
```

## Testing Checklist

After deployment, verify:

- [ ] Mock-IDP container is running: `docker ps | grep mock-idp`
- [ ] Metadata endpoint accessible: `curl http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php`
- [ ] Django can reach mock-idp metadata
- [ ] SAML login redirects to mock-idp
- [ ] Can login with test user (admin@jh.edu / password)
- [ ] User attributes appear in Django session
- [ ] Cohort access works correctly
- [ ] Role-based permissions work
- [ ] Logout works

## Troubleshooting Commands

```bash
# Check mock-idp logs
docker logs naaccord-mock-idp -f

# Test metadata endpoint
curl http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php | xmllint --format -

# Check Django SAML config
docker exec naaccord-web python manage.py shell
>>> from django.conf import settings
>>> settings.USE_DOCKER_SAML  # Should be True
>>> settings.SAML_CONFIG['metadata']  # Should show mock-idp URL

# Check SP certificates deployed
docker exec naaccord-web ls -la /opt/naaccord/depot/deploy/saml_certs/
```

## Why This Matches Production

1. **Same SAML Flow**: Authentication flow is identical - Django → IDP → Django
2. **Same Attributes**: All SAML attributes match production (email, roles, cohorts, etc.)
3. **Same Django Config**: Django SAML backend is configured identically
4. **Same Certificates**: Both use X.509 certificates (just different issuers)
5. **Same Metadata**: Both use SAML 2.0 metadata XML format

**Only differences:**
- Credential source (JHU AD vs static user list)
- Certificate authority (JHU vs self-signed)
- Domain names

This ensures **staging behaves exactly like production** for SAML authentication.

## Questions?

See the complete documentation in `README.md` in this directory, or:

- Check SimpleSAMLphp docs: https://simplesamlphp.org/docs/stable/
- Review Django SAML backend: `depot/auth/saml_backend.py`
- Check Ansible SAML role: `deploy/ansible/roles/saml/`
