<?php
/**
 * SimpleSAMLphp Configuration for test SAML IdP
 */

$config = [
    // Secret salt used for hashing - CHANGE IN PRODUCTION
    'secretsalt' => 'defaultsecretsalt-thisissupersecretfordevonly',

    // Basic configuration
    'baseurlpath' => 'simplesaml/',

    // Technician contact
    'technicalcontact_name' => 'Administrator',
    'technicalcontact_email' => 'admin@example.org',

    // Language settings
    'language.default' => 'en',

    // Timezone
    'timezone' => 'America/New_York',

    // Logging
    'logging.level' => SimpleSAML\Logger::INFO,
    'logging.handler' => 'syslog',

    // Enable admin interface
    'admin.protectindexpage' => false,
    'admin.protectmetadata' => false,

    // Session settings
    'session.cookie.secure' => false,
    'session.phpsession.savepath' => null,
    'session.phpsession.httponly' => true,

    // Authentication processing
    'authproc.idp' => [
        10 => [
            'class' => 'core:AttributeMap',
            'removeurnprefix'
        ],
        20 => 'core:TargetedID',
    ],

    // Store configuration
    'store.type' => 'phpsession',

    // Enable SAML 2.0 IdP
    'enable.saml20-idp' => true,

    // Metadata settings
    'metadata.sources' => [
        ['type' => 'flatfile'],
    ],

    // Trusted domains
    'trusted.url.domains' => ['localhost', '*.orb.local', 'naaccord-test-idp.orb.local'],
];