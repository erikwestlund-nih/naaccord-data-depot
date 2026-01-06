#!/bin/bash
#
# NA-ACCORD Vault Generator
#
# This script generates a complete Ansible vault with fresh secrets.
# Run this on your LOCAL MACHINE (not on the server).
#
# Usage:
#   ./generate-vault.sh [staging|production]
#
# Requirements:
#   - Docker (for WireGuard key generation)
#   - ansible-vault command
#   - openssl command
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Arguments
if [ -z "$1" ]; then
    echo -e "${RED}ERROR: Environment argument required${NC}"
    echo ""
    echo "Usage: $0 [staging|production]"
    echo ""
    echo "Examples:"
    echo "  $0 staging      # Generate staging vault"
    echo "  $0 production   # Generate production vault"
    exit 1
fi

ENVIRONMENT="$1"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo -e "${RED}ERROR: Invalid environment: ${ENVIRONMENT}${NC}"
    echo ""
    echo "Valid environments: staging, production"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VAULT_FILE="${REPO_DIR}/deploy/ansible/inventories/${ENVIRONMENT}/group_vars/all/vault.yml"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}NA-ACCORD Vault Generator${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Show warning if vault file exists
if [ -f "${VAULT_FILE}" ]; then
    echo -e "${YELLOW}⚠️  WARNING: Existing vault file will be OVERWRITTEN${NC}"
    echo ""
    echo "Environment:     ${ENVIRONMENT}"
    echo "Existing vault:  ${VAULT_FILE}"
    echo ""
    read -p "Are you sure you want to overwrite the ${ENVIRONMENT} vault? (yes/NO): " -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "Aborted - vault file not modified"
        exit 0
    fi
    echo ""
else
    echo "Environment: ${ENVIRONMENT}"
    echo "Vault file: ${VAULT_FILE} (new)"
    echo ""
fi

# Check requirements
echo -e "${YELLOW}Checking requirements...${NC}"

if ! command -v docker &>/dev/null; then
    echo -e "${RED}ERROR: Docker not found${NC}"
    echo "Docker is required for WireGuard key generation"
    exit 1
fi

if ! command -v ansible-vault &>/dev/null; then
    echo -e "${RED}ERROR: ansible-vault not found${NC}"
    echo "Please install Ansible: pip install ansible"
    exit 1
fi

if ! command -v openssl &>/dev/null; then
    echo -e "${RED}ERROR: openssl not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} All requirements met"
echo ""

# Function to generate random password
generate_password() {
    openssl rand -base64 32 | tr -d "=+/\n" | cut -c1-32
}

# Function to generate long secret
generate_secret() {
    openssl rand -base64 64 | tr -d "=+/\n" | cut -c1-64
}

# Function to generate hex key
generate_hex() {
    openssl rand -hex 32
}

# Function to prompt for value with default
prompt_value() {
    local prompt="$1"
    local default="$2"
    local value=""

    if [ -n "$default" ]; then
        read -p "${prompt} [default: ${default}]: " value
    else
        read -p "${prompt}: " value
    fi

    if [ -z "$value" ]; then
        printf "%s" "$default"
    else
        printf "%s" "$value"
    fi
}

# Function to prompt for password (no echo)
prompt_password() {
    local prompt="$1"
    local default="$2"
    local value=""

    if [ -n "$default" ]; then
        read -sp "${prompt} [press Enter for generated]: " value
        echo "" >&2
    else
        read -sp "${prompt}: " value
        echo "" >&2
    fi

    if [ -z "$value" ]; then
        printf "%s" "$default"
    else
        printf "%s" "$value"
    fi
}

echo -e "${BLUE}Step 1: Generating Cryptographic Secrets${NC}"
echo "================================================"
echo ""

echo -e "${YELLOW}Generating database passwords...${NC}"
DB_ROOT_PASSWORD=$(generate_password)
DB_APP_PASSWORD=$(generate_password)
DB_REPORT_PASSWORD=$(generate_password)
DB_BACKUP_PASSWORD=$(generate_password)
DB_ADMIN_PASSWORD=$(generate_password)
DB_ENCRYPTION_KEY=$(generate_hex)
echo -e "${GREEN}✓${NC} Database secrets generated"

echo -e "${YELLOW}Generating Django secrets...${NC}"
DJANGO_SECRET_KEY=$(generate_secret)
INTERNAL_API_KEY=$(generate_secret)
echo -e "${GREEN}✓${NC} Django secrets generated"

echo -e "${YELLOW}Generating Redis password...${NC}"
REDIS_PASSWORD=$(generate_password)
echo -e "${GREEN}✓${NC} Redis password generated"

echo -e "${YELLOW}Generating monitoring passwords...${NC}"
FLOWER_PASSWORD=$(generate_password)
GRAFANA_ADMIN_PASSWORD=$(generate_password)
echo -e "${GREEN}✓${NC} Monitoring passwords generated"

echo ""
echo -e "${BLUE}Step 2: Generating WireGuard Keys${NC}"
echo "================================================"
echo ""

echo -e "${YELLOW}Generating WireGuard tunnel keys...${NC}"
WG_OUTPUT=$(docker run --rm --entrypoint sh ghcr.io/jhbiostatcenter/naaccord/wireguard:latest -c '
  services_priv=$(wg genkey)
  services_pub=$(echo $services_priv | wg pubkey)
  web_priv=$(wg genkey)
  web_pub=$(echo $web_priv | wg pubkey)
  preshared=$(wg genpsk)

  echo "SERVICES_PRIVATE=$services_priv"
  echo "SERVICES_PUBLIC=$services_pub"
  echo "WEB_PRIVATE=$web_priv"
  echo "WEB_PUBLIC=$web_pub"
  echo "PRESHARED=$preshared"
' 2>/dev/null)

WG_SERVICES_PRIVATE=$(echo "$WG_OUTPUT" | grep SERVICES_PRIVATE | cut -d= -f2-)
WG_SERVICES_PUBLIC=$(echo "$WG_OUTPUT" | grep SERVICES_PUBLIC | cut -d= -f2-)
WG_WEB_PRIVATE=$(echo "$WG_OUTPUT" | grep WEB_PRIVATE | cut -d= -f2-)
WG_WEB_PUBLIC=$(echo "$WG_OUTPUT" | grep WEB_PUBLIC | cut -d= -f2-)
WG_PRESHARED=$(echo "$WG_OUTPUT" | grep PRESHARED | cut -d= -f2-)

echo -e "${GREEN}✓${NC} WireGuard keys generated"

echo ""
echo -e "${BLUE}Step 3: External Credentials${NC}"
echo "================================================"
echo ""
echo "Press Enter to skip or provide existing credentials"
echo ""

# GitHub
echo -e "${YELLOW}GitHub Container Registry (for pulling private images):${NC}"
GHCR_USERNAME=$(prompt_value "GHCR username" "erikwestlund")
GHCR_TOKEN=$(prompt_value "GHCR token (ghp_...)" "")

# NAS
echo ""
echo -e "${YELLOW}NAS Storage Configuration:${NC}"
if [ "$ENVIRONMENT" = "production" ]; then
    NAS_DOMAIN=$(prompt_value "NAS domain" "win.ad.jhu.edu")
    NAS_HOST=$(prompt_value "NAS host" "cloud.nas.jh.edu")
else
    NAS_DOMAIN=""
    NAS_HOST=$(prompt_value "NAS host" "192.168.50.1")
fi
NAS_USERNAME=$(prompt_value "NAS username" "naaccord")
NAS_PASSWORD=$(prompt_password "NAS password" "$(generate_password)")

# SSL Certificate and Key (production only)
if [ "$ENVIRONMENT" = "production" ]; then
    echo ""
    echo -e "${YELLOW}SSL Certificate (from JHU IT):${NC}"
    echo "NOTE: CSR is not secret, but stored here for convenience"
    echo ""
    echo "Paste CSR content (-----BEGIN CERTIFICATE REQUEST----- ... -----END CERTIFICATE REQUEST-----)"
    echo "Press Ctrl+D when done:"
    SSL_CSR=$(cat)
    echo ""

    echo -e "${YELLOW}SSL Private Key (from JHU IT):${NC}"
    echo "NOTE: Only the .key file is secret - commit the .crt file directly to git"
    echo ""
    echo "Paste SSL private key content (-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----)"
    echo "Press Ctrl+D when done:"
    SSL_KEY=$(cat)
    echo ""

    # SAML SP Certificate and Key (production - from JHU)
    echo -e "${YELLOW}SAML SP Certificate (public key for JHU IDP):${NC}"
    echo "NOTE: Public certificate - also registered with JHU IMI"
    echo ""
    echo "Paste SAML SP certificate (-----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----)"
    echo "Press Ctrl+D when done:"
    SAML_SP_CERT=$(cat)
    echo ""

    echo -e "${YELLOW}SAML SP Private Key (keep secret):${NC}"
    echo "NOTE: Private key for SAML signing"
    echo ""
    echo "Paste SAML SP private key (-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----)"
    echo "Press Ctrl+D when done:"
    SAML_SP_KEY=$(cat)
    echo ""
else
    # Staging environment - no SSL but still needs SAML certs for mock-idp
    SSL_CSR=""
    SSL_KEY=""

    echo ""
    echo -e "${YELLOW}SAML SP Certificate (for mock-idp):${NC}"
    echo "NOTE: Self-signed certificate from deploy/containers/mock-idp/cert/sp-staging.crt"
    echo "      If you haven't generated it yet, run: cd deploy/containers/mock-idp && ./generate-certs.sh"
    echo ""
    echo "Paste SAML SP certificate (-----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----)"
    echo "Press Ctrl+D when done:"
    SAML_SP_CERT=$(cat)
    echo ""

    echo -e "${YELLOW}SAML SP Private Key (for mock-idp):${NC}"
    echo "NOTE: Private key from deploy/containers/mock-idp/cert/sp-staging.key"
    echo ""
    echo "Paste SAML SP private key (-----BEGIN PRIVATE KEY----- ... -----END PRIVATE KEY-----)"
    echo "Press Ctrl+D when done:"
    SAML_SP_KEY=$(cat)
    echo ""

    echo -e "${YELLOW}Mock IDP Certificate (for Django to verify SAML responses):${NC}"
    echo "NOTE: Public certificate from deploy/containers/mock-idp/cert/idp.crt"
    echo "      This is the mock-idp's signing certificate that Django uses to verify SAML assertions"
    echo ""
    echo "Paste Mock IDP certificate (-----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----)"
    echo "Press Ctrl+D when done:"
    MOCK_IDP_CERT=$(cat)
    echo ""
fi

echo ""
echo -e "${BLUE}Step 4: Review Generated Secrets${NC}"
echo "================================================"
echo ""
echo "The following secrets have been generated:"
echo ""
echo "Database:"
echo "  Root password:       ${DB_ROOT_PASSWORD:0:2}...${DB_ROOT_PASSWORD: -2}"
echo "  App password:        ${DB_APP_PASSWORD:0:2}...${DB_APP_PASSWORD: -2}"
echo "  Report password:     ${DB_REPORT_PASSWORD:0:2}...${DB_REPORT_PASSWORD: -2}"
echo "  Backup password:     ${DB_BACKUP_PASSWORD:0:2}...${DB_BACKUP_PASSWORD: -2}"
echo "  Admin password:      ${DB_ADMIN_PASSWORD:0:2}...${DB_ADMIN_PASSWORD: -2}"
echo "  Encryption key:      ${DB_ENCRYPTION_KEY:0:2}...${DB_ENCRYPTION_KEY: -2}"
echo ""
echo "Django:"
echo "  Secret key:          ${DJANGO_SECRET_KEY:0:2}...${DJANGO_SECRET_KEY: -2}"
echo "  Internal API key:    ${INTERNAL_API_KEY:0:2}...${INTERNAL_API_KEY: -2}"
echo ""
echo "Redis:"
echo "  Password:            ${REDIS_PASSWORD:0:2}...${REDIS_PASSWORD: -2}"
echo ""
echo "WireGuard:"
echo "  Services public:     ${WG_SERVICES_PUBLIC:0:2}...${WG_SERVICES_PUBLIC: -2}"
echo "  Web public:          ${WG_WEB_PUBLIC:0:2}...${WG_WEB_PUBLIC: -2}"
echo ""
echo "Monitoring:"
echo "  Flower password:     ${FLOWER_PASSWORD:0:2}...${FLOWER_PASSWORD: -2}"
echo "  Grafana password:    ${GRAFANA_ADMIN_PASSWORD:0:2}...${GRAFANA_ADMIN_PASSWORD: -2}"
echo ""
echo "NAS:"
if [ -n "$NAS_DOMAIN" ]; then
    echo "  Domain:              ${NAS_DOMAIN}"
fi
echo "  Host:                ${NAS_HOST}"
echo "  Username:            ${NAS_USERNAME}"
echo "  Password:            ${NAS_PASSWORD:0:2}...${NAS_PASSWORD: -2}"
echo ""

if [ -n "$SSL_KEY" ]; then
    echo "SSL:"
    echo "  CSR:                 ${#SSL_CSR} characters"
    echo "  Private key:         ${#SSL_KEY} characters"
    echo ""
fi

if [ -n "$SAML_SP_CERT" ]; then
    echo "SAML SP:"
    echo "  Certificate:         ${#SAML_SP_CERT} characters"
    echo "  Private key:         ${#SAML_SP_KEY} characters"
    echo ""
fi

if [ -n "$MOCK_IDP_CERT" ]; then
    echo "Mock IDP:"
    echo "  Certificate:         ${#MOCK_IDP_CERT} characters"
    echo ""
fi

read -p "Continue with these values? (Y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "Aborted"
    exit 0
fi

echo ""
echo -e "${BLUE}Step 5: Creating Vault File${NC}"
echo "================================================"
echo ""

# Create vault directory if needed
mkdir -p "$(dirname "${VAULT_FILE}")"

# Create plaintext vault
TEMP_VAULT=$(mktemp)
cat > "$TEMP_VAULT" << EOF
---
# NA-ACCORD Ansible Vault - ${ENVIRONMENT}
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Database passwords
vault_db_root_password: "${DB_ROOT_PASSWORD}"
vault_db_app_password: "${DB_APP_PASSWORD}"
vault_db_report_password: "${DB_REPORT_PASSWORD}"
vault_db_backup_password: "${DB_BACKUP_PASSWORD}"
vault_db_admin_password: "${DB_ADMIN_PASSWORD}"
vault_db_encryption_key: "${DB_ENCRYPTION_KEY}"

# Django secrets
vault_django_secret_key: "${DJANGO_SECRET_KEY}"
vault_internal_api_key: "${INTERNAL_API_KEY}"

# Redis password
vault_redis_password: "${REDIS_PASSWORD}"

# WireGuard keys (PHI tunnel encryption)
vault_wg_services_private_key: "${WG_SERVICES_PRIVATE}"
vault_wg_services_public_key: "${WG_SERVICES_PUBLIC}"
vault_wg_web_private_key: "${WG_WEB_PRIVATE}"
vault_wg_web_public_key: "${WG_WEB_PUBLIC}"
vault_wg_preshared_key: "${WG_PRESHARED}"

# Monitoring passwords
vault_flower_password: "${FLOWER_PASSWORD}"
vault_grafana_admin_password: "${GRAFANA_ADMIN_PASSWORD}"

# MariaDB passwords (mapped from db_ for compatibility)
vault_mariadb_root_password: "{{ vault_db_root_password }}"
vault_mariadb_app_password: "{{ vault_db_app_password }}"
vault_mariadb_report_password: "{{ vault_db_report_password }}"
vault_mariadb_backup_password: "{{ vault_db_backup_password }}"
vault_mariadb_admin_password: "{{ vault_db_admin_password }}"
vault_mariadb_encryption_key: "{{ vault_db_encryption_key }}"

# GitHub token for accessing private repositories
vault_ghcr_username: "${GHCR_USERNAME}"
vault_ghcr_token: "${GHCR_TOKEN}"

# NAS credentials
vault_nas_domain: "${NAS_DOMAIN}"
vault_nas_host: "${NAS_HOST}"
vault_nas_username: "${NAS_USERNAME}"
vault_nas_password: "${NAS_PASSWORD}"

# SSL certificate request (not secret, stored for convenience)
vault_ssl_csr: |
$(echo "${SSL_CSR}" | sed 's/^/  /')

# SSL private key (certificate is public, committed to git)
vault_ssl_private_key: |
$(echo "${SSL_KEY}" | sed 's/^/  /')

# SAML SP certificate (public, registered with JHU IMI or self-signed for staging)
vault_saml_sp_cert: |
$(echo "${SAML_SP_CERT}" | sed 's/^/  /')

# SAML SP private key (secret, for signing SAML requests)
vault_saml_sp_key: |
$(echo "${SAML_SP_KEY}" | sed 's/^/  /')

# Mock IDP certificate (staging only - for Django to verify SAML responses)
vault_mock_idp_cert: |
$(echo "${MOCK_IDP_CERT}" | sed 's/^/  /')
EOF

echo -e "${YELLOW}Encrypting vault...${NC}"

# Prompt for vault password
echo ""
echo "Choose a vault password (used to decrypt this file with ansible-vault)"
VAULT_PASSWORD=$(prompt_password "Vault password")

if [ -z "$VAULT_PASSWORD" ]; then
    echo -e "${RED}ERROR: Vault password cannot be empty${NC}"
    rm "$TEMP_VAULT"
    exit 1
fi

# Encrypt vault
echo "$VAULT_PASSWORD" | ansible-vault encrypt "$TEMP_VAULT" --vault-password-file /dev/stdin --output "${VAULT_FILE}"
rm "$TEMP_VAULT"

echo -e "${GREEN}✓${NC} Vault encrypted and saved to: ${VAULT_FILE}"
echo ""

echo -e "${BLUE}Step 6: Summary${NC}"
echo "================================================"
echo ""
echo -e "${GREEN}Vault generation complete!${NC}"
echo ""
echo "Vault location: ${VAULT_FILE}"
echo "Vault password: (you entered this - save it securely!)"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Save vault password to password manager"
echo ""
echo "2. Commit vault to repository:"
echo "   cd ${REPO_DIR}"
echo "   git add deploy/ansible/inventories/${ENVIRONMENT}/group_vars/all/vault.yml"
echo "   git commit -m 'chore: regenerate ${ENVIRONMENT} vault secrets'"
echo "   git push origin deploy"
echo ""
echo "3. On the server, create vault password file:"
echo "   echo 'your-vault-password' > ~/.naaccord_vault_${ENVIRONMENT}"
echo "   chmod 600 ~/.naaccord_vault_${ENVIRONMENT}"
echo ""
echo "4. Run Ansible playbook on server"
echo ""
echo -e "${GREEN}Done!${NC}"
