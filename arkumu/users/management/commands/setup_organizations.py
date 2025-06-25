"""
Management command to set up predefined organizations.

This command creates Organization objects for all existing org_id codes
used throughout the system, ensuring backward compatibility while enabling
new Organization model features.

Usage:
    python manage.py setup_organizations
    python manage.py setup_organizations --dry-run  # Preview what would be created
    python manage.py setup_organizations --force    # Recreate existing organizations
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from arkumu.users.models import Organization


class Command(BaseCommand):
    help = 'Set up predefined organizations for the Arkumu system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update existing organizations with new data',
        )

    def handle(self, *args, **options):
        # Organization definitions based on the dropdown values in archivist_dashboard.html
        # These match the exact organization names and codes used in the system
        organizations_data = [
            {
                'code': 'rsh',
                'name': 'Robert Schumann Hochschule Düsseldorf',
                'domain': 'rsh-duesseldorf.de',
                'shibboleth_entity_id': '',  # Can be configured later
            },
            {
                'code': 'khm', 
                'name': 'Kunsthochschule für Medien Köln',
                'domain': 'khm.de',
                'shibboleth_entity_id': '',  # Can be configured later
            },
            {
                'code': 'fuk',
                'name': 'Folkwang Universität der Künste',
                'domain': 'folkwang-uni.de',
                'shibboleth_entity_id': '',  # Can be configured later
            },
            {
                'code': 'hmt',
                'name': 'Hochschule für Musik und Tanz Köln',
                'domain': 'hfmt-koeln.de',
                'shibboleth_entity_id': '',  # Can be configured later
            },
            {
                'code': 'det',
                'name': 'Hochschule für Musik Detmold',
                'domain': 'hfm-detmold.de',
                'shibboleth_entity_id': '',  # Can be configured later
            },
        ]

        dry_run = options['dry_run']
        force_update = options['force']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN - No changes will be made\n')
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0

        with transaction.atomic():
            for org_data in organizations_data:
                code = org_data['code']
                
                try:
                    org = Organization.objects.get(code=code)
                    
                    if force_update:
                        # Update existing organization
                        org.name = org_data['name']
                        org.domain = org_data['domain']
                        org.shibboleth_entity_id = org_data['shibboleth_entity_id']
                        org.is_active = True
                        
                        if not dry_run:
                            org.save()
                            
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"{'[DRY RUN] Would update' if dry_run else 'Updated'} organization: {org.name} (code: {code})"
                            )
                        )
                    else:
                        # Organization exists, skip
                        skipped_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Organization '{code}' already exists as '{org.name}' - skipping (use --force to update)"
                            )
                        )
                        
                except Organization.DoesNotExist:
                    # Create new organization
                    if not dry_run:
                        org = Organization.objects.create(**org_data)
                        
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{'[DRY RUN] Would create' if dry_run else 'Created'} organization: {org_data['name']} (code: {code})"
                        )
                    )

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'DRY RUN ' if dry_run else ''}Summary:"
            )
        )
        
        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  - {'Would create' if dry_run else 'Created'}: {created_count} organizations"
                )
            )
        
        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  - {'Would update' if dry_run else 'Updated'}: {updated_count} organizations"
                )
            )
        
        if skipped_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"  - Skipped: {skipped_count} organizations (already exist)"
                )
            )

        total_processed = created_count + updated_count + skipped_count
        self.stdout.write(
            self.style.SUCCESS(
                f"  - Total processed: {total_processed} organizations\n"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Run without --dry-run to actually create the organizations."
                )
            )
        elif created_count > 0 or updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "Organizations are now ready for use with the new user system!"
                )
            )
            self.stdout.write(
                "You can now:"
            )
            self.stdout.write(
                "  - Assign users to organizations via the admin interface"
            )
            self.stdout.write(
                "  - Use organization-scoped data access in views"
            )
            self.stdout.write(
                "  - Configure Shibboleth entity IDs for federated authentication"
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "All organizations already exist and are up to date."
                )
            )