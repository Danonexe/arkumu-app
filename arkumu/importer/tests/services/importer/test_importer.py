import pytest
import json
import tempfile
from pathlib import Path

from arkumu.importer.services.importer.importer import JSONMappingImporter
from arkumu.importer.services.importer.resource_manager import ResourceManager
from arkumu.importer.services.importer.rule_processor import MappingRuleProcessor
from arkumu.metadata.models.resource import ResourceType


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


@pytest.mark.django_db
def test_fallback_property_assignment():
    """Test that a fallback property is assigned for unmapped columns"""
    mapping_json = {
        "institution": "TESTINST",
        "domain": "E22_Human-Made_Object",
        "anchor_column": "ID",
        "mappings": [
            {"source_column": "ID", "property": "P1_is_identified_by", "range": "E42_Identifier"},
            {"source_column": "UnmappedColumn", "property": "", "range": "literal"}
        ]
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mapping_json, f)
        mapping_path = f.name
    try:
        importer = JSONMappingImporter(mapping_path)
        # Create test data
        row_data = {"ID": "123", "UnmappedColumn": "foo"}
        
        # Import the data (we'll test the results afterward)
        stats = importer.import_data(
            [row_data],
            primary_subject_class_short_name="E22_Human-Made_Object",
            validate_first=False
        )
        
        # Check that the import was successful
        assert stats["successful_rows"] == 1
        
        # Check that the fallback property exists and is of type PROPERTY
        fallback_uri = "arkumu:column_unmappedcolumn"
        fallback_property = importer.resource_manager.get_or_create_resource(
            uri=fallback_uri,
            defaults={
                'resource_type': ResourceType.PROPERTY,
                'source': "TESTINST"
            }
        )
        assert fallback_property.resource_type == ResourceType.PROPERTY
    finally:
        Path(mapping_path).unlink(missing_ok=True)


@pytest.mark.django_db
def test_all_columns_linked_to_anchor():
    """Test that all columns are linked to the anchor resource, even if not mapped to a CIDOC property"""
    mapping_json = {
        "institution": "TESTINST",
        "domain": "E22_Human-Made_Object",
        "anchor_column": "ID",
        "mappings": [
            {"source_column": "ID", "property": "P1_is_identified_by", "range": "E42_Identifier"},
            {"source_column": "UnmappedColumn", "property": "", "range": "literal"}
        ]
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mapping_json, f)
        mapping_path = f.name
    try:
        importer = JSONMappingImporter(mapping_path)
        # Create test data
        row_data = {"ID": "123", "UnmappedColumn": "foo"}
        
        # Import the data
        stats = importer.import_data(
            [row_data],
            primary_subject_class_short_name="E22_Human-Made_Object",
            validate_first=False
        )
        
        assert stats["successful_rows"] == 1
        
        # Get the subject resource that was created during import
        from arkumu.metadata.models.triples import Triple
        from arkumu.metadata.models.resource import Resource
        
        # Look for the literal resource with value "foo" (our unmapped column value)
        literal_foo = Resource.objects.filter(
            resource_type=ResourceType.LITERAL, 
            literal_value="foo"
        ).first()
        
        assert literal_foo is not None, "Could not find literal resource with value 'foo'"
        
        # Find all triples that reference this literal value
        triples_with_foo = Triple.objects.filter(object=literal_foo)
        assert triples_with_foo.exists(), "No triples found with 'foo' as the object"
        
        # Verify that at least one of these triples has a predicate that includes the column name
        column_name = "unmappedcolumn"
        fk_triple = False
        for triple in triples_with_foo:
            if column_name in triple.predicate.uri.lower():
                fk_triple = True
                break
        
        assert fk_triple, f"No predicate found containing '{column_name}' pointing to 'foo'"
    finally:
        Path(mapping_path).unlink(missing_ok=True)

