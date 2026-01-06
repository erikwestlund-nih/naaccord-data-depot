"""
Management command to completely refresh the database with test data
Combines database reset, seed data, and test user loading
"""
import time
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from depot.models import Cohort
from django.contrib.auth.models import Group
import subprocess
import sys

User = get_user_model()


class Command(BaseCommand):
    help = 'Complete database refresh with seed data and test users'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--no-docker',
            action='store_true',
            help='Skip Docker service checks (assume they are running)'
        )
        parser.add_argument(
            '--skip-users',
            action='store_true',
            help='Skip loading test users'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )
    
    def handle(self, *args, **options):
        # Confirmation prompt
        if not options['force']:
            self.stdout.write(self.style.WARNING(
                "\n==================================="
                "\nNA-ACCORD Database Refresh"
                "\n==================================="
                "\n\nWARNING: This will DELETE all data!"
            ))
            confirm = input("\nType 'yes' to continue: ")
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR("Aborted."))
                return
        
        # Check Docker services
        if not options['no_docker']:
            self.stdout.write("\n" + self.style.WARNING("Checking Docker services..."))
            try:
                # Check if containers are running
                result = subprocess.run(
                    ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'ps', '--format', 'json'],
                    capture_output=True,
                    text=True
                )
                
                # Start required services if needed
                self.stdout.write("Starting required Docker services...")
                subprocess.run(
                    ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'up', '-d', 'mariadb', 'redis', 'mock-idp'],
                    check=True,
                    capture_output=True
                )
                
                # Wait for services to be ready
                self.stdout.write("Waiting for services to be ready...")
                time.sleep(5)
                
            except subprocess.CalledProcessError as e:
                self.stdout.write(self.style.ERROR(f"Docker error: {e}"))
                self.stdout.write("Please ensure Docker is running and try again.")
                return
        
        # Step 1: Build test environment (reset + seed)
        self.stdout.write("\n" + self.style.WARNING("Step 1: Resetting database and loading seed data..."))
        try:
            call_command('build_test_env')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to build test environment: {e}"))
            return
        
        # Step 2: Load test users
        if not options['skip_users']:
            self.stdout.write("\n" + self.style.WARNING("Step 2: Loading test users..."))
            try:
                call_command('load_test_users', '--clear')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to load test users: {e}"))
                return
        
        # Step 3: Clean up uploads directory
        self.stdout.write("\n" + self.style.WARNING("Step 3: Cleaning uploads directory..."))
        try:
            import os
            import glob
            
            patterns = [
                'storage/uploads/**/*.csv',
                'storage/uploads/**/*.tsv',
                'storage/uploads/**/*.duckdb',
            ]
            
            removed_count = 0
            for pattern in patterns:
                for filepath in glob.glob(pattern, recursive=True):
                    try:
                        os.remove(filepath)
                        removed_count += 1
                    except:
                        pass
            
            if removed_count:
                self.stdout.write(f"Removed {removed_count} uploaded files")
            else:
                self.stdout.write("No uploaded files to remove")
                
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not clean uploads: {e}"))
        
        # Step 4: Verify results
        self.stdout.write("\n" + self.style.SUCCESS("="*50))
        self.stdout.write(self.style.SUCCESS("Database refresh complete!"))
        self.stdout.write(self.style.SUCCESS("="*50))
        
        self.stdout.write("\n" + self.style.WARNING("Verification:"))
        
        # Count objects
        user_count = User.objects.count()
        cohort_count = Cohort.objects.count()
        group_count = Group.objects.count()
        
        self.stdout.write(f"✓ Users: {user_count}")
        self.stdout.write(f"✓ Cohorts: {cohort_count}")
        self.stdout.write(f"✓ Groups: {group_count}")
        
        # Show test accounts
        self.stdout.write("\n" + self.style.WARNING("Test accounts loaded:"))
        test_emails = ['admin@va.gov', 'admin@jh.edu', 'admin@test.edu']
        
        for email in test_emails:
            try:
                user = User.objects.get(email=email)
                self.stdout.write(self.style.SUCCESS(f"  ✓ {email}"))
                
                # Show cohorts
                cohorts = user.cohortmembership_set.all()
                if cohorts:
                    cohort_names = ", ".join([c.cohort.name for c in cohorts])
                    self.stdout.write(f"    Cohorts: {cohort_names}")
                
                # Show groups
                groups = user.groups.all()
                if groups:
                    group_names = ", ".join([g.name for g in groups])
                    self.stdout.write(f"    Groups: {group_names}")
                    
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"  ✗ {email} - NOT FOUND"))
        
        # Show instructions
        self.stdout.write("\n" + self.style.WARNING("To test SAML authentication:"))
        self.stdout.write("  1. Ensure Django is running with: source .env.docker-saml && python manage.py runserver")
        self.stdout.write("  2. Visit http://localhost:8000/sign-in")
        self.stdout.write("  3. Use admin@va.gov or admin@jh.edu")
        self.stdout.write("  4. Password: admin")
        
        # Check Docker status
        if not options['no_docker']:
            self.stdout.write("\n" + self.style.WARNING("Docker services status:"))
            try:
                result = subprocess.run(
                    ['docker', 'compose', '-f', 'docker-compose.dev.yml', 'ps', '--format', 'table {{.Name}}\t{{.Status}}'],
                    capture_output=True,
                    text=True
                )
                self.stdout.write(result.stdout)
            except:
                self.stdout.write("Could not check Docker status")