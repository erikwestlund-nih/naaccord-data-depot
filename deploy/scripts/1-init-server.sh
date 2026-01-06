#!/bin/bash
#
# NA-ACCORD Server Initialization Script
#
# This script bootstraps a fresh RHEL/Rocky Linux server for NA-ACCORD deployment.
# Run this ONCE on each new server before using Ansible automation.
#
# HOW TO GET THIS SCRIPT ON THE SERVER:
#   Option 1: Copy from local machine:
#     scp deploy/scripts/1-init-server.sh user@server:~/
#
#   Option 2: Download directly on server:
#     curl -O https://raw.githubusercontent.com/JHBiostatCenter/naaccord-data-depot/deploy/deploy/scripts/1-init-server.sh
#     chmod +x 1-init-server.sh
#
#   Option 3: Manually create and paste contents on server:
#     nano ~/1-init-server.sh
#     # Paste this script
#     chmod +x ~/1-init-server.sh
#
# LOCATION: Put this script in your home directory on the target server (~/)
#
# Usage:
#   ./1-init-server.sh
#
# What it does:
#   1. Prompts for environment (staging/production) and server role (web/services)
#   2. Installs Ansible and dependencies
#   3. Sets up GitHub deploy key for repository access
#   4. Clones NA-ACCORD repository to /opt/naaccord
#   5. Prepares server for Ansible playbook execution
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Constants
REPO_URL="git@github.com:JHBiostatCenter/naaccord-data-depot.git"
REPO_BRANCH="main"
INSTALL_DIR="/opt/naaccord/depot"
ENV_MARKER_FILE="/etc/naaccord/environment"
ROLE_MARKER_FILE="/etc/naaccord/server-role"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}NA-ACCORD Server Initialization${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if server is already configured
if [ -f "$ENV_MARKER_FILE" ] && [ -f "$ROLE_MARKER_FILE" ]; then
    EXISTING_ENV=$(sudo cat "$ENV_MARKER_FILE" 2>/dev/null | tr -d '[:space:]')
    EXISTING_ROLE=$(sudo cat "$ROLE_MARKER_FILE" 2>/dev/null | tr -d '[:space:]')

    echo -e "${YELLOW}Server already configured:${NC}"
    echo "  Environment: $EXISTING_ENV"
    echo "  Server role: $EXISTING_ROLE"
    echo ""
    read -p "Keep existing configuration? (Y/n): " keep_config

    if [[ ! $keep_config =~ ^[Nn]$ ]]; then
        ENVIRONMENT="$EXISTING_ENV"
        SERVER_TYPE="$EXISTING_ROLE"
        echo -e "${GREEN}Using existing configuration${NC}"
        echo ""
    else
        echo -e "${YELLOW}Reconfiguring server...${NC}"
        echo ""
    fi
fi

# If not keeping existing config or no existing config, prompt for configuration
if [ -z "$ENVIRONMENT" ] || [ -z "$SERVER_TYPE" ]; then
    echo -e "${YELLOW}Server Configuration${NC}"
    echo ""

    # Ask environment first
    read -p "Is this (s)taging or (p)roduction? [s]: " env_choice
    if [[ "$env_choice" =~ ^[Pp]$ ]]; then
        ENVIRONMENT="production"
    else
        ENVIRONMENT="staging"
    fi

    # Ask server role second
    read -p "Is this a (w)eb or (s)ervices server? [s]: " server_choice
    if [[ "$server_choice" =~ ^[Ww]$ ]]; then
        SERVER_TYPE="web"
    else
        SERVER_TYPE="services"
    fi
    echo ""

    # Save marker files IMMEDIATELY
    echo -e "${YELLOW}Saving server configuration...${NC}"
    sudo mkdir -p /etc/naaccord
    echo "$ENVIRONMENT" | sudo tee /etc/naaccord/environment > /dev/null
    echo "$SERVER_TYPE" | sudo tee /etc/naaccord/server-role > /dev/null
    sudo chmod 644 /etc/naaccord/environment
    sudo chmod 644 /etc/naaccord/server-role
    echo -e "${GREEN}✓${NC} Environment: $ENVIRONMENT"
    echo -e "${GREEN}✓${NC} Server role: $SERVER_TYPE"
    echo ""
fi

echo "Configuration:"
echo "  Environment: ${ENVIRONMENT}"
echo "  Server Type: ${SERVER_TYPE}"
echo "Repository: ${REPO_URL}"
echo "Branch: ${REPO_BRANCH}"
echo "Install directory: ${INSTALL_DIR}"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}ERROR: Do not run this script as root${NC}"
   echo "Run as your normal user account with sudo access"
   exit 1
fi

# Detect OS
if [ -f /etc/redhat-release ]; then
    OS_VERSION=$(cat /etc/redhat-release)
    echo -e "${GREEN}✓${NC} Detected: ${OS_VERSION}"
else
    echo -e "${RED}ERROR: This script requires RHEL or Rocky Linux${NC}"
    exit 1
fi

# Check for sudo access
if ! sudo -n true 2>/dev/null; then
    echo -e "${YELLOW}This script requires sudo access${NC}"
    echo "You may be prompted for your password"
fi

# Step 1: Install EPEL repository
echo ""
echo -e "${YELLOW}Step 1: Installing EPEL repository...${NC}"
if ! rpm -q epel-release &>/dev/null; then
    sudo dnf install -y epel-release
    echo -e "${GREEN}✓${NC} EPEL repository installed"
else
    echo -e "${GREEN}✓${NC} EPEL repository already installed"
fi

# Step 2: Install Ansible and dependencies
echo ""
echo -e "${YELLOW}Step 2: Installing Ansible and dependencies...${NC}"
if ! command -v ansible &>/dev/null; then
    sudo dnf install -y ansible git
    echo -e "${GREEN}✓${NC} Ansible installed: $(ansible --version | head -n1)"
else
    echo -e "${GREEN}✓${NC} Ansible already installed: $(ansible --version | head -n1)"
fi

# Step 3: Set up GitHub deploy key
echo ""
echo -e "${YELLOW}Step 3: Setting up GitHub deploy key...${NC}"

# Create .ssh directory if it doesn't exist
mkdir -p ~/.ssh
chmod 700 ~/.ssh

DEPLOY_KEY_PATH="$HOME/.ssh/naaccord_deploy"

if [ -f "$DEPLOY_KEY_PATH" ]; then
    echo -e "${YELLOW}Deploy key already exists at $DEPLOY_KEY_PATH${NC}"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing deploy key"
    else
        rm -f "$DEPLOY_KEY_PATH" "${DEPLOY_KEY_PATH}.pub"
    fi
fi

if [ ! -f "$DEPLOY_KEY_PATH" ]; then
    echo ""
    echo -e "${GREEN}Please paste your GitHub deploy PRIVATE key below.${NC}"
    echo "Paste the entire key including:"
    echo "  -----BEGIN OPENSSH PRIVATE KEY-----"
    echo "  [key content]"
    echo "  -----END OPENSSH PRIVATE KEY-----"
    echo ""
    echo "Press Ctrl+D when done:"
    echo ""

    cat > "$DEPLOY_KEY_PATH"
    chmod 600 "$DEPLOY_KEY_PATH"

    echo ""
    echo -e "${GREEN}✓${NC} Deploy key saved to $DEPLOY_KEY_PATH"

    # Get public key
    echo ""
    echo -e "${GREEN}Now paste the PUBLIC key:${NC}"
    echo "Should start with: ssh-ed25519 or ssh-rsa"
    echo ""
    read -p "Public key: " PUBLIC_KEY
    echo "$PUBLIC_KEY" > "${DEPLOY_KEY_PATH}.pub"
    chmod 644 "${DEPLOY_KEY_PATH}.pub"

    echo -e "${GREEN}✓${NC} Public key saved to ${DEPLOY_KEY_PATH}.pub"
fi

# Configure SSH for GitHub
echo ""
echo -e "${YELLOW}Step 4: Configuring SSH for GitHub...${NC}"

SSH_CONFIG="$HOME/.ssh/config"
GITHUB_CONFIG="
# NA-ACCORD GitHub Deploy Key
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/naaccord_deploy
    IdentitiesOnly yes
"

if ! grep -q "naaccord_deploy" "$SSH_CONFIG" 2>/dev/null; then
    echo "$GITHUB_CONFIG" >> "$SSH_CONFIG"
    chmod 600 "$SSH_CONFIG"
    echo -e "${GREEN}✓${NC} SSH config updated"
else
    echo -e "${GREEN}✓${NC} SSH config already contains GitHub settings"
fi

# Test SSH connection to GitHub
echo ""
echo -e "${YELLOW}Step 5: Testing GitHub connection...${NC}"
if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo -e "${GREEN}✓${NC} GitHub authentication successful"
else
    echo -e "${RED}✗${NC} GitHub authentication failed"
    echo "Please verify your deploy key is added to GitHub:"
    echo "  https://github.com/JHBiostatCenter/naaccord-data-depot/settings/keys"
    exit 1
fi

# Step 6: Create application directory
echo ""
echo -e "${YELLOW}Step 6: Creating application directory...${NC}"
if [ ! -d "/opt/naaccord" ]; then
    sudo mkdir -p /opt/naaccord
    echo -e "${GREEN}✓${NC} Created /opt/naaccord"
fi

# Always ensure correct ownership (use primary group, not username as group)
sudo chown -R $(whoami):$(id -gn) /opt/naaccord
echo -e "${GREEN}✓${NC} Ownership set for /opt/naaccord"

# Step 7: Clone repository
echo ""
echo -e "${YELLOW}Step 7: Cloning NA-ACCORD repository...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}Repository already cloned${NC}"
    read -p "Pull latest changes? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        cd "$INSTALL_DIR"
        git pull origin "$REPO_BRANCH"
        echo -e "${GREEN}✓${NC} Repository updated"
    fi
else
    git clone -b "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    echo -e "${GREEN}✓${NC} Repository cloned to $INSTALL_DIR"
fi

# Verify directory structure
cd "$INSTALL_DIR"
if [ -d "deploy/ansible" ] && [ -d "depot" ]; then
    echo -e "${GREEN}✓${NC} Repository structure verified"
else
    echo -e "${RED}✗${NC} Repository structure unexpected"
    echo "Expected to find deploy/ansible/ and depot/ directories"
    exit 1
fi

# Step 8: Create vault password file
echo ""
echo -e "${YELLOW}Step 8: Creating vault password file...${NC}"
VAULT_PASSWORD_FILE="$HOME/.naaccord_vault_${ENVIRONMENT}"

read -sp "Enter vault password: " VAULT_PASS
echo ""

if [ -z "$VAULT_PASS" ]; then
    echo -e "${RED}ERROR: Vault password cannot be empty${NC}"
    exit 1
fi

echo "$VAULT_PASS" > "$VAULT_PASSWORD_FILE"
chmod 600 "$VAULT_PASSWORD_FILE"
unset VAULT_PASS

echo -e "${GREEN}✓${NC} Vault password file created: $VAULT_PASSWORD_FILE"

# Verify vault password works
echo ""
echo -e "${YELLOW}Verifying vault password...${NC}"
if ansible-vault view "$INSTALL_DIR/deploy/ansible/inventories/${ENVIRONMENT}/group_vars/all/vault.yml" --vault-password-file "$VAULT_PASSWORD_FILE" &>/dev/null; then
    echo -e "${GREEN}✓${NC} Vault password verified"
else
    echo -e "${RED}✗${NC} Vault password incorrect"
    echo "The password does not decrypt the vault file"
    rm -f "$VAULT_PASSWORD_FILE"
    exit 1
fi

# Success summary
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Initialization Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Repository location: $INSTALL_DIR"
echo "Branch: $(git branch --show-current)"
echo ""
echo -e "${YELLOW}Next: Run deployment script${NC}"
echo ""
echo "   $INSTALL_DIR/deploy/scripts/2-deploy.sh"
echo ""
echo -e "${GREEN}The script will automatically detect:${NC}"
echo "   • Environment: $ENVIRONMENT (from $ENV_MARKER_FILE)"
echo "   • Server role: $SERVER_TYPE (from $ROLE_MARKER_FILE)"
echo ""
echo -e "${YELLOW}NOTE:${NC} If you made a mistake, you can re-run:"
echo "   $INSTALL_DIR/deploy/scripts/1-init-server.sh"
echo ""
echo -e "${GREEN}Server is ready for deployment!${NC}"
