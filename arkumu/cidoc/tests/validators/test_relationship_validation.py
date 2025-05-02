import pytest
from django.core.exceptions import ValidationError
from django.db import transaction, models
from pathlib import Path
import os

from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.validators import (
    validate_cidoc_class,
    validate_inverse_relationship,
    validate_symmetric_relationship
)


@pytest.mark.django_db
def test_validate_inverse_relationship_real(loaded_cidoc_data):
    """Test inverse relationship validation with real database models"""
    # Find a property with an inverse
    inverse_props = CIDOCProperty.objects.exclude(inverse_property=None)
    
    if not inverse_props.exists():
        print("\nNo inverse properties found in database, skipping test")
        pytest.skip("No inverse properties found in database")
        
    prop = inverse_props.first()
    inverse = prop.inverse_property
    
    print(f"\nTesting inverse validation for: {prop.property_id} and {inverse.property_id}")
    
    # Create mock entities for testing
    class MockEntity:
        def __init__(self, has_inverse=False):
            self._has_inverse = has_inverse
            self.property_id = None
            self.inverse_property_id = None
            
        @property
        def incoming_relationships(self):
            class MockQuerySet:
                def __init__(self, exists_value, property_id=None):
                    self._exists_value = exists_value
                    self._property_id = property_id
                def filter(self, **kwargs):
                    if 'relation_type' in kwargs:
                        self._property_id = kwargs['relation_type']
                    return self
                def exists(self):
                    return self._exists_value
            return MockQuerySet(self._has_inverse)
    
    # Test with entity that has no inverse relationship
    source = MockEntity(has_inverse=False)
    target = MockEntity()
    
    with pytest.raises(ValidationError, match='Missing inverse relationship'):
        validate_inverse_relationship(prop, source, target)
    
    # Test with entity that has the inverse relationship
    source_with_inverse = MockEntity(has_inverse=True)
    validate_inverse_relationship(prop, source_with_inverse, target)


@pytest.mark.django_db
def test_validate_symmetric_relationship_real(loaded_cidoc_data):
    """Test symmetric relationship validation with real database models"""
    # Find symmetric properties
    symmetric_props = CIDOCProperty.objects.filter(is_symmetric=True)
    
    if not symmetric_props.exists():
        # Create a test symmetric property
        test_class = CIDOCClass.objects.first()
        if not test_class:
            pytest.skip("No classes found in database")
            
        test_prop, created = CIDOCProperty.objects.get_or_create(
            property_id='P_TEST_SYMMETRIC',
            defaults={
                'label': 'Test Symmetric Property',
                'description': 'Test property for symmetric validation',
                'domain_class': test_class,
                'range_class': test_class,
                'is_symmetric': True
            }
        )
        
        if not created:
            test_prop.is_symmetric = True
            test_prop.domain_class = test_class
            test_prop.range_class = test_class
            test_prop.save()
    else:
        test_prop = symmetric_props.first()
    
    print(f"\nTesting symmetric validation for property: {test_prop.property_id}")
    
    # Create mock entities for testing
    class MockEntity:
        def __init__(self, has_symmetric=False):
            self._has_symmetric = has_symmetric
            
        @property
        def incoming_relationships(self):
            class MockQuerySet:
                def __init__(self, exists_value):
                    self._exists_value = exists_value
                def filter(self, **kwargs):
                    return self
                def exists(self):
                    return self._exists_value
            return MockQuerySet(self._has_symmetric)
    
    # Test with entity that has no symmetric relationship
    source = MockEntity(has_symmetric=False)
    target = MockEntity()
    
    with pytest.raises(ValidationError, match='Missing symmetric relationship'):
        validate_symmetric_relationship(test_prop, source, target)
    
    # Test with entity that has the symmetric relationship
    source_with_symmetric = MockEntity(has_symmetric=True)
    validate_symmetric_relationship(test_prop, source_with_symmetric, target)


@pytest.mark.django_db
def test_class_hierarchy_validation_real(loaded_cidoc_data):
    """Test class hierarchy validation using real database models"""
    # Find a class with parent classes
    child_classes = CIDOCClass.objects.annotate(
        parent_count=models.Count('parent_classes')
    ).filter(parent_count__gt=0)
    
    if not child_classes.exists():
        # Create test class hierarchy
        parent = CIDOCClass.objects.create(
            class_id='E77_Persistent_Item',
            label='Persistent Item',
            description='Parent class for testing'
        )
        child = CIDOCClass.objects.create(
            class_id='E39_Actor',
            label='Actor',
            description='Child class for testing'
        )
        child.parent_classes.add(parent)
        print(f"\nCreated test class hierarchy: {child.class_id} is a {parent.class_id}")
    else:
        child = child_classes.first()
        print(f"\nTesting class hierarchy for: {child.class_id}")
    
    parents = list(child.parent_classes.all())
    print(f"Parents: {', '.join([p.class_id for p in parents])}")
    
    # Verify that the class can be validated as any of its parent classes
    for parent in parents:
        validate_cidoc_class(child, parent.class_id)
        print(f"Successfully validated {child.class_id} as {parent.class_id}")
        
    # Find a class that is not a parent of the child
    non_parent = CIDOCClass.objects.exclude(
        id__in=[p.id for p in parents]
    ).exclude(id=child.id).first()
    
    if not non_parent:
        # Create a non-parent class
        non_parent = CIDOCClass.objects.create(
            class_id='E90_Symbolic_Object',
            label='Symbolic Object',
            description='Unrelated class for testing'
        )
        print(f"Created non-parent class {non_parent.class_id}")
    
    # Verify that validation fails for non-parent class
    with pytest.raises(ValidationError):
        validate_cidoc_class(child, non_parent.class_id)
        
    print(f"Correctly rejected {child.class_id} as {non_parent.class_id}") 