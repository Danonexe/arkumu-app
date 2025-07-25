"""
Alignment Generator

Creates alignment triples between archive-specific properties and catalog-level properties.
Leverages existing integration layer functions for creating derived triples.
"""

from typing import Optional, List
from django.db import transaction
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.models.harmonization import HarmonizationRule
from arkumu.metadata.services.integration import create_skos_mapping, create_sameas_link
from arkumu.metadata.utils.rdf_helpers import get_or_create_resource
from .catalog_uri_generator import CatalogUriGenerator


class AlignmentGenerator:
    """
    Generates alignment triples between archive-specific resources
    and catalog-level resources based on harmonization rules.
    """
    
    def __init__(self, catalog_uri_generator: CatalogUriGenerator = None):
        """
        Initialize the alignment generator.
        
        Args:
            catalog_uri_generator: Generator for catalog URIs. Defaults to new instance.
        """
        self.catalog_uri_generator = catalog_uri_generator or CatalogUriGenerator()
    
    def create_property_alignment(self, 
                                archive_property: Resource,
                                catalog_property_uri: str,
                                catalog_property_label: str,
                                alignment_type: str = "exactMatch") -> Optional[Triple]:
        """
        Create alignment triple between archive property and catalog property.
        
        Args:
            archive_property: The archive-specific property resource
            catalog_property_uri: URI of the catalog-level property
            catalog_property_label: Human-readable label for catalog property  
            alignment_type: Type of alignment (exactMatch, closeMatch, etc.)
            
        Returns:
            Created Triple instance or None if creation failed
        """
        # Get or create the catalog property resource
        catalog_property, _ = get_or_create_resource(
            uri=catalog_property_uri,
            resource_type=ResourceType.PROPERTY,
            name=catalog_property_label
        )
        
        # Create SKOS mapping between the properties
        return create_skos_mapping(
            archive_property, 
            catalog_property, 
            alignment_type
        )
    
    def create_class_alignment(self,
                             archive_class: Resource,
                             catalog_class_uri: str,
                             catalog_class_label: str,
                             alignment_type: str = "exactMatch") -> Optional[Triple]:
        """
        Create alignment triple between archive class and catalog class.
        
        Args:
            archive_class: The archive-specific class resource
            catalog_class_uri: URI of the catalog-level class
            catalog_class_label: Human-readable label for catalog class
            alignment_type: Type of alignment (exactMatch, closeMatch, etc.)
            
        Returns:
            Created Triple instance or None if creation failed
        """
        # Get or create the catalog class resource  
        catalog_class, _ = get_or_create_resource(
            uri=catalog_class_uri,
            resource_type=ResourceType.CLASS,
            name=catalog_class_label
        )
        
        # Create SKOS mapping between the classes
        return create_skos_mapping(
            archive_class,
            catalog_class, 
            alignment_type
        )
    
    def create_instance_alignment(self,
                                archive_instance: Resource,
                                catalog_instance_uri: str,
                                catalog_instance_label: str) -> Optional[Triple]:
        """
        Create owl:sameAs alignment between archive instance and catalog instance.
        
        Args:
            archive_instance: The archive-specific instance resource
            catalog_instance_uri: URI of the catalog-level instance
            catalog_instance_label: Human-readable label for catalog instance
            
        Returns:
            Created Triple instance or None if creation failed
        """
        # Get or create the catalog instance resource
        catalog_instance, _ = get_or_create_resource(
            uri=catalog_instance_uri,
            resource_type=archive_instance.resource_type,  # Same type as archive instance
            name=catalog_instance_label
        )
        
        # Create owl:sameAs link between instances
        return create_sameas_link(archive_instance, catalog_instance)
    
    def apply_harmonization_rule(self, 
                               archive_resource: Resource,
                               rule: HarmonizationRule) -> Optional[Triple]:
        """
        Apply a harmonization rule to create alignment triple.
        
        Args:
            archive_resource: The archive-specific resource to align
            rule: The harmonization rule to apply
            
        Returns:
            Created Triple instance or None if creation failed
        """
        # Map rule mapping types to SKOS mapping types
        mapping_type_map = {
            'exact': 'exactMatch',
            'close': 'closeMatch', 
            'broad': 'broadMatch',
            'narrow': 'narrowMatch'
        }
        
        skos_mapping_type = mapping_type_map.get(rule.mapping_type, 'exactMatch')
        
        # Create alignment based on resource type
        if archive_resource.resource_type == ResourceType.PROPERTY:
            return self.create_property_alignment(
                archive_resource,
                rule.catalog_property_uri,
                rule.catalog_property_label,
                skos_mapping_type
            )
        elif archive_resource.resource_type == ResourceType.CLASS:
            return self.create_class_alignment(
                archive_resource, 
                rule.catalog_property_uri,  # URI works for both properties and classes
                rule.catalog_property_label,
                skos_mapping_type
            )
        else:
            # For instances, use sameAs instead of SKOS mapping
            return self.create_instance_alignment(
                archive_resource,
                rule.catalog_property_uri,
                rule.catalog_property_label
            )
    
    def bulk_create_alignments(self, 
                             alignments: List[tuple]) -> List[Triple]:
        """
        Create multiple alignments in a single transaction for efficiency.
        
        Args:
            alignments: List of (archive_resource, rule) tuples
            
        Returns:
            List of created Triple instances
        """
        created_triples = []
        
        with transaction.atomic():
            for archive_resource, rule in alignments:
                triple = self.apply_harmonization_rule(archive_resource, rule)
                if triple:
                    created_triples.append(triple)
        
        return created_triples
    
    def remove_alignment(self, archive_resource: Resource, catalog_resource: Resource) -> bool:
        """
        Remove alignment between archive resource and catalog resource.
        
        Args:
            archive_resource: The archive-specific resource
            catalog_resource: The catalog-level resource
            
        Returns:
            True if alignment was removed, False otherwise
        """
        # Find and delete triples in both directions
        deleted_count = 0
        
        # Archive -> Catalog alignments
        deleted_count += Triple.objects.filter(
            subject=archive_resource,
            object=catalog_resource,
            is_derived=True
        ).delete()[0]
        
        # Catalog -> Archive alignments (if any)
        deleted_count += Triple.objects.filter(
            subject=catalog_resource,
            object=archive_resource,
            is_derived=True
        ).delete()[0]
        
        return deleted_count > 0
    
    def get_alignments_for_resource(self, resource: Resource) -> List[Triple]:
        """
        Get all alignment triples for a given resource.
        
        Args:
            resource: Resource to find alignments for
            
        Returns:
            List of alignment Triple instances
        """
        # Find triples where resource is subject or object and triple is derived
        from django.db import models
        alignments = Triple.objects.filter(
            is_derived=True
        ).filter(
            models.Q(subject=resource) | models.Q(object=resource)
        ).select_related('subject', 'predicate', 'object')
        
        return list(alignments)
    
    def get_catalog_alignments_for_organization(self, organization) -> List[Triple]:
        """
        Get all catalog alignments for resources from a specific organization.
        
        Args:
            organization: Organization to find alignments for
            
        Returns:
            List of alignment Triple instances
        """
        from django.db import models
        
        # Find derived triples where subject belongs to the organization
        # and object is a catalog resource
        catalog_base_uri = self.catalog_uri_generator.base_uri
        
        alignments = Triple.objects.filter(
            is_derived=True,
            subject__source=organization,
            object__uri__startswith=catalog_base_uri
        ).select_related('subject', 'predicate', 'object')
        
        return list(alignments)