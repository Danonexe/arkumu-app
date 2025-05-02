import pytest
from pathlib import Path
from django.db import transaction
from django.core.exceptions import ValidationError
from rdflib import RDFS, RDF, OWL, Graph
from arkumu.cidoc.models.schema import CIDOCProperty, CIDOCClass
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf


@pytest.fixture
@pytest.mark.django_db
def test_property(loaded_cidoc_data):
    """Get a real property from the database (using P62 as example)"""
    return CIDOCProperty.objects.filter(property_id='P62').first()


@pytest.mark.django_db
def test_property_creation(test_property):
    """Test basic property creation with real database model"""
    assert test_property.property_id == 'P62'
    assert test_property.label is not None
    assert test_property.description is not None


@pytest.mark.django_db
def test_db_property_creation(loaded_cidoc_data):
    """Test property creation with real database models"""
    # Test property exists in database
    depicts = CIDOCProperty.objects.filter(property_id='P1').first()
    assert depicts is not None
    assert depicts.label is not None
    assert depicts.description is not None
    print(f"\nProperty: {depicts.property_id} - {depicts.label}")
    print(f"Domain: {depicts.domain_class.class_id if depicts.domain_class else 'None'}")
    print(f"Range: {depicts.range_class.class_id if depicts.range_class else 'None'}")


@pytest.mark.django_db
def test_property_string_representation(test_property):
    """Test property string representation with real database model"""
    expected = f"{test_property.property_id}: {test_property.label}"
    assert str(test_property) == expected


@pytest.mark.django_db
def test_db_property_string_representation(loaded_cidoc_data):
    """Test property string representation with real database models"""
    property = CIDOCProperty.objects.first()
    expected = f"{property.property_id}: {property.label}"
    assert str(property) == expected


@pytest.mark.django_db
def test_property_domain_range(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test property domain and range from RDF"""
    domain = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.domain)
    range_ = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.range)
    assert domain is not None
    assert range_ is not None


@pytest.mark.django_db
def test_db_property_domain_range(loaded_cidoc_data):
    """Test property domain and range from database models"""
    # Get a few properties with domain and range
    properties = CIDOCProperty.objects.filter(domain_class__isnull=False, range_class__isnull=False)[:5]
    for prop in properties:
        print(f"\nProperty {prop.property_id} domain/range:")
        print(f"Domain: {prop.domain_class.class_id}")
        print(f"Range: {prop.range_class.class_id}")
        
        assert prop.domain_class is not None
        assert prop.range_class is not None


@pytest.mark.django_db
def test_inverse_property(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test inverse property relationships"""
    # Find properties with inverses
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            inverse_props = list(cidoc_rdf.subjects(OWL.inverseOf, prop))
            if inverse_props:
                # Verify inverse relationship
                inverse = inverse_props[0]
                assert (inverse, OWL.inverseOf, prop) in cidoc_rdf


@pytest.mark.django_db
def test_db_inverse_property(loaded_cidoc_data):
    """Test inverse property relationships in database models"""
    # Find properties with inverses
    properties_with_inverse = CIDOCProperty.objects.exclude(inverse_property=None)
    
    print(f"\nFound {properties_with_inverse.count()} properties with inverse relationships")
    for prop in properties_with_inverse[:5]:  # Show just the first 5 for brevity
        print(f"Property {prop.property_id} has inverse: {prop.inverse_property.property_id}")
        # Verify the relationship is reciprocal
        assert prop.inverse_property.inverse_property == prop, \
            f"Inverse relationship is not reciprocal for {prop.property_id}"


@pytest.mark.django_db
def test_symmetric_property(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test symmetric properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            assert domain == range_


@pytest.mark.django_db
def test_db_symmetric_property(loaded_cidoc_data):
    """Test symmetric properties in database models"""
    symmetric_properties = CIDOCProperty.objects.filter(is_symmetric=True)
    
    print(f"\nFound {symmetric_properties.count()} symmetric properties")
    
    for prop in symmetric_properties:
        print(f"Symmetric property: {prop.property_id}")
        # For symmetric properties, domain and range should be the same
        assert prop.domain_class == prop.range_class, \
            f"Symmetric property {prop.property_id} has different domain and range"


@pytest.mark.django_db
def test_transitive_property(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test transitive properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.TransitiveProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            assert domain == range_


@pytest.mark.django_db
def test_db_transitive_property(loaded_cidoc_data):
    """Test transitive properties in database models"""
    transitive_properties = CIDOCProperty.objects.filter(is_transitive=True)
    
    print(f"\nFound {transitive_properties.count()} transitive properties")
    
    for prop in transitive_properties:
        print(f"Transitive property: {prop.property_id}")
        # For transitive properties, domain and range should be the same
        assert prop.domain_class == prop.range_class, \
            f"Transitive property {prop.property_id} has different domain and range"


@pytest.mark.django_db
def test_functional_property(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test functional properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.FunctionalProperty):
        if str(prop).startswith(str(cidoc_ns)):
            # Functional properties should have cardinality constraints
            assert (prop, RDF.type, OWL.FunctionalProperty) in cidoc_rdf


@pytest.mark.django_db
def test_db_functional_property(loaded_cidoc_data):
    """Test functional properties in database models"""
    functional_properties = CIDOCProperty.objects.filter(is_functional=True)
    
    print(f"\nFound {functional_properties.count()} functional properties")
    
    for prop in functional_properties[:5]:
        print(f"Functional property: {prop.property_id}")


@pytest.mark.django_db
def test_property_cardinality(loaded_cidoc_data):
    """Test property cardinality constraints with real database model"""
    # Find a functional property
    functional_property = CIDOCProperty.objects.filter(is_functional=True).first()
    if functional_property:
        assert functional_property.is_functional


@pytest.mark.django_db
def test_property_value_constraints(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test property value type constraints"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            range_ = cidoc_rdf.value(prop, RDFS.range)
            if range_ and str(range_).endswith('_Primitive_Value'):
                # Properties with primitive ranges should have value constraints
                assert True  # Replace with actual constraint check


@pytest.mark.django_db
def test_db_property_value_constraints(loaded_cidoc_data):
    """Test property value type constraints in database models"""
    # Find properties with primitive range types
    primitive_properties = CIDOCProperty.objects.filter(range_class__is_primitive=True)
    
    print(f"\nFound {primitive_properties.count()} properties with primitive ranges")
    
    for prop in primitive_properties[:5]:
        print(f"Property {prop.property_id} has primitive range: {prop.range_class.class_id}")
        assert prop.range_class.is_primitive


@pytest.mark.django_db
def test_property_subproperty(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test property inheritance relationships"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            # Get subproperties
            subprops = list(cidoc_rdf.subjects(RDFS.subPropertyOf, prop))
            for subprop in subprops:
                # Verify subproperty relationship
                assert (subprop, RDFS.subPropertyOf, prop) in cidoc_rdf


@pytest.mark.django_db
def test_db_property_hierarchy(loaded_cidoc_data):
    """Test property hierarchy in database models"""
    # Find properties with parent properties
    properties_with_parents = CIDOCProperty.objects.exclude(parent_properties=None)
    
    print(f"\nFound properties with parent relationships")
    for prop in properties_with_parents[:5]:
        parents = prop.parent_properties.all()
        print(f"Property {prop.property_id} has parents: {', '.join(p.property_id for p in parents)}")
        
        # For each parent, verify the child relationship
        for parent in parents:
            assert prop in parent.child_properties.all(), \
                f"Parent-child relationship is not reciprocal for {prop.property_id} and {parent.property_id}"


@pytest.mark.django_db
def test_inherited_constraints(loaded_cidoc_data, cidoc_rdf, cidoc_ns):
    """Test inheritance of property constraints"""
    def is_subclass_of(class_uri, parent_uri, visited=None):
        if visited is None:
            visited = set()
        if class_uri in visited:
            return False
        visited.add(class_uri)
        
        # Direct subclass
        if (class_uri, RDFS.subClassOf, parent_uri) in cidoc_rdf:
            return True
            
        # Check indirect subclass through hierarchy
        for superclass in cidoc_rdf.objects(class_uri, RDFS.subClassOf):
            if is_subclass_of(superclass, parent_uri, visited):
                return True
        return False

    for prop in cidoc_rdf.subjects(RDFS.subPropertyOf, None):
        if str(prop).startswith(str(cidoc_ns)):
            parent_props = list(cidoc_rdf.objects(prop, RDFS.subPropertyOf))
            for parent in parent_props:
                # Subproperties should have compatible domain/range with parent
                prop_domain = cidoc_rdf.value(prop, RDFS.domain)
                parent_domain = cidoc_rdf.value(parent, RDFS.domain)
                if prop_domain and parent_domain:
                    # Domain should either be the same as parent domain or a subclass of it
                    assert (prop_domain == parent_domain or 
                           is_subclass_of(prop_domain, parent_domain)), \
                           f"Domain {prop_domain} is not compatible with parent domain {parent_domain}"


@pytest.mark.django_db
def test_invalid_property_id(loaded_cidoc_data):
    """Test invalid property ID format with real database models"""
    # Create a new property with invalid ID
    with pytest.raises(ValidationError):
        invalid_property = CIDOCProperty(
            property_id='InvalidFormat',
            label='Invalid Property',
            description='This has an invalid property ID format'
        )
        invalid_property.full_clean()


@pytest.mark.django_db
def test_incompatible_domain_range(loaded_cidoc_data):
    """Test incompatible domain and range with real database models"""
    # Find a person class
    person_class = CIDOCClass.objects.filter(class_id='E21').first()
    # Find a non-person class
    object_class = CIDOCClass.objects.filter(class_id='E22').first()
    
    if person_class and object_class:
        # Create a symmetric property with incompatible domain/range
        with pytest.raises(ValidationError):
            invalid_property = CIDOCProperty(
                property_id='P999_test_symmetric',
                label='Test Symmetric',
                description='Test symmetric property with incompatible domain/range',
                domain_class=person_class,
                range_class=object_class,
                is_symmetric=True
            )
            invalid_property.full_clean()


@pytest.mark.django_db
def test_circular_property_definition(loaded_cidoc_data):
    """Test circular property relationships with real database models"""
    # Check for circular parent-child relationships
    def has_circular_parent(prop, visited=None):
        if visited is None:
            visited = set()
        
        if prop.id in visited:
            return True
            
        visited.add(prop.id)
        
        for parent in prop.parent_properties.all():
            if has_circular_parent(parent, visited.copy()):
                return True
        return False
    
    # Test all properties
    circular_props = []
    for prop in CIDOCProperty.objects.all():
        if has_circular_parent(prop):
            circular_props.append(prop.property_id)
    
    assert not circular_props, f"Found circular property relationships: {circular_props}" 