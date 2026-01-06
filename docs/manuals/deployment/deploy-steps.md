# NA-ACCORD Deployment Steps

**Step-by-step instructions for deploying NA-ACCORD to staging and production servers.**

## Overview

This guide walks through the complete deployment process from initial server bootstrap through production deployment. Follow these steps in order.

---

## Phase 0: Prerequisites ✅ COMPLETE

- [x] SAML-only authentication implemented
- [x] Deployment documentation created
- [x] Bootstrap scripts created
- [x] GitHub deploy keys generated

---

## Phase 1: Initial Server Bootstrap

**Goal:** Get Ansible installed, repository cloned, and vault configured on each server

### Step 1.1: Run 1-init-server.sh (Server Bootstrap)

**Purpose:** Install Ansible, configure GitHub access, clone repository

```bash
# From local machine - copy bootstrap script
scp deploy/scripts/1-init-server.sh erik@services.naaccord.lan:~/

# SSH to services server
ssh services.naaccord.lan

# Run bootstrap script (will prompt interactively)
chmod +x 1-init-server.sh
./1-init-server.sh

# Follow prompts:
# 1. Select environment (staging or production)
# 2. Select server role (services)
# 3. Paste GitHub deploy PRIVATE key (including BEGIN/END headers)
# 4. Paste GitHub deploy PUBLIC key (ssh-ed25519...)
# 5. Enter vault password
# 6. Script will install Ansible, clone repo, verify structure
```

**Verify success:**
```bash
ls -la /opt/naaccord/depot
# Should see: depot/, deploy/, docs/, manage.py, etc.

cd /opt/naaccord/depot
git status
# Should show: On branch deploy

ansible --version
# Should show: ansible [core 2.x.x]
```

### Step 1.2: Run 2-prepare-env.sh (Ansible Vault Setup)

**Purpose:** Configure deployment secrets and create Ansible vault

```bash
# On services server (after 1-init-server.sh completes)
cd /opt/naaccord/depot

# Run environment preparation
./deploy/scripts/2-prepare-env.sh staging services  # [environment] [web|services]

# Follow prompts - enter values or press Enter for auto-generated:
# - Domain name: naaccord.pequod.sh (or press Enter)
# - Database passwords (auto-generated if blank)
# - Django secret key (auto-generated if blank)
# - Internal API key (auto-generated if blank)
# - Redis password (auto-generated if blank)
# - NAS host: 192.168.1.10 (or your NAS IP)
# - NAS share: naaccord
# - NAS username: naaccord
# - NAS password: (enter or auto-generate)
# - WireGuard keys: Auto-generate? [Y/n] (press Y)
# - Monitoring passwords (auto-generated if blank)

# ⚠️ IMPORTANT: Save vault password when displayed!
# Vault password: <randomly-generated-password>
# Saved to: ~/.naaccord_vault_staging
```

**Verify vault:**
```bash
# View vault contents
ansible-vault view \
  deploy/ansible/inventories/staging/group_vars/all/vault.yml \
  --vault-password-file=~/.naaccord_vault_staging

# Check vault password file permissions
ls -la ~/.naaccord_vault_staging  # Should be -rw------- (600)
```

### Step 1.3: Repeat for Web Server

```bash
# From local machine
scp deploy/scripts/1-init-server.sh erik@web.naaccord.lan:~/
scp deploy/scripts/2-prepare-env.sh erik@web.naaccord.lan:~/

# SSH to web server
ssh web.naaccord.lan

# Run bootstrap (will prompt interactively)
chmod +x 1-init-server.sh 2-prepare-env.sh
./1-init-server.sh

# Follow prompts:
# 1. Select environment (staging or production)
# 2. Select server role (web)
# 3. Paste GitHub deploy key
# 4. Enter vault password
# Use the SAME deploy key (or separate web key if you prefer)

# Run vault setup
cd /opt/naaccord/depot
./deploy/scripts/2-prepare-env.sh staging web  # Note: 'web' for web server role
```

### Step 1.4: (Later) Bootstrap Production Servers

**Wait until staging is fully tested before production.**

```bash
# Production services server (via VPN)
ssh user@10.150.96.37
./init-server.sh production

# Production web server (via VPN)
ssh user@10.150.96.6
./init-server.sh production
```

---

## Phase 2: Create Ansible Infrastructure Roles

**Goal:** Build foundational Ansible roles for infrastructure setup

### Step 2.1: Create Ansible Directory Structure

```bash
# On local development machine
cd /Users/erikwestlund/code/naaccord/deploy

mkdir -p ansible/{roles,playbooks,inventories/{staging,production}/group_vars}
```

### Step 2.2: Create Inventory Files

**Staging inventory:** `ansible/inventories/staging/hosts.yml`
```yaml
all:
  children:
    services:
      hosts:
        services.naaccord.lan:
          ansible_host: 192.168.50.11
          wireguard_ip: 10.100.0.11

    web:
      hosts:
        web.naaccord.lan:
          ansible_host: 192.168.50.10
          wireguard_ip: 10.100.0.10

  vars:
    environment: staging
    domain: naaccord.pequod.sh
    nas_host: 192.168.1.10
```

**Production inventory:** `ansible/inventories/production/hosts.yml`
```yaml
all:
  children:
    services:
      hosts:
        naaccord-services:
          ansible_host: 10.150.96.37
          wireguard_ip: 10.100.0.11

    web:
      hosts:
        naaccord-web:
          ansible_host: 10.150.96.6
          wireguard_ip: 10.100.0.10

  vars:
    environment: production
    domain: mrpznaaccordweb01.hosts.jhmi.edu
```

### Step 2.3: Create Ansible Vaults

```bash
# Staging vault
ansible-vault create ansible/inventories/staging/group_vars/vault.yml

# Production vault
ansible-vault create ansible/inventories/production/group_vars/vault.yml
```

**Vault contents (example):**
```yaml
---
# Database
mariadb_root_password: "CHANGE_ME_SECURE_PASSWORD"
mariadb_naaccord_password: "CHANGE_ME_SECURE_PASSWORD"

# Internal API
internal_api_key: "CHANGE_ME_SECURE_API_KEY"

# WireGuard
wireguard_private_key_services: "CHANGE_ME_WG_PRIVATE_KEY"
wireguard_private_key_web: "CHANGE_ME_WG_PRIVATE_KEY"

# NAS
nas_username: "naaccord"
nas_password: "CHANGE_ME_NAS_PASSWORD"

# Cloudflare (for SSL DNS-01)
cloudflare_api_token: "CHANGE_ME_CF_TOKEN"

# Slack (for alerts)
slack_webhook_url: "https://hooks.slack.com/services/CHANGE_ME"
```

### Step 2.4: Create Base Infrastructure Roles

Create these roles (to be implemented in next steps):
- `base` - Common packages, Docker, user setup
- `firewall` - UFW configuration
- `hosts_management` - /etc/hosts entries for WireGuard
- `nas_mount` - CIFS/SMB mounting

**Commit and push:**
```bash
git add ansible/
git commit -m "feat: create Ansible directory structure and inventories"
git push origin deploy
```

---

## Phase 3: Deploy Services Server Infrastructure

**Goal:** Set up MariaDB, Redis, WireGuard on services server

### Step 3.1: Implement Infrastructure Roles

Create roles:
- `mariadb` - Encrypted database with file-key-management
- `redis` - Docker container with encrypted volume
- `wireguard_server` - WireGuard tunnel server

### Step 3.2: Create Services Server Playbook

**File:** `ansible/playbooks/services-server.yml`
```yaml
---
- name: Deploy NA-ACCORD Services Server
  hosts: services
  become: yes

  roles:
    - base
    - firewall
    - hosts_management
    - nas_mount
    - mariadb
    - redis
    - wireguard_server
```

### Step 3.3: Deploy to Staging Services Server

```bash
# SSH to services server
ssh services.naaccord.lan

# Navigate to Ansible directory
cd /opt/naaccord/deploy/ansible

# Pull latest changes
git pull origin deploy

# Run playbook
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

### Step 3.4: Verify Infrastructure

```bash
# Check MariaDB
sudo systemctl status mariadb
mysql -u root -p -e "SHOW VARIABLES LIKE 'innodb_encrypt%';"

# Check Redis
docker ps | grep redis
docker exec naaccord-redis redis-cli ping

# Check WireGuard
sudo wg show
```

---

## Phase 4: Deploy Services Server Applications

**Goal:** Set up Django services and Celery workers

**Note:** Flower (Celery monitoring) deferred to Phase 6 (Observability)

### Step 4.1: Implement Application Roles

**Already implemented via docker-compose.prod.yml:**
- Django services container (services mode)
- Celery workers
- Celery beat (scheduler)

### Step 4.2: Update Services Playbook

Add application roles to `playbooks/services-server.yml`

### Step 4.3: Deploy Applications

```bash
# On services server
cd /opt/naaccord/deploy/ansible
git pull origin deploy

ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

### Step 4.4: Verify Applications

```bash
# Check Django services
curl http://localhost:8001/health/

# Check Celery
docker logs naaccord-celery

# Check Flower
curl http://localhost:5555/
```

---

## Phase 5: Deploy Web Server ← **CURRENT PHASE**

**Goal:** Set up WireGuard client, SSL, Nginx, Django web, Grafana

**Status:** Services server is fully operational (2025-10-03). Now deploying web server.

**Services Server Operational:**
- ✅ MariaDB with proper Docker subnet grants (172.18.%)
- ✅ Redis (healthy)
- ✅ Services container (healthy, database connected)
- ✅ Celery workers (running)
- ✅ WireGuard server (healthy, listening on 10.100.0.11:51820)
- ✅ Real WireGuard keys deployed (no longer placeholders)

### Step 5.1: Bootstrap Web Server

**CRITICAL:** Run the same bootstrap process used for services server

```bash
# From local machine - copy bootstrap scripts
scp deploy/scripts/1-init-server.sh erik@web.naaccord.lan:~/
scp deploy/scripts/2-prepare-env.sh erik@web.naaccord.lan:~/

# SSH to web server
ssh web.naaccord.lan

# Run bootstrap script (will prompt interactively)
chmod +x 1-init-server.sh 2-prepare-env.sh
./1-init-server.sh

# Follow prompts:
# 1. Select environment (staging or production)
# 2. Select server role (web)
# 3. Paste GitHub deploy PRIVATE key (including BEGIN/END headers)
# 4. Paste GitHub deploy PUBLIC key (ssh-ed25519...)
# 5. Enter vault password
# 6. Script will install Ansible, clone repo, verify structure
```

**Verify bootstrap:**
```bash
ls -la /opt/naaccord/depot
# Should see: depot/, deploy/, docs/, manage.py, etc.

cd /opt/naaccord/depot
git status
# Should show: On branch deploy

ansible --version
# Should show: ansible [core 2.x.x]
```

### Step 5.2: Configure Web Server Vault

**CRITICAL:** Use the **SAME** vault as services server for consistency

```bash
# On web server (after 1-init-server.sh completes)
cd /opt/naaccord/depot

# Run environment preparation for WEB role
./deploy/scripts/2-prepare-env.sh staging web  # Note: 'web' not 'services'

# IMPORTANT: Use SAME values as services server:
# - Domain name: naaccord.pequod.sh
# - Database passwords: (from services server vault)
# - Django secret key: (from services server vault)
# - Internal API key: (from services server vault)
# - Redis password: (from services server vault)
# - NAS host: 192.168.1.10
# - NAS credentials: (from services server vault)
# - WireGuard keys: **Auto-generate will fail - use existing keys!**
#   - Use web private key from services vault
#   - Use services public key from services vault
#   - Use preshared key from services vault

# ⚠️ IMPORTANT: Vault password will be saved to: ~/.naaccord_vault_staging
```

**Alternative - Copy vault directly from services server:**
```bash
# On services server
cat /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all/vault.yml

# On web server (create the directory first)
mkdir -p /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all
nano /opt/naaccord/depot/deploy/ansible/inventories/staging/group_vars/all/vault.yml
# Paste the vault content

# Copy vault password file
# From services server: cat ~/.naaccord_vault_staging
# On web server: echo "changeme" > ~/.naaccord_vault_staging
chmod 600 ~/.naaccord_vault_staging
```

### Step 5.3: Deploy WireGuard Client Container

**CRITICAL:** Web server runs WireGuard CLIENT (not server)

```bash
# Pull WireGuard container
sudo docker pull ghcr.io/jhbiostatcenter/naaccord/wireguard:latest

# Create WireGuard client container
sudo docker run -d \
  --name naaccord-wireguard-web \
  --cap-add NET_ADMIN \
  --cap-add SYS_MODULE \
  --device /dev/net/tun:/dev/net/tun \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  --sysctl net.ipv4.ip_forward=1 \
  -e WG_PRIVATE_KEY_FILE=/run/secrets/wg_web_private_key \
  -e WG_PEER_PUBLIC_KEY_FILE=/run/secrets/wg_services_public_key \
  -e WG_PRESHARED_KEY_FILE=/run/secrets/wg_preshared_key \
  -e WG_TUNNEL_ADDRESS=10.100.0.10/24 \
  -e WG_PEER_ADDRESS=10.100.0.11 \
  -e WG_PEER_ENDPOINT=services.naaccord.lan:51820 \
  -e WG_LISTEN_PORT=51820 \
  -v /var/lib/docker/secrets:/run/secrets:ro \
  --network naaccord_internal \
  --restart unless-stopped \
  ghcr.io/jhbiostatcenter/naaccord/wireguard:latest

# Verify WireGuard health
sudo docker ps --filter name=wireguard
# Should show: Up (healthy)

sudo docker exec naaccord-wireguard-web wg show
# Should show peer configured with endpoint services.naaccord.lan:51820
```

**Test tunnel connectivity:**
```bash
# Test ping through tunnel (from web to services)
sudo docker exec naaccord-wireguard-web ping -c 3 10.100.0.11

# Expected output:
# 3 packets transmitted, 3 received, 0% packet loss
```

### Step 5.4: Deploy Web Application Stack

**CRITICAL - Static Assets Deployment:**

Before deploying containers, ensure static assets are built and copied to the container volume:

```bash
# On LOCAL development machine (build assets first)
cd /path/to/naaccord
npm run build

# Commit built assets
git add static/
git commit -m "build: compile Vite assets"
git push origin deploy

# On web server (after pulling latest code)
cd /opt/naaccord/depot

# Pull latest code with built assets
git pull origin deploy

# Copy static assets to container volume
# CRITICAL: Django context processor reads from /app/static/.vite/manifest.json
sudo cp -r static/.vite /var/lib/docker/volumes/depot_django_static/_data/
sudo cp -r static/assets /var/lib/docker/volumes/depot_django_static/_data/
sudo cp -r static/icons /var/lib/docker/volumes/depot_django_static/_data/

# Verify assets are in place
sudo docker exec naaccord-web ls -la /app/static/.vite/manifest.json
sudo docker exec naaccord-web ls -la /app/static/assets/ | head -10
sudo docker exec naaccord-web ls -la /app/static/icons/ | head -10
```

**Why this is needed:**
- Django's `context_processors.py` reads Vite manifest from `BASE_DIR / "static/.vite/manifest.json"`
- In containers, `BASE_DIR = /app`, so it needs `/app/static/.vite/manifest.json`
- The `django_static` volume is mounted at `/app/static/`
- Font Awesome icons in `static/icons/` must be accessible for the application to render icons
- Without these files, templates show `src="/static/None"` and icons don't display

**Option A: Manual deployment (recommended for first time)**

```bash
# On web server
cd /opt/naaccord/depot

# Pull latest code
git pull origin deploy

# Deploy static assets (see above)

# Build and start web containers
cd deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging
```

**Option B: Docker Compose (if compose file exists)**

```bash
# On web server
cd /opt/naaccord/depot

# Start web stack
sudo docker compose -f docker-compose.web.yml up -d

# Verify containers
sudo docker ps --filter name=naaccord
# Should show: naaccord-web, naaccord-nginx, naaccord-grafana
```

### Step 5.5: Verify Web Stack

**Check all services:**
```bash
# Test WireGuard tunnel
ping 10.100.0.11
# Should respond from services server tunnel IP

# Check Django web health
curl http://localhost:8000/health/
# Expected: {"status": "healthy", "server_role": "web"}

# Check Nginx is running
curl http://localhost/health/
# Should proxy to Django

# Check Grafana
curl http://localhost:3000/
# Should show Grafana login page

# View all containers
sudo docker ps --filter name=naaccord
# Should show: web, nginx, grafana, wireguard-web all healthy
```

**Test end-to-end PHI tunnel:**
```bash
# From web container, try to reach services API
sudo docker exec naaccord-web curl -s http://10.100.0.11:8001/health/
# Expected: {"status": "healthy", "database": "connected", "server_role": "services"}
```

### Step 5.6: Deploy Mock IDP for SAML Testing (Staging Only)

**IMPORTANT:** Staging uses a mock SAML IDP container for authentication testing.

```bash
# On staging web server
cd /opt/naaccord/depot

# Start web stack WITH mock IDP
docker compose -f docker-compose.prod.yml \
  --profile web \
  --profile staging-idp \
  up -d

# Verify mock IDP is running
docker ps --filter name=mock-idp
# Expected: naaccord-mock-idp on ports 8080/8443

# Test IDP metadata
curl http://localhost:8080/simplesaml/saml2/idp/metadata.php
# Should return XML SAML metadata
```

**Mock IDP Test Users:**
- Username: `user1` / Password: `user1pass`
- Username: `admin1` / Password: `admin1pass`

**See full documentation:** [deploy/docs/saml-configuration.md](docs/saml-configuration.md)

**Production:** Mock IDP will NOT run - production uses JHU Shibboleth (no `staging-idp` profile).

### Step 5.7: Configure SSL and Public Access

**After local verification passes:**

1. **Configure DNS:** Point naaccord.pequod.sh to web server IP
2. **Run SSL playbook:** Deploy Let's Encrypt SSL certificates
3. **Configure Nginx:** Enable HTTPS, proxy to Django
4. **Test public access:** https://naaccord.pequod.sh/

```bash
# Deploy SSL and Nginx configuration
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags ssl,nginx
```

### Step 5.8: Test SAML Authentication

**Test with mock IDP:**

1. **Access application:**
   ```
   https://naaccord.pequod.sh/
   ```

2. **Click "Sign In"** - Should redirect to mock IDP at `localhost:8080`

3. **Login with test user:**
   - Username: `user1`
   - Password: `user1pass`

4. **Verify** - Should be redirected back to NA-ACCORD as authenticated user

**See troubleshooting:** [deploy/docs/saml-configuration.md](docs/saml-configuration.md#troubleshooting)

### Step 5.9: Troubleshooting Web Deployment

**Common issues:**

1. **WireGuard tunnel not connecting:**
   ```bash
   # Check WireGuard logs
   sudo docker logs naaccord-wireguard-web

   # Verify peer endpoint is reachable
   ping services.naaccord.lan

   # Check if services server is listening
   # On services server:
   sudo docker exec naaccord-wireguard-services wg show
   ```

2. **Web container can't reach services:**
   ```bash
   # Check tunnel routing
   sudo docker exec naaccord-wireguard-web ip route

   # Should show: 10.100.0.0/24 dev wg0

   # Test connectivity
   sudo docker exec naaccord-wireguard-web ping 10.100.0.11
   ```

3. **Database connection issues:**
   ```bash
   # Verify web container has correct environment
   sudo docker exec naaccord-web env | grep DATABASE

   # DATABASE_HOST should be db.naaccord.internal
   # Services container should resolve this via WireGuard
   ```

**Next steps after web server is operational:**
- Deploy Grafana dashboards
- Configure Loki logging
- Set up Slack alerts
- Test complete submission workflow

---

## Phase 6: Configure Logging and Monitoring

**Goal:** Set up Loki for log aggregation and Grafana dashboards

### Step 6.1: Implement Loki Role

Create `loki` role for services server

### Step 6.2: Configure Grafana Data Sources

Add Loki data source via Grafana role

### Step 6.3: Create Dashboards

- Application logs dashboard
- System metrics dashboard
- Celery monitoring dashboard (via Loki logs)
  - Optional: Add Flower for dedicated Celery UI monitoring

### Step 6.4: Test Logging

```bash
# Generate some logs
docker logs naaccord-services

# View in Grafana
# Navigate to https://naaccord.pequod.sh/mon/
# Select Loki data source
# Query: {container="naaccord-services"}
```

---

## Phase 7: Deployment Automation

**Goal:** Create deployment role for application updates

### Step 7.1: Create Deploy Role

**File:** `ansible/roles/deploy/tasks/main.yml`

Handles:
- Git pull latest code
- Run migrations (web server only)
- Rebuild containers
- Restart services
- Health checks

### Step 7.2: Create Deployment Playbook

**File:** `ansible/playbooks/deploy.yml`

### Step 7.3: Test Deployment

```bash
# Make a code change locally
# Commit and push

# On server
cd /opt/naaccord/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --ask-vault-pass
```

---

## Phase 8: Slack Alerting

**Goal:** Configure Grafana to send alerts to Slack

### Step 8.1: Add Slack Webhook to Vault

Update `vault.yml` with Slack webhook URL

### Step 8.2: Configure Grafana Contact Points

Via Grafana role or manual configuration

### Step 8.3: Create Alert Rules

- Service down alerts
- Celery queue backed up
- Database errors

### Step 8.4: Test Alerts

```bash
# Stop a service to trigger alert
docker stop naaccord-services

# Wait for alert in Slack
# Restart service
docker start naaccord-services
```

---

## Phase 9: Comprehensive Staging Testing

**Goal:** Validate entire stack works end-to-end

### Test Checklist

- [ ] SAML authentication works (mock-idp)
- [ ] Can upload data files
- [ ] Files stream from web to services server
- [ ] Celery processes uploads
- [ ] Reports generate correctly
- [ ] WireGuard tunnel is stable
- [ ] Database encryption is active
- [ ] Grafana shows logs from all services
- [ ] Slack alerts are delivered
- [ ] Deployment automation works
- [ ] Health checks pass

### Performance Testing

- Upload large files (2GB+)
- Process multiple submissions simultaneously
- Monitor resource usage

### Security Validation

- Verify PHI isolation (web server has no PHI files)
- Check database encryption
- Verify WireGuard encryption
- Review audit logs

---

## Phase 10: Production Preparation

**Goal:** Coordinate with JHU IT and prepare production deployment

### Step 10.1: JHU IT Coordination

- [ ] Exchange SAML metadata with JHU Shibboleth team
- [ ] Confirm NAS mount path and credentials
- [ ] Obtain production DNS entries
- [ ] Confirm VPN access for deployment

### Step 10.2: Generate Production Secrets

```bash
# Generate secure passwords
openssl rand -base64 32  # Database root password
openssl rand -base64 32  # Database naaccord password
openssl rand -base64 32  # Internal API key

# Generate WireGuard keys
wg genkey | tee services-privatekey | wg pubkey > services-publickey
wg genkey | tee web-privatekey | wg pubkey > web-publickey
```

### Step 10.3: Update Production Vault

```bash
ansible-vault edit ansible/inventories/production/group_vars/vault.yml
```

### Step 10.4: Obtain Cloudflare API Token

For DNS-01 SSL challenges

---

## Phase 11: Production Deployment

**Goal:** Deploy to production servers

### Step 11.1: Deploy Production Services Server

```bash
# Connect to VPN
# SSH to production services server
ssh user@10.150.96.37

# Verify bootstrap is complete
ls /opt/naaccord

# Pull latest
cd /opt/naaccord
git pull origin main  # Production uses main branch

# Deploy
cd deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

### Step 11.2: Deploy Production Web Server

```bash
# SSH to production web server
ssh user@10.150.96.6

# Pull and deploy
cd /opt/naaccord
git pull origin main

cd deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass
```

### Step 11.3: Configure JHU Shibboleth

- Update SAML metadata
- Test authentication with real JHU accounts
- Verify attribute mapping

### Step 11.4: Production Verification

```bash
# Health checks
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/health-check.yml \
  --connection local

# Test SAML login
# Test file upload workflow
# Verify PHI isolation
# Check Grafana monitoring
# Test Slack alerts
```

---

## Phase 12: UAT and Handoff

**Goal:** Complete testing and hand off to operations

### Step 12.1: User Acceptance Testing

- [ ] Pilot users test with real data
- [ ] Complete workflows validated
- [ ] Performance acceptable
- [ ] All features working

### Step 12.2: Security Audit

- [ ] Penetration testing
- [ ] HIPAA compliance verification
- [ ] PHI isolation confirmed
- [ ] Audit trail complete

### Step 12.3: Create Operational Runbooks

Document:
- Daily operations
- Deployment procedures
- Troubleshooting guides
- Emergency procedures
- Backup/restore procedures

### Step 12.4: Team Training

- [ ] IT team trained on emergency access
- [ ] IT team trained on deployment
- [ ] Monitoring and alerting procedures
- [ ] Incident response training

### Step 12.5: Go-Live

- [ ] All stakeholders notified
- [ ] Support procedures in place
- [ ] Monitoring active
- [ ] Handoff complete

---

## Ongoing Operations

### Application Updates

```bash
# Local development
npm run build
git add static/
git commit -m "build: compile assets"
git push

# Build and push containers
docker build -t ghcr.io/jhbiostatcenter/naaccord-web:latest .
docker push ghcr.io/jhbiostatcenter/naaccord-web:latest

# Deploy to production
ssh user@10.150.96.6
cd /opt/naaccord/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --ask-vault-pass
```

### Monitoring

- Check Grafana dashboards daily
- Review Slack alerts
- Monitor resource usage
- Check backup completion

### Troubleshooting

See:
- [Emergency Access Guide](../docs/deployment/guides/emergency-access.md)
- [Deployment Workflow](../docs/deployment/guides/deployment-workflow.md)
- [Architecture Guide](../docs/deployment/guides/architecture.md)

---

## Quick Reference

**Common Commands:**

```bash
# Update code
cd /opt/naaccord && git pull origin deploy

# Run deployment
cd /opt/naaccord/deploy/ansible
ansible-playbook -i inventories/staging/hosts.yml playbooks/deploy.yml --connection local --ask-vault-pass

# Check health
ansible-playbook -i inventories/staging/hosts.yml playbooks/health-check.yml --connection local

# View logs
docker logs naaccord-services -f
docker logs naaccord-celery -f

# Restart services
docker restart naaccord-services
docker restart naaccord-celery
```

**Important Paths:**

- Application root: `/opt/naaccord/`
- Django app: `/opt/naaccord/depot/`
- Ansible playbooks: `/opt/naaccord/deploy/ansible/`
- NAS mount: `/mnt/nas/`

**Emergency Contacts:**

- DevOps Lead: [Contact]
- Security Team: [Contact]
- JHU IT Support: [Contact]
