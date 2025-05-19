import pytest
import json
import logging
from arkumu.importer.services.resource_manager import ResourceManager
from arkumu.importer.services.uri_utils import (
    RDF_BASE_URI, 
    RDFS_BASE_URI, 
    CIDOC_CRM_BASE_URI
    # XSD_BASE_URI is not used in this file after removing utility tests
)
from arkumu.metadata.models import Resource, ResourceType
from arkumu.importer.services.uri_utils import slugify_uri_part # For institution slug
# Removed: from arkumu.importer.services.importer import JSONMappingImporter, XSD_BASE_URI
# Removed: from datetime import datetime - not used after removing utility tests

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    # logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING) # No longer importer
    logging.getLogger('arkumu.importer.services.resource_manager').setLevel(logging.WARNING)
    yield

# Removed minimal_mapping_content_for_helpers and mapping_file_for_helpers fixtures

@pytest.fixture
def institution_code():
    return "HELPER_TEST_INST" # From original minimal_mapping_content

@pytest.fixture
def resource_manager_instance(institution_code):
    # ResourceManager expects a slugified institution code
    slugified_inst_code = slugify_uri_part(institution_code)
    return ResourceManager(institution_code=slugified_inst_code)

@pytest.mark.django_db
class TestResourceManagerHelpers: # Renamed class for clarity

    def test_get_or_create_rdf_term_creation(self, resource_manager_instance):
        term_name = "seeAlso"
        description = "RDF seeAlso property"
        # Call on resource_manager_instance
        resource = resource_manager_instance.get_or_create_rdf_term(term_name, description)
        
        assert resource is not None
        assert resource.uri == f"{RDF_BASE_URI}{term_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "RDF"
        assert resource.source_field == f"rdf:{term_name}"
        assert resource.literal_value == description
        # The count logic depends on how ResourceManager.get_or_create_resource handles label/type creation.
        # If it creates 1 for term, 1 for its rdf:type, 1 for its rdfs:label (if description provided), then count = 3
        # Let's assume for now the original logic holds if a description is provided for simplicity in this step.
        # Initial state of DB is empty, so we expect the term + its type + its label.
        assert Resource.objects.count() == 3 

    def test_get_or_create_rdf_term_retrieval(self, resource_manager_instance):
        term_name = "type" 
        description = "RDF type property"
        
        resource1 = resource_manager_instance.get_or_create_rdf_term(term_name, description)
        assert Resource.objects.count() == 3 # Direct assertion after first call

        # Second call should retrieve it
        resource2 = resource_manager_instance.get_or_create_rdf_term(term_name, description)
        assert resource2 is not None
        assert resource2.uri == f"{RDF_BASE_URI}{term_name}" 
        assert Resource.objects.count() == 3 # No new resource should be created
        assert resource1 == resource2 # Should be the same instance from cache or DB
        # Removed: assert resource == importer_instance.rdf_type_resource

    def test_get_or_create_rdfs_term_creation(self, resource_manager_instance):
        term_name = "comment"
        description = "RDFS comment property"
        resource = resource_manager_instance.get_or_create_rdfs_term(term_name, description)
        
        assert resource is not None
        assert resource.uri == f"{RDFS_BASE_URI}{term_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "RDFS"
        assert resource.source_field == f"rdfs:{term_name}"
        assert resource.literal_value == description
        # Similar count logic as above
        assert Resource.objects.count() == 3 

    def test_get_or_create_rdfs_term_retrieval(self, resource_manager_instance):
        term_name = "label" 
        description = "RDFS label property"

        resource1 = resource_manager_instance.get_or_create_rdfs_term(term_name, description)
        assert Resource.objects.count() == 3 # Direct assertion after first call
        
        resource2 = resource_manager_instance.get_or_create_rdfs_term(term_name, description)
        assert resource2 is not None
        assert resource2.uri == f"{RDFS_BASE_URI}{term_name}"
        assert Resource.objects.count() == 3 # No new creation
        assert resource1 == resource2
        # Removed: assert resource == importer_instance.rdfs_label_resource

    def test_get_or_create_cidoc_class_creation(self, resource_manager_instance):
        class_short_name = "E22_Man-Made_Object"
        expected_description = f"CIDOC-CRM Class: {class_short_name}"
        resource = resource_manager_instance.get_or_create_cidoc_class_resource(class_short_name)
        
        assert resource is not None
        assert resource.uri == f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        assert resource.resource_type == ResourceType.CLASS
        assert resource.source == "CIDOC-CRM"
        assert resource.source_field == f"cidoc:{class_short_name}"
        assert resource.literal_value == expected_description
        # Class itself, its rdf:type (rdfs:Class), and its rdfs:label (description)
        assert Resource.objects.count() == 3 

    def test_get_or_create_cidoc_class_retrieval(self, resource_manager_instance):
        class_short_name = "E5_Event"
        resource1 = resource_manager_instance.get_or_create_cidoc_class_resource(class_short_name)
        assert Resource.objects.count() == 3 # Direct assertion after first call

        resource2 = resource_manager_instance.get_or_create_cidoc_class_resource(class_short_name)
        assert resource2 is not None
        assert resource2.uri == f"{CIDOC_CRM_BASE_URI}{class_short_name}"
        assert Resource.objects.count() == 3 # No new creation
        assert resource1 == resource2

    def test_get_or_create_cidoc_property_creation(self, resource_manager_instance):
        property_short_name = "P1_is_identified_by"
        expected_description = f"CIDOC-CRM Property: {property_short_name}"
        resource = resource_manager_instance.get_or_create_cidoc_property_resource(property_short_name)
        
        assert resource is not None
        assert resource.uri == f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        assert resource.resource_type == ResourceType.PROPERTY
        assert resource.source == "CIDOC-CRM"
        assert resource.source_field == f"cidoc:{property_short_name}"
        assert resource.literal_value == expected_description
        # Property itself, its rdf:type (rdf:Property), and its rdfs:label (description)
        assert Resource.objects.count() == 3 

    def test_get_or_create_cidoc_property_retrieval(self, resource_manager_instance):
        property_short_name = "P2_has_type"
        resource1 = resource_manager_instance.get_or_create_cidoc_property_resource(property_short_name)
        assert Resource.objects.count() == 3 # Direct assertion after first call

        resource2 = resource_manager_instance.get_or_create_cidoc_property_resource(property_short_name)
        assert resource2 is not None
        assert resource2.uri == f"{CIDOC_CRM_BASE_URI}{property_short_name}"
        assert Resource.objects.count() == 3
        assert resource1 == resource2
