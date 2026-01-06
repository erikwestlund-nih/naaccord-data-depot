#!/bin/bash
#
# Build mock-idp container for NA-ACCORD staging
# Mimics JHU Shibboleth IDP for SAML testing
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="ghcr.io/jhbiostatcenter/naaccord/mock-idp"
TAG="${1:-latest}"

echo "=========================================="
echo "Building NA-ACCORD Mock IDP Container"
echo "=========================================="
echo ""
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Platform: linux/amd64"
echo ""

# Verify certificates exist
if [ ! -f "${SCRIPT_DIR}/mock-idp/cert/idp.key" ]; then
    echo "ERROR: Mock IDP certificates not found"
    echo "Run ./mock-idp/generate-certs.sh first"
    exit 1
fi

# Build the container
echo "Building container..."
docker build \
    --platform linux/amd64 \
    --tag "${IMAGE_NAME}:${TAG}" \
    --file "${SCRIPT_DIR}/mock-idp/Dockerfile" \
    "${SCRIPT_DIR}/mock-idp"

echo ""
echo "✓ Build complete: ${IMAGE_NAME}:${TAG}"
echo ""
echo "To push: ./push-mock-idp.sh ${TAG}"
echo "To test: docker run --rm -p 8080:8080 ${IMAGE_NAME}:${TAG}"
