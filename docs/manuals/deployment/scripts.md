# NA-ACCORD Deployment Scripts

**Bootstrap scripts for initial server setup before Ansible automation.**

## Overview

These scripts solve the "chicken and egg" problem of deploying NA-ACCORD:
- Need Ansible playbooks from git repository
- But need Ansible installed and GitHub access configured to clone repository

**Solution:** Manual bootstrap script that runs once per server, then Ansible takes over.

## Scripts

### 0. `deploy.sh` - Application Deployment (RECOMMENDED)

**Purpose:** Deploy application updates with fresh code to servers

**What it does:**
1. Pulls latest code from git repository
2. Copies static assets to container volumes (web server only)
3. Restarts Docker containers with fresh code
4. Verifies container health

**Usage:**

```bash
# On web or services server (after bootstrap is complete)
cd /opt/naaccord/depot

# Deploy to staging
./deploy/scripts/deploy.sh staging deploy

# Deploy to production
./deploy/scripts/deploy.sh production main
```

**Arguments:**
- First argument: Environment (`staging` or `production`)
- Second argument: Git branch (default: `deploy`)

**What it updates:**
- ✅ Pulls latest code from repository
- ✅ Copies static assets (`.vite/manifest.json` and `assets/`) to container volume
- ✅ Restarts all containers with fresh code
- ✅ Waits for containers to be healthy
- ✅ Displays deployment summary

**Requirements:**
- Server already bootstrapped with `1-init-server.sh` and `2-prepare-env.sh`
- Ansible playbooks in place
- Vault password file exists (`~/.naaccord_vault_{environment}`)

**Example output:**
```
========================================
NA-ACCORD Application Deployment
========================================

Environment: staging
Branch: deploy
Inventory: /opt/naaccord/depot/deploy/ansible/inventories/staging/hosts.yml

Running deployment playbook...
[Ansible output...]

========================================
Deployment Complete!
========================================
```

### 1. `1-init-server.sh` - Server Bootstrap

**Purpose:** One-time initialization of a fresh RHEL/Rocky Linux server

**What it does:**
1. Installs EPEL repository
2. Installs Ansible and git
3. Sets up GitHub deploy key for repository access
4. Configures SSH for GitHub authentication
5. Clones NA-ACCORD repository to `/opt/naaccord`
6. Verifies directory structure
7. Provides next steps for Ansible deployment

**Usage:**

```bash
# Copy script to server (via scp, or manually paste)
scp deploy/scripts/1-init-server.sh user@services.naaccord.lan:~/

# SSH to server
ssh services.naaccord.lan

# Make executable
chmod +x 1-init-server.sh

# Run initialization (script will prompt for environment and server role)
./1-init-server.sh
```

**Interactive prompts:**
- Environment selection (staging or production)
- Server role (web or services)
- GitHub deploy private key (paste entire key including headers)
- GitHub deploy public key (ssh-ed25519 or ssh-rsa key)
- Vault password for decrypting secrets
- Confirmation if files already exist

**Requirements:**
- RHEL 8+ or Rocky Linux 8+
- User account with sudo access
- GitHub deploy key generated and added to repository

### 2. `2-prepare-env.sh` - Ansible Vault Setup

**Purpose:** Set up Ansible vault with deployment secrets and configuration

**What it does:**
1. Prompts for all deployment-specific secrets (database passwords, API keys, etc.)
2. Generates secure random passwords for unspecified values
3. Generates WireGuard keys for PHI tunnel encryption
4. Creates/updates Ansible vault file with encrypted secrets
5. Saves vault password to secure location
6. Provides next steps for running Ansible playbooks

**Usage:**

```bash
# After 1-init-server.sh completes
cd /opt/naaccord/depot

# Run environment preparation
./deploy/scripts/2-prepare-env.sh staging services  # [environment] [web|services]
```

**Interactive prompts:**
- Domain name (e.g., naaccord.pequod.sh)
- Database passwords (root, app, report, backup users)
- Django secret key and internal API key
- Redis password
- NAS storage credentials (host, share, username, password)
- WireGuard key generation (auto-generated or manual entry)
- Monitoring passwords (Flower, Grafana)

**Generates:**
- Ansible vault file: `deploy/ansible/inventories/{environment}/group_vars/all/vault.yml`
- Vault password file: `~/.naaccord_vault_{environment}` (mode 600)
- WireGuard encryption keys (if auto-generated)

**Security notes:**
- All secrets are encrypted in Ansible vault
- Vault password saved to `~/.naaccord_vault_{environment}` for automation
- **MUST** back up vault password to password manager
- Never commit vault password file to git

**Requirements:**
- `1-init-server.sh` completed (repository cloned)
- Docker installed (for WireGuard key generation)
- Ansible installed

## Bootstrap Workflow

### Complete Deployment Process (Step-by-Step)

**Step 1: Generate GitHub Deploy Keys** (one-time):
```bash
# On each server
ssh-keygen -t ed25519 -C "naaccord-services-staging" -f ~/.ssh/naaccord_deploy
```

Add public keys to GitHub:
- Repository → Settings → Deploy keys → Add deploy key
- One for staging, one for production

**Step 2: Copy init script to server:**
```bash
# From local machine
scp deploy/scripts/1-init-server.sh erik@services.naaccord.lan:~/
```

**Step 3: Run 1-init-server.sh on server:**
```bash
# SSH to server
ssh services.naaccord.lan

# Run initialization (will prompt interactively)
chmod +x 1-init-server.sh
./1-init-server.sh
```

Follow prompts:
- Select environment (staging or production)
- Select server role (web or services)
- Paste GitHub deploy private key when requested
- Paste GitHub deploy public key when requested
- Enter vault password when requested
- Script will test GitHub connection and clone repository

**Step 4: Run prepare-env.sh for vault setup:**
```bash
# After 1-init-server.sh completes
cd /opt/naaccord/depot

# Run environment preparation
./deploy/scripts/2-prepare-env.sh staging services  # [environment] [web|services]
```

Follow prompts:
- Enter domain, database passwords, API keys, etc.
- Choose to auto-generate WireGuard keys (recommended)
- **Save the vault password** displayed at the end!

**Step 5: Verify vault and configuration:**
```bash
# View vault contents
ansible-vault view \
  deploy/ansible/inventories/staging/group_vars/all/vault.yml \
  --vault-password-file=~/.naaccord_vault_staging

# Check vault password file
ls -la ~/.naaccord_vault_staging  # Should be mode 600
```

**Step 6: Run Ansible playbook:**
```bash
cd /opt/naaccord/depot/deploy/ansible

# Services server
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=~/.naaccord_vault_staging

# OR Web server
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file=~/.naaccord_vault_staging
```

**Step 7: Verify deployment:**
```bash
# Check Docker containers
docker ps

# Check health endpoint (services server)
curl http://localhost:8001/health/

# Check logs
docker logs naaccord-services
```

## Troubleshooting

### GitHub Authentication Fails

**Symptom:** Script fails at "Testing GitHub connection"

**Solution:**
1. Verify deploy key is added to GitHub repository
2. Check key permissions: `ls -la ~/.ssh/naaccord_deploy` (should be 600)
3. Test manually: `ssh -T git@github.com`
4. Check SSH config: `cat ~/.ssh/config`

### Repository Clone Fails

**Symptom:** Git clone command fails

**Solution:**
1. Verify GitHub authentication works: `ssh -T git@github.com`
2. Check repository URL is correct in script
3. Verify deploy key has repository access
4. Try manual clone: `git clone git@github.com:JHBiostatCenter/naaccord-data-depot.git /tmp/test`

### Permission Denied on /opt/naaccord

**Symptom:** Cannot create `/opt/naaccord` directory

**Solution:**
1. Verify you have sudo access: `sudo -v`
2. Check directory ownership: `ls -la /opt/`
3. Manually create and fix ownership:
   ```bash
   sudo mkdir -p /opt/naaccord
   sudo chown $(whoami):$(whoami) /opt/naaccord
   ```

### Ansible Not Found After Install

**Symptom:** `ansible: command not found` after installation

**Solution:**
1. Log out and back in to refresh PATH
2. Or manually source: `source /etc/profile`
3. Verify EPEL is enabled: `dnf repolist | grep epel`
4. Manually install: `sudo dnf install -y ansible`

## Server-Specific Notes

### Services Server (services.naaccord.lan)

After `1-init-server.sh`, run services playbook:
```bash
cd /opt/naaccord/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

### Web Server (web.naaccord.lan)

After `1-init-server.sh`, run web playbook:
```bash
cd /opt/naaccord/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass
```

## Environment-Specific Details

### Staging
- Services: `services.naaccord.lan` (192.168.50.11)
- Web: `web.naaccord.lan` (192.168.50.10)
- SAML: Mock-idp (local container)
- NAS: `smb://192.168.1.10`

### Production
- Services: 10.150.96.37 (via VPN)
- Web: 10.150.96.6 (via VPN)
- SAML: JHU Shibboleth
- NAS: TBD from JHU IT

## Related Documentation

- [Deployment Workflow](../../docs/deployment/guides/deployment-workflow.md) - Full deployment procedures
- [Architecture Guide](../../docs/deployment/guides/architecture.md) - System architecture
- [Deploy TODO Tracking](../../docs/deploy-todo-tracking.md) - Implementation checklist
