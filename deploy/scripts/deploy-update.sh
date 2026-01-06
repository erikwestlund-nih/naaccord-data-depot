#!/bin/bash
# Quick deployment script - Updates code and containers only
# Safe to run repeatedly for application updates
# Auto-detects environment from /etc/naaccord/environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="$SCRIPT_DIR/../ansible"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}NA-ACCORD Quick Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Detect environment
if [ -f /etc/naaccord/environment ]; then
    ENVIRONMENT=$(cat /etc/naaccord/environment)
    echo -e "${GREEN}✓${NC} Detected environment: ${BLUE}$ENVIRONMENT${NC}"
else
    echo -e "${RED}✗${NC} Could not detect environment"
    echo "Expected /etc/naaccord/environment with 'staging' or 'production'"
    exit 1
fi

# Determine inventory and vault
case $ENVIRONMENT in
    staging)
        INVENTORY="$ANSIBLE_DIR/inventories/staging/hosts.yml"
        VAULT_FILE="$HOME/.naaccord_vault_staging"
        ;;
    production)
        INVENTORY="$ANSIBLE_DIR/inventories/production/hosts.yml"
        VAULT_FILE="$HOME/.naaccord_vault_production"
        ;;
    *)
        echo -e "${RED}✗${NC} Unknown environment: $ENVIRONMENT"
        exit 1
        ;;
esac

# Verify files exist
if [ ! -f "$INVENTORY" ]; then
    echo -e "${RED}✗${NC} Inventory not found: $INVENTORY"
    exit 1
fi

if [ ! -f "$VAULT_FILE" ]; then
    echo -e "${RED}✗${NC} Vault password file not found: $VAULT_FILE"
    exit 1
fi

echo -e "${GREEN}✓${NC} Inventory: $INVENTORY"
echo -e "${GREEN}✓${NC} Vault: $VAULT_FILE"
echo ""

# Run deployment
echo -e "${BLUE}Starting deployment...${NC}"
echo ""

cd "$ANSIBLE_DIR"

# Limit to current hostname only
CURRENT_HOST=$(hostname)

# Run deployment as current user
# Playbook will use sudo for docker commands if user lacks docker group access
ansible-playbook \
    -i "$INVENTORY" \
    playbooks/deploy-update.yml \
    --connection local \
    --limit "$CURRENT_HOST" \
    --vault-password-file "$VAULT_FILE"
RESULT=$?

echo ""
if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Deployment Complete${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Deployment Failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit $RESULT
fi
