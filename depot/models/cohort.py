from django.db import models

from depot import settings
from depot.models import BaseModel


class CohortStatus(models.TextChoices):
    ACTIVE = "active"
    INACTIVE = "inactive"
    WITHDRAWN = "withdrawn"


class CohortType(models.TextChoices):
    CLINICAL = "clinical"
    INTERVAL = "interval"


class Cohort(BaseModel):
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=255, choices=CohortStatus.choices, default=CohortStatus.ACTIVE
    )
    type = models.CharField(
        max_length=255, choices=CohortType.choices, default=CohortType.CLINICAL
    )

    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CohortMembership",
        related_name="cohorts",
    )

    def __str__(self):
        return self.name
