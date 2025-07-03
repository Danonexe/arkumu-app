#!/usr/bin/env python3
"""
Simple test script to verify the modular structure works correctly.
This can be run independently to test the import and basic functionality.
"""

import sys
import os

# Add the project root to the Python path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))

def test_imports():
    """Test that all modules can be imported successfully."""
    print("Testing imports...")
    
    try:
        from arkumu.importer.services.importer.bulk_data_analyzer import BulkDataAnalyzer
        print("✓ BulkDataAnalyzer imported successfully")
        
        from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
        print("✓ BulkURIService imported successfully")
        
        from arkumu.importer.services.importer.bulk_update_engine import BulkUpdateEngine, UpdateStrategy, BulkUpdateStats
        print("✓ BulkUpdateEngine imported successfully")
        
        from arkumu.importer.services.importer.bulk_database_executor import BulkDatabaseExecutor
        print("✓ BulkDatabaseExecutor imported successfully")
        
        from arkumu.importer.services.importer.bulk_relationship_processor import BulkRelationshipProcessor, FKRelationship
        print("✓ BulkRelationshipProcessor imported successfully")
        
        # Test that import_workflow and mapping_processor work with modular imports
        from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
        print("✓ ImportWorkflowService (with modular imports) imported successfully")
        
        from arkumu.importer.services.importer.mapping_processor import GUIMappingProcessor
        print("✓ GUIMappingProcessor (with modular imports) imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without database access."""
    print("\nTesting basic functionality...")
    
    try:
        import polars as pl
        from arkumu.importer.services.importer.bulk_data_analyzer import BulkDataAnalyzer
        from arkumu.importer.services.importer.bulk_uri_service import BulkURIService
        
        # Test data analyzer
        analyzer = BulkDataAnalyzer(multi_value_threshold=0.2)
        test_df = pl.DataFrame({
            "name": ["Alice", "Bob,Charlie", "David"],
            "age": [25, 30, 35]
        })
        
        multi_value_analysis = analyzer.analyze_dataset_multi_values(test_df)
        print(f"✓ Multi-value analysis completed: {len(multi_value_analysis)} columns analyzed")
        
        # Test URI service
        uri_service = BulkURIService("http://test.org", "test_institution")
        
        dataset_uri = uri_service.generate_dataset_uri("test_dataset")
        print(f"✓ Dataset URI generated: {dataset_uri}")
        
        cell_uri = uri_service.generate_cell_uri("test_dataset", "name", "row1")
        print(f"✓ Cell URI generated: {cell_uri}")
        
        # Test URI parsing
        row_id = uri_service.extract_row_id_from_uri(cell_uri)
        column_name = uri_service.extract_column_name_from_uri(cell_uri)
        print(f"✓ URI parsing: row_id={row_id}, column_name={column_name}")
        
        return True
        
    except Exception as e:
        print(f"✗ Functionality test failed: {e}")
        return False

def test_modular_architecture():
    """Test that the modular architecture is properly structured."""
    print("\nTesting modular architecture...")
    
    try:
        from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
        from arkumu.importer.services.importer.mapping_processor import GUIMappingProcessor
        from arkumu.importer.services.importer.bulk_update_engine import UpdateStrategy
        
        # Test that ImportWorkflowService can be instantiated and has modular services
        workflow_service = ImportWorkflowService()
        
        # Verify that modular services are available
        assert workflow_service.data_analyzer is not None, "Data analyzer not initialized"
        assert hasattr(workflow_service, 'uri_service'), "URI service attribute not available"
        assert workflow_service.update_engine is not None, "Update engine not initialized"
        assert workflow_service.database_executor is not None, "Database executor not initialized"
        assert workflow_service.relationship_processor is not None, "Relationship processor not initialized"
        
        print("✓ ImportWorkflowService modular architecture properly structured")
        
        # Test that GUIMappingProcessor can be instantiated
        mapping_processor = GUIMappingProcessor()
        assert hasattr(mapping_processor, 'data_analyzer'), "Mapping processor missing data_analyzer attribute"
        assert hasattr(mapping_processor, 'uri_service'), "Mapping processor missing uri_service attribute"
        
        print("✓ GUIMappingProcessor modular architecture properly structured")
        
        return True
        
    except Exception as e:
        print(f"✗ Architecture test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Modular Smart Bulk Updater Architecture")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_basic_functionality,
        test_modular_architecture
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Modular structure is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())