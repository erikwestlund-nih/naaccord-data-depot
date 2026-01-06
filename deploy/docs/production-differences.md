# Production vs Staging Differences

This document outlines all the differences between staging and production deployments to ensure smooth production deployment.

## Critical Differences

### 1. SAML Authentication

**Staging:**
- Mock IDP container (`naaccord-mock-idp`)
- Entity ID: `https://naaccord.pequod.sh`
- Metadata URL: `http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php`
- No real JHU accounts required

**Production:**
- JHU Shibboleth IDP (login.jh.edu)
- Entity ID: `https://login.jh.edu/idp/shibboleth`
- Metadata: File-based (deploy/idp_metadata_production.xml)
- Real JHU JHED accounts required
- Contact: enterpriseauth@jh.edu

**Production Configuration Required:**
```yaml
# In production inventory group_vars/all/main.yml
saml_entity_id: "https://naaccord-production.jhu.edu"  # UPDATE WITH ACTUAL DOMAIN
saml_acs_url: "https://naaccord-production.jhu.edu/saml2/acs/"
saml_sls_url: "https://naaccord-production.jhu.edu/saml2/sls/"
saml_idp_metadata_file: "/opt/naaccord/depot/deploy/idp_metadata_production.xml"
```

**Action Items:**
- [ ] Get production domain from JHU IT
- [ ] Register NA-ACCORD as SP with JHU Enterprise Auth team
- [ ] Populate actual X509 certificates in idp_metadata_production.xml
- [ ] Test SAML login with JHU accounts before production cutover

### 2. NAS Storage

**Staging:**
- SMB: `//192.168.50.1/submissions`
- Mount: `/mnt/nas`
- Local network, no authentication complexity

**Production:**
- SMB: `//cloud.nas.jh.edu/na-accord$`
- Mount: `/na_accord_nas` ⚠️ **DIFFERENT PATH**
- Domain: `win.ad.jhu.edu`
- Size: 100GB total
- Authentication: JHU credentials via Kerberos/CIFS

**Configuration Changes Needed:**
```yaml
# In production inventory
nas_mount_point: "/na_accord_nas"  # NOT /mnt/nas
nas_host: "cloud.nas.jh.edu"
nas_share: "na-accord$"

# In production vault (encrypted)
vault_nas_domain: "win.ad.jhu.edu"
vault_nas_username: "naaccord"
vault_nas_password: "[from JHU IT]"
```

**Action Items:**
- [ ] Update NAS mount path in production inventory
- [ ] Verify CIFS credentials in vault
- [ ] Test NAS mount before deployment
- [ ] Configure automatic mount on boot
- [ ] Document backup/retention policies with JHU IT

### 3. Data Seeding (Cohorts vs Users)

**Cohorts (SAME in all environments):**
- Both staging and production use `cohorts.csv`
- All 31 NA-ACCORD cohorts loaded in both environments
- Cohorts are organizational entities, not user-specific

**Users (DIFFERENT in each environment):**
- **Development/Staging:** Same test users from `load_test_users` command (mock accounts)
- **Production:** Real JHU accounts via SAML (no test users)
- Production user provisioning through JHU Enterprise Auth and Active Directory

**Action Items:**
- [ ] Verify all 31 cohorts are correct in `resources/data/seed/cohorts.csv`
- [ ] Create production user seeding strategy (likely manual via SAML)
- [ ] Document user-to-cohort assignment process for production
- [ ] Coordinate with NA-ACCORD team on user access requirements

### 4. SSL Certificates

**Staging:**
- Domain: naaccord.pequod.sh (personal domain)
- Certificate: Let's Encrypt via Cloudflare DNS-01
- Wildcard: *.pequod.sh

**Production:**
- Domain: na-accord-depot.publichealth.jhu.edu ✅
- Certificate: JHU IT-provided (deployed from Ansible vault)
- Paths:
  - Certificate: `/etc/ssl/certs/naaccord/naaccord.crt`
  - Private key: `/etc/ssl/private/naaccord/naaccord.key`
  - CA Bundle: `/etc/ssl/certs/naaccord/ca-bundle.crt`

**Action Items:**
- [x] Determine production domain name (na-accord-depot.publichealth.jhu.edu)
- [ ] Coordinate SSL certificate provisioning with JHU IT
- [ ] Install certificates on web server
- [ ] Test certificate renewal process
- [ ] Document who manages DNS records (likely JHU IT)

### 5. Network Configuration

**Staging:**
- Web: 192.168.50.10 (local VM)
- Services: 192.168.50.11 (local VM)
- WireGuard: Local tunnel only
- No firewall restrictions

**Production:**
- Web: 10.150.96.6 (mrpznaaccordweb01.hosts.jhmi.edu)
- Services: 10.150.96.37 (mrpznaaccorddb01 - likely this host)
- WireGuard: Between production servers
- JHU firewall rules required

**Action Items:**
- [ ] Confirm WireGuard port 51820 is allowed between servers
- [ ] Verify no firewall blocks on internal docker networks
- [ ] Test WireGuard tunnel connectivity
- [ ] Document any port forwarding requirements

### 6. User Accounts

**Staging:**
- Test users from `load_test_users` command
- Mock SAML accounts (any email works)

**Production:**
- Real JHU JHED accounts only
- Must be in appropriate Active Directory groups
- User provisioning through JHU Enterprise Auth

**Action Items:**
- [ ] Create `users_production.csv` from template
- [ ] Map AD groups to Django permission groups
- [ ] Create initial superuser(s) for admin access
- [ ] Document user provisioning workflow

### 7. Monitoring & Logging

**Staging:**
- Grafana at /mon/ (optional)
- Container logs only
- No alerting

**Production:**
- Grafana required for ops monitoring
- Loki log aggregation required
- Slack alerts to operations channel
- PHI audit trail compliance

**Action Items:**
- [ ] Set up production Grafana workspace
- [ ] Configure Loki retention policies
- [ ] Create Slack webhook for alerts
- [ ] Document alert escalation procedures
- [ ] Set up PHI access audit reports

### 8. Database

**Staging:**
- MariaDB on bare metal (services server)
- Encryption at rest enabled
- Simple password auth
- Database users: root, naaccord_app, naaccord_admin

**Production:**
- MariaDB on bare metal (services server)
- Encryption at rest REQUIRED
- Key rotation policy needed
- Backup to NAS required
- Database users: root, naaccord_app, naaccord_admin

**Database User Access:**

| User | Purpose | Grants | Use Case |
|------|---------|--------|----------|
| `root` | Emergency/disaster recovery | ALL | Server crashes, corruption, true disasters |
| `naaccord_app` | Django application | ALL on naaccord.* | Normal operations (via Django) |
| `naaccord_admin` | Debugging/analysis | SELECT | TablePlus inspection, query analysis via SSH tunnel |

**Data Change Policy:**
- ✅ **Default:** Use Django shell for all data changes (`docker exec -it naaccord-services python manage.py shell`)
- ✅ **Rationale:** Django ORM provides validation, audit trails, signal handlers, and PHI tracking
- ⚠️ **Direct SQL:** Only for documented emergencies (corruption, disaster recovery)
- ℹ️ **PHI Note:** Most database data is NOT PHI (de-identified cohortPatientId only). PHI exists only in uploaded files, temporary processing files, and NAS storage.

**Action Items:**
- [ ] Verify encryption keys are properly secured
- [ ] Set up automated backups to NAS
- [ ] Test backup restoration procedure
- [ ] Document key rotation schedule
- [ ] Configure backup retention (likely 30 days)
- [ ] Document TablePlus SSH tunnel connection procedure for naaccord_admin user

### 9. Docker Registry

**Staging:**
- GHCR: ghcr.io/jhbiostatcenter/naaccord/*
- Public registry
- Latest/develop tags

**Production:**
- GHCR: ghcr.io/jhbiostatcenter/naaccord/*
- Same registry (good!)
- Use stable/versioned tags (not 'latest')

**Action Items:**
- [ ] Implement semantic versioning for container tags
- [ ] Document release process
- [ ] Create production branch in git
- [ ] Set up tag-based container builds

### 10. Environment Variables

**Staging:**
```bash
NAACCORD_ENVIRONMENT=staging
USE_MOCK_SAML=True
DEBUG=False
```

**Production:**
```bash
NAACCORD_ENVIRONMENT=production
USE_MOCK_SAML=False
DEBUG=False  # CRITICAL - never True in production
ALLOWED_HOSTS=na-accord-depot.publichealth.jhu.edu,mrpznaaccordweb01.hosts.jhmi.edu,10.150.96.6
```

## Deployment Readiness Checklist

### Pre-Deployment
- [ ] All action items above completed
- [ ] Production inventory fully configured
- [ ] Vault passwords created and distributed to team
- [ ] All secrets populated in vault.yml
- [ ] Production cohorts CSV populated
- [ ] SAML registered with JHU Enterprise Auth
- [ ] SSL certificates provisioned
- [ ] NAS mount tested and working
- [ ] WireGuard tunnel tested between servers
- [ ] Database encryption verified
- [ ] Backup/restore tested

### Deployment Day
- [ ] Run init-server.sh on both servers
- [ ] Verify /etc/naaccord/environment = production
- [ ] Verify /etc/naaccord/server-role is correct
- [ ] Run services-server.yml playbook
- [ ] Verify all services containers healthy
- [ ] Run web-server.yml playbook
- [ ] Verify all web containers healthy
- [ ] Test WireGuard connectivity
- [ ] Test database connectivity from web server
- [ ] Run database migrations
- [ ] Seed production data (cohorts, users)
- [ ] Test SAML login with JHU account
- [ ] Verify static files serving
- [ ] Test file upload workflow
- [ ] Verify Grafana monitoring
- [ ] Test backup process

### Post-Deployment
- [ ] Document any deviations from plan
- [ ] Update runbook with production specifics
- [ ] Schedule first backup verification
- [ ] Set up monitoring alerts
- [ ] Train operations team
- [ ] Hand off to IT support team

## Known Risks & Mitigations

### Risk: SAML Integration Failure
**Mitigation:** Emergency Django shell access via SSH allows manual user creation if SAML fails

### Risk: NAS Mount Issues
**Mitigation:** Docker volumes can temporarily store data if NAS unavailable; migrate when restored

### Risk: WireGuard Tunnel Down
**Mitigation:** Application detects connection failure; monitoring alerts ops team immediately

### Risk: Certificate Expiration
**Mitigation:** Automated renewal with Let's Encrypt; monitoring checks cert expiration 30 days out

### Risk: Database Corruption
**Mitigation:** Automated backups every 6 hours to NAS; tested restore procedure

## Rollback Plan

If production deployment fails:

1. **Stop all containers:**
   ```bash
   docker compose -f docker-compose.prod.yml down
   ```

2. **Restore database from backup:**
   ```bash
   # Documented in emergency procedures
   ```

3. **Revert code to last known good commit:**
   ```bash
   cd /opt/naaccord/depot
   git checkout <last-good-tag>
   ```

4. **Restart services:**
   ```bash
   ./deploy/scripts/2-deploy.sh production
   ```

5. **Notify stakeholders** of rollback and timeline for retry

## Production Support Contacts

- **JHU Enterprise Auth (SAML):** enterpriseauth@jh.edu
- **JHU IT (Infrastructure):** TBD
- **NA-ACCORD Team:** TBD
- **Emergency Contact:** TBD

## Next Steps

1. Review this document with operations team
2. Complete all action items
3. Schedule production deployment date
4. Conduct pre-deployment readiness review
5. Execute deployment plan
6. Conduct post-deployment review

---

**Document Version:** 1.0
**Last Updated:** 2025-10-06
**Owner:** Development Team
**Reviewers:** Operations Team, JHU IT
