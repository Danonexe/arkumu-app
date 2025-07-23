"""
Integration Layer Services

Functions for creating derived triples that link entities across archives.
These are system-generated triples that represent integration/federation
relationships rather than original archival data.
"""

from typing import Optional
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.utils.rdf_helpers import get_or_create_resource


def create_sameas_link(entity1: Resource, entity2: Resource) -> Optional[Triple]:
    """
    Create a derived owl:sameAs triple linking two entities.
    
    This is used to indicate that two entities from different archives
    represent the same real-world object.
    
    Args:
        entity1: First entity resource
        entity2: Second entity resource
        
    Returns:
        Created Triple instance or None if creation failed
    """
    # Get or create the owl:sameAs property
    owl_sameas, _ = get_or_create_resource(
        uri='http://www.w3.org/2002/07/owl#sameAs',
        resource_type=ResourceType.PROPERTY,
        name='sameAs'
    )
    
    # Create the derived triple
    triple, created = Triple.objects.get_or_create(
        subject=entity1,
        predicate=owl_sameas,
        object=entity2,
        defaults={
            'source': None,  # No source - this is derived
            'is_derived': True
        }
    )
    
    return triple if created else None


def create_skos_mapping(concept1: Resource, concept2: Resource, 
                       mapping_type: str = 'exactMatch') -> Optional[Triple]:
    """
    Create a SKOS mapping relationship between concepts from different vocabularies.
    
    Args:
        concept1: First concept resource
        concept2: Second concept resource
        mapping_type: Type of SKOS mapping (exactMatch, closeMatch, broadMatch, etc.)
        
    Returns:
        Created Triple instance or None if creation failed
    """
    # Map of SKOS mapping properties
    skos_mappings = {
        'exactMatch': 'http://www.w3.org/2004/02/skos/core#exactMatch',
        'closeMatch': 'http://www.w3.org/2004/02/skos/core#closeMatch',
        'broadMatch': 'http://www.w3.org/2004/02/skos/core#broadMatch',
        'narrowMatch': 'http://www.w3.org/2004/02/skos/core#narrowMatch',
        'relatedMatch': 'http://www.w3.org/2004/02/skos/core#relatedMatch'
    }
    
    mapping_uri = skos_mappings.get(mapping_type)
    if not mapping_uri:
        raise ValueError(f"Invalid SKOS mapping type: {mapping_type}")
    
    # Get or create the SKOS mapping property
    skos_property, _ = get_or_create_resource(
        uri=mapping_uri,
        resource_type=ResourceType.PROPERTY,
        name=mapping_type
    )
    
    # Create the derived triple
    triple, created = Triple.objects.get_or_create(
        subject=concept1,
        predicate=skos_property,
        object=concept2,
        defaults={
            'source': None,
            'is_derived': True
        }
    )
    
    return triple if created else None


def link_to_external_authority(local_entity: Resource, 
                              authority_uri: str,
                              link_type: str = 'sameAs') -> Optional[Triple]:
    """
    Link a local entity to an external authority (e.g., Wikidata, VIAF, GND).
    
    Args:
        local_entity: Local entity resource
        authority_uri: URI of the external authority record
        link_type: Type of link (sameAs, seeAlso, etc.)
        
    Returns:
        Created Triple instance or None if creation failed
    """
    # Map of common linking properties
    link_properties = {
        'sameAs': 'http://www.w3.org/2002/07/owl#sameAs',
        'seeAlso': 'http://www.w3.org/2000/01/rdf-schema#seeAlso',
        'isDefinedBy': 'http://www.w3.org/2000/01/rdf-schema#isDefinedBy',
        'isPrimaryTopicOf': 'http://xmlns.com/foaf/0.1/isPrimaryTopicOf'
    }
    
    property_uri = link_properties.get(link_type)
    if not property_uri:
        raise ValueError(f"Invalid link type: {link_type}")
    
    # Get or create the linking property
    link_property, _ = get_or_create_resource(
        uri=property_uri,
        resource_type=ResourceType.PROPERTY,
        name=link_type
    )
    
    # Get or create the external authority resource
    authority_resource, _ = get_or_create_resource(
        uri=authority_uri,
        resource_type=ResourceType.IRI,
        name=authority_uri.split('/')[-1]  # Use last part of URI as name
    )
    
    # Create the derived triple
    triple, created = Triple.objects.get_or_create(
        subject=local_entity,
        predicate=link_property,
        object=authority_resource,
        defaults={
            'source': None,
            'is_derived': True
        }
    )
    
    return triple if created else None