# NA-ACCORD Container Architecture

## Services Server (--profile services)

| Container | Image | Purpose | Status |
|-----------|-------|---------|--------|
| naaccord-redis | redis:7-alpine | Cache (tmpfs) | ✅ Running |
| naaccord-wireguard-services | wireguard:latest | PHI tunnel server | ⚠️ Unhealthy |
| naaccord-services | services:latest | Django API (gunicorn) | ⚠️ Unhealthy (DB connection) |
| naaccord-celery | services:latest | Celery worker | ❌ Waiting for services health |
| naaccord-celery-beat | services:latest | Celery scheduler | ❌ Waiting for services health |

**Why celery isn't running:** 
```yaml
depends_on:
  services:
    condition: service_healthy  # ← Services is unhealthy due to DB grants
```

## Web Server (--profile web)

| Container | Image | Purpose |
|-----------|-------|---------|
| naaccord-redis | redis:7-alpine | Cache |
| naaccord-wireguard-web | wireguard:latest | PHI tunnel client |
| naaccord-nginx | nginx:latest | Reverse proxy + SSL |
| naaccord-web | web:latest | Django web (gunicorn) |

## Current Issue

**Root Cause:** MariaDB user `naaccord_app` doesn't have grants from Docker subnet `172.18.%`

**Error:**
```
Access denied for user 'naaccord_app'@'172.18.0.3' (using password: YES)
```

**Solution:** Run MariaDB Ansible role with proper vault passwords to create subnet grants

**Quick Fix for Testing:**
```bash
# Grant access from Docker subnet (requires root access)
sudo mysql -uroot -p<root_password> -e "
  GRANT ALL PRIVILEGES ON naaccord.* TO 'naaccord_app'@'172.18.%' 
  IDENTIFIED BY '<app_password>';
  FLUSH PRIVILEGES;
"
```

## What's in docker-compose.prod.yml

✅ **Complete** - All containers defined:
- Redis (both profiles)
- WireGuard (web & services)  
- Nginx (web only)
- Web Django (web only)
- Services Django (services only)
- Celery worker (services only)
- Celery beat (services only)

