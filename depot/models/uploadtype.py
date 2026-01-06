from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from enum import Enum

from depot import settings
from depot.gates import member_of


class UploadType(models.TextChoices):
    RAW = "raw", "Raw file"
    VALIDATION_INPUT = "validation_input", "Validation input"
    OTHER = "other", "Other"
    # Add types as needed
