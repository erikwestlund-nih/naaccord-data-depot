# SAML Attribute Mappings

## Purpose
This directory contains SAML attribute mappings that define how IdP attributes are mapped to Django user fields.

## Files
- `basic.py` - Standard attribute mapping configuration

## Usage Environments
- **Development**: Uses these mappings with Docker SimpleSAMLphp for testing
- **Production**: Uses these same mappings with institutional IdP (e.g., Johns Hopkins SSO)

## Configuration
The `basic.py` file maps common SAML attributes to Django User fields:
- Email variations → `email`
- eduPersonPrincipalName → `username`
- Name attributes → `first_name`, `last_name`
- NA-ACCORD specific attributes → custom fields

## Production vs Development
The **mappings themselves are the same** for both environments. The difference is:
- **Development**: SimpleSAMLphp provides test attributes
- **Production**: Real IdP provides actual user attributes

## Testing
When testing with Docker SimpleSAMLphp:
1. Configure test users in SimpleSAMLphp with appropriate attributes
2. Mappings will translate these to Django user fields
3. Use `.env.docker-saml` for SAML configuration

## Production Deployment
1. Update IdP metadata URL in environment variables
2. Register production SP certificate with institutional IdP
3. Verify attribute release policy includes required attributes
4. Test with real IdP accounts in staging first