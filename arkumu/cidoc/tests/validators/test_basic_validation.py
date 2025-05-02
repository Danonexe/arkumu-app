import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from pathlib import Path
import os

from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.validators import (
    validate_cidoc_class,
    validate_cidoc_entity,
    validate_cidoc_relationship
)


@pytest.mark.django_db
def test_validate_cidoc_entity_real(loaded_cidoc_data):
    """Test validation of CIDOC entity class IDs with real database models"""
    # Print all available classes for debugging
    all_classes = list(CIDOCClass.objects.values_list('class_id', flat=True))
    print(f"\nAll available classes in database: {all_classes[:10]}")
    
    # Get the first available class or create one if none exists
    first_class = CIDOCClass.objects.first()
    if not first_class:
        # Create a test class
        first_class = CIDOCClass.objects.create(
            class_id='E1_CRM_Entity',
            label='Test CRM Entity',
            description='Test class for entity validation'
        )
        print(f"Created test class: {first_class.class_id}")
    else:
        print(f"Using first available class: {first_class.class_id}")
    
    # Test with a valid class ID that exists in the database
    validate_cidoc_entity(first_class.class_id)
    
    # Test with empty class ID
    with pytest.raises(ValidationError, match='Entity must have a CIDOC-CRM class'):
        validate_cidoc_entity('')
        
    # Test with a non-existent class ID
    with pytest.raises(ValidationError, match='Invalid CIDOC-CRM class'):
        validate_cidoc_entity('E999_NonExistentClass')


@pytest.mark.django_db
def test_validate_cidoc_class_real(loaded_cidoc_data):
    """Test CIDOC class validation using real database models"""
    # Find a specific class and its parent
    all_classes = list(CIDOCClass.objects.values_list('class_id', flat=True))
    print(f"\nAll available classes: {all_classes[:10]}")
    
    person = CIDOCClass.objects.first()
    if not person:
        # Create a test class hierarchy
        parent = CIDOCClass.objects.create(
            class_id='E77_Persistent_Item',
            label='Persistent Item',
            description='Test parent class'
        )
        person = CIDOCClass.objects.create(
            class_id='E39_Actor',
            label='Actor',
            description='Test child class'
        )
        person.parent_classes.add(parent)
        print(f"Created test class hierarchy: {person.class_id} is a {parent.class_id}")
    
    print(f"Using class: {person.class_id}")
    
    # Get its parents
    parent_classes = list(person.parent_classes.all())
    
    # Test with direct match
    validate_cidoc_class(person, person.class_id)
    
    if parent_classes:
        # Test with parent class
        parent = parent_classes[0]
        validate_cidoc_class(person, parent.class_id)
        print(f"\nValidated {person.class_id} as a {parent.class_id}")
        
        # Test with an unrelated class
        unrelated_class = CIDOCClass.objects.exclude(
            id__in=[person.id] + [p.id for p in parent_classes]
        ).first()
        
        if unrelated_class:
            with pytest.raises(ValidationError, match='Invalid CIDOC class'):
                validate_cidoc_class(person, unrelated_class.class_id)
    else:
        # Create a parent class if none exists
        parent = CIDOCClass.objects.create(
            class_id='E1_CRM_Entity',
            label='CRM Entity',
            description='Root class for testing'
        )
        person.parent_classes.add(parent)
        print(f"Added parent class {parent.class_id} to {person.class_id}")
        
        # Now test with the parent class
        validate_cidoc_class(person, parent.class_id)
        print(f"\nValidated {person.class_id} as a {parent.class_id}")
        
        # Create an unrelated class
        unrelated_class = CIDOCClass.objects.create(
            class_id='E90_Symbolic_Object',
            label='Symbolic Object',
            description='Unrelated class for testing'
        )
        
        # Test with the unrelated class
        with pytest.raises(ValidationError, match='Invalid CIDOC class'):
            validate_cidoc_class(person, unrelated_class.class_id)


@pytest.mark.django_db
def test_validate_cidoc_relationship_real(loaded_cidoc_data):
    """Test validation of CIDOC relationship between classes using real database models"""
    # Print available properties
    print("\nAvailable properties:")
    for p in CIDOCProperty.objects.all()[:5]:
        print(f"- {p.property_id}: domain={p.domain_class.class_id if p.domain_class else None}, range={p.range_class.class_id if p.range_class else None}")
    
    # Find a property with domain and range
    property = CIDOCProperty.objects.filter(
        domain_class__isnull=False, 
        range_class__isnull=False
    ).first()
    
    if not property:
        pytest.skip("No properties with domain and range found")
        
    print(f"\nTesting with property: {property.property_id}")
    print(f"Domain: {property.domain_class.class_id}")
    print(f"Range: {property.range_class.class_id}")
    
    # Test with valid relationship
    validate_cidoc_relationship(
        property.property_id,
        property.domain_class.class_id,
        property.range_class.class_id
    )
    
    # Test with empty property ID
    with pytest.raises(ValidationError, match='Relationship must have a CIDOC-CRM property'):
        validate_cidoc_relationship('', 
                                   property.domain_class.class_id, 
                                   property.range_class.class_id)
    
    # Test with invalid property
    with pytest.raises(ValidationError, match='Invalid CIDOC-CRM property'):
        validate_cidoc_relationship('P999_NonExistentProperty', 
                                   property.domain_class.class_id, 
                                   property.range_class.class_id)
    
    # Test with invalid source class
    with pytest.raises(ValidationError, match='Invalid CIDOC-CRM class'):
        validate_cidoc_relationship(property.property_id, 
                                   'E999_NonExistentClass', 
                                   property.range_class.class_id)


@pytest.mark.django_db
def test_class_id_format_real(loaded_cidoc_data):
    """Test class ID format validation using real database classes"""
    # Get actual class IDs from database
    classes = list(CIDOCClass.objects.values_list('class_id', flat=True))
    print(f"\nClass IDs in database: {classes[:10]}")
    
    # Test that classes exist
    assert len(classes) > 0, "No classes found in database"
    
    # Test that all classes start with 'E'
    for cls in classes:
        assert cls.startswith('E'), f"Class {cls} does not start with 'E'"
    
    # Test invalid formats - none of these should be in the database
    invalid_ids = ['21', 'Person', 'E21 Person', '']
    for invalid_id in invalid_ids:
        assert invalid_id not in classes, f"Invalid ID format {invalid_id} found in database"


@pytest.mark.django_db
def test_property_id_format_real(loaded_cidoc_data):
    """Test property ID format using real database properties"""
    # Get actual property IDs from database
    properties = list(CIDOCProperty.objects.values_list('property_id', flat=True))
    print(f"\nProperty IDs in database: {properties[:10]}")
    
    # Test that properties exist
    assert len(properties) > 0, "No properties found in database"
    
    # Test that all properties start with 'P'
    for prop in properties:
        assert prop.startswith('P'), f"Property {prop} does not start with 'P'"
    
    # Test invalid formats - none of these should be in the database
    invalid_ids = ['62', 'depicts', 'P62 depicts', '']
    for invalid_id in invalid_ids:
        assert invalid_id not in properties, f"Invalid ID format {invalid_id} found in database" 