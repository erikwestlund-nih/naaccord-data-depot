# Production Inventory Configuration Guide

This guide explains what needs to be configured in `production/hosts.yml` and `production/group_vars/all/vault.yml` for the production deployment.

## 🔧 Required Configuration Changes from Staging

### 1. **WireGuard IPs** (inventories/production/hosts.yml)

**Staging Configuration:**
```yaml
services:
  hosts:
    services.naaccord.lan:
      ansible_host: 192.168.50.11
      wireguard_ip: 10.100.0.11  # ← Production: Keep same (tunnel IP)

web:
  hosts:
    web.naaccord.lan:
      ansible_host: 192.168.50.10
      wireguard_ip: 10.100.0.10  # ← Production: Keep same (tunnel IP)
```

**Production Configuration:**
```yaml
services:
  hosts:
    mrpznaaccordsvcs01.hosts.jhmi.edu:  # ← Change hostname
      ansible_host: 10.150.96.37         # ← Change to production IP
      wireguard_ip: 10.100.0.11          # ✓ Keep same (WireGuard tunnel IP)

web:
  hosts:
    mrpznaaccordweb01.hosts.jhmi.edu:   # ← Change hostname
      ansible_host: 10.150.96.6          # ← Change to production IP
      wireguard_ip: 10.100.0.10          # ✓ Keep same (WireGuard tunnel IP)
```

**Note:** WireGuard tunnel IPs (10.100.0.10 and 10.100.0.11) should remain the same across environments for consistency.

---

### 2. **Domain Name** (inventories/production/hosts.yml)

**Staging:**
```yaml
vars:
  domain: naaccord.pequod.sh  # ← Staging domain
```

**Production:**
```yaml
vars:
  domain: naaccord.jhsph.edu  # ← Production domain (update based on JHU DNS)
```

This domain is used for:
- Django `ALLOWED_HOSTS` setting
- SAML SP entity ID
- SAML ACS URL
- SSL certificate subject

---

### 3. **ALLOWED_HOSTS (Docker Container IPs)**

**⚠️ CRITICAL: Update after first deployment**

The `allowed_hosts_wireguard_docker` list in `roles/docker_services/defaults/main.yml` contains Docker container IPs on the `naaccord_wireguard` network (10.101.0.0/24).

**Current Staging IPs:**
```yaml
allowed_hosts_wireguard_docker:
  - 10.101.0.5   # Services container IP
  - 10.101.0.11  # Web container IP
```

**How to update for production:**

1. **After first deployment**, run on each server:
   ```bash
   # On services server:
   sudo docker inspect naaccord-services --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

   # On web server:
   sudo docker inspect naaccord-web --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
   ```

2. **Update the role defaults** with actual IPs:
   ```yaml
   # File: roles/docker_services/defaults/main.yml
   allowed_hosts_wireguard_docker:
     - <services-container-ip>   # From step 1, services server
     - <web-container-ip>         # From step 1, web server
   ```

3. **Alternative: Use wildcard** (less secure but simpler):
   ```yaml
   allowed_hosts_wireguard_docker:
     - 10.101.0.0/24  # Allow all IPs on wireguard docker network
   ```

   **Note:** Django doesn't support CIDR notation directly. Use individual IPs or ranges like `10.101.0.*` if your Django version supports it.

**Why this matters:**
- Services API at `http://10.101.0.5:8001/` must accept requests from web container
- Web container may access services via tunnel IP (10.100.0.11) or docker network IP (10.101.0.5)
- Incorrect ALLOWED_HOSTS causes HTTP 400 "Bad Request" errors

---

### 4. **NAS Configuration** (inventories/production/hosts.yml)

**Staging (Samba mount):**
```yaml
nas_type: samba
nas_host: 192.168.1.10
nas_share: NAAccord
nas_mount_point: /mnt/nas
nas_username: "{{ vault_nas_username }}"
nas_password: "{{ vault_nas_password }}"
```

**Production (Pre-mounted by IT):**
```yaml
nas_type: premounted  # ← IT will mount NAS before deployment
nas_mount_point: /mnt/nas  # ← Verify with IT what path they use
# nas_host, nas_share, nas_username, nas_password NOT needed for premounted
```

**Coordinate with JHU IT:**
- NAS mount path
- Permissions (naaccord user needs read/write)
- Subdirectories: `/mnt/nas/uploads`, `/mnt/nas/submissions`, `/mnt/nas/reports`

---

### 5. **SAML Configuration** (inventories/production/hosts.yml)

**Staging (Mock IDP):**
```yaml
saml_sp_entity_id: "https://{{ domain }}"
saml_sp_acs_url: "https://{{ domain }}/saml2/acs/"
saml_idp_metadata_url: "http://192.168.50.10:8080/simplesaml/saml2/idp/metadata.php"
saml_idp_base_url: "http://192.168.50.10:8080/simplesaml/"
```

**Production (JHU Shibboleth):**
```yaml
saml_sp_entity_id: "https://{{ domain }}"  # Keep same pattern
saml_sp_acs_url: "https://{{ domain }}/saml2/acs/"  # Keep same pattern
saml_idp_metadata_url: "https://idp.jhu.edu/idp/shibboleth"  # ← Get from JHU IT
saml_idp_base_url: ""  # Not needed for Shibboleth
```

**Coordinate with JHU IT:**
- IDP metadata URL
- Service Provider registration
- Attribute mapping (email, groups)

---

### 6. **SSL Configuration** (inventories/production/hosts.yml)

**Staging (NPM handles SSL):**
```yaml
ssl_provider: none
ssl_enabled: false
```

**Production (Let's Encrypt DNS-01):**
```yaml
ssl_provider: letsencrypt
ssl_acme_email: naaccord-admin@jhsph.edu  # ← Update
ssl_domains:
  - naaccord.jhsph.edu  # ← Update to match domain
```

**Cloudflare API Token Required:**
Add to `production/group_vars/all/vault.yml`:
```yaml
vault_cloudflare_api_token: "your-dns-token-here"
```

---

### 7. **Firewall Ports** (Auto-configured, verify only)

The Ansible playbook automatically configures these ports:

**Services Server:**
- `22/tcp` - SSH
- `51820/udp` - WireGuard tunnel

**Web Server:**
- `22/tcp` - SSH
- `443/tcp` - HTTPS
- `51820/udp` - WireGuard tunnel (client side)

**No changes needed** unless JHU IT has specific firewall requirements.

---

### 8. **Vault Secrets** (inventories/production/group_vars/all/vault.yml)

Create encrypted vault file with:
```bash
ansible-vault create inventories/production/group_vars/all/vault.yml
```

**Required secrets:**
```yaml
# Database passwords
vault_db_root_password: "<generate-secure-password>"
vault_db_app_password: "<generate-secure-password>"
vault_db_report_password: "<generate-secure-password>"
vault_db_backup_password: "<generate-secure-password>"

# Redis password
vault_redis_password: "<generate-secure-password>"

# MariaDB (aliases for compatibility)
vault_mariadb_root_password: "{{ vault_db_root_password }}"
vault_mariadb_app_password: "{{ vault_db_app_password }}"
vault_mariadb_report_password: "{{ vault_db_report_password }}"
vault_mariadb_backup_password: "{{ vault_db_backup_password }}"

# Django secret key (50+ chars random)
vault_django_secret_key: "<generate-50-char-random-string>"

# Internal API key (for web→services communication)
vault_internal_api_key: "<generate-secure-random-string>"

# WireGuard keys (generate with: wg genkey)
vault_wg_web_private_key: "<wg-genkey-output>"
vault_wg_web_public_key: "<wg-pubkey-from-private>"
vault_wg_services_private_key: "<wg-genkey-output>"
vault_wg_services_public_key: "<wg-pubkey-from-private>"
vault_wg_preshared_key: "<wg-genpsk-output>"

# NAS credentials (if nas_type=samba)
vault_nas_username: "naaccord"
vault_nas_password: "<nas-password-from-it>"

# GitHub Container Registry (for pulling images)
vault_ghcr_username: "naaccord-deploy"
vault_ghcr_token: "<github-personal-access-token>"

# Monitoring
vault_flower_password: "<generate-secure-password>"
vault_grafana_admin_password: "<generate-secure-password>"

# Cloudflare (for Let's Encrypt DNS-01)
vault_cloudflare_api_token: "<cloudflare-dns-token>"
```

**Generate secure passwords:**
```bash
# 32-char random passwords
openssl rand -base64 24

# 50-char Django secret key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# WireGuard keys
wg genkey | tee private.key | wg pubkey > public.key
wg genpsk > preshared.key
```

---

## 📋 Pre-Deployment Checklist

- [ ] Update `inventories/production/hosts.yml` with production IPs and hostnames
- [ ] Update `domain` variable to production domain
- [ ] Create `inventories/production/group_vars/all/vault.yml` with all secrets
- [ ] Coordinate with JHU IT for:
  - [ ] NAS mount path and permissions
  - [ ] Shibboleth IDP metadata URL
  - [ ] Firewall rules (ports 22, 443, 51820)
  - [ ] SSL certificate requirements
- [ ] Generate WireGuard keys and add to vault
- [ ] Generate all passwords and add to vault
- [ ] Test vault decryption: `ansible-vault view inventories/production/group_vars/all/vault.yml`

---

## 🚀 Deployment Commands

**Services Server:**
```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --ask-vault-pass
```

**Web Server:**
```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --connection local \
  --ask-vault-pass
```

**Post-Deployment:**
1. Verify container IPs on wireguard network
2. Update `allowed_hosts_wireguard_docker` if needed
3. Re-run deployment to apply updated ALLOWED_HOSTS

---

## 🔍 Verification

After deployment, verify on each server:

```bash
# Check containers
sudo docker ps --filter "name=naaccord"

# Check WireGuard tunnel
sudo docker exec naaccord-wireguard-services wg show  # On services
sudo docker exec naaccord-wireguard-web wg show       # On web

# Test tunnel connectivity
sudo docker exec naaccord-web curl -f http://10.100.0.11:8001/health/

# Check logs
sudo docker logs naaccord-services
sudo docker logs naaccord-web
```
