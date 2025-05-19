# Tests for standalone utility functions from uri_utils and data_utils
import pytest
import logging
# No need for json or JSONMappingImporter here anymore

from arkumu.importer.services.uri_utils import (
    DEFAULT_INSTITUTION_BASE_URI, 
    XSD_BASE_URI,
    slugify_uri_part, # Though not directly tested here, mint_uri uses it.
    mint_uri
)
from arkumu.importer.services.data_utils import (
    infer_datatype,
    infer_language,
    split_multi_values
)

@pytest.fixture(autouse=True)
def configure_logging():
    logging.basicConfig()
    # Adjust logger level if data_utils or uri_utils have specific loggers we want to check
    logging.getLogger('arkumu.importer.services.data_utils').setLevel(logging.WARNING)
    logging.getLogger('arkumu.importer.services.uri_utils').setLevel(logging.WARNING) # If it had one
    yield

# Fixtures for importer instance are no longer needed for these utility tests.

# TestMintUri can now directly test uri_utils.mint_uri
# It needs a base URI and a slugified institution code.
TEST_INST_SLUG = slugify_uri_part("TEST_INST") # Assuming TEST_INST was from basic_mapping_content

class TestMintUri:
    @pytest.mark.parametrize("parts,expected_suffix", [
        (("e21-person", "person123"), f"testinst/e21-person/person123"),
        (("e22-man-made-object", "Object with spaces!"), f"testinst/e22-man-made-object/object-with-spaces")
    ])
    def test_mint_uri_basic_and_special(self, parts, expected_suffix):
        # Construct expected full URI using DEFAULT_INSTITUTION_BASE_URI
        # Ensure DEFAULT_INSTITUTION_BASE_URI ends with a slash for this test construction
        base = DEFAULT_INSTITUTION_BASE_URI
        if not base.endswith('/'):
            base += '/'
        expected = base + expected_suffix
        assert mint_uri(DEFAULT_INSTITUTION_BASE_URI, TEST_INST_SLUG, *parts) == expected

    def test_mint_uri_normalization(self):
        uri1 = mint_uri(DEFAULT_INSTITUTION_BASE_URI, TEST_INST_SLUG, "e39-actor", "John Doe")
        uri2 = mint_uri(DEFAULT_INSTITUTION_BASE_URI, TEST_INST_SLUG, "e39-actor", "john doe")
        assert uri1 == uri2

class TestInferDatatype:
    @pytest.mark.parametrize("value,expected", [
        ("Just a string", f"{XSD_BASE_URI}string"),
        (42, f"{XSD_BASE_URI}integer"),
        (42.5, f"{XSD_BASE_URI}float"),
        ("2023-01-15", f"{XSD_BASE_URI}date"),
        ("2023-01-15T14:30:00", f"{XSD_BASE_URI}dateTime")
    ])
    def test_infer_datatype_various(self, value, expected):
        assert infer_datatype(value) == expected

class TestInferLanguage:
    def test_infer_language_rule_and_column(self):
        rule_en = {"language": "en", "language_column": "lang_col"}
        rule_col = {"language_column": "lang_col"}
        row_data = {"text": "Text", "lang_col": "fr"}
        assert infer_language(rule_en, row_data) == "en"
        assert infer_language(rule_col, row_data) == "fr"
        assert infer_language({}, {}) is None

class TestSplitMultiValues:
    @pytest.mark.parametrize("rule,value,expected", [
        ({"multi_value_separator": "|"}, "a|b|c", ["a", "b", "c"]),
        ({"note": "Separated by a ';'"}, "a;b; c", ["a", "b", "c"]),
        ({}, "single", ["single"]),
        ({"multi_value_separator": ","}, "a,,b, ,c", ["a", "b", "c"])
    ])
    def test_split_multi_values(self, rule, value, expected):
        assert split_multi_values(rule, value) == expected
    
    def test_split_multi_values_non_string(self):
        assert split_multi_values({}, 42) == [42]
        assert split_multi_values({}, None) == [None] 