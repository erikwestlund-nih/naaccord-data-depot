# Web Server Deployment Checklist

**Created:** 2025-10-03 (after services server completion)
**Status:** Ready to deploy
**Services Server:** ✅ Operational (all containers healthy)

---

## Pre-Deployment Checklist

### Prerequisites
- [ ] Services server fully operational (✅ confirmed)
- [ ] WireGuard keys generated and in vault (✅ confirmed)
- [ ] GitHub deploy keys available
- [ ] Web server accessible via SSH
- [ ] DNS configured (staging: naaccord.pequod.sh → web server IP)

---

## Phase 1: Bootstrap Web Server (20 minutes)

### Step 1.1: Copy Bootstrap Scripts
```bash
# From local machine
scp deploy/scripts/1-init-server.sh erik@web.naaccord.lan:~/
scp deploy/scripts/2-prepare-env.sh erik@web.naaccord.lan:~/
```

### Step 1.2: Run Server Initialization
```bash
# SSH to web server
ssh web.naaccord.lan

# Run bootstrap
chmod +x 1-init-server.sh 2-prepare-env.sh
./1-init-server.sh staging deploy
# Paste GitHub deploy keys when prompted
```

**Verify:**
```bash
ls -la /opt/naaccord/depot
ansible --version
git status  # Should show: On branch deploy
```

### Step 1.3: Copy Vault from Services Server

**IMPORTANT:** Use the **same vault** as services server for consistency.

**Option A: Direct copy (recommended)**
```bash
# On services server
cat /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all/vault.yml

# On web server (create directory first)
mkdir -p /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all
nano /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all/vault.yml
# Paste vault content (Ctrl+X to save)

# Copy vault password
# On services server: cat ~/.naaccord_vault_staging
# On web server:
echo "changeme" > ~/.naaccord_vault_staging
chmod 600 ~/.naaccord_vault_staging
```

**Option B: Run prepare-env manually**
```bash
cd /opt/naaccord/depot
./deploy/scripts/2-prepare-env.sh staging web

# CRITICAL: Use SAME values as services server
# - All passwords must match
# - WireGuard keys must match
# - Internal API key must match
```

---

## Phase 2: Deploy Docker Secrets (5 minutes)

```bash
cd /opt/naaccord/depot/deploy/ansible

# Deploy secrets only
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags secrets
```

**Verify:**
```bash
ls -la /var/lib/docker/secrets/
# Should show: wg_*, django_secret_key, internal_api_key, db_password
```

---

## Phase 3: Deploy WireGuard Client (10 minutes)

### Step 3.1: Create WireGuard Client Container

**Method A: Via Ansible (recommended)**
```bash
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags wireguard
```

**Method B: Manual docker-compose**
```bash
cd /opt/naaccord/depot

docker compose -f docker-compose.prod.yml \
  --profile web \
  pull wireguard-web

docker compose -f docker-compose.prod.yml \
  --profile web \
  up -d wireguard-web
```

### Step 3.2: Verify WireGuard Tunnel

```bash
# Check container status
docker ps --filter name=wireguard-web
# Expected: Up (healthy)

# Check WireGuard interface
docker exec naaccord-wireguard-web wg show
# Should show peer: services.naaccord.lan:51820

# Test tunnel connectivity
docker exec naaccord-wireguard-web ping -c 3 10.100.0.11
# Expected: 3 packets transmitted, 3 received, 0% packet loss
```

**If tunnel fails:**
- Check services server WireGuard: `docker exec naaccord-wireguard-services wg show`
- Verify DNS: `ping services.naaccord.lan`
- Check firewall: Port 51820/udp must be open

---

## Phase 4: Deploy Web Application Stack (15 minutes)

### Step 4.1: Deploy All Web Services

```bash
cd /opt/naaccord/depot/deploy/ansible

# Full web stack deployment
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging
```

**This deploys:**
- Django web container
- Nginx reverse proxy
- Mock SAML IDP (staging only)
- Grafana (if configured)

### Step 4.2: Verify Web Stack

```bash
# Check all containers
docker ps --filter name=naaccord
# Expected: naaccord-web, naaccord-wireguard-web, naaccord-mock-idp

# Check Django web health
curl http://localhost:8000/health/
# Expected: {"status": "healthy", "server_role": "web"}

# Check Nginx
curl http://localhost/health/
# Should proxy to Django

# Check mock IDP
curl http://localhost:8080/simplesaml/saml2/idp/metadata.php
# Should return XML SAML metadata
```

---

## Phase 5: Configure SSL/TLS (20 minutes)

### Staging: LetsEncrypt (Automated)

```bash
# Deploy LetsEncrypt configuration
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags ssl

# Verify certificate
sudo ls -la /etc/letsencrypt/live/naaccord.pequod.sh/
# Should show: cert.pem, chain.pem, fullchain.pem, privkey.pem

# Test HTTPS
curl https://naaccord.pequod.sh/health/
# Expected: {"status": "healthy", "server_role": "web"}
```

### Production: IT-Provided Certificates

```bash
# Copy certificates from IT
# Expected files:
# - certificate.crt
# - certificate.key
# - ca-bundle.crt

# Place in standard location
sudo mkdir -p /etc/ssl/naaccord
sudo cp certificate.crt /etc/ssl/naaccord/
sudo cp certificate.key /etc/ssl/naaccord/
sudo cp ca-bundle.crt /etc/ssl/naaccord/

# Update Nginx configuration (Ansible will handle this)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production \
  --tags ssl,nginx
```

---

## Phase 6: Test SAML Authentication (10 minutes)

### Step 6.1: Access Application

```bash
# Open browser to:
https://naaccord.pequod.sh/
```

### Step 6.2: Test Login Flow

1. Click "Sign In"
2. Should redirect to mock IDP: `http://localhost:8080/simplesaml/`
3. Login with test user:
   - Username: `user1`
   - Password: `user1pass`
4. Should redirect back to NA-ACCORD authenticated

### Step 6.3: Verify User Creation

```bash
docker exec naaccord-web python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> user = User.objects.get(username='user1')
>>> print(user.email)
user1@example.com
>>> exit()
```

---

## Phase 7: End-to-End PHI Workflow Test (15 minutes)

### Step 7.1: Test Data Upload

```bash
# Login as user1
# Navigate to: https://naaccord.pequod.sh/submissions/upload/

# Upload test patient file
# File should stream from web → services via WireGuard tunnel
```

### Step 7.2: Verify File Processing

```bash
# On services server - check Celery logs
docker logs naaccord-celery --tail 50
# Should show: Task processing, DuckDB conversion, report generation

# Check services API from web
docker exec naaccord-web curl -s http://10.100.0.11:8001/health/
# Expected: {"status": "healthy", "database": "connected", "server_role": "services"}
```

### Step 7.3: Verify Report Generation

```bash
# Check if reports are accessible
# Navigate to: https://naaccord.pequod.sh/submissions/reports/

# Should show generated report
# Report should be served from services server via tunnel
```

---

## Phase 8: Performance and Security Verification (10 minutes)

### Step 8.1: Check Resource Usage

```bash
# Web server resources
docker stats --no-stream naaccord-web naaccord-wireguard-web

# Services server resources
ssh services.naaccord.lan
docker stats --no-stream naaccord-services naaccord-celery
```

### Step 8.2: Verify PHI Isolation

```bash
# Web server should have NO PHI files
sudo find /opt/naaccord -name "*.csv" -o -name "*.duckdb"
# Expected: No PHI data files (only application code)

# Services server should have PHI in NAS only
ssh services.naaccord.lan
sudo ls -la /mnt/nas/submissions/
# PHI files should exist here
```

### Step 8.3: Test WireGuard Tunnel Stability

```bash
# Run continuous ping test
docker exec naaccord-wireguard-web ping -c 100 10.100.0.11
# Expected: 0% packet loss
```

---

## Phase 9: Logging and Monitoring Setup (Optional - Phase 6)

**Note:** Can be deferred to Phase 6 of deployment plan.

```bash
# Deploy Loki and Grafana
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags monitoring

# Access Grafana
# Navigate to: https://naaccord.pequod.sh/mon/
```

---

## Troubleshooting Guide

### WireGuard Tunnel Issues

**Problem:** Web can't reach services via tunnel

**Solutions:**
```bash
# Check WireGuard logs
docker logs naaccord-wireguard-web
docker logs naaccord-wireguard-services

# Verify peer configuration
docker exec naaccord-wireguard-web wg show
# Should show endpoint: services.naaccord.lan:51820

# Test DNS resolution
ping services.naaccord.lan

# Restart WireGuard on both servers
docker restart naaccord-wireguard-web
ssh services.naaccord.lan 'docker restart naaccord-wireguard-services'
```

### Database Connection Issues

**Problem:** Web container can't connect to database

**Solutions:**
```bash
# Verify database host in environment
docker exec naaccord-web env | grep DATABASE_HOST
# Should be: db.naaccord.internal or 10.100.0.11

# Test database connectivity through tunnel
docker exec naaccord-web nc -zv 10.100.0.11 3306
# Should succeed

# Check MariaDB grants on services server
ssh services.naaccord.lan
sudo mysql -uroot -p -e "SELECT User, Host FROM mysql.user WHERE User='naaccord_app';"
```

### SAML Authentication Issues

**Problem:** SAML redirect loop or login fails

**Solutions:**
```bash
# Verify mock IDP is running (staging)
docker ps --filter name=mock-idp
docker logs naaccord-mock-idp

# Check SAML configuration
docker exec naaccord-web env | grep SAML

# Test IDP metadata
curl http://localhost:8080/simplesaml/saml2/idp/metadata.php

# Restart mock IDP
docker restart naaccord-mock-idp
```

### SSL Certificate Issues

**Problem:** SSL certificate errors or not found

**Staging (LetsEncrypt):**
```bash
# Check certificate files
sudo ls -la /etc/letsencrypt/live/naaccord.pequod.sh/

# Re-run certbot
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials ~/.secrets/cloudflare.ini \
  -d naaccord.pequod.sh

# Restart Nginx
docker restart naaccord-nginx
```

**Production (IT certs):**
```bash
# Verify certificate files exist
sudo ls -la /etc/ssl/naaccord/

# Check Nginx configuration
docker exec naaccord-nginx nginx -t

# Restart Nginx
docker restart naaccord-nginx
```

---

## Success Criteria

### Must Pass Before Declaring Success

- [ ] All containers running and healthy
- [ ] WireGuard tunnel stable (0% packet loss)
- [ ] Web can reach services API (10.100.0.11:8001)
- [ ] SAML authentication works (user can login)
- [ ] SSL/TLS configured (HTTPS working)
- [ ] Data upload workflow completes end-to-end
- [ ] Reports generate and display correctly
- [ ] No PHI files on web server
- [ ] Mock IDP running in staging only
- [ ] Health checks pass: `/health/` returns 200

---

## Quick Reference Commands

```bash
# Check all containers
docker ps --filter name=naaccord

# View logs
docker logs naaccord-web -f
docker logs naaccord-wireguard-web -f

# Restart services
docker restart naaccord-web
docker restart naaccord-nginx

# Test tunnel
docker exec naaccord-wireguard-web ping 10.100.0.11

# Test services API
docker exec naaccord-web curl -s http://10.100.0.11:8001/health/

# Check SAML config
cat /opt/naaccord/depot/.env | grep SAML

# Re-run Ansible
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook -i inventories/staging/hosts.yml playbooks/web-server.yml \
  --connection local --vault-password-file ~/.naaccord_vault_staging
```

---

## Estimated Timeline

| Phase | Task | Time |
|-------|------|------|
| 1 | Bootstrap web server | 20 min |
| 2 | Deploy Docker secrets | 5 min |
| 3 | Deploy WireGuard client | 10 min |
| 4 | Deploy web application stack | 15 min |
| 5 | Configure SSL/TLS | 20 min |
| 6 | Test SAML authentication | 10 min |
| 7 | End-to-end PHI workflow test | 15 min |
| 8 | Performance and security verification | 10 min |
| **Total** | **Core deployment** | **~2 hours** |

---

## Post-Deployment Tasks

After successful deployment:

1. **Update documentation:**
   - Mark web server as operational in deployment status docs
   - Update architecture diagrams
   - Document any issues encountered

2. **Create deployment log:**
   - Similar to services server deploy-log.md
   - Document any manual steps taken
   - Note any deviations from plan

3. **Verify reproducibility:**
   - Update ansible-reproducibility-checklist.md
   - Confirm all steps are captured in Ansible

4. **Plan Phase 6:**
   - Logging and monitoring setup (Loki, Grafana)
   - Slack alerting configuration
   - Dashboard creation

---

## Next Phase: Production Deployment

Once staging is stable:

1. Coordinate with JHU IT:
   - Exchange SAML metadata
   - Obtain SSL certificates
   - Confirm NAS mount configuration

2. Update production vault:
   - Generate production-specific secrets
   - Update production inventory

3. Deploy to production:
   - Follow same process
   - Use production inventory
   - NO mock IDP (uses JHU Shibboleth)
   - IT-provided SSL certificates
