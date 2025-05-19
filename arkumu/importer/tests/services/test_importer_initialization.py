# Tests for JSONMappingImporter initialization and related error handling
import pytest
import json
import logging
# from arkumu.importer.services.importer import JSONMappingImporter, DEFAULT_INSTITUTION_BASE_URI # Old import
from arkumu.importer.services.importer import JSONMappingImporter # Keep JSONMappingImporter
from arkumu.importer.services.uri_utils import DEFAULT_INSTITUTION_BASE_URI # New import for constant
from arkumu.cidoc.models import Resource
# For type checking of Resource instances       

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING)
    yield

@pytest.fixture
def minimal_mapping_content():
    return {
        "institution": "TEST_INST",
        "mappings": [
            {"source_column": "col1", "predicate": "P1"},
            {"source_column": "col2", "predicate": "P2"}
        ]
    }

@pytest.fixture
def mapping_file_valid(tmp_path, minimal_mapping_content):
    file_path = tmp_path / "valid_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(minimal_mapping_content, f)
    return str(file_path)

@pytest.fixture
def mapping_file_no_institution(tmp_path):
    content = {
        "mappings": [
            {"source_column": "col1", "predicate": "P1"}
        ]
    }
    file_path = tmp_path / "no_institution_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(content, f)
    return str(file_path)

@pytest.fixture
def related_source_data():
    return {
        "related_table": [
            {"id": "1", "value": "First value", "language": "en"},
            {"id": "2", "value": "Second value", "language": "de"}
        ]
    }

@pytest.mark.django_db
def test_successful_initialization(mapping_file_valid, minimal_mapping_content):
    """Test successful initialization with a valid mapping file."""
    importer = JSONMappingImporter(mapping_file_path=mapping_file_valid)
    assert importer.mapping_config == minimal_mapping_content
    assert importer.institution_code == "TEST_INST"
    assert importer.source_format == "N/A" # Default
    assert importer.mappings == minimal_mapping_content["mappings"]
    assert importer.institution_base_uri == DEFAULT_INSTITUTION_BASE_URI
    assert isinstance(importer.rdf_type_resource, Resource)
    assert isinstance(importer.rdfs_label_resource, Resource)
    assert importer.related_sources == {}
    assert importer.default_domain_class is None
    assert not hasattr(importer, 'begin_of_begin_predicate')
    assert not hasattr(importer, 'end_of_end_predicate')
    assert not hasattr(importer, 'beginning_is_qualified_predicate')
    assert not hasattr(importer, 'end_is_qualified_predicate')

@pytest.mark.django_db
def test_initialization_with_related_sources(mapping_file_valid, related_source_data):
    """Test initialization with related sources data."""
    importer = JSONMappingImporter(
        mapping_file_path=mapping_file_valid,
        related_sources=related_source_data
    )
    assert importer.related_sources == related_source_data
    assert importer.related_sources["related_table"][0]["id"] == "1"
    assert importer.related_sources["related_table"][1]["value"] == "Second value"

@pytest.mark.django_db
def test_initialization_with_source_format_in_mapping(tmp_path, minimal_mapping_content):
    """Test that source_format is read from mapping if present."""
    custom_content = minimal_mapping_content.copy()
    custom_content["source_format"] = "CustomCSV_v2"
    file_path = tmp_path / "source_format_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(custom_content, f)
    importer = JSONMappingImporter(mapping_file_path=str(file_path))
    assert importer.source_format == "CustomCSV_v2"

@pytest.mark.django_db
def test_initialization_with_custom_base_uri(mapping_file_valid):
    """Test initialization with a custom institution_base_uri."""
    custom_uri = "http://my.custom.uri/data/"
    importer = JSONMappingImporter(mapping_file_path=mapping_file_valid, institution_base_uri=custom_uri)
    assert importer.institution_base_uri == custom_uri
    custom_uri_no_slash = "http://my.custom.uri/data"
    importer_no_slash = JSONMappingImporter(mapping_file_path=mapping_file_valid, institution_base_uri=custom_uri_no_slash)
    assert importer_no_slash.institution_base_uri == custom_uri # Should add trailing slash

@pytest.fixture
def mapping_file_various_source_columns(tmp_path):
    content = {
        "institution": "TEST_INST",
        "mappings": [
            {"source_column": "id", "predicate": "P1"},
            {"source_column": "name", "predicate": "P2"},
            {"source_column": "description"},
            {"predicate": "P4_has_time-span"},
            {"source_column": "id"},
            {
                "source_column": "parent_col", 
                "predicate": "P_PARENT",
                "object_class": "E_PARENT",
                "object_properties": [
                    {"source_column": "child_col_1", "predicate": "P_CHILD_1"},
                    {"predicate": "P_CHILD_2", "fixed_value": "foo"},
                    {"source_column": "child_col_2", "predicate": "P_CHILD_3"},
                    {"source_column": "name"}
                ]
            }
        ]
    }
    file_path = tmp_path / "various_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(content, f)
    return str(file_path)

@pytest.mark.django_db
def test_extracts_expected_source_columns_various(mapping_file_various_source_columns):
    """Test extraction with various source_column scenarios including duplicates, missing, and nested ones."""
    importer = JSONMappingImporter(mapping_file_path=mapping_file_various_source_columns)
    assert importer.expected_source_columns == {
        "id", "name", "description", "parent_col", "child_col_1", "child_col_2"
    }

@pytest.mark.django_db
def test_initialization_missing_institution_key(mapping_file_no_institution):
    """Test initialization fails if 'institution' key is missing in mapping."""
    with pytest.raises(ValueError, match="Mapping JSON must contain an 'institution' code."):
        JSONMappingImporter(mapping_file_path=mapping_file_no_institution)

@pytest.mark.django_db
def test_initialization_non_existent_file():
    """Test initialization fails if mapping file does not exist."""
    non_existent_path = "/this/path/does/not/exist/foobar.json"
    with pytest.raises(FileNotFoundError):
        JSONMappingImporter(mapping_file_path=non_existent_path)

@pytest.mark.django_db
def test_rdf_rdfs_terms_creation(mapping_file_valid):
    """Verify rdf:type and rdfs:label resources are available after init."""
    importer = JSONMappingImporter(mapping_file_path=mapping_file_valid)
    assert importer.rdf_type_resource is not None
    assert importer.rdf_type_resource.uri == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    assert importer.rdfs_label_resource is not None
    assert importer.rdfs_label_resource.uri == "http://www.w3.org/2000/01/rdf-schema#label"

@pytest.mark.django_db
def test_initialization_with_domain_in_mapping(tmp_path, minimal_mapping_content):
    """Test that default_domain_class is read from mapping if present."""
    custom_content = minimal_mapping_content.copy()
    custom_content["domain"] = "E21_Person"
    file_path = tmp_path / "domain_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(custom_content, f)
    importer = JSONMappingImporter(mapping_file_path=str(file_path))
    assert importer.default_domain_class == "E21_Person"

# TODO: If any test here is duplicated in other files, consolidate in the next step. 