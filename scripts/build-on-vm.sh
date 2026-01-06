#!/bin/bash
# NA-ACCORD Remote VM Build Script
# Build containers on a fast AMD64 VM for better performance

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VM_HOST=${BUILD_VM:-"build.example.com"}
VM_USER=${BUILD_VM_USER:-"builder"}
VM_PATH=${BUILD_VM_PATH:-"/tmp/naaccord-build"}
REGISTRY=${REGISTRY:-"localhost:5000"}
VERSION=${VERSION:-$(git describe --tags --always 2>/dev/null || echo "dev")}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[VM-BUILD]${NC} $1"
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

# Check SSH connectivity
check_ssh() {
    log "Checking SSH connection to $VM_HOST..."

    if ! ssh -o ConnectTimeout=5 "$VM_USER@$VM_HOST" "echo 'SSH OK'" &> /dev/null; then
        error "Cannot connect to build VM at $VM_USER@$VM_HOST"
        echo ""
        echo "Please ensure:"
        echo "  1. VM_HOST environment variable is set correctly"
        echo "  2. SSH key is configured for passwordless access"
        echo "  3. Build VM is running and accessible"
        echo ""
        echo "Example:"
        echo "  export BUILD_VM=build.example.com"
        echo "  export BUILD_VM_USER=builder"
        echo "  $0"
        exit 1
    fi

    success "SSH connection established"
}

# Sync code to VM
sync_code() {
    log "Syncing code to $VM_HOST:$VM_PATH..."

    # Create remote directory
    ssh "$VM_USER@$VM_HOST" "mkdir -p $VM_PATH"

    # Sync files (excluding unnecessary directories)
    rsync -avz --delete \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='venv' \
        --exclude='*.pyc' \
        --exclude='__pycache__' \
        --exclude='storage' \
        --exclude='media' \
        --exclude='static' \
        --exclude='.env' \
        --exclude='*.log' \
        --progress \
        "$PROJECT_ROOT/" \
        "$VM_USER@$VM_HOST:$VM_PATH/"

    if [ $? -eq 0 ]; then
        success "Code synced successfully"
    else
        error "Failed to sync code"
        exit 1
    fi
}

# Build containers on VM
build_on_vm() {
    log "Building containers on VM..."

    local build_command="cd $VM_PATH && \
        REGISTRY=$REGISTRY \
        VERSION=$VERSION \
        PLATFORM=linux/amd64 \
        PUSH=true \
        ./deploy/containers/build-containers.sh $*"

    ssh "$VM_USER@$VM_HOST" "$build_command"

    if [ $? -eq 0 ]; then
        success "Build completed on VM"
    else
        error "Build failed on VM"
        exit 1
    fi
}

# Pull images locally (optional)
pull_images() {
    log "Pulling built images to local machine..."

    local services=("web" "services" "nginx" "wireguard" "quarto-executor")

    for service in "${services[@]}"; do
        log "Pulling naaccord-$service:$VERSION..."
        docker pull "$REGISTRY/naaccord-$service:$VERSION"

        if [ $? -eq 0 ]; then
            success "Pulled $service"
            # Also tag as latest locally
            docker tag "$REGISTRY/naaccord-$service:$VERSION" "naaccord-$service:latest"
        else
            warn "Failed to pull $service (might not be built)"
        fi
    done
}

# Clean up VM workspace
cleanup_vm() {
    log "Cleaning up VM workspace..."
    ssh "$VM_USER@$VM_HOST" "rm -rf $VM_PATH"
    success "VM workspace cleaned"
}

# Print usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [SERVICE]

Build NA-ACCORD containers on a remote VM

OPTIONS:
    -v, --vm HOST              Build VM hostname (default: from BUILD_VM env)
    -u, --user USER            VM user (default: builder)
    -r, --registry REGISTRY    Docker registry (default: localhost:5000)
    -V, --version VERSION      Version tag (default: git tag or 'dev')
    -p, --pull                 Pull images to local after build
    -c, --cleanup              Clean up VM workspace after build
    -h, --help                 Show this help message

SERVICE:
    all         Build all containers (default)
    web         Build web server container
    services    Build services container
    nginx       Build nginx container
    wireguard   Build WireGuard container
    quarto      Build Quarto executor container

ENVIRONMENT VARIABLES:
    BUILD_VM        Build VM hostname
    BUILD_VM_USER   Build VM user (default: builder)
    BUILD_VM_PATH   Build path on VM (default: /tmp/naaccord-build)

EXAMPLES:
    # Build all containers on VM
    export BUILD_VM=fast-builder.internal
    $0

    # Build and pull specific service
    $0 --vm build.example.com --pull web

    # Build with custom version and cleanup
    $0 --version v1.2.3 --cleanup all
EOF
}

# Parse command line arguments
SERVICE="all"
PULL_AFTER=false
CLEANUP_AFTER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--vm)
            VM_HOST="$2"
            shift 2
            ;;
        -u|--user)
            VM_USER="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -V|--version)
            VERSION="$2"
            shift 2
            ;;
        -p|--pull)
            PULL_AFTER=true
            shift
            ;;
        -c|--cleanup)
            CLEANUP_AFTER=true
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
echo "NA-ACCORD Remote VM Build"
echo "============================================="
echo "Build VM:  $VM_USER@$VM_HOST"
echo "VM Path:   $VM_PATH"
echo "Registry:  $REGISTRY"
echo "Version:   $VERSION"
echo "Service:   $SERVICE"
echo "Pull:      $PULL_AFTER"
echo "Cleanup:   $CLEANUP_AFTER"
echo "============================================="
echo ""

# Execute build steps
check_ssh
sync_code
build_on_vm "$SERVICE"

if [ "$PULL_AFTER" = "true" ]; then
    pull_images
fi

if [ "$CLEANUP_AFTER" = "true" ]; then
    cleanup_vm
fi

echo ""
echo "============================================="
success "Remote build complete!"
echo "============================================="
echo ""
echo "Images are available in registry: $REGISTRY"
echo ""
echo "To use in Docker Compose:"
echo "  export REGISTRY=$REGISTRY"
echo "  export VERSION=$VERSION"
echo "  docker compose up"