import csv
from django.core.management.base import BaseCommand
from django.apps import apps


class Command(BaseCommand):
    help = "Seed the database with data from a CSV file for a specified model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            type=str,
            required=True,
            help="The model to seed (format: app_label.ModelName)",
        )
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="The CSV file to load data from",
        )

    def handle(self, *args, **kwargs):
        model = kwargs["model"]
        file = kwargs["file"]

        try:
            Model = apps.get_model(model)
            if not Model:
                self.stdout.write(
                    self.style.ERROR(f'Error: Model "{model}" not found.')
                )
                return

            with open(file, mode="r") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    Model.objects.get_or_create(**row)

            self.stdout.write(
                self.style.SUCCESS(f"Successfully seeded data into {model} from {file}")
            )
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Error: File "{file}" not found.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
