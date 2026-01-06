# NA-ACCORD Shell Aliases Reference

**Automatically deployed to all NA-ACCORD servers via Ansible.**

Shell aliases are configured via the `base` Ansible role and automatically available to all users after login.

## Quick Start

When you SSH to a NA-ACCORD server, you'll see this message:

```
🚀 NA-ACCORD Quick Commands:
  deployna      - Deploy latest code and restart containers
  narefresh     - Refresh shell aliases after deployment
  nahelp        - Show all NA-ACCORD aliases
  cdna          - Navigate to /opt/naaccord/depot
  nalogs        - View all container logs
  nastatus      - Show container status

Run 'nahelp' to see all available aliases.
```

## Primary Deployment Commands

### `deployna`
**Deploy latest code and restart all containers**

```bash
deployna
```

This single command:
1. Auto-detects environment from `/etc/naaccord/environment`
2. Pulls latest code from git (correct branch for environment)
3. Pulls latest Docker images from registry
4. Stops and restarts all containers
5. Runs Django migrations
6. Copies static files to container volumes
7. Updates shell aliases
8. Verifies container health

**Environment-specific behavior:**
- **Staging**: Uses `deploy` branch
- **Production**: Uses `main` branch

### `narefresh`
**Refresh shell aliases after deployment**

```bash
narefresh
```

Use this after `deployna` to reload aliases in your current shell session without logging out.

## Navigation Aliases

| Alias | Command | Description |
|-------|---------|-------------|
| `cdna` | `cd /opt/naaccord/depot` | Navigate to NA-ACCORD repository root |
| `cdnadeploy` | `cd /opt/naaccord/depot/deploy/ansible` | Navigate to Ansible directory |
| `cdnalogs` | `cd /opt/naaccord/depot && docker compose logs -f` | Navigate to repo and tail logs |

## Docker Management Aliases

| Alias | Command | Description |
|-------|---------|-------------|
| `nalogs` | `docker compose logs -f` | Tail all container logs |
| `narestart` | `docker compose restart` | Restart all containers |
| `nastatus` | `docker compose ps` | Show container status |
| `nahealth` | `curl http://localhost:8000/health/` | Check Django health endpoint |

## Container-Specific Logs

| Alias | Description |
|-------|-------------|
| `nalogs-web` | Tail Django web container logs |
| `nalogs-services` | Tail Django services container logs |
| `nalogs-celery` | Tail Celery worker logs |
| `nalogs-nginx` | Tail Nginx logs |

## Git Shortcuts

| Alias | Command | Description |
|-------|---------|-------------|
| `nagit` | `cd /opt/naaccord/depot && git status` | Show git status |
| `napull` | `cd /opt/naaccord/depot && git pull` | Pull latest code (correct branch) |

## Ansible Deployment Aliases

| Alias | Description |
|-------|-------------|
| `nadeploy-web` | Run full web server Ansible playbook |
| `nadeploy-services` | Run full services server Ansible playbook |

**Note:** These run the FULL server setup playbooks. For quick deployments, use `deployna` instead.

## Help Command

| Alias | Description |
|-------|-------------|
| `nahelp` | Show all available aliases |

## How Aliases are Deployed

Aliases are automatically configured via Ansible:

```bash
# Aliases are deployed when running server playbooks
ansible-playbook -i inventories/staging/hosts.yml playbooks/web-server.yml --connection local

# Or when running just the aliases tag
ansible-playbook -i inventories/staging/hosts.yml playbooks/web-server.yml --connection local --tags aliases
```

**Files created:**
- `/etc/profile.d/naaccord-aliases.sh` - Alias definitions (sourced on login)
- `/etc/motd` - Message of the day with quick reference

## Customization

To add or modify aliases:

1. Edit `deploy/ansible/roles/base/tasks/aliases.yml`
2. Commit changes to git
3. Re-run the playbook with `--tags aliases`

**Example:**
```bash
# After editing aliases.yml
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags aliases
```

## Troubleshooting

### Aliases not available after login

**Problem:** Aliases don't work after SSH

**Solution:**
```bash
# Use the refresh command
narefresh

# Or manually source the aliases
source /etc/profile.d/naaccord-aliases.sh

# Or logout and login again
exit
ssh user@server
```

### Aliases not updated after deployment

**Problem:** Ran `deployna` but aliases haven't changed

**Solution:**
```bash
# Use the refresh command
narefresh

# This is the same as:
# source /etc/profile.d/naaccord-aliases.sh
```

### Aliases not updated after Ansible run

**Problem:** Changed aliases but they don't appear

**Solution:**
```bash
# Use the refresh command
narefresh

# Or start a new shell session
bash -l
```

### Wrong environment or branch in deployna

**Problem:** `deployna` uses wrong environment/branch

**Solution:** Re-run Ansible to regenerate with correct inventory variables:
```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging \
  --tags aliases
```

## Examples

### Deploy fresh code
```bash
# One command deployment
deployna

# Refresh aliases in current shell
narefresh
```

### Check application health
```bash
# View all container logs
nalogs

# Check specific service
nalogs-celery

# Check health endpoint
nahealth
```

### Navigate and check git status
```bash
# Navigate to repo
cdna

# Check git status
nagit

# Pull latest
napull
```

### Restart services after manual changes
```bash
# Restart all containers
narestart

# Check they're running
nastatus
```

## Related Documentation

- [Deployment Scripts](../scripts/README.md) - Bootstrap and deployment scripts
- [Deployment Steps](../deploy-steps.md) - Full deployment workflow
- [Deployment Workflow](../../docs/deployment/guides/deployment-workflow.md) - Deployment procedures
