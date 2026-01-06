# Docker WireGuard Deployment - Critical Changes Summary

## 🔧 Changes Applied (2025-10-04)

### Problem Statement
WireGuard tunnel between web and services containers was failing with:
- **0 B received** - no data flowing through tunnel
- **Handshake failures** - tunnel never established
- **Public key mismatch** - keys not derived from private keys
- **Network conflicts** - services-net and tunnel using same subnet

### Root Causes Identified
1. **Public key generation error** - Public keys must be derived from private keys using `wg pubkey`
2. **Network subnet conflict** - Both services-net and WireGuard tunnel using `10.100.0.0/24`
3. **Missing iptables rules** - Port forwarding not configured to route traffic to services network
4. **Container network mode issues** - Services container using `network_mode: service` prevented proper routing

## ✅ Solutions Implemented

### 1. Network Configuration

#### docker-compose.yml (development)
```yaml
networks:
  services-net:
    subnet: 10.101.0.0/24  # Changed from 10.100.0.0/24 to avoid conflict
  tunnel-net:
    subnet: 172.20.0.0/24  # WireGuard container interconnect
```

**WireGuard Tunnel IPs (unchanged):**
- Web: `10.100.0.10/24`
- Services: `10.100.0.11/24`

**Services Network IPs:**
- MariaDB: `10.101.0.2`
- WireGuard-Services: `10.101.0.3`
- Redis: `10.101.0.4`
- Services container: `10.101.0.5`

#### docker-compose.prod.yml (production)
```yaml
networks:
  wireguard:
    subnet: 10.101.0.0/24  # Changed from 10.100.0.0/24
```

### 2. WireGuard Public Key Generation

**CRITICAL FIX:** Public keys must be derived from private keys:

```bash
# ✅ CORRECT
wg genkey > web-private.key
cat web-private.key | wg pubkey > web-public.key

# ❌ WRONG (creates mismatched keypair)
wg genkey > web-private.key
wg genkey > web-public.key
```

**Files Updated:**
- `deploy/configs/wireguard/dev/web-public.key` - Regenerated from private key
- `deploy/configs/wireguard/dev/services-public.key` - Regenerated from private key
- `deploy/ansible/WIREGUARD-KEYS.md` - Complete documentation for Ansible

### 3. WireGuard Port Forwarding

#### Updated entrypoint.sh
**File:** `deploy/containers/wireguard/scripts/entrypoint.sh`

**New format supports destination IP specification:**
```bash
# Format: port:protocol:destination_ip
WG_FORWARD_PORTS="3306:tcp:10.101.0.2 6379:tcp:10.101.0.4 8001:tcp:10.101.0.5"
```

**iptables rules automatically configured:**
```bash
# DNAT - rewrite destination for incoming tunnel traffic
iptables -t nat -A PREROUTING -i wg0 -p tcp --dport 3306 -j DNAT --to-destination 10.101.0.2:3306

# MASQUERADE - rewrite source for forwarded traffic
iptables -t nat -A POSTROUTING -o eth0 -p tcp -d 10.101.0.2 --dport 3306 -j MASQUERADE
```

### 4. Container Network Configuration

#### Development (docker-compose.yml)
**Services container:**
```yaml
services:
  environment:
    DB_HOST: 10.101.0.2      # Direct IP on services-net
    CELERY_BROKER_URL: redis://10.101.0.4:6379/0
  networks:
    services-net:
      ipv4_address: 10.101.0.5
```

**Web container:**
```yaml
web:
  environment:
    DB_HOST: 10.100.0.11      # Via WireGuard tunnel
    CELERY_BROKER_URL: redis://10.100.0.11:6379/0
  network_mode: "service:wireguard-web"
```

#### Production (docker-compose.prod.yml)
**Services container:**
```yaml
services:
  environment:
    DATABASE_HOST: ${DATABASE_HOST}  # External MariaDB (bare metal)
    REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
  networks:
    wireguard:
      ipv4_address: 10.101.0.5
  ports:
    - "8001:8001"
```

**Web container:**
```yaml
web:
  environment:
    DATABASE_HOST: 10.100.0.11     # Via WireGuard tunnel
    REDIS_URL: redis://:${REDIS_PASSWORD}@10.100.0.11:6379/0
  network_mode: "service:wireguard-web"
```

**Redis:**
```yaml
redis:
  networks:
    wireguard:
      ipv4_address: 10.101.0.4
```

**WireGuard-services:**
```yaml
wireguard-services:
  environment:
    WG_FORWARD_PORTS: "3306:tcp:10.101.0.2 6379:tcp:10.101.0.4 8001:tcp:10.101.0.5"
    WG_FORWARD_INTERFACE: eth0
  networks:
    wireguard:
      ipv4_address: 10.101.0.3
```

### 5. Database Environment Variables

**Standardized naming across web and services:**

**Web container** (via tunnel):
```bash
DATABASE_HOST=10.100.0.11
DATABASE_PORT=3306
DATABASE_NAME=${DB_NAME}
DATABASE_USER=${DB_USER}
DATABASE_PASSWORD_FILE=/run/secrets/db_password
```

**Services container** (direct):
```bash
DATABASE_HOST=${DATABASE_HOST}  # From Ansible (bare metal DB)
DATABASE_PORT=${DATABASE_PORT:-3306}
DATABASE_NAME=${DB_NAME}
DATABASE_USER=${DB_USER}
DATABASE_PASSWORD_FILE=/run/secrets/db_password
```

## 📋 Ansible Requirements

### 1. Ansible Vault Variables

**File:** `deploy/ansible/inventories/production/group_vars/vault.yml`

```yaml
# WireGuard Keys - MUST be derived correctly
vault_wg_web_private_key: "<wg genkey output>"
vault_wg_web_public_key: "<cat web-private.key | wg pubkey output>"
vault_wg_services_private_key: "<wg genkey output>"
vault_wg_services_public_key: "<cat services-private.key | wg pubkey output>"
vault_wg_preshared_key: "<wg genpsk output>"
```

### 2. Docker Compose Profiles

**Web server:** `docker_compose_profile: web`
- Starts: wireguard-web, web, nginx

**Services server:** `docker_compose_profile: services`
- Starts: wireguard-services, services, redis, celery, flower

### 3. Key Verification Commands

```bash
# Verify keys match on deployment
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/verify-wireguard-keys.yml \
  --ask-vault-pass
```

## 🧪 Testing & Verification

### 1. Verify WireGuard Tunnel
```bash
# Check handshake (should show non-zero timestamp)
docker exec wireguard-web wg show wg0 latest-handshakes
docker exec wireguard-services wg show wg0 latest-handshakes

# Check data transfer (should show bytes received)
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
```

### 3. Verify Port Forwarding
```bash
# Check iptables rules on wireguard-services
docker exec wireguard-services iptables -t nat -L PREROUTING -n -v

# Should show DNAT rules:
# Chain PREROUTING (policy ACCEPT)
# pkts bytes target     prot opt in     out     source               destination
#    0     0 DNAT       tcp  --  wg0    *       0.0.0.0/0            0.0.0.0/0            tcp dpt:3306 to:10.101.0.2:3306
#    0     0 DNAT       tcp  --  wg0    *       0.0.0.0/0            0.0.0.0/0            tcp dpt:6379 to:10.101.0.4:6379
#    0     0 DNAT       tcp  --  wg0    *       0.0.0.0/0            0.0.0.0/0            tcp dpt:8001 to:10.101.0.5:8001
```

### 4. Application Health Checks
```bash
# Web server health
curl http://localhost:8000/health/

# Services API health
curl http://localhost:8001/health/
```

## 📚 Documentation References

- **WireGuard Keys:** `deploy/ansible/WIREGUARD-KEYS.md`
- **Deployment Steps:** `deploy/deploy-steps.md`
- **Architecture:** `docs/deployment/guides/architecture.md`
- **Main CLAUDE.md:** `CLAUDE.md` (project overview)
- **Deploy CLAUDE.md:** `deploy/CLAUDE.md` (deployment domain)

## 🚨 Common Issues & Solutions

### Issue: 0 B received in tunnel
**Cause:** Public key mismatch
**Solution:** Regenerate public keys from private keys, redeploy containers

### Issue: Connection timeout to 10.100.0.11
**Cause:** iptables rules not configured or services on wrong network
**Solution:** Check WG_FORWARD_PORTS environment variable, verify services have static IPs

### Issue: Subnet conflict warnings
**Cause:** Multiple networks using same IP range
**Solution:** Ensure services-net uses 10.101.0.0/24, tunnel uses 10.100.0.0/24

### Issue: Container can't resolve service names
**Cause:** Using network_mode: service prevents DNS resolution
**Solution:** Use IP addresses for cross-network communication, DNS names within same network

## ✅ Deployment Checklist

- [ ] Generate WireGuard keys correctly (private → derive public)
- [ ] Encrypt keys in Ansible vault
- [ ] Update docker-compose.prod.yml with subnet 10.101.0.0/24
- [ ] Configure WG_FORWARD_PORTS with destination IPs
- [ ] Assign static IPs to services containers
- [ ] Set DATABASE_* environment variables (not DB_*)
- [ ] Deploy with correct profile (web or services)
- [ ] Verify tunnel handshake (non-zero timestamp)
- [ ] Verify data transfer (bytes received > 0)
- [ ] Test database connectivity from web container
- [ ] Verify iptables forwarding rules
- [ ] Check application health endpoints

## 📝 Next Steps

1. **Test in staging environment** with profiles
2. **Update production vault** with correctly derived keys
3. **Deploy to production** following deploy-steps.md
4. **Monitor tunnel health** using Grafana/Loki
5. **Document any issues** encountered during deployment
