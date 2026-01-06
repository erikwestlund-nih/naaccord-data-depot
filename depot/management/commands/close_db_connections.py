"""
Management command to close all database connections.

Useful for cleaning up connection leaks, especially after running tests.
"""
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = 'Close all database connections to fix connection leaks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--show-count',
            action='store_true',
            help='Show connection count before closing',
        )

    def handle(self, *args, **options):
        show_count = options.get('show_count', False)

        # Count connections if requested
        if show_count:
            connection_count = len([c for c in connections.all()])
            self.stdout.write(f"Found {connection_count} database connections")

        # Close all connections
        closed_count = 0
        for conn in connections.all():
            if conn.connection is not None:
                conn.close()
                closed_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully closed {closed_count} database connection(s)"
            )
        )

        # Verify all connections are closed
        remaining = len([c for c in connections.all() if c.connection is not None])
        if remaining > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: {remaining} connection(s) still open"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("All database connections closed")
            )
