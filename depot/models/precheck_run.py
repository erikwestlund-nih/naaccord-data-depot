from django.db import models
from django.utils import timezone

from depot.models import BaseModel


class PrecheckRun(BaseModel):
    """
    Temporary container for files validated via the precheck flow.

    Historically this model powered the Upload Precheck + Auditor pipeline.
    It now exists to support Precheck Validation and shares the same table
    (see migration that renames PrecheckRun -> PrecheckRun).
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing_duckdb", "Processing DuckDB"),
        ("processing_notebook", "Processing Notebook"),  # legacy field retained for backwards compatibility
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    uploaded_file = models.ForeignKey(
        "UploadedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Reference to the uploaded file in storage",
    )
    cohort = models.ForeignKey("Cohort", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    data_file_type = models.ForeignKey("DataFileType", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="uploaded_precheck_runs",
    )
    created_by = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="created_precheck_runs",
        help_text="Deprecated - use uploaded_by instead",
    )

    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_path = models.CharField(max_length=500, blank=True, help_text="NAS storage path")

    result = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    celery_task_id = models.CharField(max_length=255, null=True, blank=True)

    def mark_processing_duckdb(self, task_id):
        self.status = "processing_duckdb"
        self.celery_task_id = task_id
        self.save(update_fields=["status", "celery_task_id", "updated_at"])

    def mark_processing_notebook(self):
        self.status = "processing_notebook"
        self.save(update_fields=["status", "updated_at"])

    def mark_completed(self, result):
        self.status = "completed"
        self.completed_at = timezone.now()
        self.result = result
        self.save(update_fields=["status", "completed_at", "result", "updated_at"])

    def mark_failed(self, error):
        self.status = "failed"
        self.completed_at = timezone.now()
        self.error = error
        self.save(update_fields=["status", "completed_at", "error", "updated_at"])

    def mark_notebook_failed(self, error):
        self.status = "failed"
        self.error = error
        self.save(update_fields=["status", "error", "updated_at"])

    def mark_notebook_completed(self):
        self.status = "completed"
        self.save(update_fields=["status", "updated_at"])

    def can_access(self, user):
        if user.is_na_accord_admin():
            return True

        from depot.models import CohortMembership

        return CohortMembership.objects.filter(user=user, cohort=self.cohort).exists()

    class Meta:
        ordering = ["-created_at"]
