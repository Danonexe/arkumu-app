from django.test import TestCase
import pytest
from django.core.exceptions import ValidationError
from django.core.cache import cache
from ..validators import (
    CIDOCSchemaValidator,
    validate_cidoc_entity,
    validate_cidoc_relationship,
    validate_property_type,
    get_valid_properties
)
from pathlib import Path
from rdflib import Graph, Namespace, RDFS, RDF, OWL

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the cache before each test"""
    cache.clear()
    yield
    cache.clear()

class TestCIDOCSchemaValidator:
    def test_schema_loading(self):
        """Test that the schema loads successfully"""
        validator = CIDOCSchemaValidator.get_instance()
        assert validator.graph is not None
        assert len(validator.graph) > 0  # Check if graph contains triples

    def test_singleton_pattern(self):
        """Test that get_instance returns the same cached instance"""
        # Clear cache first to ensure clean state
        CIDOCSchemaValidator.clear_cache()
        
        # Get first instance
        validator1 = CIDOCSchemaValidator.get_instance()
        # Get second instance (should be same object from cache)
        validator2 = CIDOCSchemaValidator.get_instance()
        assert validator1 is validator2

    def test_namespaces(self):
        """Test that namespaces are properly configured"""
        validator = CIDOCSchemaValidator.get_instance()
        assert str(validator.CRM) == "http://www.cidoc-crm.org/cidoc-crm/"
        assert str(validator.CRMDIG) == "http://www.ics.forth.gr/isl/CRMdig/"

    def test_schema_loading_method(self):
        """Test the _load_schema_files method specifically"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Clear the graph to test loading
        validator.graph = Graph()
        
        # Test the loading method
        validator._load_schema_files()
        
        # Verify the files were loaded correctly
        assert len(validator.graph) > 0, "Graph is empty after loading schemas"
        
        # Check if namespaces were bound correctly
        namespaces = dict(validator.graph.namespaces())
        assert 'crm' in namespaces, "CRM namespace not bound"
        assert 'crmdig' in namespaces, "CRMdig namespace not bound"
        
        # Verify some basic content from both schemas
        crm_class = validator.CRM['E21_Person']
        crmdig_class = validator.CRMDIG['D1_Digital_Object']
        
        assert (crm_class, RDF.type, RDFS.Class) in validator.graph, "CIDOC-CRM class not found"
        assert (crmdig_class, RDF.type, RDFS.Class) in validator.graph, "CRMdig class not found"

class TestEntityValidation:
    def test_valid_entity_classes(self):
        """Test validation of valid CIDOC entity classes"""
        valid_classes = ['E21_Person', 'E22_Human-Made_Object', 'D1_Digital_Object']
        for class_id in valid_classes:
            validate_cidoc_entity(class_id)  # Should not raise

    def test_invalid_entity_classes(self):
        """Test validation of invalid CIDOC entity classes"""
        invalid_classes = ['E999_Invalid', 'NotAClass', 'D999_Invalid']
        for class_id in invalid_classes:
            with pytest.raises(ValidationError):
                validate_cidoc_entity(class_id)

class TestRelationshipValidation:
    def test_valid_relationships(self):
        """Test validation of valid CIDOC relationships"""
        valid_relationships = [
            # Core CIDOC-CRM relationships
            ('P1_is_identified_by', 'E21_Person', 'E41_Appellation'),  # Person identified by name
            ('P2_has_type', 'E18_Physical_Thing', 'E55_Type'),  # Physical thing has type
            ('P67_refers_to', 'E89_Propositional_Object', 'E1_CRM_Entity'),  # Document refers to entity
            
            # Physical object relationships
            ('P46_is_composed_of', 'E19_Physical_Object', 'E19_Physical_Object'),  # Physical composition
            ('P49_has_former_or_current_keeper', 'E18_Physical_Thing', 'E39_Actor'),  # Ownership/custody
            
            # Digital relationships from CRMdig
            ('L1_digitized', 'D2_Digitization_Process', 'E18_Physical_Thing'),  # Digitization of physical object
            ('L19_stores', 'D13_Digital_Information_Carrier', 'D1_Digital_Object'),  # Digital storage
            ('L23_used_software_or_firmware', 'D7_Digital_Machine_Event', 'D14_Software'),  # Software usage
        ]
        
        for prop_id, domain, range_class in valid_relationships:
            validate_cidoc_relationship(prop_id, domain, range_class)  # Should not raise

    def test_invalid_relationships(self):
        """Test validation of invalid CIDOC relationships"""
        invalid_relationships = [
            # Wrong domain
            ('P1_is_identified_by', 'E55_Type', 'E41_Appellation'),  # Type cannot be identified by appellation
            
            # Wrong range
            ('P2_has_type', 'E18_Physical_Thing', 'E21_Person'),  # Person is not a type
            
            # Non-existent property
            ('P999_not_real', 'E1_CRM_Entity', 'E1_CRM_Entity'),
            
            # Digital relationship with wrong domain
            ('L1_digitized', 'E21_Person', 'E18_Physical_Thing'),  # Person cannot digitize
            
            # Digital relationship with wrong range
            ('L19_stores', 'D13_Digital_Information_Carrier', 'E21_Person')  # Cannot store a person digitally
        ]
        
        for prop_id, domain, range_class in invalid_relationships:
            with pytest.raises((ValueError, ValidationError)):  # Allow either exception type
                validate_cidoc_relationship(prop_id, domain, range_class)

class TestPropertyValidation:
    def test_property_type_validation(self):
        """Test validation of property value types"""
        # Test string property
        validate_property_type('P1_is_identified_by', 'Test String')  # Should not raise
        
        # Test numeric property (if applicable in your schema)
        validate_property_type('P90_has_value', '42')  # Should not raise

    def test_get_valid_properties(self):
        """Test retrieving valid properties for a class"""
        # Test for a common class like E21_Person
        properties = get_valid_properties('E21_Person')
        assert len(properties) > 0
        # Verify some expected properties are present
        property_ids = {str(p).split('/')[-1] for p in properties}
        assert 'P1_is_identified_by' in property_ids

class TestSchemaLoading:
    def test_schema_files_exist(self):
        """Test that the schema files exist in the expected location"""
        schema_dir = Path(__file__).parent.parent / 'schema'
        
        cidoc_file = schema_dir / 'CIDOC_CRM_v7.1.1.rdf'
        crmdig_file = schema_dir / 'CRMdig_v3.2.1.rdfs'
        
        assert cidoc_file.exists(), "CIDOC-CRM schema file not found"
        assert crmdig_file.exists(), "CRMdig schema file not found"

    def test_schema_namespaces(self):
        """Test that the required namespaces are properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Check CIDOC-CRM namespace
        assert str(validator.CRM) == "http://www.cidoc-crm.org/cidoc-crm/"
        
        # Check CRMdig namespace
        assert str(validator.CRMDIG) == "http://www.ics.forth.gr/isl/CRMdig/"
        
        # Convert generator to list for easier assertion
        namespaces = list(validator.graph.namespaces())
        assert any(prefix == 'crm' and uri == str(validator.CRM) for prefix, uri in namespaces)
        assert any(prefix == 'crmdig' and uri == str(validator.CRMDIG) for prefix, uri in namespaces)

    def test_core_classes_loaded(self):
        """Test that core CIDOC-CRM classes are properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        CRM = validator.CRM

        # Test some fundamental CIDOC-CRM classes
        core_classes = [
            'E1_CRM_Entity',
            'E18_Physical_Thing',
            'E21_Person',
            'E55_Type'
        ]
        
        for class_name in core_classes:
            class_uri = CRM[class_name]
            # Check if class exists in graph
            assert (class_uri, RDF.type, RDFS.Class) in validator.graph, f"Class {class_name} not found in schema"

    def test_digital_classes_loaded(self):
        """Test that CRMdig classes are properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        CRMDIG = validator.CRMDIG

        # Test some fundamental CRMdig classes
        digital_classes = [
            'D1_Digital_Object',
            'D2_Digitization_Process',
            'D8_Digital_Device'
        ]
        
        for class_name in digital_classes:
            class_uri = CRMDIG[class_name]
            # Check if class exists in graph
            assert (class_uri, RDF.type, RDFS.Class) in validator.graph, f"Class {class_name} not found in schema"

    def test_properties_loaded(self):
        """Test that properties are properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        CRM = validator.CRM
        
        # Test some fundamental CIDOC-CRM properties
        properties = [
            'P1_is_identified_by',
            'P2_has_type',
            'P46_is_composed_of'
        ]
        
        for prop_name in properties:
            prop_uri = CRM[prop_name]
            # Check if property exists and has domain/range
            assert (prop_uri, RDF.type, RDF.Property) in validator.graph, f"Property {prop_name} not found in schema"
            assert any(validator.graph.triples((prop_uri, RDFS.domain, None))), f"Property {prop_name} has no domain"
            assert any(validator.graph.triples((prop_uri, RDFS.range, None))), f"Property {prop_name} has no range"

    def test_class_hierarchy(self):
        """Test that class hierarchy is properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        CRM = validator.CRM
        
        # Test some known subclass relationships
        subclass_pairs = [
            ('E21_Person', 'E39_Actor'),  # Person is subclass of Actor
            ('E22_Human-Made_Object', 'E19_Physical_Object'),  # Human-Made Object is subclass of Physical Object
        ]
        
        for child, parent in subclass_pairs:
            child_uri = CRM[child]
            parent_uri = CRM[parent]
            assert (child_uri, RDFS.subClassOf, parent_uri) in validator.graph, \
                f"Missing subclass relationship: {child} -> {parent}"

    def test_property_inverses(self):
        """Test that property inverses are properly loaded"""
        validator = CIDOCSchemaValidator.get_instance()
        CRM = validator.CRM
        
        # Test some known inverse relationships
        inverse_pairs = [
            ('P46_is_composed_of', 'P46i_forms_part_of'),
            ('P49_has_former_or_current_keeper', 'P49i_is_former_or_current_keeper_of')
        ]
        
        for prop, inverse in inverse_pairs:
            prop_uri = CRM[prop]
            inverse_uri = CRM[inverse]
            assert (prop_uri, OWL.inverseOf, inverse_uri) in validator.graph or \
                   (inverse_uri, OWL.inverseOf, prop_uri) in validator.graph, \
                f"Missing inverse relationship between {prop} and {inverse}"

    def test_schema_paths():
        """Debug test to print actual paths"""
        validator_path = Path(__file__).parent / 'schema'
        test_path = Path(__file__).parent.parent / 'schema'
        print(f"\nValidator looking in: {validator_path}")
        print(f"Test looking in: {test_path}")
        print(f"Files exist in validator path: {list(validator_path.glob('*.rd*'))}")
        print(f"Files exist in test path: {list(test_path.glob('*.rd*'))}")

