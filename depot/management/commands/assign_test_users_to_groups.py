import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from depot.constants.groups import Groups

User = get_user_model()


class Command(BaseCommand):
    help = 'Assign users to permission groups (environment-aware: only creates test users in staging)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--environment',
            type=str,
            default=None,
            help='Environment (staging/production, auto-detects if not specified)'
        )

    def handle(self, *args, **options):
        # Detect environment
        environment = options['environment'] or os.environ.get('NAACCORD_ENVIRONMENT', 'staging')

        self.stdout.write(f'Assigning users to groups for environment: {environment}')

        # Get new permission groups (not old/legacy groups)
        try:
            na_admin_group = Group.objects.get(name=Groups.NA_ACCORD_ADMINISTRATORS)
            cohort_manager_group = Group.objects.get(name=Groups.COHORT_MANAGERS)
            cohort_viewer_group = Group.objects.get(name=Groups.COHORT_VIEWERS)
        except Group.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                'Permission groups not found. Run setup_permission_groups first.'
            ))
            return

        # Assign all superusers to NA Accord Administrators
        admin_users = User.objects.filter(is_superuser=True)
        for user in admin_users:
            user.groups.add(na_admin_group)
            self.stdout.write(f'  Added {user.username} to NA Accord Administrators')

        # Only create test users in staging environment
        if environment == 'staging':
            self.create_staging_test_users(na_admin_group, cohort_manager_group, cohort_viewer_group)
        else:
            self.stdout.write(self.style.SUCCESS(
                'Production environment: Skipping test user creation (users loaded from CSV)'
            ))

        # Ensure any existing users with cohort memberships are in appropriate group
        from depot.models import CohortMembership
        cohort_members = CohortMembership.objects.select_related('user').all()
        for membership in cohort_members:
            # Skip if user already has a group
            if membership.user.groups.exists():
                continue

            # Default cohort members to Cohort Managers group
            membership.user.groups.add(cohort_manager_group)
            self.stdout.write(f'  Added {membership.user.username} to Cohort Managers (has cohort membership)')

        self.stdout.write(self.style.SUCCESS('✅ Users assigned to groups successfully!'))

    def create_staging_test_users(self, na_admin_group, cohort_manager_group, cohort_viewer_group):
        """Create test users for staging environment only"""
        self.stdout.write('Creating staging test users...')

        test_users = [
            ('admin1', 'admin1@example.com', na_admin_group, True, False),
            ('manager1', 'manager1@example.com', cohort_manager_group, True, False),
            ('manager2', 'manager2@example.com', cohort_manager_group, True, False),
            ('researcher1', 'researcher1@example.com', cohort_viewer_group, False, False),
            ('researcher2', 'researcher2@example.com', cohort_viewer_group, False, False),
            ('researcher3', 'researcher3@example.com', cohort_viewer_group, False, False),
        ]

        for username, email, group, is_staff, is_superuser in test_users:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': username.capitalize(),
                    'last_name': 'User',
                    'is_active': True,
                    'is_staff': is_staff,
                    'is_superuser': is_superuser,
                }
            )

            if created:
                user.set_password('password123')  # Set a default password for test users
                user.save()
                self.stdout.write(f'  Created test user: {username}')

            # Assign to group
            user.groups.add(group)
            self.stdout.write(f'  Added {username} to {group.name}')