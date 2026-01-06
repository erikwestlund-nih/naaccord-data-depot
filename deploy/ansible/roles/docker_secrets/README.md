# Docker Secrets Role

## Purpose

Manages Docker secret files on the host system from Ansible vault variables. Secrets are stored in `/var/lib/docker/secrets/` and mounted into containers via Docker Compose.

## Security

- All secret files owned by root with mode 0600
- Secrets stored in `/var/lib/docker/secrets/` (not in tmpfs, but protected by filesystem permissions)
- No logging of secret contents (no_log: true)
- Secrets directory has mode 0700 (only root can list)

## Secrets Created

### All Servers
- `db_password` - Database application user password
- `django_secret_key` - Django session/CSRF secret
- `internal_api_key` - Web-to-services API authentication
- `wg_preshared_key` - WireGuard tunnel preshared key

### Web Server Only
- `wg_web_private_key` - WireGuard client private key
- `wg_web_public_key` - WireGuard client public key

### Services Server Only
- `redis_password` - Redis authentication password
- `wg_services_private_key` - WireGuard server private key
- `wg_services_public_key` - WireGuard server public key

## Usage

```yaml
roles:
  - docker_secrets
```

## Tags

- `docker` - All Docker-related tasks
- `secrets` - Secret management tasks
- `database` - Database secrets only
- `django` - Django secrets only
- `api` - API key secrets only
- `redis` - Redis secrets only
- `wireguard` - WireGuard secrets only
- `verify` - Verification tasks only

## Rotation

To rotate a secret:

1. Update the vault variable
2. Re-run the playbook with specific tags:
   ```bash
   ansible-playbook playbooks/services-server.yml --tags secrets,<specific-tag>
   ```
3. Restart affected containers:
   ```bash
   docker restart naaccord-services naaccord-celery
   ```

## Verification

After running this role, verify secrets were created:

```bash
sudo ls -la /var/lib/docker/secrets/
```

All files should be owned by root with mode 0600.
