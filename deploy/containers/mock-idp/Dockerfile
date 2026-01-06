# SimpleSAMLphp Mock IDP Container for NA-ACCORD Staging
# Mimics JHU Shibboleth IDP for SAML testing
FROM php:8.2-apache

# Install required PHP extensions
RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libldap2-dev \
    libssl-dev \
    && docker-php-ext-install xml \
    && docker-php-ext-configure ldap \
    && docker-php-ext-install ldap \
    && rm -rf /var/lib/apt/lists/*

# Install SimpleSAMLphp
ENV SIMPLESAMLPHP_VERSION=2.3.4
RUN curl -L -o /tmp/simplesamlphp.tar.gz \
    "https://github.com/simplesamlphp/simplesamlphp/releases/download/v${SIMPLESAMLPHP_VERSION}/simplesamlphp-${SIMPLESAMLPHP_VERSION}-full.tar.gz" \
    && tar -xzf /tmp/simplesamlphp.tar.gz -C /var \
    && mv "/var/simplesamlphp-${SIMPLESAMLPHP_VERSION}" /var/simplesamlphp \
    && rm /tmp/simplesamlphp.tar.gz

# Configure Apache
RUN printf "Alias /simplesaml /var/simplesamlphp/public\n\n\
<Directory /var/simplesamlphp/public>\n\
    Require all granted\n\
    Options FollowSymLinks\n\
    AllowOverride All\n\
</Directory>\n" > /etc/apache2/conf-available/simplesamlphp.conf \
    && a2enconf simplesamlphp \
    && a2enmod rewrite \
    && a2enmod ssl

# Configure Apache to listen on port 8080 instead of 80
RUN sed -i 's/Listen 80/Listen 8080/' /etc/apache2/ports.conf \
    && sed -i 's/:80>/:8080>/' /etc/apache2/sites-available/000-default.conf

# Set permissions
RUN chown -R www-data:www-data /var/simplesamlphp \
    && chmod -R 755 /var/simplesamlphp

# Create writable directories for data and logs
RUN mkdir -p /var/simplesamlphp/data /var/simplesamlphp/log \
    && chown -R www-data:www-data /var/simplesamlphp/data /var/simplesamlphp/log \
    && chmod -R 775 /var/simplesamlphp/data /var/simplesamlphp/log

# Copy configuration files (will be mounted at runtime)
WORKDIR /var/simplesamlphp

# Expose HTTP port (HTTPS handled by Nginx in production)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/simplesaml/ || exit 1

CMD ["apache2-foreground"]
