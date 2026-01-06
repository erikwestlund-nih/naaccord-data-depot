# Database Access Guide

## Overview

This document describes database access patterns, user accounts, and safe data modification practices for NA-ACCORD production and staging environments.

## Database User Accounts

| User | Purpose | Grants | Networks | Use Case |
|------|---------|--------|----------|----------|
| `root` | Emergency/disaster recovery | ALL | localhost | Server crashes, corruption, true disasters |
| `naaccord_app` | Django application | ALL on naaccord.* | localhost, Docker subnets, WireGuard tunnel | Normal operations (via Django) |
| `naaccord_admin` | Debugging/analysis | SELECT on naaccord.* | localhost, Docker subnets, WireGuard tunnel | TablePlus inspection, query analysis |

### Network Access Patterns

Each user (except root) has grants from multiple network locations:

- **localhost** - Direct connections on services server
- **Docker subnets** (`172.18.%`, `172.19.%`, `172.20.%`) - Container connections
- **WireGuard tunnel** (`10.100.0.%`) - Cross-server PHI tunnel
- **WireGuard bridge** (`10.101.0.%`) - WireGuard container to database

## Accessing the Database

### Method 1: Django Shell (RECOMMENDED)

**Use this for all data modifications.**

```bash
# SSH to services server
ssh mrpznaaccorddb01.hosts.jhmi.edu

# Enter Django shell
docker exec -it naaccord-services python manage.py shell

# Use Django ORM
from depot.models import User, Cohort, Audit
user = User.objects.get(username='erikwestlund')
user.is_active = True
user.save()  # Triggers signals, validation, audit trails
```

**Why Django shell?**
- ✅ Data validation through model clean() methods
- ✅ Audit trail via signal handlers
- ✅ PHI tracking for file operations
- ✅ Business logic enforcement
- ✅ Foreign key integrity checks
- ✅ Consistent with application behavior

### Method 2: TablePlus (Read-Only Analysis)

**Use this for debugging, query analysis, and data inspection.**

#### Connection Setup

1. **Create SSH Tunnel Connection**
   - Connection Type: MariaDB
   - Connection Method: Over SSH

2. **SSH Configuration**
   - Host: `mrpznaaccorddb01.hosts.jhmi.edu` (production) or `192.168.50.11` (staging)
   - Port: `22`
   - User: `<your-jhu-username>`
   - Authentication: Password (RADIUS/MFA)

3. **Database Configuration**
   - Host: `localhost` (or `127.0.0.1`)
   - Port: `3306`
   - User: `naaccord_admin`
   - Password: `<from vault: vault_mariadb_admin_password>`
   - Database: `naaccord`

#### SSH Tunnel with MFA

**JHU servers use RADIUS authentication with MFA.** Here's how it works:

1. TablePlus establishes SSH connection
2. You authenticate with password + MFA token
3. SSH tunnel remains open for the session
4. All database queries go through the tunnel
5. No need to re-authenticate for each query

**Connection stays alive** as long as TablePlus is running, so you won't need to MFA repeatedly.

#### Recommended TablePlus Settings

- **Read-only mode:** Enable in TablePlus preferences (prevents accidental writes)
- **Query timeout:** Set to 30 seconds (prevents runaway queries)
- **Max rows:** Limit to 1000 (prevents accidentally pulling entire tables)

### Method 3: Direct MariaDB Client

**For emergencies only.**

```bash
# SSH to services server
ssh mrpznaaccorddb01.hosts.jhmi.edu

# Connect as naaccord_admin (read-only)
mysql -u naaccord_admin -p naaccord

# Or connect as root (emergency only)
sudo mysql -u root -p naaccord
```

## Data Modification Policy

### Default Approach: Django Shell

**ALL data modifications should use Django shell unless documented emergency.**

```bash
# Example: Fixing user account
docker exec -it naaccord-services python manage.py shell

from depot.models import User
user = User.objects.get(username='researcher01')
user.email = 'newemail@jhu.edu'
user.save()  # Safe - triggers validation and audit
```

### Emergency Direct SQL (Rare)

Only use direct SQL for:
- Database corruption repair
- Emergency data restoration
- Schema-level fixes that can't go through Django
- Disaster recovery scenarios

**If you must use direct SQL:**
1. Document the change in incident log
2. Test on staging first if possible
3. Take database backup before making change
4. Use transactions (BEGIN; ... COMMIT; or ROLLBACK;)
5. Verify foreign key integrity after change
6. Update Django-managed audit trails manually if needed

## PHI Considerations

**Most database data is NOT PHI:**
- User accounts and permissions ❌ Not PHI
- Cohort metadata ❌ Not PHI
- Audit/submission records ❌ Not PHI
- File tracking logs ❌ Not PHI
- Data definitions ❌ Not PHI

**PHI exists only in:**
- ✅ Uploaded data files (tracked by PHIFileTracking)
- ✅ Temporary processing files (cleanup monitored)
- ✅ NAS storage (encrypted at rest)

The database uses **de-identified cohortPatientId only** - no names, dates of birth, or other direct identifiers.

## Password Management

### Staging

Passwords stored in:
```
/Users/erikwestlund/code/naaccord/deploy/ansible/inventories/staging/group_vars/all/vault.yml
```

Decrypt with:
```bash
cd /Users/erikwestlund/code/naaccord/deploy/ansible/inventories/staging/group_vars/all
ansible-vault decrypt vault.yml
# Enter vault password
```

### Production

Passwords stored in:
```
/Users/erikwestlund/code/naaccord/deploy/ansible/inventories/production/group_vars/all/vault.yml
```

**Vault password:** Stored in password manager (1Password/LastPass)

## Troubleshooting

### Cannot connect via TablePlus

**Symptom:** Connection timeout or refused

**Check:**
1. SSH tunnel is working: `ssh <user>@<host>` should succeed
2. MariaDB is running on services server: `systemctl status mariadb`
3. Firewall allows SSH (port 22)
4. Using correct credentials from vault

### "Access denied for user 'naaccord_admin'"

**Check:**
1. Password matches vault: `ansible-vault view vault.yml | grep mariadb_admin_password`
2. User exists: `mysql -u root -p -e "SELECT User, Host FROM mysql.user WHERE User='naaccord_admin';"`
3. Grants are correct: `mysql -u root -p -e "SHOW GRANTS FOR 'naaccord_admin'@'localhost';"`

### Need to modify data but Django shell not working

**If containers are down:**
1. Check container status: `docker ps -a`
2. Restart services: `docker restart naaccord-services`
3. Check logs: `docker logs naaccord-services`

**If Django shell crashes:**
1. Use direct MySQL as root (emergency only)
2. Document what you changed
3. File bug report for Django shell issue

### WireGuard tunnel down, web server can't reach database

**Symptom:** Web server shows database connection errors

**Check:**
1. WireGuard container running: `docker ps | grep wireguard`
2. Tunnel interface exists: `docker exec wireguard-client wg show`
3. Can ping services server: `ping 10.100.0.11` (from web server)
4. Restart WireGuard: `docker restart wireguard-client wireguard-server`

## Security Best Practices

1. **Never share database passwords** via email, Slack, or unencrypted channels
2. **Use vault** for all credential storage
3. **Rotate passwords** when team members leave
4. **Audit database access** regularly (check mysql.user table)
5. **Use read-only account** (naaccord_admin) for analysis when possible
6. **Document all direct SQL changes** in incident log
7. **Test on staging first** before production database changes

## Related Documentation

- [Production Differences](production-differences.md) - Database section
- [Emergency Access](../docs/deployment/guides/emergency-access.md) - Emergency procedures
- [CLAUDE.md](../CLAUDE.md) - Main development guide
- [MariaDB Role](../ansible/roles/mariadb/README.md) - Ansible configuration

---

**Document Version:** 1.0
**Last Updated:** 2025-10-10
**Owner:** Development Team
**Next Review:** After production deployment
