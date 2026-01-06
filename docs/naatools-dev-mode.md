# NAATools Development Mode

This document explains how to work with local NAATools development in the containerized environment.

## Overview

NA-ACCORD supports two modes for NAATools:

1. **Production Mode (default)**: Uses NAATools installed from GitHub in container image
2. **Development Mode**: Mounts local NAATools directory for live development

## When to Use Each Mode

### Production Mode (Default)
- ✅ Normal development work on NA-ACCORD itself
- ✅ Testing with stable NAATools version
- ✅ Faster container startup
- ✅ Consistent behavior across environments

**How to use:**
```bash
# Standard tmux script
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh

# OR manually
./scripts/naaccord-docker.sh start --env dev
```

### Development Mode
- ✅ Active NAATools package development
- ✅ Testing NAATools changes immediately
- ✅ No need to rebuild/reinstall after changes
- ✅ Debug R code in real-time

**How to use:**
```bash
# NAATools dev tmux script
/Users/erikwestlund/code/projects/tmux/start_naaccord_naatools_dev.sh

# OR manually
./scripts/naaccord-docker.sh start --env dev --naatools-dev
```

## How It Works

### Normal Mode
```
Container → /usr/local/lib/R/site-library/NAATools (installed from GitHub)
```

### Dev Mode
```
Container → /home/django/code/NAATools → (mounted from) → /Users/erikwestlund/code/NAATools
```

When `.r_dev_mode` file is present in container, `scaffold_r.R` loads NAATools from `/home/django/code/NAATools` instead of the installed version.

## Architecture

### Files Involved

1. **`.r_dev_mode`** (gitignored, in repo)
   - Config file that tells R to use local NAATools
   - Contains path: `NAATOOLS_DIR=$HOME/code/NAATools`
   - Only mounted into containers in dev mode

2. **`docker-compose.naatools-dev.yml`** (new override file)
   - Mounts local NAATools directory
   - Mounts `.r_dev_mode` config file
   - Applied with: `docker compose -f docker-compose.yml -f docker-compose.naatools-dev.yml`

3. **`.dockerignore`** (updated)
   - Excludes `.r_dev_mode` from being baked into images
   - Ensures production images never have dev mode enabled

4. **`scripts/naaccord-docker.sh`** (updated)
   - New flag: `--naatools-dev`
   - Automatically applies override file when flag is used

5. **Tmux Scripts**
   - `start_naaccord.sh`: Normal mode (existing)
   - `start_naaccord_naatools_dev.sh`: Dev mode (new)

## Switching Between Modes

### From Normal to Dev Mode
```bash
# Stop containers
docker compose down

# Start with NAATools dev mode
./scripts/naaccord-docker.sh start --env dev --naatools-dev

# OR use dedicated tmux script
/Users/erikwestlund/code/projects/tmux/start_naaccord_naatools_dev.sh
```

### From Dev Mode to Normal
```bash
# Stop containers
docker compose down

# Start in normal mode
./scripts/naaccord-docker.sh start --env dev

# OR use standard tmux script
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

### Quick Restart in Current Mode
```bash
# Restart without changing mode
docker compose restart services celery
```

## Verifying Current Mode

Check if NAATools is mounted:
```bash
# Check if .r_dev_mode exists in container
docker exec naaccord-test-celery ls -la /app/.r_dev_mode

# Check if NAATools directory is mounted
docker exec naaccord-test-celery ls -la /home/django/code/NAATools
```

If either command succeeds, you're in dev mode.

## Making NAATools Changes

### In Dev Mode
1. Edit files in `/Users/erikwestlund/code/NAATools`
2. Changes are immediately available in containers
3. No rebuild or reinstall needed
4. Test by running an audit or notebook

### In Normal Mode
1. Make changes and commit to NAATools repo
2. Rebuild services container:
   ```bash
   ./scripts/naaccord-docker.sh build
   docker compose up -d services celery
   ```
3. Or update NAATools version in container and reinstall

## Troubleshooting

### "NAATools development directory not found" Error

This happens when `.r_dev_mode` exists in container but directory is not mounted.

**Solution:**
```bash
# Remove dev mode file from container
docker exec naaccord-test-celery rm /app/.r_dev_mode
docker exec naaccord-test-services rm /app/.r_dev_mode

# OR restart in correct mode
docker compose down
./scripts/naaccord-docker.sh start --env dev  # Normal mode
```

### Changes Not Reflected

**In Dev Mode:**
- Verify NAATools directory is mounted:
  ```bash
  docker exec naaccord-test-celery ls /home/django/code/NAATools
  ```
- Check that `.r_dev_mode` exists in container:
  ```bash
  docker exec naaccord-test-celery cat /app/.r_dev_mode
  ```
- Restart services to reload R environment:
  ```bash
  docker compose restart services celery
  ```

**In Normal Mode:**
- Rebuild container to include latest NAATools from GitHub:
  ```bash
  ./scripts/naaccord-docker.sh build
  docker compose up -d services celery
  ```

## Best Practices

1. **Default to Normal Mode**: Use production mode unless actively developing NAATools
2. **Commit Before Switching**: Commit NAATools changes before switching to normal mode
3. **Test Both Modes**: Verify changes work in both dev and normal mode
4. **Document Changes**: Update NAATools version in Dockerfile after merging changes
5. **Clean Switches**: Always use `docker compose down` before switching modes

## Production Deployment

Production deployments **never** use dev mode:
- `.r_dev_mode` excluded via `.dockerignore`
- Override file not used in production
- NAATools always installed from GitHub tag/release
- Consistent, reproducible builds
