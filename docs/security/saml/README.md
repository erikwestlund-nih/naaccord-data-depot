# SAML Configuration

**Consolidated SAML authentication configuration for NA-ACCORD**

## Directory Structure

```
saml/
├── attribute_mappings/  # SAML attribute to Django field mappings
│   ├── basic.py        # Standard attribute mapping configuration
│   └── README.md       # Attribute mapping documentation
├── certs_test/         # Test certificates for development
│   ├── sp.key          # Service Provider private key (test)
│   ├── sp.crt          # Service Provider certificate (test)
│   └── README.md       # Certificate documentation
└── docker-idp/         # Docker SimpleSAMLphp configuration
    ├── config.php      # SimpleSAMLphp base configuration
    ├── authsources.php # Test users and authentication sources
    ├── saml20-sp-remote.php  # Service Provider metadata
    └── idp_metadata.xml      # IdP metadata (reference, dynamically fetched)
```

## Purpose

This directory consolidates all SAML-related configuration files for:
- **Development**: Docker-based SimpleSAMLphp IdP for testing
- **Production**: Integration with institutional IdPs (Johns Hopkins SSO)

## Development Setup

### Using Docker SimpleSAMLphp

1. **Start the mock IdP**:
   ```bash
   docker compose up mock-idp
   ```

2. **Access the IdP**:
   - URL: http://naaccord-test-idp.orb.local:8080/simplesaml/
   - Admin: admin/admin (configured in `docker-idp/config.php`)

3. **Test Users**:
   Configured in `docker-idp/authsources.php`:
   - cohort_admin:cohort_admin
   - site_admin:site_admin
   - cohort_user:cohort_user

4. **Environment Configuration**:
   ```bash
   # Use Docker SAML configuration
   USE_DOCKER_SAML=True
   USE_MOCK_SAML=False
   SAML_IDP_METADATA_URL=http://naaccord-test-idp.orb.local:8080/simplesaml/saml2/idp/metadata.php
   ```

## Production Deployment

### Certificate Management

**⚠️ IMPORTANT**: The certificates in `certs_test/` are for **development only**.

For production:

1. **Generate Production Certificates**:
   ```bash
   # Generate private key
   openssl req -new -x509 -days 3652 -nodes \
     -out saml_certs_prod/sp.crt \
     -keyout saml_certs_prod/sp.key \
     -subj "/CN=naaccord.example.com"

   # Secure the private key
   chmod 600 saml_certs_prod/sp.key
   ```

2. **Configure Production Settings**:
   ```python
   # depot/settings.py
   SAML_CONFIG = {
       'key_file': env('SAML_KEY_FILE', default='/etc/naaccord/saml/sp.key'),
       'cert_file': env('SAML_CERT_FILE', default='/etc/naaccord/saml/sp.crt'),
   }
   ```

3. **Register with IdP**:
   - Upload `sp.crt` to institutional IdP
   - Configure SP entity ID: `https://naaccord.example.com`
   - Set ACS URL: `https://naaccord.example.com/saml2/acs/`
   - Request attribute release policy

### Attribute Mappings

The `attribute_mappings/basic.py` maps IdP attributes to Django user fields:

```python
MAP = {
    'identifier': 'urn:oasis:names:tc:SAML:2.0:attrname-format:uri',
    'fro': {
        'email': 'email',
        'eduPersonPrincipalName': 'username',
        'givenName': 'first_name',
        'sn': 'last_name',
    },
    'to': {
        'email': 'email',
        'username': 'eduPersonPrincipalName',
        'first_name': 'givenName',
        'last_name': 'sn',
    }
}
```

**Required Attributes from IdP**:
- `email` or `mail` - User email address
- `eduPersonPrincipalName` - Unique username
- `givenName` - First name
- `sn` - Surname/last name

## Testing SAML Integration

### Development Testing

1. **Start services**:
   ```bash
   docker compose up web mock-idp
   ```

2. **Navigate to login**:
   - Open: http://localhost:8000/saml2/login/
   - Redirects to SimpleSAMLphp
   - Login with test credentials
   - Redirects back to NA-ACCORD

3. **Verify user creation**:
   ```bash
   docker compose exec web python manage.py shell
   from django.contrib.auth import get_user_model
   User = get_user_model()
   User.objects.all()  # Should show SAML-authenticated user
   ```

### Production Testing

1. **Test in staging first**
2. **Verify attribute release** from institutional IdP
3. **Check user creation** and group assignments
4. **Test single sign-out** functionality

See `docs/security/saml-testing.md` for comprehensive testing procedures.

## Configuration Files

### `docker-idp/config.php`

SimpleSAMLphp base configuration:
- Admin password: `admin`
- Secret salt: `defaultsecretphrase`
- Timezone: America/New_York
- Logging level: DEBUG (development only)

### `docker-idp/authsources.php`

Authentication sources and test users:
- Test accounts with predefined attributes
- Example SAML assertions
- Group membership testing

### `docker-idp/saml20-sp-remote.php`

Service Provider metadata:
- Entity ID configuration
- ACS URL endpoints
- Attribute requirements
- Certificate configuration

## Security Considerations

### Development
- ✅ Test certificates are in git (not sensitive)
- ✅ SimpleSAMLphp runs in isolated container
- ✅ Only accessible from local network

### Production
- ⚠️ **NEVER** commit production certificates to git
- ✅ Store production certs in `/etc/naaccord/saml/` on server
- ✅ Set proper file permissions (600 for `.key`, 644 for `.crt`)
- ✅ Use environment variables for sensitive configuration
- ✅ Enable HTTPS for all SAML endpoints
- ✅ Configure proper certificate validation

## Troubleshooting

### Common Issues

**"SAML Authentication Failed"**:
- Check IdP metadata URL is accessible
- Verify SP certificate is registered with IdP
- Check attribute release policy includes required attributes

**"Invalid Assertion"**:
- Verify clock synchronization between SP and IdP
- Check certificate validity dates
- Confirm ACS URL matches registered endpoint

**"User Created But No Access"**:
- Check attribute mappings in `attribute_mappings/basic.py`
- Verify group assignment logic in `depot/auth/saml_backend.py`
- Check cohort membership assignment

### Debug Mode

Enable SAML debugging:

```python
# depot/settings.py
SAML_CONFIG = {
    'debug': True,  # Enable verbose SAML logging
}

# View logs
docker compose logs web | grep -i saml
```

## Related Documentation

- [SAML Testing Guide](../docs/security/saml-testing.md) - Comprehensive testing procedures
- [Authentication Workflow](../docs/security/auth-workflow.md) - Complete authentication flow
- [Test Accounts](../docs/security/test-accounts.md) - Available test user accounts

## Migration Notes

This directory consolidates several previously scattered SAML configurations:
- `saml_attribute_mappings/` → `saml/attribute_mappings/`
- `saml_certs_test/` → `saml/certs_test/`
- `docker/saml-idp/` → `saml/docker-idp/`
- Removed duplicate: `deploy/containers/saml-idp/` (older version)

All references in `docker-compose.yml`, `depot/settings.py`, and documentation have been updated.