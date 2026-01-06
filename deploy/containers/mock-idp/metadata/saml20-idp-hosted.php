<?php
/*
 * SAML 2.0 IDP Metadata for NA-ACCORD Mock IDP
 * Hosted metadata - defines this IDP's configuration
 */

$metadata['__DEFAULT__'] = [
    // Use __DEFAULT__ to match any hostname (needed for direct IP access)
    'host' => '__DEFAULT__',

    // X.509 key and certificate for this IDP
    'privatekey' => '/var/simplesamlphp/cert/idp.key',
    'certificate' => '/var/simplesamlphp/cert/idp.crt',

    // Authentication source to use
    'auth' => 'example-userpass',

    // Attributes to release
    'attributes.NameFormat' => 'urn:oasis:names:tc:SAML:2.0:attrname-format:uri',
    'authproc' => [
        // Convert LDAP names to oids for compatibility
        100 => ['class' => 'core:AttributeMap', 'name2oid'],
    ],

    // Session duration
    'session.duration' => 8 * 60 * 60, // 8 hours

    // NameID format
    'NameIDFormat' => 'urn:oasis:names:tc:SAML:2.0:nameid-format:transient',
];
