import json
import tempfile
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import polars as pl

from arkumu.importer.services.validation.validation import MappingValidator, validate_mapping, validate_mapping_columns
from arkumu.importer.services.validation.validation_utils import ValidationReport, ValidationError


class TestValidationError:
    """Test suite for ValidationError class"""

    def test_init(self):
        """Test ValidationError initialization"""
        error = ValidationError("TEST_ERROR", "Test message", {"test": "rule"}, "test_field", 1)
        
        assert error.error_type == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.rule == {"test": "rule"}
        assert error.field == "test_field"
        assert error.row == 1

    def test_str_full(self):
        """Test string representation with all fields"""
        error = ValidationError("TEST_ERROR", "Test message", {"test": "rule"}, "test_field", 1)
        result = str(error)
        
        assert "TEST_ERROR: Test message in field 'test_field' at row 1" == result

    def test_str_field_only(self):
        """Test string representation with field only"""
        error = ValidationError("TEST_ERROR", "Test message", field="test_field")
        result = str(error)
        
        assert "TEST_ERROR: Test message in field 'test_field'" == result

    def test_str_minimal(self):
        """Test string representation with minimal fields"""
        error = ValidationError("TEST_ERROR", "Test message")
        result = str(error)
        
        assert "TEST_ERROR: Test message" == result

    def test_to_dict(self):
        """Test conversion to dictionary"""
        error = ValidationError("TEST_ERROR", "Test message", {"test": "rule"}, "test_field", 1)
        result = error.to_dict()
        
        expected = {
            "error_type": "TEST_ERROR",
            "message": "Test message",
            "field": "test_field",
            "row": 1,
            "rule": {"test": "rule"}
        }
        assert result == expected


class TestValidationReport:
    """Test suite for ValidationReport class"""

    def test_init(self):
        """Test ValidationReport initialization"""
        report = ValidationReport()
        
        assert report.errors == []
        assert report.warnings == []
        assert report.info == []
        assert report.details == {}
        assert report.is_valid is True

    def test_add_error(self):
        """Test adding errors to report"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test message", {"test": "rule"}, "test_field", 1)
        
        assert len(report.errors) == 1
        assert report.errors[0].error_type == "TEST_ERROR"
        assert report.is_valid is False

    def test_add_warning(self):
        """Test adding warnings to report"""
        report = ValidationReport()
        report.add_warning("TEST_WARNING", "Test warning")
        
        assert len(report.warnings) == 1
        assert report.warnings[0].error_type == "TEST_WARNING"
        assert report.is_valid is True

    def test_add_info(self):
        """Test adding info messages to report"""
        report = ValidationReport()
        report.add_info("TEST_INFO", "Test info")
        
        assert len(report.info) == 1
        assert report.info[0].error_type == "TEST_INFO"
        assert report.is_valid is True

    def test_summary_valid(self):
        """Test summary for valid report"""
        report = ValidationReport()
        summary = report.summary()
        
        assert "✅ Validation passed!" in summary

    def test_summary_invalid(self):
        """Test summary for invalid report"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error")
        report.add_warning("TEST_WARNING", "Test warning")
        summary = report.summary()
        
        assert "❌ Validation failed with 1 errors" in summary
        assert "⚠️ Found 1 warnings" in summary
        assert "Test error" in summary
        assert "Test warning" in summary

    def test_to_dict(self):
        """Test conversion to dictionary"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error")
        report.details = {"test": "data"}
        
        result = report.to_dict()
        
        assert result["is_valid"] is False
        assert result["error_count"] == 1
        assert result["warning_count"] == 0
        assert result["details"] == {"test": "data"}
        assert len(result["errors"]) == 1


class TestMappingValidator:
    """Test suite for MappingValidator class"""

    def test_init(self):
        """Test MappingValidator initialization"""
        validator = MappingValidator()
        
        assert validator.data_loader is None
        assert validator.related_sources == {}
        assert validator.mapping_file_path is None

    def test_init_with_data_loader(self):
        """Test MappingValidator initialization with data loader"""
        mock_loader = Mock()
        validator = MappingValidator(data_loader=mock_loader)
        
        assert validator.data_loader == mock_loader

    def test_validate_mapping_file_not_found(self):
        """Test validation of non-existent mapping file"""
        validator = MappingValidator()
        report = validator.validate_mapping_file("/nonexistent/mapping.json")
        
        assert not report.is_valid
        assert len(report.errors) == 1
        assert report.errors[0].error_type == "FILE_NOT_FOUND"

    def test_validate_mapping_file_invalid_json(self):
        """Test validation of mapping file with invalid JSON"""
        validator = MappingValidator()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"invalid": json}')
            mapping_file = f.name
        
        try:
            report = validator.validate_mapping_file(mapping_file)
            
            assert not report.is_valid
            assert len(report.errors) == 1
            assert report.errors[0].error_type == "INVALID_JSON"
        finally:
            os.unlink(mapping_file)

    def test_validate_mapping_file_missing_required_fields(self):
        """Test validation of mapping file missing required fields"""
        validator = MappingValidator()
        
        mapping_data = {"institution": "test"}  # Missing required fields
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        try:
            report = validator.validate_mapping_file(mapping_file)
            
            assert not report.is_valid
            assert len(report.errors) >= 1
            error_types = [e.error_type for e in report.errors]
            assert "MISSING_FIELD" in error_types
        finally:
            os.unlink(mapping_file)

    def test_validate_mapping_file_invalid_mappings(self):
        """Test validation of mapping file with invalid mappings field"""
        validator = MappingValidator()
        
        mapping_data = {
            "institution": "test",
            "domain": "test",
            "anchor_column": "id",
            "mappings": "not_a_list"  # Should be a list
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        try:
            report = validator.validate_mapping_file(mapping_file)
            
            assert not report.is_valid
            assert any(e.error_type == "INVALID_MAPPINGS" for e in report.errors)
        finally:
            os.unlink(mapping_file)

    def test_validate_mapping_file_valid(self):
        """Test validation of valid mapping file"""
        validator = MappingValidator()
        
        mapping_data = {
            "institution": "test",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "name",
                    "property": "rdfs:label",
                    "range": "String"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        try:
            report = validator.validate_mapping_file(mapping_file)
            
            assert report.is_valid
            assert len(report.errors) == 0
        finally:
            os.unlink(mapping_file)

    def test_validate_mapping_rule_structure_missing_fields(self):
        """Test validation of mapping rule missing required fields"""
        validator = MappingValidator()
        report = ValidationReport()
        
        rule = {"source_column": "name"}  # Missing "property"
        validator._validate_mapping_rule_structure(rule, 0, report)
        
        assert not report.is_valid
        assert any(e.error_type == "MISSING_RULE_FIELD" for e in report.errors)

    def test_validate_mapping_rule_structure_missing_range_and_object_column(self):
        """Test validation of mapping rule missing both range and object_column"""
        validator = MappingValidator()
        report = ValidationReport()
        
        rule = {
            "source_column": "name",
            "property": "rdfs:label"
        }  # Missing both "range" and "object_column"
        
        validator._validate_mapping_rule_structure(rule, 0, report)
        
        assert not report.is_valid
        assert any(e.error_type == "MISSING_RANGE" for e in report.errors)

    def test_validate_mapping_rule_structure_with_object_properties(self):
        """Test validation of mapping rule with object_properties"""
        validator = MappingValidator()
        report = ValidationReport()
        
        rule = {
            "source_column": "author_id",
            "property": "author",
            "object_column": "authors",
            "object_properties": [
                {"source_column": "author_name"},  # Missing property
                {"property": "name"}  # Missing value source
            ]
        }
        
        validator._validate_mapping_rule_structure(rule, 0, report)
        
        assert not report.is_valid
        error_types = [e.error_type for e in report.errors]
        assert "MISSING_PROPERTY" in error_types
        assert "MISSING_VALUE_SOURCE" in error_types

    @patch('polars.read_csv')
    def test_validate_mapping_against_data_success(self, mock_read_csv):
        """Test successful validation of mapping against CSV data"""
        validator = MappingValidator()
        
        # Mock CSV data
        mock_df = pl.DataFrame({
            "id": [1, 2, 3],
            "name": ["A", "B", "C"]
        })
        mock_read_csv.return_value = mock_df
        
        mapping_data = {
            "institution": "test",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "name",
                    "property": "rdfs:label",
                    "range": "String"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            report = validator.validate_mapping_against_data(mapping_file, csv_file)
            
            assert report.is_valid
            assert len(report.errors) == 0
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)

    @patch('polars.read_csv')
    def test_validate_mapping_against_data_missing_columns(self, mock_read_csv):
        """Test validation of mapping against CSV data with missing columns"""
        validator = MappingValidator()
        
        # Mock CSV data without required columns
        mock_df = pl.DataFrame({
            "other_column": [1, 2, 3]
        })
        mock_read_csv.return_value = mock_df
        
        mapping_data = {
            "institution": "test",
            "domain": "test",
            "anchor_column": "id",  # Missing in CSV
            "mappings": [
                {
                    "source_column": "name",  # Missing in CSV
                    "property": "rdfs:label",
                    "range": "String"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            report = validator.validate_mapping_against_data(mapping_file, csv_file)
            
            assert not report.is_valid
            error_types = [e.error_type for e in report.errors]
            assert "MISSING_ANCHOR_COLUMN" in error_types
            assert "MISSING_SOURCE_COLUMN" in error_types
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)

    @patch('polars.read_csv')
    def test_validate_rule_against_data(self, mock_read_csv):
        """Test validation of individual rule against CSV data"""
        validator = MappingValidator()
        report = ValidationReport()
        
        csv_columns = {"id", "name", "email"}
        
        # Valid rule
        rule = {
            "source_column": "name",
            "property": "rdfs:label",
            "range": "String"
        }
        
        validator._validate_rule_against_data(rule, csv_columns, 0, report)
        assert report.is_valid
        
        # Invalid rule with missing column
        rule_invalid = {
            "source_column": "missing_column",
            "property": "rdfs:label",
            "range": "String"
        }
        
        validator._validate_rule_against_data(rule_invalid, csv_columns, 1, report)
        assert not report.is_valid
        assert any(e.error_type == "MISSING_SOURCE_COLUMN" for e in report.errors)

    @patch('arkumu.metadata.models.Resource')
    @patch('polars.read_csv')
    def test_validate_references_success(self, mock_read_csv, mock_resource):
        """Test successful reference validation"""
        validator = MappingValidator()
        
        # Mock CSV data
        mock_df = pl.DataFrame({
            "id": [1, 2, 3],
            "author_id": ["A1", "A2", "A3"]
        })
        mock_read_csv.return_value = mock_df
        
        # Mock database resources exist
        mock_resource.objects.filter.return_value.count.return_value = 5
        
        mapping_data = {
            "institution": "test_institution",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "author_id",
                    "property": "author",
                    "object_column": "authors"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            report = validator.validate_references(mapping_file, csv_file)
            
            assert report.is_valid
            assert 'references' in report.details
            assert 'authors' in report.details['references']
            assert report.details['references']['authors']['exists_in_db'] is True
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)

    @patch('arkumu.metadata.models.Resource')
    @patch('polars.read_csv')
    def test_validate_references_not_found(self, mock_read_csv, mock_resource):
        """Test reference validation when references not found in database"""
        validator = MappingValidator()
        
        # Mock CSV data
        mock_df = pl.DataFrame({
            "id": [1, 2, 3],
            "author_id": ["A1", "A2", "A3"]
        })
        mock_read_csv.return_value = mock_df
        
        # Mock no database resources found
        mock_resource.objects.filter.return_value.count.return_value = 0
        
        mapping_data = {
            "institution": "test_institution",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "author_id",
                    "property": "author",
                    "object_column": "authors"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            report = validator.validate_references(mapping_file, csv_file)
            
            assert report.is_valid  # References generate warnings, not errors
            assert len(report.warnings) > 0
            assert any(w.error_type == "MISSING_REFERENCE_SOURCE" for w in report.warnings)
            assert 'references' in report.details
            assert report.details['references']['authors']['exists_in_db'] is False
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)

    @patch('polars.read_csv')
    def test_validate_references_django_import_error(self, mock_read_csv):
        """Test reference validation when Django is not available"""
        validator = MappingValidator()
        
        # Mock CSV data
        mock_df = pl.DataFrame({
            "id": [1, 2, 3],
            "author_id": ["A1", "A2", "A3"]
        })
        mock_read_csv.return_value = mock_df
        
        mapping_data = {
            "institution": "test_institution",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "author_id",
                    "property": "author",
                    "object_column": "authors"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            # Patch the import to raise ImportError
            with patch.dict('sys.modules', {'arkumu.metadata.models': None}):
                with patch('builtins.__import__', side_effect=ImportError):
                    report = validator.validate_references(mapping_file, csv_file)
            
            assert report.is_valid  # Import errors generate warnings, not errors
            assert len(report.warnings) > 0
            assert any(w.error_type == "DB_VALIDATION_UNAVAILABLE" for w in report.warnings)
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)

    def test_load_related_sources_with_data_loader(self):
        """Test loading related sources with data loader"""
        mock_loader = Mock()
        mock_loader.load_related_sources.return_value = {"test": "data"}
        
        validator = MappingValidator(data_loader=mock_loader)
        result = validator.load_related_sources("test_institution", "/test/dir")
        
        assert result == {"test": "data"}
        mock_loader.load_related_sources.assert_called_once_with("test_institution")

    @patch('pathlib.Path.glob')
    @patch('polars.read_csv')
    def test_load_related_sources_without_data_loader(self, mock_read_csv, mock_glob):
        """Test loading related sources without data loader"""
        validator = MappingValidator()
        
        # Mock file discovery
        mock_file = Mock()
        mock_file.suffix = '.csv'
        mock_file.stem = 'test_table'
        mock_glob.return_value = [mock_file]
        
        # Mock CSV reading
        mock_df = pl.DataFrame({
            "id": [1, 2],
            "name": ["A", "B"]
        })
        mock_read_csv.return_value = mock_df
        
        result = validator.load_related_sources("test_institution", "/test/dir")
        
        assert "test_table" in result
        assert len(result["test_table"]) == 2


class TestValidationFunctions:
    """Test suite for validation utility functions"""

    @patch('arkumu.importer.services.validation.validation.validate_mapping_columns')
    @patch('arkumu.importer.services.validation.validation.MappingValidator')
    def test_validate_mapping_print_output(self, mock_validator_class, mock_validate_columns):
        """Test validate_mapping function with print output"""
        mock_validator = Mock()
        mock_validator_class.return_value = mock_validator
        
        # Mock column report
        column_report = ValidationReport()
        mock_validate_columns.return_value = column_report
        
        # Mock reference report
        ref_report = ValidationReport()
        mock_validator.validate_references.return_value = ref_report
        
        result = validate_mapping("mapping.json", "data.csv", print_output=True)
        
        assert isinstance(result, bool)
        assert result is True  # No errors or warnings

    @patch('arkumu.importer.services.validation.validation.validate_mapping_columns')
    @patch('arkumu.importer.services.validation.validation.MappingValidator')
    def test_validate_mapping_no_print_output(self, mock_validator_class, mock_validate_columns):
        """Test validate_mapping function without print output"""
        mock_validator = Mock()
        mock_validator_class.return_value = mock_validator
        
        # Mock column report
        column_report = ValidationReport()
        mock_validate_columns.return_value = column_report
        
        # Mock reference report
        ref_report = ValidationReport()
        mock_validator.validate_references.return_value = ref_report
        
        result = validate_mapping("mapping.json", "data.csv", print_output=False)
        
        assert isinstance(result, ValidationReport)
        assert result.is_valid

    @patch('polars.read_csv')
    def test_validate_mapping_columns(self, mock_read_csv):
        """Test validate_mapping_columns function"""
        # Mock CSV data
        mock_df = pl.DataFrame({
            "id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "email": ["a@test.com", "b@test.com", "c@test.com"],
            "unused": ["x", "y", "z"]
        })
        mock_read_csv.return_value = mock_df
        
        mapping_data = {
            "institution": "test",
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "name",
                    "property": "rdfs:label",
                    "range": "String"
                },
                {
                    "source_column": "email",
                    "property": "email",
                    "range": "String"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            report = validate_mapping_columns(mapping_file, csv_file, print_output=False)
            
            assert report.is_valid
            assert 'columns' in report.details
            assert report.details['columns']['total'] == 4
            assert report.details['columns']['referenced'] == 3  # id, name, email
            assert report.details['columns']['unmapped'] == 1  # unused
            assert len(report.warnings) == 1  # unmapped columns warning
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)


@pytest.mark.django_db
class TestValidationWithDatabase:
    """Integration tests with real database"""

    def test_validate_references_with_real_db(self, test_organization, test_mapping):
        """Test reference validation with real database models"""
        validator = MappingValidator()
        
        # Create a CSV file with reference data
        csv_data = "id;author_id\n1;auth1\n2;auth2\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            csv_file = f.name
        
        mapping_data = {
            "institution": test_organization.code,
            "domain": "test",
            "anchor_column": "id",
            "mappings": [
                {
                    "source_column": "author_id",
                    "property": "author",
                    "object_column": "authors"
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(mapping_data, f)
            mapping_file = f.name
        
        try:
            report = validator.validate_references(mapping_file, csv_file)
            
            # Should complete without errors even if no references found
            assert isinstance(report, ValidationReport)
            assert 'references' in report.details
        finally:
            os.unlink(mapping_file)
            os.unlink(csv_file)