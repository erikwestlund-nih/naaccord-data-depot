# NA-ACCORD Troubleshooting Guide

**Comprehensive troubleshooting for common issues across development, deployment, and production environments**

**Last Updated:** 2025-10-15

---

## Table of Contents

1. [Development Environment](#development-environment)
2. [Database Issues](#database-issues)
3. [Container and Docker Issues](#container-and-docker-issues)
4. [WireGuard Tunnel Issues](#wireguard-tunnel-issues)
5. [File Upload and Storage Issues](#file-upload-and-storage-issues)
6. [Celery and Async Processing](#celery-and-async-processing)
7. [R and NAATools Issues](#r-and-naatools-issues)
8. [Authentication and SAML](#authentication-and-saml)
9. [Frontend and Static Assets](#frontend-and-static-assets)
10. [Ansible Deployment](#ansible-deployment)
11. [Performance Issues](#performance-issues)
12. [Production-Specific Issues](#production-specific-issues)

---

## Development Environment

### Issue: Users don't see cohorts in sidebar after database reset

**Symptom:** After running database migrations or reset, users can log in but don't see any cohorts in the sidebar.

**Cause:** Missing `CohortMembership` records or user-group associations not set up.

**Solution:**
```bash
# Complete environment reset (RECOMMENDED - 4 seconds)
python manage.py reset_dev_complete --skip-confirmation

# OR manual fix if database already seeded
python manage.py assign_test_users_to_groups

# Verify users are in groups
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> u = User.objects.get(username='testuser')
>>> print(u.groups.all())  # Should show groups
>>> print(u.cohortmembership_set.all())  # Should show cohorts
```

### Issue: Port already in use (8000, 8001, 5173)

**Symptom:** `Address already in use` error when starting Django or npm dev server.

**Solution:**
```bash
# Find process using port
lsof -i :8000
lsof -i :8001
lsof -i :5173

# Kill process (replace PID)
kill -9 <PID>

# Or use pkill
pkill -f "runserver"
pkill -f "vite"
```

### Issue: tmux session management

**Symptom:** Services not running or need to restart individual tmux windows.

**Solution:**
```bash
# List all tmux sessions
command tmux list-sessions

# Attach to existing session
tmux attach -t na

# Restart specific service (from inside tmux)
# Navigate to window: Ctrl+b, then window number
# Stop service: Ctrl+c
# Restart: up arrow, Enter

# Restart Celery worker (example)
command tmux send-keys -t na:celery C-c
command tmux send-keys -t na:celery "source venv/bin/activate && celery -A depot worker -l info" C-m

# Kill entire session and restart
tmux kill-session -t na
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

### Issue: Python virtual environment not activated

**Symptom:** `ModuleNotFoundError` or wrong Python version.

**Solution:**
```bash
# Activate virtual environment
source venv/bin/activate

# Verify activation
which python  # Should show path to venv/bin/python
python --version  # Should be 3.8+

# Reinstall dependencies if needed
pip install -r requirements.txt
```

### Issue: NAS mount not accessible (development)

**Symptom:** `FileNotFoundError` when accessing `/mnt/nas/` or storage operations fail.

**Solution:**
```bash
# Check if NAS is mounted
ls /mnt/nas/

# For development, use local storage
export ENABLE_NAS_STORAGE=false
export SCRATCH_STORAGE_DISK=local

# Or mount NAS manually (macOS)
mkdir -p /mnt/nas
sudo mount_smbfs //192.168.1.10/na-accord /mnt/nas
```

---

## Database Issues

### Issue: Database connection refused

**Symptom:** `Can't connect to MySQL server` or `Connection refused` error.

**Cause:** MariaDB container not running or wrong connection settings.

**Solution:**
```bash
# Check if MariaDB container is running
docker ps | grep mariadb

# Start services with Docker Compose
docker compose -f docker-compose.dev.yml up -d mariadb

# Check container logs
docker logs naaccord-mariadb

# Verify connection settings in .env
DATABASE_HOST=localhost  # or 10.100.0.11 for WireGuard
DATABASE_PORT=3306
DATABASE_NAME=naaccord
DATABASE_USER=naaccord
DATABASE_PASSWORD=<password>

# Test connection manually
mysql -h localhost -P 3306 -u naaccord -p
```

### Issue: Migration conflicts or failures

**Symptom:** `Conflicting migrations detected` or migration fails with database error.

**Solution:**
```bash
# Reset database completely (CAUTION: deletes all data)
python manage.py reset_db

# Run migrations from scratch
python manage.py migrate

# Seed initial data
python manage.py seed_init

# Load test users and assign to groups
python manage.py load_test_users
python manage.py assign_test_users_to_groups

# Or use complete reset (recommended)
python manage.py reset_dev_complete --skip-confirmation
```

### Issue: Foreign key constraint failures

**Symptom:** `Cannot add or update a child row: a foreign key constraint fails`

**Cause:** Attempting to create records that reference non-existent related objects.

**Solution:**
```bash
# Verify seed data was loaded
python manage.py shell
>>> from depot.models import Cohort, DataFileType, ProtocolYear
>>> print(Cohort.objects.count())  # Should be 31
>>> print(DataFileType.objects.count())  # Should be > 0
>>> print(ProtocolYear.objects.count())  # Should be > 0

# If missing, run seed_init
python manage.py seed_init
```

### Issue: Database locked (SQLite only)

**Symptom:** `database is locked` error during tests.

**Cause:** Multiple processes accessing SQLite database simultaneously.

**Solution:**
```bash
# Use keepdb flag to prevent database recreation
python manage.py test --settings=depot.test_settings --keepdb

# Or use fresh database each time
python manage.py test --settings=depot.test_settings

# For development, use MariaDB instead of SQLite
# Edit settings.py to use docker-compose MariaDB
```

---

## Container and Docker Issues

### Issue: Container fails to start

**Symptom:** Container exits immediately or shows `Exited (1)` status.

**Solution:**
```bash
# Check container logs
docker logs naaccord-services
docker logs naaccord-web
docker logs naaccord-celery

# Check for common issues:
# 1. Environment variables not set
docker exec naaccord-services env | grep SERVER_ROLE

# 2. Database not accessible
docker exec naaccord-services python manage.py check --database default

# 3. Permissions issues
docker exec naaccord-services ls -la /app/

# Restart container
docker restart naaccord-services
```

### Issue: Container can't connect to other containers

**Symptom:** `Connection refused` when containers try to communicate.

**Cause:** Network misconfiguration or wrong IP addresses.

**Solution:**
```bash
# Check container networks
docker network inspect naaccord_services-net

# Verify container IPs
docker inspect naaccord-services | grep IPAddress
docker inspect naaccord-mariadb | grep IPAddress

# Check environment variables
docker exec naaccord-services env | grep DATABASE_HOST
docker exec naaccord-web env | grep SERVICES_URL

# For web→services communication, should use WireGuard IPs
docker exec naaccord-web ping 10.100.0.11
```

### Issue: Docker Compose profile issues

**Symptom:** Wrong containers start or services missing.

**Solution:**
```bash
# Use correct profile for environment
# Development (local single machine)
docker compose -f docker-compose.dev.yml up -d

# Staging/Production - web server
docker compose -f docker-compose.prod.yml --profile web up -d

# Staging/Production - services server
docker compose -f docker-compose.prod.yml --profile services up -d
```

### Issue: Container storage full

**Symptom:** `No space left on device` error.

**Solution:**
```bash
# Check Docker disk usage
docker system df

# Clean up unused images and containers
docker system prune -a

# Clean up volumes (CAUTION: may delete data)
docker volume prune

# Check specific volume usage
docker volume ls
docker volume inspect naaccord_mariadb_data
```

---

## WireGuard Tunnel Issues

### Issue: 0 B received in WireGuard tunnel

**Symptom:** `wg show` reports `transfer: 0 B received` and handshake timestamp is `0`.

**Cause:** Public key mismatch - peer's public key doesn't match their private key.

**Solution:**
```bash
# Regenerate public keys from existing private keys
cat web-private.key | wg pubkey > web-public.key
cat services-private.key | wg pubkey > services-public.key

# Update Docker secrets or Ansible vault with correct public keys

# Verify keys match
cat web-private.key | wg pubkey
cat web-public.key
# These two should match EXACTLY

# Redeploy WireGuard containers
docker restart naaccord-wireguard-web
docker restart naaccord-wireguard-services

# Verify handshake after restart
docker exec naaccord-wireguard-web wg show
# Should show recent handshake timestamp and data transfer
```

### Issue: Connection timeout to 10.100.0.11

**Symptom:** Web container can't reach services through tunnel.

**Cause:** iptables forwarding rules not configured or services on wrong network.

**Solution:**
```bash
# Check WG_FORWARD_PORTS environment variable
docker inspect naaccord-wireguard-services | grep WG_FORWARD_PORTS

# Verify iptables rules
docker exec naaccord-wireguard-services iptables -t nat -L PREROUTING -n -v
# Should show DNAT rules for ports 3306, 6379, 8001

# Verify services have static IPs on 10.101.0.0/24
docker network inspect naaccord_services-net

# Test connectivity
docker exec naaccord-web ping -c 3 10.100.0.11
docker exec naaccord-web curl -s http://10.100.0.11:8001/health/
```

### Issue: WireGuard container permission denied

**Symptom:** `Operation not permitted` when starting WireGuard container.

**Cause:** Missing NET_ADMIN and SYS_MODULE capabilities.

**Solution:**
```yaml
# In docker-compose.yml, ensure capabilities are set:
services:
  wireguard-web:
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    # Also for Docker on macOS/Windows
    privileged: true  # Only if cap_add doesn't work
```

---

## File Upload and Storage Issues

### Issue: File upload hangs or times out

**Symptom:** Large file uploads (>100MB) hang indefinitely or timeout.

**Cause:** Insufficient timeout settings, memory limits, or streaming issues.

**Solution:**
```python
# In settings.py, increase timeouts
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB (files larger stream to disk)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880

# In Nginx configuration
client_max_body_size 2G;
client_body_timeout 300s;
proxy_read_timeout 300s;

# For Celery tasks processing files
@shared_task(time_limit=3600, soft_time_limit=3300)
def process_large_file(file_path):
    # Processing code
    pass
```

### Issue: "Storage directory not writable"

**Symptom:** File uploads fail with permission errors.

**Cause:** Container doesn't have write permissions to storage directories.

**Solution:**
```bash
# Check permissions on host (development)
ls -la storage/
sudo chmod -R 755 storage/

# Check NAS mount permissions (production)
ls -la /mnt/nas/
# Should show naaccord:naaccord ownership

# Inside container
docker exec naaccord-services touch /app/storage/scratch/test.txt
docker exec naaccord-services rm /app/storage/scratch/test.txt

# Check environment variables
docker exec naaccord-services env | grep STORAGE
```

### Issue: RemoteStorageDriver fails with 500 error

**Symptom:** File operations fail with `HTTP 500 Internal Server Error`.

**Cause:** Services server not reachable, API key missing, or path traversal protection triggering.

**Solution:**
```bash
# Verify INTERNAL_API_KEY is set on both servers
docker exec naaccord-web env | grep INTERNAL_API_KEY
docker exec naaccord-services env | grep INTERNAL_API_KEY
# Should match

# Check services URL
docker exec naaccord-web env | grep SERVICES_URL
# Should be http://10.100.0.11:8001

# Test internal API directly
docker exec naaccord-web curl -H "X-Internal-API-Key: <key>" \
  http://10.100.0.11:8001/internal/storage/health

# Check services logs
docker logs naaccord-services | grep "Internal API"
```

### Issue: PHI file tracking warnings

**Symptom:** Warnings about files not being cleaned up or missing tracking records.

**Solution:**
```bash
# Show PHI audit trail
python manage.py show_phi_audit_trail --cohort 5 --days 7

# Verify cleanup completion
python manage.py verify_phi_cleanup

# Check for overdue cleanup
python manage.py shell
>>> from depot.models import PHIFileTracking
>>> overdue = PHIFileTracking.objects.filter(
...     cleanup_required=True,
...     cleanup_completed_at__isnull=True,
...     expected_cleanup_by__lt=timezone.now()
... )
>>> print(overdue.count())

# Manually mark as cleaned (if verified)
>>> for record in overdue:
...     record.cleanup_completed_at = timezone.now()
...     record.save()
```

---

## Celery and Async Processing

### Issue: Celery worker not processing tasks

**Symptom:** Tasks stuck in `PENDING` state, no log output from worker.

**Solution:**
```bash
# Check if Celery worker is running
ps aux | grep celery

# Check Celery logs
tail -f /var/log/celery/worker.log

# In tmux session
tmux attach -t na
# Navigate to celery window (Ctrl+b, then 3)

# Restart Celery worker
command tmux send-keys -t na:celery C-c
command tmux send-keys -t na:celery "source venv/bin/activate && celery -A depot worker -l info" C-m

# Or restart via Docker
docker restart naaccord-celery

# Check Redis connection
docker exec naaccord-services redis-cli ping
# Should return: PONG
```

### Issue: Task execution fails with import errors

**Symptom:** Celery worker logs show `ModuleNotFoundError` or import errors.

**Cause:** Celery worker not using same environment as Django or missing dependencies.

**Solution:**
```bash
# Verify Celery worker uses same Python environment
which celery  # Should be in venv/bin/celery

# Reinstall dependencies
pip install -r requirements.txt

# Restart Celery worker
pkill -f celery
celery -A depot worker -l info

# Check task registration
celery -A depot inspect registered
```

### Issue: Tasks timeout or run too long

**Symptom:** Long-running tasks killed or timeout errors.

**Solution:**
```python
# In tasks.py, adjust task time limits
@shared_task(
    time_limit=3600,  # Hard limit (1 hour)
    soft_time_limit=3300,  # Soft limit (55 minutes)
    bind=True  # For self.retry()
)
def long_running_task(self, file_path):
    try:
        # Processing code
        pass
    except SoftTimeLimitExceeded:
        # Cleanup and retry
        self.retry(countdown=60, max_retries=3)
```

### Issue: Celery result backend errors

**Symptom:** `redis.exceptions.ConnectionError` or results not persisting.

**Solution:**
```bash
# Check Redis container
docker ps | grep redis

# Verify Redis URL
echo $CELERY_RESULT_BACKEND
# Should be: redis://10.100.0.11:6379/0

# Test Redis connection
redis-cli -h 10.100.0.11 -p 6379 ping

# Check Redis memory usage
redis-cli -h 10.100.0.11 -p 6379 INFO memory
```

---

## R and NAATools Issues

### Issue: NAATools not found in R

**Symptom:** `Error: package 'NAATools' not found` when running audit tasks.

**Solution:**
```r
# Install NAATools from GitHub
install.packages("remotes")
remotes::install_github("JHBiostatCenter/naaccord-r-tools")

# Verify installation
library(NAATools)
packageVersion("NAATools")
```

### Issue: Development mode not working

**Symptom:** R loads installed NAATools instead of local development version.

**Solution:**
```bash
# Create .r_dev_mode file in depot directory
cat > .r_dev_mode <<EOF
NAATOOLS_DIR=$HOME/code/NAATools
EOF

# Verify in R
Sys.getenv("NAATOOLS_DIR")
# Should show your local NAATools path

# Reinstall dependencies if needed
cd ~/code/NAATools
Rscript -e "devtools::document()"
Rscript -e "devtools::install_deps()"
```

### Issue: Quarto notebook compilation fails

**Symptom:** Notebook status shows `failed` with rendering errors.

**Cause:** Missing R packages, DuckDB connection issues, or syntax errors in notebook.

**Solution:**
```bash
# Check Celery logs for R errors
docker logs naaccord-celery | grep -A 20 "Error in"

# Test notebook manually
cd depot/notebooks/audit/
quarto render generic_audit.qmd --execute-params params.json

# Check required R packages
R -e "installed.packages()[,c('Package', 'Version')]"

# Verify DuckDB file exists and is readable
ls -lh /path/to/audit.duckdb
```

### Issue: R memory errors with large datasets

**Symptom:** `Error: cannot allocate vector of size` in R processing.

**Solution:**
```r
# In notebook, use DuckDB queries instead of loading full data into R
library(duckdb)
con <- dbConnect(duckdb::duckdb(), dbdir = params$duckdb_path)

# Query only what's needed
summary_stats <- dbGetQuery(con, "
  SELECT COUNT(*) as total,
         COUNT(DISTINCT patient_id) as unique_patients
  FROM data
")

# Close connection when done
dbDisconnect(con)
```

---

## Authentication and SAML

### Issue: SAML authentication fails

**Symptom:** Redirect to SAML IdP but fails to authenticate or redirect back.

**Cause:** SAML metadata mismatch, certificate issues, or incorrect entity ID.

**Solution:**
```bash
# Verify SAML configuration
python manage.py shell
>>> from django.conf import settings
>>> print(settings.SAML_ENTITY_ID)
>>> print(settings.SAML_ACS_URL)

# Check SAML metadata is loaded
ls -la depot/saml/idp_metadata.xml

# For development with mock-idp
docker ps | grep mock-idp
curl -s http://localhost:8080/metadata
# Should return XML metadata

# Test SAML login flow
# 1. Visit /saml2/login/
# 2. Should redirect to IdP
# 3. IdP should redirect back to /saml2/acs/
# 4. Check logs for errors
docker logs naaccord-web | grep -i saml
```

### Issue: User authenticated but no access to cohorts

**Symptom:** User logs in successfully but sees "No cohorts assigned".

**Cause:** User not assigned to any cohort groups.

**Solution:**
```bash
# Assign user to cohort groups
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from django.contrib.auth.models import Group
>>> User = get_user_model()
>>> user = User.objects.get(username='username')
>>> group = Group.objects.get(name='COHORT_NAME_users')
>>> user.groups.add(group)

# Or use management command
python manage.py assign_test_users_to_groups
```

### Issue: SAML certificate expired

**Symptom:** SAML authentication fails with certificate validation error.

**Solution:**
```bash
# Check certificate expiration
openssl x509 -in depot/saml/cert.pem -noout -dates

# Generate new certificate (development only)
cd depot/saml/
./generate-cert.sh

# For production, obtain certificate from JHU Enterprise Auth team
# Update Ansible vault with new certificate
ansible-vault edit deploy/ansible/inventories/production/group_vars/vault.yml
```

---

## Frontend and Static Assets

### Issue: Static files not loading (404 errors)

**Symptom:** CSS and JavaScript files return 404, page looks broken.

**Cause:** Static files not collected or wrong STATIC_ROOT configuration.

**Solution:**
```bash
# Build frontend assets
npm run build

# Collect static files
python manage.py collectstatic --noinput

# Verify files exist
ls -la static/dist/

# In Docker, copy static files to volume
docker cp static/. naaccord-web:/app/static/

# Verify Nginx can serve files
docker exec naaccord-web ls -la /app/static/dist/
```

### Issue: Vite dev server not hot reloading

**Symptom:** Changes to JS/CSS files don't reflect in browser.

**Solution:**
```bash
# Check if Vite dev server is running
ps aux | grep vite
lsof -i :5173

# Restart Vite dev server
pkill -f vite
npm run dev

# In tmux
command tmux send-keys -t na:npm C-c
command tmux send-keys -t na:npm "npm run dev" C-m

# Check Vite configuration
cat vite.config.js
# Should have proper input/output paths
```

### Issue: Alpine.js components not working

**Symptom:** Interactive UI elements don't respond, no Alpine reactivity.

**Cause:** Alpine.js not loaded or JavaScript errors.

**Solution:**
```html
<!-- Verify Alpine.js is loaded in base template -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

<!-- Check browser console for errors -->
<!-- F12 → Console tab -->

<!-- Test Alpine.js is working -->
<div x-data="{ message: 'Hello' }">
    <p x-text="message"></p>
</div>
```

---

## Ansible Deployment

### Issue: Ansible vault password incorrect

**Symptom:** `ERROR! Decryption failed` when running playbooks.

**Solution:**
```bash
# Verify vault password file exists
cat ~/.naaccord_vault_staging

# Test vault password
ansible-vault view deploy/ansible/inventories/staging/group_vars/vault.yml \
  --vault-password-file ~/.naaccord_vault_staging

# If password lost, re-encrypt vault with new password
ansible-vault rekey deploy/ansible/inventories/staging/group_vars/vault.yml
```

### Issue: Ansible playbook fails with connection error

**Symptom:** `Connection refused` or `Host unreachable` errors.

**Cause:** SSH not configured, wrong IP address, or firewall blocking connection.

**Solution:**
```bash
# Test SSH connection
ssh user@10.150.96.6

# For local playbooks (on server itself)
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --connection local \
  --vault-password-file ~/.naaccord_vault_staging

# Check inventory file
cat deploy/ansible/inventories/staging/hosts.yml
# Verify ansible_host and ansible_connection settings
```

### Issue: Ansible role fails with missing variable

**Symptom:** `The field 'variable_name' is required but was not set`.

**Cause:** Missing variable in group_vars or vault.

**Solution:**
```bash
# Check which variables are required
cat deploy/ansible/roles/role_name/defaults/main.yml

# Verify variable is in vault or group_vars
ansible-vault view deploy/ansible/inventories/staging/group_vars/vault.yml

# Add missing variable
ansible-vault edit deploy/ansible/inventories/staging/group_vars/vault.yml
```

---

## Performance Issues

### Issue: Slow file uploads (>1 minute for large files)

**Symptom:** Large file uploads take excessively long.

**Cause:** Inefficient buffering, memory limits, or network issues.

**Solution:**
```python
# Use streaming upload in views.py
def handle_file_upload(request):
    file_obj = request.FILES['file']

    # Stream to storage without loading into memory
    storage = StorageManager.get_scratch_storage()
    file_path = storage.save('uploads/file.csv', file_obj)

    # Process asynchronously
    process_file.delay(file_path)
```

### Issue: DuckDB conversion very slow

**Symptom:** DuckDB file creation takes >5 minutes for datasets under 1GB.

**Cause:** Inefficient CSV parsing or disk I/O issues.

**Solution:**
```python
# Use optimized DuckDB CSV reader
import duckdb

con = duckdb.connect('audit.duckdb')
con.execute("""
    CREATE TABLE data AS
    SELECT * FROM read_csv_auto(
        ?,
        header=true,
        parallel=true,
        sample_size=100000
    )
""", [csv_path])
con.close()

# Or use faster options
con.execute("PRAGMA threads=4")
con.execute("PRAGMA memory_limit='4GB'")
```

### Issue: High memory usage in Celery workers

**Symptom:** Worker memory grows unbounded, eventually crashes.

**Cause:** Memory leaks in tasks or not properly closing connections.

**Solution:**
```python
# In celery.py, configure worker to restart after N tasks
app.conf.worker_max_tasks_per_child = 100

# Close connections explicitly in tasks
@shared_task
def process_file(file_path):
    try:
        # Processing code
        pass
    finally:
        # Close database connections
        from django.db import connections
        for conn in connections.all():
            conn.close()
```

---

## Production-Specific Issues

### Issue: Can't SSH to production servers

**Symptom:** SSH connection refused or times out.

**Cause:** Not connected to JHU VPN or wrong credentials.

**Solution:**
```bash
# Connect to JHU VPN first
# Visit: vpn.johnshopkins.edu

# Verify VPN is connected
ping 10.150.96.6

# SSH with correct credentials
ssh username@mrpznaaccordweb01.hosts.jhmi.edu

# Use SSH keys for authentication (preferred)
ssh-copy-id username@mrpznaaccordweb01.hosts.jhmi.edu
```

### Issue: deployna alias not found

**Symptom:** `command not found: deployna` on production server.

**Cause:** Aliases not loaded or wrong shell.

**Solution:**
```bash
# Source aliases manually
source /etc/profile.d/naaccord-aliases.sh

# Or add to your shell profile
echo "source /etc/profile.d/naaccord-aliases.sh" >> ~/.bashrc
source ~/.bashrc

# Use full deployment script path
cd /opt/naaccord/depot
./deploy/scripts/deploy.sh
```

### Issue: Production NAS mount failing

**Symptom:** `/mnt/nas/` or `/na_accord_nas/` not accessible.

**Cause:** NAS credentials expired or mount point not configured.

**Solution:**
```bash
# Check if NAS is mounted
df -h | grep nas

# Check mount configuration
cat /etc/fstab | grep nas

# Remount NAS (requires sudo)
sudo mount -a

# Or mount manually
sudo mount -t cifs -o credentials=/root/.nas_credentials,uid=naaccord,gid=naaccord \
  //cloud.nas.jh.edu/na-accord$ /na_accord_nas

# Verify access
ls -la /na_accord_nas/
```

### Issue: Let's Encrypt SSL certificate renewal fails

**Symptom:** Certificate expired or renewal failing.

**Cause:** DNS-01 challenge failing or Cloudflare API issues.

**Solution:**
```bash
# Check certificate expiration
sudo certbot certificates

# Test renewal (dry run)
sudo certbot renew --dry-run

# Force renewal
sudo certbot renew --force-renewal

# Check Cloudflare API credentials
sudo cat /root/.secrets/cloudflare.ini

# Manual renewal if needed
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
  -d naaccord.example.com
```

### Issue: Production health check failing

**Symptom:** `/health/` endpoint returns 500 or times out.

**Cause:** Database connection issues, WireGuard tunnel down, or service crashed.

**Solution:**
```bash
# Use server aliases to check status
nahealth  # Check application health
nastatus  # Check container status
nalogs    # View logs

# Check individual services
sudo docker exec naaccord-services python manage.py check --database default

# Test WireGuard tunnel
sudo docker exec naaccord-wireguard-web wg show
sudo docker exec naaccord-wireguard-web ping -c 3 10.100.0.11

# Check database connectivity
sudo docker exec naaccord-services mysql -h 10.101.0.2 -u naaccord -p
```

---

## Getting Help

### Log Locations

**Development:**
- Django: Console output or tmux windows
- Celery: tmux celery window or `tail -f logs/celery.log`
- Frontend: Browser console (F12)

**Production:**
- Application logs: `docker logs <container-name>`
- System logs: `/var/log/naaccord/`
- Nginx logs: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`
- Quick access: `nalogs` alias

### Diagnostic Commands

```bash
# Complete environment check
python manage.py check --deploy

# Database connectivity
python manage.py check --database default

# List all management commands
python manage.py help

# Django shell for interactive debugging
python manage.py shell

# Check Celery task status
celery -A depot inspect active
celery -A depot inspect scheduled
```

### Reporting Issues

When reporting issues, include:

1. **Environment**: Development, staging, or production
2. **Steps to reproduce**: Exact commands or actions taken
3. **Expected behavior**: What should happen
4. **Actual behavior**: What actually happened
5. **Error messages**: Full error output and stack traces
6. **Logs**: Relevant log entries from application/container
7. **Recent changes**: Any recent code deploys or configuration changes

---

**Questions or need additional help?** Check [CLAUDE.md](../../CLAUDE.md) for architecture details or contact the NA-ACCORD development team.
