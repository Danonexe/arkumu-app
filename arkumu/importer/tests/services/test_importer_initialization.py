# Tests for JSONMappingImporter.__init__ 
import pytest
import json
import logging
from arkumu.importer.services.importer import JSONMappingImporter, DEFAULT_INSTITUTION_BASE_URI
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
    # Verify that related_sources is initialized as empty dict
    assert importer.related_sources == {}

    # Check for default_domain_class (should be None for minimal_mapping_content)
    assert importer.default_domain_class is None

    # Verify that no hardcoded time-span properties exist
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


# This test is now subsumed by test_extracts_expected_source_columns_various
# @pytest.mark.django_db
# def test_extracts_expected_source_columns(mapping_file_valid):
#     """Test that expected_source_columns are correctly extracted."""
#     importer = JSONMappingImporter(mapping_file_path=mapping_file_valid)
#     assert importer.expected_source_columns == {"col1", "col2"}

@pytest.fixture
def mapping_file_various_source_columns(tmp_path):
    content = {
        "institution": "TEST_INST",
        "mappings": [
            {"source_column": "id", "predicate": "P1"},
            {"source_column": "name", "predicate": "P2"},
            {"source_column": "description"}, # Predicate missing, but source_column should still be caught
            {"predicate": "P4_has_time-span"}, # No source_column
            {"source_column": "id"}, # Duplicate source_column
            {
                "source_column": "parent_col", 
                "predicate": "P_PARENT",
                "object_class": "E_PARENT",
                "object_properties": [
                    {"source_column": "child_col_1", "predicate": "P_CHILD_1"},
                    {"predicate": "P_CHILD_2", "fixed_value": "foo"}, # No source_column
                    {"source_column": "child_col_2", "predicate": "P_CHILD_3"},
                    {"source_column": "name"} # Duplicate of a top-level one
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

@pytest.mark.django_db
def test_import_data_error_conditions(importer_for_main_flow, mock_csv_data_basic):
    """Test specific error conditions for import_data related to primary class determination."""
    # This importer_for_main_flow uses main_flow_mapping_content which does NOT have a top-level "domain"
    assert importer_for_main_flow.default_domain_class is None

    # Case 1: No argument and no domain in mapping
    with pytest.raises(ValueError, match="Primary subject class must be provided"):
        importer_for_main_flow.import_data(mock_csv_data_basic, primary_subject_class_short_name=None)
    
    with pytest.raises(ValueError, match="Primary subject class must be provided"):
        importer_for_main_flow.import_data(mock_csv_data_basic, primary_subject_class_short_name="")

    # Case 2: Argument provided, should override (even if domain in mapping existed)
    # (Tested implicitly by other main_flow tests that pass primary_subject_class_short_name)
    # For explicit test, we'd need a mapping with a domain, then override it.
    # Let's add a quick check here for clarity with a mapping that *does* have a domain.
    content_with_domain = {
        "institution": "DOMAIN_TEST",
        "domain": "E7_Activity",
        "mappings": [{"source_column": "id", "predicate": "P1"}]
    }
    temp_file_path = importer_for_main_flow.mapping_config_path # A bit hacky to get a tmp_path context
    # Ideally, create a new temp file path
    import os
    dir_path = os.path.dirname(temp_file_path)
    domain_map_path = os.path.join(dir_path, "domain_map_for_override.json")

    with open(domain_map_path, 'w') as f:
        json.dump(content_with_domain, f)
    
    importer_with_domain = JSONMappingImporter(domain_map_path)
    assert importer_with_domain.default_domain_class == "E7_Activity"

    # Call with explicit override, should not raise error and should use the override
    # For this, we need a way to check which class was actually used. 
    # The successful execution without error and processing based on "E5_Event" is an indirect check.
    # To be more direct, one might need to inspect logs or mock _get_or_create_cidoc_class_resource
    # For now, ensuring it doesn't fail and uses the argument is the main goal.
    try:
        # This will fail if it tries to use E7_Activity with mock_csv_data_basic if it has no 'id' col mapped for it
        # or if E5_Event is expected by underlying resource creation logic for mock_csv_data_basic's structure
        # The point is to ensure the argument `primary_subject_class_short_name` is respected.
        importer_with_domain.import_data(mock_csv_data_basic, primary_subject_class_short_name="E5_Event")
        # If it reaches here, it used E5_Event. If it used E7_Activity from domain, it might error differently
        # or succeed if E7_Activity also fits. This test is more about call path than deep data validation here.
    except Exception as e:
        # Catching generic Exception to see if it tried to use default and failed for other reasons.
        # A more specific check would be to mock the _get_or_create_cidoc_class_resource to see what it's called with.
        pytest.fail(f"import_data with explicit override failed: {e}") 

    # Clean up temp file
    if os.path.exists(domain_map_path):
        os.remove(domain_map_path) 