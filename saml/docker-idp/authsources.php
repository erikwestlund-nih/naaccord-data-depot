<?php

/**
 * SAML 2.0 IdP configuration for NA-ACCORD development
 * This file configures the test users that can authenticate via SAML
 */

$config = array(

    // Administrative login for SimpleSAMLphp itself
    'admin' => array(
        'core:AdminPassword',
    ),

    // NA-ACCORD Test Users Database
    // Each user represents different cohorts and roles
    'example-userpass' => array(
        'exampleauth:UserPass',
        
        // Admin User - Full system access
        'admin@test.edu:admin' => array(
            'uid' => array('admin'),
            'eduPersonPrincipalName' => array('admin@test.edu'),
            'email' => array('admin@test.edu'),
            'displayName' => array('Admin User'),
            'givenName' => array('Admin'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('staff', 'member'),
            'eduPersonScopedAffiliation' => array('staff@test.edu', 'member@test.edu'),
            'cohortAccess' => array('1', '2', '3'), // Multiple cohorts
            'naaccordRole' => array('admin'),
        ),

        // Research User - Single cohort access
        'researcher@test.edu:researcher' => array(
            'uid' => array('researcher'),
            'eduPersonPrincipalName' => array('researcher@test.edu'),
            'email' => array('researcher@test.edu'),
            'displayName' => array('Research User'),
            'givenName' => array('Research'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('faculty', 'member'),
            'eduPersonScopedAffiliation' => array('faculty@test.edu', 'member@test.edu'),
            'cohortAccess' => array('1'),
            'naaccordRole' => array('researcher'),
        ),

        // Coordinator User - Cohort management
        'coordinator@test.edu:coordinator' => array(
            'uid' => array('coordinator'),
            'eduPersonPrincipalName' => array('coordinator@test.edu'),
            'email' => array('coordinator@test.edu'),
            'displayName' => array('Coordinator User'),
            'givenName' => array('Coordinator'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('staff', 'member'),
            'eduPersonScopedAffiliation' => array('staff@test.edu', 'member@test.edu'),
            'cohortAccess' => array('2'),
            'naaccordRole' => array('coordinator'),
        ),

        // Johns Hopkins User
        'user@jhu.edu:jhu123' => array(
            'uid' => array('jhuuser'),
            'eduPersonPrincipalName' => array('user@jhu.edu'),
            'email' => array('user@jhu.edu'),
            'displayName' => array('Johns Hopkins User'),
            'givenName' => array('Johns Hopkins'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('member'),
            'eduPersonScopedAffiliation' => array('member@jhu.edu'),
            'cohortAccess' => array('5'), // JHHCC cohort
            'naaccordRole' => array('member'),
            'organization' => array('Johns Hopkins University'),
        ),

        // UC San Diego User
        'user@ucsd.edu:ucsd123' => array(
            'uid' => array('ucsduser'),
            'eduPersonPrincipalName' => array('user@ucsd.edu'),
            'email' => array('user@ucsd.edu'),
            'displayName' => array('UCSD User'),
            'givenName' => array('UCSD'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('member'),
            'eduPersonScopedAffiliation' => array('member@ucsd.edu'),
            'cohortAccess' => array('13'), // UCSD cohort
            'naaccordRole' => array('member'),
            'organization' => array('University of California San Diego'),
        ),

        // Case Western User
        'user@case.edu:case123' => array(
            'uid' => array('caseuser'),
            'eduPersonPrincipalName' => array('user@case.edu'),
            'email' => array('user@case.edu'),
            'displayName' => array('Case Western User'),
            'givenName' => array('Case Western'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('member'),
            'eduPersonScopedAffiliation' => array('member@case.edu'),
            'cohortAccess' => array('7'), // Case cohort
            'naaccordRole' => array('member'),
            'organization' => array('Case Western Reserve University'),
        ),

        // UAB User
        'user@uab.edu:uab123' => array(
            'uid' => array('uabuser'),
            'eduPersonPrincipalName' => array('user@uab.edu'),
            'email' => array('user@uab.edu'),
            'displayName' => array('UAB User'),
            'givenName' => array('UAB'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('member'),
            'eduPersonScopedAffiliation' => array('member@uab.edu'),
            'cohortAccess' => array('8'), // UAB cohort
            'naaccordRole' => array('member'),
            'organization' => array('University of Alabama at Birmingham'),
        ),

        // Viewer Role - Read-only access
        'viewer@test.edu:viewer' => array(
            'uid' => array('viewer'),
            'eduPersonPrincipalName' => array('viewer@test.edu'),
            'email' => array('viewer@test.edu'),
            'displayName' => array('Viewer User'),
            'givenName' => array('Viewer'),
            'sn' => array('User'),
            'eduPersonAffiliation' => array('member'),
            'eduPersonScopedAffiliation' => array('member@test.edu'),
            'cohortAccess' => array('5'), // JHHCC
            'naaccordRole' => array('viewer'),
        ),

        // VA Admin - VACS/VACS8 cohort with Data Managers group
        'admin@va.gov:admin' => array(
            'uid' => array('va_admin'),
            'eduPersonPrincipalName' => array('admin@va.gov'),
            'email' => array('admin@va.gov'),
            'displayName' => array('VA Admin'),
            'givenName' => array('VA'),
            'sn' => array('Admin'),
            'eduPersonAffiliation' => array('staff', 'member'),
            'eduPersonScopedAffiliation' => array('staff@va.gov', 'member@va.gov'),
            'cohortAccess' => array('18'), // VACS/VACS8
            'naaccordRole' => array('admin'),
            'organization' => array('Department of Veterans Affairs'),
            'groups' => array('Data Managers'),
        ),

        // Johns Hopkins Researcher - JHHCC cohort
        'admin@jh.edu:admin' => array(
            'uid' => array('jh_researcher'),
            'eduPersonPrincipalName' => array('admin@jh.edu'),
            'email' => array('admin@jh.edu'),
            'displayName' => array('JH Researcher'),
            'givenName' => array('JH'),
            'sn' => array('Researcher'),
            'eduPersonAffiliation' => array('faculty', 'member'),
            'eduPersonScopedAffiliation' => array('faculty@jh.edu', 'member@jh.edu'),
            'cohortAccess' => array('5'), // JHHCC
            'naaccordRole' => array('researcher'),
            'organization' => array('Johns Hopkins University'),
            'groups' => array('Researchers'),
        ),
    ),
);