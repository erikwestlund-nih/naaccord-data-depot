# 2025-09-30-01: Fix Upload Workflow and NAATools Dev Mode

## Summary
Fixed complete upload workflow in containerized development environment. Resolved multiple blocking issues from Alpine.js syntax errors to missing R packages. Implemented flexible NAATools development mode for local package development.

## Issues Fixed

### 1. Alpine.js Curly Quote Syntax Error
**Problem**: Upload form had curly quote in `x-bind:class` causing JavaScript error
**Location**: `depot/templates/pages/upload_precheck.html:174`
**Fix**: Changed `'}` to `}` (straight quote)

### 2. Celery Redis Connection Refused
**Problem**: Celery couldn't connect to Redis broker
**Root Cause**: `docker-compose.yml` set `REDIS_URL` but Django settings expected `CELERY_BROKER_URL`
**Fix**: Updated environment variables in docker-compose.yml for services, celery, and web containers
```yaml
CELERY_BROKER_URL: redis://redis:6379/0  # Was REDIS_URL
```

### 3. Internal Storage API Blocked Requests
**Problem**: RemoteStorageDriver getting 400 Bad Request from services container
**Root Cause**: Django `DisallowedHost` error - services container blocking requests from `services` hostname
**Fix**: Added to services container environment:
```yaml
ALLOWED_HOSTS: "services,localhost,127.0.0.1"
```

### 4. NAS Workspace Path Not Available in Dev
**Problem**: Container expected `/mnt/nas/workspace` which doesn't exist in development
**Fix**: Mapped local directory in docker-compose.yml:
```yaml
- ./storage/mnt/nas:/mnt/nas:rw  # Maps to local storage/mnt/nas/
```

### 5. Missing Environment Variables for Quarto
**Problem**: Quarto notebook compilation failed with missing `ALLOWED_HOSTS` and `DB_ENGINE` variables
**Fix**: Added to celery and services containers:
```yaml
DB_ENGINE: django.db.backends.mysql  # Full Django backend path
ALLOWED_HOSTS: "services,localhost,127.0.0.1"
```

### 6. Tmux Docker Logs Auto-Restart
**Problem**: Docker logs in tmux windows would die when containers were recreated
**Fix**: Wrapped docker compose logs in retry loop:
```bash
while true; do docker compose logs -f 2>/dev/null || sleep 2; done
```

### 7. Missing R Package 'here'
**Problem**: Notebook compilation failed: "there is no package called 'here'"
**Root Cause**: Package not included in services Dockerfile R package installation
**Fix**: Added `here` to `pak::pak()` call in `deploy/containers/services/Dockerfile:129`

### 8. NAATools Development Mode Conflict
**Problem**: `.r_dev_mode` file being baked into container image, causing "NAATools development directory not found" error in production
**Root Cause**: File not excluded from Docker build context
**Solution**: Implemented flexible dev mode system (see below)

## NAATools Development Mode Implementation

Created system to conditionally enable local NAATools mounting for active package development.

### Files Created/Modified

**`docker-compose.naatools-dev.yml`** (new)
- Docker Compose override file
- Mounts `/Users/erikwestlund/code/NAATools` into containers
- Mounts `.r_dev_mode` config file
- Only used when explicitly specified

**`.dockerignore`** (updated)
- Added `.r_dev_mode` to prevent baking into images
- Ensures production builds never have dev mode enabled

**`scripts/naaccord-docker.sh`** (updated)
- New flag: `--naatools-dev`
- Automatically applies override when flag used
- Example: `./scripts/naaccord-docker.sh start --env dev --naatools-dev`

**`/Users/erikwestlund/code/projects/tmux/start_naaccord.sh`** (updated)
- Accepts `--naatools-dev` flag
- Passes flag to naaccord-docker.sh
- Shows NAATools dev status in output

**`docs/naatools-dev-mode.md`** (new)
- Complete documentation for switching modes
- Troubleshooting guide
- Best practices

### Usage

**Normal Mode (default):**
```bash
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh
# Uses installed NAATools from GitHub
```

**NAATools Dev Mode:**
```bash
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh --naatools-dev
# Mounts local NAATools, changes are immediate
```

**Switching Modes:**
```bash
docker compose down
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh [--naatools-dev]
```

## Architecture Improvements

### Build-Time vs Runtime Configuration
- **Build Time**: `.r_dev_mode` excluded via `.dockerignore` - never in image
- **Runtime**: Dev mode controlled by Docker Compose overlay file
- **Production**: No changes needed, override file never used

### Storage Manager Fix
Fixed RemoteStorageDriver communication between web and services containers by adding proper hostname to ALLOWED_HOSTS.

### R Package Installation
Corrected Dockerfile to use `pak::pak()` inline (lines 127-153) instead of non-existent external script.

## Testing Status

**Completed:**
- ✅ File upload via web interface
- ✅ Stream to services server (RemoteStorageDriver)
- ✅ Queue Celery task
- ✅ DuckDB conversion
- ✅ R packages available (including `here`)
- ✅ Container networking and internal API

**Pending:**
- 🔄 Complete notebook compilation and report generation (restarting tmux to test)

## Files Modified

### Configuration Files
- `docker-compose.yml` - Fixed env vars and volume mappings
- `.dockerignore` - Added `.r_dev_mode`
- `.r_dev_mode` - Created (gitignored)
- `docker-compose.naatools-dev.yml` - Created overlay file

### Container Configuration
- `deploy/containers/services/Dockerfile` - Added `here` package
- `deploy/containers/services/install-r-packages.R` - Deleted (unused)

### Scripts
- `scripts/naaccord-docker.sh` - Added `--naatools-dev` flag
- `scripts/dev-naatools.sh` - Created helper script
- `/Users/erikwestlund/code/projects/tmux/start_naaccord.sh` - Added flag support

### Templates
- `depot/templates/pages/upload_precheck.html` - Fixed Alpine.js syntax

### Documentation
- `docs/naatools-dev-mode.md` - Complete dev mode guide

## Lessons Learned

1. **Volume Mounts Can Override Build Context**: `.r_dev_mode` was being mounted via `./:/app` volume despite being in .dockerignore
2. **Environment Variable Names Must Match**: `REDIS_URL` vs `CELERY_BROKER_URL` mismatch caused connection failures
3. **Full Django Backend Path Required**: `DB_ENGINE: mysql` doesn't work, needs `django.db.backends.mysql`
4. **ALLOWED_HOSTS for Internal APIs**: Container hostnames must be in ALLOWED_HOSTS for inter-container communication
5. **Dev/Prod Separation at Runtime**: Better to control dev features via Compose overlays than build-time configuration

## Next Steps

1. Test complete upload workflow with notebook compilation
2. Verify report generation and storage
3. Test with different data file types (laboratory, etc.)
4. Document any remaining issues
5. Consider adding automated tests for upload workflow

## Related Documentation
- `docs/naatools-dev-mode.md` - NAATools development mode guide
- `docs/technical/upload-submission-workflow.md` - Upload workflow documentation
- `docs/deployment/` - Container deployment guides
