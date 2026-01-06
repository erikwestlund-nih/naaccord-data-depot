# Database Connectivity Architecture

## Overview

NA-ACCORD uses a DNS-based approach for database connectivity that works seamlessly across bare metal and Docker container environments.

## Architecture

### DNS Resolution via /etc/hosts

**Hostname:** `db.naaccord.internal`

| Environment | Resolves To | Purpose |
|-------------|-------------|---------|
| Host OS | `127.0.0.1` | Direct localhost connection |
| Docker containers | `172.18.0.1` | Gateway to host MariaDB |

### How It Works

1. **Ansible adds entry to `/etc/hosts`:**
   ```
   127.0.0.1   db.naaccord.internal
   ```

2. **Docker compose maps DNS to gateway:**
   ```yaml
   extra_hosts:
     - "db.naaccord.internal:172.18.0.1"
   ```

3. **Containers resolve `db.naaccord.internal` → `172.18.0.1`** (host's Docker gateway)

4. **MariaDB grants allow Docker subnet:**
   - Ansible auto-detects `naaccord_internal` network subnet
   - Extracts pattern (e.g., `172.18.%`)
   - Creates grants: `naaccord_app@'localhost'` and `naaccord_app@'172.18.%'`

## Ansible Implementation

### 1. Hosts Management Role

**File:** `deploy/ansible/roles/hosts_management/tasks/main.yml`

```yaml
- name: Add database hostname to /etc/hosts for Docker containers
  ansible.builtin.lineinfile:
    path: /etc/hosts
    regexp: '^.*\s+db\.naaccord\.internal\s*$'
    line: '127.0.0.1   db.naaccord.internal'
    state: present
    backup: yes
  tags: ['hosts', 'database']
```

### 2. MariaDB Role - Auto-Detect Docker Subnet

**File:** `deploy/ansible/roles/mariadb/tasks/main.yml`

```yaml
- name: Detect Docker internal network subnet
  ansible.builtin.shell: |
    docker network inspect naaccord_internal --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
  register: docker_subnet_result

- name: Extract Docker network pattern (e.g., 172.18.%)
  ansible.builtin.set_fact:
    docker_network_pattern: "{{ docker_subnet.split('.')[0] }}.{{ docker_subnet.split('.')[1] }}.%"

- name: Create user from Docker subnet
  ansible.builtin.shell: |
    mysql -e "CREATE USER IF NOT EXISTS 'naaccord_app'@'{{ docker_network_pattern }}' IDENTIFIED BY '{{ mariadb_app_password }}';"
```

### 3. Docker Services Role - Environment Variables

**File:** `deploy/ansible/roles/docker_services/defaults/main.yml`

```yaml
docker_env_vars:
  DATABASE_HOST: "db.naaccord.internal"  # DNS name from /etc/hosts
```

## Benefits

1. **No Hardcoded IPs:** Works regardless of Docker network configuration
2. **Automatic Subnet Detection:** Ansible detects and configures grants dynamically
3. **Consistent Naming:** Same DNS name works everywhere
4. **Secure:** Grants limited to specific Docker subnet, not `%`
5. **Web Server Ready:** Can point to remote database by changing DNS resolution

## Web Server Variation

For the web server connecting to remote database:

**Option 1 - Direct IP (current):**
```yaml
# /etc/hosts on web server
10.100.0.11   db.naaccord.internal  # WireGuard IP to services server
```

**Option 2 - Local fallback:**
```yaml
# For development/fallback
127.0.0.1   db-local.naaccord.internal
10.100.0.11  db.naaccord.internal
```

## Troubleshooting

### Container can't connect to database

1. **Check DNS resolution in container:**
   ```bash
   docker exec naaccord-services getent hosts db.naaccord.internal
   # Should show: 172.18.0.1   db.naaccord.internal
   ```

2. **Verify Docker network:**
   ```bash
   docker network inspect naaccord_internal | jq '.[0].IPAM.Config[0]'
   # Should show gateway: 172.18.0.1
   ```

3. **Check MariaDB grants:**
   ```bash
   sudo mysql -e "SELECT user, host FROM mysql.user WHERE user='naaccord_app';"
   # Should show: naaccord_app | localhost
   #              naaccord_app | 172.18.%
   ```

4. **Test connection from container:**
   ```bash
   docker exec naaccord-services python manage.py dbshell
   ```

### Network subnet changed

If Docker network subnet changes, re-run MariaDB role:

```bash
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --connection local \
  --vault-password-file=~/.naaccord_vault_staging \
  --tags mariadb,docker
```

## Related Files

- `deploy/ansible/roles/hosts_management/tasks/main.yml` - /etc/hosts management
- `deploy/ansible/roles/mariadb/tasks/main.yml` - User grants with subnet detection
- `deploy/ansible/roles/docker_services/defaults/main.yml` - DATABASE_HOST config
- `docker-compose.prod.yml` - extra_hosts mapping
