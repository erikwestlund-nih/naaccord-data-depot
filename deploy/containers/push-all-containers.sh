#!/bin/bash
set -e

# Push All NA-ACCORD Containers Script
# Pushes all containers to ghcr.io registry

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}🚀 Pushing All NA-ACCORD Containers to Registry${NC}"

REGISTRY="ghcr.io/jhbiostatcenter/naaccord"
CONTAINERS=("services" "nginx" "web" "wireguard")

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_push() { echo -e "${CYAN}[PUSH]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Check if images exist
print_status "Checking for built images..."
MISSING_IMAGES=()

for container in "${CONTAINERS[@]}"; do
    tag="${REGISTRY}/${container}:latest"
    if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${tag}$"; then
        MISSING_IMAGES+=("${container}")
    else
        # Show image info
        size=$(docker images --format "{{.Size}}" "${tag}")
        print_status "Found: ${container} (${size})"
    fi
done

if [ ${#MISSING_IMAGES[@]} -gt 0 ]; then
    print_error "Missing images: ${MISSING_IMAGES[*]}"
    print_status "Build missing images first:"
    for missing in "${MISSING_IMAGES[@]}"; do
        echo "  ./deploy/containers/build-${missing}.sh"
    done
    echo ""
    print_status "Or build all containers:"
    echo "  ./deploy/containers/build-all-containers.sh"
    exit 1
fi

# Check authentication
print_status "Checking registry authentication..."
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

# Confirm push
echo ""
print_push "Ready to push ${#CONTAINERS[@]} containers:"
for container in "${CONTAINERS[@]}"; do
    echo "  - ${REGISTRY}/${container}:latest"
done

echo ""
read -p "Continue with push? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Push cancelled"
    exit 0
fi

# Push containers sequentially for better error handling
START_TIME=$(date +%s)
declare -A PUSH_RESULTS
ALL_SUCCESS=true

echo ""
print_push "Starting container push..."

for container in "${CONTAINERS[@]}"; do
    tag="${REGISTRY}/${container}:latest"
    log_file="push-${container}.log"

    print_status "Pushing ${container}..."
    if docker push "${tag}" 2>&1 | tee "${log_file}"; then
        print_status "✓ ${container} pushed successfully"
        PUSH_RESULTS["${container}"]="SUCCESS"
        rm -f "${log_file}"
    else
        print_error "✗ ${container} push failed"
        PUSH_RESULTS["${container}"]="FAILED"
        ALL_SUCCESS=false
    fi
done

END_TIME=$(date +%s)
PUSH_TIME=$((END_TIME - START_TIME))

# Summary
echo ""
echo -e "${BLUE}=========================${NC}"
echo -e "${BLUE}  PUSH SUMMARY${NC}"
echo -e "${BLUE}=========================${NC}"

for container in "${CONTAINERS[@]}"; do
    result=${PUSH_RESULTS[${container}]}

    if [ "${result}" = "SUCCESS" ]; then
        echo -e "${GREEN}✅ ${container}${NC}"
    else
        echo -e "${RED}❌ ${container} (${result})${NC}"
    fi
done

echo ""
echo -e "${CYAN}Total push time: ${PUSH_TIME}s${NC}"

if [ "$ALL_SUCCESS" = true ]; then
    echo -e "${GREEN}🎉 All containers pushed successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Images available at:${NC}"
    for container in "${CONTAINERS[@]}"; do
        echo "  ${REGISTRY}/${container}:latest"
    done
    echo ""
    echo -e "${CYAN}To pull on production:${NC}"
    for container in "${CONTAINERS[@]}"; do
        echo "  docker pull ${REGISTRY}/${container}:latest"
    done
else
    echo -e "${RED}❌ Some pushes failed${NC}"
    echo ""
    echo -e "${YELLOW}Check individual push logs:${NC}"
    for container in "${CONTAINERS[@]}"; do
        result=${PUSH_RESULTS[${container}]}
        if [ "${result}" != "SUCCESS" ]; then
            echo "  - Check push-${container}.log"
        fi
    done
    exit 1
fi

print_status "✅ Push complete!"