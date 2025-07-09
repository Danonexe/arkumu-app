"""
Pytest configuration and fixtures for file matching tests
"""

import os
import tempfile
import json
import csv
import pytest
from unittest.mock import Mock
from pathlib import Path

from arkumu.importer.services.file_matching.file_dataset_matcher import FileDatasetMatcher
from arkumu.importer.services.mapping_consumer.config_translator import (
    ExecutionConfig,
    DatasetConfig,
    ColumnConfig,
    ColumnType
)
from arkumu.importer.services.error_handling.error_manager import ErrorManager


@pytest.fixture
def temp_directory():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_error_manager():
    """Create a mock error manager"""
    error_manager = Mock(spec=ErrorManager)
    error_manager.record_error = Mock()
    return error_manager


@pytest.fixture
def file_matcher(mock_error_manager):
    """Create a FileDatasetMatcher instance with mock error manager"""
    return FileDatasetMatcher(error_manager=mock_error_manager)


@pytest.fixture
def sample_users_csv(temp_directory):
    """Create a sample users CSV file"""
    csv_path = os.path.join(temp_directory, "users.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'email', 'age'])
        writer.writerow(['1', 'John Doe', 'john@example.com', '30'])
        writer.writerow(['2', 'Jane Smith', 'jane@example.com', '25'])
        writer.writerow(['3', 'Bob Johnson', 'bob@example.com', '35'])
    return csv_path


@pytest.fixture
def sample_products_json(temp_directory):
    """Create a sample products JSON file"""
    json_path = os.path.join(temp_directory, "products.json")
    data = [
        {"id": 1, "name": "Laptop", "price": 999.99, "category": "Electronics"},
        {"id": 2, "name": "Phone", "price": 599.99, "category": "Electronics"},
        {"id": 3, "name": "Book", "price": 19.99, "category": "Books"}
    ]
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=2)
    return json_path


@pytest.fixture
def sample_orders_tsv(temp_directory):
    """Create a sample orders TSV file"""
    tsv_path = os.path.join(temp_directory, "orders.tsv")
    with open(tsv_path, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['order_id', 'user_id', 'product_id', 'quantity', 'order_date'])
        writer.writerow(['1', '1', '1', '1', '2023-01-15'])
        writer.writerow(['2', '2', '2', '2', '2023-01-16'])
        writer.writerow(['3', '1', '3', '1', '2023-01-17'])
    return tsv_path


@pytest.fixture
def sample_invalid_csv(temp_directory):
    """Create an invalid CSV file (missing required columns)"""
    csv_path = os.path.join(temp_directory, "invalid_users.csv")
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name'])  # Missing email column
        writer.writerow(['1', 'John Doe'])
        writer.writerow(['2', 'Jane Smith'])
    return csv_path


@pytest.fixture
def sample_empty_file(temp_directory):
    """Create an empty file"""
    empty_path = os.path.join(temp_directory, "empty.csv")
    Path(empty_path).touch()
    return empty_path


@pytest.fixture
def sample_large_file(temp_directory):
    """Create a large file for testing size limits"""
    large_path = os.path.join(temp_directory, "large.csv")
    with open(large_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'data'])
        # Write enough data to make file large
        for i in range(10000):
            writer.writerow([i, f"data_{i}" * 100])
    return large_path


@pytest.fixture
def comprehensive_execution_config():
    """Create a comprehensive execution configuration with multiple datasets"""
    
    # Users dataset
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
        ),
        ColumnConfig(
            column_name="age",
            dataset_name="users",
            arkumu_type="user_age",
            column_type=ColumnType.REGULAR
        )
    ]
    
    # Products dataset
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
        ),
        ColumnConfig(
            column_name="category",
            dataset_name="products",
            arkumu_type="product_category",
            column_type=ColumnType.REGULAR
        )
    ]
    
    # Orders dataset
    orders_columns = [
        ColumnConfig(
            column_name="order_id",
            dataset_name="orders",
            arkumu_type="order_id",
            column_type=ColumnType.ANCHOR,
            is_anchor=True
        ),
        ColumnConfig(
            column_name="user_id",
            dataset_name="orders",
            arkumu_type="user_id",
            column_type=ColumnType.FOREIGN_KEY
        ),
        ColumnConfig(
            column_name="product_id",
            dataset_name="orders",
            arkumu_type="product_id",
            column_type=ColumnType.FOREIGN_KEY
        ),
        ColumnConfig(
            column_name="quantity",
            dataset_name="orders",
            arkumu_type="order_quantity",
            column_type=ColumnType.REGULAR
        ),
        ColumnConfig(
            column_name="order_date",
            dataset_name="orders",
            arkumu_type="order_date",
            column_type=ColumnType.REGULAR
        )
    ]
    
    # Create dataset configurations
    users_dataset = DatasetConfig(
        dataset_name="users",
        columns=users_columns,
        primary_key_columns=["id"],
        dependencies=[]
    )
    
    products_dataset = DatasetConfig(
        dataset_name="products",
        columns=products_columns,
        primary_key_columns=["id"],
        dependencies=[]
    )
    
    orders_dataset = DatasetConfig(
        dataset_name="orders",
        columns=orders_columns,
        primary_key_columns=["order_id"],
        dependencies=["users", "products"]
    )
    
    return ExecutionConfig(
        mapping_id=1,
        mapping_name="Comprehensive Test Mapping",
        organization="test_org",
        version="1.1",
        datasets=[users_dataset, products_dataset, orders_dataset]
    )


@pytest.fixture
def file_collection(temp_directory):
    """Create a collection of test files with different naming patterns"""
    files = {}
    
    # Exact match files
    files['users_exact'] = os.path.join(temp_directory, "users.csv")
    files['products_exact'] = os.path.join(temp_directory, "products.json")
    files['orders_exact'] = os.path.join(temp_directory, "orders.tsv")
    
    # Underscore pattern files
    files['users_underscore'] = os.path.join(temp_directory, "users_data.csv")
    files['products_underscore'] = os.path.join(temp_directory, "products_catalog.json")
    files['orders_underscore'] = os.path.join(temp_directory, "orders_history.tsv")
    
    # Hyphen pattern files
    files['users_hyphen'] = os.path.join(temp_directory, "users-export.csv")
    files['products_hyphen'] = os.path.join(temp_directory, "products-list.json")
    files['orders_hyphen'] = os.path.join(temp_directory, "orders-report.tsv")
    
    # With numbers/versions
    files['users_numbered'] = os.path.join(temp_directory, "users_2023.csv")
    files['products_versioned'] = os.path.join(temp_directory, "products_v2.json")
    files['orders_dated'] = os.path.join(temp_directory, "orders_20231201.tsv")
    
    # Create all files with basic content
    for name, path in files.items():
        if path.endswith('.csv') or path.endswith('.tsv'):
            delimiter = '\t' if path.endswith('.tsv') else ','
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f, delimiter=delimiter)
                if 'users' in name:
                    writer.writerow(['id', 'name', 'email', 'age'])
                    writer.writerow(['1', 'John', 'john@example.com', '30'])
                elif 'products' in name:
                    writer.writerow(['id', 'name', 'price', 'category'])
                    writer.writerow(['1', 'Product', '10.99', 'Category'])
                elif 'orders' in name:
                    writer.writerow(['order_id', 'user_id', 'product_id', 'quantity', 'order_date'])
                    writer.writerow(['1', '1', '1', '1', '2023-01-15'])
        
        elif path.endswith('.json'):
            if 'products' in name:
                data = [{"id": 1, "name": "Product", "price": 10.99, "category": "Category"}]
            else:
                data = [{"id": 1, "name": "Item"}]
            
            with open(path, 'w') as f:
                json.dump(data, f)
    
    return files


@pytest.fixture
def dataset_requirements():
    """Create sample dataset requirements for compatibility testing"""
    return {
        'users': {
            'required_columns': ['id', 'name', 'email', 'age'],
            'expected_types': {
                'id': 'int',
                'name': 'str',
                'email': 'str',
                'age': 'int'
            },
            'size_range': (100, 1024 * 1024)  # 100 bytes to 1MB
        },
        'products': {
            'required_columns': ['id', 'name', 'price', 'category'],
            'expected_types': {
                'id': 'int',
                'name': 'str',
                'price': 'float',
                'category': 'str'
            },
            'size_range': (100, 1024 * 1024)  # 100 bytes to 1MB
        },
        'orders': {
            'required_columns': ['order_id', 'user_id', 'product_id', 'quantity', 'order_date'],
            'expected_types': {
                'order_id': 'int',
                'user_id': 'int',
                'product_id': 'int',
                'quantity': 'int',
                'order_date': 'str'
            },
            'size_range': (100, 1024 * 1024)  # 100 bytes to 1MB
        }
    }