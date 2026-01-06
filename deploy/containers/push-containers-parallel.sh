#!/bin/bash
# Parallel container push script
# Pushes all containers to registry in parallel

set -e

# Configuration
REGISTRY=${REGISTRY:-ghcr.io/jhbiostatcenter/naaccord}
VERSION=${VERSION:-latest}
PARALLEL_JOBS=${PARALLEL_JOBS:-4}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 NA-ACCORD Parallel Container Push${NC}"
echo -e "Registry: ${REGISTRY}"
echo -e "Version: ${VERSION}"

# Check if logged in to registry
check_registry_auth() {
    echo -e "${YELLOW}Checking registry authentication...${NC}"

    if [[ "$REGISTRY" == ghcr.io/* ]]; then
        if ! docker pull ghcr.io/hello-world 2>/dev/null; then
            echo -e "${RED}Not authenticated to GitHub Container Registry${NC}"
            echo "Please run: echo \$GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin"
            exit 1
        fi
    fi

    echo -e "${GREEN}✅ Registry authentication OK${NC}"
}

# Function to push container
push_container() {
    local name=$1
    local tag=${REGISTRY}/${name}:${VERSION}
    local latest=${REGISTRY}/${name}:latest

    echo -e "${BLUE}Pushing ${name}...${NC}"

    # Check if image exists
    if ! docker images -q ${tag} >/dev/null 2>&1; then
        echo -e "${RED}Image ${tag} not found locally${NC}"
        return 1
    fi

    # Push versioned tag
    if docker push ${tag}; then
        echo -e "${GREEN}✅ Pushed ${tag}${NC}"
    else
        echo -e "${RED}❌ Failed to push ${tag}${NC}"
        return 1
    fi

    # Push latest tag
    if docker push ${latest}; then
        echo -e "${GREEN}✅ Pushed ${latest}${NC}"
    else
        echo -e "${RED}❌ Failed to push ${latest}${NC}"
        return 1
    fi

    return 0
}

# Check authentication
check_registry_auth

# List of containers to push
containers=(
    "nginx"
    "web"
    "services"
    "wireguard"
)

# Get image sizes before push
echo -e "\n${BLUE}Images to push:${NC}"
for name in "${containers[@]}"; do
    size=$(docker images ${REGISTRY}/${name}:${VERSION} --format "{{.Size}}" 2>/dev/null || echo "Not found")
    echo -e "  ${name}: ${size}"
done

# Confirm push
echo -e "\n${YELLOW}Ready to push ${#containers[@]} containers to ${REGISTRY}${NC}"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 1
fi

# Track background jobs
pids=()
failed=()

# Start pushes in parallel
echo -e "\n${BLUE}Starting parallel push...${NC}"
start_time=$(date +%s)

for name in "${containers[@]}"; do
    # Run push in background
    (push_container "$name") &
    pids+=($!)

    # Limit parallel jobs
    while [ $(jobs -r | wc -l) -ge $PARALLEL_JOBS ]; do
        sleep 0.5
    done
done

# Wait for all pushes to complete
echo -e "\n${YELLOW}Waiting for pushes to complete...${NC}"
for i in "${!pids[@]}"; do
    pid=${pids[$i]}
    name=${containers[$i]}

    if wait $pid; then
        echo -e "${GREEN}✅ ${name} pushed${NC}"
    else
        echo -e "${RED}❌ ${name} failed${NC}"
        failed+=($name)
    fi
done

# Calculate time
end_time=$(date +%s)
duration=$((end_time - start_time))

# Summary
echo -e "\n${BLUE}Push Summary:${NC}"
echo -e "Total containers: ${#containers[@]}"
echo -e "Successful: $((${#containers[@]} - ${#failed[@]}))"
echo -e "Failed: ${#failed[@]}"
echo -e "Duration: ${duration} seconds"

if [ ${#failed[@]} -gt 0 ]; then
    echo -e "\n${RED}Failed containers:${NC}"
    for name in "${failed[@]}"; do
        echo -e "  - ${name}"
    done
    exit 1
fi

# Show registry URLs
echo -e "\n${GREEN}✅ All containers pushed successfully!${NC}"
echo -e "\n${BLUE}Registry URLs:${NC}"
for name in "${containers[@]}"; do
    echo -e "  ${REGISTRY}/${name}:${VERSION}"
done

echo -e "\n${YELLOW}Next steps:${NC}"
echo "  1. Deploy to staging:"
echo "     ssh staging 'cd /opt/naaccord && docker compose pull'"
echo "  2. Deploy to production:"
echo "     ssh production 'cd /opt/naaccord && docker compose pull'"