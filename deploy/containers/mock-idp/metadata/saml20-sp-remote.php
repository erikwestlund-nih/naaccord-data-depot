<?php
/*
 * SAML 2.0 SP Remote Metadata for NA-ACCORD Mock IDP
 * Defines NA-ACCORD (the Service Provider) from the IDP's perspective
 */

// NA-ACCORD Staging Service Provider
$metadata['https://naaccord.pequod.sh'] = [
    'entityid' => 'https://naaccord.pequod.sh',

    // Assertion Consumer Service - where SAML responses are sent
    'AssertionConsumerService' => [
        [
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            'Location' => 'https://naaccord.pequod.sh/saml2/acs/',
            'index' => 0,
        ],
    ],

    // Single Logout Service
    'SingleLogoutService' => [
        [
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            'Location' => 'https://naaccord.pequod.sh/saml2/ls/',
        ],
    ],

    // Name ID format
    'NameIDFormat' => 'urn:oasis:names:tc:SAML:2.0:nameid-format:transient',

    // Attributes to release (all attributes from authsources.php)
    'attributes' => [
        'uid',
        'eduPersonPrincipalName',
        'email',
        'displayName',
        'givenName',
        'sn',
        'eduPersonAffiliation',
        'cohortAccess',
        'naaccordRole',
        'organization',
    ],

    // Sign assertions and responses
    'sign.authnrequest' => false,
    'sign.logout' => true,
    'validate.authnrequest' => false,

    // Assertion settings
    'assertion.encryption' => false,
];

// NA-ACCORD Local Development Service Provider
$metadata['http://naaccord.test'] = [
    'entityid' => 'http://naaccord.test',

    // Assertion Consumer Service - where SAML responses are sent
    'AssertionConsumerService' => [
        [
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST',
            'Location' => 'http://naaccord.test/saml2/acs/',
            'index' => 0,
        ],
    ],

    // Single Logout Service
    'SingleLogoutService' => [
        [
            'Binding' => 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect',
            'Location' => 'http://naaccord.test/saml2/ls/',
        ],
    ],

    // Name ID format
    'NameIDFormat' => 'urn:oasis:names:tc:SAML:2.0:nameid-format:transient',

    // Attributes to release (all attributes from authsources.php)
    'attributes' => [
        'uid',
        'eduPersonPrincipalName',
        'email',
        'displayName',
        'givenName',
        'sn',
        'eduPersonAffiliation',
        'cohortAccess',
        'naaccordRole',
        'organization',
    ],

    // Sign assertions and responses
    'sign.authnrequest' => false,
    'sign.logout' => true,
    'validate.authnrequest' => false,

    // Assertion settings
    'assertion.encryption' => false,
];
