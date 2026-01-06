#!/bin/bash
#
# Diagnose vault file issues
# Run this on the server where ansible is failing
#

set -e

ENVIRONMENT="${1:-staging}"
VAULT_FILE="/opt/naaccord/depot/deploy/ansible/inventories/${ENVIRONMENT}/group_vars/all/vault.yml"

echo "=========================================="
echo "NA-ACCORD Vault Diagnostics"
echo "=========================================="
echo ""

# Check if vault file exists
if [ ! -f "${VAULT_FILE}" ]; then
    echo "ERROR: Vault file not found: ${VAULT_FILE}"
    exit 1
fi

echo "Vault file: ${VAULT_FILE}"
echo ""

# Check if it's encrypted
echo "Checking if vault is encrypted..."
if head -1 "${VAULT_FILE}" | grep -q "ANSIBLE_VAULT"; then
    echo "✓ Vault is encrypted"
else
    echo "✗ Vault is NOT encrypted (should start with \$ANSIBLE_VAULT)"
    exit 1
fi

echo ""
echo "File details:"
ls -lh "${VAULT_FILE}"

echo ""
echo "File size:"
wc -c "${VAULT_FILE}"

echo ""
echo "First 10 lines:"
head -10 "${VAULT_FILE}"

echo ""
echo "Last 10 lines:"
tail -10 "${VAULT_FILE}"

echo ""
echo "Checking for line 60 (where error occurred):"
sed -n '55,65p' "${VAULT_FILE}"

echo ""
echo "=========================================="
echo "Attempting to decrypt vault..."
echo "=========================================="

VAULT_PASSWORD_FILE="${HOME}/.naaccord_vault_${ENVIRONMENT}"

if [ -f "${VAULT_PASSWORD_FILE}" ]; then
    echo "Using vault password from: ${VAULT_PASSWORD_FILE}"

    # Try to decrypt and show structure
    if ansible-vault view "${VAULT_FILE}" --vault-password-file "${VAULT_PASSWORD_FILE}" > /tmp/vault_decrypted.yml 2>&1; then
        echo "✓ Vault decrypted successfully!"
        echo ""
        echo "Checking YAML syntax of decrypted content..."

        if python3 -c "import yaml; yaml.safe_load(open('/tmp/vault_decrypted.yml'))" 2>&1; then
            echo "✓ YAML syntax is valid"
            echo ""
            echo "Vault structure:"
            head -50 /tmp/vault_decrypted.yml
        else
            echo "✗ YAML syntax error in decrypted content"
            echo ""
            echo "Problematic area around line 60:"
            sed -n '55,65p' /tmp/vault_decrypted.yml
        fi

        rm -f /tmp/vault_decrypted.yml
    else
        echo "✗ Failed to decrypt vault"
        echo "Error output:"
        ansible-vault view "${VAULT_FILE}" --vault-password-file "${VAULT_PASSWORD_FILE}" 2>&1 || true
    fi
else
    echo "ERROR: Vault password file not found: ${VAULT_PASSWORD_FILE}"
    echo ""
    echo "Create it with:"
    echo "  echo 'your-vault-password' > ${VAULT_PASSWORD_FILE}"
    echo "  chmod 600 ${VAULT_PASSWORD_FILE}"
fi
