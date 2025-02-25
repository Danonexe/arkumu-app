from django.test import TestCase
import pytest
from django.core.exceptions import ValidationError
from django.core.cache import cache
from arkumu.cidoc.validators import (
    CIDOCSchemaValidator,
    validate_cidoc_entity,
    validate_cidoc_relationship,
    validate_property_type,
    get_valid_properties,           
    validate_property_cardinality
)
from pathlib import Path
from rdflib import Graph, Namespace, RDFS, RDF, OWL
from pytest_mock import mocker
from datetime import date, datetime, time

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

    def test_verify_classes_exist(self):
        """Test _verify_classes_exist method"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Test valid classes
        domain_uri, range_uri = validator._verify_classes_exist('E21_Person', 'E41_Appellation')
        assert domain_uri == validator.CRM['E21_Person']
        assert range_uri == validator.CRM['E41_Appellation']
        
        # Test invalid classes
        with pytest.raises(ValidationError, match="Domain class does not exist"):
            validator._verify_classes_exist('E999_Invalid', 'E41_Appellation')
            
        with pytest.raises(ValidationError, match="Range class does not exist"):
            validator._verify_classes_exist('E21_Person', 'E999_Invalid')

    def test_verify_digital_compatibility(self):
        """Test _verify_digital_compatibility method"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Test valid digital combinations
        validator._verify_digital_compatibility(
            'L1_digitized', 'D2_Digitization_Process', 'E18_Physical_Thing'
        )  # Should not raise
        
        # Test invalid digital combinations
        with pytest.raises(ValidationError, match="Digital property .* cannot be used with non-digital classes"):
            validator._verify_digital_compatibility(
                'L1_digitized', 'E21_Person', 'E18_Physical_Thing'
            )

    def test_verify_property_constraints(self):
        """Test basic property constraint validation"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Test P1_is_identified_by (domain: E1_CRM_Entity, range: E41_Appellation)
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        
        # Test exact match (should pass)
        validator._verify_property_constraints(
            prop_uri,
            validator._get_class_uri('E1_CRM_Entity'),
            validator._get_class_uri('E41_Appellation'),
            'P1_is_identified_by',
            'E1_CRM_Entity',
            'E41_Appellation'
        )
        
        # Test wrong domain (should fail)
        with pytest.raises(ValidationError, match="Invalid domain for"):
            validator._verify_property_constraints(
                prop_uri,
                validator._get_class_uri('E55_Type'),
                validator._get_class_uri('E41_Appellation'),
                'P1_is_identified_by',
                'E55_Type',
                'E41_Appellation'
            )



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
        
        # First ensure the validator has loaded the schemas
        assert len(validator.graph) > 0, "Graph is empty"
        
        # Get all namespaces from the graph
        namespaces = dict(validator.graph.namespaces())
        print("\nFound namespaces:", namespaces)  # Debug output
        
        # Check CIDOC-CRM namespace
        assert str(validator.CRM) == "http://www.cidoc-crm.org/cidoc-crm/", "CRM URI is incorrect"
        assert 'crm' in namespaces, f"'crm' prefix not found in namespaces: {namespaces}"
        assert str(namespaces['crm']) == str(validator.CRM), \
            f"CRM URI mismatch: {namespaces.get('crm')} != {validator.CRM}"
        
        # Check CRMdig namespace
        assert str(validator.CRMDIG) == "http://www.ics.forth.gr/isl/CRMdig/", "CRMdig URI is incorrect"
        assert 'crmdig' in namespaces, f"'crmdig' prefix not found in namespaces: {namespaces}"
        assert str(namespaces['crmdig']) == str(validator.CRMDIG), \
            f"CRMdig URI mismatch: {namespaces.get('crmdig')} != {validator.CRMDIG}"
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

    def test_schema_paths(self):
        """Test that schema files are in the correct location and accessible"""
        # Get the schema directory path
        schema_dir = Path(__file__).parent.parent / 'schema'
        
        # Check if schema directory exists
        assert schema_dir.exists(), f"Schema directory not found at {schema_dir}"
        assert schema_dir.is_dir(), f"{schema_dir} is not a directory"
        
        # Check specific schema files
        cidoc_file = schema_dir / 'CIDOC_CRM_v7.1.1.rdf'
        crmdig_file = schema_dir / 'CRMdig_v3.2.1.rdfs'
        
        # Test file existence
        assert cidoc_file.exists(), f"CIDOC-CRM schema file not found at {cidoc_file}"
        assert crmdig_file.exists(), f"CRMdig schema file not found at {crmdig_file}"
        
        # Test file readability
        assert cidoc_file.is_file(), f"{cidoc_file} is not a file"
        assert crmdig_file.is_file(), f"{crmdig_file} is not a file"
        
        # Print debug info if needed
        print(f"\nSchema directory: {schema_dir}")
        print(f"CIDOC file exists: {cidoc_file.exists()}")
        print(f"CRMdig file exists: {crmdig_file.exists()}")
        print(f"Found files: {list(schema_dir.glob('*.rd*'))}")




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


class TestDomainValidation:
    """Tests specifically for domain validation logic"""
    
    @pytest.fixture
    def validator(self):
        return CIDOCSchemaValidator.get_instance()

    def test_exact_domain_match(self, validator):
        """Test when domain exactly matches declared domain"""
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        validator._check_domain(
            prop_uri,
            validator._get_class_uri('E1_CRM_Entity'),
            'P1_is_identified_by',
            'E1_CRM_Entity'
        )

    def test_direct_subclass_domain(self, validator):
        """Test when domain is a direct subclass of declared domain"""
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        validator._check_domain(
            prop_uri,
            validator._get_class_uri('E77_Persistent_Item'),
            'P1_is_identified_by',
            'E77_Persistent_Item'
        )

    def test_indirect_subclass_domain(self, validator):
        """Test when domain is an indirect subclass (should fail)"""
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        with pytest.raises(ValidationError, match="Invalid domain for"):
            validator._check_domain(
                prop_uri,
                validator._get_class_uri('E21_Person'),
                'P1_is_identified_by',
                'E21_Person'
            )

    def test_unrelated_class_domain(self, validator):
        """Test when domain is an unrelated class (should fail)"""
        prop_uri = validator._get_property_uri('P1_is_identified_by')
        with pytest.raises(ValidationError, match="Invalid domain for"):
            validator._check_domain(
                prop_uri,
                validator._get_class_uri('E55_Type'),
                'P1_is_identified_by',
                'E55_Type'
            )

    def test_missing_domain_definition(self, validator):
        """Test when property has no domain defined"""
        # Create a test property without domain
        test_prop = validator.CRM['TestProperty']
        with pytest.raises(ValidationError, match="Property .* has no domain defined"):
            validator._check_domain(
                test_prop,
                validator._get_class_uri('E1_CRM_Entity'),
                'TestProperty',
                'E1_CRM_Entity'
            )

    def test_digital_class_domain(self, validator):
        """Test domain validation with digital classes"""
        prop_uri = validator._get_property_uri('L1_digitized')
        validator._check_domain(
            prop_uri,
            validator._get_class_uri('D2_Digitization_Process'),
            'L1_digitized',
            'D2_Digitization_Process'
        )

class MockQuerySet:
    def __init__(self, count):
        self._count = count
    def filter(self, **kwargs):
        return self
    def count(self):
        return self._count

class TestCacheManagement:
    """Tests for cache management functionality"""

    def test_cache_warming(self):
        """Test that caches are properly pre-warmed"""
        validator = CIDOCSchemaValidator.get_instance()
        
        # Check class cache
        assert len(validator._class_cache) > 0, "Class cache not warmed"
        assert 'E21_Person' in validator._class_cache, "Common class not cached"
        
        # Check property cache
        assert len(validator._property_cache) > 0, "Property cache not warmed"
        assert 'P1_is_identified_by' in validator._property_cache, "Common property not cached"

    def test_cache_invalidation(self):
        """Test cache clearing functionality"""
        # Get initial instance
        validator1 = CIDOCSchemaValidator.get_instance()
        initial_class_cache = validator1._class_cache.copy()
        
        # Clear cache
        CIDOCSchemaValidator.clear_cache()
        
        # Get new instance
        validator2 = CIDOCSchemaValidator.get_instance()
        
        # Verify caches are different objects
        assert validator2._class_cache is not initial_class_cache

