# NA-ACCORD Data Depot Technical Administration Guide

**Version 1.0 | Last Updated: October 2025**

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Security Model](#security-model)
4. [Installation and Setup](#installation-and-setup)
5. [Routine Maintenance](#routine-maintenance)
6. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
7. [Backup and Recovery](#backup-and-recovery)
8. [Disaster Recovery](#disaster-recovery)
9. [Development Workflow](#development-workflow)
10. [Deployment Procedures](#deployment-procedures)

---

## System Overview

### What This System Does

NA-ACCORD Data Depot is a clinical research data validation and storage platform that:
- Validates large clinical datasets (up to 40M rows) against JSON-defined schemas
- Generates interactive HTML reports using R/Quarto notebooks
- Manages multi-file submissions with version tracking
- Provides HIPAA-compliant PHI processing with complete audit trails
- Enforces cohort-based access control

### Technology Stack

**Backend:**
- Python 3.12+ (Django 5.x web framework)
- Celery for async task processing
- MariaDB for metadata storage (bare metal installation)
- Redis for caching and Celery broker
- R with NAATools package for data validation
- DuckDB for efficient analytics on large datasets

**Frontend:**
- Vite build system
- Alpine.js for reactive UI
- Tailwind CSS for styling

**Infrastructure:**
- Red Hat Enterprise Linux (RHEL) 9.6
- Docker containers for application services
- Nginx reverse proxy (in container)
- WireGuard VPN for PHI-compliant data transit (in container)
- NAS storage for long-term archival

**Deployment Automation:**
- Ansible for all infrastructure management
- GitHub Container Registry (GHCR) for container images
- Git-based deployment workflow

### Key Features

1. **Multi-Server PHI Architecture**: Web and services tiers with encrypted data transit
2. **Storage Abstraction**: Automatic driver selection based on server role
3. **Complete Audit Trails**: PHIFileTracking system logs every file operation
4. **DuckDB Processing**: Efficient handling of large datasets
5. **R-based Validation**: Statistical validation using NAATools package
6. **Quarto Reports**: Dynamic HTML reports with embedded visualizations
7. **Version Tracking**: Complete history of file uploads and modifications
8. **Ansible-Managed**: All deployment and configuration via Ansible playbooks

---

## Architecture

### Production Deployment Model

The system uses a two-server architecture for HIPAA compliance:

```
┌───────────────────────────────────────────────────────────────┐
│                         Web Server                            │
│                (mrpznaaccordweb01.hosts.jhmi.edu)            │
│                                                               │
│  ┌──────────────┐         ┌─────────────────┐                 │
│  │   Nginx      │────────>│  Django Web     │                 │
│  │  (Container) │         │  (Container)    │                 │
│  └──────────────┘         └─────────────────┘                 │
│                                    │                          │
│                           ┌─────────────────┐                 │
│                           │   WireGuard     │                 │
│                           │  (10.100.0.10)  │                 │
│                           │  (Container)    │                 │
│                           └─────────────────┘                 │
│                                    │                          │
│                              Encrypted PHI                    │
│                              ChaCha20-Poly1305                │
└─────────────────────────────────┼─────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────┐
│                      Services Server                          │
│                (mrpznaaccorddb01.hosts.jhmi.edu)             │
│                                                               │
│  ┌─────────────────┐         ┌─────────────────┐              │
│  │   WireGuard     │────────>│  Django API     │              │
│  │  (10.100.0.11)  │         │  (Container)    │              │
│  │  (Container)    │         └─────────────────┘              │
│  └─────────────────┘                │                        │
│                                     │                         │
│  ┌─────────────────┐         ┌─────────────────┐              │
│  │  Celery Worker  │<────────│  Redis Broker   │              │
│  │  (Container)    │         │  (Container)    │              │
│  └─────────────────┘         └─────────────────┘              │
│           │                                                   │
│           ├──────> R Processing (NAATools + Quarto)           │
│           ├──────> DuckDB Analytics                           │
│           └──────> PHI File Operations                        │
│                                                               │
│  ┌─────────────────┐                                          │
│  │    MariaDB      │  ← Bare Metal Installation               │
│  │  (Encrypted)    │                                          │
│  └─────────────────┘                                          │
│                                                               │
│  ┌─────────────────────────────────────────────┐              │
│  │        NAS Mount (/na_accord_nas)           │              │
│  │        Long-term Archival Storage           │              │
│  └─────────────────────────────────────────────┘              │
└───────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**Web Server:**
- HTTPS termination with Nginx (containerized)
- User authentication (SAML SSO)
- Depot App web interface (containerized)
- File upload streaming (never stores PHI locally)
- RemoteStorageDriver for all PHI operations

**Services Server:**
- Depot App API for internal operations (containerized)
- Celery async task processing (containerized)
- R/Quarto report generation
- DuckDB data processing
- MariaDB database (bare metal, encrypted)
- Redis cache (containerized)
- PHI file storage and processing

**Key Design Principles:**
1. Web server NEVER stores PHI data locally
2. All PHI operations logged to PHIFileTracking
3. Encrypted data transit via WireGuard
4. Complete separation of web and processing tiers
5. Automatic cleanup of temporary files
6. All infrastructure managed via Ansible

### Storage Architecture

The system uses local file system storage:

**Storage Types:**
1. **Scratch Storage**: Temporary processing files (auto-cleanup)
2. **Submission Storage**: Permanent file storage (NAS mount)
3. **Report Storage**: Generated HTML reports (local file system)

**Storage Drivers:**
- `LocalFileSystemStorage`: Direct file system access (services server)
- `RemoteStorageDriver`: Streams to services API (web server)

**Production Storage:**
- NAS Mount Point: `/na_accord_nas` (NOT `/mnt/nas`)
- NAS Path: `//cloud.nas.jh.edu/na-accord$`
- Capacity: 100GB

---

## Security Model

### HIPAA Compliance

The system implements technical safeguards for HIPAA compliance:

**Access Control:**
- Cohort-based access restrictions
- Role-based permissions (site admin, cohort manager, viewer)
- SAML SSO with JHU Shibboleth (production)
- API key authentication for server-to-server

**Audit Trail:**
- PHIFileTracking logs every file operation
- 20+ action types covering all PHI operations
- User activity tracking
- Complete file lifecycle documentation

**Data Protection:**
- Encryption in transit (HTTPS + WireGuard)
- Encryption at rest (MariaDB encrypted storage)
- No PHI on web tier
- Automatic temporary file cleanup

**Integrity Controls:**
- File hash verification
- Corruption detection
- Cleanup verification commands
- Overdue file tracking

### PHI File Tracking

Every PHI operation is logged:

```python
PHIFileTracking.log_operation(
    cohort=cohort,
    user=user,
    action='nas_raw_created',
    file_path='/na_accord_nas/submissions/cohort_123/patient_data.csv',
    file_type='raw_csv',
    file_size=1024000,
    content_object=audit_instance
)
```

### Management Commands for Security

```bash
# View complete PHI audit trail
docker exec naaccord-services python manage.py show_phi_audit_trail --cohort 5 --days 7

# Verify file integrity
docker exec naaccord-services python manage.py verify_phi_integrity --check-hashes

# Check cleanup completion
docker exec naaccord-services python manage.py verify_phi_cleanup --overdue-only --hours 24
```

### Network Security

**WireGuard VPN Configuration:**
- ChaCha20-Poly1305 encryption
- Peer-to-peer authentication
- Managed via Ansible wireguard role
- Containerized deployment

**Firewall Rules (Managed via Ansible):**
- Web server: 80, 443 open to internet
- Services server: No direct internet access
- WireGuard: 51820 between servers only
- Database: Local access only

---

## Installation and Setup

### Prerequisites

**System Requirements:**
- Red Hat Enterprise Linux (RHEL) 9.6
- 8GB RAM minimum (16GB recommended)
- 100GB disk space minimum
- Ansible 2.9+ (on control machine)
- Python 3.12+, R 4.0+, Node.js 16+ (installed via Ansible)

**Network Requirements:**
- Static IP addresses for both servers
- DNS records configured
- SSL certificates from JHU IT
- WireGuard connectivity between servers

### Ansible-Based Setup

**⚠️ CRITICAL: All infrastructure is deployed via Ansible. Do not manually configure servers.**

#### Initial Server Setup

```bash
# On your local machine (Ansible control machine)

# 1. Clone repository
git clone <repository-url> naaccord
cd naaccord/deploy/ansible

# 2. Configure inventory
# Edit inventories/production/hosts.yml with server IPs

# 3. Set up Ansible vault password
echo "your-vault-password" > ~/.naaccord_vault_production
chmod 600 ~/.naaccord_vault_production

# 4. Deploy services server (complete setup)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file ~/.naaccord_vault_production

# 5. Deploy web server (complete setup)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --vault-password-file ~/.naaccord_vault_production
```

#### What Ansible Does

**Services Server Playbook** (`services-server.yml`):
- Installs base packages (Git, Python, R, Node.js)
- Configures firewall rules
- Manages /etc/hosts entries
- Mounts NAS storage at `/na_accord_nas`
- Installs and configures MariaDB (bare metal, encrypted)
- Creates Docker secrets
- Configures SAML metadata
- Sets up log rotation
- Deploys Docker containers (services, celery, redis, wireguard)
- Configures WireGuard VPN server

**Web Server Playbook** (`web-server.yml`):
- Installs base packages
- Configures firewall rules
- Manages /etc/hosts entries
- Sets up SSL certificates (manual mode - IT-provided)
- Creates Docker secrets
- Configures SAML metadata
- Sets up log rotation
- Deploys Docker containers (web, nginx, wireguard)
- Configures WireGuard VPN client

### SSL Certificate Setup (Production)

**⚠️ JHU IT provides SSL certificates. Ansible expects them at specific locations.**

Ansible `ssl` role with `ssl_provider: manual`:
1. Verifies IT has placed certificates at configured paths
2. Creates LetsEncrypt-compatible symlink structure
3. No automatic certificate generation (no certbot)

**IT must provide:**
- Certificate: `/etc/pki/tls/certs/na-accord-depot.crt`
- Private Key: `/etc/pki/tls/private/na-accord-depot.key`
- CA Bundle: `/etc/pki/tls/certs/na-accord-depot-ca-bundle.crt`

### SAML Configuration

SAML is configured via Ansible `saml` role:
- Stores IdP metadata in Ansible vault
- Deploys metadata to servers during playbook run
- No manual SAML configuration needed

**Production SAML:**
- IdP: JHU Shibboleth (login.jh.edu)
- Entity ID: https://na-accord-depot.publichealth.jhu.edu
- Contact: enterpriseauth@jh.edu for SP registration

---

## Routine Maintenance

### Daily Tasks

**Automated (via systemd timers - if configured):**
- Database backups (⚠️ NOT YET IMPLEMENTED)
- Storage cleanup verification (via scheduled Celery tasks)
- Health checks (external monitoring)
- Log rotation (via logrotate Ansible role)

**Manual Checks:**
```bash
# SSH to server first
ssh user@server-ip

# Check service health
nahealth  # Shell alias for health check

# Check container status
nastatus  # Shell alias for docker ps

# Review recent uploads
docker exec naaccord-services python manage.py show_recent_uploads --days 1

# Check for failed Celery tasks
docker exec naaccord-celery celery -A depot inspect active
```

### Weekly Tasks

```bash
# SSH to server first

# 1. Review PHI audit trail
docker exec naaccord-services python manage.py show_phi_audit_trail --days 7

# 2. Check for overdue cleanup files
docker exec naaccord-services python manage.py verify_phi_cleanup --overdue-only

# 3. Review storage usage
du -sh /na_accord_nas/*

# 4. Check for failed audits
docker exec naaccord-services python manage.py list_failed_audits --days 7

# 5. Review application logs
docker logs naaccord-services --since 7d | grep -i error
docker logs naaccord-celery --since 7d | grep -i error
```

### Monthly Tasks

```bash
# 1. Update dependencies (via Ansible)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/deploy-update.yml \
  --vault-password-file ~/.naaccord_vault_production

# 2. Security updates (via Ansible base role)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file ~/.naaccord_vault_production \
  --tags packages

# 3. Review user access
docker exec naaccord-services python manage.py list_inactive_users --days 90

# 4. Verify MariaDB encryption
docker exec naaccord-services python manage.py check_database_encryption
```

### Container Management

**⚠️ Containers are managed via Ansible and shell aliases. Avoid manual docker commands.**

```bash
# View running containers
docker ps  # Or: nastatus

# View container logs
nalogs              # All logs
nalogs-services     # Services only
nalogs-celery       # Celery only
nalogs-web          # Web only

# Restart containers (use deployna instead)
deployna  # Recommended: pulls latest code and restarts

# Manual restart (if needed)
cd /opt/naaccord/depot
sudo docker compose -f docker-compose.prod.yml --profile services restart
```

---

## Monitoring and Troubleshooting

### Health Check Endpoints

```bash
# Web server health
curl https://na-accord-depot.publichealth.jhu.edu/health

# Services server health (from services server)
curl http://localhost:8001/health

# Expected response:
{
  "status": "healthy",
  "database": "ok",
  "redis": "ok",
  "storage": "ok",
  "celery": "ok"
}
```

### Log Locations

**Container Logs (via Docker):**
```bash
# Use shell aliases (recommended)
nalogs              # View all logs
nalogs-services     # Depot App services
nalogs-celery       # Celery worker
nalogs-web          # Depot App web
nalogs-nginx        # Nginx
nalogs-mariadb      # MariaDB

# Or docker logs directly
docker logs naaccord-services
docker logs naaccord-celery
docker logs naaccord-web
docker logs naaccord-nginx
```

**System Logs:**
```bash
# System journal (if needed)
journalctl -u docker -f

# MariaDB logs (bare metal)
tail -f /var/log/mariadb/mariadb.log
```

### Common Issues

#### Upload Fails with "Connection Refused"

**Diagnosis:**
```bash
# Check WireGuard connectivity
docker exec wireguard-client ping 10.100.0.11  # From web server
docker exec wireguard-server ping 10.100.0.10  # From services server

# Check services server is running
curl http://10.100.0.11:8001/health
```

**Resolution:**
```bash
# Restart WireGuard containers (via Ansible)
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --vault-password-file ~/.naaccord_vault_production \
  --tags wireguard
```

#### Celery Tasks Stuck

**Diagnosis:**
```bash
# Check Celery workers
docker exec naaccord-celery celery -A depot inspect active
docker exec naaccord-celery celery -A depot inspect stats

# Check Redis connectivity
docker exec naaccord-services redis-cli ping
```

**Resolution:**
```bash
# Restart containers (use deployna)
ssh user@services-server
deployna
```

#### Database Connection Errors

**Diagnosis:**
```bash
# Check MariaDB is running (bare metal)
systemctl status mariadb

# Check connection from container
docker exec naaccord-services python manage.py dbshell
```

**Resolution:**
```bash
# Restart MariaDB
sudo systemctl restart mariadb

# Re-deploy containers
deployna
```

---

## Backup and Recovery

### Backup Strategy

**What to Back Up:**
1. MariaDB database (all application metadata) - ⚠️ **NOT YET IMPLEMENTED**
2. NAS storage (/na_accord_nas/submissions - permanent file storage)
3. Local report storage (if any)
4. Ansible vault files (encrypted secrets)
5. SSL certificates (IT-managed)

**What NOT to Back Up:**
- Temporary scratch storage
- Docker container data (rebuilt from images)
- Application logs (managed by logrotate)
- Redis cache (transient)

### Database Backup

**⚠️ IMPORTANT: Database backup automation is NOT YET IMPLEMENTED.**

**Manual backup procedure:**
```bash
# On services server
mysqldump \
  -u root \
  -p \
  --all-databases \
  --single-transaction \
  --quick \
  --lock-tables=false \
  | gzip > /backup/naaccord_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Storage Backup

```bash
# Backup NAS storage
rsync -av --progress /na_accord_nas/submissions/ /backup/nas/submissions/
```

### Configuration Backup

Ansible vault files are your configuration backup:
- `inventories/production/group_vars/all/vault.yml`
- Keep these encrypted and version-controlled

---

## Disaster Recovery

### Complete Server Rebuild

**⚠️ Use Ansible playbooks to rebuild servers. This is the tested recovery path.**

#### Services Server Recovery

```bash
# On your local machine (Ansible control)

# 1. Provision new RHEL 9.6 server with same IP
# 2. Ensure SSH access configured
# 3. Run full services server playbook
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file ~/.naaccord_vault_production

# 4. Restore database (once backup implemented)
ssh user@services-server
# Restore database backup here

# 5. Verify services
nahealth
nastatus
```

#### Web Server Recovery

```bash
# On your local machine (Ansible control)

# 1. Provision new RHEL 9.6 server with same IP
# 2. Ensure SSH access configured
# 3. Coordinate with IT for SSL certificates
# 4. Run full web server playbook
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --vault-password-file ~/.naaccord_vault_production

# 5. Verify web server
curl https://na-accord-depot.publichealth.jhu.edu/health
```

### Emergency Contacts

**Primary Contact:**
- Name: [Your name]
- Email: [Your email]
- Phone: [Your phone]

**JHU IT Support:**
- Email: [IT support email]
- Phone: [IT support phone]

**Hosting/Infrastructure:**
- JHU IT Infrastructure team

---

## Development Workflow

### Local Development Setup

See main `CLAUDE.md` for complete development setup instructions.

**Quick summary:**
```bash
# Clone and setup
git clone <repository-url> naaccord
cd naaccord
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install R packages
R -e "remotes::install_github('JHBiostatCenter/naaccord-r-tools')"

# Install Node packages
npm install

# Run local development
python manage.py reset_dev_complete
python manage.py runserver
```

---

## Deployment Procedures

### Quick Deployment (Recommended)

**On the server:**
```bash
# SSH to server
ssh user@server-ip

# Just type:
deployna
```

This single command:
- Pulls latest code from git
- Pulls latest Docker images from GHCR
- Stops containers
- Starts updated containers
- Runs Depot App database migrations
- Copies static assets
- Verifies health

### Deployment via Ansible

**From your local machine:**
```bash
cd /path/to/naaccord/deploy/ansible

# Deploy to production
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/deploy-update.yml \
  --vault-password-file ~/.naaccord_vault_production

# Deploy to staging
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/deploy-update.yml \
  --vault-password-file ~/.naaccord_vault_staging
```

### Pre-Deployment Checklist

- [ ] All tests passing locally
- [ ] Code reviewed and approved
- [ ] Static assets built (`npm run build`)
- [ ] Changes committed and pushed to git
- [ ] Docker images built and pushed to GHCR
- [ ] Deployment tested on staging
- [ ] Users notified of maintenance window (if needed)

### Deployment Steps

The `deploy-update.yml` playbook performs these steps:

1. **Detect Environment**: Reads `/etc/naaccord/environment` marker
2. **Pull Code**: `git pull origin main`
3. **Login to GHCR**: Authenticates with GitHub Container Registry
4. **Pull Images**: `docker compose pull`
5. **Stop Containers**: `docker compose down`
6. **Start Containers**: `docker compose up -d`
7. **Wait for Ready**: Waits for services container
8. **Run Migrations**: `python manage.py migrate`
9. **Copy Static**: Copies static files to web container
10. **Fix Permissions**: Sets correct ownership for nginx
11. **Update Aliases**: Refreshes shell aliases
12. **Verify**: Shows running containers

### Rollback Procedure

**If deployment fails:**

```bash
# SSH to server
ssh user@server-ip

# Check git log
cd /opt/naaccord/depot
git log --oneline -10

# Revert to previous commit
git checkout <previous-commit-hash>

# Re-deploy
deployna

# Verify
nahealth
nastatus
```

**For major rollback, use Ansible:**
```bash
# From local machine
# Update git to previous commit, then:
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/deploy-update.yml \
  --vault-password-file ~/.naaccord_vault_production
```

---

## Appendix: Quick Reference

### Essential Commands (On Servers)

**Shell Aliases** (automatically configured):
```bash
deployna              # Deploy latest code
nahelp                # Show all available aliases
nalogs                # View all container logs
nastatus              # Show container status
nahealth              # Check application health
cdna                  # Navigate to /opt/naaccord/depot
narestart             # Restart all containers
narefresh             # Reload shell aliases
```

Type `nahelp` on any server to see the complete list.

### Ansible Playbooks

**Full Infrastructure:**
- `playbooks/services-server.yml` - Complete services server setup
- `playbooks/web-server.yml` - Complete web server setup

**Deployment:**
- `playbooks/deploy-update.yml` - Application update only

**Specific Roles:**
```bash
# Run specific Ansible role
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file ~/.naaccord_vault_production \
  --tags firewall  # Only firewall configuration
```

### File Locations

**On Servers:**
```
/opt/naaccord/depot/              # Repository root
/opt/naaccord/depot/depot/        # Depot App code
/opt/naaccord/depot/deploy/       # Deployment automation
/na_accord_nas/                   # NAS mount (production)
/etc/naaccord/environment         # Environment marker (staging/production)
/etc/profile.d/naaccord-aliases.sh # Shell aliases
/etc/pki/tls/certs/               # SSL certificates (IT-managed)
```

**Ansible:**
```
deploy/ansible/inventories/production/hosts.yml          # Server inventory
deploy/ansible/inventories/production/group_vars/vault.yml # Encrypted secrets
deploy/ansible/playbooks/                                # Playbooks
deploy/ansible/roles/                                    # Ansible roles
```

### Important URLs

**Production:**
- Web UI: https://na-accord-depot.publichealth.jhu.edu
- SAML Login: https://na-accord-depot.publichealth.jhu.edu/saml2/login/
- Health Check: https://na-accord-depot.publichealth.jhu.edu/health
- Admin: https://na-accord-depot.publichealth.jhu.edu/admin

**Internal (Services Server):**
- Services API: http://10.100.0.11:8001
- Health Check: http://10.100.0.11:8001/health

### Port Reference

| Service | Port | Access |
|---------|------|--------|
| Nginx (HTTPS) | 443 | Public |
| Nginx (HTTP) | 80 | Public (redirects to 443) |
| Depot App Web | 8000 | Internal (via Nginx container) |
| Depot App Services | 8001 | WireGuard only |
| MariaDB | 3306 | Localhost only (bare metal) |
| Redis | 6379 | Container network only |
| WireGuard | 51820 | Server-to-server |

---

**Document Version**: 1.0
**Last Updated**: October 2025
**Maintained By**: NA-ACCORD Technical Team

**For Deployment Issues**: See `deploy/CLAUDE.md` and `deploy/deploy-steps.md`

---

*This guide reflects the Ansible-managed infrastructure. All configuration changes should be made via Ansible playbooks, not manual server modifications.*
