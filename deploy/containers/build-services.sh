#!/bin/bash
# Fast Services Container Build Script
# Optimized build for Django/Celery with R and Quarto support

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🚀 Building Services Container (Django/R/Quarto)${NC}"

REGISTRY="ghcr.io/jhbiostatcenter/naaccord"
PLATFORM="linux/amd64"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Parse arguments
NO_CACHE=false
for arg in "$@"; do
    case $arg in
        --no-cache|--fresh)
            NO_CACHE=true
            shift
            ;;
        *)
            ;;
    esac
done

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

echo "Using ${CORES} cores, ${MEMORY_GB}GB RAM"

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_build() { echo -e "${CYAN}[BUILD]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

main() {
    print_build "Building services container (largest build, 15-30 minutes with R packages)..."

    # Check if in project directory
    if [ ! -f "manage.py" ]; then
        print_error "Run from NA-ACCORD project root"
        exit 1
    fi

    print_status "Building with maximum performance on ${CORES} cores..."
    START_TIME=$(date +%s)

    # Use Docker for builds with BuildKit and parallel execution
    export DOCKER_BUILDKIT=1
    export DOCKER_BUILDKIT_MAX_PARALLELISM=${CORES}
    BUILD_CMD="docker build"

    # Build args based on cache preference
    if [ "$NO_CACHE" = true ]; then
        print_warning "Building with --no-cache (fresh build, slower)"
        BUILD_ARGS="--no-cache --pull"

        # Clear Docker build cache for truly fresh build
        print_status "Clearing Docker build cache..."
        docker builder prune -af > /dev/null 2>&1 || true
    else
        print_status "Building with cache (faster for updates)"
        BUILD_ARGS="--pull"
    fi

    if ${BUILD_CMD} \
        ${BUILD_ARGS} \
        --platform "${PLATFORM}" \
        --build-arg NCPUS=${CORES} \
        --build-arg MAKEFLAGS=-j${CORES} \
        --label "org.opencontainers.image.created=${BUILD_DATE}" \
        --label "org.opencontainers.image.revision=${GIT_COMMIT}" \
        --label "org.opencontainers.image.source=https://github.com/JHBiostatCenter/naaccord" \
        -t "${REGISTRY}/services:latest" \
        -f deploy/containers/services/Dockerfile \
        . 2>&1 | tee "build-services.log"; then

        END_TIME=$(date +%s)
        BUILD_TIME=$((END_TIME - START_TIME))

        print_status "✓ Services container built in ${BUILD_TIME}s"

        # Test container
        print_status "Testing container..."
        if docker run --rm "${REGISTRY}/services:latest" python --version | head -1; then
            print_status "✓ Python working"
        else
            print_warning "⚠ Python test failed"
        fi

        if docker run --rm "${REGISTRY}/services:latest" R --version | head -1; then
            print_status "✓ R working"
        else
            print_warning "⚠ R test failed"
        fi

        # Show image info
        echo ""
        print_status "Image details:"
        docker images --format "table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}" | grep services

        echo ""
        print_status "🎉 Services container ready to use!"
        print_status "To push to registry:"
        echo "  ./push-services.sh"
    else
        END_TIME=$(date +%s)
        BUILD_TIME=$((END_TIME - START_TIME))
        print_error "✗ Services container build failed after ${BUILD_TIME}s"
        print_error "Check build-services.log for details"
        exit 1
    fi
}

if ! command -v docker &> /dev/null; then
    print_error "Docker not installed"
    exit 1
fi

main