# Production Inventory

## ⚠️ BEFORE USING THIS INVENTORY

### 1. Change Vault Password

The production vault currently uses the **staging password `changeme`** - this MUST be changed:

```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-vault rekey inventories/production/group_vars/vault.yml

# Current password: changeme
# New password: <STRONG_PRODUCTION_PASSWORD>
```

**See [../../VAULT-PRODUCTION.md](../../VAULT-PRODUCTION.md) for complete vault security guide.**

### 2. Get NAS Credentials from JHU IT

Contact JHU IT to obtain:
- NAS server IP address or hostname
- NAS share name
- NAS username
- NAS password

### 3. Update Vault with Real Credentials

```bash
ansible-vault edit inventories/production/group_vars/vault.yml
# Enter NEW production vault password

# Update contents:
---
nas_username: "actual_username_from_jhu"
nas_password: "actual_password_from_jhu"
```

### 4. Update hosts.yml with NAS Details

Edit `hosts.yml` and replace `TBD` values:
```yaml
vars:
  nas_host: "10.150.96.XX"  # From JHU IT
  nas_share: "naaccord_submissions"  # From JHU IT
```

## Production Environment Details

**Services Server:**
- Hostname: `mrpznaaccorddb01.hosts.jhmi.edu`
- IP: `10.150.96.37`
- WireGuard Tunnel IP: `10.100.0.11`
- Access: Via JHU VPN + SSH key

**Web Server:**
- Hostname: `mrpznaaccordweb01.hosts.jhmi.edu`
- IP: `10.150.96.6`
- WireGuard Tunnel IP: `10.100.0.10`
- Access: Via JHU VPN + SSH key
- Public URL: `mrpznaaccordweb01.hosts.jhmi.edu`

## Deployment to Production

**From your local machine (with VPN connected):**

```bash
# SSH to services server
ssh user@10.150.96.37

# Navigate to repository
cd /opt/naaccord/depot/deploy/ansible

# Pull latest code
git pull origin main

# Run services server playbook
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass

# Enter production vault password when prompted
```

**For web server, SSH to web server (10.150.96.6) and run:**
```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass
```

## Security Checklist

Before deploying to production, verify:

- [ ] Vault password changed from `changeme` to strong password
- [ ] Vault password stored in enterprise password manager
- [ ] Real NAS credentials obtained from JHU IT
- [ ] Vault updated with real NAS credentials
- [ ] hosts.yml updated with real NAS details (no TBD values)
- [ ] Network connectivity tested (VPN + SSH access)
- [ ] Firewall rules confirmed with JHU IT
- [ ] Backup procedures documented
- [ ] Team members know who has vault password access

## Emergency Contacts

**If deployment fails:**
1. Check [../../../docs/deployment/guides/emergency-access.md](../../../docs/deployment/guides/emergency-access.md)
2. Contact JHU IT for infrastructure issues
3. Review Ansible logs: `less /var/log/ansible.log`

**If vault password is lost:**
1. See [../../VAULT-PRODUCTION.md](../../VAULT-PRODUCTION.md) - Emergency Access section
2. Contact JHU IT for new NAS credentials
3. Recreate vault with new password and credentials
