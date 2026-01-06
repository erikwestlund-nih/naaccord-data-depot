"""
Management command to create default superuser and fix the VA superuser bug.
Creates 'ewestlund@jhu.edu' as a member of NAAccord administrators.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from depot.models import User, Cohort, CohortMembership


class Command(BaseCommand):
    help = 'Create default superuser ewestlund@jhu.edu and fix VA superuser bug'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            type=str,
            default='admin123',
            help='Password for the superuser (default: admin123)'
        )
    
    def handle(self, *args, **options):
        password = options['password']
        
        self.stdout.write(self.style.SUCCESS('Creating default superuser and fixing VA bug...'))
        
        # Create default superuser
        email = 'ewestlund@jhu.edu'
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            self.stdout.write(f'User {email} already exists')
        else:
            user = User.objects.create_user(
                email=email,
                username=email,
                first_name='Erik',
                last_name='Westlund',
                password=password,
                is_staff=True,
                is_superuser=True
            )
            self.stdout.write(self.style.SUCCESS(f'Created superuser: {email}'))
        
        # Add to NAAccord Administrators group
        try:
            admin_group = Group.objects.get(name='NAAccord Administrators')
            user.groups.add(admin_group)
            self.stdout.write(f'Added {email} to NAAccord Administrators group')
        except Group.DoesNotExist:
            self.stdout.write(self.style.WARNING('NAAccord Administrators group not found'))
        
        # Add to all cohorts (simple membership)
        cohorts_added = 0
        for cohort in Cohort.objects.all():
            membership, created = CohortMembership.objects.get_or_create(
                user=user,
                cohort=cohort
            )
            if created:
                cohorts_added += 1
        
        self.stdout.write(f'Added {email} as administrator to {cohorts_added} cohorts')
        
        # Fix VA user if it exists and is incorrectly set as superuser
        try:
            va_user = User.objects.get(username='va')
            if va_user.is_superuser:
                va_user.is_superuser = False
                va_user.is_staff = False
                va_user.save()
                self.stdout.write(self.style.SUCCESS('Fixed VA user: removed superuser privileges'))
            else:
                self.stdout.write('VA user is not a superuser (no fix needed)')
        except User.DoesNotExist:
            self.stdout.write('VA user does not exist')
        
        # Report on current superusers
        superusers = User.objects.filter(is_superuser=True)
        self.stdout.write(f'\nCurrent superusers:')
        for su in superusers:
            self.stdout.write(f'  - {su.username} ({su.email})')
        
        self.stdout.write(self.style.SUCCESS('\nDefault superuser setup complete!'))
        self.stdout.write(f'Login credentials:')
        self.stdout.write(f'  Email: {email}')
        self.stdout.write(f'  Password: {password}')
        self.stdout.write(f'  Role: Superuser + NAAccord Administrator')