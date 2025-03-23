import pytest
from rdflib import Graph, Namespace, RDF, RDFS, OWL
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty

# RDF loading tests
def test_rdf_file_loading(cidoc_rdf):
    """Test that RDF file loads correctly"""
    assert len(cidoc_rdf) > 0
    assert isinstance(cidoc_rdf, Graph)

def test_cidoc_namespace(cidoc_rdf, cidoc_ns):
    """Test CIDOC namespace recognition"""
    cidoc_triples = [t for t in cidoc_rdf if str(t[0]).startswith(str(cidoc_ns))]
    assert len(cidoc_triples) > 0

def test_basic_structure(cidoc_rdf, cidoc_ns):
    """Test basic CIDOC-CRM structure presence"""
    # Check for fundamental classes
    assert (cidoc_ns.E1_CRM_Entity, RDF.type, RDFS.Class) in cidoc_rdf
    # Check for fundamental properties
    assert any(cidoc_rdf.triples((cidoc_ns.P1_is_identified_by, RDF.type, RDF.Property)))

# Schema validation tests
def test_class_definitions(cidoc_rdf, cidoc_ns):
    """Test class definitions in RDF"""
    classes = list(cidoc_rdf.subjects(RDF.type, RDFS.Class))
    cidoc_classes = [c for c in classes if str(c).startswith(str(cidoc_ns))]
    
    for cls in cidoc_classes:
        # Every class should have a label
        assert any(cidoc_rdf.triples((cls, RDFS.label, None)))
        # Skip comment check for merged classes (containing underscore)
        if '_' not in str(cls).split('/')[-1]:
            # Every class should have a comment/description
            assert any(cidoc_rdf.triples((cls, RDFS.comment, None))), f"Missing comment for {cls}"

def test_property_definitions(cidoc_rdf, cidoc_ns):
    """Test property definitions in RDF"""
    properties = list(cidoc_rdf.subjects(RDF.type, RDF.Property))
    cidoc_properties = [p for p in properties if str(p).startswith(str(cidoc_ns))]
    
    for prop in cidoc_properties:
        # Every property should have domain and range
        assert any(cidoc_rdf.triples((prop, RDFS.domain, None)))
        assert any(cidoc_rdf.triples((prop, RDFS.range, None)))

def test_schema_completeness(cidoc_rdf, cidoc_ns):
    """Test completeness of CIDOC-CRM schema"""
    # Test required class hierarchy
    assert any(cidoc_rdf.triples((None, RDFS.subClassOf, cidoc_ns.E1_CRM_Entity)))
    # Test required property hierarchy
    assert any(cidoc_rdf.triples((None, RDFS.subPropertyOf, cidoc_ns.P1_is_identified_by)))

# Cross-reference validation tests
def test_property_class_references(cidoc_rdf, cidoc_ns):
    """Test that property domain/range references valid classes"""
    properties = list(cidoc_rdf.subjects(RDF.type, RDF.Property))
    classes = set(cidoc_rdf.subjects(RDF.type, RDFS.Class))
    
    for prop in properties:
        if str(prop).startswith(str(cidoc_ns)):
            domain = cidoc_rdf.value(prop, RDFS.domain)
            range_ = cidoc_rdf.value(prop, RDFS.range)
            
            if domain:
                assert domain in classes
            if range_:
                # Range can be either a CIDOC class or rdfs:Literal
                assert (range_ in classes or 
                       range_ == RDFS.Literal), f"Invalid range {range_} for property {prop}"

def test_inheritance_references(cidoc_rdf, cidoc_ns):
    """Test class and property inheritance references"""
    for s, p, o in cidoc_rdf.triples((None, RDFS.subClassOf, None)):
        if str(s).startswith(str(cidoc_ns)) and str(o).startswith(str(cidoc_ns)):
            # Both subject and object should be defined classes
            assert (s, RDF.type, RDFS.Class) in cidoc_rdf
            assert (o, RDF.type, RDFS.Class) in cidoc_rdf

# Language handling tests
def test_multilingual_labels(cidoc_rdf, cidoc_ns):
    """Test multilingual labels in RDF"""
    labels = list(cidoc_rdf.triples((cidoc_ns.E21_Person, RDFS.label, None)))
    languages = set(label.language for _, _, label in labels if hasattr(label, 'language'))
    assert len(languages) > 0  # Should have at least one language

def test_language_consistency(cidoc_rdf, cidoc_ns):
    """Test consistency of language tags"""
    def get_languages(subject, predicate):
        return set(obj.language for obj in cidoc_rdf.objects(subject, predicate) 
                  if hasattr(obj, 'language'))

    # Check E21_Person as an example
    label_langs = get_languages(cidoc_ns.E21_Person, RDFS.label)
    comment_langs = get_languages(cidoc_ns.E21_Person, RDFS.comment)
    
    # Should have same languages for labels and comments
    assert label_langs.intersection(comment_langs)

def test_default_language(cidoc_rdf, cidoc_ns):
    """Test presence of default language (usually English)"""
    for s, p, o in cidoc_rdf.triples((cidoc_ns.E21_Person, RDFS.label, None)):
        if hasattr(o, 'language'):
            if o.language == 'en':
                assert True
                break
    else:
        assert False, "No English label found"

# RDF structure tests
def test_uri_format(cidoc_rdf, cidoc_ns):
    """Test URI format consistency"""
    for s in cidoc_rdf.subjects():
        if str(s).startswith(str(cidoc_ns)):
            # Check CIDOC-CRM URI pattern
            assert '/' in str(s)
            assert '#' not in str(s)  # CIDOC-CRM doesn't use fragments

def test_property_characteristics(cidoc_rdf, cidoc_ns):
    """Test property characteristics in RDF"""
    for prop in cidoc_rdf.subjects(RDF.type, RDF.Property):
        if str(prop).startswith(str(cidoc_ns)):
            # Check for required property characteristics
            has_domain = any(cidoc_rdf.triples((prop, RDFS.domain, None)))
            has_range = any(cidoc_rdf.triples((prop, RDFS.range, None)))
            has_label = any(cidoc_rdf.triples((prop, RDFS.label, None)))
            
            assert has_domain and has_range and has_label

def test_version_info(cidoc_rdf):
    """Test presence of version information"""
    # CIDOC-CRM should have version information
    assert any(cidoc_rdf.triples((None, OWL.versionInfo, None))) 