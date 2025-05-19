import pytest
from unittest.mock import MagicMock, patch, mock_open

from arkumu.importer.services.importer import JSONMappingImporter
# We might need ResourceManager and MappingRuleProcessor for mocking later
# from arkumu.importer.services.resource_manager import ResourceManager 
# from arkumu.importer.services.rule_processor import MappingRuleProcessor

# Define a fixture for the mocked resource manager
@pytest.fixture
def mock_resource_manager():
    mock_rm = MagicMock()
    mock_rm.get_or_create_rdf_term.return_value = MagicMock(uri="rdf_type_uri")
    mock_rm.get_or_create_rdfs_term.return_value = MagicMock(uri="rdfs_label_uri")
    mock_rm.get_or_create_owl_term.return_value = MagicMock(uri="owl_sameas_uri")
    return mock_rm


# Define a fixture for the mocked rule processor
@pytest.fixture
def mock_rule_processor():
    return MagicMock()


# Define a fixture for a basic importer instance with all dependencies mocked
@pytest.fixture
def importer(mock_resource_manager, mock_rule_processor):
    with patch('builtins.open', new_callable=mock_open, 
               read_data='{"institution": "TESTINST", "mappings": [{"source_column": "critical_col1"}, {"source_column": "critical_col2"}]}'), \
         patch('arkumu.importer.services.importer.ResourceManager', return_value=mock_resource_manager), \
         patch('arkumu.importer.services.importer.MappingRuleProcessor', return_value=mock_rule_processor):
        importer_instance = JSONMappingImporter(mapping_file_path="dummy/path.json")
        return importer_instance


def test_init_success(importer, mock_resource_manager):
    """Test successful initialization of JSONMappingImporter."""
    assert importer.institution_code == "TESTINST"
    assert len(importer.expected_source_columns) == 2
    assert importer.expected_source_columns == {"critical_col1", "critical_col2"}
    # Check if ResourceManager methods were called
    mock_resource_manager.get_or_create_rdf_term.assert_called_with("type", "RDF type property")
    # Check rule_processor is set
    assert isinstance(importer.rule_processor, MagicMock)


def test_init_missing_institution_raises_value_error():
    """Test __init__ raises ValueError if 'institution' is missing in mapping."""
    with pytest.raises(ValueError) as exc_info:
        with patch('builtins.open', new_callable=mock_open, read_data='{"mappings": []}'), \
             patch('arkumu.importer.services.importer.ResourceManager'), \
             patch('arkumu.importer.services.importer.MappingRuleProcessor'), \
             patch('arkumu.importer.services.importer.logger.error') as mock_logger_error, \
             patch('arkumu.importer.services.importer.logger.info') as mock_logger_info:
            JSONMappingImporter(mapping_file_path="dummy/path.json")
    
    assert "Mapping JSON must contain an 'institution' code." in str(exc_info.value)
    # We can optionally verify that the logger was called with the expected message
    mock_logger_error.assert_any_call("Missing 'institution' code in mapping JSON")


def test_validate_source_headers_all_present(importer):
    """Test validate_source_headers when all expected headers are present."""
    actual_headers = ["critical_col1", "critical_col2"]
    result = importer.validate_source_headers(actual_headers)
    assert result["all_expected_present"] is True
    assert len(result["missing_critical_headers"]) == 0
    assert len(result["extra_headers"]) == 0


def test_validate_source_headers_missing_critical(importer):
    """Test validate_source_headers raises ValueError for missing critical headers."""
    actual_headers = ["critical_col1"]  # Missing critical_col2
    with pytest.raises(ValueError) as exc_info:
        importer.validate_source_headers(actual_headers)
    
    assert "Critical columns from mapping are missing" in str(exc_info.value)
    assert "critical_col2" in str(exc_info.value)


def test_validate_source_headers_with_extra(importer):
    """Test validate_source_headers identifies extra headers."""
    actual_headers = ["critical_col1", "critical_col2", "extra_col"]
    result = importer.validate_source_headers(actual_headers)
    assert result["all_expected_present"] is True
    assert len(result["missing_critical_headers"]) == 0
    assert result["extra_headers"] == ["extra_col"]

