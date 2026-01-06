from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.admin import AdminSite
from django.shortcuts import redirect
from django.urls import reverse
from django import forms
from django.utils.safestring import mark_safe

from depot.models import (
    Cohort,
    CohortMembership,
    ProtocolYear,
    DataFileType,
    Revision,
    CohortSubmission,
    CohortSubmissionDataTable,
    DataTableFile,
    SubmissionActivity,
    PrecheckValidation,
)


class SAMLAdminSite(AdminSite):
    """
    Custom Admin Site that redirects to SAML for authentication.
    No password-based login is shown.

    For emergency access, IT uses Django shell via SSH.
    See: docs/deployment/guides/emergency-access.md
    """

    def has_permission(self, request):
        """
        Override to ensure only staff users can access admin.
        """
        return request.user.is_active and request.user.is_staff

    def get_app_list(self, request, app_label=None):
        """
        Override to hide system/infrastructure apps from staff users.
        Staff users see data management (users, cohorts, submissions).
        Only superusers see system internals (Celery, AXES, etc.).
        """
        app_list = super().get_app_list(request, app_label)

        # Hide only system/infrastructure apps from non-superusers
        if not request.user.is_superuser:
            excluded_apps = ['django_celery_results', 'django_celery_beat', 'axes', 'contenttypes', 'sessions', 'admin']
            app_list = [app for app in app_list if app['app_label'] not in excluded_apps]

        return app_list

    def login(self, request, extra_context=None):
        """
        Override login to redirect to SAML instead of showing password form.
        """
        # If user is already authenticated, proceed to admin
        if request.user.is_authenticated:
            return super().login(request, extra_context)

        # Otherwise, redirect to SAML login with 'next' parameter
        next_url = request.GET.get('next', reverse('admin:index'))
        saml_login_url = reverse('auth.sign_in')
        return redirect(f"{saml_login_url}?next={next_url}")


# Replace default admin site with SAML-enabled site
admin_site = SAMLAdminSite()
admin_site.site_header = "NA-ACCORD Data Depot Administration"
admin_site.site_title = "NA-ACCORD Admin"
admin_site.index_title = "Administration"

# Replace the default site
admin.site = admin_site


class CustomUserCreationForm(forms.ModelForm):
    """Custom user creation form for SSO-only authentication (no password)."""

    class Meta:
        model = get_user_model()
        fields = ('email', 'sso_email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')

    def clean_sso_email(self):
        """Convert empty string to None for unique constraint compatibility."""
        sso_email = self.cleaned_data.get('sso_email')
        return sso_email if sso_email else None

    def save(self, commit=True):
        user = super().save(commit=False)
        # Use email as username
        user.username = user.email
        # Set unusable password since we use SSO
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class CustomUserChangeForm(UserChangeForm):
    """Custom user change form that hides password field."""
    password = None  # Remove password field entirely

    class Meta:
        model = get_user_model()
        fields = '__all__'

    def clean_sso_email(self):
        """Convert empty string to None for unique constraint compatibility."""
        sso_email = self.cleaned_data.get('sso_email')
        return sso_email if sso_email else None


@admin.register(get_user_model(), site=admin_site)
class CustomUserAdmin(UserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = ['email', 'first_name', 'last_name', 'sso_email', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['email', 'first_name', 'last_name', 'sso_email']
    ordering = ['email']

    # No password fields - all authentication is via SAML SSO
    fieldsets = (
        (None, {'fields': ('email',)}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'sso_email')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    # No password fields for adding users - all authentication is via SAML SSO
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'sso_email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active'),
            'description': 'Users authenticate via SAML SSO. No password is required.',
        }),
    )


@admin.register(Cohort, site=admin_site)
class CohortAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'status']
    list_filter = ['type', 'status']
    search_fields = ['name']
    
    def get_queryset(self, request):
        """Filter cohorts based on user permissions."""
        qs = super().get_queryset(request)

        # Staff users (NA Accord staff) can see all cohorts
        # This allows them to manage cohort assignments and data
        if request.user.is_staff:
            return qs

        # Non-staff users only see cohorts they're members of
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(id__in=user_cohorts)
    
    def has_change_permission(self, request, obj=None):
        """Check if user can edit this specific cohort."""
        # Staff users can edit all cohorts
        if request.user.is_staff:
            return super().has_change_permission(request, obj)

        # Non-staff users can only edit their assigned cohorts
        if obj is None:
            return super().has_change_permission(request, obj)

        from depot.models import CohortMembership
        return CohortMembership.objects.filter(
            user=request.user,
            cohort=obj
        ).exists() and super().has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        """Check if user can view this specific cohort."""
        # Staff users can view all cohorts
        if request.user.is_staff:
            return super().has_view_permission(request, obj)

        # Non-staff users can only view their assigned cohorts
        if obj is None:
            return super().has_view_permission(request, obj)

        from depot.models import CohortMembership
        return CohortMembership.objects.filter(
            user=request.user,
            cohort=obj
        ).exists() and super().has_view_permission(request, obj)


class CohortMembershipForm(forms.ModelForm):
    """Custom form for CohortMembership with user group information."""

    class Meta:
        model = CohortMembership
        fields = ['user', 'cohort']

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user')

        # Add warning if user has no groups (will be displayed via messages)
        if user and not user.groups.exists():
            self._no_groups_warning = True
        else:
            self._no_groups_warning = False

        return cleaned_data


@admin.register(CohortMembership, site=admin_site)
class CohortMembershipAdmin(admin.ModelAdmin):
    form = CohortMembershipForm
    list_display = ['user', 'cohort', 'user_groups_display', 'created_at']
    list_filter = ['cohort', 'user__groups']
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name', 'cohort__name']
    autocomplete_fields = ['user', 'cohort']
    date_hierarchy = 'created_at'
    readonly_fields = ['user_groups_info']

    fieldsets = (
        (None, {
            'fields': ('user', 'cohort'),
            'description': '''<div style="background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 4px; margin-bottom: 15px;">
                <strong>⚠️ Important:</strong> For a user to upload files, they must also be added to the
                <strong>Cohort Managers</strong> group. Cohort membership alone does not grant upload permissions.
                <br><br>
                <strong>Steps to enable uploads:</strong>
                <ol style="margin: 8px 0 0 20px;">
                    <li>Create the cohort membership here</li>
                    <li>Go to the user's account in Users</li>
                    <li>Add them to the "Cohort Managers" group</li>
                </ol>
            </div>'''
        }),
        ('User Permission Groups', {
            'fields': ('user_groups_info',),
            'description': 'Current permission groups assigned to this user.',
        }),
    )

    def user_groups_display(self, obj):
        """Display user's groups in list view."""
        groups = obj.user.groups.all()
        if groups:
            return ', '.join(g.name for g in groups)
        return '⚠️ No groups'
    user_groups_display.short_description = 'Permission Groups'
    user_groups_display.admin_order_field = 'user__groups__name'

    @admin.display(description='Current Groups')
    def user_groups_info(self, obj):
        """Display user's groups with status in detail view."""
        if not obj.pk:
            return 'Save the membership first to see user groups.'

        groups = obj.user.groups.all()
        if groups:
            group_list = ', '.join(f'<strong>{g.name}</strong>' for g in groups)
            has_cohort_managers = any(g.name == 'Cohort Managers' for g in groups)
            if has_cohort_managers:
                return mark_safe(f'''<div style="color: #155724; background: #d4edda; padding: 8px; border-radius: 4px;">
                    ✅ {group_list}<br>
                    <em>User can upload files to this cohort.</em>
                </div>''')
            else:
                return mark_safe(f'''<div style="color: #856404; background: #fff3cd; padding: 8px; border-radius: 4px;">
                    ⚠️ {group_list}<br>
                    <em>User is NOT in Cohort Managers group - they cannot upload files.</em>
                </div>''')
        return mark_safe('''<div style="color: #721c24; background: #f8d7da; padding: 8px; border-radius: 4px;">
            ❌ No permission groups assigned<br>
            <em>User cannot upload files. Add them to the "Cohort Managers" group in Users.</em>
        </div>''')

    def save_model(self, request, obj, form, change):
        """Save and warn if user has no groups."""
        super().save_model(request, obj, form, change)

        # Check if user has no groups or missing Cohort Managers
        user = obj.user
        groups = user.groups.all()
        has_cohort_managers = any(g.name == 'Cohort Managers' for g in groups)

        if not groups.exists():
            self.message_user(
                request,
                f'⚠️ Warning: {user.email} has no permission groups. They will NOT be able to upload files. '
                f'Add them to the "Cohort Managers" group to enable uploads.',
                level='warning'
            )
        elif not has_cohort_managers:
            self.message_user(
                request,
                f'⚠️ Warning: {user.email} is not in the "Cohort Managers" group. They can view but NOT upload files.',
                level='warning'
            )

    def get_queryset(self, request):
        """Filter memberships based on user permissions."""
        qs = super().get_queryset(request).select_related('user').prefetch_related('user__groups')

        # Superusers and staff see all memberships
        if request.user.is_superuser or request.user.is_staff:
            return qs

        # Non-staff users only see their own memberships
        return qs.filter(user=request.user)


@admin.register(DataFileType, site=admin_site)
class DataFileTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(ProtocolYear, site=admin_site)
class ProtocolYearAdmin(admin.ModelAdmin):
    pass


# Revision tracking admin
@admin.register(Revision, site=admin_site)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'model_name', 'object_id', 'object_repr']
    list_filter = ['action', 'model_name', 'created_at']
    search_fields = ['user__username', 'object_repr']
    readonly_fields = ['content_type', 'object_id', 'user', 'action', 'changes', 
                       'ip_address', 'user_agent', 'created_at', 'model_name', 'object_repr']
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False  # Revisions are only created programmatically
    
    def has_delete_permission(self, request, obj=None):
        return False  # Revisions cannot be deleted
    
    def has_change_permission(self, request, obj=None):
        return False  # Revisions cannot be edited


# Submission workflow admin
@admin.register(CohortSubmission, site=admin_site)
class CohortSubmissionAdmin(admin.ModelAdmin):
    list_display = ['cohort', 'protocol_year', 'status', 'started_by', 'created_at', 'patient_file_processed', 'signed_off', 'closed_at']
    list_filter = ['status', 'protocol_year', 'cohort', 'patient_file_processed', 'signed_off', 'closed_at']
    search_fields = ['cohort__name']
    readonly_fields = ['created_at', 'updated_at', 'patient_ids', 'signed_off', 'closed_at', 'reopened_at', 'reopened_by']
    autocomplete_fields = ['started_by']  # Makes it easier to select users
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('protocol_year', 'cohort', 'started_by', 'status', 'notes')
        }),
        ('Patient Data', {
            'fields': ('patient_file_processed', 'patient_ids')
        }),
        ('Final Sign-off', {
            'fields': ('final_comments', 'final_acknowledged', 'final_acknowledged_by', 'final_acknowledged_at', 'signed_off', 'closed_at')
        }),
        ('Reopening Information', {
            'fields': ('reopened_reason', 'reopened_by', 'reopened_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Filter submissions based on user's cohort access."""
        qs = super().get_queryset(request)

        # Superusers see everything
        if request.user.is_superuser:
            return qs

        # Staff users see submissions for their assigned cohorts
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(cohort__in=user_cohorts)


# CohortSubmissionFile is deprecated - use DataTableFile instead
# Old admin registration removed


class DataTableFileInline(admin.TabularInline):
    model = DataTableFile
    extra = 0
    fields = ['name', 'original_filename', 'version', 'is_current', 'file_size', 'uploaded_at', 'duckdb_conversion_error']
    readonly_fields = ['version', 'file_size', 'uploaded_at', 'original_filename']
    can_delete = False
    show_change_link = True


@admin.register(DataTableFile, site=admin_site)
class DataTableFileAdmin(admin.ModelAdmin):
    list_display = ['id', 'data_table_link', 'data_file_type', 'version', 'is_current', 'uploaded_by', 'uploaded_at']
    list_filter = ['is_current', 'data_table__data_file_type', 'data_table__submission__cohort']
    search_fields = ['data_table__submission__cohort__name', 'original_filename', 'name', 'uploaded_by__email']
    readonly_fields = ['created_at', 'updated_at', 'version', 'uploaded_at', 'file_hash', 'file_size', 'duckdb_created_at']
    autocomplete_fields = ['uploaded_by']  # Makes it easier to select users
    date_hierarchy = 'uploaded_at'

    fieldsets = (
        ('Data Table Info', {
            'fields': ('data_table', 'version', 'is_current')
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'uploaded_at')
        }),
        ('File Details', {
            'fields': ('name', 'original_filename', 'file_size', 'file_hash', 'uploaded_file')
        }),
        ('Processing', {
            'fields': ('duckdb_conversion_error', 'duckdb_created_at', 'raw_file_path', 'duckdb_file_path')
        }),
        ('Comments', {
            'fields': ('comments',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def data_table_link(self, obj):
        """Clickable link to the data table."""
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:depot_cohortsubmissiondatatable_change', args=[obj.data_table.id])
        return format_html('<a href="{}">{}</a>', url, obj.data_table)
    data_table_link.short_description = 'Data Table'
    data_table_link.admin_order_field = 'data_table'

    def data_file_type(self, obj):
        """Display the data file type from the related data table."""
        return obj.data_table.data_file_type.name if obj.data_table else None
    data_file_type.short_description = 'File Type'
    data_file_type.admin_order_field = 'data_table__data_file_type__name'

    def get_queryset(self, request):
        """Filter files based on user's cohort access."""
        qs = super().get_queryset(request).select_related(
            'data_table__submission__cohort',
            'data_table__data_file_type',
            'uploaded_file'
        )

        # Superusers and staff see everything
        if request.user.is_superuser or request.user.is_staff:
            return qs

        # Filter to user's cohorts
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(data_table__submission__cohort__in=user_cohorts)


@admin.register(CohortSubmissionDataTable, site=admin_site)
class CohortSubmissionDataTableAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission_link', 'data_file_type', 'status', 'signed_off', 'file_count']
    list_filter = ['status', 'signed_off', 'data_file_type', 'submission__cohort']
    search_fields = ['submission__cohort__name', 'data_file_type__name']
    readonly_fields = ['created_at', 'updated_at', 'signed_off_at', 'signed_off_by']
    date_hierarchy = 'created_at'
    inlines = [DataTableFileInline]

    fieldsets = (
        ('Submission Info', {
            'fields': ('submission', 'data_file_type', 'status')
        }),
        ('Sign-off', {
            'fields': ('signed_off', 'signed_off_by', 'signed_off_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def submission_link(self, obj):
        """Clickable link to the submission."""
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:depot_cohortsubmission_change', args=[obj.submission.id])
        return format_html('<a href="{}">{}</a>', url, obj.submission)
    submission_link.short_description = 'Submission'
    submission_link.admin_order_field = 'submission'

    def file_count(self, obj):
        """Display the number of current files."""
        return obj.files.filter(is_current=True).count()
    file_count.short_description = 'Current Files'

    def get_queryset(self, request):
        """Filter tables based on user's cohort access."""
        qs = super().get_queryset(request).select_related(
            'submission__cohort',
            'data_file_type',
            'signed_off_by'
        )

        # Superusers and staff see everything
        if request.user.is_superuser or request.user.is_staff:
            return qs

        # Filter to user's cohorts
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(submission__cohort__in=user_cohorts)


@admin.register(SubmissionActivity, site=admin_site)
class SubmissionActivityAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'submission', 'user', 'activity_type', 'file']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['submission__cohort__name', 'user__username', 'description']
    readonly_fields = ['submission', 'user', 'activity_type', 'description', 'file', 'data', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Activity Info', {
            'fields': ('submission', 'user', 'activity_type', 'description')
        }),
        ('Related File', {
            'fields': ('file',),
            'classes': ('collapse',)
        }),
        ('Additional Data', {
            'fields': ('data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Filter activities based on user's cohort access."""
        qs = super().get_queryset(request)

        # Superusers see everything
        if request.user.is_superuser:
            return qs

        # Filter to user's cohorts
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(submission__cohort__in=user_cohorts)

    def has_add_permission(self, request):
        return False  # Activities are created programmatically
    
    def has_delete_permission(self, request, obj=None):
        return False  # Activities should never be deleted (audit trail)
    
    def has_change_permission(self, request, obj=None):
        return False  # Activities cannot be edited (audit trail)


@admin.register(PrecheckValidation, site=admin_site)
class PrecheckValidationAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'user', 'cohort', 'data_file_type', 'original_filename', 'status', 'progress_percent']
    list_filter = ['status', 'data_file_type', 'cohort', 'created_at']
    search_fields = ['original_filename', 'user__email', 'user__first_name', 'user__last_name', 'cohort__name']
    readonly_fields = [
        'user', 'cohort', 'data_file_type', 'cohort_submission', 'original_filename',
        'file_path', 'file_size', 'file_hash', 'status', 'current_stage', 'progress_percent',
        'encoding', 'has_bom', 'delimiter', 'has_crlf', 'line_count', 'header_column_count',
        'columns', 'total_rows', 'malformed_rows', 'patient_id_results', 'validation_run',
        'validation_errors', 'validation_warnings', 'created_at', 'updated_at', 'completed_at',
        'error_message', 'error_traceback'
    ]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'cohort', 'data_file_type', 'cohort_submission')
        }),
        ('File Details', {
            'fields': ('original_filename', 'file_path', 'file_size', 'file_hash')
        }),
        ('Status', {
            'fields': ('status', 'current_stage', 'progress_percent')
        }),
        ('File Metadata', {
            'fields': ('encoding', 'has_bom', 'delimiter', 'has_crlf', 'line_count', 'header_column_count', 'columns'),
            'classes': ('collapse',)
        }),
        ('Integrity Results', {
            'fields': ('total_rows', 'malformed_rows'),
            'classes': ('collapse',)
        }),
        ('Patient ID Validation', {
            'fields': ('patient_id_results',),
            'classes': ('collapse',)
        }),
        ('Validation Results', {
            'fields': ('validation_run', 'validation_errors', 'validation_warnings'),
            'classes': ('collapse',)
        }),
        ('Error Details', {
            'fields': ('error_message', 'error_traceback'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Filter precheck validations based on user's cohort access."""
        qs = super().get_queryset(request)

        # Superusers see everything
        if request.user.is_superuser:
            return qs

        # Filter to user's cohorts
        from depot.models import CohortMembership
        user_cohorts = CohortMembership.objects.filter(
            user=request.user
        ).values_list('cohort', flat=True)
        return qs.filter(cohort__in=user_cohorts)

    def has_add_permission(self, request):
        return False  # Precheck validations are created via the UI

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser  # Only superusers can delete
