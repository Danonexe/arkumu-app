"""
Management command to clean up orphaned literal resources.

Usage:
    python manage.py cleanup_orphaned_literals
    python manage.py cleanup_orphaned_literals --dry-run
    python manage.py cleanup_orphaned_literals --verbose
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from arkumu.metadata.models import Resource, ResourceType


class Command(BaseCommand):
    help = 'Clean up orphaned literal resources that are no longer referenced by any triples'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed information about orphaned literals',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        # Find orphaned literals using simple ORM query
        orphaned_literals = Resource.objects.filter(
            resource_type=ResourceType.LITERAL,
            object_triples__isnull=True
        )
        
        orphan_count = orphaned_literals.count()
        
        if orphan_count == 0:
            self.stdout.write(
                self.style.SUCCESS('No orphaned literals found. Database is clean.')
            )
            return
        
        self.stdout.write(
            f"Found {orphan_count} orphaned literal(s)"
        )
        
        if verbose:
            # Show sample of orphaned literals
            sample_orphans = orphaned_literals[:10]
            
            self.stdout.write("\nSample of orphaned literals:")
            for orphan in sample_orphans:
                self.stdout.write(f"  - {orphan} (ID: {orphan.id})")
            
            if orphan_count > 10:
                self.stdout.write(f"  ... and {orphan_count - 10} more")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDRY RUN: Would delete {orphan_count} orphaned literal(s)"
                )
            )
        else:
            # Perform cleanup
            self.stdout.write("\nDeleting orphaned literals...")
            
            with transaction.atomic():
                deleted_count, _ = orphaned_literals.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully deleted {deleted_count} orphaned literal(s)"
                )
            )