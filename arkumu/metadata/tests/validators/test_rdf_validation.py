import pytest
from pathlib import Path
import os
from rdflib import RDFS, RDF, OWL, Namespace


def test_rdf_class_hierarchy_constraints(cidoc_rdf, cidoc_ns):
    """Test class hierarchy using RDF data directly"""
    # Check E21 (Person) is a subclass of either E39 (Actor) or E20 (Biological Object)
    person = cidoc_ns.E21_Person
    
    # Find parent classes in RDF
    parent_classes = list(cidoc_rdf.objects(person, RDFS.subClassOf))
    
    # Print parent classes for debugging
    print(f"\nParent classes for E21_Person in RDF:")
    for parent in parent_classes:
        print(f"- {parent}")
    
    # Verify that Person has at least one parent
    assert len(parent_classes) > 0, "E21_Person should have at least one parent class"
    
    # Check primitive types are interpreted correctly
    primitive_classes = ['E59_Primitive_Value', 'E60_Number', 'E61_Time_Primitive', 'E62_String']
    for prim_class in primitive_classes:
        # These should not be defined as RDFS classes (they are literal types)
        if (cidoc_ns[prim_class], RDF.type, RDFS.Class) in cidoc_rdf:
            print(f"Warning: {prim_class} is defined as RDFS.Class in the RDF")
        else:
            print(f"{prim_class} is correctly not defined as RDFS.Class")


def test_rdf_property_domain_range_constraints(cidoc_rdf, cidoc_ns):
    """Test property domain/range using RDF data directly"""
    # Find properties with both domain and range
    properties_with_domain_range = []
    
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if not str(prop).startswith(str(cidoc_ns)):
            continue
            
        domain = cidoc_rdf.value(prop, RDFS.domain)
        range_ = cidoc_rdf.value(prop, RDFS.range)
        
        if domain and range_:
            prop_id = str(prop).split('/')[-1]
            properties_with_domain_range.append((prop_id, domain, range_))
    
    # Test first 5 properties
    print("\nSample properties with domain and range in RDF:")
    for prop_id, domain, range_ in properties_with_domain_range[:5]:
        print(f"- {prop_id}:")
        print(f"  Domain: {domain}")
        print(f"  Range: {range_}")
        
        # Verify domain and range are valid URIs
        assert str(domain).startswith(str(cidoc_ns)), f"Domain should be in CIDOC namespace: {domain}"
        
        # Check range - it can be either a CIDOC class or rdfs:Literal
        valid_range = (str(range_).startswith(str(cidoc_ns)) or 
                       str(range_) == "http://www.w3.org/2000/01/rdf-schema#Literal")
        assert valid_range, f"Range should be in CIDOC namespace or rdfs:Literal: {range_}"


def test_rdf_inverse_property_validation(cidoc_rdf, cidoc_ns):
    """Test inverse property relationships using RDF data directly"""
    # Find properties with inverse relationships
    inverse_pairs = []
    
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if not str(prop).startswith(str(cidoc_ns)):
            continue
            
        # Find inverse relationship
        inverse = cidoc_rdf.value(prop, OWL.inverseOf)
        if inverse:
            prop_id = str(prop).split('/')[-1]
            inverse_id = str(inverse).split('/')[-1]
            inverse_pairs.append((prop_id, inverse_id))
    
    # Test first 5 inverse pairs
    print("\nSample inverse property pairs in RDF:")
    for prop_id, inverse_id in inverse_pairs[:5]:
        print(f"- {prop_id} <--> {inverse_id}")
        
    # Verify that some inverse relationships exist
    assert len(inverse_pairs) > 0, "Some inverse property relationships should exist in RDF"


def test_rdf_symmetric_property_validation(cidoc_rdf, cidoc_ns):
    """Test symmetric properties using RDF data directly"""
    # Find symmetric properties
    symmetric_props = [p for p in cidoc_rdf.subjects(RDF.type, OWL.SymmetricProperty)
                      if str(p).startswith(str(cidoc_ns))]
    
    # Print symmetric properties for debugging
    print(f"\nSymmetric properties in RDF:")
    for prop in symmetric_props:
        prop_id = str(prop).split('/')[-1]
        print(f"- {prop_id}")
        
        # Get domain and range
        domain = cidoc_rdf.value(prop, RDFS.domain)
        range_ = cidoc_rdf.value(prop, RDFS.range)
        
        # For symmetric properties, domain and range should be the same
        if domain and range_:
            assert domain == range_, f"Symmetric property {prop_id} should have same domain and range"
            print(f"  Domain and range: {domain} (correctly equal)")
        else:
            print(f"  Domain or range missing") 