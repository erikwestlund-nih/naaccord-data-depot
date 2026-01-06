# Internal HTTPS Architecture - Setup & Tradeoffs

**Date:** January 25, 2025
**Context:** Web Server → Services Server communication over localhost
**Goal:** Encrypt internal traffic while maintaining performance

---

## Current Architecture

```
Internet → [HTTPS/443] → Web Server (8000) → [HTTP/8001] → Services Server (8001)
                             │                                      │
                          Public Face                          Internal Only
                             │                                      │
                        [Handles UI]                        [Processes Data]
```

---

## Option 1: TLS on Localhost (Recommended)

### Architecture
```
Web Server ──────[HTTPS/TLS]──────▶ Services Server
(127.0.0.1:8000)                    (127.0.0.1:8001)
     │                                    │
[Certificate A]                    [Certificate B]
     │                                    │
     └──────── Mutual TLS Auth ──────────┘
```

### Implementation

#### 1. Generate Self-Signed Certificates
```bash
#!/bin/bash
# generate-internal-certs.sh

# Create CA key and certificate
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/C=US/ST=State/L=City/O=NAACCORD/CN=NAACCORD-Internal-CA"

# Generate service certificate
openssl genrsa -out services.key 2048
openssl req -new -key services.key -out services.csr \
  -subj "/C=US/ST=State/L=City/O=NAACCORD/CN=localhost"

# Sign with CA
openssl x509 -req -days 3650 -in services.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out services.crt

# Generate web server client certificate for mutual TLS
openssl genrsa -out web-client.key 2048
openssl req -new -key web-client.key -out web-client.csr \
  -subj "/C=US/ST=State/L=City/O=NAACCORD/CN=web-server"

openssl x509 -req -days 3650 -in web-client.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out web-client.crt
```

#### 2. Django Services Server Configuration
```python
# services_server.py
import ssl
from django.core.management import execute_from_command_line

if __name__ == '__main__':
    # For development with SSL
    from django.core.servers.basehttp import WSGIServer
    import django.core.servers.basehttp

    # Monkey patch to add SSL
    original_init = WSGIServer.__init__

    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        # Add SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain('services.crt', 'services.key')

        # For mutual TLS (optional but recommended)
        context.load_verify_locations('ca.crt')
        context.verify_mode = ssl.CERT_REQUIRED

        self.socket = context.wrap_socket(self.socket, server_side=True)

    WSGIServer.__init__ = new_init

    # Run server
    execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8001'])
```

#### 3. Web Server Client Configuration
```python
# depot/services/internal_client.py
import requests
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

class SSLAdapter(HTTPAdapter):
    """Custom adapter for mutual TLS."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context(cafile='ca.crt')
        context.load_cert_chain(
            certfile='web-client.crt',
            keyfile='web-client.key'
        )
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

class SecureInternalClient:
    """Client for secure internal communication."""

    def __init__(self):
        self.session = requests.Session()
        self.session.mount('https://', SSLAdapter())
        self.base_url = 'https://127.0.0.1:8001'

    def post(self, endpoint, **kwargs):
        return self.session.post(f"{self.base_url}{endpoint}", **kwargs)
```

### Advantages ✅
- **Complete encryption** of all internal traffic
- **Mutual authentication** prevents MITM attacks
- **Standards-compliant** TLS implementation
- **Defense in depth** - encrypted even on localhost
- **Audit compliance** - meets strict security requirements

### Disadvantages ❌
- **Performance overhead**: ~5-15% latency increase
- **Certificate management**: Need rotation process
- **Complexity**: More moving parts
- **Debugging harder**: Can't easily inspect traffic

---

## Option 2: Unix Domain Sockets (Alternative)

### Architecture
```
Web Server ────[Unix Socket]────▶ Services Server
     │                                  │
[/var/run/naaccord/service.sock]       │
     │                                  │
     └──── File Permission Auth ────────┘
```

### Implementation
```python
# services_server.py - Unix socket server
import os
import socket
from django.core.servers.basehttp import WSGIServer

class UnixSocketWSGIServer(WSGIServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Use Unix socket instead of TCP
        sock_path = '/var/run/naaccord/service.sock'

        # Remove old socket if exists
        if os.path.exists(sock_path):
            os.unlink(sock_path)

        # Create Unix socket
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(sock_path)

        # Secure permissions (only owner can access)
        os.chmod(sock_path, 0o600)

# Client configuration
class UnixSocketAdapter(HTTPAdapter):
    def get_connection(self, url, proxies=None):
        return UnixSocketConnection('/var/run/naaccord/service.sock')
```

### Advantages ✅
- **No network stack**: Faster than TCP
- **Kernel-level security**: File permissions
- **No encryption overhead**: Already isolated
- **Simple**: No certificates needed

### Disadvantages ❌
- **Not encrypted**: Data in memory could be accessed
- **Local only**: Can't distribute services
- **Platform specific**: Unix/Linux only
- **Limited tooling**: Harder to monitor

---

## Option 3: SSH Tunneling (Quick Setup)

### Architecture
```
Web Server ──[localhost:8001]──▶ SSH Tunnel ──[encrypted]──▶ Services Server
```

### Setup
```bash
# Create SSH tunnel
ssh -L 8001:localhost:8001 services-host -N

# Or use autossh for persistence
autossh -M 0 -f -N -L 8001:localhost:8001 services-host
```

### Advantages ✅
- **Quick setup**: No code changes
- **Strong encryption**: SSH protocol
- **Key-based auth**: SSH keys

### Disadvantages ❌
- **Extra process**: SSH tunnel management
- **Not application-aware**: Generic tunnel
- **Harder to monitor**: Opaque to application

---

## Option 4: WireGuard VPN (Production Grade)

### Architecture
```
┌──────────────────────────────────────┐
│        WireGuard Interface           │
│   Web (10.0.0.1) ←→ Services (10.0.0.2) │
│         Encrypted Tunnel              │
└──────────────────────────────────────┘
```

### Configuration
```ini
# /etc/wireguard/wg0.conf (Web Server)
[Interface]
PrivateKey = WEB_PRIVATE_KEY
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = SERVICES_PUBLIC_KEY
AllowedIPs = 10.0.0.2/32
Endpoint = 127.0.0.1:51821
```

### Advantages ✅
- **Kernel-level encryption**: Very fast
- **Modern crypto**: ChaCha20-Poly1305
- **Simple configuration**: Easy to manage
- **Production ready**: Used by many enterprises

### Disadvantages ❌
- **Kernel module**: Requires root access
- **Network layer**: Not application-aware
- **Additional complexity**: Another system to manage

---

## Performance Comparison

| Method | Latency Impact | Throughput Impact | CPU Usage |
|--------|---------------|-------------------|-----------|
| Plain HTTP | Baseline (0ms) | Baseline (100%) | Baseline |
| TLS/HTTPS | +0.5-1ms | 85-95% | +5-10% |
| Unix Socket | -0.2ms | 105-110% | -5% |
| SSH Tunnel | +1-2ms | 70-85% | +10-15% |
| WireGuard | +0.3ms | 95-98% | +2-5% |

---

## Security Comparison

| Method | Encryption | Authentication | MITM Protection | Compliance |
|--------|------------|----------------|-----------------|------------|
| Plain HTTP | ❌ | API Key | ❌ | ❌ |
| TLS/HTTPS | ✅ AES/ChaCha | Mutual TLS | ✅ | ✅ HIPAA |
| Unix Socket | ❌ | File Perms | ✅ (local) | ⚠️ Depends |
| SSH Tunnel | ✅ AES | SSH Keys | ✅ | ✅ |
| WireGuard | ✅ ChaCha20 | Pre-shared | ✅ | ✅ |

---

## Recommended Implementation Plan

### For Your Use Case (Single Port, Local Connection)

#### Phase 1: Internal Testing (Current)
```python
# Keep HTTP for now but prepare for TLS
class InternalClient:
    def __init__(self):
        self.use_tls = settings.INTERNAL_TLS_ENABLED
        self.base_url = f"{'https' if self.use_tls else 'http'}://127.0.0.1:8001"

        if self.use_tls:
            self.session = self._create_tls_session()
        else:
            self.session = requests.Session()
            # Add deprecation warning
            logger.warning("Using unencrypted internal communication - for testing only!")
```

#### Phase 2: Pre-Production
1. **Generate certificates** using script above
2. **Enable TLS** with self-signed certs
3. **Test performance** impact
4. **Implement monitoring**

#### Phase 3: Production
1. **Use proper CA** (internal PKI or Let's Encrypt)
2. **Implement mutual TLS**
3. **Add certificate rotation**
4. **Enable certificate pinning**

---

## Configuration Examples

### Nginx Reverse Proxy (Alternative)
```nginx
# /etc/nginx/sites-available/services-internal
upstream services_backend {
    server 127.0.0.1:8001;
}

server {
    listen 127.0.0.1:8443 ssl;
    server_name internal.naaccord.local;

    ssl_certificate /etc/nginx/certs/internal.crt;
    ssl_certificate_key /etc/nginx/certs/internal.key;

    # Mutual TLS
    ssl_client_certificate /etc/nginx/certs/ca.crt;
    ssl_verify_client on;

    location / {
        proxy_pass http://services_backend;
        proxy_set_header X-Client-Cert $ssl_client_s_dn;
    }
}
```

### HAProxy (Load Balancing Ready)
```
global
    tune.ssl.default-dh-param 2048

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

frontend services_frontend
    bind 127.0.0.1:8443 ssl crt /etc/haproxy/certs/services.pem ca-file /etc/haproxy/certs/ca.crt verify required
    default_backend services_backend

backend services_backend
    server services1 127.0.0.1:8001 check
```

---

## Monitoring & Debugging

### TLS Connection Monitoring
```python
# depot/monitoring/tls_monitor.py
import ssl
import socket
from datetime import datetime

def check_internal_tls():
    """Monitor internal TLS health."""
    try:
        context = ssl.create_default_context()
        with socket.create_connection(('127.0.0.1', 8001), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                cert = ssock.getpeercert()
                expiry = datetime.strptime(
                    cert['notAfter'], '%b %d %H:%M:%S %Y %Z'
                )
                days_left = (expiry - datetime.now()).days

                if days_left < 30:
                    logger.warning(f"Certificate expires in {days_left} days")

                return {
                    'status': 'healthy',
                    'cipher': ssock.cipher(),
                    'version': ssock.version(),
                    'days_to_expiry': days_left
                }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
```

### Debug Mode (Development Only)
```python
# settings.py
if DEBUG:
    # Allow unverified certificates in development
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

    # Log all internal requests
    import logging
    logging.getLogger('urllib3').setLevel(logging.DEBUG)
```

---

## Final Recommendation

For your specific requirements:

1. **Start with HTTP** for internal testing (current state is OK)
2. **Implement TLS with self-signed certificates** for pre-production
3. **Use mutual TLS** for production deployment
4. **Consider Unix sockets** if you never need to distribute services

The ~5-10% performance overhead of TLS is worth the security benefits, especially when handling PHI data. The encryption protects against:
- Memory dumps containing data in transit
- Local privilege escalation attacks
- Accidental data exposure in logs
- Compliance audit findings

Remember: Even though it's localhost, defense in depth means encrypting everywhere possible.