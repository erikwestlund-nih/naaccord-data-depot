from django.db import models

from depot.models import BaseModel


class ProtocolYear(BaseModel):
    name = models.CharField(max_length=255)
    year = models.IntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-year', 'name']

    def __str__(self):
        return self.name