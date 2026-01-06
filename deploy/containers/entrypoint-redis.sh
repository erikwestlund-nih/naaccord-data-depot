#!/bin/sh
# Redis entrypoint script to read password from Docker secret

set -e

# Read Redis password from Docker secret
if [ -f "/run/secrets/redis_password" ]; then
    REDIS_PASSWORD=$(cat /run/secrets/redis_password)
    export REDIS_PASSWORD
else
    echo "ERROR: Redis password secret not found at /run/secrets/redis_password"
    exit 1
fi

# Start Redis with password from secret
exec redis-server \
    --maxmemory 512mb \
    --maxmemory-policy allkeys-lru \
    --requirepass "$REDIS_PASSWORD"
