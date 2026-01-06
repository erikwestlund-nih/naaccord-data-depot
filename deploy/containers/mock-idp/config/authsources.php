<?php
/*
 * Authentication sources configuration for NA-ACCORD Mock IDP
 * Defines test users that mimic production user attributes
 */

$config = [
    // Admin login (for SimpleSAMLphp admin interface)
    'admin' => [
        'core:AdminPassword',
    ],

    // Example authentication source - uses static user definitions
    'example-userpass' => [
        'exampleauth:UserPass',

        // Test users matching production structure
        // Format: 'username:password' => [attributes]

        // Site Admin
        'admin@jh.edu:password' => [
            'uid' => ['admin'],
            'eduPersonPrincipalName' => ['admin@jh.edu'],
            'email' => ['admin@jh.edu'],
            'displayName' => ['System Administrator'],
            'givenName' => ['Admin'],
            'sn' => ['User'],
            'eduPersonAffiliation' => ['employee', 'staff'],
            'naaccordRole' => ['site_admin'],
            'organization' => ['Johns Hopkins University'],
        ],

        // Cohort Manager (VACS)
        'vacs.manager@jh.edu:password' => [
            'uid' => ['vacs_mgr'],
            'eduPersonPrincipalName' => ['vacs.manager@jh.edu'],
            'email' => ['vacs.manager@jh.edu'],
            'displayName' => ['VACS Manager'],
            'givenName' => ['VACS'],
            'sn' => ['Manager'],
            'eduPersonAffiliation' => ['member', 'faculty'],
            'cohortAccess' => ['VACS / VACS8'],
            'naaccordRole' => ['cohort_manager'],
            'organization' => ['Veterans Aging Cohort Study'],
        ],

        // Cohort User (MACS)
        'macs.user@jh.edu:password' => [
            'uid' => ['macs_user'],
            'eduPersonPrincipalName' => ['macs.user@jh.edu'],
            'email' => ['macs.user@jh.edu'],
            'displayName' => ['MACS User'],
            'givenName' => ['MACS'],
            'sn' => ['User'],
            'eduPersonAffiliation' => ['member', 'staff'],
            'cohortAccess' => ['MACS'],
            'naaccordRole' => ['cohort_user'],
            'organization' => ['Multicenter AIDS Cohort Study'],
        ],

        // Cohort User (WIHS)
        'wihs.user@jh.edu:password' => [
            'uid' => ['wihs_user'],
            'eduPersonPrincipalName' => ['wihs.user@jh.edu'],
            'email' => ['wihs.user@jh.edu'],
            'displayName' => ['WIHS User'],
            'givenName' => ['WIHS'],
            'sn' => ['User'],
            'eduPersonAffiliation' => ['member', 'staff'],
            'cohortAccess' => ['WIHS'],
            'naaccordRole' => ['cohort_user'],
            'organization' => ['Women\'s Interagency HIV Study'],
        ],

        // Read-only User
        'viewer@jh.edu:password' => [
            'uid' => ['viewer'],
            'eduPersonPrincipalName' => ['viewer@jh.edu'],
            'email' => ['viewer@jh.edu'],
            'displayName' => ['Read-Only Viewer'],
            'givenName' => ['Viewer'],
            'sn' => ['User'],
            'eduPersonAffiliation' => ['member'],
            'cohortAccess' => ['VACS / VACS8', 'MACS'],
            'naaccordRole' => ['viewer'],
            'organization' => ['Johns Hopkins University'],
        ],

        // Multi-cohort User (for testing multi-cohort access)
        'multi.cohort@jh.edu:password' => [
            'uid' => ['multi'],
            'eduPersonPrincipalName' => ['multi.cohort@jh.edu'],
            'email' => ['multi.cohort@jh.edu'],
            'displayName' => ['Multi-Cohort User'],
            'givenName' => ['Multi'],
            'sn' => ['Cohort'],
            'eduPersonAffiliation' => ['member', 'staff'],
            'cohortAccess' => ['VACS / VACS8', 'MACS', 'WIHS'],
            'naaccordRole' => ['cohort_user'],
            'organization' => ['Johns Hopkins University'],
        ],

        // No cohort access (for testing authorization)
        'nocohort@jh.edu:password' => [
            'uid' => ['nocohort'],
            'eduPersonPrincipalName' => ['nocohort@jh.edu'],
            'email' => ['nocohort@jh.edu'],
            'displayName' => ['No Cohort Access'],
            'givenName' => ['No'],
            'sn' => ['Cohort'],
            'eduPersonAffiliation' => ['member'],
            'naaccordRole' => ['viewer'],
            'organization' => ['Johns Hopkins University'],
        ],

        // Acunetix Scan Support User (ssuppor2)
        // Production SAML will return ssuppor2@johnshopkins.edu
        'ssuppor2@jh.edu:ScanSupport2025!' => [
            'uid' => ['ssuppor2'],
            'eduPersonPrincipalName' => ['ssuppor2@jh.edu'],
            'email' => ['ssuppor2@johnshopkins.edu'],  // Matches production SSO email
            'displayName' => ['Scan Support'],
            'givenName' => ['Scan'],
            'sn' => ['Support'],
            'eduPersonAffiliation' => ['member'],
            'cohortAccess' => ['Scan Support'],
            'naaccordRole' => ['cohort_user'],
            'organization' => ['Johns Hopkins University - Security Scanning'],
        ],
    ],
];
