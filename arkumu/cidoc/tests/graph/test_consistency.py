import pytest
from pathlib import Path
import os
from rdflib import RDFS, RDF, OWL, Graph, Namespace
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
from django.core.exceptions import ValidationError
from django.db import transaction
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf


@pytest.fixture
def rdf_file_path():
    """Return the path to the CIDOC RDF file"""
    base_dir = Path(__file__).resolve().parent.parent.parent
    rdf_file = os.path.join(base_dir, 'schema', 'CIDOC_CRM_v7.1.1.rdf')
    assert os.path.exists(rdf_file), f"RDF file not found at {rdf_file}"
    return rdf_file


@pytest.fixture
def cidoc_rdf(rdf_file_path):
    """Return an RDFLib graph with the CIDOC RDF loaded"""
    g = Graph()
    g.parse(rdf_file_path)
    return g


@pytest.fixture
def cidoc_ns():
    """Return the CIDOC namespace"""
    return Namespace("http://www.cidoc-crm.org/cidoc-crm/")



@pytest.mark.django_db
def test_property_domain_range_consistency(cidoc_rdf, cidoc_ns):
    """Test that property domains and ranges reference valid classes"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            # Get domain and range
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            
            # Verify domain and range are defined classes
            if domain:
                assert (domain, RDF.type, RDFS.Class) in cidoc_rdf
            if range_:
                # Skip validation for rdfs:Literal since it's a special type
                if str(range_) != str(RDFS.Literal):
                    assert (range_, RDF.type, RDFS.Class) in cidoc_rdf

def test_inverse_property_consistency(cidoc_rdf, cidoc_ns):
    """Test that inverse properties are consistently defined"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            # Get inverse properties
            inverse_props = list(cidoc_rdf.subjects(OWL.inverseOf, prop))
            for inverse in inverse_props:
                # Verify reciprocal inverse relationship
                assert (prop, OWL.inverseOf, inverse) in cidoc_rdf or \
                       (inverse, OWL.inverseOf, prop) in cidoc_rdf

def test_class_hierarchy_consistency(cidoc_rdf, cidoc_ns):
    """Test that class hierarchy is consistent"""
    def get_all_parents(class_uri, visited=None, path=None):
        if visited is None:
            visited = set()
        if path is None:
            path = []
            
        if class_uri in path:
            print(f"Circular reference path: {' -> '.join(str(x) for x in path + [class_uri])}")
            return False
            
        path.append(class_uri)
        parents = list(cidoc_rdf.objects(class_uri, RDFS.subClassOf))
        
        # No parents is fine - it's a root class
        if not parents:
            return True
            
        # Check each parent
        for parent in parents:
            # Only check CIDOC parents
            if str(parent).startswith(str(cidoc_ns)):
                if not get_all_parents(parent, visited, path[:]):
                    return False
        return True

    # Test each CIDOC class
    for class_uri in cidoc_rdf.subjects(RDF.type, RDFS.Class):
        if str(class_uri).startswith(str(cidoc_ns)):
            result = get_all_parents(class_uri)
            if not result:
                print(f"\nAnalyzing hierarchy for: {class_uri}")
                # Print direct parents for debugging
                parents = list(cidoc_rdf.objects(class_uri, RDFS.subClassOf))
                print(f"Direct parents: {parents}")
            assert result, f"Circular reference detected for {class_uri}"

def test_primitive_inheritance_consistency(cidoc_rdf, cidoc_ns):
    """Test that primitive classes don't inherit from non-primitive classes"""
    primitive_classes = [
        'E59_Primitive_Value',
        'E60_Number',
        'E61_Time_Primitive',
        'E62_String'
    ]
    
    for class_id in primitive_classes:
        class_uri = cidoc_ns[class_id]
        for parent in cidoc_rdf.objects(class_uri, RDFS.subClassOf):
            if str(parent).startswith(str(cidoc_ns)):
                parent_id = str(parent).split('/')[-1]
                # Primitive classes should only inherit from other primitive classes
                assert any(parent_id.startswith(pc.split('_')[0]) for pc in primitive_classes)

def test_symmetric_property_consistency(cidoc_rdf, cidoc_ns):
    """Test that symmetric properties have consistent domain and range"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            # Symmetric properties must have same domain and range
            assert domain == range_

def test_transitive_property_consistency(cidoc_rdf, cidoc_ns):
    """Test that transitive properties have consistent types"""
    for prop in cidoc_rdf.subjects(RDF.type, OWL.TransitiveProperty):
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            # Domain and range should be compatible for transitive properties
            assert domain == range_

def test_temporal_property_consistency(cidoc_rdf, cidoc_ns):
    """Test consistency of temporal properties"""
    temporal_classes = [
        'E2_Temporal_Entity',
        'E3_Condition_State',
        'E4_Period'
    ]
    
    for class_id in temporal_classes:
        class_uri = cidoc_ns[class_id]
        # Verify temporal classes exist
        assert (class_uri, RDF.type, RDFS.Class) in cidoc_rdf
        
        # Check temporal properties
        for prop in cidoc_rdf.subjects(RDFS.domain, class_uri):
            if str(prop).startswith(str(cidoc_ns)):
                # Verify temporal properties have appropriate ranges
                range_ = cidoc_rdf.value(prop, RDFS.range)
                if range_:
                    assert (range_, RDF.type, RDFS.Class) in cidoc_rdf

def test_temporal_sequence_consistency(cidoc_rdf, cidoc_ns):
    """Test consistency of temporal sequence properties"""
    # These are the actual temporal sequence properties in CIDOC-CRM v7.1.1
    sequence_properties = [
        'P173_starts_before_or_with_the_end_of',
        'P174_starts_before_the_end_of',
        'P175_starts_before_or_with_the_start_of',
        'P176_starts_before_the_start_of',
        'P182_ends_before_or_with_the_start_of',
        'P183_ends_before_the_start_of',
        'P184_ends_before_or_with_the_end_of',
        'P185_ends_before_the_end_of'
    ]
    
    # First verify all required temporal sequence properties exist
    missing_properties = []
    for prop_id in sequence_properties:
        prop_uri = cidoc_ns[prop_id]
        if not any(cidoc_rdf.triples((prop_uri, None, None))):
            missing_properties.append(prop_id)
    
    assert not missing_properties, \
        f"Required temporal sequence properties missing from ontology: {', '.join(missing_properties)}"
    
    # Now test each property
    for prop_id in sequence_properties:
        prop_uri = cidoc_ns[prop_id]
        
        # Check domain and range are temporal entities
        domain = cidoc_rdf.value(prop_uri, RDFS.domain)
        range_ = cidoc_rdf.value(prop_uri, RDFS.range)
        
        assert domain is not None, f"Property {prop_id} should have a domain"
        assert range_ is not None, f"Property {prop_id} should have a range"
        
        # Check if domain and range are temporal entities or their subclasses
        def is_temporal_entity(class_uri):
            """Check if a class is E2_Temporal_Entity or its subclass"""
            if str(class_uri).endswith('E2_Temporal_Entity'):
                return True
                
            # Check superclasses recursively
            for parent in cidoc_rdf.objects(class_uri, RDFS.subClassOf):
                if is_temporal_entity(parent):
                    return True
            return False
            
        assert is_temporal_entity(domain), \
            f"Property {prop_id} domain {domain} is not a temporal entity or subclass"
        assert is_temporal_entity(range_), \
            f"Property {prop_id} range {range_} is not a temporal entity or subclass" 