#!/bin/bash
# Service monitoring script for NA-ACCORD

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DEPLOY_PATH="${DEPLOY_PATH:-/opt/naaccord}"
LOG_FILE="/var/log/naaccord/monitor.log"
ALERT_EMAIL="${ALERT_EMAIL:-admin@naaccord.org}"

# Detect container runtime
if command -v docker &> /dev/null; then
    RUNTIME="docker"
elif command -v docker &> /dev/null; then
    RUNTIME="docker"
else
    echo "No container runtime found"
    exit 1
fi

# Create log directory
mkdir -p $(dirname "$LOG_FILE")

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to send alert
send_alert() {
    local subject=$1
    local message=$2

    # Log the alert
    log_message "ALERT: $subject - $message"

    # Send email if mail command exists
    if command -v mail &> /dev/null; then
        echo "$message" | mail -s "$subject" "$ALERT_EMAIL"
    fi
}

# Function to check container status
check_container() {
    local container=$1
    local status=$($RUNTIME ps --format "table {{.Names}}\t{{.Status}}" | grep $container | awk '{print $2}')

    if [[ $status == "Up"* ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check service health
check_health() {
    local service=$1
    local check_command=$2

    if eval $check_command &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to get container stats
get_container_stats() {
    local container=$1

    $RUNTIME stats --no-stream --format "json" $container 2>/dev/null | \
        python3 -c "import sys, json; \
        data = json.load(sys.stdin); \
        print(f\"CPU: {data.get('CPUPerc', 'N/A')}, Memory: {data.get('MemUsage', 'N/A')}\")"
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}NA-ACCORD Service Monitor${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Time: $(date)"
echo ""

# Initialize counters
SERVICES_OK=0
SERVICES_FAILED=0

# Check MariaDB
echo -e "${YELLOW}Checking MariaDB...${NC}"
if check_container "naaccord-mariadb"; then
    if $RUNTIME exec naaccord-mariadb mysqladmin ping -h localhost 2>/dev/null; then
        echo -e "${GREEN}✓ MariaDB: Running${NC}"
        echo "  Stats: $(get_container_stats naaccord-mariadb)"

        # Check encryption
        ENCRYPTION=$($RUNTIME exec naaccord-mariadb mysql -uroot -p${DB_ROOT_PASSWORD:-test_root_password} \
            -e "SHOW VARIABLES LIKE 'innodb_encrypt_tables'" 2>/dev/null | grep ON || true)
        if [ -n "$ENCRYPTION" ]; then
            echo -e "  ${GREEN}✓ Encryption: Enabled${NC}"
        else
            echo -e "  ${RED}✗ Encryption: Disabled${NC}"
        fi
        ((SERVICES_OK++))
    else
        echo -e "${RED}✗ MariaDB: Not responding${NC}"
        send_alert "MariaDB Down" "MariaDB container is running but not responding to ping"
        ((SERVICES_FAILED++))
    fi
else
    echo -e "${RED}✗ MariaDB: Container not running${NC}"
    send_alert "MariaDB Container Down" "MariaDB container is not running"
    ((SERVICES_FAILED++))
fi

# Check Redis
echo -e "\n${YELLOW}Checking Redis...${NC}"
if check_container "naaccord-redis"; then
    if $RUNTIME exec naaccord-redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo -e "${GREEN}✓ Redis: Running${NC}"
        echo "  Stats: $(get_container_stats naaccord-redis)"

        # Get Redis info
        REDIS_INFO=$($RUNTIME exec naaccord-redis redis-cli INFO server 2>/dev/null | grep redis_version | cut -d: -f2)
        echo "  Version: $REDIS_INFO"
        ((SERVICES_OK++))
    else
        echo -e "${RED}✗ Redis: Not responding${NC}"
        send_alert "Redis Down" "Redis container is running but not responding"
        ((SERVICES_FAILED++))
    fi
else
    echo -e "${RED}✗ Redis: Container not running${NC}"
    send_alert "Redis Container Down" "Redis container is not running"
    ((SERVICES_FAILED++))
fi

# Check Django
echo -e "\n${YELLOW}Checking Django...${NC}"
if check_container "naaccord-django"; then
    if curl -f http://localhost:8000/health/ &> /dev/null; then
        echo -e "${GREEN}✓ Django: Running${NC}"
        echo "  Stats: $(get_container_stats naaccord-django)"

        # Check migrations
        MIGRATIONS=$($RUNTIME exec naaccord-django python manage.py showmigrations --plan | tail -1)
        echo "  Last Migration: $MIGRATIONS"
        ((SERVICES_OK++))
    else
        echo -e "${RED}✗ Django: Health check failed${NC}"
        send_alert "Django Health Check Failed" "Django container is running but health check failed"
        ((SERVICES_FAILED++))
    fi
else
    echo -e "${RED}✗ Django: Container not running${NC}"
    send_alert "Django Container Down" "Django container is not running"
    ((SERVICES_FAILED++))
fi

# Check Celery
echo -e "\n${YELLOW}Checking Celery...${NC}"
if check_container "naaccord-celery"; then
    CELERY_STATUS=$($RUNTIME exec naaccord-celery celery -A depot inspect active 2>&1)
    if echo "$CELERY_STATUS" | grep -q "OK"; then
        echo -e "${GREEN}✓ Celery: Running${NC}"
        echo "  Stats: $(get_container_stats naaccord-celery)"

        # Get worker count
        WORKERS=$($RUNTIME exec naaccord-celery celery -A depot inspect active | grep -c "celery@" || echo "0")
        echo "  Active Workers: $WORKERS"
        ((SERVICES_OK++))
    else
        echo -e "${RED}✗ Celery: Not healthy${NC}"
        echo "  Status: $CELERY_STATUS"
        send_alert "Celery Unhealthy" "Celery workers are not healthy"
        ((SERVICES_FAILED++))
    fi
else
    echo -e "${RED}✗ Celery: Container not running${NC}"
    send_alert "Celery Container Down" "Celery container is not running"
    ((SERVICES_FAILED++))
fi

# Check Nginx
echo -e "\n${YELLOW}Checking Nginx...${NC}"
if check_container "naaccord-nginx"; then
    if curl -f http://localhost/health &> /dev/null; then
        echo -e "${GREEN}✓ Nginx: Running${NC}"
        echo "  Stats: $(get_container_stats naaccord-nginx)"

        # Check HTTPS
        if curl -kf https://localhost/health &> /dev/null; then
            echo -e "  ${GREEN}✓ HTTPS: Working${NC}"
        else
            echo -e "  ${RED}✗ HTTPS: Not working${NC}"
        fi
        ((SERVICES_OK++))
    else
        echo -e "${RED}✗ Nginx: Health check failed${NC}"
        send_alert "Nginx Health Check Failed" "Nginx container is running but health check failed"
        ((SERVICES_FAILED++))
    fi
else
    echo -e "${RED}✗ Nginx: Container not running${NC}"
    send_alert "Nginx Container Down" "Nginx container is not running"
    ((SERVICES_FAILED++))
fi

# Check disk space
echo -e "\n${YELLOW}Checking Disk Space...${NC}"
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓ Disk Usage: ${DISK_USAGE}%${NC}"
else
    echo -e "${RED}✗ Disk Usage: ${DISK_USAGE}% (High)${NC}"
    send_alert "High Disk Usage" "Disk usage is at ${DISK_USAGE}%"
fi

# Check for recent errors in logs
echo -e "\n${YELLOW}Checking Recent Errors...${NC}"
if [ -f "$DEPLOY_PATH/logs/django.log" ]; then
    ERROR_COUNT=$(grep -c "ERROR" "$DEPLOY_PATH/logs/django.log" 2>/dev/null || echo "0")
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "${YELLOW}⚠ Found $ERROR_COUNT errors in Django logs${NC}"
        RECENT_ERRORS=$(tail -n 100 "$DEPLOY_PATH/logs/django.log" | grep "ERROR" | tail -n 3)
        echo "Recent errors:"
        echo "$RECENT_ERRORS"
    else
        echo -e "${GREEN}✓ No recent errors in Django logs${NC}"
    fi
fi

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Monitor Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Services OK: ${GREEN}$SERVICES_OK${NC}"
echo -e "Services Failed: ${RED}$SERVICES_FAILED${NC}"

# Exit code based on failures
if [ "$SERVICES_FAILED" -gt 0 ]; then
    exit 1
else
    exit 0
fi