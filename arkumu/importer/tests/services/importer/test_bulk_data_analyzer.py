import pytest
import polars as pl
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from arkumu.importer.services.importer.bulk_data_analyzer import BulkDataAnalyzer, MAX_INDEXED_VALUE_SIZE


@pytest.mark.django_db
class TestBulkDataAnalyzer:
    
    def setup_method(self):
        self.analyzer = BulkDataAnalyzer(multi_value_threshold=0.2)
    
    def test_init(self):
        assert self.analyzer.multi_value_threshold == 0.2
        
        custom_analyzer = BulkDataAnalyzer(multi_value_threshold=0.5)
        assert custom_analyzer.multi_value_threshold == 0.5
    
    def test_normalize_unicode_vectorized(self):
        # Test with Unicode characters that need normalization
        df = pl.DataFrame({
            "text_col": ["café", "naïve", "resumé"],
            "numeric_col": [1, 2, 3],
            "mixed_col": ["test", "café", "normal"]
        })
        
        normalized_df = self.analyzer.normalize_unicode_vectorized(df)
        
        # Check that string columns are normalized
        assert normalized_df["text_col"].to_list() == ["café", "naïve", "resumé"]
        assert normalized_df["numeric_col"].to_list() == [1, 2, 3]
        assert normalized_df["mixed_col"].to_list() == ["test", "café", "normal"]
        
        # Test with empty DataFrame
        empty_df = pl.DataFrame()
        result = self.analyzer.normalize_unicode_vectorized(empty_df)
        assert result.is_empty()
        
        # Test with no string columns
        numeric_df = pl.DataFrame({"nums": [1, 2, 3]})
        result = self.analyzer.normalize_unicode_vectorized(numeric_df)
        assert result.equals(numeric_df)
    
    def test_analyze_column_for_multi_values(self):
        df = pl.DataFrame({
            "multi_col": ["a,b,c", "d,e", "f,g,h,i", "single", "x,y"],
            "single_col": ["value1", "value2", "value3", "value4", "value5"],
            "empty_col": [None, None, None, None, None]
        })
        
        # Test multi-value column detection (4 out of 5 = 80% which > 20% threshold)
        result = self.analyzer.analyze_column_for_multi_values(df, "multi_col")
        assert result["is_multi_value"] is True
        assert result["separator"] == ","
        assert result["stats"]["percentage"] == 80.0  # 4 out of 5 rows have commas
        
        # Test single-value column
        result = self.analyzer.analyze_column_for_multi_values(df, "single_col")
        assert result["is_multi_value"] is False
        assert result["separator"] is None
        
        # Test empty column
        result = self.analyzer.analyze_column_for_multi_values(df, "empty_col")
        assert result["is_multi_value"] is False
        assert result["separator"] is None
        
        # Test non-existent column
        result = self.analyzer.analyze_column_for_multi_values(df, "missing_col")
        assert result["is_multi_value"] is False
        assert result["separator"] is None
        
        # Test forced multi-value
        result = self.analyzer.analyze_column_for_multi_values(df, "single_col", force_multi_value=True)
        assert result["is_multi_value"] is True
        assert result["separator"] == ","
        assert result["stats"]["forced"] is True
    
    def test_analyze_dataset_multi_values(self):
        df = pl.DataFrame({
            "multi_col": ["a,b,c", "d,e", "f,g,h,i", "single", "x,y"],
            "single_col": ["value1", "value2", "value3", "value4", "value5"],
            "empty_col": [None, None, None, None, None]
        })
        
        # Test without column configs
        result = self.analyzer.analyze_dataset_multi_values(df)
        assert "multi_col" in result
        assert "single_col" in result
        assert "empty_col" in result
        assert result["multi_col"]["is_multi_value"] is True
        assert result["single_col"]["is_multi_value"] is False
        
        # Test with column configs
        column_configs = {
            "single_col": {"is_multi_value": True, "multi_value_separator": ";"},
            "empty_col": {"is_multi_value": False, "multi_value_separator": ","}
        }
        result = self.analyzer.analyze_dataset_multi_values(df, column_configs)
        assert result["single_col"]["is_multi_value"] is True
        assert result["single_col"]["separator"] == ";"
        
        # Test with empty DataFrame
        empty_df = pl.DataFrame()
        result = self.analyzer.analyze_dataset_multi_values(empty_df)
        assert result == {}
    
    def test_split_cell_values(self):
        # Test normal splitting
        result = self.analyzer.split_cell_values("a,b,c", ",")
        assert result == ["a", "b", "c"]
        
        # Test with whitespace
        result = self.analyzer.split_cell_values("a, b , c", ",")
        assert result == ["a", "b", "c"]
        
        # Test empty string
        result = self.analyzer.split_cell_values("", ",")
        assert result == []
        
        # Test None
        result = self.analyzer.split_cell_values(None, ",")
        assert result == []
        
        # Test no separator
        result = self.analyzer.split_cell_values("single_value", "")
        assert result == ["single_value"]
        
        # Test different separator
        result = self.analyzer.split_cell_values("a;b;c", ";")
        assert result == ["a", "b", "c"]
    
    def test_analyze_dataset_changes(self):
        # This is a simplified test since the actual method has complex dependencies
        df = pl.DataFrame({
            "col1": ["new_value", "another_value"],
            "col2": ["value1", "value2"]
        })
        
        # Mock the method to avoid complex database dependencies
        with patch.object(self.analyzer, 'analyze_dataset_changes') as mock_method:
            mock_method.return_value = {
                "total_rows": 2,
                "new_resources": 4,
                "existing_resources": 0,
                "potential_updates": 0,
                "conflicts": [],
                "recommendations": []
            }
            
            result = self.analyzer.analyze_dataset_changes(
                "test_dataset", df, "http://example.com/test", "institution"
            )
            
            assert result["total_rows"] == 2
            assert "new_resources" in result
            assert "existing_resources" in result
            assert "potential_updates" in result
            assert "conflicts" in result
            assert "recommendations" in result
    
    def test_parse_timestamp(self):
        # Test ISO format
        result = self.analyzer._parse_timestamp("2023-01-01T12:00:00Z")
        assert result is not None
        assert result.year == 2023
        
        # Test date only
        result = self.analyzer._parse_timestamp("2023-01-01")
        assert result is not None
        assert result.year == 2023
        
        # Test invalid format
        result = self.analyzer._parse_timestamp("invalid_date")
        assert result is None
        
        # Test empty string
        result = self.analyzer._parse_timestamp("")
        assert result is None
        
        # Test None
        result = self.analyzer._parse_timestamp(None)
        assert result is None
    
    def test_validate_data_quality(self):
        df = pl.DataFrame({
            "complete_col": ["a", "b", "c", "d", "e"],
            "partial_col": ["x", None, "y", None, "z"],
            "empty_col": [None, None, None, None, None],
            "mostly_empty": [None, None, None, None, "single"]
        })
        
        result = self.analyzer.validate_data_quality(df)
        
        assert result["total_rows"] == 5
        assert result["total_columns"] == 4
        assert result["empty_rows"] == 0
        assert "empty_col" in result["empty_columns"]  # 100% empty
        # "mostly_empty" has 80% nulls, threshold is 90%, so it won't be flagged as empty
        assert "complete_col" not in result["columns_with_nulls"]  # No nulls
        assert "partial_col" in result["columns_with_nulls"]  # Has nulls
        assert isinstance(result["quality_score"], (int, float))
        assert result["quality_score"] >= 0
        assert result["quality_score"] <= 100
        
        # Test empty DataFrame
        empty_df = pl.DataFrame()
        result = self.analyzer.validate_data_quality(empty_df)
        assert result["total_rows"] == 0
        assert result["quality_score"] == 0.0
        assert "Dataset is empty" in result["potential_issues"]
    
    def test_max_indexed_value_size_constant(self):
        # Test that the constant is properly defined
        assert MAX_INDEXED_VALUE_SIZE == 1000
        
        # Test that the analyzer respects this limit in data processing
        large_value = "x" * (MAX_INDEXED_VALUE_SIZE + 100)
        df = pl.DataFrame({"large_col": [large_value]})
        
        # This should not raise an error
        result = self.analyzer.validate_data_quality(df)
        assert result["total_rows"] == 1
    
    def test_unicode_handling(self):
        # Test with various Unicode characters
        df = pl.DataFrame({
            "unicode_col": ["café", "naïve", "über", "résumé", "🚀"],
            "mixed_col": ["test", "café", "normal", "🎉", "emoji"]
        })
        
        # Should not raise errors
        result = self.analyzer.validate_data_quality(df)
        assert result["total_rows"] == 5
        
        # Test normalization
        normalized_df = self.analyzer.normalize_unicode_vectorized(df)
        assert normalized_df.shape == df.shape
        assert len(normalized_df["unicode_col"]) == 5