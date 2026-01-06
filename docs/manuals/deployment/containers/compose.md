# Docker Compose Files Comparison

## Quick Decision Guide

| Use Case | File to Use | Command |
|----------|------------|---------|
| Local development (code outside Docker) | `docker-compose.yml` | `docker-compose up` |
| Testing SAML authentication | `docker-compose.test.yml` | `docker-compose -f docker-compose.test.yml up` |
| Production deployment | `docker-compose.prod.yml` | `docker-compose -f docker-compose.prod.yml up -d` |
| Server with git updates | `docker-compose.deploy.yml` | `./scripts/deploy.sh` |

## Detailed Comparison

| Feature | Base (.yml) | Test | Deploy | Prod |
|---------|-------------|------|--------|------|
| **Purpose** | Local dev | Full testing | Git-based deploy | Production |
| **Code Location** | Host machine | In container | Mounted from host | In container |
| **SAML IdP** | ❌ | ✅ Mock IdP | ❌ | ❌ Real SAML |
| **Vite Dev Server** | ❌ | ✅ Hot reload | ❌ | ❌ |
| **WireGuard (PHI encryption)** | ❌ | ✅ Testing | ✅ | ✅ Full |
| **Nginx** | ❌ | ❌ | ❌ | ✅ |
| **SSL/TLS** | ❌ | ❌ | ❌ | ✅ |
| **Health Checks** | ❌ | Basic | ✅ | ✅ Full |
| **Resource Limits** | ❌ | ❌ | ❌ | ✅ |
| **Secrets Management** | Env vars | Env vars | Env vars | Docker secrets |
| **Read-only Filesystem** | ❌ | ❌ | ❌ | ✅ |
| **Update Method** | Local edit | Rebuild | Git pull | Rebuild |
| **Celery Workers** | Optional | ✅ | ✅ | ✅ Multiple |
| **Debug Mode** | ✅ | ✅ | ❌ | ❌ |

## Services in Each Configuration

### Base (docker-compose.yml)
- MariaDB
- Redis
- (Django runs on host)

### Test (docker-compose.test.yml)
- MariaDB
- Redis
- WireGuard
- Web container (Django)
- Services container (Django + R)
- Mock SAML IdP
- Vite dev server
- (All in containers)

### Deploy (docker-compose.deploy.yml)
- MariaDB
- Redis
- WireGuard
- Web container (code mounted from host)
- Services container (code mounted from host)
- Celery workers
- (Code updated via git pull)

### Prod (docker-compose.prod.yml)
- Redis (external MariaDB assumed)
- WireGuard (2 containers for web/services)
- Nginx (reverse proxy + SSL)
- Web containers (multiple replicas)
- Services containers (multiple replicas)
- Celery workers (multiple)
- Celery beat (scheduler)
- Flower (monitoring)
- (Fully containerized, hardened)

## Key Differences

### 1. **Base** - Minimal Docker
- You write code locally in your editor
- Only databases run in Docker
- Fastest for development
- No SAML testing possible

### 2. **Test** - Full Featured Testing
- Everything in containers including mock SAML
- Can test authentication flow
- Has Vite for CSS/JS hot reload
- Closest to production but with dev tools

### 3. **Deploy** - Git-based Updates
- Code mounted from host filesystem
- Update by: `git pull && docker-compose restart`
- Good for staging servers
- No need to rebuild containers for code changes

### 4. **Prod** - Production Ready
- Fully hardened security
- Multiple replicas for scaling
- Real SAML (not mock)
- Nginx with SSL
- Resource limits to prevent DoS
- Health checks for auto-recovery

## Which Should You Use?

- **Developing locally?** → `docker-compose.yml`
- **Testing SAML login?** → `docker-compose.test.yml`
- **Deploying to staging?** → `docker-compose.deploy.yml`
- **Going to production?** → `docker-compose.prod.yml`