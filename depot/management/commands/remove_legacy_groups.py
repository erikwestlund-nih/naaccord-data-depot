"""
Management command to remove legacy permission groups from database.

This command:
1. Lists all users in legacy groups
2. Optionally migrates them to new groups
3. Removes legacy groups

Legacy groups being removed:
- Administrators → migrates to NA Accord Administrators
- Data Managers → migrates to NA Accord Administrators
- Researchers → migrates to Cohort Managers
- Coordinators → migrates to Cohort Managers
- Viewers → migrates to Cohort Viewers
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from depot.constants.groups import Groups

User = get_user_model()


class Command(BaseCommand):
    help = 'Remove legacy permission groups and optionally migrate users to new groups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--migrate-users',
            action='store_true',
            help='Migrate users from legacy groups to new groups before removing'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        migrate_users = options['migrate_users']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
            self.stdout.write('')

        # Define migration mapping
        migration_map = {
            Groups.LEGACY_ADMINISTRATORS: Groups.NA_ACCORD_ADMINISTRATORS,
            Groups.LEGACY_DATA_MANAGERS: Groups.NA_ACCORD_ADMINISTRATORS,
            Groups.LEGACY_RESEARCHERS: Groups.COHORT_MANAGERS,
            Groups.LEGACY_COORDINATORS: Groups.COHORT_MANAGERS,
            Groups.LEGACY_VIEWERS: Groups.COHORT_VIEWERS,
        }

        # Check for users in legacy groups
        self.stdout.write('🔍 Checking for users in legacy groups...')
        self.stdout.write('')

        total_users = 0
        groups_to_remove = []

        for legacy_group_name, new_group_name in migration_map.items():
            try:
                legacy_group = Group.objects.get(name=legacy_group_name)
                users = legacy_group.user_set.all()
                user_count = users.count()

                if user_count > 0:
                    total_users += user_count
                    self.stdout.write(f'📋 {legacy_group_name}: {user_count} users')
                    for user in users:
                        self.stdout.write(f'   - {user.email} ({user.username})')

                    if migrate_users:
                        self.stdout.write(f'   → Will migrate to: {new_group_name}')
                    self.stdout.write('')
                else:
                    self.stdout.write(f'✓ {legacy_group_name}: No users (safe to remove)')
                    self.stdout.write('')

                groups_to_remove.append(legacy_group)

            except Group.DoesNotExist:
                self.stdout.write(f'✓ {legacy_group_name}: Already removed')
                self.stdout.write('')

        if total_users > 0 and not migrate_users:
            self.stdout.write(self.style.ERROR('❌ Cannot proceed - users exist in legacy groups'))
            self.stdout.write('')
            self.stdout.write('Options:')
            self.stdout.write('  1. Run with --migrate-users to automatically migrate users to new groups')
            self.stdout.write('  2. Manually reassign users in Django admin first')
            self.stdout.write('')
            return

        # Migrate users if requested
        if migrate_users and not dry_run:
            self.stdout.write('🔄 Migrating users to new groups...')
            self.stdout.write('')

            for legacy_group_name, new_group_name in migration_map.items():
                try:
                    legacy_group = Group.objects.get(name=legacy_group_name)
                    new_group, _ = Group.objects.get_or_create(name=new_group_name)

                    for user in legacy_group.user_set.all():
                        user.groups.remove(legacy_group)
                        user.groups.add(new_group)
                        self.stdout.write(f'  ✓ Migrated {user.email}: {legacy_group_name} → {new_group_name}')

                except Group.DoesNotExist:
                    pass

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ User migration complete'))
            self.stdout.write('')

        # Remove legacy groups
        if not dry_run:
            self.stdout.write('🗑️  Removing legacy groups...')
            self.stdout.write('')

            for group in groups_to_remove:
                group_name = group.name
                group.delete()
                self.stdout.write(f'  ✓ Removed: {group_name}')

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ Legacy groups removed successfully!'))
        else:
            self.stdout.write(self.style.WARNING('Would remove the following legacy groups:'))
            for group in groups_to_remove:
                self.stdout.write(f'  - {group.name}')

        self.stdout.write('')
        self.stdout.write('Current groups (after cleanup):')
        for group_name in [Groups.NA_ACCORD_ADMINISTRATORS, Groups.COHORT_MANAGERS, Groups.COHORT_VIEWERS]:
            try:
                group = Group.objects.get(name=group_name)
                user_count = group.user_set.count()
                self.stdout.write(f'  ✓ {group_name}: {user_count} users')
            except Group.DoesNotExist:
                self.stdout.write(f'  ⚠️  {group_name}: Not created yet (run setup_permission_groups)')
