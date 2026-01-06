# NA-ACCORD Deployment Implementation Tracking

**Last Updated:** 2025-10-02
**Status:** Bootstrap Complete on Services Server, Phase 1 Starting

**Current State:**
- ✅ Staging services server bootstrapped (services.naaccord.lan)
- ✅ Repository cloned to `/opt/naaccord/`
- ✅ Ansible installed and ready
- ✅ GitHub deploy key configured
- 🎯 Ready to build Phase 1 Ansible infrastructure

**Next Steps:**
- Create Ansible directory structure and inventories
- Build core infrastructure roles (base, firewall, hosts, NAS)
- Working directly on services server for faster iteration

## Server Setup Prerequisites

Before beginning Phase 1, perform initial server setup:

```bash
# SSH to services server
ssh services.naaccord.lan

# Create application directory
sudo mkdir -p /opt/naaccord
sudo chown $(whoami):$(whoami) /opt/naaccord

# Clone repository
cd /opt
git clone https://github.com/jhbiostatcenter/naaccord-data-depot.git naaccord
cd naaccord
git checkout deploy  # or main branch

# Install Claude Code (optional, for easier on-server development)
# Follow: https://github.com/anthropics/claude-code
```

**Repository structure on server:**
```
/opt/naaccord/              # Git repository root (working directory)
├── depot/                  # Django application code
├── deploy/ansible/         # Ansible playbooks and roles
├── docs/                   # Documentation
└── manage.py               # Django management
```

## Implementation Phases

### Phase 0: Foundation & Authentication ✅ COMPLETE
- [x] Archive existing Ansible code to `deploy-backup-2025-10-02/`
- [x] Archive existing deployment documentation to `docs/deployment-backup-2025-10-02/`
- [x] Update Django to SAML-only authentication (remove password login)
- [x] Create SAMLAdminSite to redirect admin login to SAML
- [x] Document IT emergency access via Django shell (`docs/deployment/guides/emergency-access.md`)
- [x] Create new deployment documentation structure in `docs/deployment/`
- [x] Create architecture guide (`docs/deployment/guides/architecture.md`)
- [x] Create deployment workflow guide (`docs/deployment/guides/deployment-workflow.md`)
- [x] Update `deploy/CLAUDE.md` with new architecture and links
- [x] Test SAML authentication with mock-idp
- [x] Commit Phase 0 changes

### Phase 1: Core Infrastructure Roles 🎯 NEXT
- [ ] Create Ansible directory structure: `deploy/ansible/{roles,playbooks,inventories}`
- [ ] Create inventory files for staging and production
- [ ] Initialize Ansible vault for staging and production secrets
- [ ] Create `base` role: Docker, common packages, user setup
- [ ] Create `firewall` role: UFW configuration (Services: 22+51820, Web: 22+443)
- [ ] Create `hosts_management` role: /etc/hosts entries for WireGuard tunnel IPs
- [ ] Create `nas_mount` role: CIFS/SMB mounting with vault credentials
- [ ] Test roles on local VMs

### Phase 2: Dockerfiles & Local Workflow
- [ ] Create `deploy/containers/Dockerfile.web` for web server
- [ ] Create `deploy/containers/Dockerfile.services` for services server
- [ ] Create `deploy/containers/Dockerfile.celery` for Celery workers
- [ ] Create docker-compose files for each environment
- [ ] Document local build workflow (npm run build + commit assets)
- [ ] Document container build and push to GHCR
- [ ] Test Docker builds locally
- [ ] Push initial images to GHCR

### Phase 3: Services Server Infrastructure
- [ ] Create `mariadb` role: Encrypted database with file-key-management
- [ ] Create `redis` role: Docker with encrypted volume + RDB snapshots every 5min
- [ ] Create `wireguard_server` role: Tunnel server (10.100.0.11 on 10.100.0.0/24)
- [ ] Create services server playbook: `playbooks/services-server.yml`
- [ ] Test MariaDB encryption keys
- [ ] Test Redis persistence through restart
- [ ] Test WireGuard server configuration

### Phase 4: Services Server Applications
- [ ] Create `services_app` role: Django services + internal API
- [ ] Create `services_celery` role: Celery workers (1 worker/core, autoscale)
- [ ] Create `services_flower` role: Flower monitoring (localhost:5555)
- [ ] Update services playbook with application roles
- [ ] Test complete services stack
- [ ] Verify internal API authentication

### Phase 5: Web Server Setup
- [ ] Create `wireguard_client` role: Connect to services tunnel (10.100.0.10)
- [ ] Create `ssl_letsencrypt` role: DNS-01 with Cloudflare automation
- [ ] Create `web_app` role: Django web + Nginx reverse proxy
- [ ] Create web server playbook: `playbooks/web-server.yml`
- [ ] Test WireGuard tunnel connectivity (ping 10.100.0.11)
- [ ] Test SSL certificate automation
- [ ] Test Nginx → Django → Services API flow

### Phase 6: Logging and Grafana
- [ ] Create `loki` role: Log aggregation on services server
- [ ] Create `grafana` role: Grafana on web server at /mon path
- [ ] Configure Grafana data source for Loki (via WireGuard tunnel)
- [ ] Create Grafana dashboard: Application logs
- [ ] Create Grafana dashboard: System metrics
- [ ] Create Grafana dashboard: Celery monitoring
- [ ] Test log aggregation from all containers

### Phase 7: Deployment Automation
- [ ] Create `deploy` role: Git pull + migrations + container rebuild + health checks
- [ ] Create deployment playbook: `playbooks/deploy.yml`
- [ ] Create health check playbook: `playbooks/health-check.yml`
- [ ] Create rollback playbook: `playbooks/rollback.yml`
- [ ] Test deployment workflow
- [ ] Document deployment procedures

### Phase 8: Slack Alerting
- [ ] Add Slack webhook URL to Ansible vault
- [ ] Configure Grafana contact points (Slack)
- [ ] Create alert rules: Service down
- [ ] Create alert rules: Celery queue backed up
- [ ] Create alert rules: Database errors
- [ ] Test Slack alert delivery
- [ ] Document alert escalation procedures

### Phase 9: Staging Testing
- [ ] Deploy to staging services server (192.168.50.11)
- [ ] Deploy to staging web server (192.168.50.10)
- [ ] Configure mock-idp SAML metadata
- [ ] Test complete workflow: Login → Upload → Process → Report
- [ ] Validate WireGuard tunnel security and encryption
- [ ] Verify PHI isolation (web server has no PHI stored)
- [ ] Check all Grafana dashboards
- [ ] Test Slack alerts
- [ ] Test deployment automation
- [ ] Document issues and refine

### Phase 10: Production Preparation
- [ ] Coordinate with JHU IT for Shibboleth configuration
- [ ] Exchange SAML metadata with JHU
- [ ] Confirm NAS mount path and credentials
- [ ] Generate production secrets (database passwords, API keys)
- [ ] Create production Ansible vault
- [ ] Update production inventory with server details
- [ ] Create production DNS entries
- [ ] Obtain Cloudflare API token for production SSL

### Phase 11: Production Deployment
- [ ] Deploy to production services server (10.150.96.37)
- [ ] Deploy to production web server (10.150.96.6)
- [ ] Configure JHU Shibboleth SAML
- [ ] Test SAML authentication with real JHU accounts
- [ ] Verify database encryption
- [ ] Verify WireGuard tunnel
- [ ] Test complete application workflow
- [ ] Run security validation checklist
- [ ] Verify HIPAA compliance requirements

### Phase 12: UAT and Handoff
- [ ] User acceptance testing with pilot cohort users
- [ ] Security audit and penetration testing
- [ ] HIPAA compliance documentation review
- [ ] Create operational runbooks for IT team
- [ ] Train IT team on emergency access procedures
- [ ] Train IT team on deployment procedures
- [ ] Establish monitoring and alerting procedures
- [ ] Document known issues and workarounds
- [ ] Create incident response procedures
- [ ] Handoff to operations team

---

## Non-Blocking TODOs (Future Work)

### Database Backups (Can be added after initial deployment)
- [ ] Create backup volume on NAS
- [ ] Create Ansible role for daily MariaDB backups
- [ ] Set up systemd timer for automated backups
- [ ] Test backup restoration procedure
- [ ] Document backup/restore procedures

---

## Critical Dependencies

### External Coordination Required
- **JHU Shibboleth**: Configuration, metadata exchange, testing window
- **NAS Access**: Server address, mount path, credentials
- **Cloudflare**: API token for DNS-01 SSL challenges
- **Slack**: Webhook URL for Grafana alerts

### Technical Validation Checkpoints
- WireGuard tunnel reliability under load
- MariaDB encryption performance impact
- SAML attribute mapping correctness
- PHI isolation architecture (web server has no PHI)

---

## Environment Details

### Staging Environment
- **Web Server**: 192.168.50.10 (web.naaccord.lan)
  - Public: naaccord.pequod.sh (via Cloudflare)
  - Tunnel IP: 10.100.0.10
- **Services Server**: 192.168.50.11 (services.naaccord.lan)
  - Tunnel IP: 10.100.0.11
- **NAS**: smb://192.168.1.10
- **SAML**: Mock-idp (self-hosted)

### Production Environment
- **Web Server**: 10.150.96.6 (mrpznaaccordweb01.hosts.jhmi.edu)
  - Tunnel IP: 10.100.0.10
  - VPN required for access
- **Services Server**: 10.150.96.37
  - Tunnel IP: 10.100.0.11
  - VPN required for access
- **NAS**: TBD (to be provided by JHU IT)
- **SAML**: Johns Hopkins Shibboleth

---

## Deployment Workflow

```
Local Development:
1. Make code changes
2. npm run build (compile static assets)
3. git add static/ && git commit
4. git push
5. docker build & push to GHCR

Ansible Deploy:
1. SSH to server
2. Run deploy playbook
3. Playbook executes:
   - git pull latest code
   - Run migrations (web only)
   - Rebuild containers
   - Restart services
   - Health checks
```

---

## Success Metrics
- [ ] All HIPAA compliance requirements met
- [ ] Complete audit trail for all PHI operations
- [ ] Full observability with Grafana dashboards
- [ ] Automated deployment via Ansible
- [ ] Documented runbooks for all operations
- [ ] IT team trained on emergency procedures
