"""
Management command to load users from CSV files
Works with both test users and production users
"""
import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from depot.models import Cohort, CohortMembership
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Load users from CSV files (test or production)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-dir',
            type=str,
            required=True,
            help='Directory containing CSV files (users.csv, user_groups.csv, cohort_memberships.csv)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing users from same domain before loading'
        )

    def handle(self, *args, **options):
        csv_dir = Path(options['csv_dir'])

        if not csv_dir.exists():
            self.stdout.write(self.style.ERROR(f"CSV directory not found: {csv_dir}"))
            return

        users_csv = csv_dir / 'users.csv'
        if not users_csv.exists():
            # Try alternative names
            users_csv = csv_dir / 'users_production.csv'
            if not users_csv.exists():
                self.stdout.write(self.style.ERROR(f"Users CSV not found in {csv_dir}"))
                self.stdout.write("Looking for: users.csv or users_production.csv")
                return

        # Clear users if requested
        if options['clear']:
            self.clear_users_from_csv(users_csv)

        # Load data in order
        self.load_users(users_csv)

        # Load user groups if file exists
        user_groups_csv = csv_dir / 'user_groups.csv'
        if not user_groups_csv.exists():
            user_groups_csv = csv_dir / 'user_groups_production.csv'
        if user_groups_csv.exists():
            self.load_user_groups(user_groups_csv)
        else:
            self.stdout.write(self.style.WARNING("No user_groups.csv found, skipping group assignments"))

        # Load cohort memberships if file exists
        cohort_memberships_csv = csv_dir / 'cohort_memberships.csv'
        if not cohort_memberships_csv.exists():
            cohort_memberships_csv = csv_dir / 'cohort_memberships_production.csv'
        if cohort_memberships_csv.exists():
            self.load_cohort_memberships(cohort_memberships_csv)
        else:
            self.stdout.write(self.style.WARNING("No cohort_memberships.csv found, skipping cohort memberships"))

        self.stdout.write(self.style.SUCCESS("Users loaded successfully!"))

    def clear_users_from_csv(self, users_csv):
        """Remove users whose emails are in the CSV"""
        with open(users_csv, 'r') as f:
            reader = csv.DictReader(f)
            emails = [row['email'] for row in reader]

        count = User.objects.filter(email__in=emails).delete()[0]
        if count:
            self.stdout.write(f"Deleted {count} existing users")

    def load_users(self, filepath):
        """Load users from CSV"""
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
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
                        'is_staff': row.get('is_staff', 'False').lower() == 'true',
                        'is_superuser': row.get('is_superuser', 'False').lower() == 'true',
                        'sso_email': sso_email,
                    }
                )

                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created user: {row['email']} (sso_email: {sso_email or 'None'})"))
                else:
                    # Update existing user
                    user.username = row['username']
                    user.first_name = row['first_name']
                    user.last_name = row['last_name']
                    user.is_staff = row.get('is_staff', 'False').lower() == 'true'
                    user.is_superuser = row.get('is_superuser', 'False').lower() == 'true'
                    user.sso_email = sso_email
                    user.save()
                    self.stdout.write(f"Updated user: {row['email']} (sso_email: {sso_email or 'None'})")

    def load_user_groups(self, filepath):
        """Load user-group associations from CSV"""
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    user = User.objects.get(email=row['user_email'])
                    group = Group.objects.get(name=row['group_name'])
                    user.groups.add(group)
                    self.stdout.write(f"Added {user.email} to group {group.name}")
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"User not found: {row['user_email']}"))
                except Group.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Group not found: {row['group_name']}"))

    def load_cohort_memberships(self, filepath):
        """Load cohort memberships from CSV"""
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    user = User.objects.get(email=row['user_email'])
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

                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"User not found: {row['user_email']}"))
                except Cohort.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Cohort not found: {row['cohort_id']}"))
                except ValueError:
                    self.stdout.write(self.style.ERROR(f"Invalid cohort ID: {row['cohort_id']}"))
