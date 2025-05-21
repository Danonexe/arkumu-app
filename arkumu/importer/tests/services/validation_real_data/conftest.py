import pytest
import polars as pl
import os
import json
import tempfile
from pathlib import Path

from arkumu.importer.services.validation.validation import MappingValidator


def pytest_addoption(parser):
    """Add command line options for real data tests."""
    parser.addoption(
        "--csv-file", 
        action="store", 
        default=None,
        help="Path to CSV file for real data testing"
    )
    parser.addoption(
        "--mapping-file", 
        action="store", 
        default=None,
        help="Path to mapping JSON file for real data testing"
    )
    parser.addoption(
        "--related-data-dir", 
        action="store", 
        default=None,
        help="Path to directory containing related data files"
    )


@pytest.fixture
def validator():
    """Return a MappingValidator instance for testing."""
    return MappingValidator()


@pytest.fixture
def external_mapping_file(request):
    """
    Fixture to get path to an external mapping file for testing.
    
    Can be used with a path parameter to load different mapping files:
    external_mapping_file('/path/to/mapping.json')
    """
    def _get_mapping_path(file_path=None):
        # First check command line option
        if file_path is None:
            file_path = request.config.getoption("--mapping-file")
        
        # Then check environment variable
        if file_path is None:
            file_path = os.environ.get('MAPPING_TEST_FILE')
            
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Mapping file not found: {file_path}")
        
        # Print info about the mapping file
        try:
            with open(file_path, 'r') as f:
                mapping_data = json.load(f)
                
            print(f"\nLoaded mapping file {file_path}")
            print(f"Institution: {mapping_data.get('institution')}")
            print(f"Domain: {mapping_data.get('domain')}")
            print(f"Anchor column: {mapping_data.get('anchor_column')}")
            print(f"Mapping rules: {len(mapping_data.get('mappings', []))}")
        except Exception as e:
            print(f"Warning: Could not load mapping file for info: {e}")
            
        return file_path
    
    return _get_mapping_path


@pytest.fixture
def external_csv_file(request):
    """
    Fixture to get path to an external CSV file for testing.
    
    Can be used with a path parameter to load different CSV files:
    external_csv_file('/path/to/data.csv')
    """
    def _get_csv_path(file_path=None):
        # First check command line option
        if file_path is None:
            file_path = request.config.getoption("--csv-file")
        
        # Then check environment variable
        if file_path is None:
            file_path = os.environ.get('CSV_TEST_FILE')
            
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"CSV file not found: {file_path}")
            
        return file_path
    
    return _get_csv_path


@pytest.fixture
def external_data_dir(request):
    """
    Fixture to get path to an external directory with related data files.
    
    Can be used with a path parameter:
    external_data_dir('/path/to/data_dir')
    """
    def _get_data_dir(dir_path=None):
        # First check command line option
        if dir_path is None:
            dir_path = request.config.getoption("--related-data-dir")
        
        # Then check environment variable
        if dir_path is None:
            dir_path = os.environ.get('RELATED_DATA_DIR')
            
        if not dir_path or not os.path.exists(dir_path):
            raise FileNotFoundError(f"Related data directory not found: {dir_path}")
            
        return dir_path
    
    return _get_data_dir


# Sample data fixtures for common test cases

@pytest.fixture
def sample_csv_file():
    """Create a sample CSV file with test data."""
    data = [
        {"ID": "obj1", "Title": "Test Object 1", "ObjectType": "Painting", "CreationDate": "1800", "RelatedID": "ref1"},
        {"ID": "obj2", "Title": "Test Object 2", "ObjectType": "Sculpture", "CreationDate": "1850", "RelatedID": "ref2"},
        {"ID": "obj3", "Title": "Test Object 3", "ObjectType": "Drawing", "CreationDate": "1900", "RelatedID": "ref3"}
    ]
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        df = pl.DataFrame(data)
        df.write_csv(f.name)
        csv_path = f.name
    
    yield csv_path
    
    # Cleanup
    Path(csv_path).unlink(missing_ok=True)


@pytest.fixture
def sample_mapping_file():
    """Create a sample mapping file for the test CSV."""
    mapping_data = {
        "institution": "TestInst",
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
            },
            {
                "source_column": "RelatedID",
                "property": "P67i_is_referred_to_by",
                "object_column": "RelatedData"
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(mapping_data, f)
        mapping_path = f.name
    
    yield mapping_path
    
    # Cleanup
    Path(mapping_path).unlink(missing_ok=True)


@pytest.fixture
def sample_related_data_dir():
    """Create a temporary directory with related data CSV files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a related data CSV file
        related_data = [
            {"id": "ref1", "name": "Related Item 1"},
            {"id": "ref2", "name": "Related Item 2"}
            # ref3 is intentionally missing to test validation errors
        ]
        
        # Write to file
        file_path = os.path.join(temp_dir, "RelatedData.csv")
        df = pl.DataFrame(related_data)
        df.write_csv(file_path)
        
        yield temp_dir 