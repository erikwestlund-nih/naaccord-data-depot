# SAML Authentication Configuration

**Purpose:** Configure SAML authentication for staging (mock IDP) and production (JHU Shibboleth).

**Last Updated:** 2025-10-03

---

## Overview

NA-ACCORD uses SAML 2.0 for authentication with environment-specific Identity Providers (IDPs):

- **Staging/Test:** Mock SAML IDP container (SimpleSAMLphp)
- **Production:** JHU Shibboleth Enterprise IDP

This allows testing the complete SAML workflow without requiring VPN access to production systems.

---

## Architecture

### Staging Environment

```
┌─────────────────────┐
│ Web Browser         │
└──────────┬──────────┘
           │ 1. Access app
           ↓
┌─────────────────────┐
│ NA-ACCORD Web       │
│ (Django + SAML SP)  │
└──────────┬──────────┘
           │ 2. Redirect to IDP
           ↓
┌─────────────────────┐
│ Mock IDP Container  │
│ (SimpleSAMLphp)     │
│ Port 8080/8443      │
└──────────┬──────────┘
           │ 3. SAML Response
           ↓
┌─────────────────────┐
│ NA-ACCORD Web       │
│ (User logged in)    │
└─────────────────────┘
```

### Production Environment

```
┌─────────────────────┐
│ Web Browser         │
└──────────┬──────────┘
           │ 1. Access app
           ↓
┌─────────────────────┐
│ NA-ACCORD Web       │
│ (Django + SAML SP)  │
└──────────┬──────────┘
           │ 2. Redirect to IDP
           ↓
┌─────────────────────┐
│ JHU Shibboleth      │
│ idp.jh.edu          │
│ (Enterprise IDP)    │
└──────────┬──────────┘
           │ 3. SAML Response
           ↓
┌─────────────────────┐
│ NA-ACCORD Web       │
│ (User logged in)    │
└─────────────────────┘
```

---

## Mock IDP Configuration (Staging)

### Docker Compose Profile

The mock IDP is defined in `docker-compose.prod.yml` with the `staging-idp` profile:

```yaml
mock-idp:
  image: kristophjunge/test-saml-idp:1.15
  container_name: naaccord-mock-idp
  profiles: ["staging-idp"]  # Only runs when explicitly enabled
  ports:
    - "8080:8080"  # HTTP
    - "8443:8443"  # HTTPS
  environment:
    - SIMPLESAMLPHP_SP_ENTITY_ID=${SAML_SP_ENTITY_ID}
    - SIMPLESAMLPHP_SP_ASSERTION_CONSUMER_SERVICE=${SAML_SP_ACS_URL}
    - SIMPLESAMLPHP_IDP_BASEURLPATH=${SAML_IDP_BASE_URL}
  volumes:
    - ./saml/docker-idp/config.php:/var/www/simplesamlphp/config/config.php:ro
    - ./saml/docker-idp/authsources.php:/var/www/simplesamlphp/config/authsources.php:ro
    - ./saml/docker-idp/saml20-sp-remote.php:/var/www/simplesamlphp/metadata/saml20-sp-remote.php:ro
```

### Starting Mock IDP

**In staging, start the mock IDP alongside the web server:**

```bash
# On staging web server
cd /opt/naaccord/depot

# Start web profile WITH mock IDP
docker compose -f docker-compose.prod.yml \
  --profile web \
  --profile staging-idp \
  up -d

# Verify mock IDP is running
docker ps --filter name=mock-idp
# Expected: naaccord-mock-idp running on ports 8080/8443

# Test IDP metadata
curl http://localhost:8080/simplesaml/saml2/idp/metadata.php
# Should return XML SAML metadata
```

### Ansible Deployment (Staging)

The Ansible playbook automatically handles this:

```bash
# On staging web server
cd /opt/naaccord/depot/deploy/ansible

# Deploy web stack with mock IDP
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging

# The docker_services role will:
# 1. Generate .env with USE_MOCK_SAML=True
# 2. Start containers with both 'web' and 'staging-idp' profiles
```

### Environment Variables (Staging)

**Automatically set by Ansible in staging:**

```bash
# Generated in /opt/naaccord/depot/.env
USE_MOCK_SAML=True
SAML_SP_ENTITY_ID=https://naaccord.pequod.sh
SAML_SP_ACS_URL=https://naaccord.pequod.sh/saml2/acs/
SAML_IDP_METADATA_URL=http://localhost:8080/simplesaml/saml2/idp/metadata.php
SAML_IDP_BASE_URL=http://localhost:8080/simplesaml/
```

### Test Users (Mock IDP)

The mock IDP comes with pre-configured test users:

| Username | Password | Email | Groups |
|----------|----------|-------|--------|
| user1 | user1pass | user1@example.com | naaccord_users |
| user2 | user2pass | user2@example.com | naaccord_users |
| admin1 | admin1pass | admin1@example.com | naaccord_admins |

**To add more test users:**

Edit `saml/docker-idp/authsources.php`:

```php
'example-userpass' => [
    'exampleauth:UserPass',
    'newuser:newpassword' => [
        'uid' => ['newuser'],
        'eduPersonAffiliation' => ['member', 'employee'],
        'email' => 'newuser@example.com',
        'groups' => ['naaccord_users'],
    ],
],
```

Then restart mock IDP:

```bash
docker restart naaccord-mock-idp
```

---

## Production IDP Configuration (JHU Shibboleth)

### Environment Variables (Production)

**Automatically set by Ansible in production:**

```bash
# Generated in /opt/naaccord/depot/.env
USE_MOCK_SAML=False
SAML_SP_ENTITY_ID=https://mrpznaaccordweb01.hosts.jhmi.edu
SAML_SP_ACS_URL=https://mrpznaaccordweb01.hosts.jhmi.edu/saml2/acs/
SAML_IDP_METADATA_URL=https://idp.jh.edu/idp/shibboleth
# SAML_IDP_BASE_URL not needed for Shibboleth
```

### JHU IT Coordination

**Required steps before production deployment:**

1. **Generate SP metadata:**
   ```bash
   # On production web server (after deployment)
   docker exec naaccord-web python manage.py saml_metadata
   ```

2. **Send SP metadata to JHU IT:**
   - Entity ID: `https://mrpznaaccordweb01.hosts.jhmi.edu`
   - ACS URL: `https://mrpznaaccordweb01.hosts.jhmi.edu/saml2/acs/`
   - Contact: [Your email]

3. **Request attribute release:**
   - `uid` (required)
   - `email` (required)
   - `displayName` (required)
   - `eduPersonAffiliation` (optional)
   - `isMemberOf` or `eduPersonEntitlement` (for group mapping)

4. **Verify IDP metadata URL:**
   - Confirm: `https://idp.jh.edu/idp/shibboleth`
   - Or get correct URL from JHU IT

5. **Test in staging first:**
   - JHU IT may provide a test Shibboleth IDP
   - Update `production/hosts.yml` with test IDP URL
   - Deploy to staging for validation

### Starting Production Web (No Mock IDP)

```bash
# On production web server
cd /opt/naaccord/depot

# Start ONLY web profile (no staging-idp)
docker compose -f docker-compose.prod.yml \
  --profile web \
  up -d

# Verify mock IDP is NOT running
docker ps --filter name=mock-idp
# Expected: No containers (mock IDP only runs in staging)
```

### Ansible Deployment (Production)

```bash
# On production web server
cd /opt/naaccord/depot/deploy/ansible

# Deploy web stack WITHOUT mock IDP
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production

# The docker_services role will:
# 1. Generate .env with USE_MOCK_SAML=False
# 2. Start containers with ONLY 'web' profile (no staging-idp)
```

---

## Configuration Files

### Inventory Variables

**Staging (`inventories/staging/hosts.yml`):**

```yaml
vars:
  environment: staging
  domain: naaccord.pequod.sh

  # SAML Configuration (Mock IDP for staging)
  saml_sp_entity_id: "https://{{ domain }}"
  saml_sp_acs_url: "https://{{ domain }}/saml2/acs/"
  saml_idp_metadata_url: "http://localhost:8080/simplesaml/saml2/idp/metadata.php"
  saml_idp_base_url: "http://localhost:8080/simplesaml/"
```

**Production (`inventories/production/hosts.yml`):**

```yaml
vars:
  environment: production
  domain: mrpznaaccordweb01.hosts.jhmi.edu

  # SAML Configuration (JHU Shibboleth for production)
  saml_sp_entity_id: "https://{{ domain }}"
  saml_sp_acs_url: "https://{{ domain }}/saml2/acs/"
  saml_idp_metadata_url: "https://idp.jh.edu/idp/shibboleth"
  # saml_idp_base_url not needed for Shibboleth
```

### Docker Compose Profiles

**Profile combinations:**

```bash
# Staging web + mock IDP
--profile web --profile staging-idp

# Production web (no mock IDP)
--profile web

# Services server (no IDP needed)
--profile services
```

---

## Testing SAML Authentication

### Staging Testing

1. **Access application:**
   ```
   https://naaccord.pequod.sh/
   ```

2. **Click "Sign In"** - Should redirect to mock IDP

3. **Login page shows:**
   ```
   SimpleSAMLphp Authentication
   Username: [user1]
   Password: [user1pass]
   ```

4. **After login** - Redirected back to NA-ACCORD as authenticated user

5. **Verify user attributes:**
   ```bash
   docker exec naaccord-web python manage.py shell
   >>> from django.contrib.auth import get_user_model
   >>> User = get_user_model()
   >>> user = User.objects.get(username='user1')
   >>> print(user.email)
   user1@example.com
   ```

### Production Testing

1. **Access application:**
   ```
   https://mrpznaaccordweb01.hosts.jhmi.edu/
   ```

2. **Click "Sign In"** - Should redirect to JHU Shibboleth

3. **JHU login page shows:**
   ```
   Johns Hopkins University
   JHED ID: [your_jhed]
   Password: [your_password]
   Duo 2FA: [push/code]
   ```

4. **After login** - Redirected back to NA-ACCORD as authenticated user

5. **Verify attributes:**
   - Check that JHED ID becomes username
   - Email matches JHU email
   - Group memberships properly mapped

---

## Troubleshooting

### Mock IDP Not Starting

**Problem:** `naaccord-mock-idp` container not running

**Check:**
```bash
# Verify profile is active
docker compose -f docker-compose.prod.yml config --profiles
# Should show: staging-idp

# Check logs
docker logs naaccord-mock-idp

# Verify environment is staging
cat /opt/naaccord/depot/.env | grep USE_MOCK_SAML
# Expected: USE_MOCK_SAML=True
```

### SAML Redirect Loop

**Problem:** Redirects between app and IDP repeatedly

**Check:**
1. **Verify ACS URL matches:**
   ```bash
   # In mock IDP metadata
   curl http://localhost:8080/simplesaml/saml2/idp/metadata.php | grep AssertionConsumerService

   # Should match:
   https://naaccord.pequod.sh/saml2/acs/
   ```

2. **Check Django SAML configuration:**
   ```bash
   docker exec naaccord-web python manage.py shell
   >>> from django.conf import settings
   >>> print(settings.SAML_CONFIG['sp']['assertionConsumerService'])
   ```

### Mock IDP Running in Production

**Problem:** Mock IDP accidentally running in production

**Verify:**
```bash
# On production web server
docker ps --filter name=mock-idp
# Expected: No containers

# Check environment
cat /opt/naaccord/depot/.env | grep USE_MOCK_SAML
# Expected: USE_MOCK_SAML=False

# If running, stop it
docker stop naaccord-mock-idp
docker rm naaccord-mock-idp
```

### JHU Shibboleth Connection Failed

**Problem:** Cannot connect to JHU IDP in production

**Check:**
1. **Verify metadata URL:**
   ```bash
   curl -I https://idp.jh.edu/idp/shibboleth
   # Should return 200 OK
   ```

2. **Check VPN access:**
   - JHU Shibboleth may require VPN
   - Verify web server has network access

3. **Contact JHU IT:**
   - Confirm SP registration complete
   - Verify attribute release configured
   - Request IDP metadata if URL changed

---

## Security Considerations

### Staging Security

- ✅ Mock IDP is **test-only** with known passwords
- ⚠️ Never expose staging with mock IDP to public internet
- ⚠️ Mock IDP bypasses all real authentication security
- ✅ Staging data should be synthetic/de-identified

### Production Security

- ✅ JHU Shibboleth provides enterprise-grade authentication
- ✅ Duo 2FA required for all users
- ✅ JHED credentials never stored in NA-ACCORD
- ✅ SAML assertions signed and encrypted
- ✅ Automatic session timeout

### Profile Isolation

- ✅ `staging-idp` profile ensures mock IDP only runs when explicitly enabled
- ✅ Production playbook does not include staging-idp profile
- ✅ `USE_MOCK_SAML` environment variable controls behavior
- ✅ Ansible template enforces environment-based configuration

---

## Maintenance

### Updating Mock IDP Configuration

```bash
# Edit mock IDP config
nano saml/docker-idp/authsources.php

# Commit changes
git add saml/docker-idp/
git commit -m "feat: update mock IDP test users"
git push origin deploy

# On staging server
cd /opt/naaccord/depot
git pull origin deploy
docker restart naaccord-mock-idp
```

### Updating Production IDP Metadata

```bash
# On production web server
cd /opt/naaccord/depot/deploy/ansible

# Update production inventory
nano inventories/production/hosts.yml
# Change: saml_idp_metadata_url

# Re-run Ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production \
  --tags config

# Restart web container
docker restart naaccord-web
```

---

## Summary

**Staging:**
- ✅ Mock IDP container runs on port 8080/8443
- ✅ Enabled via `--profile staging-idp`
- ✅ Test users with known passwords
- ✅ No VPN or enterprise access required
- ✅ Complete SAML workflow testing

**Production:**
- ✅ JHU Shibboleth for authentication
- ✅ Mock IDP never runs
- ✅ Real user credentials and 2FA
- ✅ Requires JHU IT coordination
- ✅ Enterprise security standards

**Environment Variable:**
- `USE_MOCK_SAML=True` → Staging with mock IDP
- `USE_MOCK_SAML=False` → Production with JHU Shibboleth
