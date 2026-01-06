# Monitoring and Backup Strategy

## Overview

This document outlines the monitoring and backup architecture for NA-ACCORD, including placement decisions, security considerations, and implementation approach.

## Monitoring Tools Placement

### Grafana - Web Server ✅

**Location:** Web server (10.150.96.6 / mrpznaaccordweb01)

**Why web server:**
- ✅ No PHI access - reads metrics/logs only, no patient data
- ✅ Web-facing makes sense - ops team needs access without VPN
- ✅ Authentication built-in - Grafana has own login system
- ✅ Read-only by nature - can't modify data, only visualize

**What Grafana monitors:**
- Prometheus metrics (container stats, Django metrics)
- Loki logs (application logs from both servers)
- Health check endpoints
- System performance metrics
- Celery queue depths (via metrics, not Flower)

**Security configuration:**
```yaml
grafana:
  environment:
    - GF_SERVER_ROOT_URL=https://na-accord-depot.publichealth.jhu.edu/mon
    - GF_SERVER_SERVE_FROM_SUB_PATH=true
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}  # From vault
    - GF_AUTH_ANONYMOUS_ENABLED=false
    - GF_USERS_ALLOW_SIGN_UP=false
  volumes:
    - grafana-data:/var/lib/grafana  # SQLite database
```

**Nginx configuration:**
```nginx
location /mon/ {
    proxy_pass http://grafana:3000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

**Storage:** SQLite database (default, recommended)
- Zero configuration required
- Handles small/medium deployments easily (<100 users)
- Stores dashboards, users, settings, alerts
- Does NOT store time-series data (comes from Prometheus/Loki)
- Backed up via Docker volume

### Flower - Services Server ✅

**Location:** Services server (10.150.96.37 / mrpznaaccorddb01)

**Why services server (NOT web):**
- ⚠️ Task arguments may contain file paths with cohort IDs
- ⚠️ Task history exposes business logic
- ⚠️ Worker stats may reveal PHI processing patterns
- ✅ Safer to keep internal-only, access via SSH tunnel

**Access method:** SSH tunnel only (no web exposure)
```bash
# From developer machine
ssh -L 5555:localhost:5555 mrpznaaccorddb01.hosts.jhmi.edu
# Browse to http://localhost:5555
```

**Why SSH tunnel over web exposure:**
- ✅ No web exposure risk
- ✅ Requires SSH/MFA to access
- ✅ Can't be accidentally exposed via misconfiguration
- ✅ Complete audit trail via SSH logs
- ✅ No additional authentication layer needed

**Alternative:** Use Grafana dashboards for Celery monitoring instead
- Shows queue depths, worker status, task completion rates
- Doesn't expose task arguments or detailed task history
- Much safer than Flower for web exposure
- Sufficient for most operational monitoring needs

## Backup Strategy

### Philosophy: Cron vs Web App

**Decision: Use cron for scheduled backups**

**Why cron wins for backups:**
1. ✅ **Decoupled from app health** - Backups run even if Django crashes
2. ✅ **System-level reliability** - OS scheduling more reliable than app-level
3. ✅ **Simpler dependency chain** - Just needs Docker + SSH, no database/Django
4. ✅ **Separation of concerns** - Backup infrastructure separate from application
5. ✅ **Survives app updates** - Backups continue during deployment

**When to use web app for backups:**
- Manual pre-deployment backups (on-demand)
- Backup status dashboard (nice to have)
- Emergency backup triggers (rare)

**Summary:** Cron for scheduled reliability, web app for manual operations.

### Grafana Backup Architecture

**Challenge:** Grafana runs on web server, but NAS is mounted on services server.

**Solution:** Services server pulls backup via SSH over WireGuard tunnel.

```
Services Server (cron job)
    ↓ SSH (10.100.0.10)
Web Server (stream Docker volume)
    ↓ WireGuard tunnel
Services Server (save to NAS)
    ↓
/na_accord_nas/backups/grafana/grafana-YYYYMMDD-HHMMSS.tar.gz
```

**Implementation:**

```bash
#!/bin/bash
# /opt/naaccord/depot/deploy/scripts/backup-grafana.sh
# Runs on services server via cron

set -e

BACKUP_DIR="/na_accord_nas/backups/grafana"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/grafana-${TIMESTAMP}.tar.gz"
TEMP_FILE="/tmp/grafana-backup-${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "$(date): Starting Grafana backup from web server..."

# SSH to web server, create tar stream, save locally
ssh -i ~/.ssh/id_ed25519_backup -o StrictHostKeyChecking=no naaccord@10.100.0.10 \
  "docker run --rm -v naaccord_grafana-data:/data alpine tar cz /data" \
  > "${TEMP_FILE}"

# Verify backup is not empty
if [ ! -s "${TEMP_FILE}" ]; then
    echo "$(date): ERROR - Backup file is empty"
    rm -f "${TEMP_FILE}"
    exit 1
fi

# Move to NAS
mv "${TEMP_FILE}" "${BACKUP_FILE}"

echo "$(date): Grafana backup successful: ${BACKUP_FILE}"
echo "$(date): Size: $(du -h ${BACKUP_FILE} | cut -f1)"

# Cleanup old backups (keep last 30 days)
find "${BACKUP_DIR}" -name "grafana-*.tar.gz" -mtime +30 -delete

echo "$(date): Cleanup complete"
```

**Cron schedule:**
```bash
# /etc/cron.d/naaccord-backups
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Grafana backup at 2 AM daily
0 2 * * * naaccord /opt/naaccord/depot/deploy/scripts/backup-grafana.sh >> /var/log/naaccord/backup-grafana.log 2>&1

# Database backup at 2:30 AM daily (offset to avoid contention)
30 2 * * * naaccord /opt/naaccord/depot/deploy/scripts/backup-database.sh >> /var/log/naaccord/backup-database.log 2>&1
```

**SSH key setup (passwordless for cron):**
```bash
# On services server (as naaccord user)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_backup -N ""

# Copy public key to web server
ssh-copy-id -i ~/.ssh/id_ed25519_backup naaccord@10.100.0.10

# Test
ssh -i ~/.ssh/id_ed25519_backup naaccord@10.100.0.10 "echo 'SSH works'"
```

### Database Backup Architecture

**Location:** Services server (MariaDB runs here)

**Destination:** NAS mount at `/na_accord_nas/backups/database/`

**Implementation:**
```bash
#!/bin/bash
# /opt/naaccord/depot/deploy/scripts/backup-database.sh
# Runs on services server via cron

set -e

BACKUP_DIR="/na_accord_nas/backups/database"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/naaccord-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "$(date): Starting database backup..."

# Backup using mariabackup or mysqldump
mysqldump -u root -p"${DB_ROOT_PASSWORD}" \
  --single-transaction \
  --routines \
  --triggers \
  --events \
  naaccord | gzip > "${BACKUP_FILE}"

# Verify backup
if [ $? -eq 0 ] && [ -s "${BACKUP_FILE}" ]; then
    echo "$(date): Database backup successful: ${BACKUP_FILE}"
    echo "$(date): Size: $(du -h ${BACKUP_FILE} | cut -f1)"

    # Cleanup old backups (keep last 30 days)
    find "${BACKUP_DIR}" -name "naaccord-*.sql.gz" -mtime +30 -delete
else
    echo "$(date): Database backup FAILED"
    rm -f "${BACKUP_FILE}"
    exit 1
fi
```

### Backup Monitoring

**Option 1: Simple log checking**
```bash
# On services server
tail -f /var/log/naaccord/backup-grafana.log
tail -f /var/log/naaccord/backup-database.log
```

**Option 2: Grafana alert on missing backups**
```bash
# Backup script writes status
echo "last_backup_time=$(date +%s)" > /var/lib/naaccord/grafana_backup_status

# Prometheus node_exporter reads it
# Grafana alerts if last_backup_time > 25 hours ago
```

**Option 3: External health check service (healthchecks.io)**
```bash
# At end of successful backup
curl -m 10 --retry 5 https://hc-ping.com/your-uuid-here
```

## Backup Retention Policy

| Backup Type | Frequency | Retention | Location |
|-------------|-----------|-----------|----------|
| Grafana | Daily 2:00 AM | 30 days | `/na_accord_nas/backups/grafana/` |
| Database | Daily 2:30 AM | 30 days | `/na_accord_nas/backups/database/` |
| Application files | On deployment | Keep 3 most recent | `/na_accord_nas/backups/app/` |
| PHI files | N/A (permanent on NAS) | Per protocol | `/na_accord_nas/submissions/` |

**NAS capacity:** 100GB total
- Estimate: ~500MB/day for all backups
- 30 days retention = ~15GB
- Leaves ~85GB for PHI file storage

## Restore Procedures

### Restore Grafana

```bash
# On web server
docker stop naaccord-grafana
docker run --rm \
  -v naaccord_grafana-data:/data \
  -v /na_accord_nas/backups/grafana:/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/grafana-YYYYMMDD-HHMMSS.tar.gz -C /"
docker start naaccord-grafana
```

### Restore Database

```bash
# On services server
systemctl stop mariadb
# Restore from backup
gunzip < /na_accord_nas/backups/database/naaccord-YYYYMMDD-HHMMSS.sql.gz | \
  mysql -u root -p"${DB_ROOT_PASSWORD}" naaccord
systemctl start mariadb
```

## Monitoring Dashboard Recommendations

### Grafana Dashboards to Create

1. **System Overview**
   - CPU, memory, disk usage for both servers
   - Docker container status
   - Network throughput (WireGuard tunnel)

2. **Application Health**
   - Django response times
   - HTTP status codes
   - Active user sessions
   - SAML auth success rate

3. **Celery Monitoring** (via metrics, not Flower)
   - Queue depths by queue name
   - Task completion rates
   - Worker health status
   - Failed task counts

4. **Database Performance**
   - Query execution times
   - Connection pool usage
   - Slow query log
   - Replication lag (if applicable)

5. **PHI Audit Trail**
   - File upload counts by cohort
   - PHI file lifecycle (created → processed → cleaned up)
   - Cleanup overdue alerts
   - Storage usage by cohort

6. **Backup Status**
   - Last successful backup timestamp
   - Backup file sizes
   - Failed backup alerts
   - NAS available space

## Security Considerations

### Grafana Security

- ✅ Strong admin password in vault
- ✅ No anonymous access
- ✅ No self-registration
- ✅ HTTPS only (via Nginx)
- ✅ Optional: Additional Nginx basic auth layer
- ✅ Optional: SAML integration for JHU accounts
- ⚠️ Dashboards show only non-PHI data

### Flower Security

- ✅ No web exposure (SSH tunnel only)
- ✅ Requires SSH + MFA
- ✅ Audit trail via SSH logs
- ✅ Can't be misconfigured to be web-accessible

### Backup Security

- ✅ SSH key authentication (no passwords in cron)
- ✅ Backups encrypted in transit (SSH/WireGuard)
- ✅ NAS storage encrypted at rest
- ✅ Restrictive file permissions (600 for keys, 640 for backups)
- ✅ Backup logs written to secure location

## Implementation Phases

### Phase 1: Grafana Setup (High Priority)
- [ ] Deploy Grafana container on web server
- [ ] Configure Nginx reverse proxy at /mon/
- [ ] Set up Prometheus data source
- [ ] Set up Loki data source
- [ ] Create initial dashboards (system overview, app health)
- [ ] Configure Grafana admin password from vault
- [ ] Test access and authentication

### Phase 2: Backup Implementation (High Priority)
- [ ] Create backup scripts (Grafana, database)
- [ ] Set up SSH keys for passwordless access
- [ ] Configure cron jobs on services server
- [ ] Test backup execution
- [ ] Test restore procedures
- [ ] Configure log rotation for backup logs
- [ ] Set up backup monitoring alerts

### Phase 3: Advanced Monitoring (Medium Priority)
- [ ] Create Celery monitoring dashboard
- [ ] Create PHI audit trail dashboard
- [ ] Create backup status dashboard
- [ ] Set up Slack alerts for critical issues
- [ ] Configure alert thresholds
- [ ] Document dashboard usage for ops team

### Phase 4: Flower Setup (Low Priority)
- [ ] Deploy Flower on services server
- [ ] Configure for localhost-only access
- [ ] Document SSH tunnel access procedure
- [ ] Optional: Evaluate if Grafana dashboards make Flower unnecessary

## Related Documentation

- [Production Differences](production-differences.md) - Monitoring section
- [Database Access](database-access.md) - Database backup procedures
- [Emergency Access](../docs/deployment/guides/emergency-access.md) - Emergency procedures
- [Architecture](../docs/deployment/guides/architecture.md) - System architecture

---

**Document Version:** 1.0
**Last Updated:** 2025-10-10
**Owner:** Development Team
**Status:** Planning - To be implemented after initial deployment
