"""
Disable password authentication for all users (SAML-only authentication).

This command sets all user passwords to unusable, enforcing SAML-only
authentication across the entire application. This is a security requirement
for production environments.

Usage:
    python manage.py disable_all_passwords
    python manage.py disable_all_passwords --skip-confirmation
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class Command(BaseCommand):
    help = 'Disable password authentication for all users (SAML-only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt (use for automation)'
        )

    def handle(self, *args, **options):
        skip_confirmation = options['skip_confirmation']

        self.stdout.write('=' * 70)
        self.stdout.write(self.style.WARNING('DISABLE PASSWORD AUTHENTICATION FOR ALL USERS'))
        self.stdout.write('=' * 70)

        # Find all users with usable passwords or empty passwords
        # Empty passwords are considered usable by Django and need to be set to !
        all_users = User.objects.all()
        users_needing_update = []

        for user in all_users:
            if user.has_usable_password() or user.password == '':
                users_needing_update.append(user)

        count = len(users_needing_update)

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('\n✓ All users already have unusable passwords (SAML-only)')
            )
            return

        self.stdout.write(f'\nFound {count} user(s) needing password updates:')
        for user in users_needing_update[:10]:  # Show first 10
            pwd_status = 'empty' if user.password == '' else 'usable'
            self.stdout.write(f'  - {user.username} ({user.email}) - {pwd_status}')
        if count > 10:
            self.stdout.write(f'  ... and {count - 10} more')

        # Confirmation
        if not skip_confirmation:
            self.stdout.write(
                self.style.WARNING('\n⚠ This will disable password authentication for ALL users!')
            )
            self.stdout.write('  Users will ONLY be able to authenticate via SAML.')
            self.stdout.write('  This action CANNOT be undone without resetting passwords.')
            response = input('\nType "DISABLE" to confirm: ')
            if response != 'DISABLE':
                self.stdout.write(self.style.ERROR('\n✗ Operation cancelled'))
                return

        # Disable passwords
        self.stdout.write('\nDisabling passwords...')
        updated_count = 0
        for user in users_needing_update:
            user.set_unusable_password()
            user.save()
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'  ✓ Disabled passwords for {updated_count} user(s)')
        )

        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('✓ PASSWORD AUTHENTICATION DISABLED'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'\n⚠ SECURITY NOTICE:')
        self.stdout.write(f'  All users now require SAML authentication')
        self.stdout.write(f'  Password login is disabled system-wide')
        self.stdout.write(f'  Users affected: {updated_count}')
        self.stdout.write('')
