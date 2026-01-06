#!/bin/bash
#
# NA-ACCORD Deployment Script
#
# This script runs the Ansible playbook to deploy NA-ACCORD infrastructure.
# Run this AFTER init-server.sh has completed successfully.
#
# Usage:
#   ./2-deploy.sh
#
# The script automatically detects:
#   - Environment from /etc/naaccord/environment (staging or production)
#   - Server role from /etc/naaccord/server-role (web or services)
#
# What it does:
#   1. Reads environment and server role from marker files
#   2. Validates configuration
#   3. Verifies vault password file exists
#   4. Runs appropriate Ansible playbook
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Constants
REPO_DIR="/opt/naaccord/depot"
ENV_MARKER_FILE="/etc/naaccord/environment"
ROLE_MARKER_FILE="/etc/naaccord/server-role"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}NA-ACCORD Deployment${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if init-server.sh was run
if [ ! -d "${REPO_DIR}" ]; then
    echo -e "${RED}ERROR: Repository not found at ${REPO_DIR}${NC}"
    echo "Please run 1-init-server.sh first"
    exit 1
fi

# Check for environment marker file (REQUIRED)
if [ ! -f "$ENV_MARKER_FILE" ]; then
    echo -e "${RED}================================${NC}"
    echo -e "${RED}ERROR: Server not configured!${NC}"
    echo -e "${RED}================================${NC}"
    echo ""
    echo "Environment marker file not found: $ENV_MARKER_FILE"
    echo ""
    echo "To create it manually:"
    echo ""
    echo "  For staging server:"
    echo "    sudo mkdir -p /etc/naaccord"
    echo "    echo 'staging' | sudo tee $ENV_MARKER_FILE"
    echo "    echo 'services' | sudo tee $ROLE_MARKER_FILE  # or 'web'"
    echo "    sudo chmod 644 /etc/naaccord/*"
    echo ""
    echo "  For production server:"
    echo "    sudo mkdir -p /etc/naaccord"
    echo "    echo 'production' | sudo tee $ENV_MARKER_FILE"
    echo "    echo 'services' | sudo tee $ROLE_MARKER_FILE  # or 'web'"
    echo "    sudo chmod 644 /etc/naaccord/*"
    echo ""
    echo "Or run 1-init-server.sh which creates these automatically."
    echo ""
    exit 1
fi

# Check for server role marker file (REQUIRED)
if [ ! -f "$ROLE_MARKER_FILE" ]; then
    echo -e "${RED}ERROR: Server role not configured!${NC}"
    echo "Role marker file not found: $ROLE_MARKER_FILE"
    echo "Run 1-init-server.sh or see instructions above."
    exit 1
fi

# Read marker files to auto-detect configuration
ENVIRONMENT=$(sudo cat "$ENV_MARKER_FILE" 2>/dev/null | tr -d '[:space:]')
SERVER_TYPE=$(sudo cat "$ROLE_MARKER_FILE" 2>/dev/null | tr -d '[:space:]')

# Validate environment marker
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}ERROR: Invalid environment marker${NC}"
    echo "File $ENV_MARKER_FILE contains: '$ENVIRONMENT'"
    echo "Must be 'staging' or 'production'"
    exit 1
fi

# Validate server role marker
if [[ ! "$SERVER_TYPE" =~ ^(services|web)$ ]]; then
    echo -e "${RED}ERROR: Invalid server role marker${NC}"
    echo "File $ROLE_MARKER_FILE contains: '$SERVER_TYPE'"
    echo "Must be 'services' or 'web'"
    exit 1
fi

echo -e "${GREEN}✓${NC} Detected environment: $ENVIRONMENT"
echo -e "${GREEN}✓${NC} Detected server role: $SERVER_TYPE"

# Set vault password file based on detected environment
VAULT_PASSWORD_FILE="$HOME/.naaccord_vault_${ENVIRONMENT}"

# Check vault password file
if [ ! -f "${VAULT_PASSWORD_FILE}" ]; then
    echo ""
    echo -e "${RED}ERROR: Vault password file not found${NC}"
    echo "Expected: ${VAULT_PASSWORD_FILE}"
    echo ""
    echo "Run 1-init-server.sh to create it, or create manually:"
    echo "  read -sp \"Enter vault password: \" VAULT_PASS && echo \"\$VAULT_PASS\" > ${VAULT_PASSWORD_FILE} && unset VAULT_PASS"
    echo "  chmod 600 ${VAULT_PASSWORD_FILE}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Vault password file found"
echo ""

# Set playbook based on server type
if [ "$SERVER_TYPE" = "services" ]; then
    PLAYBOOK="services-server.yml"
    echo -e "${GREEN}Deploying: Services Server${NC}"
else
    PLAYBOOK="web-server.yml"
    echo -e "${GREEN}Deploying: Web Server${NC}"
fi

echo ""
echo -e "${YELLOW}Pulling latest code from GitHub...${NC}"
cd "${REPO_DIR}"

# Determine branch based on environment
if [ "$ENVIRONMENT" = "production" ]; then
    BRANCH="main"
else
    BRANCH="main"  # Both staging and production use main for now
fi

git pull origin "$BRANCH"

echo ""
echo -e "${YELLOW}Running Ansible playbook...${NC}"
echo ""

cd "${REPO_DIR}/deploy/ansible"

ansible-playbook \
  -i "inventories/${ENVIRONMENT}/hosts.yml" \
  "playbooks/${PLAYBOOK}" \
  --connection local \
  --vault-password-file "${VAULT_PASSWORD_FILE}" \
  --ask-become-pass

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
