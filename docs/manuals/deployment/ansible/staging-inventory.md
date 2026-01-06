# Staging Inventory

## Quick Start

Staging uses local VMs with test credentials - safe for development and testing.

**Run services server playbook:**
```bash
cd /opt/naaccord/depot/deploy/ansible

ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")
```

## Staging Environment Details

**Services Server:**
- Hostname: `services.naaccord.lan`
- IP: `192.168.50.11`
- WireGuard Tunnel IP: `10.100.0.11`
- Access: Local network (no VPN needed)

**Web Server:**
- Hostname: `web.naaccord.lan`
- IP: `192.168.50.10`
- WireGuard Tunnel IP: `10.100.0.10`
- Access: Local network (no VPN needed)
- Public URL: `naaccord.pequod.sh` (Cloudflare DNS)

**NAS:**
- IP: `192.168.1.10`
- Share: `submissions`
- Credentials: Test credentials in vault (username: `staging_user`)

## Vault Password

**Staging vault password: `changeme`**

This is intentionally weak for ease of testing. **Never use this password in production!**

**View vault contents:**
```bash
echo "changeme" | ansible-vault view inventories/staging/group_vars/vault.yml --vault-password-file=/dev/stdin
```

**Edit vault:**
```bash
echo "changeme" | ansible-vault edit inventories/staging/group_vars/vault.yml --vault-password-file=/dev/stdin
```

## Testing Playbooks

**Test all Phase 1 roles on services server:**
```bash
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=<(echo "changeme")
```

**Test specific role with tags:**
```bash
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --tags firewall \
  --vault-password-file=<(echo "changeme")
```

**Dry run (check mode):**
```bash
ansible-playbook \
  -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --check \
  --vault-password-file=<(echo "changeme")
```

## Staging vs Production

| Aspect | Staging | Production |
|--------|---------|------------|
| Vault Password | `changeme` | Strong password (20+ chars) |
| NAS Credentials | Test credentials | Real credentials from JHU IT |
| Network | Local VMs (192.168.50.x) | JHU network (10.150.96.x) |
| Access | No VPN needed | Requires JHU VPN |
| Domain | naaccord.pequod.sh | mrpznaaccordweb01.hosts.jhmi.edu |
| SAML | Mock-idp container | JHU Shibboleth |
| Data | Test/simulated data | Real PHI data |

## Vault Contents

Current staging vault contains:
```yaml
---
nas_username: "staging_user"
nas_password: "staging_password"
```

These are test credentials for local NAS testing.

## Safe for Testing

- ✅ Safe to run repeatedly
- ✅ Safe to experiment with
- ✅ Safe to share vault password with team
- ✅ Safe to commit vault file (it's encrypted)
- ✅ Safe to use weak password (staging only)

**Production is different!** See [../production/README.md](../production/README.md) for production requirements.
