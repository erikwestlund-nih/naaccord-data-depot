#!/bin/bash
#
# Generate self-signed certificates for mock-idp
# Run this once during initial setup
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/cert"

mkdir -p "${CERT_DIR}"

echo "Generating mock-idp certificates..."

# Generate IDP certificate (self-signed)
if [ ! -f "${CERT_DIR}/idp.key" ]; then
    echo "  - Generating IDP private key and certificate..."
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/idp.key" \
        -out "${CERT_DIR}/idp.crt" \
        -days 3650 \
        -subj "/C=US/ST=Maryland/L=Baltimore/O=NA-ACCORD Mock IDP/CN=192.168.50.10"
    echo "    ✓ IDP certificate generated"
else
    echo "  - IDP certificate already exists"
fi

# Generate SP certificate (for NA-ACCORD staging)
if [ ! -f "${CERT_DIR}/sp-staging.key" ]; then
    echo "  - Generating SP private key and certificate..."
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${CERT_DIR}/sp-staging.key" \
        -out "${CERT_DIR}/sp-staging.crt" \
        -days 3650 \
        -subj "/C=US/ST=Maryland/L=Baltimore/O=NA-ACCORD Staging/OU=Data Depot/CN=naaccord.pequod.sh"
    echo "    ✓ SP certificate generated"
else
    echo "  - SP certificate already exists"
fi

echo ""
echo "Certificates generated successfully!"
echo ""
echo "Certificate locations:"
echo "  IDP: ${CERT_DIR}/idp.{key,crt}"
echo "  SP:  ${CERT_DIR}/sp-staging.{key,crt}"
echo ""
echo "Next steps:"
echo "1. Add SP certificates to staging vault:"
echo "   - vault_saml_sp_cert: contents of sp-staging.crt"
echo "   - vault_saml_sp_key: contents of sp-staging.key"
echo ""
echo "2. Update docker-compose to mount mock-idp configuration"
echo ""
