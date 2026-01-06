# API Key Rotation Strategy

**Date:** January 25, 2025
**Purpose:** Automated key rotation for internal service authentication

---

## Current State

- **Web Server → Services Server** authentication uses static `INTERNAL_API_KEY`
- Key stored in environment variables
- No rotation mechanism
- Simple string comparison

---

## Recommended Solutions

### Option 1: Ansible-Based Rotation (Recommended for Simplicity)

#### Architecture
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Ansible   │────▶│ Secrets File │────▶│  Services   │
│  Playbook   │     │  (Encrypted) │     │   (Reload)  │
└─────────────┘     └──────────────┘     └─────────────┘
       │                                         ▲
       └─────────────────────────────────────────┘
                    Restart/Reload
```

#### Implementation

**1. Ansible Vault for Secrets**
```yaml
# secrets.yml (encrypted with ansible-vault)
api_keys:
  current: "{{ lookup('password', '/dev/null chars=ascii_letters,digits length=64') }}"
  previous: "{{ api_keys_backup.current | default('initial-key') }}"
  rotation_date: "{{ ansible_date_time.iso8601 }}"
```

**2. Rotation Playbook**
```yaml
# rotate-api-keys.yml
---
- name: Rotate Internal API Keys
  hosts: naaccord_servers
  vars_files:
    - secrets.yml

  tasks:
    - name: Backup current key
      set_fact:
        api_keys_backup:
          current: "{{ api_keys.current }}"
          rotation_date: "{{ api_keys.rotation_date }}"

    - name: Generate new API key
      set_fact:
        new_api_key: "{{ lookup('password', '/dev/null chars=ascii_letters,digits length=64') }}"

    - name: Update Web Server environment
      lineinfile:
        path: /opt/naaccord/web/.env
        regexp: '^INTERNAL_API_KEY='
        line: 'INTERNAL_API_KEY={{ new_api_key }}'
      notify: reload_web_server

    - name: Update Services Server to accept both keys temporarily
      template:
        src: dual_key_config.j2
        dest: /opt/naaccord/services/.env
      vars:
        current_key: "{{ new_api_key }}"
        previous_key: "{{ api_keys.current }}"
      notify: reload_services_server

    - name: Wait for services to reload
      pause:
        seconds: 30

    - name: Remove old key from Services Server
      lineinfile:
        path: /opt/naaccord/services/.env
        regexp: '^INTERNAL_API_KEY_OLD='
        state: absent
      notify: reload_services_server

    - name: Log rotation
      lineinfile:
        path: /var/log/naaccord/key_rotations.log
        line: "{{ ansible_date_time.iso8601 }} - Key rotated successfully"
        create: yes

  handlers:
    - name: reload_web_server
      systemd:
        name: naaccord-web
        state: reloaded

    - name: reload_services_server
      systemd:
        name: naaccord-services
        state: reloaded
```

**3. Cron Schedule**
```bash
# /etc/cron.d/rotate-api-keys
# Rotate keys every Sunday at 3 AM
0 3 * * 0 ansible-playbook /opt/ansible/rotate-api-keys.yml --vault-password-file=/root/.vault_pass
```

**4. Monitoring Script**
```bash
#!/bin/bash
# /opt/monitoring/check-key-age.sh

KEY_FILE="/opt/naaccord/web/.env"
KEY_AGE_DAYS=7
ALERT_EMAIL="security@example.com"

# Get key modification time
KEY_MOD_TIME=$(stat -c %Y "$KEY_FILE")
CURRENT_TIME=$(date +%s)
AGE_SECONDS=$((CURRENT_TIME - KEY_MOD_TIME))
AGE_DAYS=$((AGE_SECONDS / 86400))

if [ $AGE_DAYS -gt $KEY_AGE_DAYS ]; then
    echo "WARNING: API key is $AGE_DAYS days old" | mail -s "API Key Rotation Overdue" $ALERT_EMAIL
fi
```

---

### Option 2: JWT with Auto-Rotation (More Secure, More Complex)

#### Implementation in Django

**1. JWT Service Authentication**
```python
# depot/auth/service_auth.py
import jwt
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache

class ServiceAuthManager:
    """Manages JWT tokens for service-to-service authentication."""

    TOKEN_LIFETIME = timedelta(hours=1)
    REFRESH_THRESHOLD = timedelta(minutes=15)

    def __init__(self):
        self.signing_key = settings.SERVICE_JWT_KEY
        self.algorithm = 'HS256'

    def generate_token(self, service_name):
        """Generate a new JWT token for a service."""
        now = datetime.utcnow()
        jti = str(uuid.uuid4())

        payload = {
            'service': service_name,
            'iat': now,
            'exp': now + self.TOKEN_LIFETIME,
            'jti': jti,
        }

        token = jwt.encode(payload, self.signing_key, algorithm=self.algorithm)

        # Store token ID for revocation capability
        cache.set(f'service_token_{jti}', True, self.TOKEN_LIFETIME.total_seconds())

        return token

    def verify_token(self, token):
        """Verify and decode a service JWT token."""
        try:
            payload = jwt.decode(token, self.signing_key, algorithms=[self.algorithm])

            # Check if token has been revoked
            jti = payload.get('jti')
            if not cache.get(f'service_token_{jti}'):
                return None, "Token has been revoked"

            # Check if token needs refresh
            exp = datetime.fromtimestamp(payload['exp'])
            if exp - datetime.utcnow() < self.REFRESH_THRESHOLD:
                return payload, "refresh_needed"

            return payload, None

        except jwt.ExpiredSignatureError:
            return None, "Token has expired"
        except jwt.InvalidTokenError as e:
            return None, f"Invalid token: {str(e)}"

    def revoke_token(self, jti):
        """Revoke a token by its JTI."""
        cache.delete(f'service_token_{jti}')

# depot/middleware/service_auth.py
from functools import wraps
from django.http import JsonResponse

def require_service_auth(view_func):
    """Decorator to require valid service JWT."""
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Missing authentication'}, status=401)

        token = auth_header[7:]
        auth_manager = ServiceAuthManager()
        payload, error = auth_manager.verify_token(token)

        if not payload:
            return JsonResponse({'error': error}, status=401)

        # Add refresh header if needed
        if error == "refresh_needed":
            new_token = auth_manager.generate_token(payload['service'])
            request.META['X-New-Token'] = new_token

        request.service = payload['service']
        return view_func(request, *args, **kwargs)

    return wrapped_view
```

**2. Automatic Token Refresh in Client**
```python
# depot/services/internal_client.py
import requests
from django.conf import settings

class InternalServiceClient:
    """Client for internal service communication with auto-refresh."""

    def __init__(self, service_name='web-server'):
        self.service_name = service_name
        self.base_url = settings.SERVICES_URL
        self.auth_manager = ServiceAuthManager()
        self.current_token = None
        self._refresh_token()

    def _refresh_token(self):
        """Get a new token."""
        self.current_token = self.auth_manager.generate_token(self.service_name)

    def _make_request(self, method, endpoint, **kwargs):
        """Make HTTP request with automatic token refresh."""
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {self.current_token}'
        kwargs['headers'] = headers

        response = requests.request(method, url, **kwargs)

        # Check for new token in response
        new_token = response.headers.get('X-New-Token')
        if new_token:
            self.current_token = new_token

        # Retry once if unauthorized
        if response.status_code == 401:
            self._refresh_token()
            headers['Authorization'] = f'Bearer {self.current_token}'
            response = requests.request(method, url, **kwargs)

        return response

    def post(self, endpoint, **kwargs):
        return self._make_request('POST', endpoint, **kwargs)
```

---

### Option 3: HashiCorp Vault (Enterprise Grade)

#### Setup
```bash
# Install Vault
wget https://releases.hashicorp.com/vault/1.15.0/vault_1.15.0_linux_amd64.zip
unzip vault_1.15.0_linux_amd64.zip
sudo mv vault /usr/local/bin/

# Configure Vault
cat > /etc/vault/config.hcl << EOF
storage "file" {
  path = "/opt/vault/data"
}

listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = 1
}

api_addr = "http://127.0.0.1:8200"
EOF

# Initialize and unseal
vault operator init
vault operator unseal
```

#### Python Integration
```python
# depot/services/vault_manager.py
import hvac
from datetime import datetime

class VaultKeyManager:
    def __init__(self):
        self.client = hvac.Client(
            url='http://127.0.0.1:8200',
            token=settings.VAULT_TOKEN
        )

    def rotate_api_key(self):
        """Rotate the internal API key in Vault."""
        # Generate new key
        new_key = secrets.token_urlsafe(32)

        # Store with metadata
        self.client.secrets.kv.v2.create_or_update_secret(
            path='naaccord/api-keys',
            secret={
                'current': new_key,
                'previous': self.get_current_key(),
                'rotated_at': datetime.utcnow().isoformat(),
                'rotated_by': 'automated',
            }
        )

        # Trigger service reload
        self._reload_services()

        return new_key

    def get_current_key(self):
        """Get the current API key from Vault."""
        response = self.client.secrets.kv.v2.read_secret_version(
            path='naaccord/api-keys'
        )
        return response['data']['data']['current']
```

---

## Monitoring & Alerts

### Prometheus Metrics
```python
# depot/metrics.py
from prometheus_client import Counter, Histogram, Gauge

api_key_age = Gauge('api_key_age_days', 'Age of current API key in days')
api_key_rotation_count = Counter('api_key_rotations_total', 'Total number of key rotations')
api_key_auth_failures = Counter('api_key_auth_failures_total', 'Failed API key authentications')

# Update in rotation code
api_key_rotation_count.inc()
api_key_age.set(0)
```

### AlertManager Rules
```yaml
# prometheus/alerts.yml
groups:
  - name: api_key_alerts
    rules:
      - alert: APIKeyTooOld
        expr: api_key_age_days > 7
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "API key is {{ $value }} days old"
          description: "The internal API key should be rotated weekly"

      - alert: APIKeyAuthFailureSpike
        expr: rate(api_key_auth_failures_total[5m]) > 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High rate of API key authentication failures"
          description: "{{ $value }} failures per second - possible attack"
```

---

## Comparison Matrix

| Solution | Complexity | Cost | Security | Automation | Downtime |
|----------|------------|------|----------|------------|----------|
| Ansible | Low | Free | Good | Full | <1 min |
| JWT | Medium | Free | Better | Full | None |
| Vault | High | Free/Paid | Best | Full | None |

---

## Recommended Implementation Path

1. **Phase 1 (Immediate):** Implement Ansible rotation
   - Quick to deploy
   - Minimal code changes
   - Weekly rotation schedule

2. **Phase 2 (Month 1):** Add monitoring
   - Prometheus metrics
   - AlertManager rules
   - Rotation audit logs

3. **Phase 3 (Month 2):** Migrate to JWT
   - Zero-downtime rotation
   - Better security
   - Automatic refresh

4. **Phase 4 (Future):** Consider Vault
   - If handling real PHI
   - For compliance requirements
   - Enterprise features needed

---

## Quick Start Commands

```bash
# Install Ansible
sudo apt-get install ansible

# Encrypt secrets file
ansible-vault create secrets.yml

# Test rotation playbook
ansible-playbook rotate-api-keys.yml --check

# Run rotation manually
ansible-playbook rotate-api-keys.yml --vault-password-file=.vault_pass

# Setup cron job
echo "0 3 * * 0 ansible-playbook /opt/ansible/rotate-api-keys.yml" | crontab -
```