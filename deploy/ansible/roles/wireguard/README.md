# WireGuard Role

## Purpose

Verifies and hardens WireGuard VPN tunnel configuration for PHI-compliant communication between web and services servers.

## Features

### Verification (All Servers)
- Verifies WireGuard kernel module loaded
- Checks `/dev/net/tun` device exists
- Waits for WireGuard container health
- Tests tunnel connectivity with ping

### Hardening (Web Server Only)
- **Policy Routing:** Forces all traffic to services server (10.100.0.11) through WireGuard tunnel
- **Firewall Rules:** Restricts tunnel traffic to only required ports (3306, 6379, 8001)
- **Defense in Depth:** Multiple layers prevent accidental PHI leakage outside tunnel

## Architecture

### WireGuard Tunnel
```
Web Server (10.100.0.10)  <--[Encrypted]-->  Services Server (10.100.0.11)
         |                                              |
    WireGuard Container                           WireGuard Container
    (ChaCha20-Poly1305)                          (ChaCha20-Poly1305)
         |                                              |
    Docker Network                                Docker Network
```

### Allowed Services Through Tunnel
- **Port 3306:** MariaDB (database access)
- **Port 6379:** Redis (cache access)
- **Port 8001:** Django Services API

All other ports are blocked at the firewall level inside the WireGuard container.

## Policy Routing

On web server, traffic to `10.100.0.11` (services server) is forced through custom routing table:

```bash
# Routing rule
ip rule add to 10.100.0.11 lookup wireguard priority 100

# Route in custom table
ip route add 10.100.0.11 dev docker0 table wireguard
```

This prevents accidental bypass of the encrypted tunnel.

## Firewall Hardening

WireGuard container uses nftables to restrict forwarded traffic:

```bash
# Only allow specific ports
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 3306 accept  # MariaDB
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 6379 accept  # Redis
nft add rule inet filter forward ip daddr 10.100.0.11 tcp dport 8001 accept  # Django

# Drop everything else
nft add chain inet filter forward '{ type filter hook forward priority 0; policy drop; }'
```

## Usage

```yaml
roles:
  - wireguard
```

## Tags

- `wireguard` - All WireGuard tasks
- `network` - Network configuration
- `verify` - Verification tasks
- `hardening` - Security hardening tasks
- `routing` - Policy routing tasks
- `firewall` - Firewall rules tasks

## Verification

After running this role:

```bash
# Check tunnel status
docker exec naaccord-wireguard-web wg show

# Check policy routing
sudo ip rule list | grep wireguard
sudo ip route show table wireguard

# Test connectivity
docker exec naaccord-wireguard-web ping -c 3 10.100.0.11
```

## WireGuard Key Management

Keys are stored in Ansible vault and deployed as Docker secrets:

```yaml
# In vault.yml
vault_wg_web_private_key: "..."
vault_wg_web_public_key: "..."
vault_wg_services_private_key: "..."
vault_wg_services_public_key: "..."
vault_wg_preshared_key: "..."
```

### Key Rotation

To rotate WireGuard keys:

1. Generate new keys on both servers:
   ```bash
   wg genkey | tee private.key | wg pubkey > public.key
   wg genpsk > preshared.key
   ```

2. Update vault variables:
   ```bash
   ansible-vault edit inventories/production/group_vars/all/vault.yml
   ```

3. Deploy new secrets:
   ```bash
   ansible-playbook playbooks/web-server.yml --tags docker_secrets,wireguard
   ansible-playbook playbooks/services-server.yml --tags docker_secrets,wireguard
   ```

4. Restart WireGuard containers (brief outage ~30-60 seconds):
   ```bash
   # On web server
   docker restart naaccord-wireguard-web

   # On services server
   docker restart naaccord-wireguard-services
   ```

5. Verify tunnel:
   ```bash
   docker exec naaccord-wireguard-web ping -c 3 10.100.0.11
   ```

**Rotation Frequency:** Every 365 days (annual)

## Troubleshooting

### Tunnel Not Working

```bash
# Check container status
docker ps | grep wireguard

# Check container logs
docker logs naaccord-wireguard-web

# Verify secrets exist
sudo ls -l /var/lib/docker/secrets/wg_*

# Check kernel module
lsmod | grep wireguard

# Check routing
ip route show
ip rule list
```

### Policy Routing Not Working

```bash
# Check systemd service
sudo systemctl status wireguard-policy-routing

# Manually apply routing
sudo /opt/naaccord/scripts/wireguard-policy-routing.sh

# Verify rules
sudo ip rule list | grep wireguard
sudo ip route show table wireguard
```

## Security Notes

- **Encryption:** ChaCha20-Poly1305 (modern, fast, secure)
- **Preshared Key:** Additional quantum-resistant layer
- **Peer Authentication:** Public key cryptography prevents man-in-the-middle
- **Traffic Restriction:** Firewall ensures only required ports accessible
- **No Bypass:** Policy routing prevents accidental cleartext communication
