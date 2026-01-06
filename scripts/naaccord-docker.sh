#!/bin/bash
# NA-ACCORD Docker Management Script
# Consolidated script for building and managing NA-ACCORD containers

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PARALLEL=true
ENV="dev"
COMPOSE_FILE=""
NAATOOLS_DEV=false

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Function to build containers
build_containers() {
    local env=$1
    local parallel=$2

    echo "═══════════════════════════════════════════"
    echo "Building NA-ACCORD Containers"
    echo "Environment: $env"
    echo "Parallel Build: $parallel"
    echo "═══════════════════════════════════════════"
    echo ""

    # Check if .dockerignore exists
    if [ ! -f .dockerignore ]; then
        print_error ".dockerignore not found! Creating one to avoid 16GB build context..."
        cat > .dockerignore << 'EOF'
# Large data directories
resources/data/
resources/nas/
ansible/
worklog/

# Build artifacts
static/
media/
storage/
*.pyc
__pycache__/
.pytest_cache/
.coverage
htmlcov/
.tox/

# Version control
.git/
.gitignore

# Virtual environments
venv/
env/
ENV/
.venv/

# IDE files
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Documentation
docs/
*.md

# Test data
tests/
test_*.py

# Node modules (if not needed in build)
node_modules/

# Database files
*.sqlite3
*.db

# Log files
*.log
logs/

# Temporary files
tmp/
temp/
*.tmp
EOF
        print_status ".dockerignore created"
    fi

    # Build commands based on parallel flag
    if [ "$parallel" = true ]; then
        print_info "Starting parallel container builds..."

        # Build all containers in parallel
        (
            echo "Building WireGuard container..."
            docker build -f deploy/containers/wireguard/Dockerfile -t naaccord-wireguard . 2>&1 | sed 's/^/[WireGuard] /'
        ) &

        (
            echo "Building Web container..."
            docker build -f deploy/containers/web/Dockerfile -t naaccord-web . 2>&1 | sed 's/^/[Web] /'
        ) &

        (
            echo "Building Services container (with R packages)..."
            docker build -f deploy/containers/services/Dockerfile -t naaccord-services . 2>&1 | sed 's/^/[Services] /'
        ) &

        # Wait for all builds to complete
        wait

        print_status "All containers built successfully"
    else
        print_info "Starting sequential container builds..."

        echo "Building WireGuard container..."
        docker build -f deploy/containers/wireguard/Dockerfile -t naaccord-wireguard .
        print_status "WireGuard container built"

        echo "Building Web container..."
        docker build -f deploy/containers/web/Dockerfile -t naaccord-web .
        print_status "Web container built"

        echo "Building Services container (with R packages)..."
        docker build -f deploy/containers/services/Dockerfile -t naaccord-services .
        print_status "Services container built"
    fi

    # Show container sizes
    echo ""
    echo "Container sizes:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep naaccord || true
}

# Function to start containers
start_containers() {
    local env=$1
    local compose_file=$2
    local naatools_dev=$3

    echo "═══════════════════════════════════════════"
    echo "Starting NA-ACCORD Containers"
    echo "Environment: $env"
    if [ "$naatools_dev" = true ]; then
        echo "NAATools Dev Mode: ENABLED"
    fi
    echo "═══════════════════════════════════════════"
    echo ""

    # Build compose command with optional NAATools dev overlay
    local compose_cmd="docker compose -f $compose_file"
    if [ "$naatools_dev" = true ]; then
        compose_cmd="$compose_cmd -f docker-compose.naatools-dev.yml"
        print_info "Mounting local NAATools from /Users/erikwestlund/code/NAATools"
    fi

    # Start containers
    eval "$compose_cmd up -d --remove-orphans"

    # Show running containers
    echo ""
    echo "Running containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep naaccord || true

    print_status "Containers started successfully"

    # Show service URLs
    echo ""
    echo "Service URLs:"
    if [ "$env" = "test" ]; then
        echo "  • Web Interface: http://localhost:8000"
        echo "  • Services API: http://localhost:8001"
        echo "  • SAML IdP: http://localhost:8080"
        echo "  • SAML IdP (HTTPS): https://localhost:8443"
    else
        echo "  • Web Interface: http://localhost:8000"
        echo "  • Services API: http://localhost:8001 (via WireGuard: 10.100.0.11)"
        echo "  • Vite Dev Server: http://localhost:3000"
    fi
    echo "  • MariaDB: localhost:3306"
    echo "  • Redis: localhost:6379"
}

# Function to stop containers
stop_containers() {
    local compose_file=$1

    echo "Stopping NA-ACCORD containers..."
    docker compose -f "$compose_file" down
    print_status "Containers stopped"
}

# Function to show logs
show_logs() {
    local compose_file=$1
    docker compose -f "$compose_file" logs -f
}

# Function to show status
show_status() {
    local compose_file=$1

    echo "═══════════════════════════════════════════"
    echo "NA-ACCORD Container Status"
    echo "═══════════════════════════════════════════"
    echo ""

    # Check services
    echo "Service Status:"

    if nc -z localhost 3306 2>/dev/null; then
        print_status "MariaDB is running (port 3306)"
    else
        print_error "MariaDB is not running"
    fi

    if nc -z localhost 6379 2>/dev/null; then
        print_status "Redis is running (port 6379)"
    else
        print_error "Redis is not running"
    fi

    if nc -z localhost 8000 2>/dev/null; then
        print_status "Web server is running (port 8000)"
    else
        print_error "Web server is not running"
    fi

    if nc -z localhost 8001 2>/dev/null; then
        print_status "Services server is running (port 8001)"
    else
        print_error "Services server is not running"
    fi

    if nc -z localhost 3000 2>/dev/null; then
        print_status "Vite dev server is running (port 3000)"
    else
        print_warning "Vite dev server is not running (dev mode only)"
    fi

    if nc -z localhost 8080 2>/dev/null; then
        print_status "SAML IdP is running (port 8080)"
    else
        print_warning "SAML IdP is not running (test mode only)"
    fi

    echo ""
    echo "Docker Containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "naaccord|NAME" || echo "No NA-ACCORD containers running"
}

# Function to clean up
cleanup() {
    echo "═══════════════════════════════════════════"
    echo "Cleaning Up NA-ACCORD Docker Resources"
    echo "═══════════════════════════════════════════"
    echo ""

    # Remove containers
    print_info "Removing stopped containers..."
    docker container prune -f

    # Remove unused images
    print_info "Removing unused images..."
    docker image prune -f

    # Remove build cache
    print_info "Removing build cache..."
    docker builder prune -f

    print_status "Cleanup complete"
}

# Parse command line arguments
COMMAND=${1:-help}
shift || true

while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --no-parallel)
            PARALLEL=false
            shift
            ;;
        --naatools-dev)
            NAATOOLS_DEV=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set compose file based on environment
if [ "$ENV" = "dev" ]; then
    COMPOSE_FILE="docker-compose.yml"
elif [ "$ENV" = "test" ]; then
    COMPOSE_FILE="docker-compose.yml"
elif [ "$ENV" = "prod" ]; then
    COMPOSE_FILE="docker-compose.deploy.yml"
else
    print_error "Invalid environment: $ENV (use dev, test, or prod)"
    exit 1
fi

# Execute command
case $COMMAND in
    build)
        build_containers "$ENV" "$PARALLEL"
        ;;
    start)
        start_containers "$ENV" "$COMPOSE_FILE" "$NAATOOLS_DEV"
        ;;
    stop)
        stop_containers "$COMPOSE_FILE"
        ;;
    restart)
        stop_containers "$COMPOSE_FILE"
        echo ""
        sleep 2
        start_containers "$ENV" "$COMPOSE_FILE" "$NAATOOLS_DEV"
        ;;
    logs)
        show_logs "$COMPOSE_FILE"
        ;;
    status)
        show_status "$COMPOSE_FILE"
        ;;
    cleanup)
        cleanup
        ;;
    all)
        # Build and start everything
        build_containers "$ENV" "$PARALLEL"
        echo ""
        start_containers "$ENV" "$COMPOSE_FILE" "$NAATOOLS_DEV"
        ;;
    help|*)
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  build    - Build all containers (parallel by default)"
        echo "  start    - Start all containers"
        echo "  stop     - Stop all containers"
        echo "  restart  - Restart all containers"
        echo "  logs     - Show and follow container logs"
        echo "  status   - Show service and container status"
        echo "  cleanup  - Clean up Docker resources"
        echo "  all      - Build and start everything"
        echo ""
        echo "Options:"
        echo "  --env <env>         - Environment (dev, test, prod) [default: dev]"
        echo "  --no-parallel       - Build containers sequentially"
        echo "  --naatools-dev      - Mount local NAATools for development"
        echo ""
        echo "Examples:"
        echo "  $0 build                       # Build containers for dev environment"
        echo "  $0 build --env test            # Build containers for test environment"
        echo "  $0 start --env dev             # Start dev environment"
        echo "  $0 start --env dev --naatools-dev  # Start with NAATools dev mode"
        echo "  $0 all --env dev               # Build and start dev environment"
        echo "  $0 build --no-parallel         # Build sequentially (for debugging)"
        ;;
esac