"""
Create scan support user for Acunetix security scanning.

This command creates:
1. A test cohort called "Scan Support"
2. A user account for JHED ssuppor2 (no password - SAML authentication)
3. Associates user with the Scan Support cohort
4. Adds user to "Cohort Manager" group
5. Sets normal user permissions (no admin)

IDEMPOTENT: Can be run multiple times. Updates existing user if found.

Usage:
    python manage.py create_scan_user
    python manage.py create_scan_user --email custom@jh.edu --jhed custom_jhed
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from depot.models import Cohort, CohortMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Create scan support user and test cohort for Acunetix security scanning'

    def add_arguments(self, parser):
        parser.add_argument(
            '--jhed',
            type=str,
            default='ssuppor2',
            help='JHED username for scan support user (default: ssuppor2)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default='ssuppor2@jh.edu',
            help='Email address for scan support user (default: ssuppor2@jh.edu)'
        )
        parser.add_argument(
            '--sso-email',
            type=str,
            default='ssuppor2@johnshopkins.edu',
            help='SSO email for SAML authentication (default: ssuppor2@johnshopkins.edu)'
        )
        parser.add_argument(
            '--first-name',
            type=str,
            default='Scan',
            help='First name (default: Scan)'
        )
        parser.add_argument(
            '--last-name',
            type=str,
            default='Support',
            help='Last name (default: Support)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        jhed = options['jhed']
        email = options['email']
        sso_email = options['sso_email']
        first_name = options['first_name']
        last_name = options['last_name']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('Creating Scan Support User and Cohort'))
        self.stdout.write('=' * 70)

        # Step 1: Create or get "Scan Support" cohort
        self.stdout.write('\n1. Creating/Getting Scan Support Cohort...')
        cohort, created = Cohort.objects.get_or_create(
            name='Scan Support',
            defaults={
                'status': 'active',
                'type': 'clinical',
            }
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Created cohort: {cohort.name} (ID: {cohort.id})')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'  ⚠ Cohort already exists: {cohort.name} (ID: {cohort.id})')
            )

        # Step 2: Create or update user account (IDEMPOTENT)
        user_exists = User.objects.filter(username=jhed).exists()
        if user_exists:
            self.stdout.write(f'\n2. Updating Existing User Account ({jhed})...')
            user = User.objects.get(username=jhed)
            user.email = email
            user.sso_email = sso_email
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = False      # Ensure NOT staff
            user.is_superuser = False  # Ensure NOT superuser
            user.is_active = True
            # Mark password as unusable for SAML-only auth
            user.set_unusable_password()
            user.save()
            self.stdout.write(
                self.style.WARNING(f'  ⚠ Updated existing user: {user.username} ({user.email}) [SSO: {sso_email}]')
            )
        else:
            self.stdout.write(f'\n2. Creating User Account ({jhed})...')
            # Create WITHOUT password - SAML authentication only
            user = User.objects.create(
                username=jhed,
                email=email,
                sso_email=sso_email,
                first_name=first_name,
                last_name=last_name,
                is_staff=False,      # NOT staff
                is_superuser=False,  # NOT superuser
                is_active=True,
            )
            # Mark password as unusable for SAML-only auth
            user.set_unusable_password()
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Created user: {user.username} ({user.email}) [SSO: {sso_email}]')
            )

        self.stdout.write(f'    - Staff: {user.is_staff}')
        self.stdout.write(f'    - Superuser: {user.is_superuser}')
        self.stdout.write(f'    - Active: {user.is_active}')
        self.stdout.write(f'    - Password: {"Unusable (SAML-only)" if not user.has_usable_password() else "HAS PASSWORD - SECURITY ISSUE!"}')

        # Step 3: Create cohort membership (if not exists)
        self.stdout.write('\n3. Creating Cohort Membership...')
        membership, created = CohortMembership.objects.get_or_create(
            user=user,
            cohort=cohort
        )
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Added {user.username} to {cohort.name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'  ⚠ Membership already exists: {user.username} in {cohort.name}')
            )

        # Step 4: Add to "Cohort Managers" group
        self.stdout.write('\n4. Adding to Cohort Managers Group...')
        try:
            cohort_manager_group = Group.objects.get(name='Cohort Managers')
            user.groups.add(cohort_manager_group)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Added {user.username} to "Cohort Managers" group')
            )
        except Group.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ "Cohort Managers" group not found!')
            )
            self.stdout.write(
                self.style.WARNING('  Run: python manage.py setup_permission_groups')
            )

        # Step 4: Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✓ SCAN USER CREATED SUCCESSFULLY'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\nUser Details:')
        self.stdout.write(f'  Username (JHED): {user.username}')
        self.stdout.write(f'  Email: {user.email}')
        self.stdout.write(f'  SSO Email: {user.sso_email}')
        self.stdout.write(f'  Name: {user.first_name} {user.last_name}')
        self.stdout.write(f'  Permissions: Normal user (no admin)')
        self.stdout.write(f'  Cohort: {cohort.name}')

        self.stdout.write(f'\n\nNext Steps:')
        self.stdout.write(f'  1. Configure Acunetix to use JHED: {jhed}')
        self.stdout.write(f'  2. Run initial scan with user-level permissions')
        self.stdout.write(f'  3. Escalate to admin: python manage.py escalate_scan_user')
        self.stdout.write(f'  4. Run second scan with admin permissions')
        self.stdout.write(f'  5. Deescalate: python manage.py deescalate_scan_user')
        self.stdout.write(f'  6. Remove when done: python manage.py remove_scan_user')
        self.stdout.write('')
