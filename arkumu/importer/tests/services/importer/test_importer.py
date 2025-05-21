import pytest
import json
import tempfile
from pathlib import Path

from arkumu.importer.services.importer.importer import JSONMappingImporter
from arkumu.importer.services.importer.resource_manager import ResourceManager
from arkumu.importer.services.importer.rule_processor import MappingRuleProcessor


@pytest.fixture
def valid_mapping_json():
    """Fixture for valid mapping JSON content"""
    return {
        "institution": "TESTINST",
        "domain": "E22_Human-Made_Object",
        "anchor_column": "ID",
        "mappings": [
            {
                "source_column": "ID",
                "property": "P1_is_identified_by",
                "range": "E42_Identifier"
            },
            {
                "source_column": "Title",
                "property": "rdfs:label",
                "range": "literal",
                "language": "en"
            },
            {
                "source_column": "ObjectType",
                "property": "P2_has_type",
                "range": "E55_Type"
            }
        ]
    }


@pytest.fixture
def temp_mapping_file(valid_mapping_json):
    """Create a temporary mapping file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(valid_mapping_json, f)
        mapping_path = f.name
    
    yield mapping_path
    
    # Cleanup
    Path(mapping_path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_importer_initialization(temp_mapping_file):
    """Test that the importer initializes correctly with real components"""
    importer = JSONMappingImporter(temp_mapping_file)
    
    # Check basic properties are initialized
    assert importer.institution_code == "TESTINST"
    # domain is not directly accessible as an attribute
    # assert importer.domain == "E22_Human-Made_Object"
    assert importer.expected_source_columns == {"ID", "Title", "ObjectType"}
    
    # Check that real components are initialized
    assert isinstance(importer.resource_manager, ResourceManager)
    assert isinstance(importer.rule_processor, MappingRuleProcessor)


@pytest.mark.django_db
def test_validate_source_headers(temp_mapping_file):
    """Test header validation with sufficient and missing columns"""
    importer = JSONMappingImporter(temp_mapping_file)
    
    # Test with all required headers
    result = importer.validate_csv_headers(["ID", "Title", "ObjectType", "Extra"])
    assert result["all_expected_present"] is True
    assert result["extra_headers"] == ["Extra"]
    
    # Test with missing headers
    with pytest.raises(ValueError) as exc_info:
        importer.validate_csv_headers(["Title"])
    
    assert "Critical columns from mapping are missing" in str(exc_info.value)
    assert "ObjectType" in str(exc_info.value)

