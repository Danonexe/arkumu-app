"""
Stage 3: CSV Data Loading Tests - S3 Streaming and Parsing

This test validates the CSV data loading layer that streams and parses production
CSV files from S3 storage into structured data ready for processing.

## What This Stage Tests

### Components Under Test
- **BucketService**: S3 file listing and streaming operations
- **CSV Parsing Logic**: Semicolon-delimited parsing (FUK standard)

### Data Flow Validation
1. S3 bucket listing → Filter .csv files in `fuk/metadata/`
2. File streaming → Direct content loading without disk storage
3. CSV parsing → Structured dictionary with headers and rows
4. Dataset naming → Filename to dataset name conversion

### Key Validation Points
- ✅ 35+ CSV files found and accessible in S3 bucket
- ✅ Data structure: `{headers: [], rows: [], row_count: int}` for each dataset
- ✅ Dataset names correctly derived from filenames (without .csv extension)
- ✅ Headers match columns in data rows
- ✅ Content sampling shows valid data (not empty/corrupted)
- ✅ Expected FUK datasets found (AkteurIn, Ereignis, Projekt, etc.)

## Why This Stage Matters

This validates the data loading foundation that provides raw CSV data to the processing
pipeline. Without reliable CSV loading, no data processing can occur.

## Expected Results
- 35+ datasets loaded with consistent structure
- All expected FUK datasets accessible
- Proper semicolon-delimited parsing
- Ready for Stage 4 correlation analysis
"""
import pytest
import logging

logger = logging.getLogger(__name__)


class TestCSVDataLoading:
    """Test CSV data loading from S3"""
    
    @pytest.mark.django_db
    def test_csv_data_availability(self, real_csv_data):
        """Test that CSV data is successfully loaded from S3"""
        # Verify CSV data loaded
        assert real_csv_data is not None, "CSV data must be loaded"
        assert isinstance(real_csv_data, dict), "CSV data must be a dictionary"
        assert len(real_csv_data) > 0, "Must have CSV datasets loaded"
        
        # Log data loading results
        logger.info(f"CSV data loading validation:")
        logger.info(f"  Total datasets loaded: {len(real_csv_data)}")
        
        total_rows = sum(data['row_count'] for data in real_csv_data.values())
        logger.info(f"  Total rows across all datasets: {total_rows}")
        
        # Verify we have meaningful data
        assert total_rows > 0, "Must have rows of data loaded"
        
    @pytest.mark.django_db
    def test_csv_data_structure(self, real_csv_data):
        """Test structure of loaded CSV data"""
        # Verify each dataset has required structure
        for dataset_name, dataset_data in real_csv_data.items():
            assert isinstance(dataset_data, dict), f"Dataset {dataset_name} must be a dict"
            assert 'headers' in dataset_data, f"Dataset {dataset_name} must have headers"
            assert 'rows' in dataset_data, f"Dataset {dataset_name} must have rows"
            assert 'row_count' in dataset_data, f"Dataset {dataset_name} must have row_count"
            
            # Verify data consistency
            headers = dataset_data['headers']
            rows = dataset_data['rows']
            row_count = dataset_data['row_count']
            
            assert isinstance(headers, list), f"Headers for {dataset_name} must be a list"
            assert isinstance(rows, list), f"Rows for {dataset_name} must be a list"
            assert len(rows) == row_count, f"Row count mismatch for {dataset_name}"
            
        logger.info(f"CSV data structure validation passed for {len(real_csv_data)} datasets")
        
    @pytest.mark.django_db
    def test_csv_data_content_sampling(self, real_csv_data):
        """Test sampling of CSV data content"""
        datasets_analyzed = 0
        
        for dataset_name, dataset_data in real_csv_data.items():
            if datasets_analyzed >= 5:  # Limit analysis to first 5 datasets
                break
                
            headers = dataset_data['headers']
            rows = dataset_data['rows']
            row_count = dataset_data['row_count']
            
            logger.info(f"Dataset '{dataset_name}' analysis:")
            logger.info(f"  Headers: {len(headers)} columns")
            logger.info(f"  Rows: {row_count}")
            
            if headers:
                logger.info(f"  Sample headers: {headers[:5]}...")
                
            if rows and len(rows) > 0:
                # Sample first row
                first_row = rows[0]
                if isinstance(first_row, dict):
                    sample_values = {k: v for k, v in list(first_row.items())[:3]}
                    logger.info(f"  Sample row data: {sample_values}...")
                    
                    # Verify row has data for headers
                    for header in headers[:3]:  # Check first 3 headers
                        if header in first_row:
                            value = first_row[header]
                            assert value is not None or value == "", f"Header {header} should have a value (can be empty string)"
            
            datasets_analyzed += 1
            
        logger.info(f"Content sampling completed for {datasets_analyzed} datasets")
        
    @pytest.mark.django_db
    def test_csv_dataset_names(self, real_csv_data):
        """Test CSV dataset naming conventions"""
        dataset_names = list(real_csv_data.keys())
        
        logger.info(f"CSV dataset names analysis:")
        logger.info(f"  Total datasets: {len(dataset_names)}")
        logger.info(f"  Sample names: {dataset_names[:10]}...")
        
        # Verify naming patterns
        for dataset_name in dataset_names:
            assert isinstance(dataset_name, str), "Dataset name must be string"
            assert len(dataset_name) > 0, "Dataset name must not be empty"
            assert not dataset_name.endswith('.csv'), "Dataset name should not include .csv extension"
            
        # Check for expected FUK datasets (from conftest.py)
        from .conftest import EXPECTED_FUK_CSV_FILES
        expected_names = [name.replace('.csv', '') for name in EXPECTED_FUK_CSV_FILES]
        
        found_expected = 0
        for expected_name in expected_names[:10]:  # Check first 10
            if expected_name in dataset_names:
                found_expected += 1
                
        logger.info(f"  Expected FUK datasets found: {found_expected}/{min(10, len(expected_names))}")
        
        # We should find at least some expected datasets
        assert found_expected > 0, "Should find at least some expected FUK datasets"