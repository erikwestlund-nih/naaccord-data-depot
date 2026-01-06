# WireGuard Security Architecture for PHI Data

## Overview
WireGuard provides encrypted tunneling for all PHI data transfers between web and services containers, ensuring data is never transmitted unencrypted, even on our own infrastructure.

## Data Flow Architecture

```
User → [Web Container:8000] → WireGuard Tunnel → [Services Container:8001] → Storage
         (Public Zone)         (Encrypted PHI)      (Secure Zone)
```

### Key Security Principles
1. **Zero Trust Network**: Even internal traffic is encrypted
2. **PHI Isolation**: Services container handles all PHI storage operations
3. **Streaming Architecture**: Large files stream through encrypted tunnel
4. **No Unencrypted PHI**: Data is encrypted at rest and in transit

## Container Roles

### Web Container (Public-facing)
- Handles authentication and authorization
- Receives file uploads from users
- **NEVER stores PHI data**
- Streams data immediately to services via WireGuard
- Returns presigned URLs for downloads

### Services Container (PHI Handler)
- Receives data through WireGuard tunnel only
- Stores PHI data in secure storage (NAS/S3)
- Runs data processing tasks (R, Quarto)
- Generates audit reports
- Returns results through encrypted tunnel

### WireGuard Containers
- **wireguard-web**: Tunnel endpoint for web container
- **wireguard-services**: Tunnel endpoint for services container
- Pre-shared keys for additional security
- Network isolation (10.100.0.0/24)

## Network Configuration

### Development Mode
```yaml
# docker-compose.dev.yml
networks:
  wireguard:
    driver: bridge
    ipam:
      config:
        - subnet: 10.100.0.0/24

services:
  web:
    environment:
      - SERVICES_URL=http://10.100.0.11:8001  # Through WireGuard
    networks:
      - public       # Internet-facing
      - wireguard    # Encrypted tunnel

  services:
    networks:
      - wireguard    # ONLY WireGuard, no public access
      - internal     # Database/Redis access
```

### Production Mode
```yaml
# docker-compose.prod.yml
services:
  wireguard-web:
    image: ${REGISTRY}/naaccord/wireguard:${VERSION}
    networks:
      wireguard:
        ipv4_address: 10.100.0.10
    secrets:
      - wg_web_private_key
      - wg_services_public_key
      - wg_preshared_key

  wireguard-services:
    image: ${REGISTRY}/naaccord/wireguard:${VERSION}
    networks:
      wireguard:
        ipv4_address: 10.100.0.11
    secrets:
      - wg_services_private_key
      - wg_web_public_key
      - wg_preshared_key

  web:
    environment:
      - SERVICES_URL=http://10.100.0.11:8001
    depends_on:
      - wireguard-web

  services:
    networks:
      - wireguard  # ONLY accessible through tunnel
      - internal
    depends_on:
      - wireguard-services
```

## File Upload Flow with WireGuard

1. **User uploads file** to web container endpoint
2. **Web validates** authentication and permissions
3. **Web initiates streaming** to services via WireGuard:
   ```python
   # depot/views/upload.py
   def handle_upload(request):
       # Stream through WireGuard tunnel
       services_url = "http://10.100.0.11:8001/internal/storage/upload"

       # Stream file chunks through encrypted tunnel
       response = requests.post(
           services_url,
           data=stream_file_chunks(request.FILES['file']),
           headers={'X-Internal-Key': settings.INTERNAL_API_KEY},
           stream=True
       )
   ```

4. **Services receives** encrypted stream
5. **Services stores** to secure storage (NAS/S3)
6. **Services returns** storage location through tunnel
7. **Web returns** success to user (no PHI data)

## Key Generation and Management

### Generate WireGuard Keys
```bash
# Generate keys for production
cd deploy/secrets

# Web container keys
wg genkey | tee wg_web_private_key | wg pubkey > wg_web_public_key

# Services container keys
wg genkey | tee wg_services_private_key | wg pubkey > wg_services_public_key

# Pre-shared key for additional security
wg genpsk > wg_preshared_key

# Create Docker secrets
docker secret create wg_web_private_key wg_web_private_key
docker secret create wg_web_public_key wg_web_public_key
docker secret create wg_services_private_key wg_services_private_key
docker secret create wg_services_public_key wg_services_public_key
docker secret create wg_preshared_key wg_preshared_key
```

### WireGuard Configuration

#### Web Container Config (/etc/wireguard/wg0.conf)
```ini
[Interface]
PrivateKey = <web_private_key>
Address = 10.100.0.10/24
ListenPort = 51820

[Peer]
PublicKey = <services_public_key>
PresharedKey = <preshared_key>
AllowedIPs = 10.100.0.11/32
Endpoint = wireguard-services:51820
PersistentKeepalive = 25
```

#### Services Container Config
```ini
[Interface]
PrivateKey = <services_private_key>
Address = 10.100.0.11/24
ListenPort = 51820

[Peer]
PublicKey = <web_public_key>
PresharedKey = <preshared_key>
AllowedIPs = 10.100.0.10/32
Endpoint = wireguard-web:51820
PersistentKeepalive = 25
```

## Security Benefits

1. **End-to-End Encryption**: All PHI data encrypted with ChaCha20-Poly1305
2. **Perfect Forward Secrecy**: Key rotation doesn't compromise past data
3. **Minimal Attack Surface**: Services container not publicly accessible
4. **Network Segmentation**: Clear separation of public and PHI zones
5. **Compliance**: Meets HIPAA encryption requirements for PHI in transit

## Testing WireGuard Connection

### In Development
```bash
# Check tunnel is up
docker exec naaccord-web ping -c 3 10.100.0.11

# Test encrypted connection
docker exec naaccord-web curl http://10.100.0.11:8001/internal/storage/health

# Monitor WireGuard
docker exec naaccord-wireguard wg show
```

### In Production
```bash
# Check tunnel status
docker exec naaccord-wireguard-web wg show

# Verify encryption
docker exec naaccord-web tcpdump -i wg0 -n
```

## Monitoring and Alerts

### Health Checks
```yaml
healthcheck:
  test: ["CMD", "/opt/wireguard/healthcheck.sh"]
  interval: 30s
  timeout: 10s
```

### Metrics to Monitor
- Tunnel uptime
- Data transfer rates
- Handshake timestamps
- Peer connectivity
- Packet loss

## Disaster Recovery

### Tunnel Down Scenario
1. Web container detects services unreachable
2. Returns 503 Service Unavailable
3. No PHI data cached or stored in web container
4. Alerts sent to operations team

### Key Compromise Response
1. Generate new key pairs immediately
2. Update Docker secrets
3. Rolling restart of WireGuard containers
4. Audit logs for suspicious activity

## Important Notes

- **NEVER** bypass WireGuard for PHI data
- **NEVER** expose services container directly to public network
- **ALWAYS** use pre-shared keys in production
- **ALWAYS** monitor tunnel health
- **ROTATE** keys quarterly or after any security incident

## Environment Variables

### Web Container
```bash
SERVICES_URL=http://10.100.0.11:8001  # Through WireGuard
INTERNAL_API_KEY=<secure-key>         # Additional auth layer
```

### Services Container
```bash
BIND_ADDRESS=10.100.0.11:8001        # Only on WireGuard network
ALLOWED_HOSTS=10.100.0.10            # Only accept from web
```

This architecture ensures that PHI data is **always encrypted** when moving between containers, meeting both security best practices and compliance requirements.