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
    validate_primitive_value,
    validate_cidoc_entity,
    validate_cidoc_relationship
)
from rdflib import RDFS, RDF, OWL, Literal
import datetime

def test_validate_cidoc_entity():
    """Test validation of CIDOC entity class IDs"""
    with patch('arkumu.cidoc.models.schema.CIDOCClass') as MockCIDOCClass:
        # Test valid class ID
        MockCIDOCClass.objects.get.return_value = Mock(class_id='E21_Person')
        validate_cidoc_entity('E21_Person')
        
        # Test empty class ID
        with pytest.raises(ValidationError, match='Entity must have a CIDOC-CRM class'):
            validate_cidoc_entity('')
            
        # Test invalid class ID
        MockCIDOCClass.objects.get.side_effect = CIDOCClass.DoesNotExist
        with pytest.raises(ValidationError, match='Invalid CIDOC-CRM class'):
            validate_cidoc_entity('Invalid_Class')

def test_validate_cidoc_relationship():
    """Test validation of CIDOC relationship between classes"""
    with patch('arkumu.cidoc.models.schema.CIDOCProperty') as MockCIDOCProperty, \
         patch('arkumu.cidoc.models.schema.CIDOCClass') as MockCIDOCClass:
        
        # Set up mocks
        property_mock = Mock(
            property_id='P62_depicts',
            domain_class=Mock(class_id='E24_Physical_Human-Made_Thing'),
            range_class=Mock(class_id='E1_CRM_Entity')
        )
        MockCIDOCProperty.objects.get.return_value = property_mock
        
        source_class_mock = Mock(class_id='E24_Physical_Human-Made_Thing')
        target_class_mock = Mock(class_id='E1_CRM_Entity')
        source_class_mock.parent_classes.all.return_value = []
        target_class_mock.parent_classes.all.return_value = []
        
        def mock_get_class(class_id):
            if class_id == 'E24_Physical_Human-Made_Thing':
                return source_class_mock
            if class_id == 'E1_CRM_Entity':
                return target_class_mock
            raise CIDOCClass.DoesNotExist()
            
        MockCIDOCClass.objects.get.side_effect = mock_get_class
        
        # Test valid relationship
        validate_cidoc_relationship(
            'P62_depicts',
            'E24_Physical_Human-Made_Thing',
            'E1_CRM_Entity'
        )
        
        # Test empty property ID
        with pytest.raises(ValidationError, match='Relationship must have a CIDOC-CRM property'):
            validate_cidoc_relationship('', 'E24_Physical_Human-Made_Thing', 'E1_CRM_Entity')
            
        # Test invalid property
        MockCIDOCProperty.objects.get.side_effect = CIDOCProperty.DoesNotExist
        with pytest.raises(ValidationError, match='Invalid CIDOC-CRM property'):
            validate_cidoc_relationship('Invalid_Property', 'E24_Physical_Human-Made_Thing', 'E1_CRM_Entity')
            
        # Test invalid source class
        # Reset property mock to return valid property
        MockCIDOCProperty.objects.get.side_effect = None
        MockCIDOCProperty.objects.get.return_value = property_mock
        
        with pytest.raises(ValidationError, match='Invalid CIDOC-CRM class in relationship'):
            validate_cidoc_relationship('P62_depicts', 'Invalid_Class', 'E1_CRM_Entity')

def test_validate_primitive_value_extended():
    """Test validation of primitive values with all supported types"""
    # Test E60_Number
    number_class = Mock(spec=CIDOCClass)
    number_class.class_id = 'E60_Number'
    number_class.is_primitive = True
    
    number_prop = Mock(spec=CIDOCProperty)
    number_prop.range_class = number_class
    
    assert validate_primitive_value(number_prop, "42") == 42.0
    assert validate_primitive_value(number_prop, "3.14") == 3.14
    assert validate_primitive_value(number_prop, "-1.5") == -1.5
    
    with pytest.raises(ValidationError, match='Value must be a number'):
        validate_primitive_value(number_prop, "not a number")
    
    # Test E61_Time_Primitive
    time_class = Mock(spec=CIDOCClass)
    time_class.class_id = 'E61_Time_Primitive'
    time_class.is_primitive = True
    
    time_prop = Mock(spec=CIDOCProperty)
    time_prop.range_class = time_class
    
    # Test date
    date_value = datetime.date(2024, 3, 20)
    assert validate_primitive_value(time_prop, date_value) == date_value
    assert validate_primitive_value(time_prop, "2024-03-20").isoformat() == "2024-03-20"
    
    # Test datetime
    datetime_value = datetime.datetime(2024, 3, 20, 14, 30)
    assert validate_primitive_value(time_prop, datetime_value) == datetime_value
    assert validate_primitive_value(time_prop, "2024-03-20T14:30:00").isoformat() == "2024-03-20T14:30:00"
    
    with pytest.raises(ValidationError, match='must be a valid date/time'):
        validate_primitive_value(time_prop, "not a date")
    
    # Test E95_Spacetime_Primitive
    geo_class = Mock(spec=CIDOCClass)
    geo_class.class_id = 'E95_Spacetime_Primitive'
    geo_class.is_primitive = True
    
    geo_prop = Mock(spec=CIDOCProperty)
    geo_prop.range_class = geo_class
    
    geo_value = {"type": "Point", "coordinates": [125.6, 10.1]}
    assert validate_primitive_value(geo_prop, geo_value) == geo_value
    
    with pytest.raises(ValidationError, match='must be a valid GeoJSON object'):
        validate_primitive_value(geo_prop, "not a GeoJSON")
    
    # Test E62_String (and default case)
    string_class = Mock(spec=CIDOCClass)
    string_class.class_id = 'E62_String'
    string_class.is_primitive = True
    
    string_prop = Mock(spec=CIDOCProperty)
    string_prop.range_class = string_class
    
    assert validate_primitive_value(string_prop, "test string") == "test string"
    assert validate_primitive_value(string_prop, 123) == "123"
    
    # Test non-primitive property
    non_primitive_prop = Mock(spec=CIDOCProperty)
    non_primitive_prop.range_class = None
    
    test_value = "any value"
    assert validate_primitive_value(non_primitive_prop, test_value) == test_value
    
    # Test None value
    assert validate_primitive_value(number_prop, None) is None

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
    
    with pytest.raises(ValidationError, match='Invalid CIDOC class'):
        validate_cidoc_class(person, 'E22_Human-Made_Object')
    
    with pytest.raises(ValidationError, match='Entity must have a CIDOC-CRM class'):
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
    
    with pytest.raises(ValidationError, match='Invalid property domain'):
        validate_property_domain_range(depicts, wrong_domain, entity)
    
    # Test missing target class
    with pytest.raises(ValidationError, match='Target class required for relationship property'):
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
    with pytest.raises(ValidationError, match='can have at most one value'):
        validate_property_cardinality(depicts, entity_with, "new_value")

def test_validate_inverse_relationship():
    """Test inverse relationship validation"""
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
    with pytest.raises(ValidationError, match='Missing inverse relationship'):
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
    with pytest.raises(ValidationError, match='Missing symmetric relationship'):
        validate_symmetric_relationship(meets, source, target)
    
    source_with_symmetric = MockEntity(has_symmetric=True)
    validate_symmetric_relationship(meets, source_with_symmetric, target) 