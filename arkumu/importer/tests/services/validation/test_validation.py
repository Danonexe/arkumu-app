import pytest
import os
import json
import tempfile
import polars as pl
from arkumu.importer.services.validation import MappingValidator, validate_mapping
from arkumu.importer.services.validation_utils import ValidationError, ValidationReport

@pytest.fixture
def valid_mapping_data():
    """Fixture for a valid mapping dict"""
    return {
        "institution": "test_inst",
        "domain": "E7_Activity",
        "anchor_column": "ID",
        "mappings": [
            {
                "source_column": "Name",
                "property": "rdfs:label",
                "range": "literal",
                "language": "en"
            },
            {
                "source_column": "Type",
                "property": "P2_has_type",
                "range": "E55_Type"
            },
            {
                "source_column": "Date",
                "property": "P4_has_time-span",
                "range": "E52_Time-Span",
                "object_properties": [
                    {
                        "property": "P79_beginning_is_qualified_by",
                        "use_parent_value": True,
                        "range": "literal"
                    }
                ]
            },
            {
                "source_column": "RelatedID",
                "property": "P67i_is_referred_to_by",
                "object_column": "RelatedData"
            }
        ]
    }


@pytest.fixture
def invalid_mapping_data():
    """Fixture for an invalid mapping dict"""
    return {
        "institution": "test_inst",
        # Missing domain
        "anchor_column": "ID",
        "mappings": [
            {
                # Missing property
                "source_column": "Name",
                "range": "literal"
            },
            {
                "source_column": "Type",
                "property": "P2_has_type"
                # Missing range or object_column
            }
        ]
    }


@pytest.fixture
def valid_csv_data():
    """Fixture for valid CSV data"""
    return [
        {"ID": "1", "Name": "Test 1", "Type": "Type A", "Date": "2023-01-01", "RelatedID": "A1"},
        {"ID": "2", "Name": "Test 2", "Type": "Type B", "Date": "2023-02-01", "RelatedID": "A2"},
        {"ID": "3", "Name": "Test 3", "Type": "Type C", "Date": "2023-03-01", "RelatedID": "A3"}
    ]


@pytest.fixture
def related_source_data():
    """Fixture for related source data"""
    return {
        "RelatedData": [
            {"id": "A1", "name": "Related 1"},
            {"id": "A2", "name": "Related 2"}
            # A3 is missing intentionally to test invalid references
        ]
    }


@pytest.fixture
def temp_mapping_file(valid_mapping_data):
    """Create a temporary mapping file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(valid_mapping_data, f)
        mapping_path = f.name
    
    yield mapping_path
    
    # Cleanup
    if os.path.exists(mapping_path):
        os.unlink(mapping_path)


@pytest.fixture
def temp_invalid_mapping_file(invalid_mapping_data):
    """Create a temporary invalid mapping file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(invalid_mapping_data, f)
        mapping_path = f.name
    
    yield mapping_path
    
    # Cleanup
    if os.path.exists(mapping_path):
        os.unlink(mapping_path)


@pytest.fixture
def temp_csv_file(valid_csv_data):
    """Create a temporary CSV file"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df = pl.DataFrame(valid_csv_data)
        df.write_csv(f.name)
        csv_path = f.name
    
    yield csv_path
    
    # Cleanup
    if os.path.exists(csv_path):
        os.unlink(csv_path)


@pytest.fixture
def temp_related_data_dir(related_source_data):
    """Create a temporary directory with related data CSV files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a CSV file for each related source
        for source_name, data in related_source_data.items():
            file_path = os.path.join(temp_dir, f"{source_name}.csv")
            df = pl.DataFrame(data)
            df.write_csv(file_path)
        
        yield temp_dir


# ----------- TESTS -----------

def test_validation_error_str():
    """Test ValidationError string representation"""
    # Test basic error
    error = ValidationError("TEST_ERROR", "This is a test error")
    assert str(error) == "TEST_ERROR: This is a test error"
    
    # Test with field
    error = ValidationError("TEST_ERROR", "This is a test error", field="test_field")
    assert str(error) == "TEST_ERROR: This is a test error in field 'test_field'"
    
    # Test with row
    error = ValidationError("TEST_ERROR", "This is a test error", row=42)
    assert str(error) == "TEST_ERROR: This is a test error at row 42"
    
    # Test with both
    error = ValidationError("TEST_ERROR", "This is a test error", field="test_field", row=42)
    assert str(error) == "TEST_ERROR: This is a test error in field 'test_field' at row 42"


def test_validation_report():
    """Test ValidationReport functionality"""
    report = ValidationReport()
    
    # Initially valid with no errors or warnings
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert len(report.warnings) == 0
    
    # Add an error
    report.add_error("ERROR1", "First error")
    assert report.is_valid is False
    assert len(report.errors) == 1
    assert report.errors[0].error_type == "ERROR1"
    
    # Add a warning
    report.add_warning("WARNING1", "First warning")
    assert report.is_valid is False  # Still invalid due to error
    assert len(report.warnings) == 1
    assert report.warnings[0].error_type == "WARNING1"
    
    # Test summary
    summary = report.summary()
    assert "❌ Validation failed with 1 errors" in summary
    assert "⚠️ Found 1 warnings" in summary
    assert "ERROR1: First error" in summary
    assert "WARNING1: First warning" in summary


def test_validate_mapping_file_structure(temp_mapping_file, temp_invalid_mapping_file):
    """Test validation of mapping file structure"""
    validator = MappingValidator()
    
    # Valid mapping
    report = validator.validate_mapping_file(temp_mapping_file)
    assert report.is_valid is True
    assert len(report.errors) == 0
    
    # Invalid mapping
    report = validator.validate_mapping_file(temp_invalid_mapping_file)
    assert report.is_valid is False
    assert len(report.errors) > 0
    
    # Check specific errors
    error_types = [e.error_type for e in report.errors]
    assert "MISSING_FIELD" in error_types  # Missing domain
    assert "MISSING_RULE_FIELD" in error_types  # Missing property in first rule
    assert "MISSING_RANGE" in error_types  # Missing range in second rule


def test_validate_mapping_against_data(temp_mapping_file, temp_csv_file):
    """Test validation of mapping against CSV data"""
    validator = MappingValidator()
    
    # Valid mapping and CSV
    report = validator.validate_mapping_against_data(temp_mapping_file, temp_csv_file)
    assert report.is_valid is True
    
    # Test with non-existent column
    # Modify the mapping temporarily
    with open(temp_mapping_file, 'r') as f:
        mapping_data = json.load(f)
    
    # Add a rule with non-existent column
    mapping_data['mappings'].append({
        "source_column": "NonExistentColumn",
        "property": "P1_is_identified_by",
        "range": "literal"
    })
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mapping_data, f)
        modified_mapping_path = f.name
    
    try:
        report = validator.validate_mapping_against_data(modified_mapping_path, temp_csv_file)
        assert report.is_valid is False
        
        # Check specific error
        assert any(e.error_type == "MISSING_SOURCE_COLUMN" for e in report.errors)
    finally:
        if os.path.exists(modified_mapping_path):
            os.unlink(modified_mapping_path)


def test_validate_references(temp_mapping_file, temp_csv_file, temp_related_data_dir):
    """Test validation of references in mapping"""
    validator = MappingValidator()
    
    # Test with related sources
    report = validator.validate_references(
        temp_mapping_file, 
        temp_csv_file,
        data_dir=temp_related_data_dir
    )
    
    # Should have a warning or error since A3 is missing from related sources
    assert report.errors or report.warnings
    assert any(e.error_type == "INVALID_REFERENCE" for e in report.errors)


def test_convenience_function(temp_mapping_file, temp_csv_file, temp_related_data_dir):
    """Test the convenience function for validation"""
    # Non-strict validation (still fails on errors, but ignores warnings)
    result = validate_mapping(
        temp_mapping_file,
        temp_csv_file,
        data_dir=temp_related_data_dir,
        strict=False
    )
    
    # Should fail when errors are present, regardless of strict mode
    assert result is False
    
    # Strict validation (fails on both errors and warnings)
    result = validate_mapping(
        temp_mapping_file,
        temp_csv_file,
        data_dir=temp_related_data_dir,
        strict=True
    )
    
    # Should also fail with errors present
    assert result is False 