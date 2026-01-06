# Logrotate Role

## Purpose

Configures log rotation for NA-ACCORD application logs, Nginx logs, and Docker container logs to prevent disk exhaustion and maintain HIPAA-compliant log retention.

## Features

- **NA-ACCORD application logs:** Daily rotation, 90-day retention
- **Nginx logs:** Daily rotation, 90-day retention (web server only)
- **Docker container logs:** Weekly rotation, 4-week retention (managed by Docker logging driver limits)
- Automatic compression of rotated logs
- Delayed compression (keeps yesterday's log uncompressed for easier access)
- Graceful handling of missing log files

## Configuration

Default values in `defaults/main.yml`:

```yaml
naaccord_log_dir: /var/log/naaccord
naaccord_log_rotation_days: 90
nginx_log_dir: /var/log/nginx
nginx_log_rotation_days: 90
docker_log_rotation_weeks: 4
```

Override in inventory `group_vars/all.yml` if needed.

## Log Retention Policy

### Hot Storage (Local Disk)
- Application logs: 90 days
- Nginx logs: 90 days
- Docker logs: 30 days

### Cold Storage (NAS - Future)
User will configure NAS archival separately based on IT guidance. Logs older than 30 days should be archived to NAS for 7-year HIPAA retention.

## Usage

```yaml
roles:
  - logrotate
```

## Tags

- `logrotate` - All logrotate tasks
- `logging` - General logging setup
- `naaccord` - NA-ACCORD logs only
- `nginx` - Nginx logs only (web server)
- `docker` - Docker container logs only
- `verify` - Verification tasks

## Verification

After running this role:

```bash
# Test configuration
sudo logrotate -d /etc/logrotate.d/naaccord

# Force rotation (testing)
sudo logrotate -f /etc/logrotate.d/naaccord

# Check rotated logs
ls -lh /var/log/naaccord/*.gz
```

## Log Archival to NAS

**Note:** NAS archival will be configured separately by user after discussing with IT.

Suggested cron job (to be created later):

```bash
# /etc/cron.d/naaccord-log-archive
0 2 * * * root /opt/naaccord/scripts/archive-logs-to-nas.sh
```

This role focuses on LOCAL log rotation. Remote archival is out of scope until NAS configuration is confirmed with IT.
