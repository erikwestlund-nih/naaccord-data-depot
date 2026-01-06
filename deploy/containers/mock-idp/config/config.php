<?php
/*
 * SimpleSAMLphp Configuration for NA-ACCORD Mock IDP
 * Mimics JHU Shibboleth for staging environment
 */

$config = [
    // Basic configuration
    // Use environment variable or default to staging domain
    'baseurlpath' => getenv('SIMPLESAMLPHP_BASEURL') ?: 'https://naaccord.pequod.sh/simplesaml/',
    'certdir' => 'cert/',
    'loggingdir' => 'log/',
    'datadir' => 'data/',
    'tempdir' => '/tmp/simplesaml',

    // Trust proxy headers from Nginx for proper protocol detection
    'proxy' => [
        'HTTP_X_FORWARDED_PROTO',
        'HTTP_X_FORWARDED_HOST',
        'HTTP_X_FORWARDED_PORT',
    ],

    // Security configuration
    'technicalcontact_name' => 'NA-ACCORD Admin',
    'technicalcontact_email' => 'admin@naaccord.local',
    'secretsalt' => getenv('SIMPLESAMLPHP_SECRET') ?: 'defaultsecretchangeme',
    'auth.adminpassword' => getenv('SIMPLESAMLPHP_ADMIN_PASSWORD') ?: 'admin',

    // Session configuration
    'session.duration' => 8 * 60 * 60, // 8 hours
    'session.datastore.timeout' => 4 * 60 * 60, // 4 hours
    'session.state.timeout' => 60 * 60, // 1 hour
    'session.cookie.name' => 'SimpleSAMLSessionID',
    'session.cookie.lifetime' => 0,
    'session.cookie.path' => '/',
    'session.cookie.domain' => null,
    'session.cookie.secure' => false, // HTTP for staging
    'session.phpsession.cookiename' => 'SimpleSAML',
    'session.phpsession.savepath' => null,
    'session.phpsession.httponly' => true,

    // Enable built-in metadata storage
    'metadata.sources' => [
        ['type' => 'flatfile'],
    ],

    // Store configuration
    'store.type' => 'phpsession',

    // Language configuration
    'language.available' => ['en'],
    'language.default' => 'en',

    // Logging
    // LOG_NOTICE = 5, LOG_INFO = 6, LOG_DEBUG = 7
    'logging.level' => 5,  // LOG_NOTICE
    'logging.handler' => 'errorlog',

    // Enable modules
    'module.enable' => [
        'exampleauth' => true,
        'core' => true,
        'admin' => true,
        'saml' => true,
    ],

    // Enable SAML 2.0 IdP functionality
    'enable.saml20-idp' => true,

    // Theme
    'theme.use' => 'default',

    // Production settings (disabled for staging)
    'admin.protectindexpage' => false,
    'admin.protectmetadata' => false,

    // Allow debugging in staging
    // 'debug' must be an array of debug messages or false/null
    'debug' => ['saml', 'backtraces', 'validatexml'],
    'showerrors' => true,
    'errorreporting' => true,
];
