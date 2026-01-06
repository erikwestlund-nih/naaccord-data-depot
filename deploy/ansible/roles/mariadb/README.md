# MariaDB Role

## Overview

Installs and configures MariaDB database server with encryption at rest for NA-ACCORD PHI data storage. Implements HIPAA-compliant database encryption using MariaDB's file-key-management plugin.

## Purpose

NA-ACCORD stores all application data (user accounts, cohort information, audit metadata, etc.) in MariaDB. This role ensures:
- **Encryption at rest** for all tables and logs
- **Secure credential management** via Ansible vault
- **Performance optimization** for clinical data workloads
- **HIPAA compliance** with comprehensive audit logging
- **Isolation** on services server (no direct external access)

## What It Does

1. **Installs MariaDB server** and required Python libraries
2. **Generates encryption keys** using OpenSSL (256-bit AES)
3. **Configures encryption** for tables, logs, temp files, and binlog
4. **Secures installation** (removes test DB, anonymous users)
5. **Sets root password** from vault
6. **Creates naaccord database** with UTF-8 character set
7. **Creates application user** with appropriate privileges
8. **Enables service** for automatic startup
9. **Verifies encryption** is active

## Requirements

- Root/sudo access
- Rocky Linux/RHEL 9
- Vault credentials configured
- Minimum 2GB RAM (4GB+ recommended)
- Services server only (not needed on web server)

## Variables

### Required (from vault)
- `vault_mariadb_root_password` - MySQL root password
- `vault_mariadb_app_password` - Application user password

### Optional (with defaults)
- `mariadb_database` - Database name (default: `naaccord`)
- `mariadb_app_user` - Application username (default: `naaccord_app`)
- `mariadb_app_host` - Host pattern for app user (default: `%` for Docker)
- `mariadb_encryption_enabled` - Enable encryption (default: `yes`)
- `mariadb_bind_address` - Network binding (default: `0.0.0.0`)
- `mariadb_port` - Server port (default: `3306`)
- `mariadb_max_connections` - Max connections (default: `200`)
- `mariadb_innodb_buffer_pool_size` - Buffer pool size (default: `1G`)

See [defaults/main.yml](defaults/main.yml) for complete variable list.

## Dependencies

- None (base role should run first for system setup)

## Usage

Applied automatically by `playbooks/services-server.yml`.

Can also be run standalone:
```bash
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/services-server.yml \
  --tags mariadb \
  --ask-vault-pass
```

## Vault Configuration

Credentials must be stored in encrypted vault file at:
- `inventories/staging/group_vars/vault.yml` (staging)
- `inventories/production/group_vars/vault.yml` (production)

**Required vault variables:**
```yaml
---
vault_mariadb_root_password: "strong_root_password_here"
vault_mariadb_app_password: "strong_app_password_here"
```

**Generate strong passwords:**
```bash
# Root password (64 characters)
openssl rand -base64 48

# App password (48 characters)
openssl rand -base64 36
```

**Update vault:**
```bash
# Staging
echo "changeme" | ansible-vault edit inventories/staging/group_vars/vault.yml --vault-password-file=/dev/stdin

# Production
ansible-vault edit inventories/production/group_vars/vault.yml --ask-vault-pass
```

## Encryption Details

### File-Key-Management Plugin

MariaDB's encryption at rest uses the `file_key_management` plugin with:
- **Algorithm**: AES-CBC (256-bit)
- **Key Storage**: `/etc/mysql/encryption/keyfile` (mode 0600, owner mysql)
- **Key Format**: `<key_id>;<hex_key>` (key_id=1, 64 hex chars = 256 bits)
- **Key Rotation**: Automatic based on `innodb_encryption_rotate_key_age`

### What Is Encrypted

- **InnoDB Tables**: All tables encrypted by default (`innodb_encrypt_tables = ON`)
- **InnoDB Logs**: Redo logs encrypted (`innodb_encrypt_log = ON`)
- **Temporary Tables**: Disk-based temp tables encrypted (`encrypt_tmp_disk_tables = ON`)
- **Temporary Files**: Temp files encrypted (`encrypt_tmp_files = ON`)
- **Binary Logs**: Binlog encrypted if enabled (`encrypt_binlog = ON`)
- **Aria Tables**: Aria storage engine tables encrypted (`aria_encrypt_tables = ON`)

### Key Management Security

- Encryption key generated once during initial deployment
- Key owned by `mysql:mysql` with mode `0600` (read/write by mysql only)
- Key never logged or displayed in Ansible output (`no_log: true`)
- Key persists across MariaDB restarts and upgrades
- Key rotation supported (change key, run `ALTER TABLE` to re-encrypt)

## Database Structure

**Database:** `naaccord`
- **Character Set**: `utf8mb4` (full Unicode support)
- **Collation**: `utf8mb4_unicode_ci` (case-insensitive Unicode)
- **Encryption**: Enabled by default for all tables

**Users:**
- `root@localhost` - Full privileges (root password from vault)
- `naaccord_app@%` - App-only privileges (password from vault)
  - Privileges: `ALL` on `naaccord.*` database
  - Can connect from any host (`%`) - needed for Docker containers

**Removed for Security:**
- Anonymous users (blank username)
- Test database

## Performance Tuning

Default configuration optimized for 4GB RAM server with moderate load:

```ini
innodb_buffer_pool_size = 1G          # 25% of RAM (adjust for your server)
innodb_log_file_size = 256M           # Large enough for write bursts
innodb_flush_log_at_trx_commit = 2    # Balanced durability/performance
innodb_flush_method = O_DIRECT        # Reduce double-buffering
max_connections = 200                 # Support Django + Celery workers
```

**For production with 8GB+ RAM:**
```yaml
# In inventory group_vars or playbook vars
mariadb_innodb_buffer_pool_size: "2G"
mariadb_max_connections: 300
```

## Security Features

1. **No remote root access** - Root only from localhost
2. **Strong passwords** - Generated, stored in vault, never logged
3. **Encryption at rest** - All data encrypted on disk
4. **Firewall isolation** - Only accessible from services server (firewall role)
5. **No test data** - Test database and anonymous users removed
6. **Audit logging** - Slow query log enabled for performance monitoring
7. **Disabled features** - `local_infile` disabled to prevent file injection

## Verification

After running the role, verify installation:

```bash
# Check service status
sudo systemctl status mariadb

# Verify encryption is enabled
sudo mysql -u root -p -e "SHOW VARIABLES LIKE 'innodb_encrypt%';"
# Should show:
# innodb_encrypt_log                 | ON
# innodb_encrypt_tables               | ON
# innodb_encryption_rotate_key_age    | 1
# innodb_encryption_threads           | 4

# Check database exists
sudo mysql -u root -p -e "SHOW DATABASES;"
# Should include: naaccord

# Verify app user can connect
mysql -u naaccord_app -p -h localhost -e "USE naaccord; SHOW TABLES;"

# Check encryption key exists
sudo ls -la /etc/mysql/encryption/keyfile
# Should show: -rw------- 1 mysql mysql 68 <date> keyfile
```

## Django Integration

Django connects using credentials from vault:

**Environment variables for Django container:**
```bash
DATABASE_HOST=10.100.0.11              # Services server via WireGuard
DATABASE_PORT=3306
DATABASE_NAME=naaccord
DATABASE_USER=naaccord_app
DATABASE_PASSWORD=${vault_mariadb_app_password}
```

**Django settings.py:**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ['DATABASE_NAME'],
        'USER': os.environ['DATABASE_USER'],
        'PASSWORD': os.environ['DATABASE_PASSWORD'],
        'HOST': os.environ['DATABASE_HOST'],
        'PORT': os.environ['DATABASE_PORT'],
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}
```

## Backup Strategy

Backup directory created at `/var/backups/mariadb/` (owned by mysql).

**Manual backup:**
```bash
# Full database dump
sudo mysqldump -u root -p --all-databases --single-transaction \
  --routines --triggers --events \
  | gzip > /var/backups/mariadb/naaccord-$(date +%Y%m%d-%H%M%S).sql.gz

# Specific database only
sudo mysqldump -u root -p naaccord --single-transaction \
  | gzip > /var/backups/mariadb/naaccord-db-$(date +%Y%m%d-%H%M%S).sql.gz
```

**Automated backups** (coming in later phase):
- Cron job for daily dumps
- Rotation policy (7 days local, 30 days NAS)
- Backup encryption before NAS transfer
- Restore testing procedures

## Troubleshooting

### MariaDB won't start

```bash
# Check logs
sudo journalctl -u mariadb -n 50
sudo tail -f /var/log/mariadb/mariadb.log

# Check config syntax
sudo mysqld --verbose --help | head -20

# Verify encryption key permissions
sudo ls -la /etc/mysql/encryption/
# Should be: drwx------ 2 mysql mysql
# And: -rw------- 1 mysql mysql <size> keyfile
```

### Encryption plugin errors

```bash
# Check plugin is loaded
sudo mysql -u root -p -e "SHOW PLUGINS;" | grep file_key

# Verify encryption config
sudo cat /etc/my.cnf.d/naaccord-encryption.cnf

# Check key file format
sudo cat /etc/mysql/encryption/keyfile
# Should show: 1;<64 hex characters>
```

### Can't connect from Docker

```bash
# Verify bind address
sudo mysql -u root -p -e "SHOW VARIABLES LIKE 'bind_address';"
# Should show: 0.0.0.0 (or specific IP)

# Check user host permissions
sudo mysql -u root -p -e "SELECT user, host FROM mysql.user WHERE user='naaccord_app';"
# Should show: naaccord_app | %

# Test from localhost first
mysql -u naaccord_app -p -h localhost naaccord

# Check firewall (if enabled)
sudo firewall-cmd --list-all
```

### Root password doesn't work

```bash
# Reset via safe mode (emergency only)
sudo systemctl stop mariadb
sudo mysqld_safe --skip-grant-tables &
mysql -u root
# In MySQL prompt:
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED BY 'new_password';
FLUSH PRIVILEGES;
EXIT;
sudo pkill mysqld
sudo systemctl start mariadb
```

### Performance issues

```bash
# Check buffer pool usage
sudo mysql -u root -p -e "SHOW STATUS LIKE 'Innodb_buffer_pool%';"

# Review slow queries
sudo cat /var/log/mariadb/mariadb-slow.log

# Check current connections
sudo mysql -u root -p -e "SHOW PROCESSLIST;"

# Increase buffer pool size
# Edit inventory vars: mariadb_innodb_buffer_pool_size: "2G"
# Re-run playbook
```

## Idempotence

Role is fully idempotent and can be run multiple times safely:
- Encryption key only generated if missing
- Root password set once (checks if already set)
- Database and users created with `state: present` (skips if exists)
- Configuration files templated (changes trigger restart)

## HIPAA Compliance

This role implements HIPAA security requirements:

- **164.312(a)(2)(iv)**: Encryption at rest via file-key-management
- **164.312(b)**: Audit controls via query logging
- **164.312(c)(1)**: Integrity controls via encryption verification
- **164.312(d)**: Access control via user authentication and privileges

**Additional compliance notes:**
- Credentials never logged (all password tasks use `no_log: true`)
- Encryption keys protected with strict file permissions
- Remote access restricted by firewall role
- Audit trail available in slow query log and binary logs (if enabled)

## Related Documentation

- [MariaDB Encryption Documentation](https://mariadb.com/kb/en/data-at-rest-encryption/)
- [File Key Management Plugin](https://mariadb.com/kb/en/file-key-management-encryption-plugin/)
- [../../VAULT-PRODUCTION.md](../../VAULT-PRODUCTION.md) - Vault security guide
- [../firewall/README.md](../firewall/README.md) - Network security
- [../../deploy-steps.md](../../deploy-steps.md) - Deployment workflow
