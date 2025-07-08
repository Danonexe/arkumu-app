"""
Tests for DataProcessor.

Tests the data processing utilities with Polars optimization,
including data cleaning, normalization, and transformation operations.
"""
import pytest
import polars as pl
from unittest.mock import Mock, patch
import unicodedata

from arkumu.importer.services.execution.data_processor import DataProcessor


class TestDataProcessor:
    """Test suite for DataProcessor"""
    
    def test_initialization(self):
        """Test DataProcessor initialization"""
        processor = DataProcessor(multi_value_threshold=0.3)
        assert processor.multi_value_threshold == 0.3
        
        # Test default threshold
        default_processor = DataProcessor()
        assert default_processor.multi_value_threshold == 0.2
    
    def test_ensure_dataframe_with_list(self, data_processor, sample_csv_data):
        """Test converting list of dictionaries to DataFrame"""
        df = data_processor.ensure_dataframe(sample_csv_data)
        
        assert isinstance(df, pl.DataFrame)
        assert df.height == len(sample_csv_data)
        assert df.width == 3  # name, age, city columns
        assert "name" in df.columns
        assert "age" in df.columns
        assert "city" in df.columns
    
    def test_ensure_dataframe_with_polars_df(self, data_processor, sample_polars_df):
        """Test that Polars DataFrame passes through unchanged"""
        result = data_processor.ensure_dataframe(sample_polars_df)
        
        assert result is sample_polars_df  # Should be the same object
        assert isinstance(result, pl.DataFrame)
    
    def test_ensure_dataframe_with_empty_list(self, data_processor):
        """Test handling of empty list"""
        df = data_processor.ensure_dataframe([])
        
        assert isinstance(df, pl.DataFrame)
        assert df.height == 0
        assert df.width == 0
    
    def test_ensure_dataframe_with_invalid_data(self, data_processor):
        """Test error handling for invalid data types"""
        with pytest.raises(TypeError, match="Data must be a Polars DataFrame or list of dictionaries"):
            data_processor.ensure_dataframe("invalid_string")
        
        with pytest.raises(ValueError, match="List data must contain only dictionaries"):
            data_processor.ensure_dataframe(["not", "dictionaries"])
        
        with pytest.raises(TypeError):
            data_processor.ensure_dataframe(123)
    
    def test_normalize_unicode_vectorized(self, data_processor, unicode_csv_data):
        """Test vectorized Unicode normalization"""
        df = data_processor.ensure_dataframe(unicode_csv_data)
        normalized_df = data_processor.normalize_unicode_vectorized(df)
        
        # Verify normalization was applied
        assert isinstance(normalized_df, pl.DataFrame)
        assert normalized_df.height == df.height
        assert normalized_df.width == df.width
        
        # Check that Unicode strings are normalized to NFC
        for row in normalized_df.iter_rows(named=True):
            for value in row.values():
                if isinstance(value, str):
                    # All strings should be in NFC form
                    assert unicodedata.normalize('NFC', value) == value
    
    def test_normalize_unicode_with_non_string_columns(self, data_processor):
        """Test Unicode normalization with mixed column types"""
        mixed_data = pl.DataFrame({
            "text_col": ["José", "François"],
            "int_col": [1, 2],
            "float_col": [1.5, 2.5],
            "bool_col": [True, False]
        })
        
        normalized_df = data_processor.normalize_unicode_vectorized(mixed_data)
        
        # Only string columns should be affected
        assert normalized_df["int_col"].to_list() == [1, 2]
        assert normalized_df["float_col"].to_list() == [1.5, 2.5]
        assert normalized_df["bool_col"].to_list() == [True, False]
        
        # String column should be normalized
        text_values = normalized_df["text_col"].to_list()
        assert all(unicodedata.normalize('NFC', val) == val for val in text_values)
    
    def test_normalize_unicode_empty_dataframe(self, data_processor):
        """Test Unicode normalization with empty DataFrame"""
        empty_df = pl.DataFrame()
        normalized_df = data_processor.normalize_unicode_vectorized(empty_df)
        
        assert normalized_df.height == 0
        assert normalized_df.width == 0
    
    def test_add_row_identifiers(self, data_processor, sample_csv_data):
        """Test adding row identifiers"""
        df = data_processor.ensure_dataframe(sample_csv_data)
        df_with_ids = data_processor.add_row_identifiers(df)
        
        assert "row_id" in df_with_ids.columns
        assert df_with_ids.height == df.height
        assert df_with_ids.width == df.width + 1
        
        # Check row IDs start from 0
        row_ids = df_with_ids["row_id"].to_list()
        assert row_ids == list(range(len(sample_csv_data)))
    
    def test_add_row_identifiers_with_offset(self, data_processor, sample_csv_data):
        """Test adding row identifiers with custom offset"""
        df = data_processor.ensure_dataframe(sample_csv_data)
        df_with_ids = data_processor.add_row_identifiers(df, start_offset=100)
        
        row_ids = df_with_ids["row_id"].to_list()
        expected_ids = list(range(100, 100 + len(sample_csv_data)))
        assert row_ids == expected_ids
    
    def test_detect_multi_value_columns_from_config(self, data_processor, multi_value_csv_data):
        """Test multi-value column detection from mapping configuration"""
        df = data_processor.ensure_dataframe(multi_value_csv_data)
        
        mapping_config = {
            "columns": {
                "skills": {
                    "is_multi_value": True,
                    "separator": ","
                },
                "hobbies": {
                    "is_multi_value": True,
                    "separator": ";"
                },
                "name": {
                    "is_multi_value": False
                }
            }
        }
        
        analysis = data_processor.detect_multi_value_columns(df, mapping_config)
        
        # Verify detection results
        assert analysis["skills"]["is_multi_value"] is True
        assert analysis["skills"]["separator"] == ","
        assert analysis["skills"]["source"] == "mapping_config"
        assert analysis["skills"]["stats"]["confidence_score"] == 1.0
        
        assert analysis["hobbies"]["is_multi_value"] is True
        assert analysis["hobbies"]["separator"] == ";"
        
        assert analysis["name"]["is_multi_value"] is False
    
    def test_detect_multi_value_columns_heuristic_disabled(self, data_processor, multi_value_csv_data):
        """Test that heuristic detection is disabled for safety"""
        df = data_processor.ensure_dataframe(multi_value_csv_data)
        
        # No mapping config - should use heuristics (but they're disabled)
        analysis = data_processor.detect_multi_value_columns(df)
        
        # All columns should be marked as not multi-value
        for column_name, column_analysis in analysis.items():
            if column_name != "row_id":
                assert column_analysis["is_multi_value"] is False
                assert column_analysis["source"] == "heuristic"
                assert column_analysis["stats"]["confidence_score"] == 0.0
    
    def test_detect_multi_value_columns_empty_dataframe(self, data_processor):
        """Test multi-value detection with empty DataFrame"""
        empty_df = pl.DataFrame()
        analysis = data_processor.detect_multi_value_columns(empty_df)
        
        assert analysis == {}
    
    def test_split_multi_value_cells_placeholder(self, data_processor, multi_value_csv_data):
        """Test multi-value cell splitting (currently a placeholder)"""
        df = data_processor.ensure_dataframe(multi_value_csv_data)
        
        multi_value_config = {
            "skills": {
                "is_multi_value": True,
                "separator": ","
            }
        }
        
        # Current implementation returns original DataFrame
        result_df = data_processor.split_multi_value_cells(df, multi_value_config)
        
        # Should return the same DataFrame for now
        assert result_df.height == df.height
        assert result_df.width == df.width
    
    def test_clean_and_validate_data_basic_cleaning(self, data_processor):
        """Test basic data cleaning and validation"""
        dirty_data = pl.DataFrame({
            "name": ["  John Doe  ", "Jane Smith", "  ", "Bob Johnson"],
            "age": ["30", "  25  ", "", "35"],
            "city": ["New York", "", "Los Angeles", "Chicago"]
        })
        
        cleaned_df = data_processor.clean_and_validate_data(dirty_data)
        
        # Should remove rows that are completely empty after cleaning
        assert cleaned_df.height <= dirty_data.height
        
        # Verify data structure is maintained
        assert set(cleaned_df.columns) == set(dirty_data.columns)
    
    def test_clean_and_validate_data_empty_dataframe(self, data_processor):
        """Test cleaning with empty DataFrame"""
        empty_df = pl.DataFrame()
        cleaned_df = data_processor.clean_and_validate_data(empty_df)
        
        assert cleaned_df.height == 0
        assert cleaned_df.width == 0
    
    def test_clean_and_validate_data_removes_empty_rows(self, data_processor):
        """Test that completely empty rows are removed"""
        data_with_empty = pl.DataFrame({
            "name": ["John", "", "  ", "Jane"],
            "age": ["30", "", "", "25"],
            "city": ["NYC", "", "   ", "LA"]
        })
        
        # Add row IDs to test exclusion from content check
        data_with_ids = data_processor.add_row_identifiers(data_with_empty)
        cleaned_df = data_processor.clean_and_validate_data(data_with_ids)
        
        # Should remove rows that have no meaningful content (excluding row_id)
        assert cleaned_df.height < data_with_ids.height
        
        # Remaining rows should have some content
        for row in cleaned_df.iter_rows(named=True):
            has_content = any(
                str(value).strip() for key, value in row.items() 
                if key != "row_id" and value is not None
            )
            assert has_content
    
    def test_validate_column_constraints_no_config(self, data_processor, sample_csv_data):
        """Test column validation with no mapping configuration"""
        df = data_processor.ensure_dataframe(sample_csv_data)
        errors = data_processor.validate_column_constraints(df)
        
        # No config means no validation errors
        assert errors == []
    
    def test_validate_column_constraints_required_columns(self, data_processor):
        """Test validation of required columns"""
        df = pl.DataFrame({
            "name": ["John", "", "Jane"],
            "age": ["30", "25", ""]
        })
        
        mapping_config = {
            "columns": {
                "name": {"required": True},
                "age": {"required": False},
                "missing_col": {"required": True}
            }
        }
        
        errors = data_processor.validate_column_constraints(df, mapping_config)
        
        # Should detect missing required column and empty values in required column
        assert len(errors) >= 1
        assert any("missing_col" in error for error in errors)
        assert any("name" in error and "empty values" in error for error in errors)
    
    def test_validate_column_constraints_data_types(self, data_processor):
        """Test validation of data type constraints"""
        df = pl.DataFrame({
            "score": ["85", "invalid", "92"]
        })
        
        mapping_config = {
            "columns": {
                "score": {"datatype": "integer"}
            }
        }
        
        # Current implementation doesn't validate data types yet
        errors = data_processor.validate_column_constraints(df, mapping_config)
        
        # Should be empty for now (validation not implemented)
        assert isinstance(errors, list)
    
    def test_prepare_for_processing_complete_pipeline(self, data_processor, sample_csv_data):
        """Test the complete data preparation pipeline"""
        prepared_df = data_processor.prepare_for_processing(sample_csv_data)
        
        # Verify pipeline steps were applied
        assert isinstance(prepared_df, pl.DataFrame)
        assert "row_id" in prepared_df.columns
        assert prepared_df.height > 0
        
        # Check Unicode normalization was applied
        for row in prepared_df.iter_rows(named=True):
            for value in row.values():
                if isinstance(value, str):
                    assert unicodedata.normalize('NFC', value) == value
    
    def test_prepare_for_processing_with_mapping_config(self, data_processor, sample_csv_data, simple_mapping_config):
        """Test preparation pipeline with mapping configuration"""
        prepared_df = data_processor.prepare_for_processing(sample_csv_data, simple_mapping_config)
        
        assert isinstance(prepared_df, pl.DataFrame)
        assert "row_id" in prepared_df.columns
        
        # Should complete without errors even with mapping config
        assert prepared_df.height > 0
    
    def test_prepare_for_processing_empty_data(self, data_processor):
        """Test preparation pipeline with empty data"""
        prepared_df = data_processor.prepare_for_processing([])
        
        assert isinstance(prepared_df, pl.DataFrame)
        assert prepared_df.height == 0
    
    def test_prepare_for_processing_polars_input(self, data_processor, sample_polars_df):
        """Test preparation pipeline with Polars DataFrame input"""
        prepared_df = data_processor.prepare_for_processing(sample_polars_df)
        
        assert isinstance(prepared_df, pl.DataFrame)
        assert "row_id" in prepared_df.columns
        assert prepared_df.height == sample_polars_df.height
        assert prepared_df.width == sample_polars_df.width + 1  # +1 for row_id


class TestDataProcessorPerformance:
    """Performance tests for DataProcessor"""
    
    def test_large_dataset_unicode_normalization(self, data_processor, performance_test_data):
        """Test Unicode normalization performance with large dataset"""
        # Use subset for testing
        test_data = performance_test_data[:5000]
        df = data_processor.ensure_dataframe(test_data)
        
        import time
        start_time = time.time()
        
        normalized_df = data_processor.normalize_unicode_vectorized(df)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify results
        assert normalized_df.height == df.height
        assert normalized_df.width == df.width
        
        # Performance should be reasonable
        assert processing_time < 5.0  # Should complete within 5 seconds
        
        print(f"Unicode normalization: {len(test_data)} rows in {processing_time:.3f}s")
    
    def test_large_dataset_cleaning(self, data_processor, performance_test_data):
        """Test data cleaning performance with large dataset"""
        # Use subset for testing
        test_data = performance_test_data[:5000]
        df = data_processor.ensure_dataframe(test_data)
        
        import time
        start_time = time.time()
        
        cleaned_df = data_processor.clean_and_validate_data(df)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify results
        assert cleaned_df.height <= df.height
        
        # Performance should be reasonable
        assert processing_time < 10.0  # Should complete within 10 seconds
        
        print(f"Data cleaning: {len(test_data)} rows in {processing_time:.3f}s")
    
    def test_complete_pipeline_performance(self, data_processor, performance_test_data):
        """Test complete preparation pipeline performance"""
        # Use subset for testing
        test_data = performance_test_data[:5000]
        
        import time
        start_time = time.time()
        
        prepared_df = data_processor.prepare_for_processing(test_data)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Verify results
        assert isinstance(prepared_df, pl.DataFrame)
        assert "row_id" in prepared_df.columns
        assert prepared_df.height > 0
        
        # Performance should be reasonable
        assert processing_time < 15.0  # Should complete within 15 seconds
        
        print(f"Complete pipeline: {len(test_data)} rows in {processing_time:.3f}s")


class TestDataProcessorEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_extremely_long_strings(self, data_processor):
        """Test handling of extremely long strings"""
        long_string = "x" * 100000  # 100KB string
        data = [{"long_field": long_string, "normal_field": "normal"}]
        
        df = data_processor.ensure_dataframe(data)
        normalized_df = data_processor.normalize_unicode_vectorized(df)
        
        # Should handle long strings without errors
        assert normalized_df.height == 1
        assert len(normalized_df["long_field"][0]) == 100000
    
    def test_null_and_none_values(self, data_processor):
        """Test handling of null and None values"""
        data = [
            {"name": "John", "age": None},
            {"name": None, "age": "30"},
            {"name": "", "age": ""}
        ]
        
        df = data_processor.ensure_dataframe(data)
        cleaned_df = data_processor.clean_and_validate_data(df)
        
        # Should handle null values gracefully
        assert isinstance(cleaned_df, pl.DataFrame)
    
    def test_mixed_unicode_normalization_forms(self, data_processor):
        """Test normalization of mixed Unicode forms"""
        # Create strings in different normalization forms
        nfc_string = "café"  # NFC form
        nfd_string = unicodedata.normalize('NFD', "café")  # NFD form
        
        data = [
            {"text": nfc_string},
            {"text": nfd_string}
        ]
        
        df = data_processor.ensure_dataframe(data)
        normalized_df = data_processor.normalize_unicode_vectorized(df)
        
        # All strings should be in NFC form
        for text_val in normalized_df["text"]:
            assert unicodedata.normalize('NFC', text_val) == text_val
    
    def test_special_characters_and_control_codes(self, data_processor):
        """Test handling of special characters and control codes"""
        special_data = [
            {"text": "Hello\tWorld"},  # Tab
            {"text": "Hello\nWorld"},  # Newline
            {"text": "Hello\r\nWorld"},  # Windows line ending
            {"text": "Hello\x00World"},  # Null character
            {"text": "Hello\x1fWorld"}  # Control character
        ]
        
        df = data_processor.ensure_dataframe(special_data)
        cleaned_df = data_processor.clean_and_validate_data(df)
        
        # Should handle special characters gracefully
        assert isinstance(cleaned_df, pl.DataFrame)
        assert cleaned_df.height > 0
    
    def test_dataframe_with_no_string_columns(self, data_processor):
        """Test DataFrame with only numeric/boolean columns"""
        numeric_df = pl.DataFrame({
            "int_col": [1, 2, 3],
            "float_col": [1.1, 2.2, 3.3],
            "bool_col": [True, False, True]
        })
        
        normalized_df = data_processor.normalize_unicode_vectorized(numeric_df)
        
        # Should return unchanged DataFrame
        assert normalized_df.equals(numeric_df)
    
    def test_very_wide_dataframe(self, data_processor):
        """Test handling of DataFrame with many columns"""
        # Create DataFrame with 100 columns
        wide_data = {f"col_{i}": [f"value_{i}"] for i in range(100)}
        wide_df = pl.DataFrame(wide_data)
        
        normalized_df = data_processor.normalize_unicode_vectorized(wide_df)
        cleaned_df = data_processor.clean_and_validate_data(normalized_df)
        
        # Should handle wide DataFrames
        assert normalized_df.width == 100
        assert cleaned_df.width == 100
    
    def test_column_names_with_unicode(self, data_processor):
        """Test handling of Unicode column names"""
        unicode_columns_data = [
            {"名前": "田中", "年齢": "30", "città": "東京"},
            {"名前": "佐藤", "年齢": "25", "città": "大阪"}
        ]
        
        df = data_processor.ensure_dataframe(unicode_columns_data)
        prepared_df = data_processor.prepare_for_processing(unicode_columns_data)
        
        # Should handle Unicode column names
        assert isinstance(prepared_df, pl.DataFrame)
        assert "名前" in prepared_df.columns
        assert "年齢" in prepared_df.columns
        assert "città" in prepared_df.columns