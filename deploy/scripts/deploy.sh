#!/bin/bash
set -e

# NA-ACCORD Application Deployment Script
# Usage: ./deploy.sh [staging|production] [branch]
#
# Examples:
#   ./deploy.sh staging deploy    # Deploy 'deploy' branch to staging
#   ./deploy.sh production main   # Deploy 'main' branch to production
#
# NOTE: This script is DEPRECATED. Use deploy-update.sh instead.
#       This wrapper exists for backwards compatibility with old aliases.

ENVIRONMENT="${1:-staging}"
BRANCH="${2:-deploy}"

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}NA-ACCORD Application Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  This script (deploy.sh) is deprecated${NC}"
echo -e "${YELLOW}   Use deploy-update.sh instead (no arguments needed)${NC}"
echo ""
echo -e "${GREEN}Forwarding to deploy-update.sh...${NC}"
echo ""

# Execute the new script
exec /opt/naaccord/depot/deploy/scripts/deploy-update.sh
