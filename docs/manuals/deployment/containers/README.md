# NA-ACCORD Container Deployment Guide

## Overview

This guide covers the containerized deployment of NA-ACCORD using Docker/Docker with a focus on security, HIPAA compliance, and production readiness.

## Container Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Host System (Rocky Linux/RHEL)          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Nginx   │  │  Django  │  │  Celery  │  │ MariaDB  │  │
│  │  (Web)   │◄─┤   +R/Q   │◄─┤   +R/Q   │  │ (Encrypt)│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│       │             │              │             │          │
│       └─────────────┴──────────────┴─────────────┘         │
│                           │                                 │
│                    ┌──────────┐                            │
│                    │  Redis   │                            │
│                    └──────────┘                            │
│                           │                                 │
│                    ┌──────────┐                            │
│                    │   NAS    │                            │
│                    │  Mount   │                            │
│                    └──────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

## Container Details

### 1. Services Container (Django/Celery with R/Quarto)

**Features:**
- Python 3.12 with Django 5.x
- R 4.x with tidyverse, plotly, knitr
- Quarto 1.4.550 for report generation
- NAATools package from GitHub
- Non-root user execution
- Health checks configured

**Security:**
- Runs as non-root user (uid 1000)
- Read-only root filesystem capability
- Tmpfs mounts for temporary data
- No network access for R execution

### 2. Nginx Container

**Features:**
- Alpine-based for minimal footprint
- mTLS support for internal communication
- Rate limiting configured
- 2GB file upload support
- Static file serving

**Security:**
- TLS 1.2/1.3 only
- Security headers configured
- Client certificate verification
- DDoS protection via rate limiting

### 3. MariaDB (Host Installation)

**Note:** MariaDB is NOT containerized for production. Install directly on host for better performance, simpler backups, and compliance.

**Installation:**
```bash
# On Services Server (192.168.50.11)
sudo dnf install mariadb-server mariadb
sudo systemctl enable --now mariadb
sudo mysql_secure_installation

# Configure encryption at rest
sudo vim /etc/my.cnf.d/encryption.cnf
```

**Security:**
- Native encryption at rest configuration
- Direct filesystem access for encryption keys
- Standard backup/restore procedures
- No container overhead for critical data

## Quick Start

### 1. Prerequisites

```bash
# Install Docker (or Docker)
sudo dnf install -y docker-ce docker-ce-cli containerd.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Install docker-compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Setup Environment

```bash
# Copy and configure environment file
cp .env.deploy.example .env.deploy

# Edit with secure values
vim .env.deploy

# CRITICAL: Generate secure passwords
# SECRET_KEY (64 chars)
openssl rand -hex 32

# Database passwords (32 chars each)
openssl rand -hex 16

# API key (64 chars)
openssl rand -hex 32
```

### 3. Build Containers

```bash
# Build containers
./deploy/containers/build-containers.sh

# This will:
# - Build Services with R/Quarto (10-15 minutes)
# - Build Nginx with mTLS
# - Tag images with date

# Note: MariaDB is installed directly on host, not containerized
```

### 4. Start Services

```bash
# Start all services
docker-compose -f docker-compose.deploy.yml up -d

# View logs
docker-compose -f docker-compose.deploy.yml logs -f

# Check status
docker-compose -f docker-compose.deploy.yml ps
```

### 5. Run Tests

```bash
# Run comprehensive test suite
./scripts/test-containers.sh

# This tests:
# - Database encryption
# - R/Quarto installation
# - NAATools availability
# - Celery task processing
# - Nginx routing
# - Volume mounts
```

## Production Deployment

### 1. Pre-deployment Checklist

- [ ] Update all passwords in .env.deploy
- [ ] Generate proper SSL certificates
- [ ] Configure firewall rules
- [ ] Setup backup strategy
- [ ] Configure monitoring
- [ ] Review security settings
- [ ] Test disaster recovery

### 2. Certificate Setup

```bash
# Generate certificates for mTLS
cd docker/nginx/certs

# Create CA
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt

# Create server certificate
openssl req -new -key server.key -out server.csr
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -out server.crt

# Create client certificate for internal services
openssl req -new -key client.key -out client.csr
openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key -out client.crt
```

### 3. Deploy to Servers

```bash
# On Web Server (10.150.96.6)
export SERVER_ROLE=web
docker-compose -f docker-compose.deploy.yml up -d nginx

# On Services Server (10.150.96.37)
export SERVER_ROLE=services
docker-compose -f docker-compose.deploy.yml up -d mariadb redis django celery celery-beat
```

### 4. Verify Deployment

```bash
# Check encryption
docker exec naaccord-mariadb mysql -uroot -p$DB_ROOT_PASSWORD \
  -e "SELECT TABLE_NAME, ENCRYPTION_SCHEME FROM information_schema.INNODB_TABLESPACES_ENCRYPTION"

# Test R execution
docker exec naaccord-django R -e "library(NAATools); sessionInfo()"

# Test Quarto
docker exec naaccord-django quarto check

# Check Celery
docker exec naaccord-celery celery -A depot inspect active
```

## Container Management

### Starting/Stopping

```bash
# Stop all containers
docker-compose -f docker-compose.deploy.yml down

# Stop specific service
docker-compose -f docker-compose.deploy.yml stop django

# Restart service
docker-compose -f docker-compose.deploy.yml restart celery

# Remove everything (including volumes)
docker-compose -f docker-compose.deploy.yml down -v
```

### Viewing Logs

```bash
# All services
docker-compose -f docker-compose.deploy.yml logs -f

# Specific service
docker-compose -f docker-compose.deploy.yml logs -f django

# Last 100 lines
docker-compose -f docker-compose.deploy.yml logs --tail=100 celery
```

### Shell Access

```bash
# Django shell
docker-compose -f docker-compose.deploy.yml exec django python manage.py shell

# R console
docker-compose -f docker-compose.deploy.yml exec django R

# Database console
docker-compose -f docker-compose.deploy.yml exec mariadb mysql -uroot -p$DB_ROOT_PASSWORD naaccord

# Bash shell
docker-compose -f docker-compose.deploy.yml exec django /bin/bash
```

## Monitoring

### Celery Flower

Access at: http://localhost:5555
- Username: admin (or from FLOWER_USER)
- Password: from FLOWER_PASSWORD

### Container Stats

```bash
# Real-time stats
docker stats

# One-time snapshot
docker-compose -f docker-compose.deploy.yml ps
```

### Health Checks

```bash
# Check all health endpoints
curl http://localhost/health        # Nginx
curl http://localhost:8000/health/  # Django
```

## Backup Strategy

### Database Backup

```bash
# Create backup
docker-compose -f docker-compose.deploy.yml exec mariadb \
  mysqldump -uroot -p$DB_ROOT_PASSWORD naaccord | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore backup
gunzip < backup_20240925.sql.gz | docker-compose -f docker-compose.deploy.yml exec -T mariadb \
  mysql -uroot -p$DB_ROOT_PASSWORD naaccord
```

### Volume Backup

```bash
# Backup volumes
docker run --rm -v naaccord_media_files:/data -v $(pwd):/backup alpine \
  tar czf /backup/media_backup.tar.gz -C /data .

docker run --rm -v naaccord_nas_storage:/data -v $(pwd):/backup alpine \
  tar czf /backup/nas_backup.tar.gz -C /data .
```

## Troubleshooting

### Common Issues

#### 1. R packages not found
```bash
# Rebuild with no cache
docker-compose -f docker-compose.deploy.yml build --no-cache django
```

#### 2. Permission denied errors
```bash
# Fix permissions
docker-compose -f docker-compose.deploy.yml exec django chown -R django:django /app
```

#### 3. Database connection errors
```bash
# Check MariaDB logs
docker-compose -f docker-compose.deploy.yml logs mariadb

# Test connection
docker-compose -f docker-compose.deploy.yml exec django python -c "from django.db import connection; connection.ensure_connection()"
```

#### 4. Celery not processing tasks
```bash
# Check Redis connection
docker-compose -f docker-compose.deploy.yml exec redis redis-cli ping

# Check Celery workers
docker-compose -f docker-compose.deploy.yml exec celery celery -A depot inspect active

# Purge queue if needed
docker-compose -f docker-compose.deploy.yml exec celery celery -A depot purge -f
```

## Security Notes

1. **Never commit .env.deploy to git**
2. **Rotate API keys weekly**
3. **Use proper certificates in production**
4. **Enable firewall rules**
5. **Monitor access logs**
6. **Regular security updates**
7. **Implement backup encryption**

## Performance Tuning

### Django Workers
Adjust in docker-compose.deploy.yml:
```yaml
command: gunicorn --workers 4  # Increase based on CPU cores
```

### Celery Concurrency
```yaml
command: celery -A depot worker --concurrency=4  # Adjust based on workload
```

### MariaDB Buffer Pool
Edit docker/mariadb/my.cnf:
```ini
innodb_buffer_pool_size = 2G  # 70% of available RAM
```

### Nginx Workers
Edit docker/nginx/nginx.conf:
```nginx
worker_processes auto;  # Or specific number
```

## Support

For issues or questions:
1. Check container logs
2. Run test suite
3. Review this documentation
4. Contact DevOps team