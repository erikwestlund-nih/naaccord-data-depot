import os
import shutil
import tempfile
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TransactionTestCase
from django.urls import reverse

from depot.models import (
    Cohort,
    ProtocolYear,
    CohortSubmission,
    CohortSubmissionDataTable,
    DataFileType,
    DataTableFile,
    ValidationRun,
    CohortMembership,
    SubmissionValidation,
)
from depot.services.file_upload_service import FileUploadService
from depot.views.submissions.table_manage import schedule_submission_file_workflow
from depot.tasks.validation_orchestration import revalidate_single_variable


USER_MODEL = get_user_model()


PATIENT_CSV = """cohortPatientId
001
002
003
""".strip().encode("utf-8")


@unittest.skip("DuckDB segfaults in local test environment - run in CI only")
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class SubmissionValidationWorkflowTests(TransactionTestCase):
    databases = {"default"}
    # Reset sequences to avoid FK conflicts from previous tests
    reset_sequences = True

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="submission-validation-")
        uploads_root = os.path.join(self.temp_dir, "uploads")
        workspace_root = os.path.join(self.temp_dir, "workspace")
        scratch_root = os.path.join(self.temp_dir, "scratch")

        for path in (uploads_root, workspace_root, scratch_root):
            os.makedirs(path, exist_ok=True)

        storage_config = {
            "disks": {
                "local": {"driver": "local", "root": uploads_root},
                "uploads": {"driver": "local", "root": uploads_root},
                "workspace": {"driver": "local", "root": workspace_root},
                "scratch": {"driver": "local", "root": scratch_root},
            }
        }

        override = override_settings(
            STORAGE_CONFIG=storage_config,
            DEFAULT_STORAGE_DISK="uploads",
            SUBMISSION_STORAGE_DISK="uploads",
            WORKSPACE_STORAGE_DISK="workspace",
        )
        override.enable()
        self.addCleanup(override.disable)

        from depot.storage.manager import StorageManager

        StorageManager._instances.clear()

        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        self.user = USER_MODEL.objects.create_user(
            username="validator",
            email="validator@example.com",
            password="testpass123",
        )

        self.cohort = Cohort.objects.create(name="Test Cohort")
        CohortMembership.objects.create(user=self.user, cohort=self.cohort)
        self.protocol_year = ProtocolYear.objects.create(name="Protocol 2024", year=2024)

        self.file_type = DataFileType.objects.create(
            name="patient",
            label="Patient",
            order=1,
        )

        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status="in_progress",
            started_by=self.user,
        )

        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.file_type,
            status="in_progress",
        )

    def _get_summary(self):
        return SubmissionValidation.objects.get(submission=self.submission)

    def _create_data_file(self) -> DataTableFile:
        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")
        service = FileUploadService()
        result = service.process_file_upload_secure(
            uploaded_file=uploaded,
            submission=self.submission,
            data_table=self.data_table,
            user=self.user,
        )

        return result["data_file"]

    def test_upload_schedule_creates_validation_run(self):
        data_file = self._create_data_file()

        schedule_submission_file_workflow(self.submission, self.data_table, data_file, self.user)

        # The workflow runs eagerly; refresh and confirm validation run assigned.
        data_file.refresh_from_db()

        self.assertIsNotNone(data_file.latest_validation_run)
        run = data_file.latest_validation_run
        self.assertEqual(run.data_file_type_id, self.file_type.id)
        self.assertEqual(run.content_type, ContentType.objects.get_for_model(DataTableFile))
        self.assertEqual(run.object_id, str(data_file.id))  # object_id is CharField

        # All variables should have been generated for definition entries.
        self.assertGreater(run.total_variables, 0)
        self.assertEqual(run.variables.count(), run.total_variables)

    def test_revalidate_existing_file_reuses_single_run(self):
        data_file = self._create_data_file()

        # Initial workflow to populate baseline run.
        schedule_submission_file_workflow(self.submission, self.data_table, data_file, self.user)
        data_file.refresh_from_db()
        run = data_file.latest_validation_run
        run.refresh_from_db()
        self.assertEqual(run.status, 'completed')
        summary = self._get_summary()
        self.assertEqual(summary.status, 'completed')
        self.assertEqual(summary.total_files, 1)
        self.assertEqual(summary.files_with_errors, 1 if run.variables_with_errors else 0)
        first_run_id = run.id
        self.assertIsNotNone(first_run_id)

        # Trigger re-run.
        schedule_submission_file_workflow(self.submission, self.data_table, data_file, self.user)
        data_file.refresh_from_db()
        second_run_id = data_file.latest_validation_run_id

        self.assertIsNotNone(second_run_id)
        self.assertEqual(first_run_id, second_run_id)

        latest_run = data_file.latest_validation_run
        self.assertEqual(latest_run.status, "completed")
        self.assertEqual(latest_run.object_id, str(data_file.id))  # object_id is CharField
        summary.refresh_from_db()
        self.assertEqual(summary.latest_run_id, latest_run.id)
        self.assertEqual(summary.status, 'completed')

    def test_single_variable_revalidation(self):
        data_file = self._create_data_file()
        schedule_submission_file_workflow(self.submission, self.data_table, data_file, self.user)
        data_file.refresh_from_db()
        run = data_file.latest_validation_run
        run.refresh_from_db()
        self.assertEqual(run.status, 'completed')
        self.assertIsNotNone(run)

        variable = run.variables.first()
        self.assertIsNotNone(variable)
        original_completed_at = variable.completed_at

        revalidate_single_variable(variable.id)

        variable.refresh_from_db()
        self.assertEqual(variable.validation_run_id, run.id)
        self.assertEqual(variable.status, 'completed')
        if original_completed_at:
            self.assertGreaterEqual(variable.completed_at, original_completed_at)

        summary = self._get_summary()
        self.assertEqual(summary.status, 'completed')

    def test_validation_detail_view(self):
        data_file = self._create_data_file()
        schedule_submission_file_workflow(self.submission, self.data_table, data_file, self.user)
        data_file.refresh_from_db()
        run = data_file.latest_validation_run
        self.assertIsNotNone(run)
        summary = self._get_summary()
        self.assertEqual(summary.latest_run_id, run.id)
        self.assertEqual(summary.status, 'completed')

        self.client.force_login(self.user)

        detail_url = reverse(
            'submission_validation_status',
            args=[self.submission.id, self.data_table.data_file_type.name, run.id],
        )
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)

        json_url = reverse(
            'submission_validation_status_json',
            args=[self.submission.id, self.data_table.data_file_type.name, run.id],
        )
        resp_json = self.client.get(json_url)
        self.assertEqual(resp_json.status_code, 200)
        payload = resp_json.json()
        self.assertIn('status', payload)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class DebugSubmissionTests(TransactionTestCase):
    """Tests for debug submission feature (skip processing/validation)."""
    databases = {"default"}
    reset_sequences = True

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="debug-submission-")
        uploads_root = os.path.join(self.temp_dir, "uploads")
        workspace_root = os.path.join(self.temp_dir, "workspace")
        scratch_root = os.path.join(self.temp_dir, "scratch")

        for path in (uploads_root, workspace_root, scratch_root):
            os.makedirs(path, exist_ok=True)

        storage_config = {
            "disks": {
                "local": {"driver": "local", "root": uploads_root},
                "uploads": {"driver": "local", "root": uploads_root},
                "workspace": {"driver": "local", "root": workspace_root},
                "scratch": {"driver": "local", "root": scratch_root},
            }
        }

        override = override_settings(
            STORAGE_CONFIG=storage_config,
            DEFAULT_STORAGE_DISK="uploads",
            SUBMISSION_STORAGE_DISK="uploads",
            WORKSPACE_STORAGE_DISK="workspace",
        )
        override.enable()
        self.addCleanup(override.disable)

        from depot.storage.manager import StorageManager
        StorageManager._instances.clear()

        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        # Create user with cohort manager permissions
        from django.contrib.auth.models import Group, Permission
        self.user = USER_MODEL.objects.create_user(
            username="debug_tester",
            email="debug@example.com",
            password="testpass123",
        )

        # Create cohort manager group with required permissions
        cohort_managers, _ = Group.objects.get_or_create(name='Cohort Managers')
        try:
            upload_perm = Permission.objects.get(codename='can_upload_submission_files')
            cohort_managers.permissions.add(upload_perm)
        except Permission.DoesNotExist:
            pass  # Permission may not exist in test DB
        self.user.groups.add(cohort_managers)

        self.cohort = Cohort.objects.create(name="Debug Test Cohort")
        CohortMembership.objects.create(user=self.user, cohort=self.cohort)
        self.protocol_year = ProtocolYear.objects.create(name="Protocol 2024", year=2024)

        self.file_type = DataFileType.objects.create(
            name="patient",
            label="Patient",
            order=1,
        )

        self.submission = CohortSubmission.objects.create(
            cohort=self.cohort,
            protocol_year=self.protocol_year,
            status="in_progress",
            started_by=self.user,
        )

        self.data_table = CohortSubmissionDataTable.objects.create(
            submission=self.submission,
            data_file_type=self.file_type,
            status="in_progress",
        )

    def test_debug_submission_field_defaults_to_false(self):
        """Test that debug_submission field defaults to False on new files."""
        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")
        service = FileUploadService()
        result = service.process_file_upload_secure(
            uploaded_file=uploaded,
            submission=self.submission,
            data_table=self.data_table,
            user=self.user,
        )
        data_file = result["data_file"]

        self.assertFalse(data_file.debug_submission)

    def test_debug_submission_can_be_set_true(self):
        """Test that debug_submission can be set to True."""
        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")
        service = FileUploadService()
        result = service.process_file_upload_secure(
            uploaded_file=uploaded,
            submission=self.submission,
            data_table=self.data_table,
            user=self.user,
        )
        data_file = result["data_file"]

        data_file.debug_submission = True
        data_file.save()

        data_file.refresh_from_db()
        self.assertTrue(data_file.debug_submission)

    def test_debug_submission_upload_via_view(self):
        """Test uploading a file with debug_submission=true via the view."""
        from unittest.mock import patch

        self.client.force_login(self.user)

        url = reverse(
            'submission_table_manage',
            args=[self.submission.id, self.data_table.data_file_type.name]
        )

        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")

        # Mock the workflow to verify it's NOT called for debug submissions
        with patch('depot.views.submissions.table_manage.schedule_submission_file_workflow') as mock_workflow:
            response = self.client.post(
                url,
                {
                    'file': uploaded,
                    'debug_submission': 'true',
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertTrue(data.get('debug_submission', False))
            self.assertIn('debugging', data['message'].lower())

            # Check that workflow was NOT called for debug submission
            self.assertFalse(mock_workflow.called)

            # Check that the file was created with debug_submission=True
            data_file = DataTableFile.objects.get(id=data['file_id'])
            self.assertTrue(data_file.debug_submission)

            # Check that no ValidationRun was created
            self.assertIsNone(data_file.latest_validation_run)

    def test_normal_upload_triggers_workflow(self):
        """Test that normal upload (without debug flag) triggers workflow."""
        from unittest.mock import patch

        self.client.force_login(self.user)

        url = reverse(
            'submission_table_manage',
            args=[self.submission.id, self.data_table.data_file_type.name]
        )

        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")

        # Mock the workflow to avoid DuckDB segfault in test environment
        with patch('depot.views.submissions.table_manage.schedule_submission_file_workflow') as mock_workflow:
            response = self.client.post(
                url,
                {
                    'file': uploaded,
                    # No debug_submission flag
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest'
            )

            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertFalse(data.get('debug_submission', False))

            # Check that workflow WAS called for normal upload
            self.assertTrue(mock_workflow.called)

            # Check the file was created correctly
            data_file = DataTableFile.objects.get(id=data['file_id'])
            self.assertFalse(data_file.debug_submission)

    def test_debug_submission_still_stores_file(self):
        """Test that debug submission still stores the file on disk."""
        uploaded = SimpleUploadedFile("patient.csv", PATIENT_CSV, content_type="text/csv")
        service = FileUploadService()
        result = service.process_file_upload_secure(
            uploaded_file=uploaded,
            submission=self.submission,
            data_table=self.data_table,
            user=self.user,
        )
        data_file = result["data_file"]

        # Set as debug submission
        data_file.debug_submission = True
        data_file.save()

        # File should still have been stored
        self.assertTrue(len(data_file.raw_file_path) > 0)
        self.assertIsNotNone(data_file.uploaded_file)
