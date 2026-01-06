# Nginx Web Server Container
# Production-ready reverse proxy with mTLS support
FROM nginx:1.25-alpine AS production

# Install additional packages
RUN apk add --no-cache \
    curl \
    openssl \
    ca-certificates \
    tzdata \
    && rm -rf /var/cache/apk/*

# Create necessary directories
RUN mkdir -p \
    /etc/nginx/certs \
    /etc/nginx/conf.d \
    /var/www/static \
    /var/www/media \
    /var/log/nginx \
    /var/cache/nginx/client_temp \
    /var/cache/nginx/proxy_temp \
    /var/cache/nginx/fastcgi_temp \
    /var/cache/nginx/uwsgi_temp \
    /var/cache/nginx/scgi_temp \
    /tmp/nginx

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

# Set proper permissions
RUN chown -R nginx:nginx /var/www /var/cache/nginx /var/log/nginx /tmp/nginx && \
    chmod -R 755 /var/www && \
    chmod -R 755 /var/cache/nginx && \
    chmod 777 /tmp/nginx

# Create self-signed certificates for testing (replace with real certs in production)
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/certs/server.key \
    -out /etc/nginx/certs/server.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=naaccord.local"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose ports
EXPOSE 80 443

# Start nginx (runs as root to bind privileged ports, nginx workers run as nginx user)
CMD ["nginx", "-g", "daemon off;"]