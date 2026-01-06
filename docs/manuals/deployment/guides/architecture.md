# NA-ACCORD Deployment Architecture

**PHI-Compliant Two-Server Design with Ansible Automation**

## Architecture Overview

```
Web Server                          Services Server
┌────────────────────────┐         ┌────────────────────────┐
│ Port 443 (HTTPS)       │         │ Port 22 (SSH)          │
│ Port 22 (SSH)          │         │ Port 51820 (WireGuard) │
│                        │         │                        │
│ Nginx                  │         │                        │
│ ├─ App @ /            │         │ WireGuard Server       │
│ └─ Grafana @ /mon     │         │ (10.100.0.11)          │
│                        │         │                        │
│ Django Web Container   │         │ MariaDB (encrypted)    │
│ (SERVER_ROLE=web)      │         │ └─ Daily backups→NAS   │
│                        │         │                        │
│ Grafana Container      │         │ Redis Container        │
│ └─ Loki data source ───┼─Tunnel──┤ └─ Encrypted volume    │
│    (via WireGuard)     │         │    └─ RDB snapshots    │
│                        │         │                        │
│ WireGuard Client ──────┼─Tunnel──┤ Django Services        │
│ (10.100.0.10)          │         │ (SERVER_ROLE=services) │
│                        │         │                        │
│ SAML Auth              │         │ Celery Workers         │
│ ├─ Staging: mock-idp   │         │ └─ Autoscale 2-8       │
│ └─ Prod: JHU Shibboleth│         │                        │
└────────────────────────┘         │ Flower Monitoring      │
                                   │ (localhost:5555)       │
                                   │                        │
                                   │ Loki Log Aggregation   │
                                   │                        │
                                   │ NAS Mount (/mnt/nas)   │
                                   │ ├─ Submissions         │
                                   │ └─ DB Backups (TODO)   │
                                   └────────────────────────┘
```

## Security Model

### PHI Isolation

**Web Server:**
- **No PHI storage** - All PHI operations streamed to services server
- Only serves application UI and routes requests
- SAML-only authentication (no password login)

**Services Server:**
- **All PHI processing** - Database, file storage, processing
- Encrypted database at rest (MariaDB with encryption keys)
- Encrypted Redis volume for session persistence
- Complete audit trail via PHIFileTracking system

### Network Security

**WireGuard Encrypted Tunnel:**
- ChaCha20-Poly1305 encryption
- Private network: 10.100.0.0/24
- Web server: 10.100.0.10
- Services server: 10.100.0.11
- All PHI traffic routed through tunnel

**Firewall Rules:**
- Web server: Ports 22 (SSH), 443 (HTTPS) only
- Services server: Ports 22 (SSH), 51820 (WireGuard UDP) only
- All other ports blocked

### Data Encryption

**At Rest:**
- MariaDB: Full encryption with file-key-management plugin
- Redis: Encrypted Docker volume
- Backups: Encrypted on NAS (TODO: implement)

**In Transit:**
- HTTPS: Let's Encrypt SSL/TLS
- WireGuard: ChaCha20-Poly1305 tunnel encryption
- Internal API: Authenticated with INTERNAL_API_KEY

## Component Details

### Web Server Components

**Nginx (Port 443)**
- Reverse proxy for Django web app
- Proxies /mon to Grafana
- SSL/TLS termination
- SAML endpoint routing

**Django Web Container**
- `SERVER_ROLE=web`
- Handles user interface
- Streams all PHI operations to services server
- SAML authentication only

**Grafana Container**
- Accessible at /mon
- Data sources:
  - Loki (via WireGuard tunnel)
  - System metrics from services server
- Dashboards: logs, Celery queues, system health
- Slack alerting configured

**WireGuard Client**
- Connects to services server tunnel
- Routes traffic to 10.100.0.11

### Services Server Components

**MariaDB**
- Bare metal install (not containerized)
- Encryption at rest enabled
- Listens on localhost only
- Accessed by Django containers

**Redis Container**
- Docker with encrypted volume
- RDB snapshots every 60 seconds
- Used by Celery and Django cache
- Persists through container restarts

**Django Services Container**
- `SERVER_ROLE=services`
- Handles all PHI processing
- Database access
- File operations on NAS

**Celery Worker Containers**
- 1 worker per CPU core initially
- Autoscale 2-8 based on load
- Processes background tasks (DuckDB conversion, R audits)

**Flower Monitoring**
- Localhost:5555 (access via SSH tunnel)
- Real-time Celery monitoring
- Queue depth visibility

**Loki Container**
- Log aggregation from both servers
- 30-day retention
- Accessed by Grafana on web server

**WireGuard Server**
- Listens on UDP port 51820
- Accepts connection from web server

**NAS Mount**
- SMB/NFS mount at /mnt/nas
- Stores submissions, reports
- Future: database backups

## Ansible Automation

### Role-Based Deployment

All infrastructure managed through Ansible roles:

**Core Roles:**
- `base` - Common utilities, Docker, firewall base
- `firewall` - Port restrictions per server
- `hosts_management` - /etc/hosts from inventory
- `nas_mount` - NAS configuration

**Services Server Roles:**
- `mariadb` - Database with encryption
- `redis` - Containerized cache
- `wireguard_server` - Tunnel server
- `services_app` - Django services container
- `services_celery` - Worker containers
- `services_flower` - Monitoring
- `loki` - Log aggregation

**Web Server Roles:**
- `wireguard_client` - Tunnel client
- `ssl_letsencrypt` - DNS-01 SSL certificates
- `web_app` - Django web container + Nginx
- `grafana` - Observability dashboard

**Operational Roles:**
- `deploy` - Application updates (pull, migrate, restart, health check)
- `monitoring` - Grafana alerts and Slack integration

### Deployment Strategy

**Localhost Execution:**
- Ansible runs on each server via SSH
- Required due to RADIUS 2FA on JHU infrastructure
- Playbooks designed for `--connection local`

**Idempotent Design:**
- All roles can be safely re-run
- Configuration changes applied incrementally
- No destructive operations without explicit flags

## Data Flow

### User Upload Workflow

1. User uploads file via web interface (HTTPS)
2. Web server streams file to services server (via WireGuard)
3. Services server stores in NAS and tracks in PHIFileTracking
4. Celery task converts to DuckDB
5. R audit generates report
6. Report stored on NAS
7. User accesses report via time-limited URL

### Authentication Flow

1. User accesses web server
2. Immediately redirected to SAML IdP
   - Staging: mock-idp container
   - Production: JHU Shibboleth
3. After SAML auth, session stored in database
4. All subsequent requests authenticated via session

### Monitoring Data Flow

1. Services server components log to journald
2. Logs shipped to Loki container
3. Grafana on web server queries Loki (via WireGuard)
4. Dashboards display logs and metrics
5. Alerts sent to Slack on critical events

## Environments

### Staging (Local VMs)

- **Web**: 192.168.50.10 (web.naaccord.lan)
- **Services**: 192.168.50.11 (services.naaccord.lan)
- **Public URL**: naaccord.pequod.sh (via Cloudflare)
- **NAS**: smb://192.168.1.10
- **SAML**: Mock-idp container

### Production (JHU Servers)

- **Web**: 10.150.96.6 (mrpznaaccordweb01.hosts.jhmi.edu)
- **Services**: 10.150.96.37
- **Access**: VPN required
- **NAS**: TBD (JHU IT to provide)
- **SAML**: JHU Shibboleth

## Health Checks

**Web Server:**
```bash
# HTTPS endpoint
curl https://web.naaccord.lan/health/

# Grafana
curl https://web.naaccord.lan/mon/

# WireGuard tunnel
ping 10.100.0.11
```

**Services Server:**
```bash
# Django API
curl http://localhost:8001/health/

# MariaDB
mysql -u root -p -e "SELECT 1;"

# Redis
docker exec redis redis-cli ping

# Celery
docker exec celery celery -A depot inspect active

# NAS mount
ls -la /mnt/nas/
```

## Scalability Considerations

**Current Design (Small Team):**
- Single web server
- Single services server
- Manual deployment via Ansible
- Basic monitoring with Grafana + Slack

**Future Growth (If Needed):**
- Multiple web servers behind load balancer
- Database replication for read scaling
- Celery worker scaling (more containers or servers)
- Full PagerDuty integration for 24/7
- Automated deployment pipeline

## Related Documentation

- [Deployment Workflow](deployment-workflow.md) - How to deploy
- [Ansible Roles](ansible-roles.md) - Role reference
- [Environment Details](../reference/environments.md) - Server specs
- [Emergency Access](emergency-access.md) - IT procedures
