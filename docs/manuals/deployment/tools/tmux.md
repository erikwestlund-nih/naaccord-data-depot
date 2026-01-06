# NA-ACCORD Tmux Development Setup

## Overview

NA-ACCORD uses tmux for managing multiple services during development. All services run in a single tmux session named `na` with dedicated windows for each component.

## Starting the Development Environment

### Automated Start
```bash
# Start all services automatically
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

This script will:
1. Check if session already exists and attach if it does
2. Start Docker services (MariaDB, Redis, MinIO)
3. Create tmux session with all service windows
4. Start all services in correct order
5. Attach to the session

### Session Structure

| Window # | Name | Purpose | Working Directory |
|----------|------|---------|------------------|
| 0 | shell_depot | Main development shell | `~/code/naaccord` |
| 1 | claude | Claude CLI for AI assistance | `~/code/naaccord` |
| 2 | shell_naatools | NAATools development shell | `~/code/NAATools` |
| 3 | django | Web server (port 8000) | `~/code/naaccord` |
| 4 | services | Services server (port 8001) | `~/code/naaccord` |
| 5 | celery | Background task worker | `~/code/naaccord` |
| 6 | npm | Frontend dev server | `~/code/naaccord` |
| 7 | r_depot | R console for depot | `~/code/naaccord/depot` |
| 8 | r_naatools | R console for NAATools | `~/code/NAATools` |
| 9 | docker | Docker compose logs | `~/code/naaccord` |

## Tmux Navigation

### Basic Commands
- **Attach to session**: `tmux attach -t na`
- **Detach from session**: `Ctrl+b`, then `d`
- **List all sessions**: `tmux list-sessions` or `command tmux list-sessions`

### Window Navigation
- **Switch to window by number**: `Ctrl+b`, then `0-9`
- **Next window**: `Ctrl+b`, then `n`
- **Previous window**: `Ctrl+b`, then `p`
- **List all windows**: `Ctrl+b`, then `w`
- **Rename current window**: `Ctrl+b`, then `,`

### Pane Management
- **Split horizontally**: `Ctrl+b`, then `%`
- **Split vertically**: `Ctrl+b`, then `"`
- **Navigate panes**: `Ctrl+b`, then arrow keys
- **Close pane**: `Ctrl+d` or `exit`
- **Resize pane**: `Ctrl+b`, then hold `Ctrl` and use arrow keys

## Service Management

### Restarting Services

#### Celery Worker
```bash
# Stop current worker
command tmux send-keys -t na:celery C-c

# Start worker
command tmux send-keys -t na:celery "source venv/bin/activate && celery -A depot worker -l info" C-m
```

#### Django Web Server (Port 8000)
```bash
# Stop server
command tmux send-keys -t na:django C-c

# Start server with environment variables
command tmux send-keys -t na:django "source venv/bin/activate" C-m
command tmux send-keys -t na:django "export SERVER_ROLE=web" C-m
command tmux send-keys -t na:django "export INTERNAL_API_KEY=test-key-123" C-m
command tmux send-keys -t na:django "export SERVICES_URL=http://localhost:8001" C-m
command tmux send-keys -t na:django "python manage.py runserver 0.0.0.0:8000" C-m
```

#### Django Services Server (Port 8001)
```bash
# Stop server
command tmux send-keys -t na:services C-c

# Start server with environment variables
command tmux send-keys -t na:services "source venv/bin/activate" C-m
command tmux send-keys -t na:services "export SERVER_ROLE=services" C-m
command tmux send-keys -t na:services "export INTERNAL_API_KEY=test-key-123" C-m
command tmux send-keys -t na:services "python manage.py runserver 0.0.0.0:8001" C-m
```

#### NPM Dev Server
```bash
# Stop server
command tmux send-keys -t na:npm C-c

# Start server
command tmux send-keys -t na:npm "npm run dev" C-m
```

### Viewing Logs

```bash
# View Celery logs
tmux select-window -t na:celery

# View Django web server logs
tmux select-window -t na:django

# View Django services server logs
tmux select-window -t na:services

# View Docker compose logs
tmux select-window -t na:docker

# Capture pane output to file
tmux capture-pane -t na:celery -p > celery.log
```

### Running Commands in Windows

```bash
# Run a command in a specific window
command tmux send-keys -t na:shell_depot "python manage.py shell" C-m

# Clear a window
command tmux send-keys -t na:celery C-l

# Send text without executing (no C-m at end)
command tmux send-keys -t na:shell_depot "python manage.py"
```

## Troubleshooting

### Port Already in Use

If you get a "port already in use" error:

```bash
# Find process using port 8000
lsof -i :8000

# Kill process using port 8000
lsof -ti :8000 | xargs kill -9

# Or for port 8001
lsof -ti :8001 | xargs kill -9
```

### Session Already Exists

```bash
# Attach to existing session
tmux attach -t na

# Or kill and restart
tmux kill-session -t na
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

### Service Won't Start

1. Check the specific window for error messages:
   ```bash
   tmux select-window -t na:django
   ```

2. Capture recent output:
   ```bash
   tmux capture-pane -t na:django -p | tail -20
   ```

3. Try manual restart with error checking:
   ```bash
   command tmux send-keys -t na:django C-c
   sleep 2
   command tmux send-keys -t na:django "source venv/bin/activate && python manage.py runserver" C-m
   ```

### ZSH Alias Issues

If tmux commands fail due to ZSH aliases, use `command` prefix:
```bash
# Instead of
tmux list-sessions

# Use
command tmux list-sessions
```

## Environment Variables

The following environment variables are set for the Django servers:

### Web Server (Port 8000)
- `SERVER_ROLE=web`
- `INTERNAL_API_KEY=test-key-123`
- `SERVICES_URL=http://localhost:8001`

### Services Server (Port 8001)
- `SERVER_ROLE=services`
- `INTERNAL_API_KEY=test-key-123`

## Docker Services

The following Docker services are managed by `docker-compose.dev.yml`:

- **MariaDB**: Database server on port 3306
- **Redis**: Cache and message broker on port 6379
- **MinIO**: S3-compatible storage on port 9000/9001

View Docker logs:
```bash
# In tmux window
tmux select-window -t na:docker

# Or directly
docker compose -f docker-compose.dev.yml logs -f

# Specific service
docker compose -f docker-compose.dev.yml logs -f mariadb
```

## Quick Reference Card

```bash
# Start everything
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh

# Attach to session
tmux attach -t na

# Common navigation
Ctrl+b, 0-9     # Switch to window
Ctrl+b, n/p     # Next/previous window
Ctrl+b, d       # Detach from session
Ctrl+b, w       # Window list

# Quick service restarts
command tmux send-keys -t na:celery C-c    # Stop Celery
command tmux send-keys -t na:django C-c    # Stop Django
command tmux send-keys -t na:npm C-c       # Stop NPM

# View logs
tmux select-window -t na:celery
tmux select-window -t na:django
tmux select-window -t na:docker

# Emergency cleanup
tmux kill-session -t na                    # Kill entire session
lsof -ti :8000 | xargs kill -9            # Clear port 8000
lsof -ti :8001 | xargs kill -9            # Clear port 8001
```

## Tips and Best Practices

1. **Always use `command` prefix**: When running tmux commands from Claude or scripts, use `command tmux` to bypass ZSH aliases.

2. **Check service status**: After restarting a service, wait a few seconds and check its window for errors.

3. **Keep windows organized**: Each service has its dedicated window - avoid running other commands there to keep logs clean.

4. **Use capture-pane for debugging**: When a service fails, capture its output for analysis:
   ```bash
   tmux capture-pane -t na:django -p > django_error.log
   ```

5. **Session persistence**: Tmux sessions persist even if you disconnect. Your services keep running in the background.

6. **Multiple terminals**: You can attach to the same tmux session from multiple terminal windows with `tmux attach -t na`.

## Related Documentation

- [Development Streaming Setup](development_streaming_setup.md) - Details on the two-server architecture
- [Quick Start Streaming](quick_start_streaming.md) - Streaming configuration guide
- [NAS Configuration](nas_configuration.md) - File storage setup