#!/bin/bash
# Generate certificates for mTLS communication between web and services servers

set -e

# Configuration
CERT_DIR="./deploy/containers/nginx/certs"
VALIDITY_DAYS=3650
COUNTRY="US"
STATE="YourState"
CITY="YourCity"
ORGANIZATION="NA-ACCORD"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}mTLS Certificate Generation${NC}"
echo -e "${BLUE}========================================${NC}"

# Create certificate directory
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

# Function to generate a key and certificate
generate_cert() {
    local name=$1
    local cn=$2

    echo -e "\n${YELLOW}Generating $name certificate...${NC}"

    # Generate private key
    openssl genrsa -out ${name}.key 2048

    # Generate certificate request
    openssl req -new -key ${name}.key -out ${name}.csr -subj \
        "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORGANIZATION/CN=$cn"

    # Sign certificate with CA
    openssl x509 -req -in ${name}.csr -CA ca.crt -CAkey ca.key \
        -CAcreateserial -out ${name}.crt -days $VALIDITY_DAYS \
        -sha256 -extfile <(printf "subjectAltName=DNS:$cn,DNS:localhost,IP:127.0.0.1")

    # Verify certificate
    openssl verify -CAfile ca.crt ${name}.crt

    echo -e "${GREEN}✓ $name certificate generated${NC}"
}

# Generate CA if it doesn't exist
if [ ! -f ca.key ]; then
    echo -e "${YELLOW}Generating Certificate Authority...${NC}"

    # Generate CA private key
    openssl genrsa -out ca.key 4096

    # Generate CA certificate
    openssl req -new -x509 -days $VALIDITY_DAYS -key ca.key -out ca.crt -subj \
        "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORGANIZATION/CN=NA-ACCORD-CA"

    echo -e "${GREEN}✓ CA certificate generated${NC}"
else
    echo -e "${GREEN}✓ CA certificate exists${NC}"
fi

# Generate server certificates
echo -e "\n${YELLOW}Select certificate generation mode:${NC}"
echo "1) Development (localhost)"
echo "2) Test Environment (192.168.50.x)"
echo "3) Production (10.150.96.x)"
echo "4) Custom"

read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        # Development certificates
        generate_cert "server" "localhost"
        generate_cert "client" "localhost"
        ;;
    2)
        # Test environment
        generate_cert "web-server" "192.168.50.10"
        generate_cert "services-server" "192.168.50.11"
        generate_cert "client" "naaccord-test.local"
        ;;
    3)
        # Production environment
        generate_cert "web-server" "10.150.96.6"
        generate_cert "services-server" "10.150.96.37"
        generate_cert "client" "naaccord.org"
        ;;
    4)
        # Custom
        read -p "Enter web server IP/hostname: " web_host
        read -p "Enter services server IP/hostname: " services_host

        generate_cert "web-server" "$web_host"
        generate_cert "services-server" "$services_host"
        generate_cert "client" "naaccord.local"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

# Create a bundle for client verification
echo -e "\n${YELLOW}Creating certificate bundle...${NC}"
cat ca.crt > ca-bundle.crt
if [ -f intermediate.crt ]; then
    cat intermediate.crt >> ca-bundle.crt
fi

# Set proper permissions
chmod 600 *.key
chmod 644 *.crt

# Generate Diffie-Hellman parameters for perfect forward secrecy
if [ ! -f dhparam.pem ]; then
    echo -e "\n${YELLOW}Generating DH parameters (this may take a while)...${NC}"
    openssl dhparam -out dhparam.pem 2048
fi

# Display certificate information
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Certificates Generated Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Certificate Details:${NC}"
for cert in *.crt; do
    if [ "$cert" != "*.crt" ]; then
        echo -e "\n${BLUE}$cert:${NC}"
        openssl x509 -in $cert -noout -subject -dates | sed 's/^/  /'
    fi
done

# Create README
cat > README.md << EOF
# mTLS Certificates

## Files

- **ca.key** - Certificate Authority private key (KEEP SECURE!)
- **ca.crt** - Certificate Authority certificate
- **server.key/crt** - Server certificate and key
- **client.key/crt** - Client certificate and key
- **dhparam.pem** - Diffie-Hellman parameters

## Usage

### Nginx Configuration
\`\`\`nginx
ssl_certificate /etc/nginx/certs/server.crt;
ssl_certificate_key /etc/nginx/certs/server.key;
ssl_client_certificate /etc/nginx/certs/ca.crt;
ssl_verify_client on;
\`\`\`

### Django Client Configuration
\`\`\`python
REQUESTS_CERT = ('/path/to/client.crt', '/path/to/client.key')
REQUESTS_VERIFY = '/path/to/ca.crt'
\`\`\`

## Security Notes

1. **Never commit private keys to git**
2. **Protect ca.key - it can sign new certificates**
3. **Rotate certificates before expiry**
4. **Use proper file permissions (600 for keys, 644 for certs)**

## Certificate Renewal

Certificates expire in $VALIDITY_DAYS days. To renew, run:
\`\`\`bash
./generate-certificates.sh
\`\`\`
EOF

echo -e "\n${YELLOW}Next steps:${NC}"
echo "1. Copy certificates to servers:"
echo "   - Web server: $CERT_DIR/web-server.*"
echo "   - Services server: $CERT_DIR/services-server.*"
echo "   - CA certificate: $CERT_DIR/ca.crt"
echo ""
echo "2. Update Nginx configuration to use certificates"
echo "3. Update Django settings for client certificates"
echo "4. Test mTLS connection between servers"