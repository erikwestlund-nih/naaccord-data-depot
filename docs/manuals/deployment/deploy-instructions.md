# NA-ACCORD Services Server Deployment

**Zero manual commands - fully automated deployment with Ansible.**

**Environments:** These instructions work for both `staging` and `production`. Simply replace `staging` with `production` in all commands.

## Prerequisites

**Local Machine (Mac/Linux):**
- Docker (for WireGuard key generation)
- Ansible (`pip install ansible`)
- OpenSSL (usually pre-installed)

**Target Server:**
- Fresh Rocky Linux 9 (staging) or RHEL 9 (production) server
- SSH access to server
- GitHub SSH keys (public and private)

## Step 0: Generate Vault (Local Machine)

**IMPORTANT:** Vault generation happens on your **local machine**, not the server.

```bash
# On your local machine (from repository root)
cd /path/to/naaccord
./deploy/scripts/generate-vault.sh production  # or: staging
```

**What this generates:**
- Database passwords (root, app, report, backup, encryption key)
- Django secrets (SECRET_KEY, INTERNAL_API_KEY)
- Redis password
- WireGuard tunnel keys (requires Docker)
- Monitoring passwords (Flower, Grafana)

**Prompts for:**
- GitHub Container Registry token (optional, press Enter to skip)
- NAS credentials (username/password)
- Vault password (used to encrypt the file)

**Output:**
- Creates encrypted vault at: `deploy/ansible/inventories/staging/group_vars/all/vault.yml`

**Commit and push:**
```bash
git add deploy/ansible/inventories/staging/group_vars/all/vault.yml
git commit -m "chore: regenerate staging vault secrets"
git push origin main
```

**Save vault password securely** - you'll need it in Step 1.

## Step 1: Bootstrap Server

Copy and run the bootstrap script on the fresh server:

**Option A: Direct copy-paste (recommended, avoids MFA on scp):**

```bash
# SSH to server
ssh user@server

# Open nano editor
nano /tmp/1-init-server.sh

# Copy entire contents of deploy/scripts/1-init-server.sh from your local machine
# Paste into nano (Cmd+V or right-click paste)
# Press Ctrl+X, then Y, then Enter to save

# Make executable and run
chmod +x /tmp/1-init-server.sh
bash /tmp/1-init-server.sh production  # or: staging
```

**Option B: Using scp (requires MFA twice):**

```bash
# From your local machine
scp deploy/scripts/1-init-server.sh user@server:/tmp/
ssh user@server 'bash /tmp/1-init-server.sh production'  # or: staging
```

**What this does:**
- Installs Ansible and dependencies
- Sets up GitHub deploy key for repository access
- Clones NA-ACCORD repository to `/opt/naaccord/depot`
- **Prompts for vault password and creates `~/.naaccord_vault_staging`**
- Verifies vault password works

**When prompted for vault password:** Enter the EXACT password from Step 0 (vault generation).

**If you make a mistake:** The script is idempotent and can be re-run from the repository:
```bash
/opt/naaccord/depot/deploy/scripts/1-init-server.sh production  # or: staging
```

## Step 2a: Deploy Services Server

Run the deployment script on the **services** server:

```bash
# On the services server (already in SSH session from Step 1)
/opt/naaccord/depot/deploy/scripts/2-deploy.sh production services  # or: staging services
```

**What this deploys:**
- Base system packages and configuration
- Firewall rules (SSH, WireGuard)
- NAS mount configuration
- MariaDB with encryption at rest
- Docker secrets from vault
- Docker containers:
  - `naaccord-redis` - Cache and message broker
  - `naaccord-wireguard-services` - Secure PHI tunnel server
  - `naaccord-services` - Django API application
  - `naaccord-celery` - Background task worker
  - `naaccord-celery-beat` - Scheduled task scheduler

**Expected duration:** ~10-15 minutes

## Step 2b: Deploy Web Server

Run the deployment script on the **web** server:

```bash
# On the web server (already in SSH session from Step 1)
/opt/naaccord/depot/deploy/scripts/2-deploy.sh production web  # or: staging web
```

**What this deploys:**
- Base system packages and configuration
- Firewall rules (SSH, HTTP/HTTPS, WireGuard)
- Docker secrets from vault
- Docker containers:
  - `naaccord-wireguard-web` - Secure PHI tunnel client
  - `naaccord-web` - Django web application
  - `naaccord-nginx` - Reverse proxy
  - `naaccord-mock-idp` - SAML mock identity provider (staging only)

**Expected duration:** ~10-15 minutes

**After both servers deployed:** Test WireGuard tunnel connectivity (see Step 3)

## Step 3: Verify Deployment

### On Services Server

Check containers:

```bash
sudo docker ps
```

**Expected containers (all healthy):**
- `naaccord-redis`
- `naaccord-wireguard-services`
- `naaccord-services`
- `naaccord-celery`
- `naaccord-celery-beat`

Check health endpoint:

```bash
curl http://localhost:8001/health/
```

**Expected:** `{"status": "healthy", "database": "connected", "redis": "connected", "server_role": "services"}`

### On Web Server

Check containers:

```bash
sudo docker ps
```

**Expected containers (all healthy):**
- `naaccord-wireguard-web`
- `naaccord-web`
- `naaccord-nginx`
- `naaccord-mock-idp` (staging only)

Check health endpoint:

```bash
curl http://localhost:8000/health/
```

**Expected:** `{"status": "healthy", "server_role": "web"}`

### Test WireGuard Tunnel (Critical!)

From **web server**, ping services server:

```bash
sudo docker exec naaccord-wireguard-web ping -c 3 10.100.0.11
```

From **services server**, ping web server:

```bash
sudo docker exec naaccord-wireguard-services ping -c 3 10.100.0.10
```

**Both should succeed.** If pings fail, check WireGuard logs:
```bash
sudo docker logs naaccord-wireguard-web
sudo docker logs naaccord-wireguard-services
```

## Troubleshooting

If deployment fails, check:

```bash
# View container logs
sudo docker logs naaccord-services --tail 50

# Check firewall rules
sudo firewall-cmd --list-all

# Verify vault password is correct
ansible-vault view inventories/staging/group_vars/all/vault.yml --vault-password-file ~/.naaccord_vault_staging

# Check MariaDB is running
sudo systemctl status mariadb
```

## Notes

- **WireGuard tunnel:** Will show "peer not reachable" until web server is deployed - this is expected
- **Safe to re-run:** The playbook is idempotent - running again won't break things
- **Database passwords:** Never regenerate vault after initial deployment or database access will break

## ⚠️ Production Deployment - Final URL Configuration

**CRITICAL:** Before production deployment, update CSRF configuration with the final production URL:

1. **Update `/opt/naaccord/depot/.env.deploy` on production servers:**
   ```bash
   ALLOWED_HOSTS=<production-ip>,localhost,127.0.0.1,<production-domain>
   CSRF_TRUSTED_ORIGINS=https://<production-domain>
   ```

2. **Replace placeholders:**
   - `<production-ip>` - Production server IP addresses
   - `<production-domain>` - Final production domain (e.g., `naaccord.jhu.edu`)

3. **Why this is required:**
   - Django 4.0+ requires explicit CSRF trusted origins for cross-origin POST requests
   - Without this, form submissions (creating cohorts, uploading files, etc.) will fail with CSRF errors
   - The domain must match exactly what users type in their browsers

4. **After updating, restart containers:**
   ```bash
   cd /opt/naaccord/depot
   docker compose -f docker-compose.prod.yml restart web
   ```

**For staging:** Already configured with `naaccord.pequod.sh`
