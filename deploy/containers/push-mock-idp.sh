#!/bin/bash
#
# Push mock-idp container to GitHub Container Registry
#

set -e

IMAGE_NAME="ghcr.io/jhbiostatcenter/naaccord/mock-idp"
TAG="${1:-latest}"

echo "=========================================="
echo "Pushing NA-ACCORD Mock IDP Container"
echo "=========================================="
echo ""
echo "Image: ${IMAGE_NAME}:${TAG}"
echo ""

# Verify image exists
if ! docker image inspect "${IMAGE_NAME}:${TAG}" >/dev/null 2>&1; then
    echo "ERROR: Image not found: ${IMAGE_NAME}:${TAG}"
    echo "Build it first: ./build-mock-idp.sh ${TAG}"
    exit 1
fi

# Push to registry
echo "Pushing to GHCR..."
docker push "${IMAGE_NAME}:${TAG}"

echo ""
echo "✓ Push complete: ${IMAGE_NAME}:${TAG}"
echo ""
echo "Pull command:"
echo "  docker pull ${IMAGE_NAME}:${TAG}"
