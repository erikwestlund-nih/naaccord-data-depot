"""
Management command to set up complete development environment.

This command ensures that after a database reset/refresh, all necessary
user associations and permissions are properly configured.

CRITICAL: This solves the recurring issue where users can't see cohorts
in the sidebar after database refresh due to missing CohortMembership records.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from depot.models import Cohort, CohortMembership

User = get_user_model()


class Command(BaseCommand):
    help = 'Set up complete development environment with proper user associations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-db',
            action='store_true',
            help='Reset database before setup',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Setting up complete development environment ==='))

        if options['reset_db']:
            self.stdout.write('Resetting database...')
            from django.core.management import call_command
            call_command('reset_db')
            call_command('migrate')
            call_command('seed_init')

        # 1. Create or get users
        self.setup_users()

        # 2. Set up permission groups
        self.setup_groups()

        # 3. Create cohort memberships (CRITICAL FOR SIDEBAR DISPLAY)
        self.setup_cohort_memberships()

        # 4. Generate some simulation data
        self.setup_simulation_data()

        self.stdout.write(
            self.style.SUCCESS('✅ Complete environment setup finished!')
        )
        self.stdout.write('🎯 All users should now see cohorts in the sidebar')

    def setup_users(self):
        """Create default users for testing."""
        self.stdout.write('Setting up users...')

        # Admin user
        admin_user, created = User.objects.get_or_create(
            email='admin@test.com',
            defaults={
                'username': 'admin',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_superuser': True,
                'is_staff': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(f'✅ Created admin user: {admin_user.email}')
        else:
            self.stdout.write(f'ℹ️  Admin user exists: {admin_user.email}')

        # VA user
        va_user, created = User.objects.get_or_create(
            email='admin@va.gov',
            defaults={
                'username': 'va_admin',
                'first_name': 'VA',
                'last_name': 'Administrator',
                'is_superuser': False,
                'is_staff': True,
            }
        )
        if created:
            va_user.set_password('va123')
            va_user.save()
            self.stdout.write(f'✅ Created VA user: {va_user.email}')
        else:
            self.stdout.write(f'ℹ️  VA user exists: {va_user.email}')

    def setup_groups(self):
        """Set up permission groups."""
        self.stdout.write('Setting up permission groups...')

        # Ensure groups exist
        groups = ['NA Accord Administrators', 'Cohort Managers', 'Cohort Viewers']
        for group_name in groups:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(f'✅ Created group: {group_name}')

        # Assign users to groups
        admin_user = User.objects.get(email='admin@test.com')
        va_user = User.objects.get(email='admin@va.gov')

        na_admin_group = Group.objects.get(name='NA Accord Administrators')
        cohort_manager_group = Group.objects.get(name='Cohort Managers')

        # Add admin to NA Accord Administrators
        admin_user.groups.add(na_admin_group)
        self.stdout.write(f'✅ Added {admin_user.email} to NA Accord Administrators')

        # Add VA user to Cohort Managers
        va_user.groups.add(cohort_manager_group)
        self.stdout.write(f'✅ Added {va_user.email} to Cohort Managers')

    def setup_cohort_memberships(self):
        """
        CRITICAL: Set up cohort memberships for users.

        This is the key step that prevents the "no cohorts visible" issue.
        Without CohortMembership records, users won't see cohorts in the sidebar.

        IMPORTANT: Assigns users to appropriate cohorts based on their email domain.
        """
        self.stdout.write('Setting up cohort memberships (CRITICAL for sidebar display)...')

        users = User.objects.all()
        all_cohorts = list(Cohort.objects.all())

        if not all_cohorts:
            self.stdout.write(self.style.WARNING('⚠️  No cohorts found! Run seed_init first.'))
            return

        memberships_created = 0

        for user in users:
            # Determine appropriate cohorts based on user email/role
            if 'va.gov' in user.email:
                # VA users get VA-specific cohorts only
                user_cohorts = [c for c in all_cohorts if 'VACS' in c.name or 'VA' in c.name]
                if not user_cohorts:
                    # Fallback to VACS if available
                    user_cohorts = [c for c in all_cohorts if 'VACS' in c.name]
                if not user_cohorts:
                    self.stdout.write(f'⚠️  No VA cohorts found for {user.email}')
                    continue
            elif user.is_superuser:
                # Superusers get access to first 10 cohorts for testing
                user_cohorts = all_cohorts[:10]
            else:
                # Regular users get a few test cohorts
                user_cohorts = all_cohorts[:3]

            for cohort in user_cohorts:
                membership, created = CohortMembership.objects.get_or_create(
                    user=user,
                    cohort=cohort
                )
                if created:
                    memberships_created += 1

        self.stdout.write(f'✅ Created {memberships_created} cohort memberships')

        # Verify each user has memberships
        for user in users:
            count = CohortMembership.objects.filter(user=user).count()
            cohort_names = [m.cohort.name for m in CohortMembership.objects.filter(user=user)[:3]]
            self.stdout.write(f'  - {user.email}: {count} cohort memberships ({", ".join(cohort_names)}{"..." if count > 3 else ""})')

    def setup_simulation_data(self):
        """Generate some basic simulation data for testing."""
        self.stdout.write('Setting up simulation data...')

        try:
            from django.core.management import call_command
            call_command('generate_sim_data')
            self.stdout.write('✅ Generated simulation data')
        except Exception as e:
            self.stdout.write(f'⚠️  Could not generate simulation data: {e}')