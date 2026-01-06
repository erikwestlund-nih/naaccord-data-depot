#!/bin/bash
# Push web container to registry

set -e

REGISTRY="ghcr.io/jhbiostatcenter/naaccord"
IMAGE_NAME="web"
TAG="${REGISTRY}/${IMAGE_NAME}:latest"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_push() { echo -e "${CYAN}[PUSH]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

main() {
    print_push "Pushing web container to registry..."

    # Fix XDG_RUNTIME_DIR for docker - common ownership issue
    print_status "Setting up XDG_RUNTIME_DIR for docker..."
    USER_ID=$(id -u)
    export XDG_RUNTIME_DIR="/tmp/runtime-${USER_ID}"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
    print_status "XDG_RUNTIME_DIR set to: $XDG_RUNTIME_DIR"

    # Check if image exists
    if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${TAG}$"; then
        print_error "Image ${TAG} not found locally"
        print_status "Build it first with: ./deploy/containers/build-web.sh"
        exit 1
    fi

    # Get image size
    size=$(docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | grep "${TAG}" | awk '{print $2}')
    print_status "Image: ${TAG}"
    print_status "Size: ${size}"

    # Check authentication
    if ! docker login --get-login ghcr.io &> /dev/null; then
        print_warning "Not logged in to ghcr.io"
        read -p "Login now? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker login ghcr.io
        else
            print_error "Cannot push without authentication"
            exit 1
        fi
    fi

    # Push the image
    print_status "Pushing ${IMAGE_NAME} to registry..."
    if docker push "${TAG}" 2>&1 | tee "push-${IMAGE_NAME}.log"; then
        print_status "✓ Successfully pushed ${IMAGE_NAME}"
        echo ""
        print_status "Image available at: ${TAG}"
        print_status "To pull on production:"
        echo "  docker pull ${TAG}"
    else
        print_error "✗ Failed to push ${IMAGE_NAME}"
        print_error "Check push-${IMAGE_NAME}.log for details"
        exit 1
    fi
}

if ! command -v docker &> /dev/null; then
    print_error "Docker not installed"
    exit 1
fi

main
