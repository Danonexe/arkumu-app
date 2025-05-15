import pytest
import json
import logging
from arkumu.importer.services.importer import (
    JSONMappingImporter, 
    RDF_BASE_URI, 
    RDFS_BASE_URI, 
    CIDOC_CRM_BASE_URI,
    XSD_BASE_URI
)
from arkumu.cidoc.models import Resource, ResourceType
from datetime import datetime

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING)
    yield

@pytest.fixture
def minimal_mapping_content_for_helpers(): # Renamed to avoid conflict if used elsewhere
    return {
        "institution": "HELPER_TEST_INST",
        "mappings": [] # Mappings content not relevant for these helpers
    }

@pytest.fixture
def mapping_file_for_helpers(tmp_path, minimal_mapping_content_for_helpers):
    file_path = tmp_path / "helper_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(minimal_mapping_content_for_helpers, f)
    return str(file_path)

@pytest.fixture
def importer_instance(mapping_file_for_helpers):
    return JSONMappingImporter(mapping_file_path=mapping_file_for_helpers)

@pytest.mark.django_db
class TestImporterResourceHelpers:

    def test_get_or_create_rdf_term_creation(self, importer_instance):
        term_name = "seeAlso"
        description = "RDF seeAlso property"
        resource = importer_instance._get_or_create_rdf_term(term_name, description)
        
        assert resource is not None
        assert resource.uri == f"{RDF_BASE_URI}{term_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "RDF"
        assert resource.source_field == f"rdf:{term_name}"
        assert resource.literal_value == description
        assert Resource.objects.count() == 1 + 2 # 1 for seeAlso, 2 for pre-cached type/label

    def test_get_or_create_rdf_term_retrieval(self, importer_instance):
        term_name = "type" # This one is pre-cached in __init__
        description = "RDF type property"
        initial_count = Resource.objects.count()
        
        resource = importer_instance._get_or_create_rdf_term(term_name, description)
        assert resource is not None
        assert resource.uri == f"{RDF_BASE_URI}{term_name}" 
        assert Resource.objects.count() == initial_count # No new resource should be created
        assert resource == importer_instance.rdf_type_resource # Should be the pre-cached one

    def test_get_or_create_rdfs_term_creation(self, importer_instance):
        term_name = "comment"
        description = "RDFS comment property"
        resource = importer_instance._get_or_create_rdfs_term(term_name, description)
        
        assert resource is not None
        assert resource.uri == f"{RDFS_BASE_URI}{term_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "RDFS"
        assert resource.source_field == f"rdfs:{term_name}"
        assert resource.literal_value == description
        assert Resource.objects.count() == 1 + 2 # 1 for comment, 2 for pre-cached type/label

    def test_get_or_create_rdfs_term_retrieval(self, importer_instance):
        term_name = "label" # This one is pre-cached in __init__
        description = "RDFS label property"
        initial_count = Resource.objects.count()

        resource = importer_instance._get_or_create_rdfs_term(term_name, description)
        assert resource is not None
        assert resource.uri == f"{RDFS_BASE_URI}{term_name}"
        assert Resource.objects.count() == initial_count
        assert resource == importer_instance.rdfs_label_resource

    def test_get_or_create_cidoc_class_creation(self, importer_instance):
        class_short_name = "E22_Man-Made_Object"
        expected_description = f"CIDOC-CRM Class: {class_short_name}"
        resource = importer_instance._get_or_create_cidoc_class_resource(class_short_name)
        
        assert resource is not None
        assert resource.uri == f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        assert resource.resource_type == ResourceType.CLASS
        assert resource.source == "CIDOC-CRM"
        assert resource.source_field == f"cidoc:{class_short_name}"
        assert resource.literal_value == expected_description
        assert Resource.objects.count() == 1 + 2

    def test_get_or_create_cidoc_class_retrieval(self, importer_instance):
        class_short_name = "E5_Event"
        initial_count = Resource.objects.count()
        resource1 = importer_instance._get_or_create_cidoc_class_resource(class_short_name)
        count_after_first_call = Resource.objects.count()
        assert count_after_first_call == initial_count + 1
        
        resource2 = importer_instance._get_or_create_cidoc_class_resource(class_short_name)
        assert resource2 is not None
        assert resource2.uri == f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        assert Resource.objects.count() == count_after_first_call # No new creation
        assert resource1 == resource2

    def test_get_or_create_cidoc_property_creation(self, importer_instance):
        property_short_name = "P1_is_identified_by"
        expected_description = f"CIDOC-CRM Property: {property_short_name}"
        resource = importer_instance._get_or_create_cidoc_property_resource(property_short_name)
        
        assert resource is not None
        assert resource.uri == f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "CIDOC-CRM"
        assert resource.source_field == f"cidoc:{property_short_name}"
        assert resource.literal_value == expected_description
        assert Resource.objects.count() == 1 + 2

    def test_get_or_create_cidoc_property_retrieval(self, importer_instance):
        property_short_name = "P2_has_type"
        initial_count = Resource.objects.count()
        resource1 = importer_instance._get_or_create_cidoc_property_resource(property_short_name)
        count_after_first_call = Resource.objects.count()
        assert count_after_first_call == initial_count + 1

        resource2 = importer_instance._get_or_create_cidoc_property_resource(property_short_name)
        assert resource2 is not None
        assert resource2.uri == f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        assert Resource.objects.count() == count_after_first_call
        assert resource1 == resource2

    def test_mint_uri(self, importer_instance):
        """Test the _mint_uri helper method."""
        # Simple case
        uri = importer_instance._mint_uri("event", "1")
        expected_uri = f"{importer_instance.institution_base_uri}helper_test_inst/event/1"
        assert uri == expected_uri
        
        # Case with spaces and uppercase
        uri = importer_instance._mint_uri("Event Type", "Sample Event")
        expected_uri = f"{importer_instance.institution_base_uri}helper_test_inst/event_type/sample_event"
        assert uri == expected_uri
        
        # Multiple parts
        uri = importer_instance._mint_uri("event", "1", "appellation", "title")
        expected_uri = f"{importer_instance.institution_base_uri}helper_test_inst/event/1/appellation/title"
        assert uri == expected_uri

    def test_infer_datatype(self, importer_instance):
        """Test the _infer_datatype helper method."""
        # String
        assert importer_instance._infer_datatype("test") == f"{XSD_BASE_URI}string"
        
        # Integer
        assert importer_instance._infer_datatype(42) == f"{XSD_BASE_URI}integer"
        
        # Float
        assert importer_instance._infer_datatype(3.14) == f"{XSD_BASE_URI}float"
        
        # Date
        assert importer_instance._infer_datatype("2022-01-01") == f"{XSD_BASE_URI}date"
        
        # DateTime
        assert importer_instance._infer_datatype("2022-01-01T12:30:45") == f"{XSD_BASE_URI}dateTime"
        
        # Invalid date format falls back to string
        assert importer_instance._infer_datatype("01/01/2022") == f"{XSD_BASE_URI}string"

    def test_split_multi_values(self, importer_instance):
        """Test the _split_multi_values helper method."""
        # Test with non-string value
        assert importer_instance._split_multi_values({}, 42) == [42]
        
        # Test with explicit separator in rule
        rule = {"multi_value_separator": "|"}
        assert importer_instance._split_multi_values(rule, "a|b|c") == ["a", "b", "c"]
        
        # Test with separator hint in note
        rule = {"note": "Values separated by a ';'"}
        assert importer_instance._split_multi_values(rule, "a;b; c") == ["a", "b", "c"]
        
        # Test with no splitting needed
        rule = {}
        assert importer_instance._split_multi_values(rule, "single value") == ["single value"]
        
        # Test with empty values being filtered
        rule = {"multi_value_separator": ","}
        assert importer_instance._split_multi_values(rule, "a,,b, ,c") == ["a", "b", "c"] 