"""
Harmonization Bulk Processor

Efficiently processes multiple resources for harmonization using batch operations.
"""

import logging
from typing import List, Dict, Set, Optional
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.harmonization import (
    HarmonizationRule, 
    HarmonizationExecution,
    HarmonizationConflict
)
from .mapping_rules import RuleMatcher, RuleMatchResult
from .alignment_generator import AlignmentGenerator
from .catalog_uri_generator import CatalogUriGenerator

logger = logging.getLogger(__name__)


class ProcessingStats:
    """Statistics container for harmonization processing."""
    
    def __init__(self):
        self.resources_processed = 0
        self.triples_created = 0
        self.conflicts_found = 0
        self.conflicts_resolved = 0
        self.errors = []
        self.start_time = timezone.now()
        self.end_time = None
    
    def add_error(self, error_msg: str, resource_uri: str = None):
        """Add an error to the stats."""
        error_entry = {
            'message': error_msg,
            'timestamp': timezone.now().isoformat(),
            'resource_uri': resource_uri
        }
        self.errors.append(error_entry)
        logger.error(f"Harmonization error: {error_msg} (resource: {resource_uri})")
    
    def finish(self):
        """Mark processing as finished."""
        self.end_time = timezone.now()
    
    @property
    def duration_seconds(self) -> int:
        """Get processing duration in seconds."""
        if self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return int((timezone.now() - self.start_time).total_seconds())


class HarmonizationBulkProcessor:
    """
    Processes multiple resources for harmonization efficiently using batch operations.
    """
    
    def __init__(self,
                 rule_matcher: RuleMatcher = None,
                 alignment_generator: AlignmentGenerator = None,
                 catalog_uri_generator: CatalogUriGenerator = None,
                 batch_size: int = 100):
        """
        Initialize the bulk processor.
        
        Args:
            rule_matcher: Rule matcher instance. Defaults to new instance.
            alignment_generator: Alignment generator instance. Defaults to new instance.
            catalog_uri_generator: Catalog URI generator. Defaults to new instance.
            batch_size: Number of resources to process in each batch
        """
        self.rule_matcher = rule_matcher or RuleMatcher()
        self.alignment_generator = alignment_generator or AlignmentGenerator()
        self.catalog_uri_generator = catalog_uri_generator or CatalogUriGenerator()
        self.batch_size = batch_size
    
    def process_organization(self, 
                           organization,
                           execution: HarmonizationExecution = None,
                           resource_types: List[ResourceType] = None) -> ProcessingStats:
        """
        Process all resources from an organization for harmonization.
        
        Args:
            organization: Organization to process
            execution: Optional HarmonizationExecution to track progress
            resource_types: Optional list of resource types to process
            
        Returns:
            ProcessingStats with processing results
        """
        stats = ProcessingStats()
        
        try:
            # Get resources to process
            resources = self._get_organization_resources(organization, resource_types)
            
            # Process in batches
            for i in range(0, len(resources), self.batch_size):
                batch = resources[i:i + self.batch_size]
                batch_stats = self._process_resource_batch(batch, execution)
                
                # Aggregate stats
                stats.resources_processed += batch_stats.resources_processed
                stats.triples_created += batch_stats.triples_created
                stats.conflicts_found += batch_stats.conflicts_found
                stats.conflicts_resolved += batch_stats.conflicts_resolved
                stats.errors.extend(batch_stats.errors)
                
                logger.info(f"Processed batch {i//self.batch_size + 1} "
                           f"({len(batch)} resources) for {organization.name}")
            
            # Update execution record if provided
            if execution:
                self._update_execution_stats(execution, stats)
            
        except Exception as e:
            stats.add_error(f"Organization processing failed: {str(e)}")
            logger.exception(f"Failed to process organization {organization.name}")
        
        stats.finish()
        return stats
    
    def process_resources(self,
                         resources: List[Resource],
                         execution: HarmonizationExecution = None) -> ProcessingStats:
        """
        Process a specific list of resources for harmonization.
        
        Args:
            resources: List of resources to process
            execution: Optional HarmonizationExecution to track progress
            
        Returns:
            ProcessingStats with processing results
        """
        stats = ProcessingStats()
        
        try:
            # Process in batches
            for i in range(0, len(resources), self.batch_size):
                batch = resources[i:i + self.batch_size]
                batch_stats = self._process_resource_batch(batch, execution)
                
                # Aggregate stats
                stats.resources_processed += batch_stats.resources_processed
                stats.triples_created += batch_stats.triples_created
                stats.conflicts_found += batch_stats.conflicts_found
                stats.conflicts_resolved += batch_stats.conflicts_resolved
                stats.errors.extend(batch_stats.errors)
            
            # Update execution record if provided
            if execution:
                self._update_execution_stats(execution, stats)
                
        except Exception as e:
            stats.add_error(f"Resource processing failed: {str(e)}")
            logger.exception("Failed to process resources")
        
        stats.finish()
        return stats
    
    def _process_resource_batch(self, 
                              resources: List[Resource],
                              execution: HarmonizationExecution = None) -> ProcessingStats:
        """Process a batch of resources."""
        batch_stats = ProcessingStats()
        
        try:
            with transaction.atomic():
                # Find matching rules for all resources in batch
                match_results = self.rule_matcher.find_matching_rules_bulk(resources)
                
                # Separate resolved and conflicted results
                resolved_results = []
                conflicted_results = []
                
                for resource, result in match_results.items():
                    batch_stats.resources_processed += 1
                    
                    if result.has_conflicts:
                        conflicted_results.append(result)
                        batch_stats.conflicts_found += 1
                        
                        # Create conflict record if execution provided
                        if execution:
                            self.rule_matcher.create_conflict_record(result, execution)
                        
                        # Resolve by priority for now
                        result.resolve_by_priority()
                        if result.selected_rule:
                            resolved_results.append((resource, result.selected_rule))
                            batch_stats.conflicts_resolved += 1
                    
                    elif result.selected_rule:
                        resolved_results.append((resource, result.selected_rule))
                
                # Create alignments for resolved results
                if resolved_results:
                    created_triples = self.alignment_generator.bulk_create_alignments(resolved_results)
                    batch_stats.triples_created += len(created_triples)
                    
                    # Update execution with applied rules
                    if execution:
                        applied_rules = [rule for _, rule in resolved_results]
                        execution.rules_applied.add(*applied_rules)
        
        except Exception as e:
            batch_stats.add_error(f"Batch processing failed: {str(e)}")
            logger.exception("Failed to process resource batch")
        
        return batch_stats
    
    def _get_organization_resources(self, 
                                  organization,
                                  resource_types: List[ResourceType] = None) -> List[Resource]:
        """Get resources for an organization."""
        queryset = Resource.objects.filter(source=organization)
        
        if resource_types:
            queryset = queryset.filter(resource_type__in=resource_types)
        
        # Focus on properties and classes primarily
        if not resource_types:
            queryset = queryset.filter(
                resource_type__in=[ResourceType.PROPERTY, ResourceType.CLASS]
            )
        
        return list(queryset.select_related('source'))
    
    def _update_execution_stats(self, 
                              execution: HarmonizationExecution,
                              stats: ProcessingStats):
        """Update execution record with current stats."""
        execution.resources_processed = stats.resources_processed
        execution.triples_created = stats.triples_created
        execution.conflicts_resolved = stats.conflicts_resolved
        execution.errors = stats.errors
        execution.save(update_fields=[
            'resources_processed',
            'triples_created', 
            'conflicts_resolved',
            'errors'
        ])
    
    def cleanup_existing_alignments(self, organization) -> int:
        """
        Remove existing catalog alignments for an organization.
        
        Args:
            organization: Organization to clean up alignments for
            
        Returns:
            Number of alignments removed
        """
        removed_count = 0
        
        try:
            # Find all catalog alignments for this organization
            alignments = self.alignment_generator.get_catalog_alignments_for_organization(organization)
            
            with transaction.atomic():
                for alignment in alignments:
                    if alignment.delete():
                        removed_count += 1
            
            logger.info(f"Cleaned up {removed_count} existing alignments for {organization.name}")
        
        except Exception as e:
            logger.exception(f"Failed to cleanup alignments for {organization.name}: {e}")
        
        return removed_count
    
    def validate_rules_for_organization(self, organization) -> Dict[str, List[str]]:
        """
        Validate all rules for an organization.
        
        Args:
            organization: Organization to validate rules for
            
        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'valid_rules': [],
            'invalid_rules': [],
            'warnings': []
        }
        
        rules = HarmonizationRule.objects.filter(
            source_organization=organization,
            is_active=True
        )
        
        for rule in rules:
            is_valid, message = self.rule_matcher.validate_rule_pattern(rule.source_property_pattern)
            
            if is_valid:
                validation_results['valid_rules'].append(str(rule))
                if message:  # Warning message
                    validation_results['warnings'].append(f"{rule}: {message}")
            else:
                validation_results['invalid_rules'].append(f"{rule}: {message}")
        
        return validation_results