from django.db import models

from depot.models import BaseModel


class DataFileType(BaseModel):
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0, help_text="Display order for file types")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.label
