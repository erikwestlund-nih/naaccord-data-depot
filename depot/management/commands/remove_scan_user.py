"""
Remove scan support user and optionally the Scan Support cohort.

This command:
1. Finds the scan support user (ssuppor2 by default)
2. Removes cohort memberships
3. Deletes the user account
4. Optionally removes the "Scan Support" cohort
5. Documents the removal for audit trail

Usage:
    python manage.py remove_scan_user
    python manage.py remove_scan_user --jhed custom_jhed
    python manage.py remove_scan_user --remove-cohort
    python manage.py remove_scan_user --skip-confirmation
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from depot.models import Cohort, CohortMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Remove scan support user and optionally the Scan Support cohort'

    def add_arguments(self, parser):
        parser.add_argument(
            '--jhed',
            type=str,
            default='ssuppor2',
            help='JHED username for scan support user (default: ssuppor2)'
        )
        parser.add_argument(
            '--remove-cohort',
            action='store_true',
            help='Also remove the "Scan Support" cohort (default: False)'
        )
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt (for automation)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        jhed = options['jhed']
        remove_cohort = options['remove_cohort']
        skip_confirmation = options['skip_confirmation']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('REMOVING SCAN USER'))
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

        # Display current status
        self.stdout.write(f'\nUser to Remove:')
        self.stdout.write(f'  Username: {user.username}')
        self.stdout.write(f'  Email: {user.email}')
        self.stdout.write(f'  Name: {user.first_name} {user.last_name}')
        self.stdout.write(f'  Staff: {user.is_staff}')
        self.stdout.write(f'  Superuser: {user.is_superuser}')

        # Show cohort memberships
        memberships = CohortMembership.objects.filter(user=user)
        if memberships.exists():
            self.stdout.write(f'\nCohort Memberships:')
            for membership in memberships:
                self.stdout.write(f'  - {membership.cohort.name}')
        else:
            self.stdout.write(f'\nNo cohort memberships found')

        # Check for Scan Support cohort
        scan_cohort = None
        try:
            scan_cohort = Cohort.objects.get(name='Scan Support')
            other_members = CohortMembership.objects.filter(
                cohort=scan_cohort
            ).exclude(user=user).count()

            self.stdout.write(f'\n"Scan Support" Cohort:')
            self.stdout.write(f'  Found: Yes')
            self.stdout.write(f'  Other members: {other_members}')

            if remove_cohort:
                if other_members > 0:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⚠ Cannot remove cohort: {other_members} other member(s) exist'
                        )
                    )
                    remove_cohort = False  # Override flag
                else:
                    self.stdout.write(
                        self.style.WARNING('  ⚠ Will be removed (--remove-cohort flag)')
                    )
        except Cohort.DoesNotExist:
            self.stdout.write(f'\n"Scan Support" Cohort: Not found')
            remove_cohort = False

        # Confirmation prompt
        if not skip_confirmation:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('⚠ THIS ACTION CANNOT BE UNDONE'))
            response = input('Type "DELETE" to confirm removal: ')
            if response != 'DELETE':
                self.stdout.write(self.style.ERROR('\n✗ Removal cancelled'))
                return

        # Remove cohort memberships
        self.stdout.write(f'\nRemoving Cohort Memberships...')
        membership_count = memberships.count()
        memberships.delete()
        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Removed {membership_count} membership(s)')
        )

        # Remove user
        self.stdout.write(f'\nRemoving User Account...')
        user_info = f'{user.username} ({user.email})'
        user.force_delete()  # Hard delete (not soft delete)
        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Deleted user: {user_info}')
        )

        # Remove cohort if requested and safe
        if remove_cohort and scan_cohort:
            self.stdout.write(f'\nRemoving "Scan Support" Cohort...')
            scan_cohort.force_delete()  # Hard delete (not soft delete)
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Deleted cohort: Scan Support')
            )

        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✓ SCAN USER REMOVED'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n⚠ SECURITY NOTICE:')
        self.stdout.write(f'  User {jhed} has been permanently removed')
        self.stdout.write(f'  Removed at: {timezone.now().isoformat()}')

        if not remove_cohort and scan_cohort:
            self.stdout.write(f'\nNote:')
            self.stdout.write(f'  "Scan Support" cohort was retained')
            self.stdout.write(f'  To remove it: python manage.py remove_scan_user --remove-cohort')

        self.stdout.write('')
