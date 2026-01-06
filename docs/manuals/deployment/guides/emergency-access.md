# Emergency Access Procedures for IT Team

**Purpose:** Document secure emergency access to NA-ACCORD when SAML is unavailable

## Authentication Design

NA-ACCORD uses **SAML-only authentication** in production. There is no password-based login through the web interface.

### Normal Operation

All users authenticate via:
- **Staging**: Mock-idp SAML provider
- **Production**: Johns Hopkins Shibboleth

### Emergency Scenarios

If SAML authentication is unavailable:
1. SAML IdP is down
2. SAML configuration broken
3. Network issues preventing SAML communication
4. Emergency user account needed outside SAML

## Emergency Access Method: Django Shell

### Prerequisites

- SSH access to services server (requires VPN + RADIUS 2FA)
- Sudo or root access on server
- Knowledge of Django ORM

### Step 1: SSH to Services Server

```bash
# Connect to VPN first (if production)

# Staging
ssh user@192.168.50.11

# Production
ssh user@10.150.96.37
```

### Step 2: Access Django Shell

```bash
# Navigate to application directory
cd /opt/naaccord

# Activate Django shell via Docker
docker exec -it naaccord-services python manage.py shell
```

### Step 3: Create Emergency Superuser

```python
from depot.models import User

# Create superuser
user = User.objects.create_superuser(
    username='emergency_admin',
    email='admin@naaccord.org',
    password='TEMPORARY_SECURE_PASSWORD'  # Change immediately
)

# Optionally: Make existing user superuser
user = User.objects.get(username='existing_user')
user.is_superuser = True
user.is_staff = True
user.save()

print(f"User {user.username} is now superuser")
```

### Step 4: Access Django Admin

1. Navigate to admin interface: `https://naaccord.yourdomain.com/admin/`
2. Login with emergency credentials
3. Perform necessary administrative actions
4. **CRITICAL**: Delete emergency account when done

### Step 5: Clean Up

```python
# In Django shell
from depot.models import User

# Delete emergency account
User.objects.filter(username='emergency_admin').delete()

# Or remove superuser privileges
user = User.objects.get(username='existing_user')
user.is_superuser = False
user.is_staff = False
user.save()
```

## Common Emergency Tasks

### Reset User Permissions

```python
from depot.models import User
from django.contrib.auth.models import Group

# Get user
user = User.objects.get(username='username')

# Add to group
group = Group.objects.get(name='Cohort Managers')
user.groups.add(group)

# Remove from group
user.groups.remove(group)

# List user's groups
for group in user.groups.all():
    print(group.name)
```

### Check SAML Configuration

```bash
# View SAML configuration
docker exec naaccord-web python manage.py shell

from django.conf import settings
print(settings.SAML_CONFIG)

# Check SAML metadata
cat /opt/naaccord/saml/metadata/idp_metadata.xml
```

### Verify Database Connectivity

```python
from django.db import connection

# Test database connection
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
    row = cursor.fetchone()
    print(f"Database connection: {'OK' if row[0] == 1 else 'FAIL'}")

# Check database encryption
cursor.execute("SHOW VARIABLES LIKE 'innodb_encrypt%'")
for row in cursor.fetchall():
    print(row)
```

### Clear Stuck Sessions

```python
from django.contrib.sessions.models import Session
from django.utils import timezone

# Delete expired sessions
Session.objects.filter(expire_date__lt=timezone.now()).delete()

# Delete all sessions (logs everyone out)
Session.objects.all().delete()
```

### Inspect Celery Queue

```bash
# Check Celery worker status
docker exec naaccord-celery celery -A depot inspect active

# Check queue length
docker exec naaccord-celery celery -A depot inspect reserved

# Purge all tasks (DESTRUCTIVE)
docker exec naaccord-celery celery -A depot purge -f
```

### Fix File Permissions

```bash
# On services server
sudo chown -R 1000:1000 /mnt/nas/submissions/
sudo chmod -R 755 /mnt/nas/

# Fix storage permissions
docker exec naaccord-services python manage.py shell

from pathlib import Path
import os

storage_path = Path('/opt/naaccord/storage')
for item in storage_path.rglob('*'):
    os.chown(item, 1000, 1000)
```

## Security Guidelines

### DO:
- Document all emergency access in audit log
- Use strong temporary passwords
- Delete emergency accounts immediately after use
- Limit emergency access to minimum necessary
- Coordinate with team before making changes

### DON'T:
- Create permanent password-based accounts
- Share emergency credentials
- Leave emergency accounts active
- Bypass audit logging
- Make changes without documentation

## Audit Trail

All emergency access should be documented:

```bash
# Log emergency access
echo "$(date): Emergency access by [YOUR_NAME] - Reason: [REASON]" | \
  sudo tee -a /var/log/naaccord/emergency-access.log
```

## Escalation Contacts

**System Issues:**
- DevOps Lead: [Contact info]
- Database Admin: [Contact info]

**SAML/Auth Issues:**
- Identity Management Team: [JHU IT contact]
- Security Team: [Contact info]

**Application Issues:**
- Development Team Lead: [Contact info]
- Project Manager: [Contact info]

## Related Documentation

- [Architecture Overview](architecture.md) - System design
- [Deployment Workflow](deployment-workflow.md) - Normal deployment procedures
- Main CLAUDE.md - Development and troubleshooting guide
