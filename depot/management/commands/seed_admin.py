from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from depot.models import Cohort, CohortMembership


class Command(BaseCommand):
    help = "Seed admin user with necessary privileges"

    def handle(self, *args, **kwargs):
        User = get_user_model()

        try:
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stderr.write("No superuser found. Please create one first.")
                return

            cohort, created = Cohort.objects.get_or_create(
                name="Test Cohort",
                defaults={"type": "clinical", "status": "active"},
            )

            CohortMembership.objects.get_or_create(user=user, cohort=cohort)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Superuser {user.email} added to cohort '{cohort.name}'"
                )
            )

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
