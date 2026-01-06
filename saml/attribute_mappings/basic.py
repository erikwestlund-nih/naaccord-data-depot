"""
SAML Attribute Mapping for NA-ACCORD
Maps SAML IdP attributes to Django user attributes
"""

# Map from SAML attribute names to Django User model fields
MAP = {
    # Basic user information
    'email': 'email',
    'emailAddress': 'email', 
    'mail': 'email',
    
    'eduPersonPrincipalName': 'username',
    
    'displayName': 'get_full_name',
    'cn': 'get_full_name',
    'commonName': 'get_full_name',
    
    'givenName': 'first_name',
    'firstName': 'first_name', 
    'given_name': 'first_name',
    
    'sn': 'last_name',
    'surname': 'last_name',
    'lastName': 'last_name',
    'last_name': 'last_name',
    
    # NA-ACCORD specific attributes (handled in custom backend)
    'eduPersonAffiliation': 'eduPersonAffiliation',
    'eduPersonScopedAffiliation': 'eduPersonScopedAffiliation', 
    'cohortAccess': 'cohortAccess',
    'naaccordRole': 'naaccordRole',
    'organization': 'organization',
}

# Reverse mapping for creating SAML assertions (for testing)
REVERSE_MAP = {v: k for k, v in MAP.items()}