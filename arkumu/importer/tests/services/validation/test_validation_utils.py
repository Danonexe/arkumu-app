import pytest
from arkumu.importer.services.validation.validation_utils import ValidationError, ValidationReport


class TestValidationError:
    """Test suite for ValidationError class"""

    def test_init_minimal(self):
        """Test ValidationError initialization with minimal parameters"""
        error = ValidationError("TEST_ERROR", "Test message")
        
        assert error.error_type == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.rule is None
        assert error.field is None
        assert error.row is None

    def test_init_full(self):
        """Test ValidationError initialization with all parameters"""
        rule = {"source_column": "test", "property": "test:prop"}
        error = ValidationError("TEST_ERROR", "Test message", rule, "test_field", 5)
        
        assert error.error_type == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.rule == rule
        assert error.field == "test_field"
        assert error.row == 5

    def test_str_minimal(self):
        """Test string representation with minimal data"""
        error = ValidationError("TEST_ERROR", "Test message")
        result = str(error)
        
        assert result == "TEST_ERROR: Test message"

    def test_str_with_field(self):
        """Test string representation with field"""
        error = ValidationError("TEST_ERROR", "Test message", field="test_field")
        result = str(error)
        
        assert result == "TEST_ERROR: Test message in field 'test_field'"

    def test_str_with_row(self):
        """Test string representation with row"""
        error = ValidationError("TEST_ERROR", "Test message", row=10)
        result = str(error)
        
        assert result == "TEST_ERROR: Test message at row 10"

    def test_str_with_field_and_row(self):
        """Test string representation with field and row"""
        error = ValidationError("TEST_ERROR", "Test message", field="test_field", row=10)
        result = str(error)
        
        assert result == "TEST_ERROR: Test message in field 'test_field' at row 10"

    def test_to_dict_minimal(self):
        """Test dictionary conversion with minimal data"""
        error = ValidationError("TEST_ERROR", "Test message")
        result = error.to_dict()
        
        expected = {
            "error_type": "TEST_ERROR",
            "message": "Test message",
            "field": None,
            "row": None,
            "rule": None
        }
        assert result == expected

    def test_to_dict_full(self):
        """Test dictionary conversion with all data"""
        rule = {"source_column": "test", "property": "test:prop"}
        error = ValidationError("TEST_ERROR", "Test message", rule, "test_field", 5)
        result = error.to_dict()
        
        expected = {
            "error_type": "TEST_ERROR",
            "message": "Test message",
            "field": "test_field",
            "row": 5,
            "rule": rule
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

    def test_is_valid_empty(self):
        """Test is_valid property with empty report"""
        report = ValidationReport()
        assert report.is_valid is True

    def test_is_valid_with_warnings(self):
        """Test is_valid property with only warnings"""
        report = ValidationReport()
        report.add_warning("TEST_WARNING", "Test warning")
        assert report.is_valid is True

    def test_is_valid_with_info(self):
        """Test is_valid property with only info messages"""
        report = ValidationReport()
        report.add_info("TEST_INFO", "Test info")
        assert report.is_valid is True

    def test_is_valid_with_errors(self):
        """Test is_valid property with errors"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error")
        assert report.is_valid is False

    def test_add_error(self):
        """Test adding error to report"""
        report = ValidationReport()
        rule = {"test": "rule"}
        
        report.add_error("TEST_ERROR", "Test message", rule, "test_field", 1)
        
        assert len(report.errors) == 1
        error = report.errors[0]
        assert error.error_type == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.rule == rule
        assert error.field == "test_field"
        assert error.row == 1

    def test_add_warning(self):
        """Test adding warning to report"""
        report = ValidationReport()
        rule = {"test": "rule"}
        
        report.add_warning("TEST_WARNING", "Test message", rule, "test_field", 1)
        
        assert len(report.warnings) == 1
        warning = report.warnings[0]
        assert warning.error_type == "TEST_WARNING"
        assert warning.message == "Test message"
        assert warning.rule == rule
        assert warning.field == "test_field"
        assert warning.row == 1

    def test_add_info(self):
        """Test adding info message to report"""
        report = ValidationReport()
        rule = {"test": "rule"}
        
        report.add_info("TEST_INFO", "Test message", rule, "test_field", 1)
        
        assert len(report.info) == 1
        info = report.info[0]
        assert info.error_type == "TEST_INFO"
        assert info.message == "Test message"
        assert info.rule == rule
        assert info.field == "test_field"
        assert info.row == 1

    def test_summary_valid_empty(self):
        """Test summary for valid empty report"""
        report = ValidationReport()
        summary = report.summary()
        
        assert "✅ Validation passed!" in summary

    def test_summary_valid_with_warnings_and_info(self):
        """Test summary for valid report with warnings and info"""
        report = ValidationReport()
        report.add_warning("TEST_WARNING", "Test warning")
        report.add_info("TEST_INFO", "Test info")
        
        summary = report.summary()
        
        assert "✅ Validation passed!" in summary
        assert "⚠️ Found 1 warnings" in summary
        assert "ℹ️ 1 informational messages" in summary
        assert "Test warning" in summary
        assert "Test info" in summary

    def test_summary_invalid_with_errors(self):
        """Test summary for invalid report with errors"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error")
        report.add_warning("TEST_WARNING", "Test warning")
        
        summary = report.summary()
        
        assert "❌ Validation failed with 1 errors" in summary
        assert "⚠️ Found 1 warnings" in summary
        assert "Test error" in summary
        assert "Test warning" in summary

    def test_summary_multiple_errors_and_warnings(self):
        """Test summary with multiple errors and warnings"""
        report = ValidationReport()
        report.add_error("ERROR1", "First error")
        report.add_error("ERROR2", "Second error")
        report.add_warning("WARNING1", "First warning")
        report.add_warning("WARNING2", "Second warning")
        report.add_info("INFO1", "First info")
        
        summary = report.summary()
        
        assert "❌ Validation failed with 2 errors" in summary
        assert "⚠️ Found 2 warnings" in summary
        assert "ℹ️ 1 informational messages" in summary
        assert "First error" in summary
        assert "Second error" in summary
        assert "First warning" in summary
        assert "Second warning" in summary
        assert "First info" in summary

    def test_print_report_basic(self, capsys):
        """Test print_report method with basic data"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error")
        report.add_warning("TEST_WARNING", "Test warning")
        
        report.print_report()
        
        captured = capsys.readouterr()
        assert "❌ Validation failed with 1 errors" in captured.out
        assert "⚠️ Found 1 warnings" in captured.out
        assert "Test error" in captured.out
        assert "Test warning" in captured.out

    def test_print_report_with_column_details(self, capsys):
        """Test print_report method with column details"""
        report = ValidationReport()
        report.details = {
            'columns': {
                'total': 5,
                'referenced': 3,
                'missing': 1,
                'unmapped': 1
            },
            'anchor_column': {
                'name': 'id',
                'found': True,
                'unique_count': 100,
                'total_rows': 100
            },
            'column_data': [
                {
                    'name': 'name',
                    'found': True,
                    'property': 'rdfs:label',
                    'range': 'String',
                    'non_null_count': 95,
                    'total_rows': 100,
                    'non_null_percent': 95.0
                },
                {
                    'name': 'missing_col',
                    'found': False,
                    'property': 'test:missing',
                    'range': 'String'
                }
            ],
            'unmapped_columns': ['extra_col']
        }
        
        report.print_report()
        
        captured = capsys.readouterr()
        assert "COLUMN STATISTICS" in captured.out
        assert "Total CSV columns: 5" in captured.out
        assert "Referenced columns: 3" in captured.out
        assert "Missing columns: 1" in captured.out
        assert "Unmapped columns: 1" in captured.out
        assert "✅ Anchor column 'id' - FOUND" in captured.out
        assert "MAPPING COLUMNS TABLE" in captured.out
        assert "name" in captured.out
        assert "missing_col" in captured.out
        assert "UNMAPPED CSV COLUMNS" in captured.out
        assert "extra_col" in captured.out

    def test_print_report_with_reference_details(self, capsys):
        """Test print_report method with reference details"""
        report = ValidationReport()
        report.details = {
            'columns': {
                'total': 3,
                'referenced': 2,
                'missing': 0,
                'unmapped': 1
            },
            'column_data': [
                {
                    'name': 'author_id',
                    'found': True,
                    'property': 'author',
                    'range': 'Author',
                    'references_table': 'authors',
                    'non_null_count': 50,
                    'total_rows': 50,
                    'non_null_percent': 100.0
                }
            ],
            'references': {
                'authors': {
                    'name': 'authors',
                    'exists_in_db': True,
                    'reference_count': 25,
                    'status': 'FOUND_IN_DB',
                    'values_to_check': 50
                }
            },
            'unmapped_columns': []
        }
        
        report.print_report()
        
        captured = capsys.readouterr()
        assert "TABLE NAME" in captured.out
        assert "DATABASE STATUS" in captured.out
        assert "authors" in captured.out
        assert "✅ FOUND" in captured.out
        assert "MAPPING COLUMNS TABLE" in captured.out
        assert "authors ✅" in captured.out

    def test_print_report_with_sub_columns(self, capsys):
        """Test print_report method with sub-columns"""
        report = ValidationReport()
        report.details = {
            'columns': {
                'total': 4,
                'referenced': 3,
                'missing': 0,
                'unmapped': 1
            },
            'column_data': [
                {
                    'name': 'author_name',
                    'found': True,
                    'is_sub_column': True,
                    'parent_column': 'author_id',
                    'property': 'name'
                }
            ],
            'unmapped_columns': []
        }
        
        report.print_report()
        
        captured = capsys.readouterr()
        assert "SUB-COLUMNS" in captured.out
        assert "author_name" in captured.out
        assert "author_id" in captured.out

    def test_to_dict_empty(self):
        """Test to_dict method with empty report"""
        report = ValidationReport()
        result = report.to_dict()
        
        expected = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "error_count": 0,
            "warning_count": 0,
            "summary": "✅ Validation passed!",
            "details": {}
        }
        assert result == expected

    def test_to_dict_with_data(self):
        """Test to_dict method with data"""
        report = ValidationReport()
        report.add_error("TEST_ERROR", "Test error", field="test_field")
        report.add_warning("TEST_WARNING", "Test warning")
        report.details = {"test": "data"}
        
        result = report.to_dict()
        
        assert result["is_valid"] is False
        assert result["error_count"] == 1
        assert result["warning_count"] == 1
        assert len(result["errors"]) == 1
        assert len(result["warnings"]) == 1
        assert result["details"] == {"test": "data"}
        assert "Test error" in result["summary"]
        assert "Test warning" in result["summary"]

    def test_to_dict_error_structure(self):
        """Test to_dict method error structure"""
        report = ValidationReport()
        rule = {"source_column": "test"}
        report.add_error("TEST_ERROR", "Test error", rule, "test_field", 5)
        
        result = report.to_dict()
        
        error_dict = result["errors"][0]
        assert error_dict["error_type"] == "TEST_ERROR"
        assert error_dict["message"] == "Test error"
        assert error_dict["rule"] == rule
        assert error_dict["field"] == "test_field"
        assert error_dict["row"] == 5