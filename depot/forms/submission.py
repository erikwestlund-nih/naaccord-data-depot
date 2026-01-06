from django import forms
from django.db import transaction
from depot.models import CohortSubmission, ProtocolYear, Cohort


class SubmissionCreateForm(forms.Form):
    protocol_year = forms.ModelChoiceField(
        queryset=ProtocolYear.objects.filter(is_active=True),
        required=True,
        empty_label="Select a protocol year",
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-red-600 sm:text-sm sm:leading-6'
        })
    )
    cohort = forms.ModelChoiceField(
        queryset=Cohort.objects.none(),  # Will be set in __init__
        required=True,
        empty_label="Select a cohort",
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-red-600 sm:text-sm sm:leading-6'
        })
    )
    
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user  # Store user for validation

        # Set protocol year queryset to only active years
        self.fields['protocol_year'].queryset = ProtocolYear.objects.filter(
            is_active=True
        ).order_by('-year', 'name')

        if user:
            # Filter cohorts based on user permissions
            if user.is_superuser or user.is_na_accord_admin():
                # Show all active cohorts for superusers and NA-ACCORD admins
                self.fields['cohort'].queryset = Cohort.objects.filter(
                    status='active'
                ).order_by('name')
            else:
                # Show only user's active cohorts for all other users (including cohort managers)
                from depot.models import CohortMembership
                user_cohorts = CohortMembership.objects.filter(
                    user=user
                ).values_list('cohort', flat=True)
                self.fields['cohort'].queryset = Cohort.objects.filter(
                    id__in=user_cohorts,
                    status='active'
                ).order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        protocol_year = cleaned_data.get('protocol_year')
        cohort = cleaned_data.get('cohort')

        if protocol_year and cohort:
            # Check if submission already exists
            if CohortSubmission.objects.filter(
                protocol_year=protocol_year,
                cohort=cohort
            ).exists():
                raise forms.ValidationError(
                    f"A submission for {cohort.name} already exists for protocol year {protocol_year.name}"
                )

        return cleaned_data

    def clean_cohort(self):
        """Additional validation to ensure user can only select their cohorts."""
        cohort = self.cleaned_data.get('cohort')
        if cohort and hasattr(self, 'user') and self.user:
            # Superusers and NA-ACCORD admins can access all cohorts
            if not (self.user.is_superuser or self.user.is_na_accord_admin()):
                # Check if user is a member of this cohort
                from depot.models import CohortMembership
                if not CohortMembership.objects.filter(
                    user=self.user,
                    cohort=cohort
                ).exists():
                    raise forms.ValidationError(
                        "You don't have permission to create submissions for this cohort."
                    )
        return cohort
    
    def save(self, user):
        """Create the CohortSubmission"""
        with transaction.atomic():
            submission = CohortSubmission.objects.create(
                protocol_year=self.cleaned_data['protocol_year'],
                cohort=self.cleaned_data['cohort'],
                started_by=user,
                status='draft'
            )
            submission.save_revision(user, 'created')
            return submission