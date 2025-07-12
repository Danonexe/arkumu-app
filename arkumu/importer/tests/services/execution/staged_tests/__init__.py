"""
Staged Production Integration Tests

This package contains staged tests that break down the full production integration
pipeline into individual testable stages, each validating specific outputs and behaviors.

Test Stages:
1. test_01_mapping_loading.py - Mapping database storage and loading
2. test_02_mapping_translation.py - Translation to execution config  
3. test_03_csv_data_loading.py - CSV data loading from S3
4. test_04_data_correlation.py - Mapping-CSV correlation analysis
5. test_05_processor_execution.py - Data processing execution
6. test_06_database_validation.py - Database object validation

All tests share the same fixtures from conftest.py to ensure consistency.
"""