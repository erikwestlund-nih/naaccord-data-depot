# NA-ACCORD Docker Setup Documentation

## Overview

NA-ACCORD is fully containerized using Docker for both development and production environments. This guide covers the complete Docker setup, including the two-server architecture, WireGuard encryption for PHI data, and simplified developer workflows.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Docker Networks                     │
├────────────┬────────────────┬────────────────────────┤
│   public   │    internal    │      wireguard         │
└────────────┴────────────────┴────────────────────────┘
      │              │                   │
  ┌───┴───┐    ┌─────┴─────┐      ┌─────┴─────┐
  │ nginx │    │  mariadb  │      │ wireguard │
  └───┬───┘    │   redis   │      │  tunnel   │
      │        │   celery  │      └─────┬─────┘
  ┌───┴───┐    └─────┬─────┘            │
  │  web  ├──────────┴──────────────────┤
  └───────┘    ┌───────────┐            │
               │ services  ├────────────┘
               └───────────┘
```

### Services

- **nginx**: Reverse proxy with SSL termination
- **web**: Django web server (SERVER_ROLE=web)
- **services**: Django API server (SERVER_ROLE=services)
- **celery**: Background task workers
- **mariadb**: Database (development only, production uses external)
- **redis**: Cache and message broker
- **wireguard**: Encrypted tunnel for PHI data transfer
- **flower**: Celery monitoring (development only)
- **mock-idp**: SAML testing (development only)

## Quick Start

### Prerequisites

- Docker Desktop (Mac/Windows) or Docker Engine (Linux)
- Docker Compose v2.0+
- Git
- 8GB+ RAM available for Docker

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/naaccord/data-depot.git
   cd naaccord
   ```

2. **Start the development environment**
   ```bash
   ./dev/start.sh
   ```

   This single command:
   - Creates necessary directories
   - Sets up environment variables
   - Starts all Docker containers
   - Runs database migrations
   - Creates test users
   - Shows service status

3. **Access the application**
   - Web UI: http://localhost:8000
   - Services API: http://localhost:8001
   - Flower: http://localhost:5555 (admin/admin)
   - Mock SAML IdP: http://localhost:8080

### Using tmux (Optional)

For developers who prefer tmux for session management:

```bash
./dev/tmux.sh create
```

This creates a tmux session with pre-configured windows:
- Window 0: Docker logs
- Window 1: Web container shell
- Window 2: Services container shell
- Window 3: Django Python shell
- Window 4: MariaDB client
- Window 5: Redis CLI
- Window 6: Celery logs
- Window 7: Local shell
- Window 8: Status monitor

## Container Management

### Starting Services

```bash
# Start all services
./dev/start.sh start

# Or using docker-compose directly
docker compose -f docker-compose.dev.yml up -d
```

### Stopping Services

```bash
# Stop all services
./dev/start.sh stop

# Or using docker-compose directly
docker compose -f docker-compose.dev.yml down
```

### Viewing Logs

```bash
# Follow all logs
docker compose -f docker-compose.dev.yml logs -f

# Follow specific service logs
docker compose -f docker-compose.dev.yml logs -f web
docker compose -f docker-compose.dev.yml logs -f services celery
```

### Accessing Containers

```bash
# Open bash shell in web container
docker compose -f docker-compose.dev.yml exec web bash

# Run Django management commands
docker compose -f docker-compose.dev.yml exec web python manage.py shell
docker compose -f docker-compose.dev.yml exec web python manage.py migrate
docker compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Access database
docker compose -f docker-compose.dev.yml exec mariadb mysql -u naaccord -p
```

### Rebuilding Containers

```bash
# Rebuild all containers
docker compose -f docker-compose.dev.yml build

# Rebuild specific service
docker compose -f docker-compose.dev.yml build web

# Rebuild without cache
docker compose -f docker-compose.dev.yml build --no-cache
```

## Building Containers

### Local Build

```bash
# Build all containers
./deploy/containers/build-containers.sh

# Build specific service
./deploy/containers/build-containers.sh web

# Build and push to registry
./deploy/containers/build-containers.sh --push --registry myregistry.com:5000
```

### Remote VM Build (for fast AMD64 builds)

```bash
# Set build VM
export BUILD_VM=fast-builder.example.com

# Build on VM
./scripts/build-on-vm.sh

# Build and pull to local
./scripts/build-on-vm.sh --pull

# Build specific service
./scripts/build-on-vm.sh web
```

## Production Deployment

### Environment Setup

1. **Create production environment file**
   ```bash
   cp .env.example .env.prod
   # Edit .env.prod with production values
   ```

2. **Configure external database**
   ```bash
   # In .env.prod
   DATABASE_HOST=your-mariadb-server.example.com
   DATABASE_PORT=3306
   DATABASE_NAME=naaccord_prod
   DATABASE_USER=naaccord_prod
   DATABASE_PASSWORD=secure-password
   ```

3. **Create Docker secrets**
   ```bash
   echo "your-api-key" | docker secret create internal_api_key -
   echo "your-db-password" | docker secret create db_password -
   echo "your-django-secret" | docker secret create django_secret_key -
   ```

### Deploy to Production

```bash
# Deploy with Docker Swarm
docker stack deploy -c docker-compose.prod.yml naaccord

# Or use Docker Compose
docker compose -f docker-compose.prod.yml up -d
```

## WireGuard Configuration

### Development

WireGuard runs automatically in development with pre-configured keys. No additional setup required.

### Production

1. **Generate WireGuard keys**
   ```bash
   # Generate private key
   wg genkey > wg-private.key

   # Generate public key
   wg pubkey < wg-private.key > wg-public.key

   # Generate preshared key
   wg genpsk > wg-preshared.key
   ```

2. **Create Docker secrets**
   ```bash
   docker secret create wg_web_private_key wg-private.key
   docker secret create wg_web_public_key wg-public.key
   docker secret create wg_preshared_key wg-preshared.key
   ```

3. **Configure in docker-compose.prod.yml**
   - Keys are loaded from Docker secrets
   - Tunnel IPs are pre-configured (10.100.0.10/11)
   - PHI data flows through encrypted tunnel

## File Permissions

Docker uses consistent UID/GID (1000:1000) across all containers to avoid permission issues:

- All containers run as user 1000:1000
- Volumes are mounted with proper permissions
- NAS mount uses driver options for correct ownership

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose -f docker-compose.dev.yml logs web

# Check container status
docker compose -f docker-compose.dev.yml ps

# Rebuild container
docker compose -f docker-compose.dev.yml build --no-cache web
```

### Database Connection Issues

```bash
# Check MariaDB is running
docker compose -f docker-compose.dev.yml ps mariadb

# Test connection
docker compose -f docker-compose.dev.yml exec mariadb \
  mysql -u naaccord -pI4ms3cr3t -e "SELECT 1"

# Check environment variables
docker compose -f docker-compose.dev.yml exec web env | grep DATABASE
```

### Permission Errors

```bash
# Fix volume permissions
sudo chown -R 1000:1000 ./storage

# Check container user
docker compose -f docker-compose.dev.yml exec web id
```

### Clean Restart

```bash
# Remove everything and start fresh
docker compose -f docker-compose.dev.yml down -v
rm -rf storage/nas/* storage/workspace/*
./dev/start.sh
```

## Migration from Bare Metal

### Step 1: Backup Existing Data

```bash
# Backup database
mysqldump -u naaccord -p naaccord > backup.sql

# Backup files
tar -czf files-backup.tar.gz storage/
```

### Step 2: Stop Existing Services

```bash
# Stop existing services
sudo systemctl stop nginx
sudo systemctl stop django
sudo systemctl stop celery
```

### Step 3: Deploy with Docker

```bash
# Start Docker services
./dev/start.sh

# Restore database
docker compose -f docker-compose.dev.yml exec -T mariadb \
  mysql -u naaccord -pI4ms3cr3t naaccord < backup.sql

# Restore files
tar -xzf files-backup.tar.gz
```

## Key Differences from Docker

This setup uses Docker instead of Docker to avoid:
- Complex permission issues with rootless containers
- UID/GID mapping problems
- NAS mount permission conflicts
- WireGuard kernel module complications

Docker provides:
- Simpler permission model with consistent UIDs
- Better volume driver support
- Native WireGuard userspace support
- Easier cross-platform compatibility

## Support

For issues or questions:
- Check logs: `docker compose logs -f [service]`
- Review this documentation
- Contact the development team