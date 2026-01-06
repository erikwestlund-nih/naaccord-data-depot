from django.apps import AppConfig
import os


class DepotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "depot"

    def ready(self):
        from django.conf import settings

        # Import signals to register them
        from . import signals
        from .audit import observers  # Register universal observer pattern

        directories = [
            settings.STORAGE_DIR,
            settings.UPLOADS_DIR,
            settings.AUDIT_UPLOADS_DIR,
        ]

        for directory in directories:
            os.makedirs(directory, exist_ok=True)
