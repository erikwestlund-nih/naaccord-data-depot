# Container Monitoring Role

Automated container health monitoring for NA-ACCORD infrastructure with restart tracking, health checks, and alerting.

## Features

- **Automated Monitoring**: Runs every 15 minutes via cron
- **Restart Tracking**: Alerts when containers restart frequently (threshold: 3)
- **Health Checks**: Monitors Docker healthcheck status
- **Error Detection**: Scans container logs for errors/exceptions
- **Slack Alerts**: Optional Slack notifications for critical issues
- **Log Retention**: Automatic cleanup of old monitoring logs (30 days)

## Installation

### Quick Setup

```bash
# On production web server
ssh mrpznaaccordweb01.hosts.jhmi.edu
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook -i inventories/production/hosts.yml playbooks/setup-container-monitoring.yml --connection local --ask-vault-pass

# On production services server
ssh mrpznaaccorddb01.hosts.jhmi.edu
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook -i inventories/production/hosts.yml playbooks/setup-container-monitoring.yml --connection local --ask-vault-pass
```

### Manual Installation

```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/setup-container-monitoring.yml \
  --connection local \
  --ask-vault-pass
```

## Configuration

### Default Variables

Located in `roles/container_monitoring/defaults/main.yml`:

```yaml
monitoring_cron_schedule: "*/15 * * * *"  # Every 15 minutes
restart_threshold: 3                       # Alert after 3 restarts
monitoring_log_retention_days: 30          # Keep logs for 30 days
alert_on_unhealthy: true
alert_on_high_restarts: true
alert_on_container_down: true
```

### Slack Integration (Optional)

Add to vault file (`inventories/{environment}/group_vars/vault.yml`):

```yaml
slack_webhook_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
slack_channel: "#naaccord-alerts"
```

## Usage

### Shell Aliases (Available on Servers)

After installation, the following commands are available:

```bash
# Run monitoring check immediately
namonitor

# View alert log (follow mode)
namonitor-logs

# View recent monitoring status
namonitor-status

# View all container logs
nalogs
```

### Manual Monitoring

Run monitoring check manually:

```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/monitor-container-health.yml \
  --connection local
```

### Check Monitoring Status

```bash
# View recent alerts
tail -f /var/log/naaccord/alerts.log

# View latest monitoring report
ls -lht /var/log/naaccord/monitoring-*.log | head -1 | awk '{print $9}' | xargs cat

# Check cron job status
crontab -l | grep naaccord
```

## Monitoring Checks

The system monitors:

1. **Container Status**
   - Running state
   - Uptime
   - Restart counts

2. **Health Checks**
   - Docker healthcheck status
   - Health check failures

3. **Error Logs**
   - Scans last 50 log lines
   - Searches for: error, exception, fatal, crash

4. **Resource Issues**
   - Container restarts due to OOM (Out of Memory)
   - Container exits with non-zero codes

## Alert Conditions

Alerts are triggered when:

- **🔴 CRITICAL**: Container is unhealthy
- **🟡 WARNING**: Container restart count > threshold (default: 3)
- **🟡 WARNING**: Recent errors found in logs
- **🔴 CRITICAL**: Expected container is not running

## Log Files

```bash
/var/log/naaccord/
├── monitoring-YYYYMMDD-HHMMSS.log  # Monitoring reports
├── alerts.log                       # Critical alerts
└── container-health-YYYY-MM-DD.log # Daily summaries
```

## Troubleshooting

### Monitoring Not Running

```bash
# Check cron job
crontab -l | grep naaccord

# Check if monitoring script exists
ls -l /usr/local/bin/naaccord-monitor-containers.sh

# Run manually to test
/usr/local/bin/naaccord-monitor-containers.sh
```

### No Alerts Being Generated

```bash
# Check alert log
tail -100 /var/log/naaccord/alerts.log

# Verify Slack webhook (if configured)
curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Test alert from NA-ACCORD monitoring"}'
```

### High Restart Counts

If containers are restarting frequently:

```bash
# Check container logs
docker logs naaccord-web --tail 200

# Check resource usage
docker stats

# Inspect container exit code
docker inspect naaccord-web --format='{{.State.ExitCode}}'

# Check for OOM kills
dmesg | grep -i "killed process"
```

### Web Container Specific Issues

The web container has unique characteristics:

1. **Network Mode**: Shares network with WireGuard container
2. **Healthcheck**: Checks `/health/` endpoint on port 8000
3. **Dependencies**: Requires WireGuard tunnel to services server

**Common web container issues:**

```bash
# Verify WireGuard tunnel is healthy
docker exec wireguard-web wg show

# Check if web can reach services server
docker exec naaccord-web curl -f http://10.100.0.11:8001/health/

# Check Gunicorn workers
docker exec naaccord-web ps aux | grep gunicorn

# Review Nginx access logs
docker logs naaccord-nginx | tail -100
```

## Customization

### Change Monitoring Interval

Edit cron schedule in role defaults or override:

```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/setup-container-monitoring.yml \
  --connection local \
  -e monitoring_cron_schedule="*/5 * * * *"  # Every 5 minutes
```

### Adjust Restart Threshold

```bash
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/setup-container-monitoring.yml \
  --connection local \
  -e restart_threshold=5  # Alert after 5 restarts
```

## Integration with Existing Infrastructure

This monitoring system complements:

- **Loki**: Container log aggregation
- **Grafana**: Visualization and dashboards
- **Docker Healthchecks**: Built-in container health monitoring

## Maintenance

### Clean Old Logs Manually

```bash
# Remove logs older than 30 days
find /var/log/naaccord -name "monitoring-*.log" -mtime +30 -delete
```

### Disable Monitoring

```bash
# Remove cron job
crontab -e
# Delete the line containing naaccord-monitor-containers

# Or use Ansible
ansible-playbook \
  -i inventories/production/hosts.yml \
  playbooks/setup-container-monitoring.yml \
  --connection local \
  --tags cron \
  -e monitoring_enabled=false
```

## Security Considerations

- Monitoring runs as root (required for Docker access)
- Logs contain container status information (no PHI)
- Slack webhooks should be kept in vault (encrypted)
- Alert logs are world-readable (mode 0644) but contain no sensitive data

## Related Documentation

- [Deploy Steps](../../deploy-steps.md) - Deployment workflow
- [Troubleshooting Guide](../../docs/troubleshooting.md) - General troubleshooting
- [Container Architecture](../../../docs/deployment/guides/architecture.md) - System architecture
