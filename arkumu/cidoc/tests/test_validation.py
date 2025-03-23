import pytest
from unittest.mock import Mock, patch
from django.core.exceptions import ValidationError
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from arkumu.cidoc.models.validators import (
    validate_cidoc_class,
    validate_property_domain_range,
    validate_property_cardinality,
    validate_inverse_relationship,
    validate_symmetric_relationship,
    validate_primitive_value
)
from rdflib import RDFS, RDF, OWL, Literal

def test_class_id_format(cidoc_rdf, cidoc_ns):
    """Test class ID format validation using real CIDOC classes"""
    # Get actual class IDs from RDF
    classes = [str(c).split('/')[-1] for c in cidoc_rdf.subjects(RDF.type, RDFS.Class) 
              if str(c).startswith(str(cidoc_ns))]
    
    # Test some actual valid classes
    assert 'E21_Person' in classes
    assert 'E22_Human-Made_Object' in classes
    
    # Test invalid formats
    invalid_ids = ['21_Person', 'E21', 'Person', 'E21 Person', '']
    for invalid_id in invalid_ids:
        assert invalid_id not in classes

def test_property_id_format(cidoc_rdf, cidoc_ns):
    """Test property ID format using real CIDOC properties"""
    # Get actual property IDs from RDF
    properties = [str(p).split('/')[-1] for p in cidoc_rdf.subjects(RDF.type, RDF.Property)
                 if str(p).startswith(str(cidoc_ns))]
    
    # Test some actual valid properties
    assert 'P62_depicts' in properties
    assert 'P62i_is_depicted_by' in properties
    
    # Test invalid formats
    invalid_ids = ['62_depicts', 'P62', 'depicts', 'P62 depicts', '']
    for invalid_id in invalid_ids:
        assert invalid_id not in properties

def test_class_hierarchy_constraints(cidoc_rdf, cidoc_ns):
    """Test class hierarchy using real CIDOC class relationships"""
    # Check E21_Person is a subclass of E39_Actor (correct hierarchy)
    person = cidoc_ns.E21_Person
    actor = cidoc_ns.E39_Actor
    
    # Verify the hierarchy exists in RDF
    assert (person, RDFS.subClassOf, actor) in cidoc_rdf
    
    # Check primitive types are interpreted as literals
    primitive_classes = ['E59_Primitive_Value', 'E60_Number', 'E61_Time_Primitive', 'E62_String']
    for prim_class in primitive_classes:
        # These should not be defined as RDFS classes
        assert (cidoc_ns[prim_class], RDF.type, RDFS.Class) not in cidoc_rdf

def test_property_domain_range_constraints(cidoc_rdf, cidoc_ns):
    """Test property domain/range using real CIDOC properties"""
    # Test P62_depicts
    depicts = cidoc_ns.P62_depicts
    
    # Get domain and range
    domain = cidoc_rdf.value(depicts, RDFS.domain)
    range_ = cidoc_rdf.value(depicts, RDFS.range)
    
    # Verify domain and range
    assert domain == cidoc_ns['E24_Physical_Human-Made_Thing']
    assert range_ == cidoc_ns.E1_CRM_Entity

def test_inverse_property_validation(cidoc_rdf, cidoc_ns):
    """Test inverse property relationships using real CIDOC properties"""
    # Test P62_depicts and P62i_is_depicted_by
    depicts = cidoc_ns.P62_depicts
    is_depicted_by = cidoc_ns.P62i_is_depicted_by
    
    # Verify inverse relationship
    assert (depicts, OWL.inverseOf, is_depicted_by) in cidoc_rdf

def test_symmetric_property_validation(cidoc_rdf, cidoc_ns):
    """Test symmetric properties using real CIDOC properties"""
    # Find symmetric properties (P119_meets_in_time_with might not be symmetric)
    symmetric_props = [p for p in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty)
                      if str(p).startswith(str(cidoc_ns))]
    
    # Test any symmetric properties found
    for prop in symmetric_props:
        # Get domain and range
        domain = cidoc_rdf.value(prop, RDFS.domain)
        range_ = cidoc_rdf.value(prop, RDFS.range)
        
        # For symmetric properties, domain and range should be the same
        assert domain == range_

def test_validate_cidoc_class(cidoc_rdf, cidoc_ns):
    """Test CIDOC class validation using RDF data"""
    # Create mock classes based on RDF data
    person = Mock(spec=CIDOCClass)
    person.class_id = 'E21_Person'
    
    actor = Mock(spec=CIDOCClass)
    actor.class_id = 'E39_Actor'
    
    # Set up parent relationship based on RDF
    person.parent_classes = Mock()
    person.parent_classes.all.return_value = [actor]
    
    # Test validation
    validate_cidoc_class(person, 'E21_Person')  # Direct match
    validate_cidoc_class(person, 'E39_Actor')  # Parent class
    
    with pytest.raises(ValidationError):
        validate_cidoc_class(person, 'E22_Human-Made_Object')
    
    with pytest.raises(ValidationError):
        validate_cidoc_class(None, 'E21_Person')

def test_validate_property_domain_range(cidoc_rdf, cidoc_ns):
    """Test property domain/range validation using RDF data"""
    # Create mock classes and property based on RDF data
    physical_thing = Mock(spec=CIDOCClass)
    physical_thing.class_id = 'E24_Physical_Human-Made_Thing'
    physical_thing.parent_classes = Mock()
    physical_thing.parent_classes.all.return_value = []
    
    entity = Mock(spec=CIDOCClass)
    entity.class_id = 'E1_CRM_Entity'
    entity.parent_classes = Mock()
    entity.parent_classes.all.return_value = []
    
    depicts = Mock(spec=CIDOCProperty)
    depicts.property_id = 'P62_depicts'
    depicts.domain_class = physical_thing
    depicts.range_class = entity
    depicts.is_relationship_property = True
    
    # Test validation
    validate_property_domain_range(depicts, physical_thing, entity)
    
    # Test invalid domain
    wrong_domain = Mock(spec=CIDOCClass)
    wrong_domain.class_id = 'E21_Person'
    wrong_domain.parent_classes = Mock()
    wrong_domain.parent_classes.all.return_value = []  # No parent classes
    
    with pytest.raises(ValidationError):
        validate_property_domain_range(depicts, wrong_domain, entity)
    
    # Test missing target class
    with pytest.raises(ValidationError):
        validate_property_domain_range(depicts, physical_thing)

def test_validate_property_cardinality():
    """Test property cardinality validation"""
    # Create mock property
    depicts = Mock(spec=CIDOCProperty)
    depicts.property_id = 'P62_depicts'
    depicts.is_functional = True
    
    # Create mock entities
    class MockEntity:
        def __init__(self, has_property=False):
            self._has_property = has_property
            
        @property
        def cidocentityproperty_set(self):
            class MockQuerySet:
                def __init__(self, exists_value):
                    self._exists_value = exists_value
                def filter(self, **kwargs):
                    return self
                def exists(self):
                    return self._exists_value
            return MockQuerySet(self._has_property)
    
    # Test validation
    entity_without = MockEntity(has_property=False)
    validate_property_cardinality(depicts, entity_without, "new_value")
    
    entity_with = MockEntity(has_property=True)
    with pytest.raises(ValidationError):
        validate_property_cardinality(depicts, entity_with, "new_value")

def test_validate_inverse_relationship(cidoc_rdf, cidoc_ns):
    """Test inverse relationship validation using RDF data"""
    # Create mock properties
    depicts = Mock(spec=CIDOCProperty)
    depicts.property_id = 'P62_depicts'
    
    is_depicted_by = Mock(spec=CIDOCProperty)
    is_depicted_by.property_id = 'P62i_is_depicted_by'
    
    depicts.inverse_property = is_depicted_by
    
    # Create mock entities
    class MockEntity:
        def __init__(self, has_inverse=False):
            self._has_inverse = has_inverse
            
        @property
        def incoming_relationships(self):
            class MockQuerySet:
                def __init__(self, exists_value):
                    self._exists_value = exists_value
                def filter(self, **kwargs):
                    return self
                def exists(self):
                    return self._exists_value
            return MockQuerySet(self._has_inverse)
    
    # Test validation
    source = MockEntity(has_inverse=False)
    target = MockEntity()
    with pytest.raises(ValidationError):
        validate_inverse_relationship(depicts, source, target)
    
    source_with_inverse = MockEntity(has_inverse=True)
    validate_inverse_relationship(depicts, source_with_inverse, target)

def test_validate_symmetric_relationship():
    """Test symmetric relationship validation"""
    # Create mock property
    meets = Mock(spec=CIDOCProperty)
    meets.property_id = 'P119_meets_in_time_with'
    meets.is_symmetric = True
    
    # Create mock entities
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
    
    # Test validation
    source = MockEntity(has_symmetric=False)
    target = MockEntity()
    with pytest.raises(ValidationError):
        validate_symmetric_relationship(meets, source, target)
    
    source_with_symmetric = MockEntity(has_symmetric=True)
    validate_symmetric_relationship(meets, source_with_symmetric, target)

def test_validate_primitive_value():
    """Test primitive value validation"""
    # Create mock primitive property
    number_class = Mock(spec=CIDOCClass)
    number_class.class_id = 'E60_Number'
    number_class.is_primitive = True
    
    number_prop = Mock(spec=CIDOCProperty)
    number_prop.property_id = 'P90_has_value'
    number_prop.range_class = number_class
    
    # Test validation
    validate_primitive_value(number_prop, "42")
    validate_primitive_value(number_prop, "3.14")
    validate_primitive_value(number_prop, "-1.5")
    
    with pytest.raises(ValidationError):
        validate_primitive_value(number_prop, "not a number")
    with pytest.raises(ValidationError):
        validate_primitive_value(number_prop, "") 