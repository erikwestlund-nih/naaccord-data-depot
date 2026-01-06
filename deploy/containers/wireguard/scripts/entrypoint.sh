#!/bin/bash

# NA-ACCORD WireGuard Container Entrypoint
# PHI-Compliant VPN Tunnel for Healthcare Data
set -e

# Configuration
INTERFACE="wg0"
LOG_FILE="/var/log/wireguard/wireguard.log"
CONFIG_FILE="/etc/wireguard/wg0.conf"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Create log directory
mkdir -p /var/log/wireguard

# PHI Compliance Audit Log
audit_log() {
    local event="$1"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
    echo "${timestamp} | PHI_AUDIT | ${event}" >> /var/log/wireguard/phi-audit.log
}

# Generate WireGuard configuration from secrets
generate_config() {
    log "Generating WireGuard configuration from environment..."

    # Read secrets from files
    if [ -n "$WG_PRIVATE_KEY_FILE" ] && [ -f "$WG_PRIVATE_KEY_FILE" ]; then
        WG_PRIVATE_KEY=$(cat "$WG_PRIVATE_KEY_FILE")
        log "Loaded private key from secret file"
    else
        error "WG_PRIVATE_KEY_FILE not set or file not found: $WG_PRIVATE_KEY_FILE"
        exit 1
    fi

    if [ -n "$WG_PEER_PUBLIC_KEY_FILE" ] && [ -f "$WG_PEER_PUBLIC_KEY_FILE" ]; then
        WG_PEER_PUBLIC_KEY=$(cat "$WG_PEER_PUBLIC_KEY_FILE")
        log "Loaded peer public key from secret file"
    else
        error "WG_PEER_PUBLIC_KEY_FILE not set or file not found: $WG_PEER_PUBLIC_KEY_FILE"
        exit 1
    fi

    if [ -n "$WG_PRESHARED_KEY_FILE" ] && [ -f "$WG_PRESHARED_KEY_FILE" ]; then
        WG_PRESHARED_KEY=$(cat "$WG_PRESHARED_KEY_FILE")
        log "Loaded preshared key from secret file"
    else
        warn "WG_PRESHARED_KEY_FILE not set or file not found (optional)"
    fi

    # Validate required environment variables
    if [ -z "$WG_TUNNEL_ADDRESS" ]; then
        error "WG_TUNNEL_ADDRESS not set"
        exit 1
    fi

    if [ -z "$WG_PEER_ADDRESS" ]; then
        error "WG_PEER_ADDRESS not set"
        exit 1
    fi

    # Create wireguard config directory
    mkdir -p /etc/wireguard
    chmod 700 /etc/wireguard

    # Generate config file
    cat > "$CONFIG_FILE" <<EOF
[Interface]
PrivateKey = ${WG_PRIVATE_KEY}
Address = ${WG_TUNNEL_ADDRESS}
ListenPort = 51820

[Peer]
PublicKey = ${WG_PEER_PUBLIC_KEY}
AllowedIPs = ${WG_PEER_ADDRESS}/32
EOF

    # Add endpoint if present (for client-side connections)
    if [ -n "$WG_PEER_ENDPOINT" ]; then
        echo "Endpoint = ${WG_PEER_ENDPOINT}" >> "$CONFIG_FILE"
    fi

    # Add preshared key if present
    if [ -n "$WG_PRESHARED_KEY" ]; then
        echo "PresharedKey = ${WG_PRESHARED_KEY}" >> "$CONFIG_FILE"
    fi

    # Add persistent keepalive for NAT traversal
    echo "PersistentKeepalive = 25" >> "$CONFIG_FILE"

    chmod 600 "$CONFIG_FILE"
    success "WireGuard configuration generated successfully"
    audit_log "CONFIG_GENERATED"
}

# Validate environment
validate_environment() {
    log "Validating WireGuard environment..."

    # Check for TUN device
    if [ ! -c /dev/net/tun ]; then
        error "TUN device not available. Container needs --device /dev/net/tun:/dev/net/tun"
        exit 1
    fi

    # Check for NET_ADMIN capability
    if ! ip link add dummy0 type dummy 2>/dev/null; then
        warn "NET_ADMIN capability not detected. Container may need --cap-add NET_ADMIN"
    else
        ip link delete dummy0 2>/dev/null
    fi

    # Check for configuration file
    if [ ! -f "$CONFIG_FILE" ]; then
        error "WireGuard configuration not found: $CONFIG_FILE"
        exit 1
    fi

    success "Environment validation complete"
}

# Test configuration
test_configuration() {
    log "Testing WireGuard configuration..."

    if wg-quick strip "$INTERFACE" >/dev/null 2>&1; then
        success "Configuration syntax valid"
        audit_log "CONFIG_VALIDATED"
    else
        error "Invalid WireGuard configuration"
        audit_log "CONFIG_VALIDATION_FAILED"
        exit 1
    fi
}

# Start the WireGuard tunnel
start_tunnel() {
    log "Starting WireGuard tunnel..."

    # Start the tunnel
    if wg-quick up "$INTERFACE"; then
        success "WireGuard tunnel started successfully"
        audit_log "TUNNEL_STARTED"

        # Log tunnel info
        log "Tunnel interface info:"
        ip addr show "$INTERFACE" | tee -a "$LOG_FILE"

        # Log peers
        log "Peer connections:"
        wg show "$INTERFACE" | tee -a "$LOG_FILE"

        # Setup port forwarding for services (MariaDB, Redis, Django)
        # Forward traffic from WireGuard tunnel to services network
        if [ -n "$WG_FORWARD_PORTS" ]; then
            log "Setting up port forwarding for services..."

            for port_spec in $WG_FORWARD_PORTS; do
                port=$(echo $port_spec | cut -d: -f1)
                proto=$(echo $port_spec | cut -d: -f2)
                dest_ip=$(echo $port_spec | cut -d: -f3)

                # If no destination IP specified, use Docker gateway
                if [ -z "$dest_ip" ]; then
                    dest_ip=$(ip route | grep default | awk '{print $3}')
                fi

                if [ "$proto" = "tcp" ]; then
                    # DNAT: Rewrite destination for traffic coming into tunnel
                    iptables -t nat -A PREROUTING -i $INTERFACE -p tcp --dport $port -j DNAT --to-destination ${dest_ip}:${port}
                    # MASQUERADE: Rewrite source for forwarded traffic (kernel routes to correct interface)
                    iptables -t nat -A POSTROUTING -p tcp -d ${dest_ip} --dport $port -j MASQUERADE
                    log "Forwarding TCP port $port to ${dest_ip}:${port}"
                fi
            done

            # Add MASQUERADE rule for return traffic through WireGuard tunnel
            # This allows responses from Docker network (10.101.0.0/24) to reach tunnel peers (10.100.0.0/24)
            # Extract network from WG_TUNNEL_ADDRESS (e.g., 10.100.0.11/24 → 10.100.0.0/24)
            TUNNEL_NETWORK=$(echo "$WG_TUNNEL_ADDRESS" | sed 's/\.[0-9]*\//.0\//')
            DOCKER_NETWORK="${WG_FORWARD_NETWORK:-10.101.0.0/24}"

            iptables -t nat -A POSTROUTING -s "$DOCKER_NETWORK" -d "$TUNNEL_NETWORK" -o "$INTERFACE" -j MASQUERADE
            log "MASQUERADE return traffic: $DOCKER_NETWORK → $TUNNEL_NETWORK via $INTERFACE"

            audit_log "PORT_FORWARDING_CONFIGURED"
        fi

        # Add MASQUERADE rule for client-side outgoing traffic
        # This allows the web server (10.100.0.10) to connect TO the services server (10.100.0.11)
        if [ -n "$WG_PEER_ADDRESS" ]; then
            log "Setting up MASQUERADE for outgoing tunnel traffic..."

            # Extract local tunnel IP from WG_TUNNEL_ADDRESS (e.g., 10.100.0.10/24 → 10.100.0.10)
            LOCAL_IP=$(echo "$WG_TUNNEL_ADDRESS" | cut -d/ -f1)

            # MASQUERADE outgoing traffic from this container to the peer
            iptables -t nat -A POSTROUTING -s "$LOCAL_IP" -d "$WG_PEER_ADDRESS" -o "$INTERFACE" -j MASQUERADE
            log "MASQUERADE outgoing traffic: $LOCAL_IP → $WG_PEER_ADDRESS via $INTERFACE"

            audit_log "OUTGOING_MASQUERADE_CONFIGURED"
        fi

        audit_log "TUNNEL_INFO_LOGGED"
    else
        error "Failed to start WireGuard tunnel"
        audit_log "TUNNEL_START_FAILED"
        exit 1
    fi
}

# Monitor tunnel health
monitor_tunnel() {
    log "Starting tunnel health monitoring..."

    while true; do
        # Check interface status
        if ip link show "$INTERFACE" >/dev/null 2>&1; then
            # Log peer handshakes every 5 minutes
            if [ $(($(date +%s) % 300)) -eq 0 ]; then
                wg show "$INTERFACE" latest-handshakes | while read -r peer handshake; do
                    if [ "$handshake" != "0" ]; then
                        audit_log "PEER_HANDSHAKE|${peer}|$(date -d @${handshake})"
                    fi
                done
            fi
        else
            error "WireGuard interface $INTERFACE is down"
            audit_log "TUNNEL_DOWN"
            exit 1
        fi

        sleep 5
    done
}

# Cleanup function
cleanup() {
    log "Shutting down WireGuard tunnel..."

    if wg-quick down "$INTERFACE" 2>/dev/null; then
        success "WireGuard tunnel stopped cleanly"
        audit_log "TUNNEL_STOPPED_CLEAN"
    else
        warn "WireGuard tunnel may not have stopped cleanly"
        audit_log "TUNNEL_STOPPED_UNCLEAN"
    fi

    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Main execution
main() {
    log "Starting WireGuard container"
    audit_log "CONTAINER_STARTED"

    generate_config
    validate_environment
    test_configuration
    start_tunnel

    log "WireGuard tunnel is running. Monitoring for health..."
    monitor_tunnel
}

# Execute main function
main "$@"
