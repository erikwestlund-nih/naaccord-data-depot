#!/bin/bash
set -e

# Build All NA-ACCORD Containers Script
# Improved version based on Better Shoes patterns
# Runs individual build scripts in parallel for maximum speed

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}🚀 Building All NA-ACCORD Containers${NC}"

# Parse arguments to pass through to individual builds
BUILD_ARGS=""
for arg in "$@"; do
    case $arg in
        --no-cache|--fresh)
            BUILD_ARGS="--no-cache"
            echo -e "${YELLOW}Building with --no-cache (fresh builds, slower)${NC}"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --no-cache, --fresh    Build without Docker cache (slower, but ensures fresh build)"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Default: Builds with cache (faster for incremental changes)"
            exit 0
            ;;
        *)
            ;;
    esac
done

if [ -z "$BUILD_ARGS" ]; then
    echo -e "${GREEN}Building with cache (faster for updates)${NC}"
    echo "Use --no-cache or --fresh for clean rebuild"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Auto-detect resources
if command -v nproc &> /dev/null; then
    CORES=$(nproc)
elif [ -f /proc/cpuinfo ]; then
    CORES=$(grep -c ^processor /proc/cpuinfo)
else
    CORES=4  # fallback
fi

if [ -f /proc/meminfo ]; then
    MEMORY_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    MEMORY_GB=$((MEMORY_KB / 1024 / 1024))
else
    MEMORY_GB=8  # fallback
fi

echo -e "${CYAN}System Resources: ${CORES} cores, ${MEMORY_GB}GB RAM${NC}"

# Check if individual scripts exist
BUILD_SCRIPTS=(
    "build-services.sh"
    "build-nginx.sh"
    "build-web.sh"
    "build-wireguard.sh"
)

for script in "${BUILD_SCRIPTS[@]}"; do
    if [ ! -f "${SCRIPT_DIR}/${script}" ]; then
        echo -e "${RED}Error: ${script} not found${NC}"
        exit 1
    fi
    chmod +x "${SCRIPT_DIR}/${script}"
done

# Check if in project root
if [ ! -f "${PROJECT_ROOT}/manage.py" ]; then
    echo -e "${RED}Error: Run from NA-ACCORD project root${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

START_TIME=$(date +%s)

echo -e "${YELLOW}Starting parallel builds...${NC}"

# Run builds in background and track PIDs
declare -A BUILD_PIDS
declare -A BUILD_NAMES

echo "Starting services build (largest, ~15-30 min)..."
"${SCRIPT_DIR}/build-services.sh" ${BUILD_ARGS} &
BUILD_PIDS["services"]=$!
BUILD_NAMES["services"]="Services (Django/R/Quarto)"

echo "Starting nginx build (smallest, ~1 min)..."
"${SCRIPT_DIR}/build-nginx.sh" ${BUILD_ARGS} &
BUILD_PIDS["nginx"]=$!
BUILD_NAMES["nginx"]="Nginx"

echo "Starting web build (medium, ~5 min)..."
"${SCRIPT_DIR}/build-web.sh" ${BUILD_ARGS} &
BUILD_PIDS["web"]=$!
BUILD_NAMES["web"]="Web (Django frontend)"

echo "Starting wireguard build (small, ~1 min)..."
"${SCRIPT_DIR}/build-wireguard.sh" ${BUILD_ARGS} &
BUILD_PIDS["wireguard"]=$!
BUILD_NAMES["wireguard"]="WireGuard VPN"

# Wait for builds and track results
echo -e "${YELLOW}Waiting for builds to complete...${NC}"
declare -A BUILD_RESULTS
ALL_SUCCESS=true

for name in "${!BUILD_PIDS[@]}"; do
    pid=${BUILD_PIDS[$name]}
    description=${BUILD_NAMES[$name]}

    echo "Waiting for ${description}..."
    wait $pid
    exit_code=$?
    BUILD_RESULTS[$name]=$exit_code

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ ${description} completed successfully${NC}"
    else
        echo -e "${RED}❌ ${description} failed (exit code: $exit_code)${NC}"
        ALL_SUCCESS=false
    fi
done

END_TIME=$(date +%s)
BUILD_TIME=$((END_TIME - START_TIME))

# Summary
echo ""
echo -e "${BLUE}=========================${NC}"
echo -e "${BLUE}  BUILD SUMMARY${NC}"
echo -e "${BLUE}=========================${NC}"

for name in "${!BUILD_RESULTS[@]}"; do
    exit_code=${BUILD_RESULTS[$name]}
    description=${BUILD_NAMES[$name]}

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ ${description}${NC}"
    else
        echo -e "${RED}❌ ${description} (failed)${NC}"
    fi
done

echo ""
echo -e "${CYAN}Total build time: ${BUILD_TIME}s${NC}"

if [ "$ALL_SUCCESS" = true ]; then
    echo -e "${GREEN}🎉 All containers built successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Push to registry: ./scripts/push-all-containers.sh"
    echo "  2. Or push individually: ./scripts/push-<container>.sh"
    echo ""
    echo -e "${CYAN}Built images:${NC}"
    docker images | grep "ghcr.io/jhbiostatcenter/naaccord" || echo "No images found with registry prefix"
else
    echo -e "${RED}❌ Some builds failed${NC}"
    echo ""
    echo -e "${YELLOW}Check individual build logs:${NC}"
    for name in "${!BUILD_RESULTS[@]}"; do
        if [ ${BUILD_RESULTS[$name]} -ne 0 ]; then
            echo "  - Check build logs for ${name}"
        fi
    done
    exit 1
fi
