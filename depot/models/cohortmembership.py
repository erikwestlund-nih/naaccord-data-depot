from django.db import models

from depot import settings
from depot.models import Cohort, BaseModel


class CohortMembership(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
