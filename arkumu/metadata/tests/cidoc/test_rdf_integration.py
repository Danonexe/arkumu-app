import pytest
from pathlib import Path
import os
from django.db import transaction
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from arkumu.metadata.models.cidoc import CIDOCClass, CIDOCProperty
from arkumu.metadata.rdf_import import import_cidoc_from_rdf


@pytest.mark.django_db
def test_db_model_loading(loaded_cidoc_data):
    """Test that RDF data loads correctly into database models"""
    classes_count, properties_count = loaded_cidoc_data
    assert classes_count > 0
    assert properties_count > 0
    
    # Verify the counts match what's in the database
    db_classes = CIDOCClass.objects.count()
    db_properties = CIDOCProperty.objects.count()
    
    print(f"\nDatabase has {db_classes} classes and {db_properties} properties")
    assert db_classes == classes_count
    assert db_properties == properties_count


@pytest.mark.django_db
def test_db_basic_structure(loaded_cidoc_data):
    """Test basic CIDOC-CRM structure presence in database models"""
    # Check for fundamental classes
    e1 = CIDOCClass.objects.filter(class_id='E1').first()
    assert e1 is not None
    assert e1.label is not None
    print(f"\nFound root class: {e1}")
    
    # Check for fundamental properties
    p1 = CIDOCProperty.objects.filter(property_id='P1').first()
    assert p1 is not None
    assert p1.label is not None
    print(f"\nFound fundamental property: {p1}")
    print(f"Domain: {p1.domain_class.class_id if p1.domain_class else 'None'}")
    print(f"Range: {p1.range_class.class_id if p1.range_class else 'None'}")


@pytest.mark.django_db
def test_db_class_definitions(loaded_cidoc_data):
    """Test class definitions in database models"""
    classes = CIDOCClass.objects.all()
    
    # Every class should have label and description
    for cls in classes:
        assert cls.label, f"Missing label for {cls.class_id}"
        assert cls.description, f"Missing description for {cls.class_id}"
    
    # Sample output of some classes
    sample_classes = CIDOCClass.objects.all()[:5]
    print("\nSample classes:")
    for cls in sample_classes:
        print(f"- {cls.class_id}: {cls.label}")
        print(f"  Description: {cls.description[:50]}...")


@pytest.mark.django_db
def test_db_property_definitions(loaded_cidoc_data):
    """Test property definitions in database models"""
    properties = CIDOCProperty.objects.all()
    
    # Every property should have label and description
    for prop in properties:
        assert prop.label, f"Missing label for {prop.property_id}"
        assert prop.description, f"Missing description for {prop.property_id}"
    
    # Most properties should have domain and range
    properties_with_domain = CIDOCProperty.objects.filter(domain_class__isnull=False).count()
    properties_with_range = CIDOCProperty.objects.filter(range_class__isnull=False).count()
    total_properties = CIDOCProperty.objects.count()
    
    print(f"\nProperties with domain: {properties_with_domain}/{total_properties}")
    print(f"Properties with range: {properties_with_range}/{total_properties}")
    
    # Sample output of some properties
    sample_properties = CIDOCProperty.objects.all()[:5]
    print("\nSample properties:")
    for prop in sample_properties:
        print(f"- {prop.property_id}: {prop.label}")
        print(f"  Domain: {prop.domain_class.class_id if prop.domain_class else 'None'}")
        print(f"  Range: {prop.range_class.class_id if prop.range_class else 'None'}")


@pytest.mark.django_db
def test_db_schema_completeness(loaded_cidoc_data):
    """Test completeness of CIDOC-CRM schema in database models"""
    # Get the E1 class
    e1 = CIDOCClass.objects.filter(class_id='E1').first()
    assert e1 is not None
    
    # E1 should have child classes
    child_classes = e1.child_classes.count()
    assert child_classes > 0
    print(f"\nE1 has {child_classes} child classes")
    
    # Get the P1 property
    p1 = CIDOCProperty.objects.filter(property_id='P1').first()
    assert p1 is not None
    
    # P1 should have child properties
    child_properties = p1.child_properties.count()
    print(f"P1 has {child_properties} child properties")


@pytest.mark.django_db
def test_db_property_class_references(loaded_cidoc_data):
    """Test that property domain/range references valid classes in database"""
    properties = CIDOCProperty.objects.filter(domain_class__isnull=False, range_class__isnull=False)
    
    # Sample properties for examination
    sample_properties = properties[:5]
    print("\nSample property references:")
    for prop in sample_properties:
        if prop.domain_class:
            # Verify domain class exists and is valid
            assert prop.domain_class.class_id is not None
            print(f"Property {prop.property_id} domain: {prop.domain_class.class_id}")
            
        if prop.range_class:
            # Verify range class exists and is valid
            assert prop.range_class.class_id is not None
            print(f"Property {prop.property_id} range: {prop.range_class.class_id}")


@pytest.mark.django_db
def test_db_inheritance_references(loaded_cidoc_data):
    """Test class inheritance references in database models"""
    # Test a few important class hierarchies
    e21 = CIDOCClass.objects.filter(class_id='E21').first()  # Person
    assert e21 is not None
    
    # Get parent classes of E21
    parent_classes = e21.parent_classes.all()
    print(f"\nE21 (Person) parents: {', '.join(p.class_id for p in parent_classes)}")
    assert parent_classes.count() > 0
    
    # Verify parent-child relationship consistency
    for parent in parent_classes:
        assert e21 in parent.child_classes.all(), f"Inconsistent parent-child relationship for {e21.class_id} and {parent.class_id}"


@pytest.mark.django_db
def test_db_property_characteristics(loaded_cidoc_data):
    """Test property characteristics in database models"""
    # Test functional properties
    functional = CIDOCProperty.objects.filter(is_functional=True)
    print(f"\nFunctional properties: {functional.count()}")
    
    # Test symmetric properties
    symmetric = CIDOCProperty.objects.filter(is_symmetric=True)
    print(f"Symmetric properties: {symmetric.count()}")
    for prop in symmetric[:3]:
        if prop.domain_class and prop.range_class:
            print(f"Symmetric property: {prop.property_id}")
            # Symmetric properties should have same domain and range
            assert prop.domain_class == prop.range_class, \
                f"Symmetric property {prop.property_id} has different domain and range"
    
    # Test transitive properties
    transitive = CIDOCProperty.objects.filter(is_transitive=True)
    print(f"Transitive properties: {transitive.count()}")
    for prop in transitive[:3]:
        if prop.domain_class and prop.range_class:
            print(f"Transitive property: {prop.property_id}")
            # Transitive properties should have same domain and range
            assert prop.domain_class == prop.range_class, \
                f"Transitive property {prop.property_id} has different domain and range"


@pytest.mark.django_db
def test_db_class_inheritance_depth(loaded_cidoc_data):
    """Test inheritance depth of classes in database models"""
    # Find the max inheritance depth
    def get_inheritance_depth(cls, visited=None):
        if visited is None:
            visited = set()
        if cls.id in visited:
            return 0  # Break circular references
        visited.add(cls.id)
        
        parents = cls.parent_classes.all()
        if not parents:
            return 0
        
        return 1 + max(get_inheritance_depth(parent, visited.copy()) for parent in parents)
    
    # Sample some classes to test inheritance depth
    sample_classes = [
        CIDOCClass.objects.filter(class_id='E21').first(),  # Person
        CIDOCClass.objects.filter(class_id='E22').first(),  # Human-Made Object
        CIDOCClass.objects.filter(class_id='E53').first()   # Place
    ]
    
    print("\nClass inheritance depths:")
    for cls in sample_classes:
        if cls:
            depth = get_inheritance_depth(cls)
            print(f"{cls.class_id}: {depth} levels")
            assert depth > 0, f"Class {cls.class_id} has no inheritance" 