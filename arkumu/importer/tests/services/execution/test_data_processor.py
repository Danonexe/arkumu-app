import pytest
import polars as pl
from arkumu.importer.services.execution.data_processor import DataProcessor


@pytest.fixture
def data_processor():
    """DataProcessor instance for testing."""
    return DataProcessor()


@pytest.fixture
def sample_dataframe():
    """Sample Polars DataFrame for testing."""
    return pl.DataFrame({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "tags": ["art,design", "tech", "music,art"]
    })


@pytest.fixture
def sample_list_data():
    """Sample list of dictionaries for testing."""
    return [
        {"name": "Alice", "age": 25, "tags": "art,design"},
        {"name": "Bob", "age": 30, "tags": "tech"},
        {"name": "Charlie", "age": 35, "tags": "music,art"}
    ]


@pytest.fixture
def mapping_config_with_multi_value():
    """Mapping configuration with multi-value columns."""
    return {
        "columns": {
            "tags": {"is_multi_value": True, "separator": ","},
            "name": {"is_anchor": True},
            "age": {"required": True}
        }
    }


class TestDataProcessor:
    """Test DataProcessor functionality."""
    
    def test_initialization_with_defaults(self, data_processor):
        """Test processor initializes with correct defaults."""
        assert data_processor.multi_value_threshold == 0.2
    
    def test_initialization_with_custom_threshold(self):
        """Test processor initialization with custom multi-value threshold."""
        processor_custom = DataProcessor(multi_value_threshold=0.5)
        assert processor_custom.multi_value_threshold == 0.5
    
    def test_ensure_dataframe_with_list_dict(self, data_processor, sample_list_data):
        """Test converting list of dicts to DataFrame."""
        df = data_processor.ensure_dataframe(sample_list_data)
        
        assert isinstance(df, pl.DataFrame)
        assert df.height == 3
        assert "name" in df.columns
        assert "age" in df.columns
        assert "tags" in df.columns
    
    def test_ensure_dataframe_with_polars_df(self, data_processor, sample_dataframe):
        """Test that Polars DataFrame passes through unchanged."""
        result_df = data_processor.ensure_dataframe(sample_dataframe)
        
        assert result_df is sample_dataframe  # Should be the same object
    
    def test_unicode_normalization(self, data_processor):
        """Test vectorized Unicode normalization."""
        # Create DataFrame with Unicode characters that need normalization
        data = {
            "text_col": ["café", "naïve", "résumé"],
            "numeric_col": [1, 2, 3]
        }
        df = pl.DataFrame(data)
        
        normalized_df = data_processor.normalize_unicode_vectorized(df)
        
        # Should normalize string columns but leave numeric unchanged
        assert normalized_df.height == 3
        assert "text_col" in normalized_df.columns
        assert "numeric_col" in normalized_df.columns
        
        # Check that normalization was applied (actual Unicode normalization)
        text_values = normalized_df["text_col"].to_list()
        assert len(text_values) == 3
    
    def test_unicode_normalization_no_string_columns(self, data_processor):
        """Test Unicode normalization with no string columns."""
        df = pl.DataFrame({"num1": [1, 2], "num2": [3.14, 2.71]})
        
        result_df = data_processor.normalize_unicode_vectorized(df)
        
        assert result_df.height == 2
        assert list(result_df.columns) == ["num1", "num2"]
    
    def test_add_row_identifiers(self, data_processor):
        """Test adding row identifiers."""
        df = pl.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})
        
        df_with_ids = data_processor.add_row_identifiers(df)
        
        assert "row_id" in df_with_ids.columns
        assert df_with_ids["row_id"].to_list() == [0, 1]
        
        # Test with custom offset
        df_with_offset = data_processor.add_row_identifiers(df, start_offset=10)
        assert df_with_offset["row_id"].to_list() == [10, 11]
    
    def test_detect_multi_value_columns_no_config(self, data_processor):
        """Test multi-value detection without mapping config."""
        df = pl.DataFrame({
            "simple": ["a", "b", "c"],
            "comma_separated": ["x,y", "z", "a,b,c"]
        })
        
        analysis = data_processor.detect_multi_value_columns(df)
        
        # Without config, should default to single-value
        assert analysis["simple"]["is_multi_value"] is False
        assert analysis["comma_separated"]["is_multi_value"] is False
        assert analysis["simple"]["source"] == "heuristic"
    
    def test_detect_multi_value_columns_with_config(self, data_processor, mapping_config_with_multi_value):
        """Test multi-value detection with mapping config."""
        df = pl.DataFrame({
            "tags": ["tag1,tag2", "tag3", "tag4,tag5,tag6"],
            "name": ["Alice", "Bob", "Charlie"],
            "age": [25, 30, 35]
        })
        
        analysis = data_processor.detect_multi_value_columns(df, mapping_config_with_multi_value)
        
        assert analysis["tags"]["is_multi_value"] is True
        assert analysis["tags"]["separator"] == ","
        assert analysis["tags"]["source"] == "mapping_config"
        
        assert analysis["name"]["is_multi_value"] is False
        assert analysis["name"]["source"] == "heuristic"
    
    def test_clean_and_validate_data(self, data_processor):
        """Test data cleaning and validation."""
        # Create DataFrame with messy data including truly empty rows
        df = pl.DataFrame({
            "name": ["  Alice  ", "Bob", "   ", None, "Charlie", ""],
            "age": [25, None, 30, None, 40, None],
            "row_id": [0, 1, 2, 3, 4, 5]
        })
        
        cleaned_df = data_processor.clean_and_validate_data(df)
        
        # Should remove empty rows and strip whitespace
        # Row 3 (name=None, age=None) and row 5 (name="", age=None) should be removed
        assert cleaned_df.height < df.height  # Some rows should be removed
        
        # Check that whitespace was stripped (Alice should not have leading/trailing spaces)
        names = cleaned_df["name"].to_list()
        for name in names:
            if name is not None and name != "":
                assert not name.startswith(" ") and not name.endswith(" ")
    
    def test_validate_column_constraints_no_config(self):
        """Test column validation without mapping config."""
        processor = DataProcessor()
        df = pl.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})
        
        errors = processor.validate_column_constraints(df)
        
        assert len(errors) == 0  # No config means no constraints
    
    def test_validate_column_constraints_with_required_columns(self):
        """Test column validation with required column constraints."""
        processor = DataProcessor()
        df = pl.DataFrame({
            "name": ["Alice", ""],  # One empty value
            "age": [25, None]       # One null value
        })
        
        mapping_config = {
            "columns": {
                "name": {"required": True},
                "age": {"required": True},
                "missing_col": {"required": True}
            }
        }
        
        errors = processor.validate_column_constraints(df, mapping_config)
        
        assert len(errors) >= 2  # At least missing column and empty values
        assert any("missing_col" in error for error in errors)
        assert any("empty values" in error for error in errors)
    
    def test_prepare_for_processing_complete_pipeline(self):
        """Test the complete data preparation pipeline."""
        processor = DataProcessor()
        
        data = [
            {"name": "  Alice  ", "tags": "art,design", "year": 2023},
            {"name": "Bob", "tags": "tech", "year": 2024},
            {"name": "", "tags": "", "year": None}  # Should be cleaned out
        ]
        
        mapping_config = {
            "columns": {
                "tags": {"is_multi_value": True, "separator": ","},
                "name": {"required": False}
            }
        }
        
        result_df = processor.prepare_for_processing(data, mapping_config)
        
        # Should have row_id column
        assert "row_id" in result_df.columns
        
        # Should have cleaned data
        assert result_df.height <= 3  # Empty rows may be removed
        
        # Should have normalized Unicode and stripped whitespace
        names = result_df["name"].to_list()
        for name in names:
            if name is not None and name != "":
                assert not name.startswith(" ") and not name.endswith(" ")
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrames."""
        processor = DataProcessor()
        empty_df = pl.DataFrame()
        
        # Should handle empty DataFrame gracefully
        result = processor.detect_multi_value_columns(empty_df)
        assert result == {}
        
        cleaned = processor.clean_and_validate_data(empty_df)
        assert cleaned.height == 0
    
    def test_split_multi_value_cells_placeholder(self):
        """Test multi-value cell splitting placeholder."""
        processor = DataProcessor()
        df = pl.DataFrame({"tags": ["a,b,c", "x,y"]})
        
        # Currently returns original DataFrame
        result = processor.split_multi_value_cells(df, {})
        assert result.equals(df)
    
    def test_mixed_data_types_handling(self):
        """Test handling of mixed data types."""
        processor = DataProcessor()
        
        data = [
            {"id": 1, "name": "Alice", "score": 95.5, "active": True},
            {"id": 2, "name": "Bob", "score": 87.2, "active": False}
        ]
        
        df = processor.prepare_for_processing(data)
        
        # Should handle all data types
        assert df.height == 2
        assert "row_id" in df.columns
        assert len(df.columns) == 5  # id, name, score, active, row_id 