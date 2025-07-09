"""
Tests for FileDatasetMatcher service
"""

import os
import tempfile
import json
import csv
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from arkumu.importer.services.file_matching.file_dataset_matcher import (
    FileDatasetMatcher,
    FileInfo,
    DatasetMatchCandidate,
    MatchResult,
    BatchMatchResult,
    MatchingStrategy
)
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig,
    DatasetConfig,
    ColumnConfig,
    ColumnType
)
from arkumu.importer.services.error_handling.error_manager import ErrorManager


class TestFileDatasetMatcher:
    """Test suite for FileDatasetMatcher"""
    
    @pytest.fixture
    def mock_error_manager(self):
        """Create mock error manager"""
        error_manager = Mock(spec=ErrorManager)
        error_manager.record_error = Mock()
        return error_manager
    
    @pytest.fixture
    def matcher(self, mock_error_manager):
        """Create FileDatasetMatcher instance"""
        return FileDatasetMatcher(error_manager=mock_error_manager)
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def sample_csv_file(self, temp_dir):
        """Create sample CSV file"""
        csv_path = os.path.join(temp_dir, "users.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'email'])
            writer.writerow(['1', 'John Doe', 'john@example.com'])
            writer.writerow(['2', 'Jane Smith', 'jane@example.com'])
        return csv_path
    
    @pytest.fixture
    def sample_json_file(self, temp_dir):
        """Create sample JSON file"""
        json_path = os.path.join(temp_dir, "products.json")
        data = [
            {"id": 1, "name": "Product A", "price": 10.99},
            {"id": 2, "name": "Product B", "price": 15.99}
        ]
        with open(json_path, 'w') as f:
            json.dump(data, f)
        return json_path
    
    @pytest.fixture
    def sample_execution_config(self):
        """Create sample execution configuration"""
        users_columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="users",
                arkumu_type="user_id",
                column_type=ColumnType.ANCHOR,
                is_anchor=True
            ),
            ColumnConfig(
                column_name="name",
                dataset_name="users",
                arkumu_type="user_name",
                column_type=ColumnType.REGULAR
            ),
            ColumnConfig(
                column_name="email",
                dataset_name="users",
                arkumu_type="user_email",
                column_type=ColumnType.REGULAR
            )
        ]
        
        products_columns = [
            ColumnConfig(
                column_name="id",
                dataset_name="products",
                arkumu_type="product_id",
                column_type=ColumnType.ANCHOR,
                is_anchor=True
            ),
            ColumnConfig(
                column_name="name",
                dataset_name="products",
                arkumu_type="product_name",
                column_type=ColumnType.REGULAR
            ),
            ColumnConfig(
                column_name="price",
                dataset_name="products",
                arkumu_type="product_price",
                column_type=ColumnType.REGULAR
            )
        ]
        
        users_dataset = DatasetConfig(
            dataset_name="users",
            columns=users_columns,
            primary_key_columns=["id"]
        )
        
        products_dataset = DatasetConfig(
            dataset_name="products",
            columns=products_columns,
            primary_key_columns=["id"]
        )
        
        return ExecutionConfig(
            mapping_id=1,
            mapping_name="Test Mapping",
            organization="test_org",
            datasets=[users_dataset, products_dataset]
        )


class TestFileInfo:
    """Test FileInfo dataclass"""
    
    def test_file_info_creation(self, temp_dir):
        """Test FileInfo creation and post_init"""
        file_path = os.path.join(temp_dir, "test.csv")
        Path(file_path).touch()
        
        file_info = FileInfo(
            file_path=file_path,
            filename="test.csv",
            basename="",
            extension="",
            size=0,
            exists=True,
            is_readable=True,
            directory=""
        )
        
        assert file_info.basename == "test"
        assert file_info.extension == ".csv"
        assert file_info.directory == temp_dir
        assert file_info.filename == "test.csv"


class TestDatasetNameExtraction:
    """Test dataset name extraction from filenames"""
    
    def test_get_dataset_from_filename_basic(self, matcher):
        """Test basic dataset name extraction"""
        test_cases = [
            ("users.csv", "users"),
            ("products.json", "products"),
            ("user_data.csv", "user"),
            ("product-info.json", "product"),
            ("orders_2023.csv", "orders"),
            ("customer-list-v2.json", "customer")
        ]
        
        for filename, expected in test_cases:
            result = matcher.get_dataset_from_filename(filename)
            assert result == expected, f"Expected {expected} for {filename}, got {result}"
    
    def test_get_dataset_from_filename_edge_cases(self, matcher):
        """Test edge cases for dataset name extraction"""
        test_cases = [
            ("data_users_final.csv", "users"),
            ("dataset_products.json", "products"),
            ("table_orders.csv", "orders"),
            ("file_customers.json", "customers"),
            ("123_users.csv", "users"),
            ("users_123.csv", "users"),
            ("users-456.json", "users")
        ]
        
        for filename, expected in test_cases:
            result = matcher.get_dataset_from_filename(filename)
            assert result == expected, f"Expected {expected} for {filename}, got {result}"
    
    def test_get_dataset_from_filename_none_cases(self, matcher):
        """Test cases where no dataset name can be extracted"""
        test_cases = [
            "",
            ".",
            ".csv",
            "123.json",
            "_.csv"
        ]
        
        for filename in test_cases:
            result = matcher.get_dataset_from_filename(filename)
            assert result is None or result == "", f"Expected None/empty for {filename}, got {result}"


class TestFileValidation:
    """Test file validation functionality"""
    
    def test_validate_csv_structure_valid(self, matcher, sample_csv_file, sample_execution_config):
        """Test CSV validation with valid file"""
        dataset_config = sample_execution_config.get_dataset_config("users")
        
        is_valid, issues = matcher.validate_file_structure(
            sample_csv_file,
            dataset_config
        )
        
        assert is_valid
        assert len(issues) == 0
    
    def test_validate_csv_structure_missing_columns(self, matcher, temp_dir, sample_execution_config):
        """Test CSV validation with missing columns"""
        # Create CSV with missing columns
        csv_path = os.path.join(temp_dir, "incomplete_users.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])  # Missing email column
            writer.writerow(['1', 'John Doe'])
        
        dataset_config = sample_execution_config.get_dataset_config("users")
        
        is_valid, issues = matcher.validate_file_structure(
            csv_path,
            dataset_config
        )
        
        assert not is_valid
        assert any("Missing required columns" in issue for issue in issues)
    
    def test_validate_json_structure_valid(self, matcher, sample_json_file, sample_execution_config):
        """Test JSON validation with valid file"""
        dataset_config = sample_execution_config.get_dataset_config("products")
        
        is_valid, issues = matcher.validate_file_structure(
            sample_json_file,
            dataset_config
        )
        
        assert is_valid
        assert len(issues) == 0
    
    def test_validate_file_structure_nonexistent_file(self, matcher, sample_execution_config):
        """Test validation with non-existent file"""
        dataset_config = sample_execution_config.get_dataset_config("users")
        
        is_valid, issues = matcher.validate_file_structure(
            "/nonexistent/file.csv",
            dataset_config
        )
        
        assert not is_valid
        assert any("does not exist" in issue for issue in issues)
    
    def test_validate_file_structure_empty_file(self, matcher, temp_dir, sample_execution_config):
        """Test validation with empty file"""
        empty_file = os.path.join(temp_dir, "empty.csv")
        Path(empty_file).touch()
        
        dataset_config = sample_execution_config.get_dataset_config("users")
        
        is_valid, issues = matcher.validate_file_structure(
            empty_file,
            dataset_config
        )
        
        assert not is_valid
        assert any("empty" in issue.lower() for issue in issues)


class TestMatchingStrategies:
    """Test different matching strategies"""
    
    def test_exact_match_strategy(self, matcher):
        """Test exact matching strategy"""
        assert matcher._exact_match("users", "users") == 1.0
        assert matcher._exact_match("Users", "users") == 1.0
        assert matcher._exact_match("users", "products") == 0.0
        assert matcher._exact_match(None, "users") == 0.0
    
    def test_fuzzy_match_strategy(self, matcher):
        """Test fuzzy matching strategy"""
        assert matcher._fuzzy_match("users", "users") == 1.0
        assert matcher._fuzzy_match("user", "users") > 0.8
        assert matcher._fuzzy_match("users", "products") < 0.5
        assert matcher._fuzzy_match(None, "users") == 0.0
    
    def test_pattern_match_strategy(self, matcher):
        """Test pattern matching strategy"""
        assert matcher._pattern_match("users", "users") == 0.8
        assert matcher._pattern_match("user", "users") == 0.8
        assert matcher._pattern_match("user_data", "users") == 0.8
        assert matcher._pattern_match("users_table", "users") == 0.8
        assert matcher._pattern_match("users", "products") == 0.0
    
    def test_contains_match_strategy(self, matcher):
        """Test contains matching strategy"""
        assert matcher._contains_match("users", "users") == 0.7
        assert matcher._contains_match("user", "users") == 0.7
        assert matcher._contains_match("users", "user") == 0.7
        assert matcher._contains_match("users", "products") == 0.0
        assert matcher._contains_match(None, "users") == 0.0


class TestSingleFileMatching:
    """Test single file matching"""
    
    def test_match_single_file_exact_match(self, matcher, sample_csv_file, sample_execution_config):
        """Test matching single file with exact match"""
        file_info = FileInfo(
            file_path=sample_csv_file,
            filename="users.csv",
            basename="users",
            extension=".csv",
            size=100,
            exists=True,
            is_readable=True,
            directory=os.path.dirname(sample_csv_file)
        )
        
        candidates = matcher._create_dataset_candidates(sample_execution_config)
        result = matcher._match_single_file(file_info, candidates)
        
        assert result.dataset_name == "users"
        assert result.confidence == 1.0
        assert result.matching_strategy == MatchingStrategy.EXACT_MATCH
        assert result.is_valid
    
    def test_match_single_file_fuzzy_match(self, matcher, temp_dir, sample_execution_config):
        """Test matching single file with fuzzy match"""
        # Create file with similar but not exact name
        csv_path = os.path.join(temp_dir, "user_data.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'email'])
            writer.writerow(['1', 'John Doe', 'john@example.com'])
        
        file_info = FileInfo(
            file_path=csv_path,
            filename="user_data.csv",
            basename="user_data",
            extension=".csv",
            size=100,
            exists=True,
            is_readable=True,
            directory=temp_dir
        )
        
        candidates = matcher._create_dataset_candidates(sample_execution_config)
        result = matcher._match_single_file(file_info, candidates)
        
        assert result.dataset_name == "users"
        assert result.confidence >= matcher.fuzzy_threshold
        assert result.matching_strategy in [MatchingStrategy.FUZZY_MATCH, MatchingStrategy.PATTERN_MATCH]
        assert result.is_valid
    
    def test_match_single_file_no_match(self, matcher, temp_dir, sample_execution_config):
        """Test matching single file with no match"""
        # Create file with unrelated name
        csv_path = os.path.join(temp_dir, "unrelated.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])
            writer.writerow(['1', 'Test'])
        
        file_info = FileInfo(
            file_path=csv_path,
            filename="unrelated.csv",
            basename="unrelated",
            extension=".csv",
            size=100,
            exists=True,
            is_readable=True,
            directory=temp_dir
        )
        
        candidates = matcher._create_dataset_candidates(sample_execution_config)
        result = matcher._match_single_file(file_info, candidates)
        
        assert result.confidence < matcher.fuzzy_threshold
        assert not result.is_valid


class TestBatchMatching:
    """Test batch file matching"""
    
    def test_match_files_to_datasets_success(self, matcher, sample_csv_file, sample_json_file, sample_execution_config):
        """Test successful batch matching"""
        selected_files = [sample_csv_file, sample_json_file]
        
        result = matcher.match_files_to_datasets(selected_files, sample_execution_config)
        
        assert isinstance(result, BatchMatchResult)
        assert result.total_files == 2
        assert result.total_datasets == 2
        assert len(result.successful_matches) == 2
        assert len(result.failed_matches) == 0
        assert len(result.unmatched_files) == 0
        assert result.match_rate == 1.0
        
        # Check specific matches
        matched_datasets = {match.dataset_name for match in result.successful_matches}
        assert "users" in matched_datasets
        assert "products" in matched_datasets
    
    def test_match_files_to_datasets_partial_success(self, matcher, sample_csv_file, temp_dir, sample_execution_config):
        """Test partial success in batch matching"""
        # Create an unmatched file
        unmatched_file = os.path.join(temp_dir, "unrelated.csv")
        with open(unmatched_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['col1', 'col2'])
            writer.writerow(['val1', 'val2'])
        
        selected_files = [sample_csv_file, unmatched_file]
        
        result = matcher.match_files_to_datasets(selected_files, sample_execution_config)
        
        assert result.total_files == 2
        assert len(result.successful_matches) == 1
        assert len(result.unmatched_files) == 1
        assert result.match_rate == 0.5
    
    def test_match_files_to_datasets_with_nonexistent_files(self, matcher, sample_csv_file, sample_execution_config, mock_error_manager):
        """Test batch matching with non-existent files"""
        selected_files = [sample_csv_file, "/nonexistent/file.csv"]
        
        result = matcher.match_files_to_datasets(selected_files, sample_execution_config)
        
        assert result.total_files == 1  # Only existing file processed
        assert len(result.successful_matches) == 1
        
        # Check error was recorded
        mock_error_manager.record_error.assert_called()


class TestCompatibilityAnalysis:
    """Test file compatibility analysis"""
    
    def test_analyze_file_compatibility_csv(self, matcher, sample_csv_file):
        """Test compatibility analysis for CSV file"""
        dataset_requirements = {
            'required_columns': ['id', 'name', 'email'],
            'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        result = matcher.analyze_file_compatibility(
            sample_csv_file,
            dataset_requirements
        )
        
        assert result['compatible']
        assert result['compatibility_score'] > 0.6
        assert len(result['issues']) == 0
        assert result['file_info']['extension'] == '.csv'
    
    def test_analyze_file_compatibility_json(self, matcher, sample_json_file):
        """Test compatibility analysis for JSON file"""
        dataset_requirements = {
            'required_columns': ['id', 'name', 'price'],
            'expected_types': {'id': 'int', 'name': 'str', 'price': 'float'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        result = matcher.analyze_file_compatibility(
            sample_json_file,
            dataset_requirements
        )
        
        assert result['compatible']
        assert result['compatibility_score'] > 0.6
        assert len(result['issues']) == 0
        assert result['file_info']['extension'] == '.json'
    
    def test_analyze_file_compatibility_missing_columns(self, matcher, temp_dir):
        """Test compatibility analysis with missing columns"""
        # Create CSV with missing columns
        csv_path = os.path.join(temp_dir, "incomplete.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])  # Missing email column
            writer.writerow(['1', 'John'])
        
        dataset_requirements = {
            'required_columns': ['id', 'name', 'email'],
            'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'}
        }
        
        result = matcher.analyze_file_compatibility(
            csv_path,
            dataset_requirements
        )
        
        assert not result['compatible']
        assert result['compatibility_score'] < 0.6
        assert any("Missing columns" in issue for issue in result['issues'])
    
    def test_analyze_file_compatibility_nonexistent_file(self, matcher, mock_error_manager):
        """Test compatibility analysis with non-existent file"""
        result = matcher.analyze_file_compatibility(
            "/nonexistent/file.csv",
            {}
        )
        
        assert not result['compatible']
        assert result['compatibility_score'] == 0.0
        assert any("does not exist" in issue for issue in result['issues'])


class TestUtilityMethods:
    """Test utility methods"""
    
    def test_normalize_dataset_name(self, matcher):
        """Test dataset name normalization"""
        test_cases = [
            ("User_Data", "userdata"),
            ("user-data", "userdata"),
            ("User Data", "userdata"),
            ("USER_DATA", "userdata"),
            ("user_data_table", "userdatatable")
        ]
        
        for input_name, expected in test_cases:
            result = matcher._normalize_dataset_name(input_name)
            assert result == expected, f"Expected {expected} for {input_name}, got {result}"
    
    def test_clean_dataset_name(self, matcher):
        """Test dataset name cleaning"""
        test_cases = [
            ("data_users", "users"),
            ("dataset_products", "products"),
            ("table_orders", "orders"),
            ("file_customers", "customers"),
            ("users_data", "users"),
            ("products_dataset", "products"),
            ("orders_table", "orders"),
            ("customers_file", "customers"),
            ("users_123", "users"),
            ("products_456", "products")
        ]
        
        for input_name, expected in test_cases:
            result = matcher._clean_dataset_name(input_name)
            assert result == expected, f"Expected {expected} for {input_name}, got {result}"
    
    def test_create_dataset_candidates(self, matcher, sample_execution_config):
        """Test dataset candidate creation"""
        candidates = matcher._create_dataset_candidates(sample_execution_config)
        
        assert len(candidates) == 2
        
        # Check users dataset candidate
        users_candidate = next(c for c in candidates if c.dataset_name == "users")
        assert users_candidate.normalized_name == "users"
        assert "id" in users_candidate.required_columns
        assert "name" in users_candidate.required_columns
        assert "email" in users_candidate.required_columns
        assert users_candidate.primary_keys == ["id"]
        
        # Check products dataset candidate
        products_candidate = next(c for c in candidates if c.dataset_name == "products")
        assert products_candidate.normalized_name == "products"
        assert "id" in products_candidate.required_columns
        assert "name" in products_candidate.required_columns
        assert "price" in products_candidate.required_columns
        assert products_candidate.primary_keys == ["id"]


class TestErrorHandling:
    """Test error handling in FileDatasetMatcher"""
    
    def test_error_recording_on_file_info_creation_failure(self, matcher, mock_error_manager):
        """Test error recording when file info creation fails"""
        with patch('os.path.exists', side_effect=Exception("Test error")):
            result = matcher.match_files_to_datasets(
                ["/test/file.csv"],
                ExecutionConfig(mapping_id=1, mapping_name="test", organization="test")
            )
        
        mock_error_manager.record_error.assert_called()
        assert result.total_files == 0
    
    def test_error_recording_on_validation_failure(self, matcher, mock_error_manager):
        """Test error recording when validation fails"""
        with patch.object(matcher, 'validate_file_structure', side_effect=Exception("Validation error")):
            result = matcher.validate_file_structure(
                "/test/file.csv",
                DatasetConfig(dataset_name="test", columns=[])
            )
        
        mock_error_manager.record_error.assert_called()
        assert not result[0]  # is_valid should be False
    
    def test_error_recording_on_compatibility_analysis_failure(self, matcher, mock_error_manager):
        """Test error recording when compatibility analysis fails"""
        with patch('os.path.exists', side_effect=Exception("Test error")):
            result = matcher.analyze_file_compatibility(
                "/test/file.csv",
                {}
            )
        
        mock_error_manager.record_error.assert_called()
        assert not result['compatible']
        assert result['compatibility_score'] == 0.0


@pytest.mark.integration
class TestIntegrationWithExistingServices:
    """Integration tests with existing services"""
    
    def test_integration_with_execution_config(self, matcher, sample_execution_config):
        """Test integration with ExecutionConfig"""
        # This test verifies that the matcher can work with real ExecutionConfig objects
        candidates = matcher._create_dataset_candidates(sample_execution_config)
        
        assert len(candidates) == 2
        assert all(isinstance(c.config, DatasetConfig) for c in candidates)
        assert all(c.required_columns for c in candidates)
    
    def test_integration_with_error_manager(self, mock_error_manager):
        """Test integration with ErrorManager"""
        matcher = FileDatasetMatcher(error_manager=mock_error_manager)
        
        # Trigger an error condition
        matcher.match_files_to_datasets(
            ["/nonexistent/file.csv"],
            ExecutionConfig(mapping_id=1, mapping_name="test", organization="test")
        )
        
        # Verify error was recorded
        mock_error_manager.record_error.assert_called()
        call_args = mock_error_manager.record_error.call_args
        assert call_args[1]['error_category'] == 'file_processing'
        assert 'FILE_INFO_CREATION_ERROR' in call_args[1]['error_code']