# NAS Mount Role

## Overview

Configures NAS (Network Attached Storage) mount for NA-ACCORD PHI file storage. Mounts CIFS/SMB share at `/mnt/nas` for persistent storage of clinical data submissions.

## Purpose

NA-ACCORD stores all clinical data submissions on a dedicated NAS to ensure:
- Data persistence across server upgrades
- Centralized backup management
- HIPAA-compliant storage isolation
- Separation from application server storage

## What It Does

1. Installs `cifs-utils` package for CIFS/SMB mounting
2. Creates `/mnt/nas` mount point directory
3. Mounts NAS share using credentials from vault
4. Adds mount to `/etc/fstab` for persistence across reboots
5. Creates credentials file at `/root/.nas_credentials` (mode 0600)

## Requirements

- Root/sudo access
- CIFS-compatible NAS server accessible from services server
- Vault-encrypted credentials (nas_username, nas_password)

## Variables

### Required (from vault)
- `nas_username` - NAS authentication username
- `nas_password` - NAS authentication password

### Optional (with defaults)
- `nas_host` - NAS server IP/hostname (default: from inventory)
- `nas_share` - Share name to mount (default: from inventory)
- `nas_mount_point` - Local mount path (default: `/mnt/nas`)
- `nas_mount_options` - Mount options (default: `rw,vers=3.0,uid=1000,gid=1000,file_mode=0644,dir_mode=0755`)

## Dependencies

None

## Usage

Applied automatically by `playbooks/services-server.yml`.

Can also be run standalone:
```bash
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --tags nas \
  --ask-vault-pass
```

## Vault Configuration

Credentials must be stored in encrypted vault file at:
- `inventories/staging/group_vars/vault.yml` (staging)
- `inventories/production/group_vars/vault.yml` (production)

Example vault contents:
```yaml
---
nas_username: "naaccord_user"
nas_password: "secure_password_here"
```

Create/edit vault:
```bash
ansible-vault create inventories/staging/group_vars/vault.yml
ansible-vault edit inventories/staging/group_vars/vault.yml
```

## Graceful Degradation

If vault credentials are not provided (`nas_username` or `nas_password` empty):
- Role will skip mount operations
- Display informational message about missing credentials
- Won't fail the playbook
- Mount can be configured later when credentials are available

## Implementation Notes

- Uses `ansible.posix.mount` module for reliable mounting
- Credentials stored securely in `/root/.nas_credentials` (not in fstab)
- Checks if already mounted before attempting mount
- Idempotent - can run multiple times safely
- No handlers needed - mount operations are immediate

## Security

- Credentials encrypted with ansible-vault
- Credentials file mode 0600 (root only)
- Uses `no_log: true` for credential operations
- Credentials never logged or displayed in output
- CIFS authentication required for mount access

## Troubleshooting

**Mount fails:**
```bash
# Check NAS connectivity
ping <nas_host>

# Check CIFS utilities installed
rpm -q cifs-utils

# Verify credentials
ansible-vault view inventories/staging/group_vars/vault.yml

# Test manual mount
sudo mount -t cifs //192.168.1.10/submissions /mnt/nas \
  -o credentials=/root/.nas_credentials
```

**Check mount status:**
```bash
mount | grep nas
df -h /mnt/nas
ls -la /mnt/nas
```
