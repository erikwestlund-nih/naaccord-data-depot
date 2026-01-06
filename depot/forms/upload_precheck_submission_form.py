from django import forms
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta
import hashlib
import os
import logging

from depot.models import DataFileType, Cohort, PrecheckRun, UploadedFile, UploadType, PHIFileTracking
from depot.storage.temp_files import TemporaryStorage
from depot.storage.manager import StorageManager
from depot.tasks.upload_precheck import process_precheck_run
from depot.validators.file_security import validate_data_file_upload

logger = logging.getLogger(__name__)


class PrecheckRunSubmissionForm(forms.Form):
    data_file_type_id = forms.ChoiceField(
        label="Data File Type",
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-2.5 pl-3 pr-10 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-red-600 sm:text-sm sm:leading-6'
        })
    )
    upload_method = forms.ChoiceField(
        choices=[("upload", "CSV File Upload"), ("paste", "Paste CSV File")],
        label="Upload Method",
    )
    data_content = forms.CharField(
        required=False, widget=forms.Textarea, label="Data Contents"
    )
    uploaded_csv_file = forms.FileField(required=False, label="Upload File")
    cohort_id = forms.ChoiceField(label="Cohort")  # Required field
    temp_file_id = forms.IntegerField(required=False)
    uploaded_file_id = forms.IntegerField(required=False)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        # Superusers see all cohorts, regular users see only their assigned cohorts
        if user.is_superuser:
            self.available_cohorts = Cohort.objects.all()
        else:
            self.available_cohorts = user.cohorts.all()
        data_file_type_choices = [
            (dft.id, dft.label) for dft in DataFileType.objects.all()
        ]
        # Add blank option if user has multiple cohorts
        if self.available_cohorts.count() > 1:
            cohort_choices = [('', 'Select a cohort...')] + [(c.id, c.name) for c in self.available_cohorts]
        else:
            cohort_choices = [(c.id, c.name) for c in self.available_cohorts]

        # Set default values if not passed
        initial = kwargs.setdefault("initial", {})
        # Auto-select cohort if user only has one
        if "cohort_id" not in initial and self.available_cohorts.count() == 1:
            initial["cohort_id"] = self.available_cohorts.first().id
        if "data_file_type_id" not in initial:
            # Default to Patient Record (id=1)
            initial["data_file_type_id"] = 1
        if "upload_method" not in initial:
            initial["upload_method"] = "upload"

        super().__init__(*args, **kwargs)

        # Assign choices *after* init so fields exist, but before validation
        self.fields["data_file_type_id"].choices = data_file_type_choices
        self.fields["cohort_id"].choices = cohort_choices

    def get_initial_data(self):
        return {
            "data_file_type_id": self.initial.get("data_file_type_id"),
            "cohort_id": self.data.get("cohort_id") or self.initial.get("cohort_id"),
            "upload_method": self.data.get("upload_method")
            or self.initial.get("upload_method"),
            "data_content": self.data.get("data_content")
            or self.initial.get("data_content"),
        }

    def handle_submission(self):
        # Get the data file type (no cohort needed anymore)
        data_file_type = DataFileType.objects.get(
            id=self.cleaned_data["data_file_type_id"]
        )
        # Get the selected cohort
        cohort = Cohort.objects.get(id=self.cleaned_data["cohort_id"])
        
        # Prepare the content to save
        content = None
        filename = f"audit_{data_file_type.name}_{self.user.id}.csv"
        
        # Check if we have an uploaded file ID (from AJAX upload)
        if self.cleaned_data.get("uploaded_file_id"):
            # File was already uploaded via AJAX - PHI tracking happens in AJAX endpoint
            uploaded_file = UploadedFile.objects.get(id=self.cleaned_data["uploaded_file_id"])
        else:
            # Handle file upload or paste content
            if self.cleaned_data["upload_method"] == "upload" and self.files.get("uploaded_csv_file"):
                uploaded_file_obj = self.files["uploaded_csv_file"]
                content = uploaded_file_obj.read()
                filename = uploaded_file_obj.name
            elif self.cleaned_data["upload_method"] == "paste" and self.cleaned_data.get("data_content"):
                content = self.cleaned_data["data_content"].encode('utf-8')
            else:
                # No backward compatibility needed for temp files anymore
                raise forms.ValidationError("No file content provided")
            
            # Calculate file hash
            file_hash = hashlib.sha256(content).hexdigest()
            
            # Save to workspace storage (streams to services server when SERVER_ROLE=web)
            storage = StorageManager.get_workspace_storage()
            # Include timestamp in path to prevent overwrites
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')

            # Use a generic path without cohort if cohort is not available
            if cohort:
                cohort_name = cohort.name.replace(' ', '_').replace('/', '-')
                storage_path = f"precheck_runs/{cohort.id}_{cohort_name}/{data_file_type.name}/{timestamp}_{filename}"
            else:
                storage_path = f"precheck_runs/no_cohort/{data_file_type.name}/{timestamp}_{filename}"
            
            saved_path = storage.save(
                path=storage_path,
                content=content,
                content_type='text/csv'
            )

            # Get absolute path for PHI tracking
            absolute_path = storage.get_absolute_path(saved_path)

            # Create PHI tracking record for audit trail
            try:
                file_size = len(content) if isinstance(content, (bytes, str)) else None
                cleanup_time = timezone.now() + timedelta(hours=2)

                logger.info(f"Creating PHI tracking - Size: {file_size}, Cleanup: {cleanup_time}, Hash: {file_hash[:8]}...")

                tracking = PHIFileTracking.objects.create(
                    cohort=cohort,
                    user=self.user,
                    action='file_uploaded_via_stream',
                    file_path=absolute_path,  # Use absolute path
                    file_type='raw_csv',
                    file_size=file_size,
                    file_hash=file_hash,
                    content_object=None,  # UploadedFile not created yet
                    cleanup_required=True,
                    expected_cleanup_by=cleanup_time,
                    server_role=os.environ.get('SERVER_ROLE', 'testing'),
                    metadata={'original_filename': filename, 'relative_path': saved_path}
                )
                logger.info(f"PHI tracking created: ID={tracking.id}, Size={tracking.file_size}, Cleanup={tracking.expected_cleanup_by}")
            except Exception as e:
                # Log error but don't fail the upload
                logger.error(f"Failed to create PHI tracking record: {e}", exc_info=True)

            # Create UploadedFile record
            uploaded_file = UploadedFile.objects.create(
                filename=filename,
                storage_path=saved_path,
                uploader=self.user,
                type=UploadType.VALIDATION_INPUT,
                file_hash=file_hash,
            )

        # Create the upload precheck record
        precheck_run = PrecheckRun.objects.create(
            uploaded_file=uploaded_file,
            cohort=cohort,
            data_file_type=data_file_type,
            created_by=self.user,
            uploaded_by=self.user,
            status="pending",
        )

        # Dispatch Celery task
        # Patient files don't need special handling in upload precheck context
        # The task will handle DuckDB creation and notebook generation internally
        process_precheck_run.delay(precheck_run.id)

        # Return the upload precheck record
        return precheck_run

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("upload_method")
        data_content = cleaned_data.get("data_content")
        file = self.files.get("uploaded_csv_file")
        temp_file_id = cleaned_data.get("temp_file_id")
        uploaded_file_id = cleaned_data.get("uploaded_file_id")

        if method == "paste" and not data_content:
            self.add_error("data_content", "You must provide CSV data.")

        if method == "upload" and not file and not temp_file_id and not uploaded_file_id:
            self.add_error("uploaded_csv_file", "You must upload a file.")

        # Validate uploaded file security for data files (CSV only)
        if method == "upload" and file:
            try:
                validate_data_file_upload(file)
            except forms.ValidationError as e:
                self.add_error("uploaded_csv_file", e.message)

        # Validate cohort selection (required field)
        cohort_id = cleaned_data.get("cohort_id")
        if not cohort_id:
            self.add_error("cohort_id", "Please select a cohort.")
        elif self.user:
            try:
                cohort = Cohort.objects.get(id=cohort_id)
                # Superusers can access any cohort, regular users must be members
                if not self.user.is_superuser and cohort not in self.user.cohorts.all():
                    self.add_error("cohort_id", "You do not have access to the selected cohort.")
            except Cohort.DoesNotExist:
                self.add_error("cohort_id", "Invalid cohort selected.")

        return cleaned_data
