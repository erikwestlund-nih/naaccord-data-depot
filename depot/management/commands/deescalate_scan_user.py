"""
Deescalate scan support user from superuser/admin back to normal user.

This command:
1. Finds the scan support user (ssuppor2 by default)
2. Removes from "NA Accord Administrator" group
3. Adds back to "Cohort Manager" group
4. Removes superuser and staff permissions
5. Returns user to normal cohort manager role
6. Documents the deescalation for audit trail

Usage:
    python manage.py deescalate_scan_user
    python manage.py deescalate_scan_user --jhed custom_jhed
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Deescalate scan support user from superuser/admin back to normal user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--jhed',
            type=str,
            default='ssuppor2',
            help='JHED username for scan support user (default: ssuppor2)'
        )

    def handle(self, *args, **options):
        jhed = options['jhed']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('DEESCALATING SCAN USER FROM SUPERUSER/ADMIN'))
        self.stdout.write('=' * 70)

        # Find user
        try:
            user = User.objects.get(username=jhed)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'\n✗ User {jhed} not found!')
            )
            self.stdout.write(
                self.style.WARNING('  User may have already been removed')
            )
            return

        # Check current status
        current_groups = list(user.groups.values_list('name', flat=True))
        self.stdout.write(f'\nCurrent Status:')
        self.stdout.write(f'  Username: {user.username}')
        self.stdout.write(f'  Email: {user.email}')
        self.stdout.write(f'  Staff: {user.is_staff}')
        self.stdout.write(f'  Superuser: {user.is_superuser}')
        self.stdout.write(f'  Groups: {", ".join(current_groups) if current_groups else "None"}')

        # Check if already deescalated
        if not user.is_superuser and not user.is_staff:
            self.stdout.write(
                self.style.WARNING(f'\n⚠ User {jhed} is already a normal user!')
            )
            self.stdout.write('  No changes made.')
            return

        # Step 1: Remove from "NA Accord Administrators" group
        self.stdout.write(f'\n1. Removing from NA Accord Administrators Group...')
        try:
            admin_group = Group.objects.get(name='NA Accord Administrators')
            user.groups.remove(admin_group)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Removed from "NA Accord Administrators" group')
            )
        except Group.DoesNotExist:
            self.stdout.write(
                self.style.WARNING('  ⚠ "NA Accord Administrators" group not found (already removed?)')
            )

        # Step 2: Add back to "Cohort Managers" group
        self.stdout.write(f'\n2. Adding back to Cohort Managers Group...')
        try:
            cohort_manager_group = Group.objects.get(name='Cohort Managers')
            user.groups.add(cohort_manager_group)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Added to "Cohort Managers" group')
            )
        except Group.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ "Cohort Managers" group not found!')
            )
            self.stdout.write(
                self.style.WARNING('  Run: python manage.py setup_permission_groups')
            )

        # Step 3: Deescalate Django permissions
        self.stdout.write(f'\n3. Deescalating Django Permissions...')
        user.is_staff = False
        user.is_superuser = False
        user.save()

        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Removed staff permissions')
        )
        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Removed superuser permissions')
        )

        # Verify
        user.refresh_from_db()
        new_groups = list(user.groups.values_list('name', flat=True))
        self.stdout.write(f'\nNew Status:')
        self.stdout.write(f'  Username: {user.username}')
        self.stdout.write(f'  Email: {user.email}')
        self.stdout.write(f'  Staff: {user.is_staff}')
        self.stdout.write(f'  Superuser: {user.is_superuser}')
        self.stdout.write(f'  Groups: {", ".join(new_groups) if new_groups else "None"}')

        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✓ USER DEESCALATED TO NORMAL USER'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n⚠ SECURITY NOTICE:')
        self.stdout.write(f'  User {jhed} now has NORMAL USER ACCESS only')
        self.stdout.write(f'  Deescalated at: {timezone.now().isoformat()}')

        self.stdout.write(f'\nNext Steps:')
        self.stdout.write(f'  1. Verify Acunetix second scan is complete')
        self.stdout.write(f'  2. When done with testing, remove user:')
        self.stdout.write(f'     python manage.py remove_scan_user')
        self.stdout.write('')
