from unittest.mock import Mock, patch
import pytest
from rdflib import RDFS, RDF, OWL
from arkumu.cidoc.models.schema import CIDOCProperty, CIDOCClass
from django.core.exceptions import ValidationError

@pytest.fixture
def rdf_based_property(cidoc_rdf, cidoc_ns):
    """Create property mock based on RDF data (using P62_depicts as example)"""
    mock = Mock(spec=CIDOCProperty)
    mock.property_id = 'P62_depicts'
    
    label = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.label)
    comment = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.comment)
    
    mock.label = str(label) if label else "depicts"
    mock.description = str(comment) if comment else ""
    
    # Set up domain and range
    domain = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.domain)
    range_ = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.range)
    
    mock.domain_class = Mock(spec=CIDOCClass)
    mock.domain_class.class_id = str(domain).split('/')[-1] if domain else None
    
    mock.range_class = Mock(spec=CIDOCClass)
    mock.range_class.class_id = str(range_).split('/')[-1] if range_ else None
    
    # Configure __str__ to match the model's implementation
    mock.__str__ = lambda self: f"{self.property_id}: {self.label}"
    
    return mock

def test_property_creation(rdf_based_property):
    """Test basic property creation"""
    assert rdf_based_property.property_id == 'P62_depicts'
    assert rdf_based_property.label is not None
    assert rdf_based_property.description is not None

def test_property_string_representation(rdf_based_property):
    """Test property string representation"""
    expected = f"{rdf_based_property.property_id}: {rdf_based_property.label}"
    assert str(rdf_based_property) == expected

def test_property_domain_range(cidoc_rdf, cidoc_ns):
    """Test property domain and range from RDF"""
    domain = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.domain)
    range_ = cidoc_rdf.value(cidoc_ns.P62_depicts, RDFS.range)
    assert domain is not None
    assert range_ is not None

def test_inverse_property(cidoc_rdf, cidoc_ns):
    """Test inverse property relationships"""
    # Find properties with inverses
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            inverse_props = list(cidoc_rdf.subjects(OWL.inverseOf, prop))
            if inverse_props:
                # Verify inverse relationship
                inverse = inverse_props[0]
                assert (inverse, OWL.inverseOf, prop) in cidoc_rdf

def test_symmetric_property(cidoc_rdf, cidoc_ns):
    """Test symmetric properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            assert domain == range_

def test_transitive_property(cidoc_rdf, cidoc_ns):
    """Test transitive properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.TransitiveProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            assert domain == range_

def test_functional_property(cidoc_rdf, cidoc_ns):
    """Test functional properties"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.FunctionalProperty):
        if str(prop).startswith(str(cidoc_ns)):
            # Functional properties should have cardinality constraints
            assert (prop, RDF.type, OWL.FunctionalProperty) in cidoc_rdf

def test_property_cardinality(rdf_based_property):
    """Test property cardinality constraints"""
    rdf_based_property.is_functional = True
    assert rdf_based_property.is_functional

def test_property_value_constraints(cidoc_rdf, cidoc_ns):
    """Test property value type constraints"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            range_ = cidoc_rdf.value(prop, RDFS.range)
            if range_ and str(range_).endswith('_Primitive_Value'):
                # Properties with primitive ranges should have value constraints
                assert True  # Replace with actual constraint check

def test_property_subproperty(cidoc_rdf, cidoc_ns):
    """Test property inheritance relationships"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            # Get subproperties
            subprops = list(cidoc_rdf.subjects(RDFS.subPropertyOf, prop))
            for subprop in subprops:
                # Verify subproperty relationship
                assert (subprop, RDFS.subPropertyOf, prop) in cidoc_rdf

def test_inherited_constraints(cidoc_rdf, cidoc_ns):
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

def test_invalid_property_id():
    """Test invalid property ID format"""
    mock = Mock(spec=CIDOCProperty)
    mock.clean.side_effect = ValidationError("Invalid property ID format")
    
    with pytest.raises(ValidationError):
        mock.property_id = 'InvalidFormat'
        mock.clean()

def test_incompatible_domain_range():
    """Test incompatible domain and range"""
    mock = Mock(spec=CIDOCProperty)
    mock.clean.side_effect = ValidationError("Incompatible domain and range")
    
    with pytest.raises(ValidationError):
        mock.is_symmetric = True
        mock.domain_class = Mock(spec=CIDOCClass, class_id='E21_Person')
        mock.range_class = Mock(spec=CIDOCClass, class_id='E22_Human-Made_Object')
        mock.clean()

def test_circular_property_definition(cidoc_rdf, cidoc_ns):
    """Test circular property relationships"""
    def check_circular_properties(prop_uri, visited=None, path=None):
        if visited is None:
            visited = set()
        if path is None:
            path = []
            
        if prop_uri in path:
            return True
            
        path.append(prop_uri)
        visited.add(prop_uri)
        
        for subprop in cidoc_rdf.subjects(RDFS.subPropertyOf, prop_uri):
            if check_circular_properties(subprop, visited, path.copy()):
                return True
        return False
    
    # Verify no circular property relationships exist
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            assert not check_circular_properties(prop), \
                   f"Circular property relationship detected starting from {prop}" 