#!/bin/bash
# Generate development WireGuard keys (NOT FOR PRODUCTION)
# These keys are committed to the repo for development consistency

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Generating development WireGuard keys..."
echo "WARNING: These are for DEVELOPMENT ONLY. Never use in production!"

# Web container keys
WEB_PRIVATE="EKrSaJxnNG4FRPpL1N8gOz1U+RKlsB5Xn7qjDh5bWGM="
WEB_PUBLIC="fE6BdJgFCxHVuPd1Rfmen2scgLksFa0fKny8uRNP5zs="

# Services container keys
SERVICES_PRIVATE="oMpaO9nqQdFgaHvvDJtL9LuwE5HI3B3G8D5CeIhX/3s="
SERVICES_PUBLIC="OBxlJ0K6gYLDplmPgpVK2m7S1cTaINPcMT7dXJyVhiE="

# Pre-shared key for additional security
PRESHARED="TQJmkBbz3rNQzw5+EL3yB1kxQ3GyXcD+l9tCbxGm2LU="

# Create key files
echo "$WEB_PRIVATE" > "$SCRIPT_DIR/web-private.key"
echo "$WEB_PUBLIC" > "$SCRIPT_DIR/web-public.key"
echo "$SERVICES_PRIVATE" > "$SCRIPT_DIR/services-private.key"
echo "$SERVICES_PUBLIC" > "$SCRIPT_DIR/services-public.key"
echo "$PRESHARED" > "$SCRIPT_DIR/preshared.key"

# Create WireGuard configs
cat > "$SCRIPT_DIR/web-wg0.conf" <<EOF
[Interface]
PrivateKey = $WEB_PRIVATE
Address = 10.100.0.10/24
ListenPort = 51820

[Peer]
PublicKey = $SERVICES_PUBLIC
PresharedKey = $PRESHARED
AllowedIPs = 10.100.0.11/32
Endpoint = services:51821
PersistentKeepalive = 25
EOF

cat > "$SCRIPT_DIR/services-wg0.conf" <<EOF
[Interface]
PrivateKey = $SERVICES_PRIVATE
Address = 10.100.0.11/24
ListenPort = 51821

[Peer]
PublicKey = $WEB_PUBLIC
PresharedKey = $PRESHARED
AllowedIPs = 10.100.0.10/32
Endpoint = web:51820
PersistentKeepalive = 25
EOF

# For development simplicity, create a single tunnel config
cat > "$SCRIPT_DIR/tunnel-wg0.conf" <<EOF
# Development WireGuard tunnel configuration
[Interface]
PrivateKey = $WEB_PRIVATE
Address = 10.100.0.10/24, 10.100.0.11/24
ListenPort = 51820

# Allow both IPs in dev for simplified setup
PostUp = iptables -t nat -A POSTROUTING -s 10.100.0.0/24 -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -s 10.100.0.0/24 -j MASQUERADE
EOF

chmod 600 "$SCRIPT_DIR"/*.key
chmod 600 "$SCRIPT_DIR"/*.conf

echo ""
echo "✅ Development keys generated in $SCRIPT_DIR"
echo ""
echo "Files created:"
ls -la "$SCRIPT_DIR"/*.key "$SCRIPT_DIR"/*.conf 2>/dev/null | awk '{print "  " $9}'
echo ""
echo "⚠️  SECURITY WARNING:"
echo "These keys are for DEVELOPMENT ONLY and are committed to the repository."
echo "NEVER use these keys in production environments!"