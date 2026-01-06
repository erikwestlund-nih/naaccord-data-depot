# Ansible Deployment and Django/Static File Fixes

**Date**: 2025-08-26
**Focus**: Deployment issues, Django Debug Toolbar fix, static files SELinux permissions, Celery setup

## Summary
Continued from previous session's refactoring work, shifted to fixing deployment issues on test environment (192.168.50.10 web server, 192.168.50.11 services server).

## Key Issues Resolved

### 1. Django Debug Toolbar Multiple Injection (10MB+ page size)
**Problem**: Debug Toolbar was being injected multiple times, causing pages to be 10MB+ instead of 8KB
**Solution**: Modified `depot/settings.py` to check `ENABLE_DEBUG_TOOLBAR` environment variable
```python
if DEBUG and env('ENABLE_DEBUG_TOOLBAR', default=True):
    # Debug toolbar configuration
```

### 2. Static Files 403 Forbidden
**Problem**: Nginx couldn't serve static files - returning 403 Forbidden
**User Report**: "http://192.168.50.10/static/css/app-DD2IP9Ys.css Request Method GET Status Code 403 Forbidden"
**Solution**: Fixed SELinux contexts on web server
```bash
chcon -R -t httpd_sys_content_t /var/www/naaccord/static/
```

### 3. Ansible Vault Configuration
**Problem**: Vault variables weren't loading during playbook execution
**Solution**: 
- Updated vault.yml with actual credentials
- Encrypted with ansible-vault
- Must explicitly include with `-e "@inventories/test/group_vars/vault.yml"`

## Celery Deployment Challenges

### Python Version Incompatibility
- Services server has Python 3.9
- Django 5.0.9 requires Python 3.10+
- Celery can't start due to missing Django dependencies

### Container Build Issues
- R packages installation timing out during container builds
- Created simplified Containerfile without R/Quarto
- Still faced dependency issues (django_components, beautifulsoup4, etc.)

### Temporary Solution
- Installed Celery system-wide with pip3
- Created systemd service for Celery
- Service fails due to Python/Django version mismatch

## Database Credentials (Test Environment)
Per user request:
- **Database**: naaccord_test
- **User**: naaccord
- **Password**: v1s85PTAzcRUQLGeRSQ4LDOFSwH9Xi+d
- **Host**: 192.168.50.11
- **Port**: 3306

## Files Modified
- `/Users/erikwestlund/code/naaccord/depot/settings.py` - Debug toolbar control
- `/Users/erikwestlund/code/naaccord/ansible/inventories/test/group_vars/vault.yml` - Encrypted credentials
- `/Users/erikwestlund/code/naaccord/containerfiles/Containerfile.celery-minimal` - Simplified Celery container
- `/Users/erikwestlund/code/naaccord/requirements-celery.txt` - Minimal Celery dependencies
- `/Users/erikwestlund/code/naaccord/ansible/files/celery.service` - Systemd service

## Recommendations
User suggested using GitHub Container Registry for pre-built containers - this would solve:
- Python version conflicts
- Dependency installation timeouts
- Consistent deployments across environments

## Current Status
- Web interface working at http://192.168.50.10
- Django running with DEBUG=True, Debug Toolbar disabled
- Static files serving correctly
- Celery workers not yet deployed (Python version issue)

## Git Cleanup
- Removed `static.tar.gz` from git tracking
- Added to `.gitignore`

## Lessons Learned
1. Always check Python version compatibility before deploying Django 5.x
2. SELinux contexts are critical for web server file access
3. Container pre-building in CI/CD is more reliable than building during deployment
4. Debug Toolbar can cause massive performance issues if misconfigured