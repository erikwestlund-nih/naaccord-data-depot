#!/bin/bash
# Parallel container build script with optimizations
# Uses Docker BuildKit and parallel builds for speed

set -e

# Configuration
REGISTRY=${REGISTRY:-ghcr.io/jhbiostatcenter/naaccord}
VERSION=${VERSION:-latest}
PLATFORM=${PLATFORM:-linux/amd64}
PARALLEL_JOBS=${PARALLEL_JOBS:-4}
USE_CACHE=${USE_CACHE:-true}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 NA-ACCORD Parallel Container Build${NC}"
echo -e "Registry: ${REGISTRY}"
echo -e "Version: ${VERSION}"
echo -e "Platform: ${PLATFORM}"
echo -e "Parallel Jobs: ${PARALLEL_JOBS}"

# Enable Docker BuildKit for faster builds
export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain
export COMPOSE_DOCKER_CLI_BUILD=1

# Function to get CPU and memory info
get_system_info() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        CPUS=$(nproc)
        MEMORY=$(free -h | awk '/^Mem:/ {print $2}')
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        CPUS=$(sysctl -n hw.ncpu)
        MEMORY=$(echo "scale=0; $(sysctl -n hw.memsize) / 1024 / 1024 / 1024" | bc)G
    else
        CPUS=4
        MEMORY="Unknown"
    fi

    echo -e "${YELLOW}System Resources:${NC}"
    echo -e "  CPUs: ${CPUS}"
    echo -e "  Memory: ${MEMORY}"
    echo ""
}

# Function to build container with optimizations
build_container() {
    local name=$1
    local dockerfile=$2
    local context=$3
    local build_args=$4

    echo -e "${BLUE}Building ${name}...${NC}"

    # Prepare cache options
    CACHE_OPTS=""
    if [ "$USE_CACHE" = "true" ]; then
        CACHE_OPTS="--cache-from ${REGISTRY}/${name}:${VERSION} --cache-from ${REGISTRY}/${name}:latest"
    fi

    # Build with optimizations
    docker buildx build \
        --platform ${PLATFORM} \
        --file ${dockerfile} \
        --tag ${REGISTRY}/${name}:${VERSION} \
        --tag ${REGISTRY}/${name}:latest \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --build-arg VERSION=${VERSION} \
        ${build_args} \
        ${CACHE_OPTS} \
        --cpu-quota=$((100000 * CPUS / PARALLEL_JOBS)) \
        --memory=$(echo "scale=0; $(echo $MEMORY | sed 's/G//') / $PARALLEL_JOBS" | bc)g \
        --output type=docker \
        ${context} 2>&1 | tee /tmp/build-${name}.log

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ ${name} built successfully${NC}"
        return 0
    else
        echo -e "${RED}❌ ${name} build failed${NC}"
        return 1
    fi
}

# Get system info
get_system_info

# Create buildx builder with parallelization support
echo -e "${BLUE}Setting up Docker buildx...${NC}"
docker buildx create --use --name naaccord-builder --driver docker-container --platform ${PLATFORM} || true
docker buildx inspect --bootstrap

# Build containers in parallel
echo -e "${BLUE}Starting parallel builds...${NC}"

# Define build jobs
declare -A build_jobs=(
    ["nginx"]="deploy/containers/nginx/Dockerfile . "
    ["web"]="deploy/containers/web/Dockerfile . --build-arg PYTHON_VERSION=3.12"
    ["services"]="deploy/containers/services/Dockerfile . --build-arg PYTHON_VERSION=3.12"
    ["wireguard"]="deploy/containers/wireguard/Dockerfile . "
)

# Track background jobs
pids=()
failed=()

# Start builds in parallel
for name in "${!build_jobs[@]}"; do
    IFS=' ' read -r dockerfile context build_args <<< "${build_jobs[$name]}"

    # Run build in background
    (build_container "$name" "$dockerfile" "$context" "$build_args") &
    pids+=($!)

    # Limit parallel jobs
    while [ $(jobs -r | wc -l) -ge $PARALLEL_JOBS ]; do
        sleep 1
    done
done

# Wait for all builds to complete
echo -e "\n${YELLOW}Waiting for builds to complete...${NC}"
for i in "${!pids[@]}"; do
    pid=${pids[$i]}
    name=${!build_jobs[@]:$i:1}

    if wait $pid; then
        echo -e "${GREEN}✅ ${name} completed${NC}"
    else
        echo -e "${RED}❌ ${name} failed${NC}"
        failed+=($name)
    fi
done

# Summary
echo -e "\n${BLUE}Build Summary:${NC}"
echo -e "Total containers: ${#build_jobs[@]}"
echo -e "Successful: $((${#build_jobs[@]} - ${#failed[@]}))"
echo -e "Failed: ${#failed[@]}"

if [ ${#failed[@]} -gt 0 ]; then
    echo -e "\n${RED}Failed containers:${NC}"
    for name in "${failed[@]}"; do
        echo -e "  - ${name}"
        echo -e "    Check log: /tmp/build-${name}.log"
    done
    exit 1
fi

# Display image sizes
echo -e "\n${BLUE}Image Sizes:${NC}"
for name in "${!build_jobs[@]}"; do
    size=$(docker images ${REGISTRY}/${name}:${VERSION} --format "{{.Size}}")
    echo -e "  ${name}: ${size}"
done

echo -e "\n${GREEN}✅ All containers built successfully!${NC}"

# Cleanup buildx builder
docker buildx rm naaccord-builder || true

echo -e "\n${YELLOW}Next steps:${NC}"
echo "  1. Test containers locally:"
echo "     docker compose -f docker-compose.dev.yml up"
echo "  2. Push to registry:"
echo "     ./scripts/push-containers.sh"