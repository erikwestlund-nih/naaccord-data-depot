#!/bin/bash
# Development setup script for NA-ACCORD with pre-built containers

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 NA-ACCORD Development Setup${NC}"

# Function to wait for database
wait_for_db() {
    echo -e "${YELLOW}Waiting for MariaDB to be ready...${NC}"
    while ! docker exec naaccord-mariadb mariadb -u root -pI4ms3cr3t -e "SELECT 1" >/dev/null 2>&1; do
        sleep 1
        echo -n "."
    done
    echo -e "${GREEN}✓ Database ready${NC}"
}

# Function to run management command in web container
run_manage() {
    docker exec naaccord-web python manage.py "$@"
}

# Parse arguments
RESET_DB=false
SKIP_SEED=false

for arg in "$@"; do
    case $arg in
        --reset-db)
            RESET_DB=true
            shift
            ;;
        --skip-seed)
            SKIP_SEED=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --reset-db     Drop and recreate database"
            echo "  --skip-seed    Skip seeding test data"
            echo "  --help         Show this help"
            exit 0
            ;;
    esac
done

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    exit 1
fi

# Create fake NAS directories for local development
echo -e "${BLUE}Creating storage directories...${NC}"
mkdir -p storage/nas/{uploads,reports,workspace,submissions,scratch,attachments}

# Stop any existing containers
echo -e "${BLUE}Stopping existing containers...${NC}"
docker compose -f docker-compose.dev-prebuilt.yml down

# Start infrastructure services first
echo -e "${BLUE}Starting infrastructure services...${NC}"
docker compose -f docker-compose.dev-prebuilt.yml up -d mariadb redis

# Wait for database
wait_for_db

# Start web container
echo -e "${BLUE}Starting web container...${NC}"
docker compose -f docker-compose.dev-prebuilt.yml up -d web

# Wait for web to be ready
echo -e "${YELLOW}Waiting for web container...${NC}"
sleep 5

# Reset database if requested
if [ "$RESET_DB" = true ]; then
    echo -e "${YELLOW}⚠️ Resetting database...${NC}"
    run_manage reset_db
fi

# Run migrations
echo -e "${BLUE}Running migrations...${NC}"
run_manage migrate

# Collect static files
echo -e "${BLUE}Collecting static files...${NC}"
run_manage collectstatic --noinput

# Seed initial data
if [ "$SKIP_SEED" = false ]; then
    echo -e "${BLUE}Seeding initial data...${NC}"
    run_manage seed_init || echo -e "${YELLOW}⚠️ Seed may have already run${NC}"

    echo -e "${BLUE}Setting up permission groups...${NC}"
    run_manage setup_permission_groups || echo -e "${YELLOW}⚠️ Groups may already exist${NC}"

    echo -e "${BLUE}Loading test users...${NC}"
    run_manage load_test_users || echo -e "${YELLOW}⚠️ Users may already exist${NC}"

    echo -e "${BLUE}Assigning users to groups...${NC}"
    run_manage assign_test_users_to_groups || echo -e "${YELLOW}⚠️ Assignments may already exist${NC}"
fi

# Start remaining services
echo -e "${BLUE}Starting remaining services...${NC}"
docker compose -f docker-compose.dev-prebuilt.yml up -d services celery nginx

# Show status
echo ""
echo -e "${GREEN}✅ Development environment ready!${NC}"
echo ""
echo "Services running:"
echo "  - Web:      http://localhost:8000"
echo "  - Services: http://localhost:8001"
echo "  - Nginx:    http://localhost"
echo ""
echo "Test users:"
echo "  - admin / Password123!"
echo "  - pi_vacs / test123"
echo "  - coord_vacs / test123"
echo ""
echo "To view logs:"
echo "  docker compose -f docker-compose.dev-prebuilt.yml logs -f [service]"
echo ""
echo "To stop all services:"
echo "  docker compose -f docker-compose.dev-prebuilt.yml down"