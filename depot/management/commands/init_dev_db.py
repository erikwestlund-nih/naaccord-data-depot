import MySQLdb
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates the specified database in MySQL if it does not already exist."

    def handle(self, *args, **options):
        db_settings = settings.DATABASES["default"]

        server = db_settings.get("HOST", "localhost")
        port = int(db_settings.get("PORT", "3306"))
        username = db_settings.get("USER", "root")
        password = db_settings.get("PASSWORD", "")
        db_name = db_settings.get("NAME", "naaccord")

        cursor = None
        conn = None

        try:
            # Connect to MySQL Server using MySQLdb (from mysqlclient)
            conn = MySQLdb.connect(
                host=server, user=username, passwd=password, port=port
            )
            cursor = conn.cursor()

            # Create the database if it does not exist
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`;")
            conn.commit()

            self.stdout.write(
                self.style.SUCCESS(f"Database '{db_name}' created successfully.")
            )
        except MySQLdb.MySQLError as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
        finally:
            # Safely close cursor and connection if they were created
            if cursor:
                cursor.close()
            if conn:
                conn.close()
