"""
Example usage of the FileDatasetMatcher service

This script demonstrates how to use the file matching service
for various file-to-dataset matching scenarios.
"""

import os
import tempfile
import csv
import json
from pathlib import Path

from .file_dataset_matcher import FileDatasetMatcher
from .integration_helpers import create_file_matching_integration


def create_sample_files():
    """Create sample files for demonstration"""
    temp_dir = tempfile.mkdtemp()
    
    # Create users CSV
    users_path = os.path.join(temp_dir, "users.csv")
    with open(users_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'email', 'age'])
        writer.writerow(['1', 'John Doe', 'john@example.com', '30'])
        writer.writerow(['2', 'Jane Smith', 'jane@example.com', '25'])
    
    # Create products JSON
    products_path = os.path.join(temp_dir, "products.json")
    products_data = [
        {"id": 1, "name": "Laptop", "price": 999.99, "category": "Electronics"},
        {"id": 2, "name": "Phone", "price": 599.99, "category": "Electronics"}
    ]
    with open(products_path, 'w') as f:
        json.dump(products_data, f, indent=2)
    
    # Create orders TSV
    orders_path = os.path.join(temp_dir, "orders.tsv")
    with open(orders_path, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['order_id', 'user_id', 'product_id', 'quantity'])
        writer.writerow(['1', '1', '1', '1'])
        writer.writerow(['2', '2', '2', '2'])
    
    # Create file with naming variations
    user_data_path = os.path.join(temp_dir, "user_data.csv")
    with open(user_data_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'name', 'email'])
        writer.writerow(['1', 'Alice', 'alice@example.com'])
    
    product_info_path = os.path.join(temp_dir, "product-info.json")
    with open(product_info_path, 'w') as f:
        json.dump([{"id": 1, "name": "Book", "price": 19.99}], f)
    
    return temp_dir, {
        'users': users_path,
        'products': products_path,
        'orders': orders_path,
        'user_data': user_data_path,
        'product_info': product_info_path
    }


def example_basic_matching():
    """Demonstrate basic file matching functionality"""
    print("=== Basic File Matching Example ===")
    
    matcher = FileDatasetMatcher()
    
    # Test dataset name extraction
    print("\n1. Dataset Name Extraction:")
    filenames = [
        "users.csv",
        "products.json",
        "user_data.csv",
        "product-info.json",
        "orders_2023.tsv",
        "customer-list-v2.json"
    ]
    
    for filename in filenames:
        dataset_name = matcher.get_dataset_from_filename(filename)
        print(f"   {filename} -> {dataset_name}")
    
    # Test matching strategies
    print("\n2. Matching Strategies:")
    test_cases = [
        ("users", "users"),
        ("user", "users"),
        ("user_data", "users"),
        ("product", "products"),
        ("unrelated", "users")
    ]
    
    for potential, candidate in test_cases:
        exact = matcher._exact_match(potential, candidate)
        fuzzy = matcher._fuzzy_match(potential, candidate)
        pattern = matcher._pattern_match(potential, candidate)
        contains = matcher._contains_match(potential, candidate)
        
        print(f"   '{potential}' vs '{candidate}':")
        print(f"     Exact: {exact:.2f}, Fuzzy: {fuzzy:.2f}, Pattern: {pattern:.2f}, Contains: {contains:.2f}")


def example_file_validation():
    """Demonstrate file validation functionality"""
    print("\n=== File Validation Example ===")
    
    matcher = FileDatasetMatcher()
    temp_dir, files = create_sample_files()
    
    try:
        # Mock dataset configuration
        class MockDatasetConfig:
            def __init__(self, name, columns):
                self.dataset_name = name
                self.columns = [MockColumn(col) for col in columns]
        
        class MockColumn:
            def __init__(self, name):
                self.column_name = name
        
        # Test validation
        dataset_configs = {
            'users': MockDatasetConfig('users', ['id', 'name', 'email', 'age']),
            'products': MockDatasetConfig('products', ['id', 'name', 'price', 'category']),
            'orders': MockDatasetConfig('orders', ['order_id', 'user_id', 'product_id', 'quantity'])
        }
        
        for dataset_name, config in dataset_configs.items():
            if dataset_name in files:
                file_path = files[dataset_name]
                try:
                    is_valid, issues = matcher.validate_file_structure(file_path, config)
                    print(f"\n   {dataset_name} validation:")
                    print(f"     Valid: {is_valid}")
                    if issues:
                        print(f"     Issues: {issues}")
                except Exception as e:
                    print(f"     Error: {e}")
    
    finally:
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)


def example_compatibility_analysis():
    """Demonstrate compatibility analysis"""
    print("\n=== Compatibility Analysis Example ===")
    
    matcher = FileDatasetMatcher()
    temp_dir, files = create_sample_files()
    
    try:
        # Define dataset requirements
        requirements = {
            'users': {
                'required_columns': ['id', 'name', 'email', 'age'],
                'expected_types': {'id': 'int', 'name': 'str', 'email': 'str', 'age': 'int'},
                'size_range': (100, 1024 * 1024)
            },
            'products': {
                'required_columns': ['id', 'name', 'price', 'category'],
                'expected_types': {'id': 'int', 'name': 'str', 'price': 'float', 'category': 'str'},
                'size_range': (100, 1024 * 1024)
            }
        }
        
        for dataset_name, req in requirements.items():
            if dataset_name in files:
                file_path = files[dataset_name]
                analysis = matcher.analyze_file_compatibility(file_path, req)
                
                print(f"\n   {dataset_name} compatibility:")
                print(f"     Compatible: {analysis['compatible']}")
                print(f"     Score: {analysis['compatibility_score']:.2f}")
                if analysis['issues']:
                    print(f"     Issues: {analysis['issues']}")
                if analysis['recommendations']:
                    print(f"     Recommendations: {analysis['recommendations']}")
    
    finally:
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)


def example_batch_processing():
    """Demonstrate batch processing capabilities"""
    print("\n=== Batch Processing Example ===")
    
    matcher = FileDatasetMatcher()
    temp_dir, files = create_sample_files()
    
    try:
        # Mock execution configuration
        class MockExecutionConfig:
            def __init__(self):
                self.mapping_id = 1
                self.mapping_name = "Example Mapping"
                self.organization = "example_org"
                self.datasets = [
                    MockDatasetConfig('users', ['id', 'name', 'email', 'age']),
                    MockDatasetConfig('products', ['id', 'name', 'price', 'category']),
                    MockDatasetConfig('orders', ['order_id', 'user_id', 'product_id', 'quantity'])
                ]
        
        class MockDatasetConfig:
            def __init__(self, name, columns):
                self.dataset_name = name
                self.columns = [MockColumn(col) for col in columns]
                self.primary_key_columns = ['id'] if 'id' in columns else [columns[0]]
                self.dependencies = []
        
        class MockColumn:
            def __init__(self, name):
                self.column_name = name
        
        # Test batch matching
        execution_config = MockExecutionConfig()
        selected_files = list(files.values())
        
        try:
            result = matcher.match_files_to_datasets(selected_files, execution_config)
            
            print(f"\n   Batch matching results:")
            print(f"     Total files: {result.total_files}")
            print(f"     Total datasets: {result.total_datasets}")
            print(f"     Match rate: {result.match_rate:.2%}")
            print(f"     Successful matches: {len(result.successful_matches)}")
            print(f"     Failed matches: {len(result.failed_matches)}")
            print(f"     Unmatched files: {len(result.unmatched_files)}")
            
            if result.successful_matches:
                print(f"\n   Successful matches:")
                for match in result.successful_matches:
                    print(f"     {match.file_info.filename} -> {match.dataset_name} (confidence: {match.confidence:.2f})")
            
            if result.unmatched_files:
                print(f"\n   Unmatched files:")
                for file_info in result.unmatched_files:
                    print(f"     {file_info.filename}")
        
        except Exception as e:
            print(f"   Error in batch processing: {e}")
    
    finally:
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)


def example_naming_conventions():
    """Demonstrate support for various naming conventions"""
    print("\n=== Naming Conventions Example ===")
    
    matcher = FileDatasetMatcher()
    
    # Test various naming patterns
    naming_examples = [
        # Basic patterns
        ("users.csv", "users"),
        ("products.json", "products"),
        
        # Underscore patterns
        ("user_data.csv", "user"),
        ("product_catalog.json", "product"),
        ("order_history.tsv", "order"),
        
        # Hyphen patterns
        ("user-info.csv", "user"),
        ("product-list.json", "product"),
        ("order-details.tsv", "order"),
        
        # With prefixes
        ("data_users.csv", "users"),
        ("dataset_products.json", "products"),
        ("table_orders.tsv", "orders"),
        
        # With suffixes
        ("users_data.csv", "users"),
        ("products_dataset.json", "products"),
        ("orders_table.tsv", "orders"),
        
        # With versions/numbers
        ("users_v1.csv", "users"),
        ("products_2023.json", "products"),
        ("orders_final.tsv", "orders"),
        
        # Complex patterns
        ("data_user_export_v2.csv", "user"),
        ("product-catalog-2023-final.json", "product"),
        ("order_history_backup_123.tsv", "order")
    ]
    
    print("\n   Naming convention support:")
    for filename, expected in naming_examples:
        result = matcher.get_dataset_from_filename(filename)
        status = "✓" if result == expected else "✗"
        print(f"     {status} {filename:<35} -> {result:<15} (expected: {expected})")


if __name__ == "__main__":
    # Run all examples
    print("FileDatasetMatcher Usage Examples")
    print("=" * 50)
    
    example_basic_matching()
    example_file_validation()
    example_compatibility_analysis()
    example_batch_processing()
    example_naming_conventions()
    
    print("\n" + "=" * 50)
    print("Examples completed successfully!")