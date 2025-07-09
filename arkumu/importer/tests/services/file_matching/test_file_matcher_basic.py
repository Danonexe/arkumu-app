"""
Basic tests for FileDatasetMatcher without Django dependencies
"""

import os
import tempfile
import json
import csv
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from arkumu.importer.services.file_matching.file_dataset_matcher import (
    FileDatasetMatcher,
    FileInfo,
    DatasetMatchCandidate,
    MatchResult,
    BatchMatchResult,
    MatchingStrategy
)


class TestFileDatasetMatcherBasic:
    """Basic test suite for FileDatasetMatcher without Django dependencies"""
    
    @pytest.fixture
    def basic_basic_matcher(self):
        """Create FileDatasetMatcher instance"""
        return FileDatasetMatcher()
    
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
    def mock_dataset_config(self):
        """Create mock dataset configuration"""
        config = Mock()
        config.dataset_name = "users"
        config.columns = [
            Mock(column_name="id"),
            Mock(column_name="name"),
            Mock(column_name="email")
        ]
        config.primary_key_columns = ["id"]
        config.dependencies = []
        return config
    
    @pytest.fixture
    def mock_execution_config(self, mock_dataset_config):
        """Create mock execution configuration"""
        config = Mock()
        config.datasets = [mock_dataset_config]
        config.mapping_id = 1
        config.mapping_name = "Test Mapping"
        config.organization = "test_org"
        return config


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
    
    def test_get_dataset_from_filename_basic(self, basic_matcher):
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
            result = basic_matcher.get_dataset_from_filename(filename)
            assert result == expected, f"Expected {expected} for {filename}, got {result}"
    
    def test_get_dataset_from_filename_edge_cases(self, basic_matcher):
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
            result = basic_matcher.get_dataset_from_filename(filename)
            assert result == expected, f"Expected {expected} for {filename}, got {result}"
    
    def test_get_dataset_from_filename_none_cases(self, basic_matcher):
        """Test cases where no dataset name can be extracted"""
        test_cases = [
            "",
            ".",
            ".csv",
            "123.json",
            "_.csv"
        ]
        
        for filename in test_cases:
            result = basic_matcher.get_dataset_from_filename(filename)
            assert result is None or result == "", f"Expected None/empty for {filename}, got {result}"


class TestMatchingStrategies:
    """Test different matching strategies"""
    
    def test_exact_match_strategy(self, basic_matcher):
        """Test exact matching strategy"""
        assert basic_matcher._exact_match("users", "users") == 1.0
        assert basic_matcher._exact_match("Users", "users") == 1.0
        assert basic_matcher._exact_match("users", "products") == 0.0
        assert basic_matcher._exact_match(None, "users") == 0.0
    
    def test_fuzzy_match_strategy(self, basic_matcher):
        """Test fuzzy matching strategy"""
        assert basic_matcher._fuzzy_match("users", "users") == 1.0
        assert basic_matcher._fuzzy_match("user", "users") > 0.8
        assert basic_matcher._fuzzy_match("users", "products") < 0.5
        assert basic_matcher._fuzzy_match(None, "users") == 0.0
    
    def test_pattern_match_strategy(self, basic_matcher):
        """Test pattern matching strategy"""
        assert basic_matcher._pattern_match("users", "users") == 0.8
        assert basic_matcher._pattern_match("user", "users") == 0.8
        assert basic_matcher._pattern_match("user_data", "users") == 0.8
        assert basic_matcher._pattern_match("users_table", "users") == 0.8
        assert basic_matcher._pattern_match("users", "products") == 0.0
    
    def test_contains_match_strategy(self, basic_matcher):
        """Test contains matching strategy"""
        assert basic_matcher._contains_match("users", "users") == 0.7
        assert basic_matcher._contains_match("user", "users") == 0.7
        assert basic_matcher._contains_match("users", "user") == 0.7
        assert basic_matcher._contains_match("users", "products") == 0.0
        assert basic_matcher._contains_match(None, "users") == 0.0


class TestUtilityMethods:
    """Test utility methods"""
    
    def test_normalize_dataset_name(self, basic_matcher):
        """Test dataset name normalization"""
        test_cases = [
            ("User_Data", "userdata"),
            ("user-data", "userdata"),
            ("User Data", "userdata"),
            ("USER_DATA", "userdata"),
            ("user_data_table", "userdatatable")
        ]
        
        for input_name, expected in test_cases:
            result = basic_matcher._normalize_dataset_name(input_name)
            assert result == expected, f"Expected {expected} for {input_name}, got {result}"
    
    def test_clean_dataset_name(self, basic_matcher):
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
            result = basic_matcher._clean_dataset_name(input_name)
            assert result == expected, f"Expected {expected} for {input_name}, got {result}"
    
    def test_create_dataset_candidates(self, basic_matcher, mock_execution_config):
        """Test dataset candidate creation"""
        candidates = basic_matcher._create_dataset_candidates(mock_execution_config)
        
        assert len(candidates) == 1
        
        # Check users dataset candidate
        users_candidate = candidates[0]
        assert users_candidate.dataset_name == "users"
        assert users_candidate.normalized_name == "users"
        assert len(users_candidate.required_columns) == 3
        assert users_candidate.primary_keys == ["id"]


class TestFileCreation:
    """Test file creation methods"""
    
    def test_create_file_info(self, basic_matcher, sample_csv_file):
        """Test file info creation"""
        file_info = basic_matcher._create_file_info(sample_csv_file)
        
        assert file_info.file_path == sample_csv_file
        assert file_info.filename == "users.csv"
        assert file_info.basename == "users"
        assert file_info.extension == ".csv"
        assert file_info.exists
        assert file_info.is_readable
        assert file_info.size > 0
    
    def test_create_file_info_nonexistent(self, basic_matcher):
        """Test file info creation with nonexistent file"""
        file_info = basic_matcher._create_file_info("/nonexistent/file.csv")
        
        assert file_info.file_path == "/nonexistent/file.csv"
        assert file_info.filename == "file.csv"
        assert file_info.basename == "file"
        assert file_info.extension == ".csv"
        assert not file_info.exists
        assert not file_info.is_readable
        assert file_info.size == 0


class TestCompatibilityAnalysis:
    """Test file compatibility analysis"""
    
    def test_analyze_file_compatibility_csv(self, basic_matcher, sample_csv_file):
        """Test compatibility analysis for CSV file"""
        dataset_requirements = {
            'required_columns': ['id', 'name', 'email'],
            'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        result = basic_matcher.analyze_file_compatibility(
            sample_csv_file,
            dataset_requirements
        )
        
        assert result['compatible']
        assert result['compatibility_score'] > 0.6
        assert len(result['issues']) == 0
        assert result['file_info']['extension'] == '.csv'
    
    def test_analyze_file_compatibility_json(self, basic_matcher, sample_json_file):
        """Test compatibility analysis for JSON file"""
        dataset_requirements = {
            'required_columns': ['id', 'name', 'price'],
            'expected_types': {'id': 'int', 'name': 'str', 'price': 'float'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        result = basic_matcher.analyze_file_compatibility(
            sample_json_file,
            dataset_requirements
        )
        
        assert result['compatible']
        assert result['compatibility_score'] > 0.6
        assert len(result['issues']) == 0
        assert result['file_info']['extension'] == '.json'
    
    def test_analyze_file_compatibility_nonexistent_file(self, basic_matcher):
        """Test compatibility analysis with non-existent file"""
        result = basic_matcher.analyze_file_compatibility(
            "/nonexistent/file.csv",
            {}
        )
        
        assert not result['compatible']
        assert result['compatibility_score'] == 0.0
        assert any("does not exist" in issue for issue in result['issues'])


class TestSingleFileMatching:
    """Test single file matching without Django dependencies"""
    
    def test_match_single_file_basic(self, basic_matcher, sample_csv_file):
        """Test basic single file matching"""
        file_info = basic_matcher._create_file_info(sample_csv_file)
        
        # Create mock candidate
        mock_candidate = Mock()
        mock_candidate.dataset_name = "users"
        mock_candidate.normalized_name = "users"
        mock_candidate.config = Mock()
        mock_candidate.config.dataset_name = "users"
        mock_candidate.config.columns = [
            Mock(column_name="id"),
            Mock(column_name="name"),
            Mock(column_name="email")
        ]
        
        candidates = [mock_candidate]
        
        result = basic_matcher._match_single_file(file_info, candidates)
        
        assert result.dataset_name == "users"
        assert result.confidence == 1.0
        assert result.matching_strategy == MatchingStrategy.EXACT_MATCH
        assert result.file_info.filename == "users.csv"
    
    def test_match_single_file_no_match(self, basic_matcher, temp_dir):
        """Test single file matching with no match"""
        # Create file with unrelated name
        csv_path = os.path.join(temp_dir, "unrelated.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name'])
            writer.writerow(['1', 'Test'])
        
        file_info = basic_matcher._create_file_info(csv_path)
        
        # Create mock candidate with different name
        mock_candidate = Mock()
        mock_candidate.dataset_name = "users"
        mock_candidate.normalized_name = "users"
        mock_candidate.config = Mock()
        mock_candidate.config.dataset_name = "users"
        
        candidates = [mock_candidate]
        
        result = basic_matcher._match_single_file(file_info, candidates)
        
        assert result.confidence < basic_matcher.fuzzy_threshold
        assert not result.is_valid or result.confidence < basic_matcher.fuzzy_threshold