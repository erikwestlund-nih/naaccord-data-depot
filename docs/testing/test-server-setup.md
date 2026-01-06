# NA-ACCORD Dual-Server Setup Guide

**Repository**: naaccord-data-depot
**Architecture**: Separated web and services tiers with WireGuard VPN

## Server Architecture

### Services Server (192.168.50.11) - Primary Backend
- **MariaDB** (native install with encryption)
- **Redis** (container)
- **Django Services** (container) - API + Celery + R/Quarto processing
- **WireGuard** (container) - VPN endpoint

### Web Server (192.168.50.10) - Frontend Only
- **nginx** (container) - reverse proxy + SSL termination
- **Django Web** (container) - web interface only (no database)
- **WireGuard** (container) - VPN client

### Network Communication
- **Public**: Internet → Web Server (nginx) → Django Web container
- **Private**: Django Web → WireGuard tunnel (10.100.0.0/24) → Django Services
- **Internal**: Django Services ↔ MariaDB + Redis (localhost)

## Container Images Available

All images are available at GitHub Container Registry:

- `ghcr.io/jhbiostatcenter/naaccord/services:latest` - Django API + Celery + R
- `ghcr.io/jhbiostatcenter/naaccord/web:latest` - Django web interface
- `ghcr.io/jhbiostatcenter/naaccord/nginx:latest` - nginx reverse proxy
- `ghcr.io/jhbiostatcenter/naaccord/wireguard:latest` - WireGuard VPN

## Deployment Strategy

**🎯 RECOMMENDED APPROACH:**

1. **Focus on Services Server FIRST** - Get the backend working completely
2. **Verify all backend services** - MariaDB, Redis, Django API, Celery, R processing
3. **Only then deploy Web Server** - Once backend is stable

## Part 1: Services Server Setup (192.168.50.11)

### Step 1: Initial Server Setup

```bash
# Install prerequisites
sudo dnf install -y git ansible python3-pip docker docker-compose

# Create application directory
sudo mkdir -p /app
sudo chown $USER:$USER /app

# Clone repository
cd /app
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git
cd naaccord-data-depot
```

### Step 2: Generate Secrets

```bash
# Clear any Ansible environment variables
unset ANSIBLE_VAULT_PASSWORD_FILE ANSIBLE_CONFIG

# Generate secrets (remember the vault password!)
export ANSIBLE_CONFIG=/dev/null
ansible-playbook ansible/playbooks/setup-secrets.yml --connection=local
```

### Step 3: Add GitHub Token to Vault

Edit the vault to add your GitHub Personal Access Token:
```bash
ansible-vault edit ansible/vars/secrets.yml
```

Update the line:
```yaml
vault_github_token: "ghp_YOUR_ACTUAL_TOKEN_HERE"
```

**To create a GitHub PAT:** GitHub → Settings → Developer Settings → Personal Access Tokens → Generate new token (classic) → Select `repo` and `read:packages` scopes.

### Step 4: Deploy Services Server

Run the services deployment:
```bash
ansible-playbook ansible/playbooks/deploy-services-server.yml --connection=local --ask-vault-pass --ask-become-pass -v
```

This will:
- Install and configure MariaDB with encryption
- Setup WireGuard VPN server
- Pull and start services container from GitHub registry
- Configure Redis, Django API, and Celery workers
- Initialize database with test data

### Step 5: Verify Services Server

```bash
# Check all containers are running
docker ps

# Test database connection
grep DB_APP_PASSWORD .env.deploy
mysql -u naaccord_app -p<PASSWORD> naaccord -e "SELECT 1;"

# Test Django API
curl http://localhost:8001/health/
# Expected: {"status": "healthy"}

# Test Redis
docker exec naaccord-redis redis-cli ping
# Expected: PONG

# Test Celery workers
docker exec naaccord-celery celery -A depot inspect active
# Expected: Shows active workers
```

### Step 6: Test R/Quarto Processing (Critical!)

```bash
# Enter the services container
docker exec -it naaccord-services bash

# Test R is working
R --version

# Test Quarto is working
quarto --version

# Test NAATools package
R -e "library(NAATools); packageVersion('NAATools')"

# Exit container
exit
```

**If R/Quarto tests fail, the services server is NOT ready for web server deployment.**

## Part 2: Web Server Reset (If Needed)

If you need to completely reset the web server:

```bash
# Copy and run the reset script on the web server
scp scripts/reset-web-server.sh erik@192.168.50.10:/tmp/
ssh erik@192.168.50.10 "chmod +x /tmp/reset-web-server.sh && /tmp/reset-web-server.sh"
```

## Part 3: Web Server Setup (192.168.50.10)

**⚠️ ONLY proceed when Services Server is fully working!**

### Step 1: Initial Web Server Setup

```bash
# Install prerequisites
sudo dnf install -y git ansible python3-pip docker docker-compose

# Create application directory
sudo mkdir -p /app
sudo chown $USER:$USER /app

# Clone repository
cd /app
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git
cd naaccord-data-depot
```

### Step 2: Copy Secrets from Services Server

```bash
# Copy the secrets vault from services server
scp erik@192.168.50.11:/app/naaccord-data-depot/ansible/vars/secrets.yml ansible/vars/
```

### Step 3: Deploy Web Server

```bash
ansible-playbook ansible/playbooks/deploy-web-server.yml --connection=local --ask-vault-pass --ask-become-pass -v
```

This will:
- Setup WireGuard VPN client to connect to services server
- Pull and start web container from GitHub registry
- Configure nginx reverse proxy with SSL
- Connect web interface to services server via WireGuard tunnel

### Step 4: Verify Web Server

```bash
# Check containers are running
docker ps

# Test WireGuard tunnel to services server
ping 10.100.0.2  # Services server WireGuard IP

# Test web interface can reach services API
curl http://localhost:8000/health/
# Expected: {"status": "healthy"}

# Test nginx is serving correctly
curl -I http://localhost/
# Expected: HTTP 200 or redirect
```

## Part 4: Cross-Server Communication

### WireGuard Network Layout

- **Services Server WireGuard IP**: `10.100.0.2/24`
- **Web Server WireGuard IP**: `10.100.0.1/24`
- **Services API Endpoint**: `http://10.100.0.2:8001`

### Environment Variables

**Web Server** `.env.deploy`:
```bash
SERVER_ROLE=web
SERVICES_URL=http://10.100.0.2:8001  # Via WireGuard tunnel
INTERNAL_API_KEY=<shared_secret>
# No database settings - web connects to services
```

**Services Server** `.env.deploy`:
```bash
SERVER_ROLE=services
DATABASE_HOST=host.containers.internal  # Local MariaDB
DATABASE_NAME=naaccord
DATABASE_USER=naaccord_app
DATABASE_PASSWORD=<generated_password>
REDIS_HOST=redis
REDIS_PASSWORD=<generated_password>
```

## Troubleshooting

### Services Server Issues

```bash
# Check MariaDB is working
sudo systemctl status mariadb
mysql -u naaccord_app -p<PASSWORD> naaccord -e "SHOW TABLES;"

# Check containers
docker logs naaccord-services
docker logs naaccord-celery
docker logs naaccord-redis

# Restart services if needed
docker-compose -f docker-compose.yml restart
```

### Web Server Issues

```bash
# Check WireGuard tunnel
sudo wg show
ping 10.100.0.2

# Check web container logs
docker logs naaccord-web
docker logs naaccord-nginx

# Test connection to services API
curl http://10.100.0.2:8001/health/
```

### Cross-Server Communication Issues

```bash
# From web server, test services API directly
curl -H "Authorization: Bearer <INTERNAL_API_KEY>" http://10.100.0.2:8001/api/status/

# Check WireGuard configuration
sudo wg show wg0

# Check routing
ip route show table main | grep 10.100.0
```

## Reset Commands

### Reset Web Server Only
```bash
# Run reset script on web server
/tmp/reset-web-server.sh
```

### Reset Services Server (Nuclear Option)
```bash
# Stop all containers
docker-compose -f docker-compose.yml down

# Remove all containers and images
docker system prune -af

# Reset MariaDB (⚠️ DESTROYS ALL DATA!)
sudo systemctl stop mariadb
sudo rm -rf /var/lib/mysql
sudo dnf remove -y mariadb-server mariadb

# Start over from Step 4 of Services Server setup
```

## Important Notes

1. **Services MUST be working first** - Don't deploy web server until services are fully functional
2. **WireGuard is critical** - Web server cannot reach services without the VPN tunnel
3. **Shared secrets** - Both servers need the same `INTERNAL_API_KEY`
4. **Container registry** - All images are available at `ghcr.io/jhbiostatcenter/naaccord/*:latest`
5. **Single source of truth** - All data storage and processing happens on services server

---

**Last Updated:** 2025-09-26
**Architecture:** Dual-server with WireGuard VPN
**Container Images:** Available at GitHub Container Registry