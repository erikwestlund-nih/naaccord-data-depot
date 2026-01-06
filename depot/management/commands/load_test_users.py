"""
Management command to load test users from CSV fixtures
Designed for development/testing with SAML authentication
Environment-aware: loads different users for staging vs production
"""
import csv
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.models import Cohort, CohortMembership
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Load environment-specific users from CSV fixtures for SAML authentication'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixture-dir',
            type=str,
            default=None,
            help='Directory containing CSV fixture files (auto-detects environment if not specified)'
        )
        parser.add_argument(
            '--environment',
            type=str,
            default=None,
            help='Environment to load users for (staging/production, auto-detects if not specified)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing test users before loading'
        )
    
    def handle(self, *args, **options):
        # Detect environment
        environment = options['environment'] or os.environ.get('NAACCORD_ENVIRONMENT', 'staging')

        # Auto-detect fixture directory if not specified
        if options['fixture_dir']:
            fixture_dir = Path(options['fixture_dir'])
            users_file = fixture_dir / 'users.csv'
            user_groups_file = fixture_dir / 'user_groups.csv'
            cohort_memberships_file = fixture_dir / 'cohort_memberships.csv'
        else:
            # Use environment-specific files from resources/data/seed/
            fixture_dir = Path('resources/data/seed')
            users_file = fixture_dir / f'users_{environment}.csv'
            user_groups_file = fixture_dir / f'user_groups_{environment}.csv'
            cohort_memberships_file = fixture_dir / f'cohort_memberships_{environment}.csv'

        # Check if files exist
        if not users_file.exists():
            self.stdout.write(self.style.ERROR(
                f"Users file not found: {users_file}\n"
                f"Environment: {environment}\n"
                f"Expected file: resources/data/seed/users_{environment}.csv"
            ))
            return

        self.stdout.write(self.style.SUCCESS(f"Loading users for environment: {environment}"))
        self.stdout.write(f"Users file: {users_file}")

        # Clear test users if requested
        if options['clear']:
            self.clear_test_users()

        # Load data in order (groups are loaded by setup_permission_groups command)
        self.load_users(users_file)
        self.load_user_groups(user_groups_file)
        self.load_cohort_memberships(cohort_memberships_file)

        self.stdout.write(self.style.SUCCESS(f"✅ {environment.capitalize()} users loaded successfully!"))
    
    def clear_test_users(self):
        """Remove existing test users"""
        test_domains = ['@test.edu', '@va.gov', '@jh.edu', '@ucsd.edu', '@case.edu', '@uab.edu']
        for domain in test_domains:
            count = User.objects.filter(email__endswith=domain).delete()[0]
            if count:
                self.stdout.write(f"Deleted {count} users with domain {domain}")
    
    def load_groups(self, filepath):
        """Load groups from CSV"""
        if not filepath.exists():
            self.stdout.write(self.style.WARNING(f"Groups file not found: {filepath}"))
            return
        
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                group, created = Group.objects.get_or_create(name=row['name'])
                if created:
                    self.stdout.write(f"Created group: {row['name']}")
                else:
                    self.stdout.write(f"Group exists: {row['name']}")
    
    def load_users(self, filepath):
        """Load users from CSV (idempotent - handles duplicates)"""
        if not filepath.exists():
            self.stdout.write(self.style.ERROR(f"Users file not found: {filepath}"))
            return

        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Get sso_email if present (empty string if not provided)
                    sso_email = row.get('sso_email', '').strip()
                    sso_email = sso_email if sso_email else None  # Convert empty string to None

                    # Check if user exists by email
                    user, created = User.objects.get_or_create(
                        email=row['email'],
                        defaults={
                            'username': row['username'],
                            'first_name': row['first_name'],
                            'last_name': row['last_name'],
                            'is_staff': row['is_staff'].lower() == 'true',
                            'is_superuser': row['is_superuser'].lower() == 'true',
                            'sso_email': sso_email,
                        }
                    )

                    if created:
                        # Ensure password is unusable for SAML-only auth
                        user.set_unusable_password()
                        user.save()
                        self.stdout.write(self.style.SUCCESS(f"Created user: {row['email']} (sso_email: {sso_email or 'None'})"))
                    else:
                        # Update existing user
                        user.first_name = row['first_name']
                        user.last_name = row['last_name']
                        user.is_staff = row['is_staff'].lower() == 'true'
                        user.is_superuser = row['is_superuser'].lower() == 'true'
                        user.sso_email = sso_email
                        # Ensure password is unusable for SAML-only auth
                        user.set_unusable_password()
                        user.save()
                        self.stdout.write(f"Updated user: {row['email']} (sso_email: {sso_email or 'None'})")

                except User.MultipleObjectsReturned:
                    # Handle duplicate users - clean up and keep only one
                    self.stdout.write(self.style.WARNING(
                        f"⚠️  Multiple users found for {row['email']}, cleaning up duplicates..."
                    ))
                    users = User.objects.filter(email=row['email']).order_by('id')

                    # Keep the first one, delete the rest
                    primary_user = users.first()
                    duplicate_count = 0
                    for duplicate in users[1:]:
                        self.stdout.write(f"  🗑️  Deleting duplicate user ID {duplicate.id}")
                        duplicate.delete()
                        duplicate_count += 1

                    # Update the remaining user (check username uniqueness)
                    desired_username = row['username']
                    if primary_user.username != desired_username:
                        # Check if username is taken by another user
                        if User.objects.filter(username=desired_username).exclude(id=primary_user.id).exists():
                            self.stdout.write(self.style.WARNING(
                                f"  ⚠️  Username '{desired_username}' already taken, keeping existing username '{primary_user.username}'"
                            ))
                        else:
                            primary_user.username = desired_username

                    primary_user.first_name = row['first_name']
                    primary_user.last_name = row['last_name']
                    primary_user.is_staff = row['is_staff'].lower() == 'true'
                    primary_user.is_superuser = row['is_superuser'].lower() == 'true'
                    primary_user.sso_email = row.get('sso_email', '').strip() or None
                    # Ensure password is unusable for SAML-only auth
                    primary_user.set_unusable_password()
                    primary_user.save()
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ Cleaned up {duplicate_count} duplicate(s) and updated: {row['email']}"
                    ))
    
    def load_user_groups(self, filepath):
        """Load user-group associations from CSV (handles duplicates gracefully)"""
        if not filepath.exists():
            self.stdout.write(self.style.WARNING(f"User groups file not found: {filepath}"))
            return

        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Use filter().first() to handle potential duplicates
                    user = User.objects.filter(email=row['user_email']).first()
                    if not user:
                        self.stdout.write(self.style.WARNING(f"User not found: {row['user_email']}"))
                        continue

                    group = Group.objects.get(name=row['group_name'])
                    user.groups.add(group)
                    self.stdout.write(f"Added {user.email} to group {group.name}")
                except Group.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Group not found: {row['group_name']}"))
    
    def load_cohort_memberships(self, filepath):
        """Load cohort memberships from CSV (handles duplicates gracefully)"""
        if not filepath.exists():
            self.stdout.write(self.style.WARNING(f"Cohort memberships file not found: {filepath}"))
            return

        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Use filter().first() to handle potential duplicates
                    user = User.objects.filter(email=row['user_email']).first()
                    if not user:
                        self.stdout.write(self.style.WARNING(f"User not found: {row['user_email']}"))
                        continue

                    cohort = Cohort.objects.get(id=int(row['cohort_id']))

                    membership, created = CohortMembership.objects.get_or_create(
                        user=user,
                        cohort=cohort
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f"Added {user.email} to cohort {cohort.name}"
                        ))
                    else:
                        self.stdout.write(f"{user.email} already in cohort {cohort.name}")

                except Cohort.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Cohort not found: {row['cohort_id']}"))
                except ValueError:
                    self.stdout.write(self.style.ERROR(f"Invalid cohort ID: {row['cohort_id']}"))