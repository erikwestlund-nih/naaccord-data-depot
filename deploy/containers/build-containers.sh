#!/bin/bash
# NA-ACCORD Container Build Script
# Multi-platform build support with parallel option

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REGISTRY=${REGISTRY:-"ghcr.io/jhbiostatcenter/naaccord"}
PLATFORM=${PLATFORM:-"linux/amd64"}
VERSION=${VERSION:-$(git describe --tags --always 2>/dev/null || echo "latest")}
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
PUSH=${PUSH:-false}
PARALLEL=${PARALLEL:-true}  # Default to parallel builds
PARALLEL_JOBS=${PARALLEL_JOBS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}
USE_CACHE=${USE_CACHE:-true}
USE_OPTIMIZED=${USE_OPTIMIZED:-true}  # Use optimized Dockerfiles if available

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[BUILD]${NC} $1"
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
check_requirements() {
    log "Checking build requirements..."

    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi

    # Check for buildx
    if ! docker buildx version &> /dev/null; then
        error "Docker buildx is not available"
        exit 1
    fi

    success "All requirements met"
}

# Setup buildx builder
setup_builder() {
    BUILDER_NAME="naaccord-builder"

    # Check if builder exists
    if docker buildx ls | grep -q "$BUILDER_NAME"; then
        log "Using existing builder: $BUILDER_NAME"
    else
        log "Creating new builder: $BUILDER_NAME"
        docker buildx create --name "$BUILDER_NAME" \
            --driver docker-container \
            --platform "$PLATFORM" \
            --use
    fi

    docker buildx use "$BUILDER_NAME"
    docker buildx inspect --bootstrap
}

# Build a single container
build_container() {
    local service=$1
    local dockerfile=$2
    local context=$3
    local extra_args=$4

    log "Building $service container..."
    log "  Platform: $PLATFORM"
    log "  Version: $VERSION"
    log "  Registry: $REGISTRY"

    local tags=(
        "--tag" "$REGISTRY/naaccord-$service:$VERSION"
        "--tag" "$REGISTRY/naaccord-$service:latest"
    )

    local cache_args=(
        "--cache-from" "type=registry,ref=$REGISTRY/naaccord-$service:cache"
        "--cache-to" "type=registry,ref=$REGISTRY/naaccord-$service:cache,mode=max"
    )

    local build_args=(
        "--build-arg" "VERSION=$VERSION"
        "--build-arg" "BUILD_DATE=$BUILD_DATE"
    )

    # Add extra build args if provided
    if [ -n "$extra_args" ]; then
        build_args+=($extra_args)
    fi

    # Determine push behavior
    local output_arg
    if [ "$PUSH" = "true" ]; then
        output_arg="--push"
    else
        output_arg="--load"
    fi

    # Build the container
    docker buildx build \
        --platform "$PLATFORM" \
        "${tags[@]}" \
        "${cache_args[@]}" \
        "${build_args[@]}" \
        --label "org.opencontainers.image.version=$VERSION" \
        --label "org.opencontainers.image.created=$BUILD_DATE" \
        --label "org.opencontainers.image.source=https://github.com/naaccord/data-depot" \
        --label "org.opencontainers.image.title=naaccord-$service" \
        --file "$dockerfile" \
        "$output_arg" \
        "$context"

    if [ $? -eq 0 ]; then
        success "Built $service successfully"
    else
        error "Failed to build $service"
        return 1
    fi
}

# Build all containers
build_all() {
    cd "$PROJECT_ROOT"

    # Web container
    build_container "web" \
        "deploy/containers/web/Dockerfile" \
        "." \
        "--build-arg PYTHON_VERSION=3.12"

    # Services container (with R and Quarto)
    build_container "services" \
        "deploy/containers/services/Dockerfile" \
        "." \
        "--build-arg PYTHON_VERSION=3.12 --build-arg INSTALL_R=true --build-arg INSTALL_QUARTO=true"

    # Nginx container
    build_container "nginx" \
        "deploy/containers/nginx/Dockerfile" \
        "deploy/containers/nginx"

    # WireGuard container
    build_container "wireguard" \
        "deploy/containers/wireguard/Dockerfile" \
        "deploy/containers/wireguard"

    # Quarto executor (secure R/Quarto environment)
    build_container "quarto-executor" \
        "deploy/containers/quarto/Dockerfile" \
        "deploy/containers/quarto"
}

# Build specific service
build_service() {
    local service=$1
    cd "$PROJECT_ROOT"

    case $service in
        web)
            build_container "web" \
                "deploy/containers/web/Dockerfile" \
                "." \
                "--build-arg PYTHON_VERSION=3.12"
            ;;
        services)
            build_container "services" \
                "deploy/containers/services/Dockerfile" \
                "." \
                "--build-arg PYTHON_VERSION=3.12 --build-arg INSTALL_R=true --build-arg INSTALL_QUARTO=true"
            ;;
        nginx)
            build_container "nginx" \
                "deploy/containers/nginx/Dockerfile" \
                "deploy/containers/nginx"
            ;;
        wireguard)
            build_container "wireguard" \
                "deploy/containers/wireguard/Dockerfile" \
                "deploy/containers/wireguard"
            ;;
        quarto|quarto-executor)
            build_container "quarto-executor" \
                "deploy/containers/quarto/Dockerfile" \
                "deploy/containers/quarto"
            ;;
        *)
            error "Unknown service: $service"
            echo "Available services: web, services, nginx, wireguard, quarto"
            exit 1
            ;;
    esac
}

# Print usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [SERVICE]

Build NA-ACCORD Docker containers

OPTIONS:
    -r, --registry REGISTRY    Docker registry (default: localhost:5000)
    -p, --platform PLATFORM    Target platform (default: linux/amd64)
    -v, --version VERSION      Version tag (default: git tag or 'dev')
    -P, --push                 Push to registry after build
    -h, --help                 Show this help message

SERVICE:
    all         Build all containers (default)
    web         Build web server container
    services    Build services container (with R/Quarto)
    nginx       Build nginx container
    wireguard   Build WireGuard container
    quarto      Build Quarto executor container

EXAMPLES:
    # Build all containers for local development
    $0

    # Build and push to registry
    $0 --push --registry myregistry.com:5000

    # Build specific service for ARM64
    $0 --platform linux/arm64 web

    # Build for production with version tag
    $0 --version v1.2.3 --push --registry prod.registry.com
EOF
}

# Parse command line arguments
SERVICE="all"

while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--platform)
            PLATFORM="$2"
            shift 2
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -P|--push)
            PUSH=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            SERVICE="$1"
            shift
            ;;
    esac
done

# Main execution
echo "============================================="
echo "NA-ACCORD Container Build"
echo "============================================="
echo "Registry: $REGISTRY"
echo "Platform: $PLATFORM"
echo "Version:  $VERSION"
echo "Push:     $PUSH"
echo "Service:  $SERVICE"
echo "============================================="
echo ""

check_requirements
setup_builder

if [ "$SERVICE" = "all" ]; then
    build_all
else
    build_service "$SERVICE"
fi

echo ""
echo "============================================="
success "Build complete!"
echo "============================================="

if [ "$PUSH" = "false" ]; then
    echo ""
    warn "Containers built locally. To push to registry, use --push flag"
    echo ""
    echo "View built images:"
    echo "  docker images | grep naaccord"
fi