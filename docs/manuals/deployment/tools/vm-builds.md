# NA-ACCORD Container Build Instructions for Linux VM

## VM Setup Requirements
- **CPU**: 12+ cores
- **RAM**: 32GB
- **Storage**: 100GB+ (containers with R packages are large)
- **OS**: Ubuntu 22.04 LTS or RHEL 9 compatible

## Initial VM Setup

### 1. Install Docker
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io git
sudo systemctl start docker
sudo systemctl enable docker

# RHEL/Rocky/AlmaLinux
sudo dnf install -y docker git
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (allows running docker without sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
```

### 2. Configure Docker daemon
```bash
# Configure Docker daemon for optimal performance
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "features": {
    "buildkit": true
  }
}
EOF

# Restart Docker to apply configuration
sudo systemctl restart docker

# Verify Docker configuration
docker info
```

### 3. Configure registry authentication
```bash
# Login to GitHub Container Registry
docker login ghcr.io
# Username: your-github-username
# Password: your-github-personal-access-token (with write:packages scope)
```

### 4. Clone the repository
```bash
# Clone NA-ACCORD repository
git clone https://github.com/JHBiostatCenter/naaccord.git
cd naaccord

# Or copy from your local machine
rsync -avz --exclude='venv' --exclude='node_modules' --exclude='storage' \
  /path/to/local/naaccord/ user@vm-ip:/home/user/naaccord/
```

## Building Containers

### Option 1: Build All Containers (Recommended)
```bash
# Build all containers with auto-resource detection and parallel processing
./scripts/build-all-containers.sh

# After builds complete, push to registry
./scripts/push-all-containers.sh
```

**Features of build script:**
- Auto-detects CPU cores and RAM
- Better parallel processing with PID tracking
- Docker BuildKit support for faster builds
- Cache clearing for clean builds
- Container testing after build
- Detailed progress reporting and timing

### Option 2: Individual Container Builds
```bash
# Build containers individually
./scripts/build-services.sh    # Largest, 15-30 minutes
./scripts/build-nginx.sh       # Small, ~1 minute
./scripts/build-web.sh         # Medium, ~5 minutes
./scripts/build-wireguard.sh   # Small, ~1 minute

# Push individually
./scripts/push-services.sh
./scripts/push-nginx.sh
./scripts/push-web.sh
./scripts/push-wireguard.sh
```

**Performance Benefits:**
- Better resource utilization with auto-detection
- Docker BuildKit for faster builds
- Parallel builds with proper error tracking
- Container validation after build

### Option 3: Manual Build Commands
```bash
# Build services (largest, ~2.5GB, takes 15-30 minutes)
docker build --platform linux/amd64 \
  -t ghcr.io/jhbiostatcenter/naaccord/services:latest \
  -f deploy/containers/services/Dockerfile .

# Build nginx (small, ~50MB, takes 1 minute)
docker build --platform linux/amd64 \
  -t ghcr.io/jhbiostatcenter/naaccord/nginx:latest \
  -f deploy/containers/nginx/Dockerfile deploy/containers/nginx/

# Build web (medium, ~500MB, takes 5 minutes)
docker build --platform linux/amd64 \
  -t ghcr.io/jhbiostatcenter/naaccord/web:latest \
  -f deploy/containers/web/Dockerfile .

# Build wireguard (small, ~20MB, takes 1 minute)
docker build --platform linux/amd64 \
  -t ghcr.io/jhbiostatcenter/naaccord/wireguard:latest \
  -f deploy/containers/wireguard/Dockerfile .
```

## Pushing to Registry

### Push all images
```bash
# Push individually
docker push ghcr.io/jhbiostatcenter/naaccord/services:latest
docker push ghcr.io/jhbiostatcenter/naaccord/nginx:latest
docker push ghcr.io/jhbiostatcenter/naaccord/web:latest
docker push ghcr.io/jhbiostatcenter/naaccord/wireguard:latest
```

## Optimizations for Large VM

### 1. Optimize Docker build performance
```bash
# Enable BuildKit for faster builds
export DOCKER_BUILDKIT=1

# Use multi-stage builds and cache mounts
docker build --build-arg BUILDKIT_INLINE_CACHE=1 \
  --cache-from type=registry,ref=ghcr.io/jhbiostatcenter/naaccord/services:latest \
  -t image:tag .
```

### 2. Use Docker buildx for advanced builds
```bash
# Create a new builder instance
docker buildx create --name mybuilder --use

# Build with buildx (supports advanced caching)
docker buildx build --platform linux/amd64 \
  --cache-from type=registry,ref=ghcr.io/jhbiostatcenter/naaccord/services:latest \
  --cache-to type=inline \
  -t ghcr.io/jhbiostatcenter/naaccord/services:latest \
  -f deploy/containers/services/Dockerfile .
```

### 3. Enable build caching
```bash
# Use Docker's built-in build cache
docker build --platform linux/amd64 \
  --cache-from ghcr.io/jhbiostatcenter/naaccord/services:latest \
  -t ghcr.io/jhbiostatcenter/naaccord/services:latest \
  -f deploy/containers/services/Dockerfile .
```

## Monitoring Builds

### Check build progress
```bash
# Watch build logs
tail -f build-*.log

# Monitor system resources during build
htop  # or top

# Check docker processes
docker ps -a

# Check disk usage
df -h
```

### View built images
```bash
# List all images
docker images

# Show image sizes
docker images --format "table {{.Repository}}:{{.Tag}} {{.Size}}"

# Inspect image details
docker inspect ghcr.io/jhbiostatcenter/naaccord/services:latest
```

## Troubleshooting

### If tex-common fails in services build
The Dockerfile already includes error handling for tex-common. If it still fails:
```bash
# Build without TeXLive packages (for testing)
# Edit deploy/containers/services/Dockerfile and comment out TeXLive installation
```

### If builds run out of memory
```bash
# Limit Docker memory usage
docker build --memory="8g" --memory-swap="8g" ...

# Or build sequentially
./scripts/build-all-containers.sh
```

### If push fails with authentication error
```bash
# Re-authenticate
docker logout ghcr.io
docker login ghcr.io

# Verify credentials
docker login --get-login ghcr.io
```

## Expected Build Times (with 12 cores, 32GB RAM)
- **services**: 15-30 minutes (installs R packages, TeXLive)
- **web**: 3-5 minutes (Node.js build)
- **nginx**: 30-60 seconds
- **wireguard**: 30-60 seconds
- **Total sequential**: ~25-40 minutes
- **Total parallel**: ~15-30 minutes

## Deployment Notes
Once images are pushed to ghcr.io, they can be pulled on production servers:
```bash
# On production server (with Docker)
docker pull ghcr.io/jhbiostatcenter/naaccord/services:latest
docker pull ghcr.io/jhbiostatcenter/naaccord/nginx:latest
docker pull ghcr.io/jhbiostatcenter/naaccord/web:latest
docker pull ghcr.io/jhbiostatcenter/naaccord/wireguard:latest
```