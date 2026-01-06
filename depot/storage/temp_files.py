import tempfile
from datetime import timedelta
from pathlib import Path
from django.utils import timezone
from django.conf import settings


class TemporaryStorage:
    def __init__(self, purpose, contents, suffix=".tmp", expires_in_hours=24):
        self.purpose = purpose
        self.contents = contents
        self.suffix = suffix
        self.expires_in_hours = expires_in_hours

    def create(self):
        # Allow for per-purpose folders if you want
        base_dir = settings.UPLOADS_DIR / self.purpose
        base_dir.mkdir(parents=True, exist_ok=True)

        expires_at = timezone.now() + timedelta(hours=self.expires_in_hours)

        with tempfile.NamedTemporaryFile(
            delete=False,
            mode="w",
            suffix=self.suffix,
            prefix=f"{self.purpose}_",
            dir=base_dir,
        ) as temp_file:
            temp_file.write(self.contents)
            temp_file_path = Path(temp_file.name)

        # Return without database tracking since TemporaryFile model was removed
        # PHI tracking will be handled separately through PHIFileTracking
        return {
            "path": temp_file_path,
            "expires_at": expires_at,
            "db_row": None,  # No longer tracking in database
        }
