<?php

/**
 * SAML 2.0 SP (Service Provider) metadata for NA-ACCORD
 * This tells the IdP how to communicate with our Django application
 */

// Staging configuration - HTTPS domain
$metadata['https://naaccord.pequod.sh'] = array(
    // Entity ID must match what Django sends
    'entityid' => 'https://naaccord.pequod.sh',

    // Assertion Consumer Service - where IdP sends SAML responses
    'AssertionConsumerService' => array(
        0 => array(
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            'Location' => 'https://naaccord.pequod.sh/saml2/acs/',
            'index' => 0,
            'isDefault' => true,
        ),
    ),

    // Single Logout Service (optional)
    'SingleLogoutService' => array(
        0 => array(
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            'Location' => 'https://naaccord.pequod.sh/saml2/ls/',
        ),
    ),

    // NameID format
    'NameIDFormat' => 'urn:oasis:names:tc:SAML:2.0:nameid-format:emailAddress',

    // Attributes to send to SP
    'attributes' => array(
        'eduPersonPrincipalName',
        'email',
        'displayName',
        'givenName',
        'sn',
        'eduPersonAffiliation',
        'eduPersonScopedAffiliation',
        'cohortAccess',
        'naaccordRole',
        'organization',
    ),

    // Attribute mapping (optional - maps IdP attributes to SP expected names)
    'attributes.NameFormat' => 'urn:oasis:names:tc:SAML:2.0:attrname-format:uri',

    // Sign assertions and responses
    'sign.assertion' => true,
    'sign.response' => true,

    // Encryption (disabled for development simplicity)
    'assertion.encryption' => false,
);

// Local development configuration
$metadata['http://localhost:8000'] = array(
    // Entity ID must match what Django sends
    'entityid' => 'http://localhost:8000',

    // Assertion Consumer Service - where IdP sends SAML responses
    'AssertionConsumerService' => array(
        0 => array(
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            'Location' => 'http://localhost:8000/saml2/acs/',
            'index' => 0,
            'isDefault' => true,
        ),
    ),

    // Single Logout Service (optional)
    'SingleLogoutService' => array(
        0 => array(
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            'Location' => 'http://localhost:8000/saml2/ls/',
        ),
    ),

    // NameID format
    'NameIDFormat' => 'urn:oasis:names:tc:SAML:2.0:nameid-format:emailAddress',

    // Attributes to send to SP
    'attributes' => array(
        'eduPersonPrincipalName',
        'email', 
        'displayName',
        'givenName',
        'sn',
        'eduPersonAffiliation',
        'eduPersonScopedAffiliation',
        'cohortAccess',
        'naaccordRole',
        'organization',
    ),

    // Attribute mapping (optional - maps IdP attributes to SP expected names)
    'attributes.NameFormat' => 'urn:oasis:names:tc:SAML:2.0:attrname-format:uri',
    
    // Sign assertions and responses
    'sign.assertion' => true,
    'sign.response' => true,
    
    // Encryption (disabled for development simplicity)
    'assertion.encryption' => false,
);

// Production SP metadata would go here with proper certificates
// $metadata['https://depot.naaccord.org'] = array(
//     'entityid' => 'https://depot.naaccord.org',
//     'AssertionConsumerService' => array(
//         0 => array(
//             'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
//             'Location' => 'https://depot.naaccord.org/auth/saml/acs/',
//             'index' => 0,
//             'isDefault' => true,
//         ),
//     ),
//     // ... rest of production config
// );