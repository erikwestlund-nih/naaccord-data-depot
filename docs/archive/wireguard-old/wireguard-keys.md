# WireGuard Key Generation for Ansible

## ⚠️ CRITICAL: Public Key Generation

**WireGuard public keys MUST be mathematically derived from private keys.** You cannot generate them independently.

## Key Generation Process

### 1. Generate Private Keys

```bash
# Web server private key
wg genkey > web-private.key

# Services server private key
wg genkey > services-private.key

# Preshared key (optional but recommended for post-quantum security)
wg genpsk > preshared.key
```

### 2. Derive Public Keys from Private Keys

```bash
# Web server public key (derived from web private key)
cat web-private.key | wg pubkey > web-public.key

# Services server public key (derived from services private key)
cat services-private.key | wg pubkey > services-public.key
```

### 3. Verify Key Pairs

```bash
# Verify web keys match
echo "Web private:" && cat web-private.key
echo "Web public (should match derived):" && cat web-private.key | wg pubkey
echo "Web public (from file):" && cat web-public.key

# Verify services keys match
echo "Services private:" && cat services-private.key
echo "Services public (should match derived):" && cat services-private.key | wg pubkey
echo "Services public (from file):" && cat services-public.key
```

## Ansible Vault Configuration

After generating keys, add them to Ansible vault:

### inventories/production/group_vars/vault.yml

```yaml
# WireGuard Keys (PHI Tunnel Encryption)
# CRITICAL: Public keys must be derived from private keys using 'wg pubkey'

# Web server keys
vault_wg_web_private_key: "<contents of web-private.key>"
vault_wg_web_public_key: "<contents of web-public.key>"

# Services server keys
vault_wg_services_private_key: "<contents of services-private.key>"
vault_wg_services_public_key: "<contents of services-public.key>"

# Preshared key (shared between both peers for post-quantum security)
vault_wg_preshared_key: "<contents of preshared.key>"
```

### Encrypt the vault:

```bash
ansible-vault encrypt inventories/production/group_vars/vault.yml
```

## Common Mistakes to Avoid

### ❌ WRONG: Generating public keys independently
```bash
# DON'T DO THIS
wg genkey > web-private.key
wg genkey > web-public.key   # ❌ This creates a DIFFERENT keypair!
```

### ✅ CORRECT: Deriving public from private
```bash
# DO THIS
wg genkey > web-private.key
cat web-private.key | wg pubkey > web-public.key   # ✅ Correctly derived
```

## Troubleshooting

### Tunnel handshake fails (0 B received)

**Symptom:** `wg show` reports `transfer: 0 B received` and handshake timestamp is `0`

**Cause:** Public key mismatch - the peer's public key doesn't match their private key

**Solution:**
1. Regenerate public keys from existing private keys:
   ```bash
   cat web-private.key | wg pubkey > web-public.key
   cat services-private.key | wg pubkey > services-public.key
   ```
2. Update Ansible vault with correct public keys
3. Redeploy containers

### Verifying deployed keys

```bash
# On running container - check configured peer public key
docker exec wireguard-web wg show wg0 peers

# Compare to what should be configured (services public key)
cat services-public.key

# If they don't match, public keys were not correctly derived
```

## WireGuard Configuration in docker-compose.prod.yml

### Web Server (Client)
```yaml
wireguard-web:
  environment:
    - WG_PRIVATE_KEY_FILE=/run/secrets/wg_web_private_key
    - WG_PEER_PUBLIC_KEY_FILE=/run/secrets/wg_services_public_key  # ← Services PUBLIC key
    - WG_PRESHARED_KEY_FILE=/run/secrets/wg_preshared_key
    - WG_TUNNEL_ADDRESS=10.100.0.10/24
    - WG_PEER_ADDRESS=10.100.0.11
    - WG_PEER_ENDPOINT=${SERVICES_SERVER_HOST}:51820
```

### Services Server
```yaml
wireguard-services:
  environment:
    - WG_PRIVATE_KEY_FILE=/run/secrets/wg_services_private_key
    - WG_PEER_PUBLIC_KEY_FILE=/run/secrets/wg_web_public_key  # ← Web PUBLIC key
    - WG_PRESHARED_KEY_FILE=/run/secrets/wg_preshared_key
    - WG_TUNNEL_ADDRESS=10.100.0.11/24
    - WG_PEER_ADDRESS=10.100.0.10
    - WG_FORWARD_PORTS=3306:tcp:10.101.0.2 6379:tcp:10.101.0.4 8001:tcp:10.101.0.5
```

## Security Notes

1. **Never commit unencrypted keys to git**
2. **Development keys** in `deploy/configs/wireguard/dev/` are for local testing only
3. **Production keys** must be:
   - Generated on secure workstation
   - Stored in encrypted Ansible vault
   - Never logged or displayed
   - Rotated periodically (every 6-12 months)

4. **Preshared keys** provide post-quantum security layer
   - Optional but highly recommended for PHI data
   - Shared secret known only to both peers
   - Adds cryptographic agility

## References

- [WireGuard Quick Start](https://www.wireguard.com/quickstart/)
- [WireGuard Key Generation](https://www.wireguard.com/quickstart/#key-generation)
- [Post-Quantum Preshared Keys](https://www.wireguard.com/papers/wireguard.pdf)
