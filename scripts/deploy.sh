#!/bin/bash
#
# NA-ACCORD Deployment Script
# Pulls latest code from git and restarts containers
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.deploy.yml"
BACKUP_DIR="/var/backups/naaccord"
LOG_DIR="/var/log/naaccord"

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Pre-deployment checks
pre_deploy_checks() {
    log "Running pre-deployment checks..."

    # Check if we're in the right directory
    if [ ! -f "manage.py" ]; then
        error "Not in NA-ACCORD directory. Please run from project root."
        exit 1
    fi

    # Check if docker is running
    if ! docker info > /dev/null 2>&1; then
        error "Docker is not running"
        exit 1
    fi

    # Check if docker-compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        error "Docker compose file not found: $COMPOSE_FILE"
        exit 1
    fi

    log "Pre-deployment checks passed"
}

# Backup database
backup_database() {
    log "Backing up database..."

    # Create backup directory if it doesn't exist
    mkdir -p "$BACKUP_DIR"

    # Generate backup filename with timestamp
    BACKUP_FILE="$BACKUP_DIR/naaccord_$(date +'%Y%m%d_%H%M%S').sql"

    # Backup using docker exec or native mysqldump
    if docker ps | grep -q naaccord-mariadb; then
        docker exec naaccord-mariadb mysqldump -u root -p${DB_ROOT_PASSWORD:-root} naaccord > "$BACKUP_FILE"
    else
        mysqldump -h localhost -u root -p${DB_ROOT_PASSWORD:-root} naaccord > "$BACKUP_FILE" 2>/dev/null || {
            warning "Database backup skipped (database not accessible)"
            return
        }
    fi

    if [ -f "$BACKUP_FILE" ]; then
        gzip "$BACKUP_FILE"
        log "Database backed up to: ${BACKUP_FILE}.gz"

        # Keep only last 7 days of backups
        find "$BACKUP_DIR" -name "naaccord_*.sql.gz" -mtime +7 -delete
    fi
}

# Pull latest code
pull_latest_code() {
    log "Pulling latest code from git..."

    # Stash any local changes
    if [ -n "$(git status --porcelain)" ]; then
        warning "Local changes detected, stashing..."
        git stash save "Auto-stash before deployment $(date +'%Y-%m-%d %H:%M:%S')"
    fi

    # Pull latest from current branch
    CURRENT_BRANCH=$(git branch --show-current)
    log "Pulling latest from branch: $CURRENT_BRANCH"
    git pull origin "$CURRENT_BRANCH" || {
        error "Failed to pull from git"
        exit 1
    }

    log "Code updated successfully"
}

# Build containers if needed
build_containers() {
    log "Checking if containers need to be built..."

    # Check if Dockerfiles have changed
    if git diff HEAD@{1} --name-only | grep -qE "(Dockerfile|requirements.*\.txt)"; then
        log "Docker files changed, rebuilding containers..."
        docker-compose -f "$COMPOSE_FILE" build --parallel
    else
        log "No Docker changes detected, skipping build"
    fi
}

# Run migrations
run_migrations() {
    log "Running database migrations..."

    # Run migrations via docker
    docker-compose -f "$COMPOSE_FILE" exec -T django python manage.py migrate --noinput || {
        warning "Migration via docker failed, trying direct..."
        python manage.py migrate --noinput || {
            error "Migrations failed"
            return 1
        }
    }

    log "Migrations completed"
}

# Collect static files
collect_static() {
    log "Collecting static files..."

    docker-compose -f "$COMPOSE_FILE" exec -T django python manage.py collectstatic --noinput || {
        warning "Collectstatic via docker failed, trying direct..."
        python manage.py collectstatic --noinput || {
            warning "Collectstatic failed, continuing..."
        }
    }

    log "Static files collected"
}

# Restart services
restart_services() {
    log "Restarting services..."

    # Stop existing containers
    log "Stopping containers..."
    docker-compose -f "$COMPOSE_FILE" down

    # Start containers
    log "Starting containers..."
    docker-compose -f "$COMPOSE_FILE" up -d

    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 10

    # Check service health
    docker-compose -f "$COMPOSE_FILE" ps
}

# Health check
health_check() {
    log "Running health checks..."

    # Check web service
    if curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
        log "✓ Web service is healthy"
    else
        error "✗ Web service is not responding"
    fi

    # Check services API
    if curl -f http://localhost:8001/internal/storage/health > /dev/null 2>&1; then
        log "✓ Services API is healthy"
    else
        warning "✗ Services API is not responding"
    fi

    # Check Celery workers
    if docker exec naaccord-celery celery -A depot inspect active > /dev/null 2>&1; then
        log "✓ Celery workers are healthy"
    else
        warning "✗ Celery workers not responding"
    fi
}

# Clear caches
clear_caches() {
    log "Clearing caches..."

    # Clear Django cache
    docker-compose -f "$COMPOSE_FILE" exec -T django python manage.py clear_cache 2>/dev/null || true

    # Clear Redis cache
    docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli FLUSHDB 2>/dev/null || true

    log "Caches cleared"
}

# Main deployment flow
main() {
    log "========================================="
    log "NA-ACCORD Deployment Starting"
    log "========================================="

    # Parse arguments
    SKIP_BACKUP=false
    SKIP_BUILD=false
    CLEAR_CACHE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-backup)
                SKIP_BACKUP=true
                shift
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --clear-cache)
                CLEAR_CACHE=true
                shift
                ;;
            --help)
                echo "Usage: $0 [options]"
                echo "Options:"
                echo "  --skip-backup    Skip database backup"
                echo "  --skip-build     Skip container rebuild"
                echo "  --clear-cache    Clear all caches after deployment"
                echo "  --help           Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Run deployment steps
    pre_deploy_checks

    if [ "$SKIP_BACKUP" = false ]; then
        backup_database
    fi

    pull_latest_code

    if [ "$SKIP_BUILD" = false ]; then
        build_containers
    fi

    restart_services
    run_migrations
    collect_static

    if [ "$CLEAR_CACHE" = true ]; then
        clear_caches
    fi

    health_check

    log "========================================="
    log "Deployment completed successfully!"
    log "========================================="
}

# Run main function
main "$@"