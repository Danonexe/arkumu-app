# Tests for JSONMappingImporter utility helper methods (_mint_uri, _infer_datatype, _infer_language) 

import pytest
import logging
import json
from datetime import datetime
from arkumu.importer.services.importer import (
    JSONMappingImporter,
    CIDOC_CRM_BASE_URI,
    DEFAULT_INSTITUTION_BASE_URI,
    XSD_BASE_URI
)

# Configure logging for tests
@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging to suppress debug logs during tests."""
    logging.basicConfig()
    logging.getLogger('arkumu.importer.services.importer').setLevel(logging.WARNING)
    yield

@pytest.fixture
def basic_mapping_content():
    return {
        "institution": "TEST_INST",
        "mappings": [] 
    }

@pytest.fixture
def mapping_file(tmp_path, basic_mapping_content):
    file_path = tmp_path / "test_mapping.json"
    with open(file_path, 'w') as f:
        json.dump(basic_mapping_content, f)
    return str(file_path)

@pytest.fixture
def importer(mapping_file):
    return JSONMappingImporter(mapping_file_path=mapping_file)

@pytest.mark.django_db
class TestMintUri:
    
    def test_mint_uri_basic(self, importer):
        uri = importer._mint_uri("e21-person", "person123")
        # Institution code is lowercased in the implementation
        expected_uri = f"{DEFAULT_INSTITUTION_BASE_URI}test_inst/e21-person/person123"
        assert uri == expected_uri
        
    def test_mint_uri_special_chars(self, importer):
        uri = importer._mint_uri("e22-man-made-object", "Object with spaces & special chars!")
        # Spaces become underscores, special chars are preserved
        expected_uri = f"{DEFAULT_INSTITUTION_BASE_URI}test_inst/e22-man-made-object/object_with_spaces_&_special_chars!"
        assert uri == expected_uri
        
    def test_mint_uri_with_custom_institution(self, importer):
        # Set a custom institution 
        original_institution = importer.institution_code
        importer.institution_code = "CUSTOM_INST"
        
        try:
            uri = importer._mint_uri("e55-type", "some-type")
            # Institution code is lowercased
            expected_uri = f"{DEFAULT_INSTITUTION_BASE_URI}custom_inst/e55-type/some-type"
            assert uri == expected_uri
        finally:
            # Restore original institution
            importer.institution_code = original_institution
            
    def test_mint_uri_with_empty_identifier(self, importer):
        uri = importer._mint_uri("e31-document", "")
        # Empty parts are filtered out - no trailing slash
        expected_uri = f"{DEFAULT_INSTITUTION_BASE_URI}test_inst/e31-document"
        assert uri == expected_uri
        
    def test_mint_uri_normalization(self, importer):
        # Test that case is normalized
        uri1 = importer._mint_uri("e39-actor", "John Doe")
        uri2 = importer._mint_uri("e39-actor", "john doe")
        assert uri1 == uri2
        
        # Multiple spaces are preserved as multiple underscores
        uri3 = importer._mint_uri("e39-actor", "John  Doe")
        expected_uri3 = f"{DEFAULT_INSTITUTION_BASE_URI}test_inst/e39-actor/john__doe"
        assert uri3 == expected_uri3

@pytest.mark.django_db
class TestInferDatatype:
    
    def test_infer_datatype_string(self, importer):
        datatype = importer._infer_datatype("Just a string")
        assert datatype == f"{XSD_BASE_URI}string"
        
    def test_infer_datatype_integer_string(self, importer):
        # String that looks like an integer is still a string
        datatype = importer._infer_datatype("42")
        assert datatype == f"{XSD_BASE_URI}string"
        
    def test_infer_datatype_decimal_string(self, importer):
        # String that looks like a decimal is still a string
        datatype = importer._infer_datatype("42.5")
        assert datatype == f"{XSD_BASE_URI}string"
        
    def test_infer_datatype_boolean_string(self, importer):
        # String that looks like a boolean is still a string
        datatype = importer._infer_datatype("true")
        assert datatype == f"{XSD_BASE_URI}string"
        
        datatype = importer._infer_datatype("false")
        assert datatype == f"{XSD_BASE_URI}string"
        
    def test_infer_datatype_date_string(self, importer):
        # Valid date string should be detected as a date
        datatype = importer._infer_datatype("2023-01-15")
        assert datatype == f"{XSD_BASE_URI}date"
        
    def test_infer_datatype_datetime_string(self, importer):
        # Valid datetime string should be detected as datetime
        datatype = importer._infer_datatype("2023-01-15T14:30:00")
        assert datatype == f"{XSD_BASE_URI}dateTime"
        
    def test_infer_datatype_invalid_date_string(self, importer):
        # Invalid date formats should default to string
        datatype = importer._infer_datatype("01/15/2023")
        assert datatype == f"{XSD_BASE_URI}string"
        
        datatype = importer._infer_datatype("January 15, 2023")
        assert datatype == f"{XSD_BASE_URI}string"
        
    def test_infer_datatype_actual_int(self, importer):
        datatype = importer._infer_datatype(42)
        assert datatype == f"{XSD_BASE_URI}integer"
        
    def test_infer_datatype_actual_float(self, importer):
        datatype = importer._infer_datatype(42.5)
        assert datatype == f"{XSD_BASE_URI}float"
        
    def test_infer_datatype_empty_string(self, importer):
        datatype = importer._infer_datatype("")
        assert datatype == f"{XSD_BASE_URI}string"

@pytest.mark.django_db
class TestInferLanguage:
    
    def test_infer_language_empty(self, importer):
        # Method requires rule and row_data parameters
        language = importer._infer_language({}, {})
        assert language is None
        
    def test_infer_language_with_language_in_rule(self, importer):
        # Explicit language in rule
        rule = {"language": "en"}
        row_data = {"text": "Some English text"}
        language = importer._infer_language(rule, row_data)
        assert language == "en"
        
    def test_infer_language_from_language_column(self, importer):
        # Language from column referenced in rule
        rule = {"language_column": "text_language"}
        row_data = {"text": "Bonjour le monde", "text_language": "fr"}
        language = importer._infer_language(rule, row_data)
        assert language == "fr"
        
    def test_infer_language_missing_column(self, importer):
        # Language column not found in row data
        rule = {"language_column": "missing_column"}
        row_data = {"text": "Some text"}
        language = importer._infer_language(rule, row_data)
        assert language is None
        
    def test_infer_language_precedence(self, importer):
        # Rule language takes precedence over language column
        rule = {"language": "en", "language_column": "text_language"}
        row_data = {"text": "Text", "text_language": "fr"}
        language = importer._infer_language(rule, row_data)
        assert language == "en"  # Rule language has precedence

@pytest.mark.django_db
class TestSplitMultiValues:
    
    def test_split_multi_values_non_string(self, importer):
        # Non-string values should be wrapped in a list
        values = importer._split_multi_values({}, 42)
        assert values == [42]
        
        values = importer._split_multi_values({}, None)
        assert values == [None]
        
    def test_split_multi_values_explicit_separator(self, importer):
        # Using explicit separator from rule
        rule = {"multi_value_separator": "|"}
        values = importer._split_multi_values(rule, "value1|value2|value3")
        assert values == ["value1", "value2", "value3"]
        
    def test_split_multi_values_from_note_hint(self, importer):
        # Using separator hint from note
        rule = {"note": "Values are separated by a ';'"}
        values = importer._split_multi_values(rule, "value1;value2; value3")
        assert values == ["value1", "value2", "value3"]
        
    def test_split_multi_values_empty_parts(self, importer):
        # Empty parts should be filtered out
        rule = {"multi_value_separator": ","}
        values = importer._split_multi_values(rule, "value1,,value2, ,value3")
        assert values == ["value1", "value2", "value3"]
        
    def test_split_multi_values_single_value(self, importer):
        # Single value should be wrapped in a list
        rule = {"multi_value_separator": "|"}
        values = importer._split_multi_values(rule, "single_value")
        assert values == ["single_value"]
        
    def test_split_multi_values_no_separator_specified(self, importer):
        # No separator in rule or note, should not split
        rule = {}
        values = importer._split_multi_values(rule, "value1;value2|value3")
        assert values == ["value1;value2|value3"] 