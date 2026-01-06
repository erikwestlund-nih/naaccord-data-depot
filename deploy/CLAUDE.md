# Deploy Domain - CLAUDE.md

## 🚨 CRITICAL: NEVER RESET THE PRODUCTION DATABASE

**THE PRODUCTION DATABASE CONTAINS REAL RESEARCH DATA. NEVER RESET IT.**

The `database-reset.yml` playbook **DESTROYS ALL DATA**. It is ONLY for:
- Initial server setup (empty database)
- Local development environments

**To add cohorts or users to production, use incremental commands:**
```bash
# SSH to services server, then:
docker exec naaccord-services python manage.py seed_from_csv --model depot.Cohort --file resources/data/seed/cohorts.csv
docker exec naaccord-services python manage.py load_production_users
```

---

## Overview

The deploy domain contains all infrastructure-as-code, deployment automation, and container definitions for NA-ACCORD's PHI-compliant two-server architecture.

**Status:** Phase 0 Complete (SAML-only auth, bootstrap scripts) - Phase 1 Ready (Ansible roles)

## Quick Start

**Deploying NA-ACCORD?** → Follow **[deploy-steps.md](deploy-steps.md)** step-by-step

**Need to bootstrap a new server?** → See **[scripts/README.md](scripts/README.md)** for init-server.sh usage

## Documentation Structure

**⭐ START HERE:**
- **[deploy-steps.md](deploy-steps.md)** - **STEP-BY-STEP DEPLOYMENT GUIDE** - Follow this to deploy from scratch
- **[scripts/README.md](scripts/README.md)** - Bootstrap scripts for initial server setup
- **[docs/aliases-reference.md](docs/aliases-reference.md)** - Shell aliases reference (deployna, nahelp, etc.)
- **[docs/production-differences.md](docs/production-differences.md)** - **PRODUCTION READINESS** - Critical differences between staging and production

**Primary Documentation:**
- **[../docs/deploy-todo-tracking.md](../docs/deploy-todo-tracking.md)** - Implementation tracking and checklist
- **[../docs/deployment/README.md](../docs/deployment/README.md)** - Deployment documentation hub
- **[../docs/deployment/guides/architecture.md](../docs/deployment/guides/architecture.md)** - System architecture overview
- **[../docs/deployment/guides/deployment-workflow.md](../docs/deployment/guides/deployment-workflow.md)** - Deployment patterns and procedures
- **[../docs/deployment/guides/emergency-access.md](../docs/deployment/guides/emergency-access.md)** - IT emergency procedures


## Current Deployment Architecture

### Two-Server PHI-Compliant Design

```
Web Server (Port 443, 22)          Services Server (Port 22, 51820)
┌──────────────────────┐          ┌────────────────────────────┐
│ Nginx + SSL          │          │ MariaDB (encrypted)        │
│ Django Web           │          │ Redis (tmpfs RAM-only)     │
│ Grafana (/mon)       │          │ Django Services            │
│ WireGuard Client ────┼─ Tunnel ─┤ Celery Workers             │
│ (10.100.0.10)        │          │ Loki Logs                  │
│                      │          │ WireGuard Server           │
│ SAML-only Auth       │          │ (10.100.0.11)              │
└──────────────────────┘          │ NAS Mount                  │
                                  └────────────────────────────┘
```

### Key Architectural Decisions

Based on multi-model consensus analysis (Claude Opus, OpenAI o3, Google Gemini):

| Component | Decision | Rationale |
|-----------|----------|-----------|
| **Registry** | GHCR | GitHub-integrated, no extra infrastructure |
| **SSL/TLS** | Let's Encrypt DNS-01 | No port 80 exposure, Cloudflare automated |
| **Emergency Access** | Django shell via SSH | Secure, auditable, IT-managed |
| **Redis** | tmpfs (RAM-only) | Ephemeral cache, never touches disk, survives app updates |
| **Backups** | MariaDB → NAS | Focused on critical data |
| **Logging** | Loki + Grafana | Lightweight, automatic rotation |
| **Migrations** | Ansible-controlled | Safe, explicit deployment step |
| **Static Assets** | Build locally, commit | Simple workflow |
| **Celery** | 1 worker/core, autoscale | Conservative start, monitor |
| **Monitoring** | Grafana + Slack | Web-hosted, security-conscious |

## Directory Structure (After Phase 0 Completion)

```
deploy/
├── CLAUDE.md                      # This file
├── ansible/                       # Ansible automation (NEW)
│   ├── inventories/
│   │   ├── staging/
│   │   │   ├── hosts.yml
│   │   │   └── group_vars/
│   │   │       └── vault.yml      # Encrypted secrets
│   │   └── production/
│   │       ├── hosts.yml
│   │       └── group_vars/
│   │           └── vault.yml      # Encrypted secrets
│   ├── roles/
│   │   ├── base/                  # Common setup
│   │   ├── firewall/              # Port restrictions
│   │   ├── hosts_management/      # /etc/hosts management
│   │   ├── nas_mount/             # NAS configuration
│   │   ├── mariadb/               # Database + encryption (bare metal)
│   │   ├── docker_services/       # Container orchestration (services profile)
│   │   ├── wireguard_client/      # Tunnel client (TODO)
│   │   ├── ssl_letsencrypt/       # DNS-01 SSL automation (TODO)
│   │   ├── web_app/               # Django web + Nginx (TODO)
│   │   ├── loki/                  # Log aggregation (TODO)
│   │   ├── grafana/               # Observability (TODO)
│   │   ├── deploy/                # Application updates (TODO)
│   │   └── monitoring/            # Slack alerts (TODO)
│   ├── playbooks/
│   │   ├── services-server.yml    # Full services deploy
│   │   ├── web-server.yml         # Full web deploy
│   │   ├── deploy.yml             # Application update
│   │   ├── health-check.yml       # Verification
│   │   └── rollback.yml           # Emergency rollback
│   └── group_vars/
│       ├── all.yml                # Common variables
│       ├── staging.yml            # Staging config
│       └── production.yml         # Production config
└── containers/                    # Container build context (NEW)
    ├── Dockerfile.web             # Web server image
    ├── Dockerfile.services        # Services server image
    ├── Dockerfile.celery          # Celery worker image
    └── docker-compose.*.yml       # Compose files per environment
```

## Deployment Workflow

### Quick Deployment (RECOMMENDED)

**On the server, just type:**
```bash
deployna
```

This single command:
- Pulls latest code from git (correct branch for environment)
- Copies static assets to container volumes
- Restarts all containers with fresh code
- Verifies container health

**See [docs/aliases-reference.md](docs/aliases-reference.md) for all available aliases.**

### Local Development

```bash
# 1. Build static assets
npm run build

# 2. Commit assets
git add static/
git commit -m "build: compile assets"

# 3. Push to repository
git push origin deploy  # or 'main' for production

# 4. Deploy on server
ssh user@server-ip
deployna  # That's it!
```

### Manual Deployment (Alternative)

```bash
# SSH to target server (with 2FA)
ssh user@server-ip

# Option A: Use deployment script (recommended)
cd /opt/naaccord/depot
./deploy/scripts/2-deploy.sh
# Script auto-detects environment and server role from /etc/naaccord/ marker files

# Option B: Run Ansible playbook directly
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging
```

### Shell Aliases Available on Servers

All NA-ACCORD servers have helpful aliases automatically configured:

| Alias | Description |
|-------|-------------|
| `deployna` | Deploy latest code and restart containers |
| `nahelp` | Show all available aliases |
| `nalogs` | View all container logs |
| `nastatus` | Show container status |
| `nahealth` | Check application health |
| `cdna` | Navigate to /opt/naaccord/depot |

Run `nahelp` on any server to see the complete list.

## Implementation Phases

See **[../docs/deploy-todo-tracking.md](../docs/deploy-todo-tracking.md)** for detailed checklist.

**Summary:**
- **Phase 0**: Archive old code, SAML-only auth ← START HERE
- **Phase 1**: Core infrastructure roles
- **Phase 2**: Dockerfiles and local workflow
- **Phase 3**: Services server infrastructure
- **Phase 4**: Services server applications
- **Phase 5**: Web server setup
- **Phase 6**: Logging and Grafana
- **Phase 7**: Deployment automation
- **Phase 8**: Slack alerting
- **Phase 9**: Staging testing
- **Phase 10**: Production preparation
- **Phase 11**: Production deployment
- **Phase 12**: UAT and handoff

## Security Patterns

### SAML-Only Authentication

**No password-based login exists.** All authentication via SAML:
- Staging: mock-idp container
- Production: JHU Shibboleth

**Emergency access:** See [emergency-access.md](../docs/deployment/guides/emergency-access.md)

### PHI Isolation

**Web server:**
- No PHI stored locally
- All PHI operations streamed to services server via WireGuard

**Services server:**
- All PHI processing
- Encrypted database (MariaDB with file-key-management)
- Encrypted Redis volume
- Complete audit trail (PHIFileTracking)

### Encryption Layers

1. **In transit:**
   - HTTPS (Let's Encrypt)
   - WireGuard tunnel (ChaCha20-Poly1305)
   - Internal API authentication

2. **At rest:**
   - MariaDB full encryption
   - Redis encrypted Docker volume
   - Backups encrypted on NAS (TODO)

## Environment Details

### Staging (Local VMs)

- **Web**: 192.168.50.10 → naaccord.pequod.sh
- **Services**: 192.168.50.11
- **NAS**: smb://192.168.1.10
- **SAML**: Mock-idp

### Production (JHU Servers)

- **Web**: 10.150.96.6 → mrpznaaccordweb01.hosts.jhmi.edu
- **Services**: 10.150.96.37 → mrpznaaccorddb01.hosts.jhmi.edu
- **Access**: VPN required
- **NAS**: //cloud.nas.jh.edu/na-accord$ → /na_accord_nas (100GB)
- **SAML**: JHU Shibboleth (login.jh.edu)

**⚠️ Production-Specific Notes:**
- NAS mount path is `/na_accord_nas` (NOT `/mnt/nas` like staging)
- SAML uses real JHU accounts (entityID: https://login.jh.edu/idp/shibboleth)
- Contact JHU Enterprise Auth team for SAML registration: enterpriseauth@jh.edu
- See [docs/production-differences.md](docs/production-differences.md) for complete production readiness checklist

## Key Files and Locations

### Repository Structure on Servers

**Repository Root:** `/opt/naaccord/` (git working directory)

```
/opt/naaccord/              # Git repository root
├── depot/                  # Django application code
│   ├── models/
│   ├── views/
│   ├── tasks/
│   └── ...
├── deploy/                 # Deployment automation
│   ├── ansible/           # Ansible infrastructure
│   │   ├── inventories/   # Staging & production configs
│   │   ├── playbooks/     # Deployment playbooks
│   │   └── roles/         # Ansible roles
│   └── containers/        # Container definitions
├── docs/                   # Documentation
├── manage.py               # Django management
├── requirements.txt        # Python dependencies
└── ...
```

### Configuration Files

**Ansible Secrets:**
- `/opt/naaccord/deploy/ansible/inventories/staging/group_vars/vault.yml` - Staging secrets (encrypted)
- `/opt/naaccord/deploy/ansible/inventories/production/group_vars/vault.yml` - Production secrets (encrypted)

**Container Builds:**
- `/opt/naaccord/deploy/containers/Dockerfile.web` - Web server image
- `/opt/naaccord/deploy/containers/Dockerfile.services` - Services server image
- `/opt/naaccord/deploy/containers/Dockerfile.celery` - Celery worker image

**Deployment Scripts:**
- `/opt/naaccord/deploy/scripts/deploy.sh` - Quick deployment script (used by `deployna` alias)
- `/opt/naaccord/deploy/ansible/playbooks/services-server.yml` - Full services deployment
- `/opt/naaccord/deploy/ansible/playbooks/web-server.yml` - Full web deployment
- `/opt/naaccord/deploy/ansible/playbooks/deploy.yml` - Application update playbook
- `/opt/naaccord/deploy/ansible/playbooks/health-check.yml` - System verification

**Shell Aliases:**
- `/etc/profile.d/naaccord-aliases.sh` - Alias definitions (automatically sourced on login)
- `/etc/motd` - Message of the day with quick command reference

### Runtime Locations on Servers

**Services Server:**
- Application root: `/opt/naaccord/`
- Django app: `/opt/naaccord/depot/`
- NAS mount: `/mnt/nas/`
- Database encryption keys: `/etc/mysql/encryption/`
- Logs: `/var/log/naaccord/`

**Web Server:**
- Application root: `/opt/naaccord/`
- Django app: `/opt/naaccord/depot/`
- SSL certificates: `/etc/letsencrypt/live/`
- Grafana data: `/var/lib/grafana/`

## Common Operations

### Deploy Application Update

**Quick method (RECOMMENDED):**
```bash
# On target server - just type:
deployna
```

**Alternative methods:**
```bash
# Option A: Using deployment script (auto-detects environment and role)
cd /opt/naaccord/depot
./deploy/scripts/2-deploy.sh

# Option B: Using Ansible playbook directly
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging
```

**What deployment does:**
1. Pulls latest code from git
2. Copies static assets to container volumes
3. Restarts all containers with fresh code
4. Verifies container health

### Check System Health

**Quick method:**
```bash
# On target server
nahealth  # Checks Django health endpoint
nastatus  # Shows all container status
```

**Alternative methods:**
```bash
# Via Ansible playbook
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/health-check.yml \
  --connection local

# Via Grafana (preferred)
# Navigate to https://naaccord.pequod.sh/mon/
```

### View Logs

**Quick method:**
```bash
# On target server
nalogs            # View all container logs
nalogs-services   # View services container only
nalogs-celery     # View Celery worker logs
nalogs-web        # View web container logs
```

**Alternative methods:**
```bash
# Via Docker directly
docker logs naaccord-services -f
docker logs naaccord-celery -f

# Via Grafana/Loki (preferred)
# Navigate to /mon/, select Loki data source
```

### Emergency Access

If SAML is down, IT can access via Django shell:

```bash
ssh user@services-server
docker exec -it naaccord-services python manage.py shell
# Create emergency superuser, make changes, delete account
```

See [emergency-access.md](../docs/deployment/guides/emergency-access.md) for full procedure.

## Troubleshooting

### Ansible Issues

```bash
# Verify vault password
ansible-vault view inventories/staging/group_vars/vault.yml

# Check inventory
ansible-inventory -i inventories/staging/hosts.yml --list

# Test connection (won't work with --connection local)
ansible all -i inventories/staging/hosts.yml -m ping
```

### Container Issues

**Quick method:**
```bash
# On target server
nastatus   # Check all container status
nalogs     # View all logs
narestart  # Restart all containers
```

**Alternative (manual):**
```bash
# Check status
docker ps -a

# View logs
docker logs naaccord-services
docker logs naaccord-celery

# Restart
docker restart naaccord-services
```

### WireGuard Tunnel

```bash
# Check tunnel
docker exec wireguard-client wg show
docker exec wireguard-server wg show

# Test connectivity
ping 10.100.0.11  # from web to services
ping 10.100.0.10  # from services to web
```

## Related Documentation

**Deployment Docs:**
- [../docs/deployment/README.md](../docs/deployment/README.md) - Documentation hub
- [../docs/deployment/guides/architecture.md](../docs/deployment/guides/architecture.md) - Architecture overview
- [../docs/deployment/guides/deployment-workflow.md](../docs/deployment/guides/deployment-workflow.md) - How to deploy
- [../docs/deployment/guides/emergency-access.md](../docs/deployment/guides/emergency-access.md) - Emergency procedures

**Implementation:**
- [../docs/deploy-todo-tracking.md](../docs/deploy-todo-tracking.md) - Phase-by-phase checklist

**Main Project:**
- [../CLAUDE.md](../CLAUDE.md) - Main development guide
- [../docs/CLAUDE.md](../docs/CLAUDE.md) - Documentation domain overview

## Next Steps

**If starting fresh deployment:**
1. Review [architecture.md](../docs/deployment/guides/architecture.md)
2. Follow [deploy-todo-tracking.md](../docs/deploy-todo-tracking.md)
3. Start with Phase 0 (archive and SAML-only auth)

**If updating existing deployment:**
1. Build assets locally: `npm run build`
2. Commit and push: `git add static/ && git commit -m "build: assets" && git push`
3. SSH to server
4. Deploy: `deployna` (or `./deploy/scripts/deploy.sh staging deploy`)
5. Verify: `nahealth` and `nastatus`

**For emergencies:**
1. See [emergency-access.md](../docs/deployment/guides/emergency-access.md)
2. Use Django shell via SSH
3. Document all actions
4. Clean up emergency access when done
