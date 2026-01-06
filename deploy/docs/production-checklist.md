# Production Deployment Checklist

Quick reference for production deployment. See [production-differences.md](production-differences.md) for detailed information.

## Pre-Deployment (Complete Before Deployment Day)

### Infrastructure Setup
- [ ] VPN access to JHU network confirmed
- [ ] SSH access to both servers verified (mrpznaaccordweb01, mrpznaaccorddb01)
- [ ] NAS mount tested: `//cloud.nas.jh.edu/na-accord$` → `/na_accord_nas`
- [ ] WireGuard port 51820 allowed between servers in firewall

### SAML Configuration
- [ ] Production domain name obtained from JHU IT
- [ ] NA-ACCORD registered as SP with JHU Enterprise Auth (enterpriseauth@jh.edu)
- [ ] X509 certificates populated in `deploy/idp_metadata_production.xml`
- [ ] Test JHU account identified for SAML testing
- [ ] Entity ID updated in production inventory: `saml_entity_id`

### Configuration Files
- [ ] `resources/data/seed/cohorts.production.csv` populated with actual cohorts
- [ ] `deploy/ansible/inventories/production/group_vars/all/main.yml` reviewed
- [ ] `deploy/ansible/inventories/production/group_vars/all/vault.yml` populated
- [ ] Production vault password created and shared securely with team
- [ ] Verify `nas_mount_point: "/na_accord_nas"` in production inventory

### SSL/TLS
- [ ] Production domain DNS records configured
- [ ] SSL certificate provisioning coordinated with JHU IT
- [ ] Certificate renewal process documented

### Database
- [ ] MariaDB encryption keys secured
- [ ] Backup location on NAS confirmed: `/na_accord_nas/backups/`
- [ ] Backup retention policy agreed: 30 days
- [ ] Backup restoration tested on staging

### Monitoring
- [ ] Grafana workspace created for production
- [ ] Slack webhook obtained for alerts
- [ ] Loki retention policy configured: 7 days
- [ ] Alert escalation procedure documented

### Documentation
- [ ] Emergency access procedure reviewed with IT
- [ ] Runbook updated with production specifics
- [ ] Support contact list populated
- [ ] Rollback plan reviewed and approved

## Deployment Day

### Server Preparation
```bash
# On BOTH servers (web and services):

# 1. Bootstrap server
./1-init-server.sh production

# 2. Verify marker files
cat /etc/naaccord/environment     # Should show: production
cat /etc/naaccord/server-role     # Should show: web or services

# 3. Verify vault password
cat ~/.naaccord_vault_production  # Should contain password
```

### Services Server Deployment
```bash
# On mrpznaaccorddb01 (services server):

# 1. Deploy services infrastructure
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production \
  --ask-become-pass

# 2. Verify containers
docker ps --filter "name=naaccord-"
# Expected: naaccord-wireguard-services, naaccord-services, naaccord-celery, naaccord-celery-beat, naaccord-redis

# 3. Check health
docker ps --filter "name=naaccord-" --format "{{.Names}}\t{{.Status}}"

# 4. Test WireGuard
docker exec naaccord-wireguard-services wg show
ping 10.100.0.11  # Should work from services server

# 5. Test database connectivity
docker exec naaccord-services python manage.py dbshell
```

### Database Setup
```bash
# On services server:

# 1. Run migrations
docker exec naaccord-services python manage.py migrate
docker exec naaccord-services python manage.py migrate django_celery_beat

# 2. Seed initial data (uses cohorts.production.csv automatically)
docker exec naaccord-services python manage.py seed_init

# 3. Setup permission groups
docker exec naaccord-services python manage.py setup_permission_groups

# 4. Create initial superuser via Django shell
docker exec -it naaccord-services python manage.py shell
# In shell:
from depot.models import User
User.objects.create_superuser('admin@jhu.edu', email='admin@jhu.edu')
# Exit shell
```

### Web Server Deployment
```bash
# On mrpznaaccordweb01 (web server):

# 1. Deploy web infrastructure
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_production \
  --ask-become-pass

# 2. Verify containers
docker ps --filter "name=naaccord-"
# Expected: naaccord-wireguard-web, naaccord-web, naaccord-nginx

# 3. Test WireGuard tunnel
docker exec naaccord-wireguard-web wg show
ping 10.100.0.11  # Should reach services server through tunnel

# 4. Test database connectivity through tunnel
docker exec naaccord-web python manage.py dbshell
```

### Connectivity Testing
```bash
# From web server, test each service through WireGuard:

# Test MariaDB (port 3306)
nc -zv 10.100.0.11 3306

# Test Redis (port 6379)
nc -zv 10.100.0.11 6379

# Test Django services API (port 8001)
nc -zv 10.100.0.11 8001
```

### Application Testing
- [ ] Access https://naaccord-production.jhu.edu (or actual domain)
- [ ] SAML login redirects to login.jh.edu
- [ ] Login with test JHU account succeeds
- [ ] User sees correct cohort in sidebar
- [ ] Static assets (CSS/JS) load correctly
- [ ] Upload test file (non-PHI)
- [ ] Verify file appears in NAS: `ls -lah /na_accord_nas/submissions/`
- [ ] Check Grafana at /mon/
- [ ] Verify logs in Loki

### Backup Verification
```bash
# On services server:

# Trigger test backup
docker exec naaccord-services python manage.py backup_database

# Verify backup exists on NAS
ls -lah /na_accord_nas/backups/
```

## Post-Deployment

### Monitoring Setup
- [ ] Verify Grafana dashboards loading
- [ ] Test Slack alert webhook with test message
- [ ] Verify log aggregation in Loki
- [ ] Set up uptime monitoring (external)

### Documentation
- [ ] Update runbook with any deployment deviations
- [ ] Document production-specific configurations discovered
- [ ] Share production access details with operations team
- [ ] Schedule backup verification (next day)

### Training
- [ ] Walkthrough with operations team
- [ ] Demonstrate emergency procedures
- [ ] Review monitoring dashboards
- [ ] Explain rollback procedure

### Handoff
- [ ] Provide support contacts to operations
- [ ] Schedule follow-up meeting (1 week)
- [ ] Document any known issues
- [ ] Transition to normal support procedures

## Emergency Rollback

If critical issues occur:

```bash
# 1. Stop all containers
docker compose -f docker-compose.prod.yml down

# 2. Restore database from latest backup
# (Follow database restore procedure)

# 3. Revert code to last known good version
cd /opt/naaccord/depot
git checkout <last-good-tag>

# 4. Redeploy
./deploy/scripts/2-deploy.sh production

# 5. Notify stakeholders
```

## Success Criteria

Deployment is successful when:
- [ ] Both servers running all expected containers (healthy status)
- [ ] WireGuard tunnel established and stable
- [ ] SAML login works with JHU accounts
- [ ] File uploads succeed and appear in NAS
- [ ] Database queries work through tunnel
- [ ] Static assets serve correctly
- [ ] Grafana monitoring operational
- [ ] Slack alerts working
- [ ] Backups running on schedule
- [ ] No errors in container logs
- [ ] Operations team signed off on handoff

---

**Document Version:** 1.0
**Last Updated:** 2025-10-06
**Next Review:** Before production deployment
