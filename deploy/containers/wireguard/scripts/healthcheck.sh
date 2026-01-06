#!/bin/bash

# NA-ACCORD WireGuard Health Check
# PHI Compliance Monitoring
set -e

INTERFACE="wg0"
LOG_FILE="/var/log/wireguard/health.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Health check functions
check_interface() {
    if ip link show "$INTERFACE" >/dev/null 2>&1; then
        log "${GREEN}✓ Interface $INTERFACE is up${NC}"
        return 0
    else
        log "${RED}✗ Interface $INTERFACE is down${NC}"
        return 1
    fi
}

check_peers() {
    local peer_count=$(wg show "$INTERFACE" peers 2>/dev/null | wc -l)

    if [ "$peer_count" -gt 0 ]; then
        log "${GREEN}✓ $peer_count peer(s) configured${NC}"

        # Check recent handshakes
        while read -r peer handshake; do
            if [ "$handshake" != "0" ]; then
                local age=$(($(date +%s) - handshake))
                if [ "$age" -lt 300 ]; then
                    log "${GREEN}✓ Peer $peer: Recent handshake (${age}s ago)${NC}"
                else
                    log "${YELLOW}⚠ Peer $peer: Stale handshake (${age}s ago)${NC}"
                fi
            fi
        done < <(wg show "$INTERFACE" latest-handshakes 2>/dev/null || echo "")

        return 0
    else
        log "${RED}✗ No peers configured${NC}"
        return 1
    fi
}

check_tunnel_connectivity() {
    # Try to ping through tunnel (if peer endpoints are known)
    local tunnel_ip=$(ip addr show "$INTERFACE" 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)

    if [ -n "$tunnel_ip" ]; then
        log "${GREEN}✓ Tunnel IP: $tunnel_ip${NC}"

        # Test basic tunnel functionality
        if ip route show dev "$INTERFACE" >/dev/null 2>&1; then
            log "${GREEN}✓ Tunnel routing active${NC}"
            return 0
        else
            log "${YELLOW}⚠ No routes through tunnel${NC}"
            return 1
        fi
    else
        log "${RED}✗ No tunnel IP assigned${NC}"
        return 1
    fi
}

# PHI Compliance checks
check_encryption() {
    # Verify encryption is active
    if wg show "$INTERFACE" 2>/dev/null | grep -q "public key"; then
        log "${GREEN}✓ Encryption keys active${NC}"
        return 0
    else
        log "${RED}✗ No encryption keys found${NC}"
        return 1
    fi
}

audit_status() {
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
    local status="$1"
    echo "${timestamp} | PHI_AUDIT | HEALTH_CHECK_${status}" >> /var/log/wireguard/phi-audit.log
}

# Main health check
main() {
    log "Starting WireGuard health check..."

    local exit_code=0

    check_interface || exit_code=1
    check_peers || exit_code=1
    check_tunnel_connectivity || exit_code=1
    check_encryption || exit_code=1

    if [ "$exit_code" -eq 0 ]; then
        log "${GREEN}✓ All health checks passed${NC}"
        audit_status "PASSED"
    else
        log "${RED}✗ Some health checks failed${NC}"
        audit_status "FAILED"
    fi

    wg show "$INTERFACE" 2>/dev/null || log "Interface not available"

    exit "$exit_code"
}

main "$@"
