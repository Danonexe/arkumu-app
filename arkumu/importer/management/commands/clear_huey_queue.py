"""
Django management command to clear Huey task queue from Redis.

This command is essential when:
1. Cancelling tasks that are stuck in the queue
2. Clearing stale task references after code changes
3. Resolving Huey registry errors
4. Debugging task queue issues

Usage:
    python manage.py clear_huey_queue
    python manage.py clear_huey_queue --confirm
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import redis
from arkumu.importer.services.task_manager import clear_huey_queue_on_shutdown


class Command(BaseCommand):
    help = 'Clear Huey task queue from Redis'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm the operation without prompting'
        )
        parser.add_argument(
            '--queue-name',
            type=str,
            default=None,
            help='Specific queue name to clear (default: all Huey queues)'
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            confirm = input("\nDo you want to clear the Huey queue? [y/N]: ")
            if confirm.lower() not in ['y', 'yes']:
                self.stdout.write("Operation cancelled.")
                return
        
        self.stdout.write("Clearing Huey queue...")
        
        try:
            success = clear_huey_queue_on_shutdown()
            if success:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Huey queue cleared successfully. "
                        "You can now restart your Huey consumer."
                    )
                )
            else:
                self.stderr.write(
                    self.style.ERROR("Failed to clear Huey queue.")
                )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error clearing Huey queue: {e}")
            )