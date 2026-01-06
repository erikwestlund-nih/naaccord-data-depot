from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from depot.models import (
    Cohort,
    CohortMembership,
    CohortSubmission,
    CohortSubmissionDataTable,
    DataTableFile,
    SubmissionActivity,
    PrecheckRun,
    PrecheckValidation,
    Notebook,
)
from depot.constants.groups import Groups


class Command(BaseCommand):
    help = 'Set up permission groups for NA-ACCORD'

    def handle(self, *args, **options):
        self.stdout.write('Setting up permission groups...')

        # Delete legacy groups if they exist
        legacy_groups = Groups.get_legacy_groups()
        deleted_count = 0
        for legacy_group_name in legacy_groups:
            deleted, _ = Group.objects.filter(name=legacy_group_name).delete()
            if deleted > 0:
                deleted_count += 1
                self.stdout.write(f'  🗑️  Deleted legacy group: {legacy_group_name}')

        if deleted_count > 0:
            self.stdout.write(self.style.WARNING(f'Deleted {deleted_count} legacy groups'))
            self.stdout.write('')

        # Create groups - ONLY the new simplified structure
        na_admin_group, _ = Group.objects.get_or_create(name=Groups.NA_ACCORD_ADMINISTRATORS)
        cohort_manager_group, _ = Group.objects.get_or_create(name=Groups.COHORT_MANAGERS)
        cohort_viewer_group, _ = Group.objects.get_or_create(name=Groups.COHORT_VIEWERS)
        
        # Get content types
        user_ct = ContentType.objects.get_for_model(get_user_model())
        cohort_ct = ContentType.objects.get_for_model(Cohort)
        cohort_membership_ct = ContentType.objects.get_for_model(CohortMembership)
        submission_ct = ContentType.objects.get_for_model(CohortSubmission)
        data_table_ct = ContentType.objects.get_for_model(CohortSubmissionDataTable)
        data_table_file_ct = ContentType.objects.get_for_model(DataTableFile)
        activity_ct = ContentType.objects.get_for_model(SubmissionActivity)
        precheck_run_ct = ContentType.objects.get_for_model(PrecheckRun)
        precheck_validation_ct = ContentType.objects.get_for_model(PrecheckValidation)
        notebook_ct = ContentType.objects.get_for_model(Notebook)
        
        # =============================================================
        # NEW GROUP PERMISSIONS
        # =============================================================
        
        # NA Accord Administrators - full access (replaces Administrators + Data Managers)
        na_admin_permissions = Permission.objects.filter(
            content_type__in=[
                user_ct, cohort_ct, cohort_membership_ct,
                submission_ct, data_table_ct, data_table_file_ct, activity_ct,
                precheck_run_ct, precheck_validation_ct, notebook_ct
            ]
        )
        na_admin_group.permissions.set(na_admin_permissions)
        
        # Cohort Manager - can manage users, cohorts, and submissions for their assigned cohorts
        cohort_manager_permissions = Permission.objects.filter(
            content_type__in=[
                user_ct, cohort_ct, cohort_membership_ct,
                submission_ct, data_table_ct, data_table_file_ct, activity_ct,
                precheck_run_ct, precheck_validation_ct, notebook_ct
            ],
            codename__in=[
                # User management
                'view_user',
                'add_user',
                'change_user',
                # Cohort management
                'view_cohort',
                'add_cohort',
                'change_cohort',
                # CohortMembership management
                'view_cohortmembership',
                'add_cohortmembership',
                'change_cohortmembership',
                'delete_cohortmembership',
                # CohortSubmission
                'view_cohortsubmission',
                'add_cohortsubmission',
                'change_cohortsubmission',
                # CohortSubmissionDataTable (new)
                'view_cohortsubmissiondatatable',
                'add_cohortsubmissiondatatable',
                'change_cohortsubmissiondatatable',
                # DataTableFile (new)
                'view_datatablefile',
                'add_datatablefile',
                'change_datatablefile',
                # SubmissionActivity (view only)
                'view_submissionactivity',
                # PrecheckRun
                'view_uploadprecheck',
                'add_uploadprecheck',
                # PrecheckValidation
                'view_precheckvalidation',
                # Notebook
                'view_notebook',
            ]
        )
        cohort_manager_group.permissions.set(cohort_manager_permissions)
        
        # Cohort Viewer - read-only access (replaces Viewers)
        cohort_viewer_permissions = Permission.objects.filter(
            content_type__in=[
                user_ct, cohort_ct, cohort_membership_ct,
                submission_ct, data_table_ct, data_table_file_ct, activity_ct,
                precheck_run_ct, precheck_validation_ct, notebook_ct
            ],
            codename__in=[
                # View-only permissions
                'view_user',
                'view_cohort',
                'view_cohortmembership',
                'view_cohortsubmission',
                'view_cohortsubmissiondatatable',
                'view_datatablefile',
                'view_submissionactivity',
                'view_uploadprecheck',
                'view_precheckvalidation',
                'view_notebook',
            ]
        )
        cohort_viewer_group.permissions.set(cohort_viewer_permissions)

        self.stdout.write(self.style.SUCCESS('✅ Permission groups created successfully!'))
        self.stdout.write('')
        self.stdout.write('Created groups:')
        self.stdout.write(f'  - {Groups.NA_ACCORD_ADMINISTRATORS}: {na_admin_permissions.count()} permissions (full access)')
        self.stdout.write(f'  - {Groups.COHORT_MANAGERS}: {cohort_manager_permissions.count()} permissions (manage assigned cohorts)')
        self.stdout.write(f'  - {Groups.COHORT_VIEWERS}: {cohort_viewer_permissions.count()} permissions (read-only)')