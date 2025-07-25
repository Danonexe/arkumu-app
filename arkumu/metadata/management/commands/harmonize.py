"""
Django management command for running harmonization processes.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from arkumu.users.models import Organization
from arkumu.metadata.models.resource import ResourceType
from arkumu.metadata.services.harmonization import HarmonizationService

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run harmonization processes for organizations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization', '-o',
            type=str,
            help='Organization code to harmonize (e.g., "khm")'
        )
        
        parser.add_argument(
            '--all-organizations',
            action='store_true',
            help='Harmonize all organizations'
        )
        
        parser.add_argument(
            '--resource-types',
            nargs='+',
            choices=['property', 'class', 'individual'],
            help='Resource types to process (default: property, class)'
        )
        
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Preview harmonization without making changes'
        )
        
        parser.add_argument(
            '--cleanup-existing',
            action='store_true',
            default=True,
            help='Remove existing alignments before creating new ones (default: True)'
        )
        
        parser.add_argument(
            '--no-cleanup',
            action='store_true',
            help='Do not remove existing alignments'
        )
        
        parser.add_argument(
            '--resolve-conflicts',
            choices=['priority', 'recency', 'specificity'],
            default='priority',
            help='Strategy for resolving conflicts (default: priority)'
        )
        
        parser.add_argument(
            '--user',
            type=str,
            help='Username to associate with the execution'
        )
        
        parser.add_argument(
            '--validate-rules',
            action='store_true',
            help='Validate harmonization rules without executing'
        )

    def handle(self, *args, **options):
        # Initialize service
        service = HarmonizationService()
        
        # Get user for execution tracking
        user = None
        if options['user']:
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"User '{options['user']}' not found. Running without user.")
                )
        
        # Determine resource types to process
        resource_types = None
        if options['resource_types']:
            type_mapping = {
                'property': ResourceType.PROPERTY,
                'class': ResourceType.CLASS,
                'individual': ResourceType.INDIVIDUAL
            }
            resource_types = [type_mapping[rt] for rt in options['resource_types']]
        
        # Determine cleanup behavior
        cleanup_existing = options['cleanup_existing'] and not options['no_cleanup']
        
        # Get organizations to process
        organizations = self._get_organizations(options)
        
        if not organizations:
            raise CommandError("No organizations specified or found")
        
        # Process each organization
        for organization in organizations:
            self.stdout.write(f"\nProcessing organization: {organization.name}")
            
            try:
                if options['validate_rules']:
                    self._validate_rules(service, organization)
                elif options['preview']:
                    self._preview_harmonization(service, organization, resource_types)
                else:
                    self._run_harmonization(
                        service, 
                        organization, 
                        user,
                        resource_types,
                        cleanup_existing,
                        options['resolve_conflicts']
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to process {organization.name}: {str(e)}")
                )
                logger.exception(f"Harmonization failed for {organization.name}")
        
        self.stdout.write(self.style.SUCCESS("Harmonization completed"))

    def _get_organizations(self, options):
        """Get organizations to process based on command options."""
        if options['all_organizations']:
            return Organization.objects.filter(is_active=True).order_by('name')
        elif options['organization']:
            try:
                org = Organization.objects.get(code=options['organization'])
                return [org]
            except Organization.DoesNotExist:
                raise CommandError(f"Organization with code '{options['organization']}' not found")
        else:
            raise CommandError("Must specify either --organization or --all-organizations")

    def _validate_rules(self, service, organization):
        """Validate harmonization rules for an organization."""
        self.stdout.write(f"Validating rules for {organization.name}...")
        
        validation_results = service.validate_organization_rules(organization)
        
        self.stdout.write(f"  Valid rules: {len(validation_results['valid_rules'])}")
        self.stdout.write(f"  Invalid rules: {len(validation_results['invalid_rules'])}")
        self.stdout.write(f"  Warnings: {len(validation_results['warnings'])}")
        
        if validation_results['invalid_rules']:
            self.stdout.write(self.style.ERROR("Invalid rules found:"))
            for rule in validation_results['invalid_rules']:
                self.stdout.write(f"    - {rule}")
        
        if validation_results['warnings']:
            self.stdout.write(self.style.WARNING("Warnings:"))
            for warning in validation_results['warnings']:
                self.stdout.write(f"    - {warning}")

    def _preview_harmonization(self, service, organization, resource_types):
        """Preview harmonization for an organization."""
        self.stdout.write(f"Previewing harmonization for {organization.name}...")
        
        preview = service.preview_harmonization(organization, resource_types)
        
        self.stdout.write(f"  Resources analyzed: {preview['total_resources_analyzed']}")
        self.stdout.write(f"  Resources with matches: {preview['resources_with_matches']}")
        self.stdout.write(f"  Resources with conflicts: {preview['resources_with_conflicts']}")
        self.stdout.write(f"  Estimated triples to create: {preview['estimated_triples']}")
        self.stdout.write(f"  Catalog properties to create: {preview['catalog_properties_to_create']}")
        self.stdout.write(f"  Conflicts to resolve: {preview['conflicts_to_resolve']}")
        
        if preview['sample_matches']:
            self.stdout.write("  Sample matches:")
            for match in preview['sample_matches'][:5]:
                conflict_indicator = " (CONFLICT)" if match['has_conflict'] else ""
                self.stdout.write(
                    f"    - {match['resource_name']} -> {', '.join(match['catalog_properties'])}{conflict_indicator}"
                )

    def _run_harmonization(self, service, organization, user, resource_types, cleanup_existing, conflict_strategy):
        """Run harmonization for an organization."""
        self.stdout.write(f"Running harmonization for {organization.name}...")
        
        # Get initial status
        initial_status = service.get_harmonization_status(organization)
        self.stdout.write(f"  Initial aligned resources: {initial_status['aligned_resources']}")
        
        # Run harmonization
        execution = service.harmonize_organization(
            organization=organization,
            user=user,
            execution_mode='manual',
            cleanup_existing=cleanup_existing,
            resource_types=resource_types
        )
        
        # Report results
        self.stdout.write(f"  Execution ID: {execution.id}")
        self.stdout.write(f"  Status: {execution.status}")
        self.stdout.write(f"  Resources processed: {execution.resources_processed}")
        self.stdout.write(f"  Triples created: {execution.triples_created}")
        self.stdout.write(f"  Conflicts resolved: {execution.conflicts_resolved}")
        
        if execution.errors:
            self.stdout.write(self.style.WARNING(f"  Errors: {len(execution.errors)}"))
            for error in execution.errors[:3]:  # Show first 3 errors
                self.stdout.write(f"    - {error.get('message', 'Unknown error')}")
        
        # Resolve any remaining conflicts
        if execution.status == 'completed':
            self.stdout.write("  Resolving remaining conflicts...")
            conflict_stats = service.resolve_conflicts(
                organization=organization,
                execution=execution,
                strategy=conflict_strategy
            )
            
            if conflict_stats['resolved'] > 0 or conflict_stats['skipped'] > 0:
                self.stdout.write(f"    Resolved: {conflict_stats['resolved']}")
                self.stdout.write(f"    Skipped: {conflict_stats['skipped']}")
                self.stdout.write(f"    Failed: {conflict_stats['failed']}")
        
        # Get final status
        final_status = service.get_harmonization_status(organization)
        self.stdout.write(f"  Final aligned resources: {final_status['aligned_resources']}")
        self.stdout.write(f"  Alignment percentage: {final_status['alignment_percentage']:.1f}%")
        
        if execution.duration_seconds:
            self.stdout.write(f"  Duration: {execution.duration_seconds}s")
        
        if execution.status == 'completed':
            self.stdout.write(self.style.SUCCESS(f"✓ Successfully harmonized {organization.name}"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ Harmonization failed for {organization.name}"))