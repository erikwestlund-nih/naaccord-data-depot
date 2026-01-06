# Deployment Workflow

**How to deploy NA-ACCORD using Ansible automation**

## Overview

NA-ACCORD uses Ansible for infrastructure automation. All deployment is done via SSH to each server, running playbooks locally due to RADIUS 2FA requirements.

## Prerequisites

- VPN access (production only)
- SSH access to servers with RADIUS 2FA
- Ansible vault password
- Git repository access

## Directory Structure on Servers

The repository is cloned to `/opt/naaccord/` which contains:

```
/opt/naaccord/              # Git repository root (working directory)
├── depot/                  # Django application code
│   ├── models/
│   ├── views/
│   ├── tasks/
│   └── ...
├── deploy/                 # Deployment automation
│   ├── ansible/           # Ansible roles and playbooks
│   │   ├── inventories/
│   │   ├── playbooks/
│   │   └── roles/
│   └── containers/        # Dockerfiles
├── docs/                   # Documentation
├── manage.py               # Django management command
├── requirements.txt        # Python dependencies
└── ...
```

**Key paths:**
- Application root: `/opt/naaccord/`
- Django app: `/opt/naaccord/depot/`
- Ansible playbooks: `/opt/naaccord/deploy/ansible/`
- Container definitions: `/opt/naaccord/deploy/containers/`

## Local Development Build Workflow

### Build Static Assets

```bash
# On local development machine
cd /path/to/naaccord

# Build frontend assets
npm run build

# Commit built assets
git add static/
git commit -m "build: compile static assets for deployment"
git push
```

### Build and Push Docker Images

```bash
# Build images locally
docker build -t ghcr.io/jhbiostatcenter/naaccord-web:latest -f Dockerfile.web .
docker build -t ghcr.io/jhbiostatcenter/naaccord-services:latest -f Dockerfile.services .
docker build -t ghcr.io/jhbiostatcenter/naaccord-celery:latest -f Dockerfile.celery .

# Push to GHCR
docker push ghcr.io/jhbiostatcenter/naaccord-web:latest
docker push ghcr.io/jhbiostatcenter/naaccord-services:latest
docker push ghcr.io/jhbiostatcenter/naaccord-celery:latest
```

## Initial Deployment

### Phase 0: Preparation

```bash
# On local machine - archive existing Ansible
cd /path/to/naaccord
cp -r deploy/ansible deploy/ansible-archive-$(date +%Y%m%d)
git add deploy/ansible-archive-*
git commit -m "archive: backup existing Ansible before rebuild"

# Create fresh Ansible structure (if not exists)
mkdir -p deploy/ansible/{roles,playbooks,inventories}
```

### Phase 1: Deploy to Staging Services Server

```bash
# SSH to staging services server
ssh user@192.168.50.11  # or services.naaccord.lan

# Clone/pull repository
cd /opt/naaccord || git clone https://github.com/jhbiostatcenter/naaccord-data-depot.git /opt/naaccord
cd /opt/naaccord
git pull origin deploy  # or main

# Run services server playbook
cd deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass

# Verify deployment
curl http://localhost:8001/health/
docker ps
```

### Phase 2: Deploy to Staging Web Server

```bash
# SSH to staging web server
ssh user@192.168.50.10  # or web.naaccord.lan

# Clone/pull repository
cd /opt/naaccord || git clone https://github.com/jhbiostatcenter/naaccord-data-depot.git /opt/naaccord
cd /opt/naaccord
git pull origin deploy  # or main

# Run web server playbook
cd deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass

# Verify deployment
curl https://localhost/health/
docker ps
```

### Phase 3: Test Staging

```bash
# Check WireGuard tunnel
ping 10.100.0.11  # from web server
ping 10.100.0.10  # from services server

# Test application
curl https://naaccord.pequod.sh/health/

# Check Grafana
curl https://naaccord.pequod.sh/mon/

# Run health check playbook
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/health-check.yml \
  --connection local
```

## Application Updates (Ongoing Deployment)

### Update Workflow

```bash
# On services server
ssh user@services-server
cd /opt/naaccord

# Run deploy role
cd deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \  # or production
  playbooks/deploy.yml \
  --connection local \
  --ask-vault-pass
```

**What the deploy role does:**
1. Pulls latest code from git
2. Runs database migrations (web server only)
3. Rebuilds Docker containers
4. Restarts containers
5. Runs health checks
6. Verifies deployment success

### Deployment Verification

```bash
# Check container status
docker ps

# Check logs
docker logs naaccord-services -f
docker logs naaccord-web -f
docker logs naaccord-celery -f

# Test endpoints
curl http://localhost:8001/health/  # services
curl https://localhost/health/      # web
```

## Production Deployment

### Pre-Production Checklist

- [ ] All changes tested in staging
- [ ] Static assets built and committed
- [ ] Docker images pushed to GHCR
- [ ] Database backup taken
- [ ] JHU IT coordinated for Shibboleth
- [ ] NAS credentials obtained
- [ ] Vault secrets updated for production
- [ ] Slack webhook configured

### Production Deploy Process

```bash
# Connect to VPN
# VPN connection required for 10.150.96.x access

# Deploy services server
ssh user@10.150.96.37
cd /opt/naaccord
git pull origin main  # production uses main branch

cd deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass

# Deploy web server
ssh user@10.150.96.6
cd /opt/naaccord
git pull origin main

cd deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass
```

### Production Verification

```bash
# Health checks
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/health-check.yml \
  --connection local

# Test SAML login
# Navigate to https://mrpznaaccordweb01.hosts.jhmi.edu/
# Verify redirect to JHU Shibboleth
# Test complete login flow

# Check Grafana monitoring
# https://mrpznaaccordweb01.hosts.jhmi.edu/mon/

# Verify PHI isolation
# Web server should have no PHI files locally
ssh user@10.150.96.6
ls -la /opt/naaccord/storage/  # Should be minimal/empty
```

## Rollback Procedure

### If Deployment Fails

```bash
# Option 1: Re-run previous version
cd /opt/naaccord
git checkout <previous-commit-hash>

ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --ask-vault-pass

# Option 2: Use rollback playbook (if implemented)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/rollback.yml \
  --connection local \
  --ask-vault-pass \
  --extra-vars "rollback_version=<tag-or-commit>"
```

### If Database Issues

```bash
# Restore from backup
# On services server
cd /mnt/nas/backups/
ls -la  # Find most recent backup

# Stop application
docker stop naaccord-services naaccord-celery

# Restore database
# [TODO: Document backup/restore procedure after Phase 9]

# Restart application
docker start naaccord-services naaccord-celery
```

## Common Tasks

### Update Static Assets Only

```bash
# Build locally
npm run build
git add static/
git commit -m "build: update static assets"
git push

# On server
git pull
docker restart naaccord-web
```

### Run Database Migrations

```bash
# Migrations run automatically via deploy role
# Or manually:
docker exec naaccord-services python manage.py migrate
```

### Restart Services

```bash
# Restart specific service
docker restart naaccord-services
docker restart naaccord-celery
docker restart naaccord-web

# Restart all via Ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --tags restart \
  --connection local
```

### View Logs

```bash
# Via Docker
docker logs naaccord-services -f
docker logs naaccord-celery -f

# Via Grafana (preferred)
# Navigate to https://naaccord.pequod.sh/mon/
# Select Loki data source
# Filter by container name
```

## Troubleshooting

### Ansible Vault Issues

```bash
# Can't decrypt vault
# Verify vault password is correct
ansible-vault view inventories/staging/group_vars/vault.yml

# Re-encrypt vault with new password
ansible-vault rekey inventories/staging/group_vars/vault.yml
```

### Container Issues

```bash
# Container won't start
docker logs naaccord-services

# Check environment variables
docker exec naaccord-services env

# Rebuild container
docker-compose down
docker-compose build services
docker-compose up -d services
```

### WireGuard Tunnel Issues

```bash
# Check tunnel status
docker exec wireguard-client wg show
docker exec wireguard-server wg show

# Test connectivity
ping 10.100.0.11  # from web to services
ping 10.100.0.10  # from services to web

# Restart WireGuard
docker restart wireguard-client
docker restart wireguard-server
```

### SAML Issues

```bash
# Check SAML configuration
# On web server
docker exec naaccord-web python manage.py shell

from django.conf import settings
print(settings.SAML_CONFIG)

# Verify metadata
cat /opt/naaccord/saml/metadata/idp_metadata.xml

# Check SAML logs
docker logs naaccord-web | grep -i saml
```

## Related Documentation

- [Architecture Overview](architecture.md) - System design
- [Ansible Roles Reference](ansible-roles.md) - Role details
- [Emergency Access](emergency-access.md) - Emergency procedures
- [Environment Details](../reference/environments.md) - Server specs
- [Deploy TODO Tracking](../../deploy-todo-tracking.md) - Implementation checklist
