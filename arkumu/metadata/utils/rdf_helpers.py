from typing import Dict, List, Tuple, Optional, Any, Union
from django.db import transaction
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple


def get_or_create_resource(
    uri: Optional[str] = None,
    resource_type: str = ResourceType.IRI,
    source: str = "",
    name: Optional[str] = None,
    value: Optional[str] = None,
    datatype: Optional[str] = None,
    language: Optional[str] = None,
    is_placeholder: bool = False
) -> Tuple[Resource, bool]:
    """
    Get or create a Resource, handling the differences between literal and non-literal resources.
    
    Args:
        uri: URI for non-literal resources
        resource_type: Type of resource (IRI, CLASS, PROPERTY, LITERAL)
        source: Source or origin of this resource
        name: Name of the column, property, or context
        value: Value for literal resources
        datatype: Datatype URI for literal values
        language: Language tag for literals
        is_placeholder: Whether this is a placeholder resource
        
    Returns:
        Tuple of (resource, created) where created is True if a new resource was created
    """
    if resource_type == ResourceType.LITERAL:
        # For literals, we need to check the unique combination of fields
        return Resource.objects.get_or_create(
            resource_type=resource_type,
            value=value,
            name=name,
            source=source,
            datatype=datatype,
            language=language,
            defaults={
                "is_placeholder": is_placeholder
            }
        )
    else:
        # For non-literals, we can use the URI as the unique identifier
        return Resource.objects.get_or_create(
            uri=uri,
            defaults={
                "resource_type": resource_type,
                "source": source,
                "name": name,
                "value": value,
                "is_placeholder": is_placeholder,
                "datatype": datatype,
                "language": language
            }
        )


def create_triple_if_not_exists(
    subject: Resource,
    predicate: Resource,
    object: Resource
) -> Tuple[Triple, bool]:
    """
    Create a triple only if it doesn't already exist.
    
    Args:
        subject: Subject resource
        predicate: Predicate resource
        object: Object resource
        
    Returns:
        Tuple of (triple, created) where created is True if a new triple was created
    """
    # The unique constraint on the model will prevent duplicates,
    # but we can check first to avoid validation errors
    return Triple.objects.get_or_create(
        subject=subject,
        predicate=predicate,
        object=object
    )


def bulk_create_triples(triples_data: List[Dict[str, Resource]]) -> int:
    """
    Bulk create triples with deduplication.
    
    Args:
        triples_data: List of dicts with subject, predicate, object keys
        
    Returns:
        Number of new triples created
    """
    # First check which triples already exist
    existing_triples = set()
    for data in triples_data:
        subject = data['subject']
        predicate = data['predicate']
        object = data['object']
        
        if Triple.objects.filter(
            subject=subject,
            predicate=predicate,
            object=object
        ).exists():
            key = (subject.id, predicate.id, object.id)
            existing_triples.add(key)
    
    # Create only non-existing triples
    new_triples = []
    for data in triples_data:
        subject = data['subject']
        predicate = data['predicate']
        object = data['object']
        
        key = (subject.id, predicate.id, object.id)
        if key not in existing_triples:
            new_triples.append(Triple(
                subject=subject,
                predicate=predicate,
                object=object
            ))
    
    # Bulk create new triples
    if new_triples:
        Triple.objects.bulk_create(new_triples)
    
    return len(new_triples)


def add_semantic_triple(
    subject_uri: str,
    predicate_uri: str,
    object_uri_or_value: str,
    is_object_literal: bool = False,
    source: str = "",
    object_datatype: Optional[str] = None,
    object_language: Optional[str] = None
) -> Tuple[Triple, bool]:
    """
    Add a semantic triple by URIs (or literal value), creating resources if needed.
    
    Args:
        subject_uri: URI of the subject
        predicate_uri: URI of the predicate
        object_uri_or_value: URI of the object or literal value
        is_object_literal: Whether the object is a literal
        source: Source or origin of these resources
        object_datatype: Datatype URI for literal values
        object_language: Language tag for literals
        
    Returns:
        Tuple of (triple, created) where created is True if a new triple was created
    """
    with transaction.atomic():
        # Get or create subject
        subject, _ = get_or_create_resource(
            uri=subject_uri,
            resource_type=ResourceType.IRI,
            source=source
        )
        
        # Get or create predicate
        predicate, _ = get_or_create_resource(
            uri=predicate_uri,
            resource_type=ResourceType.PROPERTY,
            source=source
        )
        
        # Get or create object
        if is_object_literal:
            object, _ = get_or_create_resource(
                resource_type=ResourceType.LITERAL,
                value=object_uri_or_value,
                source=source,
                datatype=object_datatype,
                language=object_language
            )
        else:
            object, _ = get_or_create_resource(
                uri=object_uri_or_value,
                resource_type=ResourceType.IRI,
                source=source
            )
        
        # Create triple if it doesn't exist
        return create_triple_if_not_exists(subject, predicate, object)


def add_class_to_resource(
    resource_uri: str,
    class_uri: str,
    source: str = ""
) -> Tuple[Triple, bool]:
    """
    Add a class relationship to a resource (rdf:type).
    
    Args:
        resource_uri: URI of the resource
        class_uri: URI of the class
        source: Source or origin of these resources
        
    Returns:
        Tuple of (triple, created) where created is True if a new triple was created
    """
    # Get RDF type predicate
    rdf_type, _ = get_or_create_resource(
        uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        resource_type=ResourceType.PROPERTY,
        name="type",
        source=source
    )
    
    # Add the triple
    return add_semantic_triple(
        subject_uri=resource_uri,
        predicate_uri=rdf_type.uri,
        object_uri_or_value=class_uri,
        source=source
    ) 