# NA-ACCORD Ansible Automation

Infrastructure-as-code for deploying NA-ACCORD's PHI-compliant two-server architecture.

## Quick Start

**Staging (Local Development):**
```bash
cd /opt/naaccord/depot/deploy/ansible

# Services server
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")

# Web server
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")
```

**Production (JHU Servers):**
```bash
# ⚠️ FIRST: Read VAULT-PRODUCTION.md to secure vault!

# SSH to target server, then:
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

## 📚 Documentation

### Start Here
- **[VAULT-PRODUCTION.md](VAULT-PRODUCTION.md)** - ⚠️ **MUST READ before production deployment**
- **[inventories/staging/README.md](inventories/staging/README.md)** - Staging environment guide
- **[inventories/production/README.md](inventories/production/README.md)** - Production deployment checklist

### Role Documentation
- [roles/base/README.md](roles/base/README.md) - System setup, users, Docker
- [roles/firewall/README.md](roles/firewall/README.md) - Port restrictions (coming soon)
- [roles/hosts_management/README.md](roles/hosts_management/README.md) - WireGuard /etc/hosts
- [roles/nas_mount/README.md](roles/nas_mount/README.md) - NAS storage configuration

### Deploy Guides
- [../deploy-steps.md](../deploy-steps.md) - Step-by-step deployment procedure
- [../CLAUDE.md](../CLAUDE.md) - Deploy domain overview

## 🏗️ Architecture

### Two-Server PHI-Compliant Design

```
Web Server                          Services Server
┌──────────────────────┐           ┌────────────────────────────┐
│ 10.150.96.6          │           │ 10.150.96.37               │
│ (web.naaccord.lan)   │           │ (services.naaccord.lan)    │
│                      │           │                            │
│ Nginx + Django Web   │           │ Django Services + Celery   │
│ WireGuard Client ────┼──Tunnel──┤ WireGuard Server          │
│ (10.100.0.10)        │  Encrypted│ (10.100.0.11)             │
│                      │           │                            │
│ No PHI Storage       │           │ MariaDB (encrypted)        │
│                      │           │ Redis (encrypted volume)   │
│                      │           │ NAS Mount (/mnt/nas)       │
└──────────────────────┘           └────────────────────────────┘
```

## 📁 Directory Structure

```
ansible/
├── README.md                      # This file
├── VAULT-PRODUCTION.md            # ⚠️ Production vault security guide
├── ansible.cfg                    # Ansible configuration
├── inventories/
│   ├── staging/
│   │   ├── README.md              # Staging guide
│   │   ├── hosts.yml              # Staging inventory
│   │   └── group_vars/
│   │       └── vault.yml          # Encrypted (password: changeme)
│   └── production/
│       ├── README.md              # ⚠️ Production checklist
│       ├── hosts.yml              # Production inventory
│       └── group_vars/
│           └── vault.yml          # Encrypted (CHANGE PASSWORD!)
├── playbooks/
│   ├── services-server.yml        # Phase 1 services setup
│   └── web-server.yml             # Phase 1 web setup
└── roles/
    ├── base/                      # System config, Docker, users
    ├── firewall/                  # Port restrictions (firewalld)
    ├── hosts_management/          # WireGuard /etc/hosts entries
    └── nas_mount/                 # NAS storage mounting
```

## 🎯 Current Phase: Phase 1 Complete

**Phase 1 Roles (Complete):**
- ✅ `base` - System setup, packages, Docker, zsh, users
- ✅ `firewall` - Port restrictions with firewalld
- ✅ `hosts_management` - WireGuard tunnel /etc/hosts entries
- ✅ `nas_mount` - NAS storage configuration

**Next Phases:**
- Phase 2: Dockerfiles and build workflow
- Phase 3: Services infrastructure (MariaDB, Redis, WireGuard)
- Phase 4: Services applications (Django, Celery, Flower)
- Phase 5: Web server (Nginx, Django web, WireGuard client)
- Phase 6: Logging (Loki, Grafana)
- Phase 7: Deployment automation
- Phase 8: Monitoring and alerting

See [../../docs/deploy-todo-tracking.md](../../docs/deploy-todo-tracking.md) for complete roadmap.

## 🔐 Vault Management

### Staging (Local Development)
- **Password:** `changeme` (intentionally weak for testing)
- **Credentials:** Test credentials for local NAS
- **Safe to:** Share password, run repeatedly, experiment

### Production (JHU Servers)
- **Password:** ⚠️ **MUST CHANGE from `changeme`**
- **Credentials:** Real NAS credentials from JHU IT
- **Required:** Strong password (20+ chars), password manager storage
- **See:** [VAULT-PRODUCTION.md](VAULT-PRODUCTION.md) for complete guide

**⚠️ NEVER use staging password in production!**

## 🚀 Running Playbooks

### Full Server Setup
```bash
# Services server (includes NAS mount)
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")

# Web server (no NAS mount)
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")
```

### Run Specific Role (Tags)
```bash
# Only firewall
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --tags firewall \
  --vault-password-file=<(echo "changeme")

# Only NAS mount
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --tags nas \
  --ask-vault-pass
```

### Dry Run (Check Mode)
```bash
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --check \
  --vault-password-file=<(echo "changeme")
```

### Verbose Output (Debugging)
```bash
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  -vvv \
  --vault-password-file=<(echo "changeme")
```

## 🔧 Common Operations

### View Vault Contents
```bash
# Staging
echo "changeme" | ansible-vault view inventories/staging/group_vars/vault.yml --vault-password-file=/dev/stdin

# Production (will prompt for password)
ansible-vault view inventories/production/group_vars/vault.yml
```

### Edit Vault
```bash
# Staging
echo "changeme" | ansible-vault edit inventories/staging/group_vars/vault.yml --vault-password-file=/dev/stdin

# Production
ansible-vault edit inventories/production/group_vars/vault.yml --ask-vault-pass
```

### Change Vault Password
```bash
# Production: Change from 'changeme' to strong password
ansible-vault rekey inventories/production/group_vars/vault.yml
# Current password: changeme
# New password: <STRONG_PASSWORD>
# Confirm: <STRONG_PASSWORD>
```

### List Inventory
```bash
ansible-inventory -i inventories/staging/hosts.yml --list
ansible-inventory -i inventories/staging/hosts.yml --graph
```

## ✅ Pre-Production Checklist

Before deploying to production servers, verify:

- [ ] Read [VAULT-PRODUCTION.md](VAULT-PRODUCTION.md) completely
- [ ] Changed production vault password from `changeme`
- [ ] Stored vault password in enterprise password manager
- [ ] Obtained real NAS credentials from JHU IT
- [ ] Updated production vault with real credentials
- [ ] Updated production hosts.yml (no TBD values)
- [ ] Tested VPN + SSH access to JHU servers
- [ ] Confirmed firewall rules with JHU IT
- [ ] Documented who has vault password access
- [ ] Reviewed emergency access procedures

## 🆘 Troubleshooting

### "Vault password incorrect"
- Staging uses `changeme`
- Production uses strong password (check password manager)
- No extra spaces or newlines in password

### "Role not found"
- Verify you're in `/opt/naaccord/depot/deploy/ansible/` directory
- Check `ansible.cfg` has correct `roles_path = ./roles`
- Ensure role directory exists: `ls -la roles/`

### "Connection refused" (SSH)
- For local: Use `--connection local`
- For remote: Verify SSH access and VPN connection
- Check inventory has correct IP addresses

### "NAS mount failed"
- Vault credentials may be empty (check with `ansible-vault view`)
- Verify NAS connectivity: `ping <nas_host>`
- Check credentials with JHU IT
- Review role README: [roles/nas_mount/README.md](roles/nas_mount/README.md)

### "Permission denied"
- Most tasks require `become: yes` (sudo)
- Verify user has sudo access on target server
- Check SSH key authentication is working

## 📞 Support

**For deployment issues:**
1. Check role-specific README in `roles/<role_name>/README.md`
2. Review playbook output for specific errors
3. See [../../docs/deployment/guides/emergency-access.md](../../docs/deployment/guides/emergency-access.md)

**For vault issues:**
1. See [VAULT-PRODUCTION.md](VAULT-PRODUCTION.md)
2. Test password: `ansible-vault view <vault_file>`
3. Emergency: Recreate vault with new credentials from JHU IT

**For infrastructure issues:**
1. Contact JHU IT (for production servers/NAS)
2. Check network connectivity (VPN, firewall rules)
3. Review [../deploy-steps.md](../deploy-steps.md)
