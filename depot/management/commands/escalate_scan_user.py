"""
Escalate scan support user to superuser/admin for second security scan.

This command:
1. Finds the scan support user (ssuppor2 by default)
2. Removes from "Cohort Manager" group
3. Adds to "NA Accord Administrator" group
4. Grants superuser and staff permissions
5. Documents the escalation for audit trail

Usage:
    python manage.py escalate_scan_user
    python manage.py escalate_scan_user --jhed custom_jhed
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Escalate scan support user to superuser/admin for second security scan'

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
        self.stdout.write(self.style.WARNING('ESCALATING SCAN USER TO SUPERUSER/ADMIN'))
        self.stdout.write('=' * 70)

        # Find user
        try:
            user = User.objects.get(username=jhed)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'\n✗ User {jhed} not found!')
            )
            self.stdout.write(
                self.style.WARNING('  Run: python manage.py create_scan_user first')
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

        # Check if already escalated
        if user.is_superuser and user.is_staff:
            self.stdout.write(
                self.style.WARNING(f'\n⚠ User {jhed} is already a superuser!')
            )
            self.stdout.write('  No changes made.')
            return

        # Step 1: Remove from "Cohort Managers" group
        self.stdout.write(f'\n1. Removing from Cohort Managers Group...')
        try:
            cohort_manager_group = Group.objects.get(name='Cohort Managers')
            user.groups.remove(cohort_manager_group)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Removed from "Cohort Managers" group')
            )
        except Group.DoesNotExist:
            self.stdout.write(
                self.style.WARNING('  ⚠ "Cohort Managers" group not found (already removed?)')
            )

        # Step 2: Add to "NA Accord Administrators" group
        self.stdout.write(f'\n2. Adding to NA Accord Administrators Group...')
        try:
            admin_group = Group.objects.get(name='NA Accord Administrators')
            user.groups.add(admin_group)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Added to "NA Accord Administrators" group')
            )
        except Group.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ "NA Accord Administrators" group not found!')
            )
            self.stdout.write(
                self.style.WARNING('  Run: python manage.py setup_permission_groups')
            )

        # Step 3: Escalate Django permissions
        self.stdout.write(f'\n3. Escalating Django Permissions...')
        user.is_staff = True
        user.is_superuser = True
        user.save()

        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Granted staff permissions')
        )
        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Granted superuser permissions')
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
        self.stdout.write(self.style.SUCCESS('✓ USER ESCALATED TO SUPERUSER/ADMIN'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n⚠ SECURITY NOTICE:')
        self.stdout.write(f'  User {jhed} now has FULL ADMIN ACCESS')
        self.stdout.write(f'  Escalated at: {timezone.now().isoformat()}')

        self.stdout.write(f'\nNext Steps:')
        self.stdout.write(f'  1. Configure Acunetix for second scan with admin access')
        self.stdout.write(f'  2. Run comprehensive admin-level security scan')
        self.stdout.write(f'  3. When done, IMMEDIATELY deescalate:')
        self.stdout.write(f'     python manage.py deescalate_scan_user')
        self.stdout.write('')
