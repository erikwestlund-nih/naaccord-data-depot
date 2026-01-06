#!/bin/bash
# Build wireguard container only (fast, ~1 minute)

set -e

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

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_build() { echo -e "${BLUE}[BUILD]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

main() {
    print_build "Building wireguard container (VPN)..."
    print_status "This is a small container and builds quickly (~1 minute)"
    print_status "Registry: ${REGISTRY}/wireguard:latest"
    print_status "Platform: ${PLATFORM}"
    print_status "Using ${CORES} cores, ${MEMORY_GB}GB RAM"

    # Fix XDG_RUNTIME_DIR for docker - common ownership issue
    print_status "Setting up XDG_RUNTIME_DIR for docker..."
    USER_ID=$(id -u)
    export XDG_RUNTIME_DIR="/tmp/runtime-${USER_ID}"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
    print_status "XDG_RUNTIME_DIR set to: $XDG_RUNTIME_DIR"

    cd "$(dirname "$0")/../.."

    # Check if Dockerfile exists
    if [ ! -f "deploy/containers/wireguard/Dockerfile" ]; then
        print_error "WireGuard Dockerfile not found at deploy/containers/wireguard/Dockerfile"
        exit 1
    fi

    # Use docker for builds with BuildKit and parallel execution
    export DOCKER_BUILDKIT=1
    export DOCKER_BUILDKIT_MAX_PARALLELISM=${CORES}
    BUILD_CMD="docker build"

    # Build args based on cache preference
    if [ "$NO_CACHE" = true ]; then
        print_warning "Building with --no-cache (fresh build, slower)"
        BUILD_ARGS="--no-cache --pull"
    else
        print_status "Building with cache (faster for updates)"
        BUILD_ARGS="--pull"
    fi

    if ${BUILD_CMD} \
        ${BUILD_ARGS} \
        --platform "${PLATFORM}" \
        --label "org.opencontainers.image.created=${BUILD_DATE}" \
        --label "org.opencontainers.image.revision=${GIT_COMMIT}" \
        --label "org.opencontainers.image.source=https://github.com/JHBiostatCenter/naaccord" \
        -t "${REGISTRY}/wireguard:latest" \
        -f deploy/containers/wireguard/Dockerfile \
        . 2>&1 | tee "build-wireguard.log"; then

        print_status "✓ WireGuard container built successfully"

        # Show image info
        echo ""
        print_status "Image details:"
        docker images --format "table {{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}" | grep wireguard

        echo ""
        print_status "To push to registry:"
        echo "  ./push-wireguard.sh"
        echo ""
        print_status "To test locally:"
        echo "  docker run --rm ${REGISTRY}/wireguard:latest --help"
    else
        print_error "✗ WireGuard container build failed"
        print_warning "This may be due to missing scripts (healthcheck.sh, entrypoint.sh)"
        print_error "Check build-wireguard.log for details"

        # Show common missing files
        echo ""
        print_status "Checking for required files:"
        for file in scripts/healthcheck.sh scripts/entrypoint.sh; do
            if [ -f "$file" ]; then
                echo "  ✓ Found: $file"
            else
                echo "  ✗ Missing: $file"
            fi
        done

        exit 1
    fi
}

if ! command -v docker &> /dev/null; then
    print_error "Docker not installed"
    exit 1
fi

main