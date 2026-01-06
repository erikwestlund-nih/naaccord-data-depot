# Containerized WireGuard for PHI Data Encryption
# Uses wireguard-go userspace implementation for Docker compatibility
FROM alpine:3.19

# Install WireGuard with userspace implementation
# wireguard-tools includes wg-quick and wg userspace tools
RUN apk add --no-cache \
    bash \
    curl \
    iptables \
    ip6tables \
    iproute2 \
    openssl \
    ca-certificates \
    wireguard-tools \
    jq \
    busybox-extras \
    netcat-openbsd \
    && rm -rf /var/cache/apk/*

# Create WireGuard directory structure
RUN mkdir -p /etc/wireguard /var/log/wireguard /opt/wireguard

# Copy scripts
COPY deploy/containers/wireguard/scripts/healthcheck.sh /opt/wireguard/healthcheck.sh
COPY deploy/containers/wireguard/scripts/entrypoint.sh /opt/wireguard/entrypoint.sh

# Set permissions
RUN chmod +x /opt/wireguard/*.sh && \
    chmod 700 /etc/wireguard

# Create wireguard user
RUN addgroup -g 1000 wireguard && \
    adduser -u 1000 -G wireguard -s /bin/bash -D wireguard

# Environment variables
ENV WG_INTERFACE=wg0
ENV WG_LOG_LEVEL=info
ENV HEALTH_CHECK_INTERVAL=30

# Health check for tunnel status
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD /opt/wireguard/healthcheck.sh

# Expose WireGuard port
EXPOSE 51820/udp

# Log to stdout for container logging
VOLUME ["/var/log/wireguard"]

# Run as non-root when possible (WireGuard needs NET_ADMIN)
USER root

ENTRYPOINT ["/opt/wireguard/entrypoint.sh"]