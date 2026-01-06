# SAML Certificates - TEST ONLY

⚠️ **WARNING: These are self-signed TEST certificates**

These certificates (`sp.crt` and `sp.key`) are **FOR TESTING ONLY** and should **NEVER** be used in production.

## Purpose
- Local development SAML testing
- Docker SimpleSAMLphp integration testing
- CI/CD pipeline testing

## Production Deployment
In production environments:
1. Generate proper certificates from your organization's Certificate Authority
2. Store certificates securely (e.g., AWS Secrets Manager, HashiCorp Vault)
3. Mount certificates at runtime via secure mechanisms
4. **NEVER** commit production certificates to version control

## Current Files
- `sp.crt` - Self-signed Service Provider certificate (TEST)
- `sp.key` - Service Provider private key (TEST)

## Generating New Test Certificates
```bash
# Generate new self-signed test certificates
openssl req -x509 -newkey rsa:2048 -keyout sp.key -out sp.crt \
  -days 365 -nodes \
  -subj "/C=US/ST=Test/L=Test/O=NA-ACCORD Test/CN=localhost"
```

## Security Note
These test certificates are intentionally committed to version control for development convenience. Production certificates must be handled through secure deployment pipelines.