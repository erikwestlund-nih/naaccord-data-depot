"""
Management command to migrate users from legacy groups to new simplified groups.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.constants.groups import Groups

User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate users from legacy groups to new simplified group structure'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get mapping from constants
        mapping = Groups.get_migration_mapping()
        
        # Show mapping
        self.stdout.write('\nGroup Migration Mapping:')
        for old_group, new_group in mapping.items():
            self.stdout.write(f'  {old_group} → {new_group}')
        
        # Count users by legacy group
        self.stdout.write('\nUsers to migrate:')
        total_users = 0
        for old_group_name in Groups.get_legacy_groups():
            try:
                old_group = Group.objects.get(name=old_group_name)
                user_count = old_group.user_set.count()
                if user_count > 0:
                    self.stdout.write(f'  {old_group_name}: {user_count} users')
                    total_users += user_count
            except Group.DoesNotExist:
                self.stdout.write(f'  {old_group_name}: Group not found (skipping)')
        
        if total_users == 0:
            self.stdout.write(self.style.WARNING('No users found in legacy groups'))
            return
        
        # Confirmation
        if not dry_run and not force:
            confirm = input(f'\nMigrate {total_users} users to new groups? (y/N): ')
            if confirm.lower() != 'y':
                self.stdout.write('Migration cancelled')
                return
        
        # Perform migration
        migrated_count = 0
        for old_group_name, new_group_name in mapping.items():
            try:
                old_group = Group.objects.get(name=old_group_name)
                new_group = Group.objects.get(name=new_group_name)
                
                users = list(old_group.user_set.all())
                if users:
                    self.stdout.write(f'\nMigrating {len(users)} users from {old_group_name} to {new_group_name}...')
                    
                    for user in users:
                        if not dry_run:
                            # Add to new group
                            user.groups.add(new_group)
                            # Remove from old group
                            user.groups.remove(old_group)
                        
                        self.stdout.write(f'  ✓ {user.email}')
                        migrated_count += 1
                
            except Group.DoesNotExist as e:
                self.stdout.write(self.style.ERROR(f'Group not found: {e}'))
                continue
        
        if dry_run:
            self.stdout.write(f'\nDRY RUN: Would migrate {migrated_count} users')
        else:
            self.stdout.write(self.style.SUCCESS(f'\nMigration complete! Migrated {migrated_count} users'))
            
            # Show final status
            self.stdout.write('\nFinal group membership:')
            for group_name in Groups.get_new_groups():
                try:
                    group = Group.objects.get(name=group_name)
                    count = group.user_set.count()
                    self.stdout.write(f'  {group_name}: {count} users')
                except Group.DoesNotExist:
                    self.stdout.write(f'  {group_name}: Group not found')