"""
Model to store extracted patient IDs for each data table file.
This allows us to track which patient IDs are in each file and validate them
against the main patient file.
"""
from django.db import models
from depot.models import BaseModel


class DataTableFilePatientIDs(BaseModel):
    """Store extracted patient IDs for each uploaded file."""

    # Link to the specific file
    data_file = models.ForeignKey(
        'DataTableFile',
        on_delete=models.CASCADE,
        related_name='patient_ids_records'
    )

    # Patient IDs found in this file (stored as JSON array)
    patient_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of patient IDs found in this file"
    )

    # Count for quick access
    patient_count = models.IntegerField(
        default=0,
        help_text="Total number of unique patient IDs"
    )

    # Validation against main patient file
    valid_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Patient IDs that match the main patient file"
    )

    invalid_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Patient IDs not found in the main patient file"
    )

    # Extraction metadata
    extraction_date = models.DateTimeField(
        auto_now_add=True,
        help_text="When the patient IDs were extracted"
    )

    extraction_error = models.TextField(
        blank=True,
        help_text="Error message if extraction failed"
    )

    # Validation metadata
    validated = models.BooleanField(
        default=False,
        help_text="Whether this file has been validated against main patient file"
    )

    validation_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the validation was performed"
    )

    validation_error = models.TextField(
        blank=True,
        help_text="Error message if validation failed"
    )

    # Enhanced validation tracking
    VALIDATION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('extracting', 'Extracting IDs'),
        ('validating', 'Validating'),
        ('valid', 'Valid'),
        ('invalid', 'Invalid IDs Found'),
        ('error', 'Error'),
    ]
    validation_status = models.CharField(
        max_length=20,
        choices=VALIDATION_STATUS_CHOICES,
        default='pending',
        help_text="Current validation status"
    )

    # Invalid ID tracking
    invalid_count = models.IntegerField(
        default=0,
        help_text="Number of invalid patient IDs found"
    )

    # Progress tracking
    progress = models.IntegerField(
        default=0,
        help_text="Validation progress percentage (0-100)"
    )

    # Validation report
    validation_report_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="S3 URL for detailed validation report"
    )

    class Meta:
        verbose_name = "Data Table File Patient IDs"
        verbose_name_plural = "Data Table File Patient IDs"
        indexes = [
            models.Index(fields=['data_file', 'validated']),
            models.Index(fields=['data_file', 'validation_status']),
        ]

    def __str__(self):
        return f"Patient IDs for {self.data_file} ({self.patient_count} IDs)"

    def extract_and_store_ids(self, patient_ids_list):
        """Extract and store patient IDs from a list."""
        import logging
        from django.db import connection, transaction

        logger = logging.getLogger(__name__)
        logger.info(f"About to store {len(patient_ids_list)} patient IDs")

        # Ensure connection is fresh before save - be more aggressive
        try:
            if connection.connection is not None:
                if not connection.is_usable():
                    logger.info("Connection not usable, closing and reconnecting")
                    connection.close()
                    connection.ensure_connection()
                else:
                    logger.info("Connection is usable")
            else:
                logger.info("No existing connection, will create new one")
                connection.ensure_connection()
        except Exception as e:
            logger.warning(f"Connection check failed: {e}, forcing new connection")
            connection.close()
            connection.ensure_connection()

        # Remove duplicates and store
        unique_ids = list(set(patient_ids_list))
        logger.info(f"Processing {len(unique_ids)} unique patient IDs")

        # For very large datasets, we need a different approach
        if len(unique_ids) > 1000000:  # > 1M IDs
            logger.warning(f"Extremely large dataset ({len(unique_ids)} IDs) - storing count only, not full list")
            # For massive datasets, just store the count and a sample
            self.patient_ids = unique_ids[:1000]  # Store first 1000 as sample
            self.patient_count = len(unique_ids)
            self.extraction_error = f"Dataset too large ({len(unique_ids)} IDs) - stored sample of 1000 IDs"

            with transaction.atomic():
                self.save()
                logger.info(f"Saved count ({len(unique_ids)}) and sample (1000 IDs) for massive dataset")
        else:
            # For normal datasets, save the full list
            self.patient_ids = unique_ids
            self.patient_count = len(unique_ids)
            self.extraction_error = ""

            with transaction.atomic():
                self.save()
                logger.info(f"Successfully saved {len(unique_ids)} unique patient IDs")

        return unique_ids

    def validate_against_main(self, main_patient_ids):
        """
        Validate this file's patient IDs against the main patient file.

        Args:
            main_patient_ids: Set or list of valid patient IDs from main file
        """
        from django.utils import timezone
        from django.db import connection

        # Ensure connection is fresh before save
        if connection.connection is not None and not connection.is_usable():
            connection.close()

        main_ids_set = set(main_patient_ids)
        file_ids_set = set(self.patient_ids)

        # Find valid and invalid IDs
        self.valid_ids = list(file_ids_set & main_ids_set)  # Intersection
        self.invalid_ids = list(file_ids_set - main_ids_set)  # Difference

        self.validated = True
        self.validation_date = timezone.now()
        self.validation_error = ""
        self.save()

        return {
            'total': len(self.patient_ids),
            'valid': len(self.valid_ids),
            'invalid': len(self.invalid_ids),
            'invalid_ids': self.invalid_ids[:10]  # Return first 10 invalid IDs for display
        }