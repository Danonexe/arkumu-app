"""
Standalone tests for FileDatasetMatcher core functionality
"""

import tempfile
import os
import csv
import json
from pathlib import Path

from arkumu.importer.services.file_matching.file_dataset_matcher import (
    FileDatasetMatcher,
    FileInfo,
    MatchingStrategy
)


def test_file_info_creation():
    """Test FileInfo creation and post_init"""
    with tempfile.TemporaryDirectory() as temp_dir:
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


def test_dataset_name_extraction():
    """Test basic dataset name extraction"""
    matcher = FileDatasetMatcher()
    
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


def test_matching_strategies():
    """Test different matching strategies"""
    matcher = FileDatasetMatcher()
    
    # Test exact match
    assert matcher._exact_match("users", "users") == 1.0
    assert matcher._exact_match("Users", "users") == 1.0
    assert matcher._exact_match("users", "products") == 0.0
    assert matcher._exact_match(None, "users") == 0.0
    
    # Test fuzzy match
    assert matcher._fuzzy_match("users", "users") == 1.0
    assert matcher._fuzzy_match("user", "users") > 0.8
    assert matcher._fuzzy_match("users", "products") < 0.5
    assert matcher._fuzzy_match(None, "users") == 0.0
    
    # Test pattern match
    assert matcher._pattern_match("users", "users") == 0.8
    assert matcher._pattern_match("user", "users") == 0.8
    assert matcher._pattern_match("users", "products") == 0.0
    
    # Test contains match
    assert matcher._contains_match("users", "users") == 0.7
    assert matcher._contains_match("user", "users") == 0.7
    assert matcher._contains_match("users", "products") == 0.0
    assert matcher._contains_match(None, "users") == 0.0


def test_utility_methods():
    """Test utility methods"""
    matcher = FileDatasetMatcher()
    
    # Test normalize dataset name
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
    
    # Test clean dataset name
    clean_test_cases = [
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
    
    for input_name, expected in clean_test_cases:
        result = matcher._clean_dataset_name(input_name)
        assert result == expected, f"Expected {expected} for {input_name}, got {result}"


def test_file_creation():
    """Test file creation methods"""
    matcher = FileDatasetMatcher()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create CSV file
        csv_path = os.path.join(temp_dir, "users.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'email'])
            writer.writerow(['1', 'John Doe', 'john@example.com'])
        
        file_info = matcher._create_file_info(csv_path)
        
        assert file_info.file_path == csv_path
        assert file_info.filename == "users.csv"
        assert file_info.basename == "users"
        assert file_info.extension == ".csv"
        assert file_info.exists
        assert file_info.is_readable
        assert file_info.size > 0
        
        # Test nonexistent file
        file_info_nonexistent = matcher._create_file_info("/nonexistent/file.csv")
        assert not file_info_nonexistent.exists
        assert not file_info_nonexistent.is_readable
        assert file_info_nonexistent.size == 0


def test_compatibility_analysis():
    """Test basic compatibility analysis"""
    matcher = FileDatasetMatcher()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create CSV file
        csv_path = os.path.join(temp_dir, "users.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'email'])
            writer.writerow(['1', 'John Doe', 'john@example.com'])
        
        dataset_requirements = {
            'required_columns': ['id', 'name', 'email'],
            'expected_types': {'id': 'int', 'name': 'str', 'email': 'str'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        result = matcher.analyze_file_compatibility(csv_path, dataset_requirements)
        
        assert result['compatible']
        assert result['compatibility_score'] > 0.6
        assert len(result['issues']) == 0
        assert result['file_info']['extension'] == '.csv'
        
        # Test JSON file
        json_path = os.path.join(temp_dir, "products.json")
        data = [{"id": 1, "name": "Product A", "price": 10.99}]
        with open(json_path, 'w') as f:
            json.dump(data, f)
        
        json_requirements = {
            'required_columns': ['id', 'name', 'price'],
            'expected_types': {'id': 'int', 'name': 'str', 'price': 'float'},
            'size_range': (0, 1024 * 1024)  # 0-1MB
        }
        
        json_result = matcher.analyze_file_compatibility(json_path, json_requirements)
        assert json_result['compatible']
        assert json_result['compatibility_score'] > 0.6
        assert json_result['file_info']['extension'] == '.json'


def test_nonexistent_file_handling():
    """Test handling of nonexistent files"""
    matcher = FileDatasetMatcher()
    
    result = matcher.analyze_file_compatibility("/nonexistent/file.csv", {})
    assert not result['compatible']
    assert result['compatibility_score'] == 0.0
    assert any("does not exist" in issue for issue in result['issues'])


if __name__ == "__main__":
    # Run all tests
    test_file_info_creation()
    test_dataset_name_extraction()
    test_matching_strategies()
    test_utility_methods()
    test_file_creation()
    test_compatibility_analysis()
    test_nonexistent_file_handling()
    print("All tests passed!")