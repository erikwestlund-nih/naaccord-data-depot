# WireGuard VPN for PHI Data Encryption

**Complete guide to WireGuard implementation for NA-ACCORD's PHI-compliant architecture**

**Last Updated:** 2025-10-15

---

## Table of Contents
1. [Overview](#overview)
2. [Why WireGuard for NA-ACCORD](#why-wireguard-for-na-accord)
3. [Architecture](#architecture)
4. [Installation and Setup](#installation-and-setup)
5. [Key Generation](#key-generation)
6. [Configuration](#configuration)
7. [Docker Deployment](#docker-deployment)
8. [Testing and Verification](#testing-and-verification)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)
11. [Security Best Practices](#security-best-practices)

---

## Overview

WireGuard provides encrypted tunneling for all PHI data transfers between web and services containers, ensuring data is never transmitted unencrypted, even on internal infrastructure. This implementation uses ChaCha20-Poly1305 encryption with perfect forward secrecy.

### Key Benefits
- **Minimal overhead**: 2-5% vs 10-15% for TLS
- **High throughput**: 95-98% of baseline for streaming
- **Simple configuration**: No certificate management
- **Kernel-level operation**: Faster than userspace SSL
- **Perfect forward secrecy**: Key rotation doesn't compromise past data

---

## Why WireGuard for NA-ACCORD

### Performance Comparison for Streaming Data

| Method | Latency | Throughput | CPU Impact | Streaming Performance |
|--------|---------|------------|------------|-----------------------|
| Plain HTTP | 0ms | 100% | Baseline | ⭐⭐⭐⭐⭐ |
| **WireGuard** | **+0.3ms** | **95-98%** | **+2-5%** | **⭐⭐⭐⭐⭐** |
| TLS/HTTPS | +0.5-1ms | 85-95% | +5-10% | ⭐⭐⭐ |
| SSH Tunnel | +1-2ms | 70-85% | +10-15% | ⭐⭐ |

**WireGuard wins for streaming because:**
- Minimal latency impact (crucial for real-time data transfer)
- Maintains high throughput for large file transfers (40M rows/2GB files)
- Low CPU overhead leaves resources for R processing and DuckDB analytics
- Automatic reconnection handles network issues gracefully

### Security Advantages
1. **Small attack surface**: Only 4,000 lines of code (vs OpenSSL's 400,000+)
2. **Formally verified cryptography**: ChaCha20-Poly1305
3. **DDoS resistant**: Stateless design, no response to unauthenticated packets
4. **Minimal Attack Surface**: Services container not publicly accessible

---

## Architecture

### Data Flow Architecture

```
User → [Web Container:8000] → WireGuard Tunnel → [Services Container:8001] → Storage
         (Public Zone)         (Encrypted PHI)      (Secure Zone)
```

### Security Principles
1. **Zero Trust Network**: Even internal traffic is encrypted
2. **PHI Isolation**: Services container handles all PHI storage operations
3. **Streaming Architecture**: Large files stream through encrypted tunnel
4. **No Unencrypted PHI**: Data encrypted at rest and in transit

### Container Roles

#### Web Container (Public-facing)
- Handles authentication and authorization
- Receives file uploads from users
- **NEVER stores PHI data locally**
- Streams data immediately to services via WireGuard
- Returns presigned URLs for downloads

#### Services Container (PHI Handler)
- Receives data through WireGuard tunnel only
- Stores PHI data in secure storage (NAS/S3)
- Runs data processing tasks (R/Quarto, DuckDB)
- Generates audit reports
- Returns results through encrypted tunnel

#### WireGuard Containers
- **wireguard-web**: Tunnel endpoint for web container (10.100.0.10)
- **wireguard-services**: Tunnel endpoint for services container (10.100.0.11)
- Pre-shared keys for additional post-quantum security
- Network isolation with dedicated subnet

### Network Configuration

#### Development Environment
```yaml
# docker-compose.yml
networks:
  services-net:
    subnet: 10.101.0.0/24  # Services internal network
  tunnel-net:
    subnet: 172.20.0.0/24  # WireGuard container interconnect

# WireGuard Tunnel IPs:
# - Web: 10.100.0.10/24
# - Services: 10.100.0.11/24

# Services Network IPs:
# - MariaDB: 10.101.0.2
# - WireGuard-Services: 10.101.0.3
# - Redis: 10.101.0.4
# - Services container: 10.101.0.5
```

#### Production Environment
```yaml
# docker-compose.prod.yml
networks:
  wireguard:
    subnet: 10.101.0.0/24  # Changed from 10.100.0.0/24 to avoid conflict

# Two-server deployment:
# - Web server: 10.150.96.6
# - Services server: 10.150.96.37
```

---

## Installation and Setup

### 1. Install WireGuard

```bash
# macOS (for development)
brew install wireguard-tools

# Linux (for production)
sudo apt-get update
sudo apt-get install wireguard
```

### 2. Enable IP Forwarding (Linux)

```bash
# Enable IP forwarding
sudo sysctl -w net.ipv4.ip_forward=1

# Make permanent
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
```

---

## Key Generation

### ⚠️ CRITICAL: Public Key Generation

**WireGuard public keys MUST be mathematically derived from private keys.** You cannot generate them independently.

### Generate Keys for Development

```bash
#!/bin/bash
# Generate keys for development environment

# Create directory for keys
mkdir -p deploy/configs/wireguard/dev
cd deploy/configs/wireguard/dev

# Web server keys
wg genkey > web-private.key
cat web-private.key | wg pubkey > web-public.key

# Services server keys
wg genkey > services-private.key
cat services-private.key | wg pubkey > services-public.key

# Preshared key (optional but recommended for post-quantum security)
wg genpsk > preshared.key

# Secure the keys
chmod 600 *.key

echo "Keys generated:"
echo "Web Public: $(cat web-public.key)"
echo "Services Public: $(cat services-public.key)"
```

### Generate Keys for Production

```bash
#!/bin/bash
# Generate keys for production (encrypt with Ansible vault)

# Generate keys in secure location
mkdir -p /tmp/naaccord-wg-keys
cd /tmp/naaccord-wg-keys

# Web server keys
wg genkey > web-private.key
cat web-private.key | wg pubkey > web-public.key

# Services server keys
wg genkey > services-private.key
cat services-private.key | wg pubkey > services-public.key

# Preshared key
wg genpsk > preshared.key

# Display keys for vault
echo "Add these to Ansible vault (deploy/ansible/inventories/production/group_vars/vault.yml):"
echo ""
echo "vault_wg_web_private_key: $(cat web-private.key)"
echo "vault_wg_web_public_key: $(cat web-public.key)"
echo "vault_wg_services_private_key: $(cat services-private.key)"
echo "vault_wg_services_public_key: $(cat services-public.key)"
echo "vault_wg_preshared_key: $(cat preshared.key)"

# Clean up (IMPORTANT - don't leave keys on disk)
cd ..
rm -rf /tmp/naaccord-wg-keys
```

### Verify Key Pairs

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

### Common Mistakes to Avoid

#### ❌ WRONG: Generating public keys independently
```bash
# DON'T DO THIS
wg genkey > web-private.key
wg genkey > web-public.key   # ❌ This creates a DIFFERENT keypair!
```

#### ✅ CORRECT: Deriving public from private
```bash
# DO THIS
wg genkey > web-private.key
cat web-private.key | wg pubkey > web-public.key   # ✅ Correctly derived
```

---

## Configuration

### Web Server Interface

```ini
# /etc/wireguard/wg-web.conf (or via Docker secrets)
[Interface]
# Web server's private key
PrivateKey = <web-private-key>
# Virtual IP for web server
Address = 10.100.0.10/24
# Listen port
ListenPort = 51820
# Keep connection alive
PostUp = iptables -A FORWARD -i %i -j ACCEPT
PostDown = iptables -D FORWARD -i %i -j ACCEPT

[Peer]
# Services server's public key
PublicKey = <services-public-key>
# Optional preshared key for post-quantum security
PresharedKey = <preshared-key>
# Services server's virtual IP
AllowedIPs = 10.100.0.11/32
# Connect to services server
Endpoint = <services-server-ip>:51820
# Keep alive every 25 seconds
PersistentKeepalive = 25
```

### Services Server Interface

```ini
# /etc/wireguard/wg-services.conf (or via Docker secrets)
[Interface]
# Services server's private key
PrivateKey = <services-private-key>
# Virtual IP for services server
Address = 10.100.0.11/24
# Listen port
ListenPort = 51820

[Peer]
# Web server's public key
PublicKey = <web-public-key>
# Optional preshared key
PresharedKey = <preshared-key>
# Web server's virtual IP
AllowedIPs = 10.100.0.10/32
# Connect to web server
Endpoint = <web-server-ip>:51820
# Keep alive
PersistentKeepalive = 25
```

### MTU Optimization for Large Files

```bash
# Set MTU to 1420 (optimal for WireGuard)
sudo ip link set dev wg0 mtu 1420
```

---

## Docker Deployment

### Development docker-compose.yml

```yaml
version: '3.8'

networks:
  services-net:
    driver: bridge
    ipam:
      config:
        - subnet: 10.101.0.0/24
  tunnel-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24

services:
  wireguard-web:
    image: ghcr.io/jhbiostatcenter/naaccord/wireguard:latest
    container_name: naaccord-wireguard-web
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    environment:
      - WG_PRIVATE_KEY_FILE=/run/secrets/wg_web_private_key
      - WG_PEER_PUBLIC_KEY_FILE=/run/secrets/wg_services_public_key
      - WG_PRESHARED_KEY_FILE=/run/secrets/wg_preshared_key
      - WG_TUNNEL_ADDRESS=10.100.0.10/24
      - WG_PEER_ADDRESS=10.100.0.11
      - WG_PEER_ENDPOINT=wireguard-services:51820
    networks:
      - tunnel-net
    secrets:
      - wg_web_private_key
      - wg_services_public_key
      - wg_preshared_key

  wireguard-services:
    image: ghcr.io/jhbiostatcenter/naaccord/wireguard:latest
    container_name: naaccord-wireguard-services
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    environment:
      - WG_PRIVATE_KEY_FILE=/run/secrets/wg_services_private_key
      - WG_PEER_PUBLIC_KEY_FILE=/run/secrets/wg_web_public_key
      - WG_PRESHARED_KEY_FILE=/run/secrets/wg_preshared_key
      - WG_TUNNEL_ADDRESS=10.100.0.11/24
      - WG_PEER_ADDRESS=10.100.0.10
      - WG_FORWARD_PORTS=3306:tcp:10.101.0.2 6379:tcp:10.101.0.4 8001:tcp:10.101.0.5
      - WG_FORWARD_INTERFACE=eth0
    networks:
      services-net:
        ipv4_address: 10.101.0.3
      tunnel-net:
    secrets:
      - wg_services_private_key
      - wg_web_public_key
      - wg_preshared_key

  web:
    image: ghcr.io/jhbiostatcenter/naaccord/web:latest
    environment:
      - SERVER_ROLE=web
      - SERVICES_URL=http://10.100.0.11:8001
      - DATABASE_HOST=10.100.0.11  # Via WireGuard tunnel
      - REDIS_URL=redis://10.100.0.11:6379/0
    network_mode: "service:wireguard-web"
    depends_on:
      - wireguard-web

  services:
    image: ghcr.io/jhbiostatcenter/naaccord/services:latest
    environment:
      - SERVER_ROLE=services
      - DATABASE_HOST=10.101.0.2  # Direct on services-net
      - REDIS_URL=redis://10.101.0.4:6379/0
    networks:
      services-net:
        ipv4_address: 10.101.0.5
    depends_on:
      - wireguard-services

secrets:
  wg_web_private_key:
    file: ./deploy/configs/wireguard/dev/web-private.key
  wg_web_public_key:
    file: ./deploy/configs/wireguard/dev/web-public.key
  wg_services_private_key:
    file: ./deploy/configs/wireguard/dev/services-private.key
  wg_services_public_key:
    file: ./deploy/configs/wireguard/dev/services-public.key
  wg_preshared_key:
    file: ./deploy/configs/wireguard/dev/preshared.key
```

### Port Forwarding Configuration

The WireGuard services container forwards ports to services on the internal network:

```bash
# Format: port:protocol:destination_ip
WG_FORWARD_PORTS="3306:tcp:10.101.0.2 6379:tcp:10.101.0.4 8001:tcp:10.101.0.5"

# This creates iptables rules:
# - DNAT: rewrite destination for incoming tunnel traffic
# - MASQUERADE: rewrite source for forwarded traffic

# Example rules created automatically:
iptables -t nat -A PREROUTING -i wg0 -p tcp --dport 3306 -j DNAT --to-destination 10.101.0.2:3306
iptables -t nat -A POSTROUTING -o eth0 -p tcp -d 10.101.0.2 --dport 3306 -j MASQUERADE
```

---

## Testing and Verification

### 1. Verify WireGuard Tunnel

```bash
# Check tunnel is up
docker exec wireguard-web ping -c 3 10.100.0.11
docker exec wireguard-services ping -c 3 10.100.0.10

# Check handshake (should show non-zero timestamp)
docker exec wireguard-web wg show wg0 latest-handshakes
docker exec wireguard-services wg show wg0 latest-handshakes

# Check data transfer (should show bytes received > 0)
docker exec wireguard-web wg show | grep "transfer:"
# Should show: transfer: X.XX KiB received, Y.YY KiB sent
```

### 2. Verify Network Connectivity

```bash
# From web container - test database via tunnel
docker exec web python -c "import socket; s = socket.socket(); print(s.connect_ex(('10.100.0.11', 3306)))"
# Should return: 0 (success)

# From services container - test database directly
docker exec services python -c "import socket; s = socket.socket(); print(s.connect_ex(('10.101.0.2', 3306)))"
# Should return: 0 (success)

# Test encrypted connection
docker exec web curl -s http://10.100.0.11:8001/internal/storage/health
```

### 3. Verify Port Forwarding

```bash
# Check iptables rules on wireguard-services
docker exec wireguard-services iptables -t nat -L PREROUTING -n -v

# Should show DNAT rules for ports 3306, 6379, 8001
```

### 4. Verify Encryption

```bash
# Capture traffic to verify encryption
sudo tcpdump -i lo -w wireguard.pcap port 51820

# Stream a file
curl -X POST http://localhost:8000/upload/stream \
  -F "file=@test_data.csv"

# Analyze capture - should see only encrypted packets
wireshark wireguard.pcap
```

### 5. Application Health Checks

```bash
# Web server health
curl http://localhost:8000/health/

# Services API health (via tunnel from web)
docker exec web curl http://10.100.0.11:8001/health/
```

---

## Monitoring

### Real-time Statistics

```bash
# Watch transfer statistics
watch -n 1 'sudo wg show wg0 transfer'

# Monitor bandwidth
sudo iftop -i wg0

# Check latency
ping -c 10 10.100.0.11

# View WireGuard status
docker exec wireguard-web wg show
docker exec wireguard-services wg show
```

### Django Logging

```python
# depot/middleware/wireguard_monitor.py

class WireGuardMonitor:
    """Monitor WireGuard tunnel performance."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)

        # Log if using WireGuard
        if '10.100.0.' in request.META.get('REMOTE_ADDR', ''):
            duration = time.time() - start
            logger.info(f"WireGuard request: {duration:.3f}s")

        return response
```

### Metrics to Monitor

- Tunnel uptime
- Data transfer rates (bytes sent/received)
- Handshake timestamps (should update regularly)
- Peer connectivity status
- Packet loss
- Latency through tunnel

---

## Troubleshooting

### Issue: 0 B received in tunnel

**Symptom:** `wg show` reports `transfer: 0 B received` and handshake timestamp is `0`

**Cause:** Public key mismatch - the peer's public key doesn't match their private key

**Solution:**
1. Regenerate public keys from existing private keys:
   ```bash
   cat web-private.key | wg pubkey > web-public.key
   cat services-private.key | wg pubkey > services-public.key
   ```
2. Update Docker secrets or Ansible vault with correct public keys
3. Redeploy containers

### Issue: Connection timeout to 10.100.0.11

**Cause:** iptables rules not configured or services on wrong network

**Solution:**
- Check `WG_FORWARD_PORTS` environment variable
- Verify services have static IPs on 10.101.0.0/24 network
- Verify iptables rules: `docker exec wireguard-services iptables -t nat -L -n -v`

### Issue: Subnet conflict warnings

**Cause:** Multiple networks using same IP range

**Solution:**
- Ensure services-net uses 10.101.0.0/24
- Ensure WireGuard tunnel uses 10.100.0.0/24
- Update docker-compose.yml network configuration

### Issue: Container can't resolve service names

**Cause:** Using `network_mode: service` prevents DNS resolution

**Solution:**
- Use IP addresses for cross-network communication
- Use DNS names only within same Docker network

### Issue: Firewall blocking WireGuard

```bash
# Check firewall
sudo iptables -L -n | grep 51820

# Add rules if needed
sudo iptables -A INPUT -p udp --dport 51820 -j ACCEPT
sudo iptables -A INPUT -p udp --dport 51821 -j ACCEPT
```

### Issue: Performance degradation

```bash
# Check for packet fragmentation
ping -M do -s 1400 10.100.0.11

# If fails, reduce MTU
sudo ip link set dev wg0 mtu 1380

# Check if WireGuard module is loaded
lsmod | grep wireguard
```

### Verifying deployed keys

```bash
# On running container - check configured peer public key
docker exec wireguard-web wg show wg0 peers

# Compare to what should be configured (services public key)
cat services-public.key

# If they don't match, public keys were not correctly derived
```

---

## Security Best Practices

### Key Management

1. **Never commit unencrypted keys to git**
2. **Development keys** in `deploy/configs/wireguard/dev/` are for local testing only
3. **Production keys** must be:
   - Generated on secure workstation
   - Stored in encrypted Ansible vault
   - Never logged or displayed
   - Rotated periodically (every 6-12 months)

### Configuration Security

- **NEVER** bypass WireGuard for PHI data
- **NEVER** expose services container directly to public network
- **ALWAYS** use pre-shared keys in production for post-quantum security
- **ALWAYS** monitor tunnel health continuously
- **ROTATE** keys quarterly or after any security incident

### Environment Variables

#### Web Container
```bash
SERVICES_URL=http://10.100.0.11:8001  # Through WireGuard
INTERNAL_API_KEY=<secure-key>         # Additional auth layer
DATABASE_HOST=10.100.0.11             # Via tunnel
```

#### Services Container
```bash
BIND_ADDRESS=10.100.0.11:8001        # Only on WireGuard network
ALLOWED_HOSTS=10.100.0.10            # Only accept from web
DATABASE_HOST=10.101.0.2             # Direct on services-net
```

### Disaster Recovery

#### Tunnel Down Scenario
1. Web container detects services unreachable
2. Returns 503 Service Unavailable
3. No PHI data cached or stored in web container
4. Alerts sent to operations team

#### Key Compromise Response
1. Generate new key pairs immediately
2. Update Docker secrets or Ansible vault
3. Rolling restart of WireGuard containers
4. Audit logs for suspicious activity

---

## Ansible Deployment

### Vault Configuration

Add keys to `deploy/ansible/inventories/production/group_vars/vault.yml`:

```yaml
# WireGuard Keys (PHI Tunnel Encryption)
# CRITICAL: Public keys must be derived from private keys using 'wg pubkey'

# Web server keys
vault_wg_web_private_key: "<contents of web-private.key>"
vault_wg_web_public_key: "<contents of web-public.key>"

# Services server keys
vault_wg_services_private_key: "<contents of services-private.key>"
vault_wg_services_public_key: "<contents of services-public.key>"

# Preshared key (shared between both peers)
vault_wg_preshared_key: "<contents of preshared.key>"
```

### Encrypt the vault:

```bash
ansible-vault encrypt inventories/production/group_vars/vault.yml
```

### Deploy with Ansible

```bash
# Deploy WireGuard to production
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/deploy-wireguard.yml \
  --ask-vault-pass

# Verify keys match
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/verify-wireguard-keys.yml \
  --ask-vault-pass
```

---

## Related Documentation

- **[Storage Manager](../technical/storage-manager-abstraction.md)** - How file streaming uses WireGuard
- **[PHI File Tracking](PHIFileTracking-system.md)** - Complete audit trail system
- **[Architecture Overview](../deployment/guides/architecture.md)** - Two-server design
- **[Deployment Steps](../../deploy/deploy-steps.md)** - Production deployment guide
- **[Docker Configuration](../deployment/containers/docker.md)** - Container setup

---

## Deployment Checklist

- [ ] Generate WireGuard keys correctly (private → derive public)
- [ ] Encrypt keys in Ansible vault (production) or Docker secrets (development)
- [ ] Update docker-compose files with correct subnet (10.101.0.0/24 for services)
- [ ] Configure WG_FORWARD_PORTS with destination IPs
- [ ] Assign static IPs to all services containers
- [ ] Set DATABASE_* environment variables correctly
- [ ] Deploy with correct Docker Compose profile (web or services)
- [ ] Verify tunnel handshake (non-zero timestamp)
- [ ] Verify data transfer (bytes received > 0)
- [ ] Test database connectivity from web container through tunnel
- [ ] Verify iptables forwarding rules
- [ ] Check application health endpoints
- [ ] Monitor tunnel metrics in production

---

**Questions?** The WireGuard setup provides the best balance of security and performance for NA-ACCORD's streaming use case!
