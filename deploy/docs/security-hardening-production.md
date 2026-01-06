# NA-ACCORD Production Security Hardening Guide

**Document Version:** 1.0
**Date:** October 5, 2025
**Status:** Ready for Implementation
**Production Readiness Score:** 85/100

## Executive Summary

The NA-ACCORD infrastructure demonstrates **strong security fundamentals** with a well-architected PHI-compliant two-server design. The proposed improvements in this document are incremental hardening measures rather than critical vulnerability fixes. All recommendations can be implemented safely with minimal risk to production operations.

**Key Finding:** Current deployment is **production-ready** with recommended Phase 0 and Phase 1 improvements before launch.

---

## Table of Contents

1. [Priority Matrix](#priority-matrix)
2. [Secrets Management](#secrets-management)
3. [WireGuard Tunnel Hardening](#wireguard-tunnel-hardening)
4. [Container Hardening](#container-hardening)
5. [Logging Infrastructure](#logging-infrastructure)
6. [Documentation Consolidation](#documentation-consolidation)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Risk Assessment](#risk-assessment)

---

## Priority Matrix

### IMMEDIATE (Pre-Production - Week 1)

| Task | Effort | Risk | Impact |
|------|--------|------|--------|
| Move Redis password to Docker secret | 15 min | ZERO | HIGH |
| Configure Docker logging limits | 30 min | ZERO | HIGH |
| Setup logrotate for Nginx/Django | 1 hour | ZERO | CRITICAL |

### HIGH PRIORITY (Week 1-2)

| Task | Effort | Risk | Impact |
|------|--------|------|--------|
| Configure log archival to NAS | 2 hours | LOW | HIGH |
| Document secrets rotation procedures | 4 hours | ZERO | HIGH |
| Add read-only filesystem to containers | 1 hour | LOW | MEDIUM |

### MEDIUM PRIORITY (Week 2-3)

| Task | Effort | Risk | Impact |
|------|--------|------|--------|
| Restrict WireGuard AllowedIPs | 2 hours | LOW | MEDIUM |
| Add nftables rules in WireGuard | 3 hours | MEDIUM | MEDIUM |
| Drop unnecessary container capabilities | 2 hours | LOW | LOW |
| Consolidate deployment docs | 8 hours | ZERO | LOW |

### LOW PRIORITY (Week 3-4+)

| Task | Effort | Risk | Impact |
|------|--------|------|--------|
| Implement automated secrets rotation | 16 hours | HIGH | MEDIUM |
| Add AppArmor/SELinux profiles | 8 hours | MEDIUM | LOW |
| Setup WireGuard policy routing | 4 hours | LOW | LOW |

---

## Secrets Management

### Current State Assessment

**Status: ACCEPTABLE for Production**

The current Docker secrets implementation is production-ready with these findings:

- ✅ **GOOD:** Secrets stored in /var/lib/docker/secrets/ (tmpfs, not disk-persisted)
- ✅ **GOOD:** Mounted read-only into containers via Docker secrets
- ✅ **GOOD:** Not exposed in environment variables (with one exception)
- ❌ **FIX:** Redis password currently in .env file (not Docker secret)
- ❌ **ACCEPT:** No automated rotation (manual process acceptable for initial launch)
- ❌ **ACCEPT:** No expiry tracking (track externally for now)

### Secret Inventory

| Secret | Location | Rotation Frequency | Complexity | Risk Level |
|--------|----------|-------------------|------------|------------|
| `redis_password` | .env FILE | 90 days | LOW | MEDIUM |
| `internal_api_key` | Docker secret | 30 days | MEDIUM | HIGH |
| `django_secret_key` | Docker secret | 90 days | LOW | LOW |
| `db_password` | Docker secret | 180 days | HIGH | CRITICAL |
| `wg_web_private_key` | Docker secret | 365 days | HIGH | CRITICAL |
| `wg_services_private_key` | Docker secret | 365 days | HIGH | CRITICAL |
| `wg_preshared_key` | Docker secret | 365 days | MEDIUM | HIGH |

### CRITICAL FIX: Redis Password

**Issue:** Redis password currently stored in `.env` file, not Docker secret.

**Fix (15 minutes):**

```bash
# 1. Generate secure password
openssl rand -base64 32 > /var/lib/docker/secrets/redis_password
chmod 600 /var/lib/docker/secrets/redis_password

# 2. Update docker-compose.prod.yml
# Change redis service:
#   FROM:
#     command: --requirepass ${REDIS_PASSWORD}
#   TO:
#     environment:
#       - REDIS_PASSWORD_FILE=/run/secrets/redis_password
#     secrets:
#       - redis_password
#     command: --requirepass $(cat /run/secrets/redis_password)

# 3. Update all containers using Redis URL
#   FROM: redis://:${REDIS_PASSWORD}@redis:6379/0
#   TO: Read password from secret file in entrypoint script

# 4. Restart containers
docker compose -f docker-compose.prod.yml --profile services restart
```

### Recommended Rotation Schedule

```
Timeline:

  T+0 (Launch)
    |
    |-- Redis password: IMMEDIATE FIX (before launch)
    |
  T+30 days
    |
    |-- Internal API key rotation (first rotation)
    |
  T+90 days
    |
    |-- Django secret key rotation
    |-- Redis password rotation (first scheduled rotation)
    |
  T+180 days
    |
    |-- Database password rotation (major procedure)
    |
  T+365 days
    |
    |-- WireGuard keys rotation (highest risk)
```

### Rotation Procedures

#### 1. Redis Password Rotation (EASIEST - LOW RISK)

```bash
#!/bin/bash
# scripts/rotate-redis-password.sh

set -e

echo "Rotating Redis password..."

# Generate new password
NEW_PASSWORD=$(openssl rand -base64 32)
echo "$NEW_PASSWORD" > /var/lib/docker/secrets/redis_password.new

# Atomic swap
mv /var/lib/docker/secrets/redis_password.new \
   /var/lib/docker/secrets/redis_password

# Restart Redis (ephemeral cache, data loss OK)
docker restart naaccord-redis

# Restart dependent containers
docker restart naaccord-services \
               naaccord-celery \
               naaccord-celery-beat \
               naaccord-web

echo "Redis password rotated successfully"
echo "Downtime: ~15 seconds"
```

**Expected Impact:**
- Downtime: 10-20 seconds
- Data Loss: None (cache is ephemeral)
- User Impact: Brief connection delay
- Risk: LOW

#### 2. Internal API Key Rotation (MODERATE RISK)

**Requires code change to support dual-key transition:**

```python
# depot/middleware/internal_auth.py

def get_valid_api_keys():
    """Return list of valid API keys during rotation window"""
    keys = []

    # Current key (always present)
    current_key = read_secret_file('/run/secrets/internal_api_key')
    if current_key:
        keys.append(current_key)

    # Old key (only during rotation - remove after 24 hours)
    old_key = read_secret_file('/run/secrets/internal_api_key_old')
    if old_key:
        keys.append(old_key)

    return keys

class InternalAPIAuthMiddleware:
    def process_request(self, request):
        provided_key = request.headers.get('X-Internal-API-Key')

        if provided_key not in get_valid_api_keys():
            return HttpResponseForbidden('Invalid API key')
```

**Rotation procedure:**

```bash
#!/bin/bash
# scripts/rotate-internal-api-key.sh

set -e

echo "Step 1: Generate new API key"
NEW_KEY=$(openssl rand -base64 48)

echo "Step 2: Backup current key as 'old'"
cp /var/lib/docker/secrets/internal_api_key \
   /var/lib/docker/secrets/internal_api_key_old

echo "Step 3: Write new key"
echo "$NEW_KEY" > /var/lib/docker/secrets/internal_api_key

echo "Step 4: Restart services (they now accept BOTH keys)"
docker restart naaccord-services naaccord-web

echo "Step 5: Wait 5 minutes for connections to stabilize"
sleep 300

echo "Step 6: Remove old key (only new key accepted now)"
rm /var/lib/docker/secrets/internal_api_key_old
docker restart naaccord-services naaccord-web

echo "Rotation complete - zero downtime"
```

**Expected Impact:**
- Downtime: 0 seconds (dual-key transition)
- Transition Window: 5 minutes
- User Impact: None
- Risk: MEDIUM (requires code deployment)

#### 3. Django Secret Key Rotation (LOW RISK)

```bash
#!/bin/bash
# scripts/rotate-django-secret.sh

set -e

echo "Generating new Django secret key..."
NEW_SECRET=$(openssl rand -base64 64)

# Blue-green deployment
echo "Step 1: Write new secret"
echo "$NEW_SECRET" > /var/lib/docker/secrets/django_secret_key

echo "Step 2: Scale up to 2 web containers"
docker compose -f docker-compose.prod.yml --profile web up -d --scale web=2

echo "Step 3: Wait for health checks"
sleep 30

echo "Step 4: Scale back to 1 container (old container stops)"
docker compose -f docker-compose.prod.yml --profile web up -d --scale web=1

echo "Rotation complete"
echo "Note: Users will need to re-login (sessions invalidated)"
```

**Expected Impact:**
- Downtime: 0 seconds
- User Impact: Session invalidation (re-login required)
- Risk: LOW

#### 4. Database Password Rotation (HIGH RISK - COMPLEX)

**Zero-downtime rotation using temporary dual-user approach:**

```bash
#!/bin/bash
# scripts/rotate-db-password.sh

set -e

DB_HOST="db.naaccord.internal"
CURRENT_USER="naaccord"
NEW_USER="naaccord_temp"
ROOT_PASSWORD="<from-vault>"

echo "CRITICAL: This is a high-risk operation. Test in staging first."
read -p "Continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted"
    exit 1
fi

# Generate new password
NEW_PASSWORD=$(openssl rand -base64 32)

echo "Step 1: Create temporary database user"
mysql -h "$DB_HOST" -u root -p"$ROOT_PASSWORD" <<EOF
CREATE USER IF NOT EXISTS '$NEW_USER'@'%' IDENTIFIED BY '$NEW_PASSWORD';
GRANT ALL PRIVILEGES ON naaccord.* TO '$NEW_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Step 2: Update Docker secret"
echo "$NEW_PASSWORD" > /var/lib/docker/secrets/db_password

echo "Step 3: Update DATABASE_USER environment variable"
# Modify docker-compose.prod.yml or use override
cat > docker-compose.override.yml <<EOF
services:
  services:
    environment:
      - DATABASE_USER=$NEW_USER
  celery:
    environment:
      - DATABASE_USER=$NEW_USER
  celery-beat:
    environment:
      - DATABASE_USER=$NEW_USER
  web:
    environment:
      - DB_USER=$NEW_USER
EOF

echo "Step 4: Restart containers with new credentials"
docker compose -f docker-compose.prod.yml --profile services restart

echo "Step 5: Verify connectivity (waiting 30 seconds)"
sleep 30

echo "Step 6: Test database access"
docker exec naaccord-services python manage.py dbshell -c "SELECT 1;"

if [ $? -ne 0 ]; then
    echo "ERROR: Database connection failed. Rolling back..."
    # Rollback procedure here
    exit 1
fi

echo "Step 7: Drop old database user"
mysql -h "$DB_HOST" -u root -p"$ROOT_PASSWORD" <<EOF
DROP USER IF EXISTS '$CURRENT_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Step 8: Rename temporary user to permanent name"
mysql -h "$DB_HOST" -u root -p"$ROOT_PASSWORD" <<EOF
RENAME USER '$NEW_USER'@'%' TO '$CURRENT_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Step 9: Update environment to use original username"
rm docker-compose.override.yml
docker compose -f docker-compose.prod.yml --profile services restart

echo "Database password rotation complete - zero downtime"
```

**Expected Impact:**
- Downtime: 0 seconds (if successful)
- User Impact: None
- Risk: HIGH (database connectivity critical)
- **MUST test thoroughly in staging first**

#### 5. WireGuard Keys Rotation (HIGHEST RISK)

**Requires coordinated action on BOTH servers simultaneously:**

```bash
#!/bin/bash
# scripts/rotate-wireguard-keys.sh

set -e

WEB_SERVER="10.150.96.6"
SERVICES_SERVER="10.150.96.37"

echo "WARNING: This will cause 30-60 second tunnel outage"
read -p "Schedule maintenance window? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    exit 1
fi

echo "Step 1: Generate new keypairs on both servers"

# On web server
ssh root@$WEB_SERVER 'wg genkey | tee /var/lib/docker/secrets/wg_web_private_key | wg pubkey > /var/lib/docker/secrets/wg_web_public_key'

# On services server
ssh root@$SERVICES_SERVER 'wg genkey | tee /var/lib/docker/secrets/wg_services_private_key | wg pubkey > /var/lib/docker/secrets/wg_services_public_key'

# Generate new preshared key (on one server, copy to both)
ssh root@$SERVICES_SERVER 'wg genpsk > /var/lib/docker/secrets/wg_preshared_key'
scp root@$SERVICES_SERVER:/var/lib/docker/secrets/wg_preshared_key /tmp/
scp /tmp/wg_preshared_key root@$WEB_SERVER:/var/lib/docker/secrets/

echo "Step 2: Exchange public keys"
WEB_PUBKEY=$(ssh root@$WEB_SERVER 'cat /var/lib/docker/secrets/wg_web_public_key')
SERVICES_PUBKEY=$(ssh root@$SERVICES_SERVER 'cat /var/lib/docker/secrets/wg_services_public_key')

ssh root@$WEB_SERVER "echo '$SERVICES_PUBKEY' > /var/lib/docker/secrets/wg_services_public_key"
ssh root@$SERVICES_SERVER "echo '$WEB_PUBKEY' > /var/lib/docker/secrets/wg_web_public_key"

echo "Step 3: Restart WireGuard containers SIMULTANEOUSLY"
ssh root@$WEB_SERVER "docker restart naaccord-wireguard-web" &
ssh root@$SERVICES_SERVER "docker restart naaccord-wireguard-services" &
wait

echo "Step 4: Verify tunnel connectivity"
sleep 10
ssh root@$WEB_SERVER "docker exec naaccord-wireguard-web ping -c 3 10.100.0.11"

if [ $? -eq 0 ]; then
    echo "SUCCESS: Tunnel established with new keys"
else
    echo "ERROR: Tunnel not working - manual intervention required"
    exit 1
fi

echo "WireGuard keys rotated successfully"
echo "Downtime: ~30-60 seconds"
```

**Expected Impact:**
- Downtime: 30-60 seconds
- User Impact: Brief "server unavailable" errors
- PHI Access: Interrupted during rotation
- Risk: HIGH
- **MUST schedule maintenance window**

### Secrets Vault Evaluation

**Question:** Should we use HashiCorp Vault instead of Docker Secrets?

**Analysis:**

| Factor | Docker Secrets | HashiCorp Vault |
|--------|---------------|-----------------|
| **Complexity** | LOW - Built into Docker | HIGH - Separate service to maintain |
| **Learning Curve** | LOW - Simple file-based | HIGH - New system to learn |
| **Single Point of Failure** | NO - Distributed with Docker | YES - Vault must be highly available |
| **Rotation** | Manual (acceptable) | Automatic (nice to have) |
| **Audit Trail** | Limited | Comprehensive |
| **Cost** | FREE | Infrastructure + maintenance cost |
| **HIPAA Compliance** | YES (with procedures) | YES (with procedures) |

**Recommendation:** **Stick with Docker Secrets for initial production launch.**

**Rationale:**
1. Docker Secrets are production-ready and HIPAA-compliant
2. Manual rotation with documented procedures is acceptable
3. HashiCorp Vault adds significant complexity for marginal benefit
4. Current team size doesn't justify Vault operational overhead
5. Can migrate to Vault later if requirements change

**Future Consideration:**
Revisit Vault if:
- Team grows beyond 5 developers
- Rotation becomes burdensome (>10 manual rotations/month)
- Compliance requirements demand automatic expiry
- Organization standardizes on Vault

---

## WireGuard Tunnel Hardening

### Current Configuration Review

**Status: GOOD - Well-Configured**

Current strengths:
- ✅ Separate containers for isolation
- ✅ ChaCha20-Poly1305 encryption (modern, fast)
- ✅ Preshared keys for quantum resistance
- ✅ Health checks configured
- ✅ Proper network namespace isolation

### Recommended Improvements

#### 1. Restrict AllowedIPs (RECOMMENDED)

**Current Issue:** AllowedIPs may be too permissive in some configurations.

**Fix:**

```ini
# /var/lib/docker/secrets/wg_web.conf
[Interface]
PrivateKey = <from-secret-file>
Address = 10.100.0.10/24
ListenPort = 51820

[Peer]
PublicKey = <services-public-key>
PresharedKey = <preshared-key>
AllowedIPs = 10.100.0.11/32, 10.101.0.0/24  # ONLY services server IP + internal network
Endpoint = 10.150.96.37:51820
PersistentKeepalive = 25
```

```ini
# /var/lib/docker/secrets/wg_services.conf
[Interface]
PrivateKey = <from-secret-file>
Address = 10.100.0.11/24
ListenPort = 51820

[Peer]
PublicKey = <web-public-key>
PresharedKey = <preshared-key>
AllowedIPs = 10.100.0.10/32  # ONLY web server IP
PersistentKeepalive = 25
```

**Impact:**
- Prevents tunnel from routing unintended traffic
- Defense-in-depth security layer
- No performance impact

#### 2. Add Firewall Rules Within WireGuard Container (DEFENSE IN DEPTH)

**Purpose:** Ensure only specific ports are accessible through tunnel.

**Implementation:**

Create `/opt/wireguard/firewall-init.sh` in WireGuard container:

```bash
#!/bin/bash
# WireGuard container firewall rules
# Only allow specific ports through tunnel

set -e

# Install nftables
apk add --no-cache nftables

# Create restrictive forwarding rules
nft add table inet filter
nft add chain inet filter forward '{ type filter hook forward priority 0; policy drop; }'

# Allow only required services
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 3306 accept comment '"MariaDB"'
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 6379 accept comment '"Redis"'
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 8001 accept comment '"Django API"'

# Allow established connections back
nft add rule inet filter forward ct state established,related accept

# Log dropped packets (for debugging)
nft add rule inet filter forward limit rate 10/minute log prefix '"WG-BLOCK: "' level info

# Drop everything else
nft add rule inet filter forward drop

echo "WireGuard firewall rules applied"
```

Update WireGuard Dockerfile:

```dockerfile
FROM alpine:latest

RUN apk add --no-cache wireguard-tools nftables

COPY firewall-init.sh /opt/wireguard/
RUN chmod +x /opt/wireguard/firewall-init.sh

CMD ["/opt/wireguard/start.sh"]
```

**Verification:**

```bash
# Test that only allowed ports work
docker exec naaccord-wireguard-web nc -zv 10.100.0.11 3306  # Should work
docker exec naaccord-wireguard-web nc -zv 10.100.0.11 22    # Should FAIL
```

#### 3. Policy Routing (PARANOID - OPTIONAL)

**Purpose:** Ensure traffic to services server MUST go through WireGuard tunnel (cannot bypass).

**Implementation on web server host:**

```bash
# Create custom routing table for WireGuard
echo "100 wireguard" >> /etc/iproute2/rt_tables

# Force all traffic to services server through tunnel
ip rule add to 10.100.0.11 lookup wireguard priority 100
ip route add 10.100.0.11 dev docker0 table wireguard

# Make persistent
cat >> /etc/rc.local <<'EOF'
ip rule add to 10.100.0.11 lookup wireguard priority 100
ip route add 10.100.0.11 dev docker0 table wireguard
EOF

chmod +x /etc/rc.local
```

**Verification:**

```bash
# Verify routing table
ip rule list | grep wireguard
ip route show table wireguard

# Test (should fail if tunnel is down)
docker exec naaccord-web curl -f http://10.100.0.11:8001/health/
```

**Note:** This is paranoid security - not strictly necessary if firewall rules are properly configured.

---

## Container Hardening

### Current Security Posture

**Status: GOOD**

Current strengths:
- ✅ No privileged containers (except WireGuard with minimal necessary capabilities)
- ✅ All application containers run as non-root user (1000:1000)
- ✅ `no-new-privileges:true` security option enabled
- ✅ tmpfs for sensitive directories (prevents disk writes)
- ✅ Resource limits configured (memory, CPU)
- ✅ Health checks implemented

### Recommended Easy Wins

#### 1. Read-Only Root Filesystem (RECOMMENDED)

**Purpose:** Prevent container compromise from modifying binaries or libraries.

**Implementation:**

```yaml
# docker-compose.prod.yml additions

web:
  read_only: true
  tmpfs:
    - /tmp:rw,noexec,nosuid,size=512m
    - /app/tmp:rw,noexec,nosuid,size=256m
    - /var/cache/nginx:rw,size=256m

services:
  read_only: true
  tmpfs:
    - /tmp:rw,noexec,nosuid,size=1g
    - /app/tmp:rw,size=512m
    - /var/log/app:rw,size=256m

celery:
  read_only: true
  tmpfs:
    - /tmp:rw,noexec,nosuid,size=1g

celery-beat:
  read_only: true
  tmpfs:
    - /tmp:rw,noexec,nosuid,size=256m
```

**Testing:**

```bash
# Verify read-only filesystem
docker exec naaccord-web touch /usr/bin/test  # Should FAIL
docker exec naaccord-web touch /tmp/test      # Should WORK
```

**Rollback:** Remove `read_only: true` if application breaks.

#### 2. Drop Unnecessary Linux Capabilities (ALREADY DONE)

**Status:** ✅ **No action needed**

Since containers run as non-root user (1000:1000), Linux capabilities are already dropped. Running as non-root is more effective than explicit capability dropping.

**Verification:**

```bash
docker exec naaccord-web capsh --print
# Should show: Current: =
# (empty capability set)
```

#### 3. Seccomp Profile (OPTIONAL - ADVANCED)

**Purpose:** Block dangerous system calls that application doesn't need.

**Implementation:**

Create `/opt/naaccord/deploy/seccomp-default.json`:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": [
    "SCMP_ARCH_X86_64",
    "SCMP_ARCH_X86",
    "SCMP_ARCH_X32"
  ],
  "syscalls": [
    {
      "names": [
        "accept", "accept4", "access", "arch_prctl", "bind", "brk",
        "clone", "close", "connect", "dup", "dup2", "dup3",
        "epoll_create", "epoll_create1", "epoll_ctl", "epoll_wait",
        "execve", "exit", "exit_group", "fcntl", "fstat",
        "futex", "getdents", "getdents64", "getegid", "geteuid",
        "getgid", "getpid", "getppid", "getrandom", "getrlimit",
        "getsockname", "getsockopt", "gettid", "getuid",
        "ioctl", "listen", "lseek", "madvise", "mmap", "mprotect",
        "munmap", "nanosleep", "open", "openat", "pipe", "pipe2",
        "poll", "ppoll", "prctl", "pread64", "pwrite64",
        "read", "readlink", "recvfrom", "recvmsg", "rt_sigaction",
        "rt_sigprocmask", "rt_sigreturn", "select", "sendmsg",
        "sendto", "set_robust_list", "set_tid_address", "setitimer",
        "setsockopt", "shutdown", "sigaltstack", "socket",
        "socketpair", "stat", "statfs", "tgkill", "uname",
        "wait4", "write", "writev"
      ],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

Update docker-compose.prod.yml:

```yaml
web:
  security_opt:
    - no-new-privileges:true
    - seccomp=/opt/naaccord/deploy/seccomp-default.json
```

**Testing:**

```bash
# Start container with seccomp profile
docker compose -f docker-compose.prod.yml --profile web up -d

# Test application still works
curl -f http://localhost/health/
```

**Note:** This is an advanced hardening measure. Only implement if team has seccomp expertise.

---

## Logging Infrastructure

### Current State

**Status: NEEDS IMPROVEMENT**

Current gaps:
- ❌ Nginx logs not rotated (disk exhaustion risk)
- ❌ Django logs go to stdout only (ephemeral, lost on container restart)
- ❌ Docker container logs not size-limited (disk exhaustion risk)
- ❌ No log archival (compliance risk)
- ❌ No retention policy defined

### Implementation Plan

#### 1. Docker Logging Configuration

**Add to ALL services in docker-compose.prod.yml:**

```yaml
# Global logging configuration
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
    compress: "true"
    labels: "service,environment"

services:
  nginx:
    logging: *default-logging
    # ... rest of config

  web:
    logging: *default-logging
    # ... rest of config

  services:
    logging: *default-logging
    # ... rest of config

  celery:
    logging: *default-logging
    # ... rest of config

  # ... apply to all containers
```

**Result:**
- Each container limited to 50MB logs (10MB × 5 files)
- Automatic compression
- Prevents disk exhaustion

#### 2. Logrotate Configuration

**Create /etc/logrotate.d/naaccord:**

```bash
# Nginx logs
/var/log/nginx/*.log {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    create 0644 nginx nginx
    sharedscripts
    postrotate
        docker exec naaccord-nginx nginx -s reload
    endscript
}

# Django application logs
/var/log/naaccord/*.log {
    daily
    rotate 90
    compress
    delaycompress
    missingok
    notifempty
    create 0644 naaccord naaccord
    sharedscripts
    postrotate
        # Signal containers to reopen log files (if writing to files)
        systemctl reload docker
    endscript
}

# Docker container logs (managed by Docker, just clean old)
/var/lib/docker/containers/*/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
    copytruncate
}
```

**Installation:**

```bash
# Copy config
sudo cp logrotate-naaccord.conf /etc/logrotate.d/naaccord

# Test configuration
sudo logrotate -d /etc/logrotate.d/naaccord

# Force rotation to verify
sudo logrotate -f /etc/logrotate.d/naaccord
```

#### 3. Django Logging Configuration

**Add to depot/settings.py:**

```python
import logging.config
import os

# Create log directory
LOG_DIR = '/var/log/naaccord'
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d'
        },
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file_app': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'django.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
        },
        'file_audit': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'audit.log'),
            'maxBytes': 100 * 1024 * 1024,  # 100MB
            'backupCount': 20,
            'formatter': 'json',
        },
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'security.log'),
            'maxBytes': 50 * 1024 * 1024,  # 50MB
            'backupCount': 10,
            'formatter': 'json',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_app'],
            'level': 'INFO',
        },
        'depot': {
            'handlers': ['console', 'file_app'],
            'level': 'INFO',
        },
        'depot.audit': {
            'handlers': ['file_audit'],
            'level': 'INFO',
            'propagate': False,
        },
        'depot.security': {
            'handlers': ['file_security', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
```

**Install dependency:**

```bash
pip install python-json-logger
# Add to requirements.txt
```

#### 4. Log Archival to NAS

**Create /opt/naaccord/scripts/archive-logs.sh:**

```bash
#!/bin/bash
# Archive logs to NAS for long-term storage (HIPAA compliance: 7 years)

set -e

LOG_DIR="/var/log/naaccord"
NGINX_LOG_DIR="/var/log/nginx"
ARCHIVE_DIR="/mnt/nas/logs/archive"
RETENTION_DAYS=30
HIPAA_RETENTION_DAYS=2555  # 7 years

# Ensure archive directory exists
mkdir -p "$ARCHIVE_DIR"

# Archive application logs older than 30 days
echo "Archiving application logs older than $RETENTION_DAYS days..."
find "$LOG_DIR" -name "*.log.*" -mtime +$RETENTION_DAYS -exec mv {} "$ARCHIVE_DIR/" \;

# Archive nginx logs older than 30 days
echo "Archiving nginx logs older than $RETENTION_DAYS days..."
find "$NGINX_LOG_DIR" -name "*.log.*" -mtime +$RETENTION_DAYS -exec mv {} "$ARCHIVE_DIR/" \;

# Compress archived logs (if not already compressed)
echo "Compressing archived logs..."
find "$ARCHIVE_DIR" -name "*.log.*" ! -name "*.gz" -exec gzip {} \;

# Delete archives older than 7 years (HIPAA retention limit)
echo "Deleting archives older than $HIPAA_RETENTION_DAYS days (7 years)..."
find "$ARCHIVE_DIR" -name "*.log.*.gz" -mtime +$HIPAA_RETENTION_DAYS -delete

# Log completion
ARCHIVED_COUNT=$(find "$ARCHIVE_DIR" -name "*.log.*.gz" | wc -l)
logger -t naaccord-archive "Archived logs: $ARCHIVED_COUNT files in $ARCHIVE_DIR"

echo "Log archival complete: $ARCHIVED_COUNT files archived"
```

**Install as cron job:**

```bash
# /etc/cron.d/naaccord-logs
0 2 * * * root /opt/naaccord/scripts/archive-logs.sh >> /var/log/naaccord/archive.log 2>&1
```

**Verification:**

```bash
# Test archive script
sudo /opt/naaccord/scripts/archive-logs.sh

# Check cron job
sudo crontab -l | grep archive-logs
```

#### 5. Log Monitoring with Grafana Loki

**Promtail configuration (if not already configured):**

```yaml
# /etc/promtail/config.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log

  - job_name: django
    static_configs:
      - targets:
          - localhost
        labels:
          job: django
          __path__: /var/log/naaccord/*.log

  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
```

### Logging Summary

After implementation:

```
Log Flow:

  Application --> Container Logs (10MB × 5 files, compressed)
                       |
                       v
                  Docker JSON Driver
                       |
                       v
                Host Filesystem (/var/log/naaccord/)
                       |
                       +-- Logrotate (daily, 90 days)
                       |
                       +-- Archive to NAS (after 30 days)
                       |         |
                       |         v
                       |    /mnt/nas/logs/archive/ (7 years)
                       |
                       +-- Grafana Loki (real-time viewing)
```

**HIPAA Compliance:**
- ✅ 90 days hot storage (fast access)
- ✅ 7 years cold storage on NAS (compliance requirement)
- ✅ Automated archival and cleanup
- ✅ Audit trail preserved

---

## Documentation Consolidation

### Current Documentation Assessment

**Issue:** Documentation is scattered across multiple locations with significant redundancy.

**Locations:**
- `deploy/` - Multiple deployment guides
- `docs/` - Security and technical documentation
- `docs/worklogs/` - Historical implementation notes

**Redundant/Overlapping Files:**
- `deploy/deploy-steps.md` vs `deploy/CLAUDE.md` vs `deploy/deploy-web-steps.md`
- Multiple SSL configuration documents
- Old deployment logs and debug files

### Consolidation Plan

#### Files to Create

1. **deploy/security-hardening-production.md** (THIS DOCUMENT)
   - Complete security hardening guide
   - Secrets rotation procedures
   - Container hardening recommendations
   - Logging infrastructure setup

2. **deploy/secrets-rotation-playbook.md**
   - Detailed step-by-step rotation procedures
   - Rotation schedule and tracking
   - Rollback procedures
   - Testing checklist

3. **deploy/incident-response.md**
   - Security incident procedures
   - Escalation paths
   - Evidence collection
   - Post-incident review template

4. **deploy/security-audit-checklist.md**
   - Pre-production security checklist
   - Quarterly security review checklist
   - Compliance verification checklist

#### Files to Update

1. **deploy/CLAUDE.md**
   - Add link to security hardening docs
   - Update deployment status
   - Reference new security procedures

2. **docs/security/deployment-todos.md**
   - Mark completed items
   - Update priorities based on this document

3. **deploy/deploy-steps.md**
   - Add security hardening steps
   - Reference rotation procedures
   - Update with current best practices

#### Files to Archive

Create `deploy/archive-2025-10-05/` and move:

```
deploy/
├── archive-2025-10-05/
│   ├── deploy-debug.md           # Old debugging notes
│   ├── deploy-log.md              # Old deployment logs
│   ├── NGINX-PROXY-MANAGER-CONFIG.md  # Not using NPM in production
│   ├── SSL-IMPLEMENTATION-COMPLETE-SUMMARY.md  # Consolidate into main docs
│   └── README.md                  # Index of archived files
```

**Archive README.md:**

```markdown
# Archived Documentation - October 5, 2025

These files are preserved for historical reference but are no longer current.

## Why Archived

- deploy-debug.md: Replaced by current troubleshooting docs
- deploy-log.md: Historical deployment notes
- NGINX-PROXY-MANAGER-CONFIG.md: Not using NPM in production
- SSL-IMPLEMENTATION-COMPLETE-SUMMARY.md: Consolidated into deploy-steps.md

## Current Documentation

See parent directory for up-to-date documentation.
```

---

## Implementation Roadmap

### Phase 0: Immediate (Pre-Production)

**Timeline:** 1-2 hours before production launch

**Tasks:**

1. **Fix Redis password secret** (15 minutes)
   - Generate password
   - Update docker-compose.prod.yml
   - Test container restart

2. **Add Docker logging limits** (30 minutes)
   - Update docker-compose.prod.yml
   - Restart containers
   - Verify log size limits

3. **Create logrotate configs** (30 minutes)
   - Create /etc/logrotate.d/naaccord
   - Test configuration
   - Force initial rotation

**Success Criteria:**
- ✅ Redis password in Docker secret (not .env)
- ✅ Container logs limited to 50MB per container
- ✅ Logrotate configured and tested

### Phase 1: High Priority (Week 1)

**Timeline:** 4-6 hours

**Tasks:**

1. **Configure log archival** (2 hours)
   - Create archive script
   - Setup cron job
   - Test archival to NAS
   - Verify 7-year retention

2. **Document rotation procedures** (3 hours)
   - Create secrets-rotation-playbook.md
   - Test Redis rotation in staging
   - Document rollback procedures

3. **Add read-only filesystems** (1 hour)
   - Update docker-compose.prod.yml
   - Test application functionality
   - Document any tmpfs additions needed

**Success Criteria:**
- ✅ Logs archived to NAS automatically
- ✅ All rotation procedures documented and tested
- ✅ Read-only containers running successfully

### Phase 2: Medium Priority (Week 2)

**Timeline:** 6-8 hours

**Tasks:**

1. **Harden WireGuard** (4 hours)
   - Restrict AllowedIPs configuration
   - Add nftables firewall rules
   - Test tunnel with restrictions
   - Verify only required ports accessible

2. **Container hardening** (2 hours)
   - Verify capabilities dropped
   - Test read-only filesystems
   - Document any issues

3. **Documentation consolidation** (2 hours)
   - Archive old documents
   - Update current documentation
   - Create security audit checklist

**Success Criteria:**
- ✅ WireGuard tunnel hardened
- ✅ Container security verified
- ✅ Documentation organized and current

### Phase 3: Low Priority (Week 3+)

**Timeline:** As needed

**Tasks:**

1. **First secrets rotation** (2 hours)
   - Rotate Redis password (30 days post-launch)
   - Document actual time taken
   - Update procedures based on experience

2. **Security audit** (4 hours)
   - Run through security audit checklist
   - Document any gaps
   - Plan remediation

3. **Advanced hardening (optional):**
   - Seccomp profiles (if team has expertise)
   - AppArmor profiles (if using Ubuntu)
   - Policy routing (paranoid security)

**Success Criteria:**
- ✅ First rotation successful
- ✅ Security audit complete
- ✅ Production running smoothly

---

## Risk Assessment

### Risk Matrix

```
IMPACT vs PROBABILITY:

HIGH IMPACT, HIGH PROBABILITY:
- [FIX NOW] Redis password in .env file
- [FIX NOW] No log rotation (disk exhaustion)

HIGH IMPACT, LOW PROBABILITY:
- [DOCUMENT] Database password rotation failure
- [DOCUMENT] WireGuard tunnel rotation outage
- [ACCEPT] Secrets vault compromise

LOW IMPACT, HIGH PROBABILITY:
- [ACCEPT] Manual rotation burden
- [ACCEPT] Documentation drift

LOW IMPACT, LOW PROBABILITY:
- [IGNORE] Container escape (running as non-root)
- [IGNORE] Docker socket exposure (not mounted)
```

### Identified Risks

| Risk | Impact | Probability | Mitigation | Status |
|------|--------|-------------|------------|--------|
| Redis password in .env | HIGH | CERTAIN | Move to Docker secret | FIX IMMEDIATELY |
| No log rotation | HIGH | HIGH | Configure logrotate | FIX IMMEDIATELY |
| Secrets not rotated | MEDIUM | LOW | Document procedures | ACCEPT FOR NOW |
| DB password rotation fails | HIGH | LOW | Test in staging, document rollback | DOCUMENT |
| WireGuard rotation outage | MEDIUM | LOW | Schedule maintenance window | ACCEPT |
| Container compromise | LOW | VERY LOW | Running as non-root, read-only FS | MITIGATED |

### Rollback Procedures

**For each change, document rollback:**

1. **Docker logging limits:**
   ```bash
   # Remove logging section from docker-compose.prod.yml
   # Restart containers
   docker compose -f docker-compose.prod.yml restart
   ```

2. **Read-only filesystems:**
   ```bash
   # Remove read_only: true from docker-compose.prod.yml
   # Restart containers
   docker compose -f docker-compose.prod.yml restart
   ```

3. **WireGuard configuration changes:**
   ```bash
   # Restore previous WireGuard config from backup
   cp /var/lib/docker/secrets/wg_*.conf.backup /var/lib/docker/secrets/
   docker restart naaccord-wireguard-web naaccord-wireguard-services
   ```

4. **Secrets rotation:**
   - Detailed rollback in each rotation procedure
   - Always keep previous secret for 24 hours
   - Test rollback in staging before production rotation

---

## Conclusion

### Production Readiness Score: 85/100

**Breakdown:**
- Infrastructure Security: 90/100 (solid foundation)
- Secrets Management: 75/100 (needs rotation procedures)
- Logging & Audit: 80/100 (needs archival setup)
- Documentation: 85/100 (needs consolidation)
- Container Security: 95/100 (excellent practices)

**Deductions:**
- -5: Secrets rotation not documented
- -5: Logging not persisted/archived
- -5: Documentation scattered

### Recommendation

**READY FOR PRODUCTION** after implementing Phase 0 and Phase 1:

1. **Phase 0 (IMMEDIATE - 2 hours):**
   - Fix Redis password secret
   - Add Docker logging limits
   - Configure logrotate

2. **Phase 1 (Week 1 - 6 hours):**
   - Setup log archival to NAS
   - Document all rotation procedures
   - Add read-only filesystems

**Phases 2-4 can be completed post-launch** without impacting production readiness.

### Next Steps

1. Review this document with team
2. Test Phase 0 changes in staging
3. Schedule implementation window
4. Execute Phase 0 before production launch
5. Plan Phase 1 implementation for first week
6. Schedule first secrets rotation for 30 days post-launch

---

## Appendix

### Useful Commands

**Check secrets:**
```bash
# List Docker secrets
ls -la /var/lib/docker/secrets/

# Verify secret permissions
stat /var/lib/docker/secrets/db_password

# Read secret from within container
docker exec naaccord-services cat /run/secrets/db_password
```

**Check logs:**
```bash
# View container logs
docker logs naaccord-services -f

# Check log file sizes
du -sh /var/log/naaccord/*
du -sh /var/log/nginx/*

# Test logrotate
sudo logrotate -d /etc/logrotate.d/naaccord
```

**Check WireGuard:**
```bash
# Show tunnel status
docker exec naaccord-wireguard-web wg show
docker exec naaccord-wireguard-services wg show

# Test tunnel connectivity
docker exec naaccord-wireguard-web ping -c 3 10.100.0.11
```

**Check container security:**
```bash
# Verify running as non-root
docker exec naaccord-services id
# Should show: uid=1000(app) gid=1000(app)

# Verify capabilities
docker exec naaccord-services capsh --print
# Should show: Current: = (empty)

# Verify read-only filesystem
docker exec naaccord-services touch /test
# Should fail with: Read-only file system
```

### Contact Information

**Security Lead:** [TBD]
**DevOps Lead:** [TBD]
**Compliance Officer:** [TBD]

---

*End of Document*
