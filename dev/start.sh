#!/bin/bash
# NA-ACCORD Development Environment Startup Script
# One-command setup for local development with Docker

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[DEV]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        echo "Please install Docker from: https://docs.docker.com/get-docker/"
        exit 1
    fi

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        error "Docker Compose is not available"
        echo "Please ensure you have Docker Compose v2"
        exit 1
    fi

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running"
        echo "Please start Docker Desktop or the Docker daemon"
        exit 1
    fi

    success "All prerequisites met"
}

# Setup environment
setup_environment() {
    cd "$PROJECT_ROOT"

    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        log "Creating .env file from template..."
        if [ -f .env.example ]; then
            cp .env.example .env
            success "Created .env file"
        else
            warn "No .env.example found, creating basic .env"
            cat > .env << EOF
# NA-ACCORD Development Environment Variables
DEBUG=True
SECRET_KEY=django-insecure-dev-key-change-in-production
DATABASE_HOST=mariadb
DATABASE_NAME=naaccord
DATABASE_USER=naaccord
DATABASE_PASSWORD=I4ms3cr3t
DB_ROOT_PASSWORD=I4ms3cr3t
REDIS_PASSWORD=
INTERNAL_API_KEY=test-key-123
NAS_MOUNT_PATH=./storage/nas
FLOWER_USER=admin
FLOWER_PASSWORD=admin
EOF
            success "Created basic .env file"
        fi
    else
        log ".env file already exists"
    fi

    # Create necessary directories
    log "Creating necessary directories..."
    mkdir -p storage/nas storage/workspace logs
    success "Directories created"
}

# Start services
start_services() {
    log "Starting Docker services..."

    # Pull latest images (optional, comment out for faster startup)
    # docker compose -f docker-compose.dev.yml pull

    # Start all services
    docker compose -f docker-compose.dev.yml up -d --remove-orphans

    if [ $? -ne 0 ]; then
        error "Failed to start Docker services"
        exit 1
    fi

    success "Docker services started"
}

# Wait for services to be healthy
wait_for_services() {
    log "Waiting for services to be healthy..."

    # Wait for MariaDB
    log "Waiting for MariaDB..."
    until docker compose -f docker-compose.dev.yml exec -T mariadb \
        mariadb -u root -pI4ms3cr3t -e "SELECT 1" &> /dev/null; do
        echo -n "."
        sleep 2
    done
    echo ""
    success "MariaDB is ready"

    # Wait for Redis
    log "Waiting for Redis..."
    until docker compose -f docker-compose.dev.yml exec -T redis \
        redis-cli ping &> /dev/null; do
        echo -n "."
        sleep 1
    done
    echo ""
    success "Redis is ready"

    # Wait for Django web
    log "Waiting for Django web server..."
    until curl -f http://localhost:8000/health/ &> /dev/null; do
        echo -n "."
        sleep 2
    done
    echo ""
    success "Django web server is ready"

    # Wait for Django services
    log "Waiting for Django services server..."
    until curl -f http://localhost:8001/internal/storage/health &> /dev/null; do
        echo -n "."
        sleep 2
    done
    echo ""
    success "Django services server is ready"
}

# Run migrations
run_migrations() {
    log "Running database migrations..."
    docker compose -f docker-compose.dev.yml exec -T web \
        python manage.py migrate

    if [ $? -eq 0 ]; then
        success "Migrations completed"
    else
        warn "Migrations may have issues, check logs"
    fi
}

# Create test data
create_test_data() {
    log "Creating test users and data..."

    # Check if we need to create test data
    if docker compose -f docker-compose.dev.yml exec -T web \
        python -c "from django.contrib.auth import get_user_model; User = get_user_model(); exit(0 if User.objects.filter(username='admin').exists() else 1)" 2>/dev/null; then
        log "Test data already exists, skipping..."
    else
        log "Creating test users..."
        docker compose -f docker-compose.dev.yml exec -T web \
            python manage.py reset_dev_complete --skip-confirmation

        if [ $? -eq 0 ]; then
            success "Test data created"
        else
            warn "Failed to create test data, you may need to run manually"
        fi
    fi
}

# Show status
show_status() {
    echo ""
    echo "============================================="
    success "NA-ACCORD Development Environment Ready!"
    echo "============================================="
    echo ""
    echo "Services:"
    echo "  Web UI:          http://localhost:8000"
    echo "  Services API:    http://localhost:8001"
    echo "  Flower:          http://localhost:5555 (admin/admin)"
    echo "  Mock SAML IdP:   http://localhost:8080"
    echo ""
    echo "Database:"
    echo "  MariaDB:         localhost:3306 (naaccord/I4ms3cr3t)"
    echo "  Redis:           localhost:6379"
    echo ""
    echo "Useful commands:"
    echo "  View logs:       docker compose -f docker-compose.dev.yml logs -f [service]"
    echo "  Django shell:    docker compose -f docker-compose.dev.yml exec web python manage.py shell"
    echo "  Database shell:  docker compose -f docker-compose.dev.yml exec mariadb mysql -u naaccord -p"
    echo "  Stop all:        docker compose -f docker-compose.dev.yml down"
    echo "  Clean restart:   docker compose -f docker-compose.dev.yml down -v && $0"
    echo ""
    echo "Service status:"
    docker compose -f docker-compose.dev.yml ps
}

# Stop services
stop_services() {
    log "Stopping all services..."
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.dev.yml down
    success "All services stopped"
}

# Clean everything (including volumes)
clean_all() {
    warn "This will remove all containers, volumes, and data!"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$PROJECT_ROOT"
        docker compose -f docker-compose.dev.yml down -v
        rm -rf storage/nas/* storage/workspace/* logs/*
        success "All containers, volumes, and data removed"
    else
        log "Cancelled"
    fi
}

# Parse command line arguments
COMMAND=${1:-start}

case $COMMAND in
    start)
        echo "============================================="
        echo "Starting NA-ACCORD Development Environment"
        echo "============================================="
        echo ""
        check_prerequisites
        setup_environment
        start_services
        wait_for_services
        run_migrations
        create_test_data
        show_status
        ;;

    stop)
        stop_services
        ;;

    restart)
        stop_services
        echo ""
        exec "$0" start
        ;;

    status)
        cd "$PROJECT_ROOT"
        docker compose -f docker-compose.dev.yml ps
        ;;

    logs)
        cd "$PROJECT_ROOT"
        shift
        docker compose -f docker-compose.dev.yml logs -f $@
        ;;

    shell)
        cd "$PROJECT_ROOT"
        service=${2:-web}
        docker compose -f docker-compose.dev.yml exec $service bash
        ;;

    clean)
        clean_all
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs|shell|clean}"
        echo ""
        echo "Commands:"
        echo "  start    - Start all services and set up environment"
        echo "  stop     - Stop all services"
        echo "  restart  - Restart all services"
        echo "  status   - Show status of all services"
        echo "  logs     - Follow logs (optionally specify service)"
        echo "  shell    - Open bash shell in container (default: web)"
        echo "  clean    - Remove all containers, volumes, and data"
        exit 1
        ;;
esac